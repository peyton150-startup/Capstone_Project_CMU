"""Read-only frontend API contract and privacy regression tests."""

import json
from datetime import datetime, timedelta, timezone

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip(
        "Optional web API dependencies are installed in frontend CI",
        allow_module_level=True,
    )

from capstone.api.app import create_app  # noqa: E402
from capstone.api.config import UiConfig
from capstone.api.readers import recorder_snapshot, safe_evaluations


def change(*, status=0, identifier="spindle", value=42.0):
    """A valid source-stamped Siemens OPC UA v2 line, not a fake HTTP API field."""
    severity = (
        "bad" if status >> 30 == 2 else "uncertain" if status >> 30 == 1 else "good"
    )
    return {
        "record_type": "data_change",
        "schema_version": 2,
        "source": "opcua",
        "server_uri": "urn:test",
        "node": {
            "namespace_uri": "urn:nc",
            "identifier": identifier,
            "identifier_type": "string",
        },
        "value": value,
        "value_type": "Double",
        "non_finite": None,
        "status": {"code": status, "severity": severity, "name": None},
        "source_timestamp": datetime.now(timezone.utc).isoformat(),
        "server_timestamp": None,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "session_epoch": 1,
        "subscription_id": 1,
        "notification_seq": 2,
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
    result = client.get(
        "/api/v1/recordings/siemens-local/health",
        headers={"Authorization": "Bearer " + token},
    )
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
    write_lines(
        exp,
        [
            {
                "run_key": "run-1",
                "scenario_id": "sim-1",
                "seed": 5,
                "conclusion": "check load",
                "score": {"hidden_root_cause": "secret"},
                "internal_secret": "super-secret",
            }
        ],
    )
    assert "secret" not in json.dumps(safe_evaluations(exp))
    token = "very-long-evaluator-session-token"
    common = {"experiment": exp, "token": token}
    viewer = TestClient(create_app(UiConfig(**common, evaluator=False)))
    evaluator = TestClient(create_app(UiConfig(**common, evaluator=True)))
    header = {"Authorization": "Bearer " + token}
    assert viewer.get("/api/v1/evaluations", headers=header).status_code == 403
    assert evaluator.get("/api/v1/evaluations", headers=header).status_code == 200
    assert (
        evaluator.get("/api/v1/evaluations?workspace=pilot", headers=header).status_code
        == 403
    )


def test_restricted_pilot_investigation_and_no_command_routes(tmp_path):
    audit = tmp_path / "audit.jsonl"
    audit.write_text("", encoding="utf-8")
    client = TestClient(
        create_app(
            UiConfig(
                investigations=audit,
                token="secret-long-enough-to-be-valid",
            )
        )
    )
    auth = {"Authorization": "Bearer secret-long-enough-to-be-valid"}
    assert (
        client.get("/api/v1/investigations?workspace=pilot", headers=auth).json()[
            "items"
        ]
        == []
    )
    assert (
        client.post("/api/v1/recordings/start", headers=auth).status_code == 405
        or client.post("/api/v1/recordings/start", headers=auth).status_code == 404
    )
    assert client.post("/api/v1/lab/runs", headers=auth).status_code in (404, 405)


def test_scorecards_require_evaluator_role_and_never_expose_simulator_truth(tmp_path):
    from capstone.api.readers import safe_scorecards
    records = tmp_path / "results.jsonl"
    write_lines(records, [{
        "run_key": "run-a", "scenario_id": "case-a", "seed": 7,
        "score": {
            "true_fault": "SECRET_ROOT_CAUSE",
            "true_machine_id": "SECRET_MACHINE",
            "fault_correct": None, "target_correct": None,
            "resolved": False, "action_correct": True, "tool_calls": 4,
            "causes_found": None, "wrong_causes": None,
        },
    }])
    rows = safe_scorecards(records)
    assert rows[0]["judged"] is False
    assert rows[0]["fault_correct"] is None
    assert "SECRET" not in json.dumps(rows)
    config = UiConfig(
        experiment=records, token="viewer-strong-token-0000000001",
        evaluator=True, evaluator_token="evaluator-strong-token-000000001",
        runs_enabled=True, run_db=tmp_path / "runs.db",
        run_token="runner-strong-token-00000000001",
        review_token="reviewer-strong-token-00000001",
    )
    client = TestClient(create_app(config))
    # Both evaluator endpoints must require the evaluator token when roles exist.
    list_endpoint = "/api/v1/evaluations"
    assert client.get(list_endpoint, headers={"Authorization": "Bearer " + config.token}).status_code == 403
    assert client.get(list_endpoint, headers={"Authorization": "Bearer " + config.run_token}).status_code == 403
    assert client.get(list_endpoint, headers={"Authorization": "Bearer " + config.review_token}).status_code == 403
    assert client.get(list_endpoint, headers={"Authorization": "Bearer " + config.evaluator_token}).status_code == 200
    endpoint = "/api/v1/evaluations/scorecards"
    assert client.get(endpoint, headers={"Authorization": "Bearer " + config.token}).status_code == 403
    assert client.get(endpoint, headers={"Authorization": "Bearer " + config.run_token}).status_code == 403
    result = client.get(endpoint, headers={"Authorization": "Bearer " + config.evaluator_token})
    assert result.status_code == 200
    assert result.json()["items"][0]["judged"] is False
    assert "SECRET" not in result.text


def test_legacy_mtconnect_is_version_isolated_and_never_fabricates_good(tmp_path):
    from capstone.api.readers import mtconnect_snapshot
    v1 = tmp_path / "mtconnect.jsonl"
    stamp = datetime.now(timezone.utc).isoformat()
    write_lines(v1, [
        {"record_type": "collector", "schema_version": 2, "source": "http://private-agent",
         "event": "started", "at": stamp},
        {"record_type": "observation", "schema_version": 1, "source": "http://private-agent",
         "instance_id": "1", "device": "CNC-A", "component": "Spindle",
         "data_item_id": "load", "category": "SAMPLE", "type": "Load",
         "value": "25", "available": True, "sequence": 1,
         "source_timestamp": stamp, "received_at": stamp},
        {"record_type": "observation", "schema_version": 1, "source": "http://private-agent",
         "instance_id": "1", "device": "CNC-A", "component": "Spindle",
         "data_item_id": "temp", "category": "SAMPLE", "type": "Temperature",
         "value": None, "available": False, "sequence": 2,
         "source_timestamp": stamp, "received_at": stamp},
    ])
    legacy = mtconnect_snapshot(v1)
    assert legacy["recorder"]["available"] == 1
    assert legacy["recorder"]["unavailable"] == 1
    assert "good" not in legacy["recorder"]
    assert all(item["value"] is None and item["analysis_eligible"] is False
               for item in legacy["signals"])
    assert "private-agent" not in json.dumps(legacy)
    token = "mtconnect-local-safe-viewer-token"
    client = TestClient(create_app(UiConfig(mtconnect=v1, token=token)))
    assert client.get("/api/v1/recordings/mtconnect-local/health").status_code == 401
    result = client.get("/api/v1/recordings/mtconnect-local/health",
                        headers={"Authorization": "Bearer " + token})
    assert result.status_code == 200
    assert result.json()["recorder"]["source"] == "MTConnect v1"
    assert result.json()["recorder"]["subscription_state"] == "not_applicable" if (
        "subscription_state" in result.json()["recorder"]) else True
    assert client.get("/api/v1/recordings", headers={"Authorization": "Bearer " + token}
                      ).json()["items"][0]["source"] == "MTConnect v1"


def test_subscribed_marker_requires_real_acceptance_and_does_not_imply_measurement(tmp_path):
    from capstone.api.readers import recorder_snapshot
    stamp = datetime.now(timezone.utc).isoformat()
    def marker(event):
        return {"record_type": "opcua_session", "schema_version": 2, "source": "opcua",
                "server_uri": "urn:test", "event": event, "at": stamp, "session_epoch": 1}
    path = tmp_path / "capture.jsonl"
    write_lines(path, [marker("connected")])
    connected = recorder_snapshot(path)["recorder"]
    assert connected["connection_state"] == "connected"
    assert connected["subscription_state"] == "unconfirmed"
    write_lines(path, [marker("connected"), marker("subscribed")])
    subscribed = recorder_snapshot(path)["recorder"]
    assert subscribed["subscription_state"] == "confirmed"
    assert subscribed["measurement_state"] == "none"
    assert subscribed["analysis_eligible"] is None
    write_lines(path, [marker("connected"), marker("subscribed"), marker("disconnected")])
    disconnected = recorder_snapshot(path)["recorder"]
    assert disconnected["connection_state"] == "disconnected"
    assert disconnected["subscription_state"] == "unconfirmed"


def test_future_collector_clock_cannot_claim_live_connection(tmp_path):
    """Clock skew never upgrades an expired or unconfirmed source to healthy."""
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    capture = tmp_path / "future.jsonl"
    data = change()
    data["received_at"] = future
    data["source_timestamp"] = future
    markers = [
        {"record_type": "opcua_session", "schema_version": 2,
         "source": "opcua", "server_uri": "urn:test",
         "event": event, "at": future, "session_epoch": 1}
        for event in ("connected", "subscribed")
    ]
    write_lines(capture, [*markers, data])
    recorder = recorder_snapshot(capture)["recorder"]
    assert recorder["connection_state"] == "unknown"
    assert recorder["subscription_state"] == "unconfirmed"
    assert recorder["measurement_state"] == "stale_or_none"
    assert recorder["analysis_eligible"] is None
