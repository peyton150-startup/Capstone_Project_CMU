"""On-site, resumable Siemens JSONL uploader; never talks to the CNC controller.

The recorder writes an independent durable local spool. This process reads
only complete JSONL lines, validates the approved scope before egress, and
advances a fsynced local cursor ONLY after the cloud transaction ACK.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from capstone.ingestion.cloud_contract import scope_from_file
from capstone.ingestion.cloud_contract import CloudScope, IngestBatch, validate_record
from capstone.ingestion.siemens_opcua_record import NodeRef
from capstone.ingestion.privacy import refusal

MAX_LINE_BYTES = 64 * 1024
MAX_BATCH_BYTES = 120 * 1024


class UploadError(Exception):
    """A safe retryable upload failure; checkpoint is unchanged."""


class Cursor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_path: str
    stream_id: UUID
    next_line: int = Field(ge=0)
    offset: int = Field(ge=0)
    prefix_count: int = Field(ge=0, le=256)
    prefix_sha256: str


def _prefix(path: Path, count: int) -> str:
    with path.open("rb") as source:
        return hashlib.sha256(source.read(count)).hexdigest()


def _atomic_save(path: Path, state: Cursor) -> None:
    """Atomic cursor replacement with durable file and parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "wb") as output:
            output.write(state.model_dump_json().encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def load_cursor(capture: Path, path: Path) -> Cursor:
    if not capture.is_file():
        raise ValueError("approved Siemens capture file is missing")
    source = str(capture.resolve())
    if path.exists():
        state = Cursor.model_validate_json(path.read_bytes())
        if state.source_path != source:
            raise ValueError("cursor belongs to another capture file")
        if capture.stat().st_size < state.offset:
            raise ValueError("capture was truncated: use a new approved stream")
        if _prefix(capture, state.prefix_count) != state.prefix_sha256:
            raise ValueError("capture prefix changed: do not replay modified data")
        return state
    count = min(capture.stat().st_size, 256)
    state = Cursor(
        source_path=source, stream_id=uuid4(), next_line=0, offset=0,
        prefix_count=count, prefix_sha256=_prefix(capture, count),
    )
    _atomic_save(path, state)
    return state


@contextmanager
def exclusive_cursor(path: Path):
    """Refuse concurrent uploaders for the same state; stale locks need review."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def read_batch(
    capture: Path, state: Cursor, scope: CloudScope,
) -> tuple[IngestBatch | None, int]:
    """Bounded memory; an incomplete final line is never submitted or skipped."""
    records: list[dict] = []
    used = 0
    end = state.offset
    with capture.open("rb") as source:
        source.seek(state.offset)
        for _ in range(64):
            start = source.tell()
            line = source.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_LINE_BYTES:
                raise ValueError("oversize line in Siemens capture")
            if not line.endswith(b"\n"):
                break
            if records and used + len(line) > MAX_BATCH_BYTES:
                source.seek(start)
                break
            if not line.strip():
                raise ValueError("blank line in Siemens capture")
            payload = validate_record(
                scope, json.loads(line.decode("utf-8"))
            )
            records.append(payload)
            used += len(line)
            end = source.tell()
    if not records:
        return None, end
    return IngestBatch.build(
        scope=scope, stream_id=state.stream_id,
        first_line=state.next_line, records=records,
    ), end


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def send_batch(endpoint: str, token: str, batch: IngestBatch) -> dict:
    """HTTPS only, redirects forbidden to avoid bearer-token leakage."""
    url = urlsplit(endpoint)
    if (
        url.scheme != "https" or not url.hostname or url.username
        or url.password or url.query or url.fragment or not endpoint.endswith(
            "/api/v1/ingest/siemens/batches"
        )
    ):
        raise ValueError("Uploader requires a trusted HTTPS ingest endpoint")
    if len(token) < 32:
        raise ValueError("Uploader requires a distinct strong collector token")
    data = batch.model_dump_json().encode("utf-8")
    if len(data) > 256 * 1024:
        raise ValueError("serialized capture batch exceeds ingress limit")
    request = Request(
        endpoint, data=data, method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=15) as response:
            result = json.loads(response.read(4097))
    except HTTPError as error:
        raise UploadError(f"Cloud receiver returned HTTP {error.code}") from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise UploadError("Cloud receiver unreachable or sent invalid receipt") from None
    if not isinstance(result, dict) or (
        result.get("digest") != batch.digest
        or result.get("next_line") != batch.first_line + len(batch.records)
        or result.get("accepted") != len(batch.records)
    ):
        raise UploadError("Cloud receipt did not match submitted batch")
    return result


def upload_once(
    capture: Path, cursor_path: Path, scope: CloudScope,
    send: Callable[[IngestBatch], dict],
) -> int:
    """Safe to rerun after timeout/crash; only committed cloud data is ACKed."""
    scope.assert_active()
    uploaded = 0
    with exclusive_cursor(cursor_path):
        state = load_cursor(capture, cursor_path)
        while True:
            batch, end = read_batch(capture, state, scope)
            if batch is None:
                return uploaded
            acknowledgement = send(batch)
            if (
                acknowledgement.get("digest") != batch.digest
                or acknowledgement.get("next_line")
                != state.next_line + len(batch.records)
                or acknowledgement.get("accepted") != len(batch.records)
            ):
                raise UploadError("Cloud acknowledgement mismatch")
            count = state.prefix_count or min(capture.stat().st_size, 256)
            new_state = state.model_copy(
                update={
                    "offset": end,
                    "next_line": acknowledgement["next_line"],
                    "prefix_count": count,
                    "prefix_sha256": _prefix(capture, count),
                }
            )
            _atomic_save(cursor_path, new_state)
            state = new_state
            uploaded += len(batch.records)


def validate_collector_scope(config_path: Path, scope: CloudScope) -> None:
    """Stop cloud export if collector subscription exceeds approved nodes."""
    if (
        not config_path.is_absolute()
        or refusal(config_path, "--collector-config") is not None
        or config_path.stat().st_size > 32_768
    ):
        raise ValueError("collector config must be a private bounded file")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("expected_server_uri") != scope.server_uri:
        raise PermissionError("collector source differs from cloud approval")
    observed = {
        NodeRef.model_validate(node).key for node in config.get("nodes", [])
    }
    allowed = {item.node.key for item in scope.nodes}
    if not observed or not observed <= allowed:
        raise PermissionError("collector includes unapproved subscribed nodes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upload already-approved on-site Siemens JSONL, never CNC commands"
    )
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--cursor", required=True, type=Path)
    parser.add_argument("--scope", required=True, type=Path)
    parser.add_argument("--collector-config", required=True, type=Path)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token-env", default="CAPSTONE_LIVE_INGEST_TOKEN")
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args(argv)
    if args.interval < 1:
        parser.error("polling interval must be at least one second")
    for name, path in (
        ("--capture", args.capture), ("--cursor", args.cursor),
        ("--scope", args.scope),
        ("--collector-config", args.collector_config),
    ):
        if not path.is_absolute() or refusal(path, name) is not None:
            parser.error(f"{name} must be an absolute path outside a Git checkout")
    # Validate the endpoint before reading a single capture line.
    token = os.environ.get(args.token_env, "")
    endpoint = args.endpoint
    if urlsplit(endpoint).scheme != "https" or len(token) < 32:
        parser.error("HTTPS ingest endpoint and strong collector token required")
    try:
        while True:
            scope = scope_from_file(args.scope)
            validate_collector_scope(args.collector_config, scope)
            count = upload_once(
                args.capture, args.cursor, scope,
                lambda batch: send_batch(endpoint, token, batch),
            )
            print(f"cloud Siemens records acknowledged: {count}", flush=True)
            if not args.follow:
                return 0
            time.sleep(args.interval)
    except (UploadError, OSError, ValueError, PermissionError) as error:
        # No secrets, OEM text, JSON rows or raw HTTP bodies on stdout.
        print(f"upload halted safely: {type(error).__name__}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
