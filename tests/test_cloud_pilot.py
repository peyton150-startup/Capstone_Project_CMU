"""Offline authenticated Siemens cloud ingest, authorization and replay tests."""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")

from capstone.ingestion.cloud_contract import (
    ApprovedNode,
    CloudScope,
    IngestBatch,
    scope_from_file,
    validate_record,
)
from capstone.ingestion.cloud_store import postgres_engine
from capstone.ingestion.siemens_opcua_record import (
    NodeRef,
    OpcUaGap,
    OpcUaSessionMarker,
    data_change,
)
from capstone.ingestion.cloud_uplink import (
    UploadError,
    load_cursor,
    read_batch,
    upload_once,
)

T0 = datetime(2026, 11, 17, 14, 0, tzinfo=UTC)
NODE = NodeRef(namespace_uri="urn:approved:nc", identifier="/Spindle/Speed")
SERVER = "urn:approved:siemens"


def scope(*, permit_text=False, approved=True):
    return CloudScope(
        site_id="plant-test", machine_id="cnc-1", server_uri=SERVER,
        controller_fingerprint="controller-build-verified",
        source_profile_revision="2026.11.1",
        approval_reference="SIGNED-APPROVAL-TEST-001",
        approved_by="Authorized Test Operator",
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        retention_days=30, max_sample_age_seconds=10,
        cloud_transfer_approved=approved,
        nodes=(
            ApprovedNode(
                node=NODE, permit_numeric_analysis=True, unit="rpm",
                permit_text=permit_text,
            ),
        ),
    )


def change(*, node=NODE, status_code=0, value=12000.0, value_type="Double"):
    return data_change(
        server_uri=SERVER, node=node, value=value, value_type=value_type,
        status_code=status_code, source_timestamp=T0,
        server_timestamp=T0 + timedelta(milliseconds=50),
        received_at=T0 + timedelta(milliseconds=80),
        session_epoch=1, subscription_id=10, notification_seq=12,
    ).model_dump(mode="json")


def marker(*, gap=False):
    return OpcUaSessionMarker(
        server_uri=SERVER, event="gap" if gap else "heartbeat", at=T0,
        session_epoch=1, reason="Potentially sensitive operator text",
        gap=OpcUaGap(cause="session_lost") if gap else None,
    ).model_dump(mode="json")


def test_good_approved_numeric_retains_exact_identity_and_quality():
    row = validate_record(scope(), change())
    assert row["node"] == NODE.model_dump()
    assert row["value"] == 12000.0
    assert row["analysis_eligible"] is True and row["verified_unit"] == "rpm"
    assert row["source_timestamp"] and row["server_timestamp"]
    assert row["session_epoch"] == 1 and row["notification_seq"] == 12


def test_bad_uncertain_and_missing_time_are_not_numeric_evidence():
    for status in (0x40000000, 0x80310000):
        row = validate_record(scope(), change(status_code=status))
        assert row["analysis_eligible"] is False
        assert row["verified_unit"] is None
    raw = change()
    raw["source_timestamp"] = None
    assert validate_record(scope(), raw)["analysis_eligible"] is False


def test_foreign_nodes_server_and_sensitive_text_are_rejected():
    foreign = NodeRef(namespace_uri="urn:approved:nc", identifier="/PLC/Programs")
    with pytest.raises(PermissionError):
        validate_record(scope(), change(node=foreign))
    with pytest.raises(PermissionError):
        validate_record(
            scope(), change(value="customer 123", value_type="String")
        )
    record = change()
    record["server_uri"] = "urn:other"
    with pytest.raises(PermissionError):
        validate_record(scope(), record)


def test_marker_gap_remains_but_unreviewed_text_is_redacted():
    saved = validate_record(scope(), marker(gap=True))
    assert saved["reason"] is None
    assert saved["gap"]["cause"] == "session_lost"
    assert saved["analysis_eligible"] is False


