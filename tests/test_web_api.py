"""Read-only frontend API contract and privacy regression tests."""
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from capstone.api.app import create_app
from capstone.api.config import UiConfig
from capstone.api.readers import recorder_snapshot, safe_evaluations


def change(*, status=0, identifier="spindle", value=42.0):
    """A valid source-stamped Siemens OPC UA v2 line, not a fake HTTP API field."""
    severity = "bad" if status >> 30 == 2 else "uncertain" if status >> 30 == 1 else "good"
    return {
        "record_type": "data_change", "schema_version": 2, "source": "opcua",
        "server_uri": "urn:test", "node": {"namespace_uri": "urn:nc", "identifier": identifier,
                                          "identifier_type": "string"},
        "value": value, "value_type": "Double",
        "non_finite": None, "status": {"code": status, "severity": severity, "name": None},
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
        "server_timestamp": None, "received_at": datetime.now(timezone.utc).isoformat(),
        "session_epoch": 1, "subscription_id": 1, "notification_seq": 2,
    }


def write_lines(path, records):
    path.write_text("".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")


def test_private_file_requires_strong_token(tmp_path):
    with pytest.raises(ValueError, match="TOKEN"):
        UiConfig(capture=tmp_path / "capture.jsonl")
    with pytest.raises(ValueError, match="absolute"):
        UiConfig(capture=__import__("pathlib").Path("relative.jsonl"), token="x" * 30)


def test_capabilities_and_auth_do_not_leak_secret(tmp_path):
    path = tmp_path / "source.jsonl"
    write_lines(path, [change()])
    token = "super-secret-session-token-000001"
    client = TestClient(create_app(UiConfig(capture=path, token=token)))
    assert client.get("/api/v1/capabilities").status_code == 401
    assert client.get("/api/v1/recordings").status_code == 401
    result = client.get("/api/v1/recordings/siemens-local/health",
                        headers={"Authorization": "Bearer " + token})
    assert result.status_code == 200
    payload = result.json()
    assert token not in json.dumps(payload)
    assert str(tmp_path) not in json.dumps(payload)
    assert payload["recorder"]["subscription_state"] == "unconfirmed"
    assert payload["recorder"]["process_state"] == "unknown"
    assert payload["recorder"]["analysis_eligible"] is None


def test_bad_data_never_counts_as_valid_numeric(tmp_path):
    path = tmp_path / "source.jsonl"
    write_lines(path, [change(status=0x80000000)])
    result = recorder_snapshot(path, show_values=True)
    assert result["recorder"]["bad"] == 1
    assert result["recorder"]["good"] == 0
    assert result["recorder"]["last_good_numeric_at"] is None
    assert result["signals"][0]["analysis_eligible"] is False


def test_distinct_physical_nodes_cannot_collide(tmp_path):
    path = tmp_path / "source.jsonl"
    write_lines(path, [change(identifier="axis1"), change(identifier="axis2")])
    signals = recorder_snapshot(path)["signals"]
    assert len(signals) == 2
    assert signals[0]["id"] != signals[1]["id"]


def test_empty_and_unconfigured_are_not_healthy(tmp_path):
    assert recorder_snapshot(None)["availability"] == "not_configured"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    result = recorder_snapshot(empty)
    assert result["recorder"]["measurement_state"] == "none"
    assert result["recorder"]["connection_state"] == "unknown"


def test_partial_jsonl_does_not_fabricate_observations(tmp_path):
    path = tmp_path / "source.jsonl"
    path.write_text(json.dumps(change()) + "\n" + '{"record_type":', encoding="utf-8")
    assert recorder_snapshot(path)["recorder"]["received"] == 1


def test_audit_and_evaluator_truth_separated(tmp_path):
    exp = tmp_path / "eval.jsonl"
    write_lines(exp, [{
        "run_key": "run-1", "scenario_id": "sim-1", "seed": 5,
        "conclusion": "check load", "score": {"hidden_root_cause": "secret"},
        "internal_secret": "super-secret",
    }])
    assert "secret" not in json.dumps(safe_evaluations(exp))
    token = "very-long-evaluator-session-token"
    common = {"experiment": exp, "token": token}
    viewer = TestClient(create_app(UiConfig(**common, evaluator=False)))
    evaluator = TestClient(create_app(UiConfig(**common, evaluator=True)))
    header = {"Authorization": "Bearer " + token}
    assert viewer.get("/api/v1/evaluations", headers=header).status_code == 403
    assert evaluator.get("/api/v1/evaluations", headers=header).status_code == 200
    assert evaluator.get("/api/v1/evaluations?workspace=pilot", headers=header).status_code == 403


def test_restricted_pilot_investigation_and_no_command_routes(tmp_path):
    audit = tmp_path / "audit.jsonl"
    audit.write_text("", encoding="utf-8")
    client = TestClient(create_app(UiConfig(
        investigations=audit, token="secret-long-enough-to-be-valid",
    )))
    auth = {"Authorization": "Bearer secret-long-enough-to-be-valid"}
    assert client.get("/api/v1/investigations?workspace=pilot", headers=auth).json()["items"] == []
    assert client.post("/api/v1/recordings/start", headers=auth).status_code == 405 or \
           client.post("/api/v1/recordings/start", headers=auth).status_code == 404
    assert client.post("/api/v1/lab/runs", headers=auth).status_code in (404, 405)
