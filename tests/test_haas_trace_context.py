"""Safe end-to-end correlation identifiers without logging source payloads."""

import json
from io import StringIO

import pytest

from capstone.observability import EventLogger


def test_collector_incident_correlation_keeps_structured_metadata_only():
    stream = StringIO()
    logger = EventLogger(stream)
    logger.log_event(
        "haas.capture_qualified",
        capture_session_id="capture-001",
        incident_id="incident-001",
        run_id="run-001",
        investigation_id="investigation-001",
        evidence_id="E1",
        success=True,
        counts={"accepted": 4, "rejected": 1},
    )
    row = json.loads(stream.getvalue())
    assert row["capture_session_id"] == "capture-001"
    assert row["incident_id"] == "incident-001"
    assert row["counts"] == {"accepted": 4, "rejected": 1}
    assert "payload" not in row


def test_invalid_correlation_identifier_is_never_logged():
    stream = StringIO()
    logger = EventLogger(stream)
    with pytest.raises(ValueError, match="capture_session_id"):
        logger.log_event("haas.test", capture_session_id="PRIVATE FACTORY PROGRAM")
    assert not stream.getvalue()
