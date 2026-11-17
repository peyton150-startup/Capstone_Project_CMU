"""Collector-only FastAPI ingress security, bounded body and ACK contract."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from capstone.api.live_ingest import router_for
from capstone.ingestion.cloud_contract import IngestBatch, validate_record
from tests.test_cloud_pilot import change, scope


class FakeRepository:
    def __init__(self):
        self.accepted = []

    def accept(self, batch, approved_scope):
        self.accepted.append((batch, approved_scope))
        return {
            "digest": batch.digest, "next_line": batch.first_line + len(batch.records),
            "accepted": len(batch.records), "replayed": False,
        }


def client(repository, source=None):
    app = fastapi.FastAPI()
    app.include_router(
        router_for(
            "s" * 48, source or scope, repository,
        )
    )
    return TestClient(app)


def good_batch():
    source = scope()
    row = validate_record(source, change())
    return IngestBatch.build(
        scope=source, stream_id=uuid4(), first_line=0, records=[row]
    )


def test_unauthenticated_upload_is_refused_before_repository():
    store = FakeRepository()
    app = client(store)
    assert app.post("/api/v1/ingest/siemens/batches", content=b"invalid").status_code == 401
    assert store.accepted == []


def test_collector_token_produces_receipt_and_ui_token_cannot_upload():
    store = FakeRepository()
    app = client(store)
    payload = good_batch()
    endpoint = "/api/v1/ingest/siemens/batches"
    invalid = app.post(
        endpoint, json=payload.model_dump(mode="json"),
        headers={"Authorization": "Bearer viewer-not-collector"},
    )
    assert invalid.status_code == 401
    result = app.post(
        endpoint, json=payload.model_dump(mode="json"),
        headers={"Authorization": "Bearer " + "s" * 48},
    )
    assert result.status_code == 200
    assert result.json()["digest"] == payload.digest
    assert result.json()["next_line"] == 1
    assert len(store.accepted) == 1


def test_oversized_batch_and_invalid_digest_fail_before_write():
    store = FakeRepository()
    app = client(store)
    auth = {"Authorization": "Bearer " + "s" * 48}
    endpoint = "/api/v1/ingest/siemens/batches"
    assert app.post(endpoint, content=b"x" * (256 * 1024 + 1), headers=auth).status_code == 413
    batch = good_batch().model_copy(update={"digest": "a" * 64})
    assert app.post(endpoint, json=batch.model_dump(mode="json"), headers=auth).status_code == 422
    assert store.accepted == []


def test_scope_revocation_blocks_future_batches_without_server_restart():
    store = FakeRepository()
    flag = {"enabled": True}

    def approved():
        return scope().model_copy(
            update={"cloud_transfer_approved": flag["enabled"]}
        )

    app = client(store, source=approved)
    flags = {"Authorization": "Bearer " + "s" * 48}
    batch = good_batch().model_dump(mode="json")
    assert app.post("/api/v1/ingest/siemens/batches", json=batch, headers=flags).status_code == 200
    flag["enabled"] = False
    assert app.post("/api/v1/ingest/siemens/batches", json=batch, headers=flags).status_code == 403
    assert len(store.accepted) == 2  # Fake was called; real store validates consent.


def test_store_failure_response_is_sanitized():
    class Broken:
        def accept(self, *args):
            raise RuntimeError("psycopg private-password")

    app = client(Broken())
    result = app.post(
        "/api/v1/ingest/siemens/batches",
        json=good_batch().model_dump(mode="json"),
        headers={"Authorization": "Bearer " + "s" * 48},
    )
    assert result.status_code == 503
    assert "private-password" not in result.text
