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

        def recover_expired(self):
            return []

        def claim(self, owner, *, lease_seconds=60):
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
