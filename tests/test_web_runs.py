"""Managed simulator API acceptance: roles, idempotency, review and recovery.

No model calls or simulator writes: deterministic fake worker exercises the real
FastAPI + SQLite bridge without modifying the existing agent implementation.
"""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("FastAPI optional local dependencies not installed", allow_module_level=True)

from capstone.api.app import create_app
from capstone.api.config import UiConfig
from capstone.api.runs import RunRequest, SimulatorRuns


TOKEN = "viewer-abcdefghijklmnopqrstuvwxyz"
OPERATOR = "operator-abcdefghijklmnopqrstuvwxyz"
REVIEWER = "reviewer-abcdefghijklmnopqrstuvwxyz"
KEY = "idempotent-0000000001"


def config(tmp_path):
    return UiConfig(
        token=TOKEN, run_token=OPERATOR, review_token=REVIEWER,
        run_db=tmp_path / "sim-runs.sqlite", runs_enabled=True,
    )


def auth(token):
    return {"Authorization": "Bearer " + token}


def test_run_roles_and_idempotency(tmp_path, monkeypatch):
    def fake_run(self, run_id, request):
        self._emit(run_id, "run.completed", {"status": "completed", "mode": request.mode},
                   state="completed")
        with self.lock:
            self.active.discard(run_id)
    monkeypatch.setattr(SimulatorRuns, "_execute", fake_run)
    client = TestClient(create_app(config(tmp_path)))
    payload = {"seed": 3, "kind": "standard", "mode": "deep"}
    assert client.post("/api/v1/lab/runs", json=payload,
                       headers={**auth(TOKEN), "Idempotency-Key": KEY}).status_code == 403
    assert client.post("/api/v1/lab/runs?workspace=pilot", json=payload,
                       headers={**auth(OPERATOR), "Idempotency-Key": KEY}).status_code == 403
    assert client.post("/api/v1/lab/runs", json=payload, headers=auth(OPERATOR)).status_code == 422
    result = client.post("/api/v1/lab/runs", json=payload,
                         headers={**auth(OPERATOR), "Idempotency-Key": KEY})
    assert result.status_code == 202
    id_ = result.json()["run_id"]
    second = client.post("/api/v1/lab/runs", json=payload,
                         headers={**auth(OPERATOR), "Idempotency-Key": KEY})
    assert second.status_code == 202 and second.json()["run_id"] == id_
    conflict = client.post("/api/v1/lab/runs", json={**payload, "seed": 5},
                           headers={**auth(OPERATOR), "Idempotency-Key": KEY})
    assert conflict.status_code == 409
    assert client.get(f"/api/v1/lab/runs/{id_}", headers=auth(TOKEN)).status_code == 200
    assert client.get(f"/api/v1/lab/runs/{id_}?workspace=pilot",
                      headers=auth(TOKEN)).status_code == 403
    response = client.get(f"/api/v1/lab/runs/{id_}/events", headers=auth(TOKEN))
    assert response.status_code == 200
    assert "event: run.completed" in response.text
    assert "id: 1" in response.text
    assert TOKEN not in response.text


def test_durable_pending_approval_and_double_decision(tmp_path, monkeypatch):
    ready = threading.Event()
    def fake_run(self, run_id, request):
        self._emit(run_id, "run.started", {"status": "running"}, state="running")
        ready.set()
        verdict, note = self._await_review(run_id, SimpleNamespace(
            proposal_id=1, machine_id="CNC-01", action="replace_bearing",
            reason="Simulated evidence", predicted_effect="Temperature should fall",
        ))
        self._emit(run_id, "run.completed", {
            "status": "completed", "approved": verdict, "note": note,
            "action_executed": False, "verification_outcome": None,
        }, state="completed")
        with self.lock:
            self.active.discard(run_id)
    monkeypatch.setattr(SimulatorRuns, "_execute", fake_run)
    client = TestClient(create_app(config(tmp_path)))
    launched = client.post("/api/v1/lab/runs", json={"seed": 2},
                           headers={**auth(OPERATOR), "Idempotency-Key": KEY})
    assert launched.status_code == 202
    id_ = launched.json()["run_id"]
    assert ready.wait(2)
    for _ in range(100):
        response = client.get("/api/v1/simulator/reviews", headers=auth(TOKEN))
        if response.json()["items"]:
            break
        time.sleep(0.01)
    items = response.json()["items"]
    assert len(items) == 1 and items[0]["proposal_id"] == 1
    path = f"/api/v1/simulator/reviews/{id_}"
    decision = {"proposal_id": 1, "decision": "approve", "note": "Reviewed evidence"}
    assert client.post(path, json=decision, headers=auth(OPERATOR)).status_code == 403
    assert client.post(path + "?workspace=pilot", json=decision,
                       headers=auth(REVIEWER)).status_code == 403
    assert client.post(path, json=decision, headers=auth(REVIEWER)).status_code == 200
    assert client.post(path, json=decision, headers=auth(REVIEWER)).status_code == 409
    for _ in range(100):
        result = client.get(f"/api/v1/lab/runs/{id_}", headers=auth(TOKEN)).json()
        if result["state"] == "completed":
            break
        time.sleep(0.01)
    assert result["state"] == "completed"
    assert result["snapshot"]["approved"] is True
    assert result["snapshot"]["action_executed"] is False
    assert client.get("/api/v1/simulator/reviews", headers=auth(TOKEN)).json()["items"] == []


def test_restart_interruption_and_private_token_validation(tmp_path):
    c = config(tmp_path)
    manager = SimulatorRuns(c.run_db)
    request = RunRequest(seed=1)
    # Build a fully durable run without launching a worker, like a forced crash.
    with manager._db() as db:
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", (
            "interrupted-episode", "once", request.model_dump_json(), "running",
            json.dumps({"status": "running"}), "2026-11-16T00:00:00Z",
            "2026-11-16T00:00:00Z",
        ))
    recovered = SimulatorRuns(c.run_db)
    assert recovered.get("interrupted-episode")["state"] == "interrupted"
    with pytest.raises(ValueError, match="distinct"):
        UiConfig(token=TOKEN, run_token=TOKEN, review_token=REVIEWER,
                 runs_enabled=True, run_db=tmp_path/"other.db")
    assert not any("secret" in json.dumps(x) for x in recovered.list_runs())
