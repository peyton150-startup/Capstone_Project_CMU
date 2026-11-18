"""Managed-run per-run settings preview, authorization and durable admission."""

import json

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("FastAPI optional dependency missing", allow_module_level=True)

from capstone.api.app import create_app
from capstone.api.runs import SimulatorRuns
from tests.test_web_runs import KEY, OPERATOR, TOKEN, auth, config


def _worker(self, run_id, request):
    """No model is called; test the real submission and journal boundaries."""
    try:
        saved = self.get(run_id)["requested"]
        effective = saved["effective_configuration"]
        if request.mode == "deep":
            assert request._effective_triage is None
            assert effective["effective_triage"] is None
        else:
            assert request._effective_triage is not None
            assert (
                request._effective_triage.model_dump(mode="json")
                == effective["effective_triage"]
            )
        self._emit(
            run_id, "run.completed",
            {
                "status": "completed",
                "mode": request.mode,
                "effective_configuration": effective,
            },
            state="completed",
        )
    finally:
        with self.lock:
            self.active.discard(run_id)


def test_local_browser_preflight_allows_authenticated_post(tmp_path):
    client = TestClient(create_app(config(tmp_path)))
    response = client.options(
        "/api/v1/lab/runs/preview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_viewer_preview_operator_submit_and_persisted_configuration(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(SimulatorRuns, "_execute", _worker)
    client = TestClient(create_app(config(tmp_path)))
    defaults = client.get(
        "/api/v1/lab/runs/configuration", headers=auth(TOKEN)
    )
    assert defaults.status_code == 200
    assert defaults.json()["editable_per_run"]
    assert not defaults.json()["global_environment_editable"]
    assert defaults.json()["defaults"]["run_mode"] in {"custom", "deterministic"}
    overrides = {
        "run_mode": "deterministic",
        "plan": "model",
        "investigate": "off",
        "hypothesize": "model",
        "packet": False,
        "evidence_tests": False,
        "then_deep": False,
        "seconds": 70,
        "tool_calls": 4,
        "conclude_brief": False,
        "conclude_cap": False,
    }
    payload = {"seed": 19, "mode": "triage", "triage_settings": overrides}
    preview = client.post(
        "/api/v1/lab/runs/preview", headers=auth(TOKEN), json=payload
    )
    assert preview.status_code == 200
    preview_config = preview.json()
    effective = preview_config["effective_triage"]
    assert effective["run_mode"] == "deterministic"
    assert effective["plan"] == "fixed"
    assert effective["investigate"] == "deterministic"
    assert effective["hypothesize"] == "deterministic"
    assert effective["seconds"] == 70 and effective["tool_calls"] == 4
    assert effective["then_deep"] is False
    assert effective["conclude_brief"] is False
    assert preview_config["stages"]["conclude"] == "model"
    assert {"plan", "investigate", "hypothesize", "packet"} <= set(preview_config["overridden"])
    assert client.post(
        "/api/v1/lab/runs",
        headers={**auth(TOKEN), "Idempotency-Key": KEY},
        json={**payload, "configuration_fingerprint": preview_config["fingerprint"]},
    ).status_code == 403
    response = client.post(
        "/api/v1/lab/runs",
        headers={**auth(OPERATOR), "Idempotency-Key": KEY},
        json={**payload, "configuration_fingerprint": preview_config["fingerprint"]},
    )
    assert response.status_code == 202
    run = client.get(
        f"/api/v1/lab/runs/{response.json()['run_id']}",
        headers=auth(TOKEN),
    ).json()
    assert run["requested"]["effective_configuration"] == config
    recorded_request = run["requested"]["triage_settings"]
    for name, value in overrides.items():
        assert recorded_request[name] == value
    assert recorded_request["packet_prompt"] is None
    assert recorded_request["observe_calls"] is None
    assert recorded_request["hypothesis_seconds"] is None
    assert "api_key" not in json.dumps(run)
    assert "password" not in json.dumps(run)


def test_invalid_custom_settings_stale_previews_and_pilot_denials(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(SimulatorRuns, "_execute", _worker)
    client = TestClient(create_app(config(tmp_path)))
    bad = {
        "seed": 1, "mode": "triage",
        "triage_settings": {
            "run_mode": "custom", "plan": "model",
            "investigate": "deterministic", "hypothesize": "model",
        },
    }
    assert client.post(
        "/api/v1/lab/runs/preview", headers=auth(TOKEN), json=bad
    ).status_code == 422
    assert client.post(
        "/api/v1/lab/runs",
        headers={**auth(OPERATOR), "Idempotency-Key": KEY}, json=bad,
    ).status_code == 422
    injection = {
        "seed": 1,
        "triage_settings": {"run_mode": "deterministic", "api_key": "SECRET"},
    }
    assert client.post(
        "/api/v1/lab/runs/preview", headers=auth(TOKEN), json=injection
    ).status_code == 422
    assert client.post(
        "/api/v1/lab/runs/preview?workspace=pilot",
        headers=auth(TOKEN), json={"seed": 1},
    ).status_code == 403
    assert client.get(
        "/api/v1/lab/runs/configuration?workspace=pilot",
        headers=auth(TOKEN),
    ).status_code == 403
    payload = {"seed": 1, "triage_settings": {"run_mode": "deterministic"}}
    preview = client.post(
        "/api/v1/lab/runs/preview", headers=auth(TOKEN), json=payload
    ).json()
    stale = client.post(
        "/api/v1/lab/runs",
        headers={**auth(OPERATOR), "Idempotency-Key": KEY},
        json={**payload, "configuration_fingerprint": "0" * 20},
    )
    assert stale.status_code == 409
    accepted = client.post(
        "/api/v1/lab/runs",
        headers={**auth(OPERATOR), "Idempotency-Key": KEY},
        json={**payload, "configuration_fingerprint": preview["fingerprint"]},
    )
    assert accepted.status_code == 202
    reuse = client.post(
        "/api/v1/lab/runs",
        headers={**auth(OPERATOR), "Idempotency-Key": KEY},
        json={"seed": 2, "configuration_fingerprint": preview["fingerprint"]},
    )
    assert reuse.status_code == 409


def test_deep_only_does_not_apply_triage_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulatorRuns, "_execute", _worker)
    client = TestClient(create_app(config(tmp_path)))
    payload = {
        "seed": 14, "mode": "deep",
        "triage_settings": {"run_mode": "deterministic", "then_deep": False},
    }
    preview = client.post(
        "/api/v1/lab/runs/preview", headers=auth(TOKEN), json=payload
    )
    assert preview.status_code == 200
    preview_config = preview.json()
    assert not preview_config["applied"]
    assert preview_config["effective_triage"] is None
    assert preview_config["stages"]["triage"] == "not run"
    assert preview_config["not_applied"] == ["run_mode", "then_deep"]


def test_submission_rejects_settings_drift_between_route_and_journal(
    tmp_path, monkeypatch
):
    """A race after preview is a stale configuration, not a reused key."""
    from capstone.settings import Settings

    monkeypatch.setattr(SimulatorRuns, "_execute", _worker)
    old = Settings(
        _env_file=None, triage_tool_calls=6, triage_run_mode="custom"
    )
    changed = Settings(
        _env_file=None, triage_tool_calls=3, triage_run_mode="custom"
    )
    monkeypatch.setattr("capstone.api.app.get_settings", lambda: old)
    monkeypatch.setattr("capstone.api.runs.get_settings", lambda: changed)
    client = TestClient(create_app(config(tmp_path)))
    payload = {"seed": 17, "mode": "triage"}
    original = client.post(
        "/api/v1/lab/runs/preview", headers=auth(TOKEN), json=payload
    )
    assert original.status_code == 200
    rejected = client.post(
        "/api/v1/lab/runs",
        headers={**auth(OPERATOR), "Idempotency-Key": KEY},
        json={
            **payload,
            "configuration_fingerprint": original.json()["fingerprint"],
        },
    )
    assert rejected.status_code == 409
    assert "Settings changed" in rejected.json()["detail"]
    assert client.get(
        "/api/v1/lab/runs", headers=auth(TOKEN)
    ).json()["items"] == []
