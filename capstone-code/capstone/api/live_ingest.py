"""Non-browser authenticated Siemens batch ingress for stateless Render FastAPI.

No CNC network access or controller operations occur on the cloud server.
The verified on-site collector remains an independent read-only process.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from capstone.ingestion.cloud_contract import CloudScope, IngestBatch, scope_from_file
from capstone.ingestion.cloud_store import (
    IngestConflict,
    SiemensCloudRepository,
    postgres_engine,
)

MAX_UPLOAD_BYTES = 256 * 1024


def router_for(
    token: str,
    scope: Callable[[], CloudScope],
    repository: SiemensCloudRepository,
) -> APIRouter:
    if not token or len(token) < 32:
        raise ValueError("CAPSTONE_LIVE_INGEST_TOKEN must be at least 32 characters")
    router = APIRouter()

    @router.post("/api/v1/ingest/siemens/batches")
    async def ingest(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict:
        # Authorization BEFORE reading an untrusted body; this token is separate
        # from all browser/operator/evaluator credentials.
        supplied = (
            authorization[len("Bearer ") :]
            if authorization and authorization.startswith("Bearer ")
            else ""
        )
        if not hmac.compare_digest(supplied, token):
            raise HTTPException(
                status_code=401, detail="Collector authorization required"
            )
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Capture batch too large")
        try:
            batch = IngestBatch.model_validate_json(bytes(body))
            source = scope()
            source.assert_active()
            batch.authorized_lines(source)
            return repository.accept(batch, source)
        except PermissionError:
            raise HTTPException(
                status_code=403, detail="Capture scope not authorized"
            ) from None
        except (ValueError, ValidationError):
            raise HTTPException(
                status_code=422, detail="Invalid Siemens capture batch"
            ) from None
        except IngestConflict:
            raise HTTPException(
                status_code=409, detail="Capture stream conflict"
            ) from None
        except RuntimeError:
            raise HTTPException(
                status_code=503, detail="Durable Siemens storage unavailable"
            ) from None

    return router


def router_from_env(browser_tokens: tuple[str | None, ...] = ()) -> APIRouter | None:
    """No endpoint, connection or file I/O until explicitly enabled."""
    if os.getenv("CAPSTONE_LIVE_INGEST_ENABLED") != "1":
        return None
    token = os.getenv("CAPSTONE_LIVE_INGEST_TOKEN", "")
    if not token or token in browser_tokens:
        raise ValueError("Collector token must be distinct from UI tokens")
    url = os.getenv("CAPSTONE_LIVE_DB_URL", "")
    path = Path(os.getenv("CAPSTONE_LIVE_SCOPE_FILE", ""))
    if not path.is_absolute():
        raise ValueError("CAPSTONE_LIVE_SCOPE_FILE must be an absolute private path")
    # Fail startup if the approved profile is missing/malformed or expired.
    scope_from_file(path).assert_active()
    store = SiemensCloudRepository(postgres_engine(url))
    return router_for(token, lambda: scope_from_file(path), store)
