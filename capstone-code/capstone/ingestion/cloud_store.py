"""Transactional, replay-safe write side for authorized Siemens cloud captures."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from capstone.ingestion.cloud_contract import CloudScope, IngestBatch

_log = logging.getLogger(__name__)


class IngestConflict(Exception):
    """A replay is inconsistent, or line ordering/identity changed."""


def postgres_engine(url: str) -> Engine:
    """Only explicit TLS PostgreSQL; never DATABASE_URL or the Neon manual URL."""
    try:
        parsed = make_url(url)
        if parsed.drivername in ("postgres", "postgresql"):
            parsed = parsed.set(drivername="postgresql+psycopg")
        if parsed.drivername != "postgresql+psycopg":
            raise ValueError
        if parsed.query.get("sslmode") not in ("require", "verify-ca", "verify-full"):
            raise ValueError
        return create_engine(
            parsed, pool_pre_ping=True, pool_size=3, max_overflow=0,
            pool_timeout=5, connect_args={"connect_timeout": 5},
        )
    except (TypeError, ValueError):
        raise ValueError("CAPSTONE_LIVE_DB_URL requires PostgreSQL with TLS") from None


class SiemensCloudRepository:
    """Only ACK after *all* rows and cursor commit; retries are safe."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def close(self) -> None:
        self.engine.dispose()

    def accept(self, batch: IngestBatch, scope: CloudScope) -> dict:
        rows = batch.authorized_lines(scope)
        received_at = datetime.now(timezone.utc)
        retained_until = received_at + timedelta(days=scope.retention_days)
        identity = {
            "site": scope.site_id,
            "machine": scope.machine_id,
            "stream": batch.stream_id,
        }
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text("""
                        INSERT INTO capstone_ingest.streams
                            (site_id, machine_id, stream_id, server_uri,
                             controller_fingerprint, scope_fingerprint)
                        VALUES (:site, :machine, :stream, :server,
                                :controller, :scope)
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        **identity, "server": scope.server_uri,
                        "controller": scope.controller_fingerprint,
                        "scope": scope.fingerprint,
                    },
                )
                state = connection.execute(
                    text("""
                        SELECT next_line, server_uri, controller_fingerprint,
                               scope_fingerprint
                          FROM capstone_ingest.streams
                         WHERE site_id=:site AND machine_id=:machine
                           AND stream_id=:stream FOR UPDATE
                    """),
                    identity,
                ).mappings().one()
                if (
                    state["server_uri"] != scope.server_uri
                    or state["controller_fingerprint"] != scope.controller_fingerprint
                    or state["scope_fingerprint"] != scope.fingerprint
                ):
                    raise IngestConflict("capture scope changed; start a new stream")
                previous = connection.execute(
                    text("""
                        SELECT next_line FROM capstone_ingest.batches
                         WHERE site_id=:site AND machine_id=:machine
                           AND stream_id=:stream AND digest=:digest
                    """),
                    {**identity, "digest": batch.digest},
                ).scalar_one_or_none()
                expected_next = batch.first_line + len(rows)
                if previous is not None:
                    if previous != expected_next:
                        raise IngestConflict("batch digest conflicts with receipt")
                    return {
                        "digest": batch.digest,
                        "next_line": expected_next,
                        "accepted": len(rows),
                        "replayed": True,
                    }
                if state["next_line"] != batch.first_line:
                    raise IngestConflict("out-of-order or modified capture stream")
                for index, row in enumerate(rows, start=batch.first_line):
                    canonical = json.dumps(
                        row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    )
                    timestamp = (
                        row.get("source_timestamp")
                        if row["record_type"] == "data_change" else row.get("at")
                    )
                    quality = (
                        row["status"]["severity"]
                        if row["record_type"] == "data_change" else None
                    )
                    connection.execute(
                        text("""
                            INSERT INTO capstone_ingest.records
                                (site_id, machine_id, stream_id, line_number,
                                 server_uri, record_type, event_at, received_at,
                                 quality, analysis_eligible, payload, sha256,
                                 retained_until)
                            VALUES
                                (:site, :machine, :stream, :line, :server,
                                 :type, :event_at, :received_at, :quality,
                                 :eligible, CAST(:payload AS jsonb), :sha,
                                 :retained_until)
                        """),
                        {
                            **identity, "line": index, "server": scope.server_uri,
                            "type": row["record_type"],
                            "event_at": timestamp,
                            "received_at": row.get("received_at"),
                            "quality": quality,
                            "eligible": row["analysis_eligible"],
                            "payload": canonical,
                            "sha": hashlib.sha256(canonical.encode()).hexdigest(),
                            "retained_until": retained_until,
                        },
                    )
                connection.execute(
                    text("""
                        INSERT INTO capstone_ingest.batches
                            (site_id, machine_id, stream_id, digest,
                             first_line, next_line)
                        VALUES (:site, :machine, :stream, :digest, :start, :end)
                    """),
                    {
                        **identity, "digest": batch.digest,
                        "start": batch.first_line, "end": expected_next,
                    },
                )
                connection.execute(
                    text("""
                        UPDATE capstone_ingest.streams
                           SET next_line=:next, last_accepted_at=now()
                         WHERE site_id=:site AND machine_id=:machine
                           AND stream_id=:stream
                    """),
                    {**identity, "next": expected_next},
                )
        except SQLAlchemyError:
            _log.warning("siemens_cloud_transaction_failed")
            raise RuntimeError("Durable Siemens storage unavailable") from None
        return {
            "digest": batch.digest, "next_line": expected_next,
            "accepted": len(rows), "replayed": False,
        }
