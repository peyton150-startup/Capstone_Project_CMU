"""Safe hosted process boundaries that do not require Render or a live model."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from capstone.api.config import UiConfig
from capstone.api.run_repository import ReviewProposal, RunExecutionConfig, StagePayload
from capstone.worker.runner import check_strategy, record, serve_worker


def test_hosted_config_requires_distinct_roles_and_no_local_disk():
    cfg = UiConfig(
        run_backend="hosted",
        run_database_url="postgresql://test:secret@localhost/unused",
        runs_enabled=True,
        run_db=None,
        token="v" * 24,
        run_token="o" * 24,
        review_token="r" * 24,
        browser_origin="https://example.com",
    )
    assert cfg.run_db is None
    assert cfg.browser_origin == "https://example.com"
    with pytest.raises(ValueError, match="HTTPS origin"):
        UiConfig(browser_origin="http://example.com")
    with pytest.raises(ValueError, match="tokens"):
        UiConfig(
            run_backend="hosted",
            run_database_url="postgresql://example/unused",
            runs_enabled=True,
            token="v" * 24,
            run_token="o" * 24,
            review_token="o" * 24,
        )


def test_stage_contract_rejects_raw_state_and_question_text():
    valid = {
        "investigation_id": str(uuid.uuid4()),
        "mode": "triage",
        "stage": "investigate",
        "iteration_count": 2,
        "tool_calls": 3,
        "evidence_count": 3,
        "hypothesis_count": 0,
        "unresolved_question_ids": ["Q1"],
        "termination_reason": None,
        "conclusion_available": False,
    }
    assert StagePayload.model_validate(valid).stage == "investigate"
    with pytest.raises(ValidationError):
        StagePayload.model_validate({**valid, "provider_api_key": "sensitive"})
    with pytest.raises(ValidationError):
        StagePayload.model_validate({
            **valid, "unresolved_question_ids": ["What is the API key?"]
        })
    with pytest.raises(ValidationError):
        StagePayload.model_validate({**valid, "tool_calls": -1})


def test_review_contract_does_not_accept_raw_tool_arguments():
    args = {
        "proposal_id": 1, "machine_id": "CNC-01",
        "action": "wait", "reason": "verify",
        "predicted_effect": "observe",
    }
    assert ReviewProposal.model_validate(args).proposal_id == 1
    with pytest.raises(ValidationError):
        ReviewProposal.model_validate({**args, "private_tool_result": "secret"})


def test_structured_logs_drop_unapproved_fields_and_values(caplog):
    claim = SimpleNamespace(
        run_id=uuid.uuid4(), job_id=uuid.uuid4()
    )
    with caplog.at_level(logging.INFO, logger="capstone.worker"):
        record("claimed", claim=claim, count=1, api_key="NEVER_LOG")
    entry = json.loads(caplog.records[-1].message)
    assert entry["run_id"] == str(claim.run_id)
    assert entry["job_id"] == str(claim.job_id)
    assert entry["count"] == 1
    assert "NEVER_LOG" not in caplog.records[-1].message
    with pytest.raises(ValueError):
        record("model.response.secret")


def test_strategy_drift_fails_closed(monkeypatch):
    import capstone.settings as settings

    current = SimpleNamespace(
        triage_plan="fixed",
        triage_investigate="deterministic",
        triage_hypothesize="model",
        triage_evidence_tests=True,
    )
    monkeypatch.setattr(settings, "get_settings", lambda: current)
    monkeypatch.delenv("CAPSTONE_SOURCE_REVISION", raising=False)
    good = RunExecutionConfig(
        triage_plan="fixed", triage_investigate="deterministic"
    )
    check_strategy(good)
    with pytest.raises(RuntimeError, match="does not match"):
        check_strategy(RunExecutionConfig())


def test_idle_worker_does_not_start_an_agent(monkeypatch):
    stop = threading.Event()

    class EmptyQueue:
        def ready(self):
            return True

        def worker_heartbeat(self, owner, *, source_revision, status):
            assert status in {"idle", "running"}
            assert owner.startswith("worker:")

        def recover_expired(self):
            return []

        def claim(self, owner, *, lease_seconds=60, expected_config=None):
            assert expected_config is not None
            assert owner.startswith("worker:")
            stop.set()
            return None

    # No provider or Graph need be imported to serve an empty queue.
    serve_worker(EmptyQueue(), stop=stop, poll_seconds=0.2)


def test_hosted_api_adapter_is_actored_and_never_runs_episode():
    from capstone.api.hosted_runs import HostedSimulatorRuns

    class FakeRepo:
        def get(self, run_id, *, actor_id):
            assert actor_id == "hosted-simulator"
            return {"run_id": run_id}

        def list_runs(self, *, actor_id, limit):
            assert actor_id == "hosted-simulator"
            return []

    instance = object.__new__(HostedSimulatorRuns)
    instance.repository = FakeRepo()
    assert instance.get(str(uuid.uuid4()))["run_id"]
    assert instance.list_runs() == []


def test_extended_progress_matches_pr294_without_raw_readings():
    safe = {
        "investigation_id": str(uuid.uuid4()),
        "mode": "triage",
        "stage": None,
        "iteration_count": 4,
        "tool_calls": 6,
        "evidence_count": 3,
        "hypothesis_count": 2,
        "unresolved_question_ids": ["Q1"],
        "unresolved_question_count": 1,
        "conclusion_available": False,
        "triage_decide_reads": 4,
        "remaining_tool_calls": 0,
        "packet_roster_verified": True,
        "requirement_statuses": [
            {
                "requirement_id": "Q1:sensor",
                "status": "insufficient",
                "evidence_count": 2,
            }
        ],
    }
    result = StagePayload.model_validate(safe).model_dump(
        mode="json", exclude_unset=True
    )
    assert result["triage_decide_reads"] == 4
    assert result["stage"] is None
    assert result["requirement_statuses"][0]["evidence_count"] == 2
    assert "raw_readings" not in result
    with pytest.raises(ValidationError):
        StagePayload.model_validate({**safe, "raw_readings": [400.0]})
    with pytest.raises(ValidationError):
        StagePayload.model_validate({
            **safe,
            "requirement_statuses": [
                {
                    "requirement_id": "Q1:sensor",
                    "status": "satisfied",
                    "evidence_count": 0,
                    "provider_response": "SECRET",
                }
            ],
        })


def test_hosted_fastapi_routes_do_not_start_worker_or_expose_private_audit(monkeypatch):
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("Optional FastAPI test dependency not installed")
    import capstone.api.hosted_runs as hosted
    from capstone.api.app import create_app

    run_id = str(uuid.uuid4())
    investigation_id = str(uuid.uuid4())
    observed = {"submissions": 0, "decisions": 0}

    class NoAgentApi:
        def __init__(self, database_url):
            assert database_url.endswith("/capstone_test")

        def ready(self):
            return True

        def close(self):
            pass

        def submit(self, request, key):
            observed["submissions"] += 1
            assert request.seed == 11
            return {"run_id": run_id, "state": "queued"}

        def get(self, _id):
            assert _id == run_id
            return {
                "run_id": run_id,
                "state": "completed",
                "snapshot": {
                    "investigation": {"investigation_id": investigation_id},
                },
            }

        def list_runs(self, limit=50):
            return []

        def queue_metrics(self):
            return {
                "queued": 1,
                "active_claims": 0,
                "stale_claims": 0,
                "oldest_queued_seconds": 8,
                "last_heartbeat_age_seconds": None,
                "worker_liveness": "unverified",
            }

        def events_since(self, _id, cursor, limit=100):
            return (
                [{"seq": 1, "event": "run.completed", "data": {"status": "completed"}}]
                if cursor == 0 else []
            )

        def pending_reviews(self):
            return []

        def decide(self, _id, decision):
            observed["decisions"] += 1
            return {"decision": decision.decision}

        def investigation_detail(self, _id, target):
            assert target == investigation_id
            return {"investigation_id": target}

        def observability_items(self, _id):
            return [{"event": "stage.updated", "counts": {"tool_calls": 5}}]

    monkeypatch.setattr(hosted, "HostedSimulatorRuns", NoAgentApi)
    cfg = UiConfig(
        run_backend="hosted",
        run_database_url="postgresql://dummy/capstone_test",
        runs_enabled=True,
        token="v" * 24,
        run_token="o" * 24,
        review_token="r" * 24,
        browser_origin="https://frontend.example",
    )
    client = TestClient(create_app(cfg))
    viewer = {"Authorization": "Bearer " + "v" * 24}
    operator = {"Authorization": "Bearer " + "o" * 24}
    reviewer = {"Authorization": "Bearer " + "r" * 24}
    assert client.get("/api/v1/ready").status_code == 200
    system = client.get("/api/v1/system", headers=viewer)
    assert system.status_code == 200
    assert system.json()["run_queue"]["queued"] == 1
    assert system.json()["run_queue"]["worker_liveness"] == "unverified"
    assert "lease_token" not in system.text
    assert client.post(
        "/api/v1/lab/runs", headers={**viewer, "Idempotency-Key": "a" * 20},
        json={"seed": 11},
    ).status_code == 403
    created = client.post(
        "/api/v1/lab/runs",
        headers={**operator, "Idempotency-Key": "a" * 20},
        json={"seed": 11},
    )
    assert created.status_code == 202
    assert observed["submissions"] == 1
    assert client.get(
        "/api/v1/lab/runs/" + run_id + "/investigation", headers=viewer
    ).json()["detail"]["investigation_id"] == investigation_id
    assert client.get(
        "/api/v1/lab/runs/" + run_id + "/observability", headers=viewer
    ).json()["items"][0]["counts"]["tool_calls"] == 5
    stream = client.get("/api/v1/lab/runs/" + run_id + "/events", headers=viewer)
    assert stream.status_code == 200
    assert "event: stream.closed" in stream.text
    assert client.post(
        "/api/v1/simulator/reviews/" + run_id,
        headers=viewer, json={"proposal_id": 1, "decision": "reject"},
    ).status_code == 403
    assert client.post(
        "/api/v1/simulator/reviews/" + run_id,
        headers=reviewer, json={"proposal_id": 1, "decision": "reject"},
    ).status_code == 200
    assert observed["decisions"] == 1


def test_worker_logs_only_allowlisted_failure_codes_and_build_sha(caplog, monkeypatch):
    from capstone.worker.runner import record

    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    with caplog.at_level(logging.INFO, logger="capstone.worker"):
        record("failed", failure_code="configuration_mismatch", api_key="SECRET")
    event = json.loads(caplog.records[-1].message)
    assert event["failure_code"] == "configuration_mismatch"
    assert event["revision"] == "a" * 12
    assert "SECRET" not in caplog.records[-1].message
    with pytest.raises(ValueError):
        record("failed", failure_code="private provider exception")


def test_worker_resolves_pr301_profile_without_reimplementing_it(monkeypatch):
    """Two Render services must persist the true effective Graph control plane."""
    import capstone.settings as settings

    # Deliberately contradictory raw knobs: PR #301's profile wins.
    original = SimpleNamespace(
        triage_plan="model", triage_investigate="off",
        triage_hypothesize="model", triage_evidence_tests=False,
        effective_triage=SimpleNamespace(
            run_mode="deterministic", plan="fixed",
            investigate="deterministic", hypothesize="deterministic",
            evidence_tests=True, packet=True, packet_prompt=True,
            observe_calls="separate", hypothesis_seconds=0.0,
            critic=False, critic_followup=False, critic_reinstate=False,
        ),
    )
    monkeypatch.setattr(settings, "get_settings", lambda: original)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("CAPSTONE_SOURCE_REVISION", raising=False)
    effective = RunExecutionConfig.current()
    assert effective.triage_run_mode == "deterministic"
    assert effective.triage_plan == "fixed"
    assert effective.triage_investigate == "deterministic"
    assert effective.triage_hypothesize == "deterministic"
    assert effective.triage_evidence_tests
    assert effective.triage_packet
    assert effective.triage_observe_calls == "separate"
    assert effective.triage_hypothesis_seconds == 0.0
    assert not effective.triage_critic
    assert effective != RunExecutionConfig()
