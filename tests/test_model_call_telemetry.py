"""End-to-end managed model-call telemetry without contacting providers."""

import json
import uuid

from capstone.agent.model_policy import ModelCall
from capstone.api.model_calls import SafeModelCall, classify_outcome, project_model_call
from capstone.api.runs import SimulatorRuns
from capstone.providers.chat import Attempt


def example_calls():
    return [
        ModelCall(
            job="conclude", stage="conclude", mode="triage",
            outcome="no_answer", answered_by=None,
            attempts=(
                Attempt(
                    model="nvidia/nemotron", outcome="the model service answered HTTP 401",
                    seconds=0.25, prompt_chars=220, prompt_version="abcdef1234567890",
                ),
                Attempt(
                    model="nvidia/nemotron", outcome="the model service timed out",
                    seconds=14.0,
                ),
                Attempt(
                    model="mistral/fallback", outcome="the model service answered HTTP 429",
                    seconds=0.1,
                ),
            ),
        ),
        ModelCall(
            job="plan", stage="plan", mode="deep",
            outcome="answered", answered_by="mistral/fallback",
            attempts=(
                Attempt(model="nvidia/nemotron", outcome="the model service timed out"),
                Attempt(
                    model="mistral/fallback", outcome="answered",
                    seconds=0.123, input_tokens=91, output_tokens=12,
                ),
            ),
        ),
    ]


def seed_run(runner):
    run_id = str(uuid.uuid4())
    with runner._db() as db:
        db.execute(
            "INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
            (
                run_id, "telemetry-test-key", '{"seed":3}', "running",
                '{"stage":"plan","status":"running"}',
                "2026-11-17T00:00:00Z", "2026-11-17T00:00:00Z",
            ),
        )
    return run_id


def test_safe_model_attempts_redact_provider_text_and_classify_failures():
    first, second = example_calls()
    projected = project_model_call(first, 1)
    assert SafeModelCall.model_validate(projected).question_index == 1
    assert [x["outcome"] for x in projected["attempts"]] == [
        "unauthorized", "timeout", "rate_limited"
    ]
    assert projected["retry_count"] == 1
    assert projected["fallback_selected"] is True
    assert projected["fallback_succeeded"] is False
    answered = project_model_call(second, 2)
    assert answered["fallback_succeeded"] is True
    assert answered["answered_by"] == "mistral/fallback"
    assert answered["attempts"][1]["input_tokens"] == 91
    assert answered["attempts"][1]["output_tokens"] == 12
    assert "HTTP" not in json.dumps(projected)
    assert classify_outcome("HTTP 403 private nvapi-token") == "forbidden"
    assert classify_outcome("provider sent sk-secret") == "other_error"


def test_secret_like_model_name_is_redacted_and_invalid_timing_is_dropped():
    call = ModelCall(
        job="conclude", stage="conclude", mode="triage", outcome="no_answer",
        attempts=(
            Attempt(
                model="nvapi-secret1234",
                outcome="HTTP 500 secret body: Bearer PRIVATE",
                seconds=float("inf"),
            ),
        ),
    )
    result = project_model_call(call, 1)
    assert result["attempts"][0]["model"] == "redacted"
    assert result["attempts"][0]["seconds"] is None
    assert result["attempts"][0]["outcome"] == "provider_error"
    assert "PRIVATE" not in json.dumps(result)
    assert "nvapi-secret" not in json.dumps(result)


def test_sqlite_model_journal_preserves_snapshot_across_restart(tmp_path):
    path = tmp_path / "runs.sqlite"
    runner = SimulatorRuns(path)
    run_id = seed_run(runner)
    original = runner.get(run_id)["snapshot"]
    assert runner.model_calls(run_id)["availability"] == "not_recorded"
    runner._append_model_event(run_id, "model.monitor", {"schema_version": 1})
    for index, call in enumerate(example_calls(), 1):
        runner.record_model_call(run_id, call, index)

    assert runner.get(run_id)["snapshot"] == original
    calls = runner.model_calls(run_id)
    assert calls["availability"] == "available"
    assert [x["question_index"] for x in calls["items"]] == [1, 2]
    assert calls["items"][0]["mode"] == "triage"
    assert calls["items"][1]["mode"] == "deep"
    assert calls["items"][0]["seq"] < calls["items"][1]["seq"]

    restarted = SimulatorRuns(path)
    assert restarted.model_calls(run_id)["items"] == calls["items"]
    with restarted._db() as db:
        db.execute(
            "INSERT INTO run_events VALUES(?,?,?,?,?)",
            (
                run_id, 20, "model.call",
                '{"schema_version":1,"api_key":"nvapi-test-secret"}',
                "2026-11-17T00:00:00Z",
            ),
        )
    assert len(restarted.model_calls(run_id)["items"]) == 2
    assert "nvapi-test-secret" not in json.dumps(restarted.model_calls(run_id))


def test_model_call_http_endpoint_enforces_auth_and_pilot_isolation(tmp_path):
    from fastapi.testclient import TestClient

    from capstone.api.app import create_app
    from capstone.api.config import UiConfig

    root = tmp_path / "runs.sqlite"
    runner = SimulatorRuns(root)
    run_id = seed_run(runner)
    runner._append_model_event(run_id, "model.monitor", {"schema_version": 1})
    runner.record_model_call(run_id, example_calls()[0], 1)

    token = "viewer-abcdefghijklmnopqrstuvwxyz"
    cfg = UiConfig(
        run_db=root, token=token,
        run_token="operator-abcdefghijklmnopqrstuvwxyz",
        review_token="reviewer-abcdefghijklmnopqrstuvwxyz", runs_enabled=True,
    )
    client = TestClient(create_app(cfg))
    url = f"/api/v1/lab/runs/{run_id}/model-calls"
    assert client.get(url).status_code == 401
    assert client.get(url + "?workspace=pilot",
                      headers={"Authorization": "Bearer " + token}).status_code == 403
    response = client.get(
        url + "?workspace=simulator",
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == 200
    assert response.json()["availability"] == "available"
    assert response.json()["items"][0]["attempts"][0]["outcome"] == "unauthorized"
    assert "HTTP 401" not in response.text