def test_batch_rejects_tampering_foreign_scope_and_raw_unsanitized_markers():
    approved = scope()
    row = validate_record(approved, change())
    batch = IngestBatch.build(
        scope=approved, stream_id=uuid4(), first_line=0, records=[row]
    )
    assert batch.authorized_lines(approved) == [row]
    changed = batch.model_copy(update={"records": [dict(row, value=9999.0)]})
    with pytest.raises(ValueError, match="digest"):
        changed.authorized_lines(approved)
    with pytest.raises(PermissionError):
        batch.authorized_lines(
            approved.model_copy(update={"machine_id": "another"})
        )
    raw_marker = marker()
    unsanitized = IngestBatch.build(
        scope=approved, stream_id=uuid4(), first_line=0, records=[raw_marker]
    )
    with pytest.raises(ValueError, match="unminimized"):
        unsanitized.authorized_lines(approved)


def test_scope_requires_active_approved_cloud_permission():
    with pytest.raises(PermissionError):
        scope(approved=False).assert_active()
    expired = scope().model_copy(update={"expires_at": T0})
    with pytest.raises(PermissionError):
        expired.assert_active()


def test_scope_file_checks_schema_and_bounds(tmp_path):
    path = tmp_path / "scope.json"
    path.write_text(scope().model_dump_json())
    assert scope_from_file(path).site_id == "plant-test"
    path.write_text("{ broken")
    with pytest.raises(RuntimeError, match="profile unavailable"):
        scope_from_file(path)


def test_resumable_uplink_never_acks_failed_cloud_transaction(tmp_path):
    capture, cursor = tmp_path / "capture.jsonl", tmp_path / "cursor.json"
    raw = change()
    raw_marker = marker(gap=True)
    capture.write_text(
        json.dumps(raw) + "\n" + json.dumps(raw_marker) + "\n"
    )
    rejected = []

    def fail(batch):
        rejected.append(batch)
        raise UploadError("simulated network interruption")

    with pytest.raises(UploadError):
        upload_once(capture, cursor, scope(), fail)
    original = load_cursor(capture, cursor)
    assert original.offset == 0 and original.next_line == 0
    accepted = []

    def succeed(batch):
        accepted.append(batch)
        return {
            "digest": batch.digest,
            "next_line": batch.first_line + len(batch.records),
            "accepted": len(batch.records),
        }

    assert upload_once(capture, cursor, scope(), succeed) == 2
    latest = load_cursor(capture, cursor)
    assert latest.offset == capture.stat().st_size
    assert latest.next_line == 2
    assert accepted[0].digest == rejected[0].digest
    assert upload_once(capture, cursor, scope(), succeed) == 0


def test_incomplete_line_is_never_sent_or_skipped(tmp_path):
    capture = tmp_path / "capture.jsonl"
    first = json.dumps(change()).encode() + b"\n"
    capture.write_bytes(first + b'{"record_type":"data_change"')
    state = load_cursor(capture, tmp_path / "cursor.json")
    batch, end = read_batch(capture, state, scope())
    assert batch is not None and len(batch.records) == 1
    assert end == len(first)


def test_modified_capture_refused_even_when_new_lines_are_appended(tmp_path):
    capture = tmp_path / "capture.jsonl"
    cursor = tmp_path / "cursor.json"
    capture.write_text(json.dumps(change()) + "\n")
    load_cursor(capture, cursor)
    original = capture.read_bytes()
    capture.write_bytes(original.replace(b"12000.0", b"12001.0", 1))
    with pytest.raises(ValueError, match="prefix changed"):
        load_cursor(capture, cursor)


def test_db_url_requires_tls_even_if_a_local_sqlite_url_is_configured():
    for url in (
        "sqlite:////tmp/pilot.db",
        "postgresql://test:secret@localhost/pilot?sslmode=disable",
        "postgresql://test:secret@localhost/pilot",
    ):
        with pytest.raises(ValueError) as error:
            postgres_engine(url)
        assert "secret" not in str(error.value)


def test_storage_migration_is_private_and_separate_from_simulator_journal():
    source = (
        Path(__file__).resolve().parents[1]
        / "migrations/supabase/live_siemens_0001.sql"
    ).read_text()
    assert "capstone_ingest.records" in source
    assert "capstone_ingest.streams" in source
    assert "FOREIGN KEY" in source and "ENABLE ROW LEVEL SECURITY" in source
    assert "REVOKE ALL" in source and "retained_until" in source
    assert "capstone_private" not in source  # Independent from PR #289.
