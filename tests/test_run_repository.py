"""Hosted run queue contract against disposable, local PostgreSQL when present."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from capstone.api.run_repository import LostLease, RunExecutionConfig, RunRepository
from capstone.api.runs import RunRequest


def test_repository_rejects_non_postgres_url_without_connecting():
    with pytest.raises(ValueError, match="PostgreSQL"):
        RunRepository("sqlite:///:memory:")
    with pytest.raises(ValueError, match="TLS"):
        RunRepository(
            "postgresql://test:secret@localhost/capstone_test?sslmode=disable"
        )


def test_execution_config_excludes_secrets_and_invalid_strategy():
    with pytest.raises(ValueError, match="extra_forbidden"):
        RunExecutionConfig.model_validate({"provider_api_key": "never-persist"})
    with pytest.raises(ValueError, match="fixed plan"):
        RunExecutionConfig(triage_investigate="deterministic")


def test_event_contract_refuses_unapproved_fields():
    from capstone.api.run_models import SimRun

    class Session:
        def scalar(self, *args):
            pytest.fail("Unsafe event must be refused before querying the database")

    with pytest.raises(ValueError, match="unapproved"):
        RunRepository._append(
            Session(),
            SimRun(run_id=None),
            "run.failed",
            {"status": "failed", "provider_error": "private body"},
        )


def test_empty_hosted_migration_round_trip(repository):
    """A new empty hosted schema can roll back without touching legacy rows."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    configuration = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(configuration, "0002_simulator_journal")
    with repository.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT to_regclass('capstone_private.sim_runs')")
            ).scalar_one()
            is None
        )
        assert (
            connection.execute(
                text("SELECT to_regclass('capstone_private.runs')")
            ).scalar_one()
            is not None
        )
    command.upgrade(configuration, "head")
    assert repository.ready()


@pytest.fixture
def repository(monkeypatch):
    """Use only the disposable CI/local test database, never a hosted project."""
    # Variables:
    #   url: Explicit localhost test database; no production fallback is allowed.
    url = os.environ.get("CAPSTONE_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Disposable PostgreSQL test database is not configured")
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    if (
        parsed.host not in {"localhost", "127.0.0.1"}
        or parsed.database != "capstone_test"
    ):
        pytest.fail("Run repository tests require localhost/capstone_test")
    from alembic import command
    from alembic.config import Config

    import capstone.settings as settings_module
    from capstone.settings import Settings

    settings = Settings(_env_file=None, DATABASE_URL=url)
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    command.upgrade(
        Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head"
    )
    instance = RunRepository(url)
    with instance.engine.begin() as connection:
        connection.exec_driver_sql(
            "TRUNCATE capstone_private.sim_run_artifacts, "
            "capstone_private.sim_run_reviews, capstone_private.sim_run_events, "
            "capstone_private.sim_jobs, capstone_private.sim_runs, "
            "capstone_private.sim_worker_heartbeats"
        )
    yield instance
    instance.close()


def test_concurrent_idempotency_creates_one_run_and_one_job(repository):
    # Variables:
    #   responses: Simultaneous callers with the same actor and key.
    request = RunRequest(seed=42, mode="triage")

    def submit(_):
        return repository.submit(
            request,
            "same-key-simultaneous-001",
            actor_id="test-operator",
            effective_config=RunExecutionConfig(triage_plan="fixed"),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(submit, range(8)))
    assert len({row["run_id"] for row in responses}) == 1
    with repository.engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT count(*) FROM capstone_private.sim_jobs"
            ).scalar_one()
            == 1
        )
    with pytest.raises(ValueError, match="Idempotency"):
        repository.submit(
            RunRequest(seed=43),
            "same-key-simultaneous-001",
            actor_id="test-operator",
            effective_config=RunExecutionConfig(),
        )
    assert (
        repository.submit(
            request,
            "same-key-simultaneous-001",
            actor_id="other-operator",
            effective_config=RunExecutionConfig(),
        )["run_id"]
        != responses[0]["run_id"]
    )


def test_parallel_claims_fence_state_and_preserve_event_order(repository):
    submitted = repository.submit(
        RunRequest(seed=8),
        "parallel-claim-key-001",
        actor_id="test-operator",
        effective_config=RunExecutionConfig(),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(repository.claim, ["worker-one", "worker-two"]))
    claim = next(item for item in claims if item is not None)
    owner = "worker-one" if claims[0] is not None else "worker-two"
    assert sum(item is not None for item in claims) == 1
    assert claim.effective_config == RunExecutionConfig()
    assert repository.heartbeat(claim, owner)
    assert not repository.heartbeat(claim, "wrong-owner")
    with pytest.raises(LostLease):
        repository.transition(
            claim, "wrong-owner", "completed", "run.completed", {"status": "completed"}
        )
    with pytest.raises(ValueError, match="Invalid event"):
        repository.transition(
            claim, owner, "completed", "run.unknown", {"status": "completed"}
        )
    assert repository.get(submitted["run_id"])["state"] == "running"
    assert [
        item["seq"] for item in repository.events_since(submitted["run_id"], 0)
    ] == [
        1,
        2,
    ]
    repository.transition(
        claim, owner, "completed", "run.completed", {"status": "completed"}
    )
    with pytest.raises(LostLease):
        repository.transition(
            claim, owner, "failed", "run.failed", {"status": "failed"}
        )
    events = repository.events_since(submitted["run_id"], 0)
    assert [(item["seq"], item["event"]) for item in events] == [
        (1, "run.queued"),
        (2, "run.started"),
        (3, "run.completed"),
    ]
    assert repository.events_since(submitted["run_id"], 2) == events[2:]
    assert repository.get(submitted["run_id"], actor_id="other-operator") is None
    assert repository.list_runs(actor_id="other-operator") == []


def test_expired_started_claim_interrupts_without_retry(repository):
    submitted = repository.submit(
        RunRequest(seed=9),
        "expired-claim-key-001",
        actor_id="test-operator",
        effective_config=RunExecutionConfig(),
    )
    claim = repository.claim("worker-one")
    assert claim is not None
    with repository.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE capstone_private.sim_jobs SET lease_until = "
            "CURRENT_TIMESTAMP - interval '1 second' WHERE run_id = %s",
            (claim.run_id,),
        )
    assert repository.recover_expired() == [submitted["run_id"]]
    assert repository.get(submitted["run_id"])["state"] == "interrupted"
    assert repository.claim("worker-two") is None
    assert not repository.heartbeat(claim, "worker-one")


def test_hosted_review_is_durable_actor_scoped_and_lease_fenced(repository):
    """Two independent processes can agree on an exact approved proposal."""
    from capstone.api.run_repository import ReviewProposal
    from capstone.api.runs import ReviewDecision

    queued = repository.submit(
        RunRequest(seed=31, mode="deep"),
        "review-cross-process-001",
        actor_id="hosted-simulator",
        effective_config=RunExecutionConfig(),
    )
    claim = repository.claim("worker-one")
    assert claim is not None
    safe = ReviewProposal(
        proposal_id=1,
        machine_id="CNC-01",
        action="wait",
        reason="observe a simulated intervention",
        predicted_effect="more reliable readings",
    )
    repository.request_review(claim, "worker-one", safe)
    assert repository.get(queued["run_id"])["state"] == "awaiting_review"
    assert repository.pending_reviews(actor_id="not-the-actor") == []
    assert repository.pending_reviews(actor_id="hosted-simulator")[0][
        "proposal_id"
    ] == 1
    with pytest.raises(LookupError):
        repository.decide_review(
            queued["run_id"],
            ReviewDecision(proposal_id=1, decision="approve"),
            actor_id="not-the-actor",
            reviewer_id="test-reviewer",
        )
    decision = repository.decide_review(
        queued["run_id"],
        ReviewDecision(proposal_id=1, decision="approve", note="authorized"),
        actor_id="hosted-simulator",
        reviewer_id="test-reviewer",
    )
    assert decision["decision"] == "approve"
    with pytest.raises(ValueError, match="no longer pending"):
        repository.decide_review(
            queued["run_id"],
            ReviewDecision(proposal_id=1, decision="approve"),
            actor_id="hosted-simulator",
            reviewer_id="test-reviewer",
        )
    assert repository.review_status(claim, "worker-one", 1) == "approve"
    repository.resume_review(claim, "worker-one")
    assert repository.get(queued["run_id"])["state"] == "running"
    assert [
        event["event"] for event in repository.events_since(queued["run_id"], 0)
    ] == [
        "run.queued", "run.started", "review.requested",
        "review.decided", "run.started",
    ]


def test_hosted_progress_artifact_and_terminal_are_fenced(repository):
    """Persisted audit is private; late stage writes cannot regress completion."""
    from capstone.api.run_repository import StagePayload
    from uuid import uuid4

    queued = repository.submit(
        RunRequest(seed=32, mode="triage"),
        "phase-and-artifacts-001",
        actor_id="hosted-simulator",
        effective_config=RunExecutionConfig(),
    )
    claim = repository.claim("worker-one")
    assert claim is not None
    stage = StagePayload(
        investigation_id=str(uuid4()),
        mode="triage",
        stage="conclude",
        iteration_count=2,
        tool_calls=3,
        evidence_count=1,
        hypothesis_count=0,
        unresolved_question_ids=["Q1"],
        conclusion_available=True,
    )
    repository.publish_progress(claim, "worker-one", stage.model_dump(mode="json"))
    observed = repository.get(queued["run_id"], actor_id="hosted-simulator")
    assert observed["snapshot"]["progress"]["triage"]["stage"] == "conclude"
    assert repository.get(queued["run_id"], actor_id="someone-else") is None
    repository.store_artifacts(
        claim, "worker-one",
        {"audit": b'{"private":"audit"}\n', "observability": b'{"event":"worker.started"}\n'},
    )
    assert repository.read_artifact(
        queued["run_id"], "audit", actor_id="hosted-simulator"
    ).startswith(b'{"private":')
    assert repository.read_artifact(
        queued["run_id"], "audit", actor_id="someone-else"
    ) is None
    repository.transition(
        claim, "worker-one", "completed", "run.completed",
        {"status": "completed"},
    )
    with pytest.raises(LostLease):
        repository.publish_progress(claim, "worker-one", stage.model_dump(mode="json"))
    assert repository.get(queued["run_id"])["state"] == "completed"


def test_worker_uses_pydantic_graph_episode_without_a_web_thread(repository, monkeypatch):
    """Fixture policy exercises a real job claim, audit persistence and completion."""
    from types import SimpleNamespace
    from uuid import uuid4

    import capstone.episode as episode
    import capstone.experiment as experiment
    import capstone.worker.runner as worker

    queued = repository.submit(
        RunRequest(seed=33, mode="triage"),
        "worker-fixture-episode-001",
        actor_id="hosted-simulator",
        effective_config=RunExecutionConfig(),
    )
    state = SimpleNamespace(
        investigation_id=uuid4(),
        mode="triage",
        stage="conclude",
        iteration_count=2,
        tool_call_count=1,
        evidence=[],
        hypotheses=[],
        unanswered_questions=[],
        termination_reason=None,
        conclusion=SimpleNamespace(diagnosis="unknown", recommendation="escalate"),
        action_started_tick=None,
        verification=None,
        triage_report=None,
    )

    def fake_episode(seed, policy, *, watch, log, **kwargs):
        assert seed == 33
        assert kwargs["triage"] is True
        watch(state)
        log.path.write_text('{"private":"audit"}\n', encoding="utf-8")
        return SimpleNamespace(
            state=state, triage=None, desk=SimpleNamespace(proposals=lambda: [])
        )

    monkeypatch.setattr(episode, "run_episode", fake_episode)
    monkeypatch.setattr(
        experiment, "model_policy_factory", lambda **kwargs: lambda: object()
    )
    monkeypatch.setattr(worker, "check_strategy", lambda _: None)
    claim = repository.claim("worker-integration")
    assert claim is not None
    worker.execute_claim(repository, claim, "worker-integration", heartbeat_seconds=1)
    result = repository.get(queued["run_id"])
    assert result["state"] == "completed"
    assert result["snapshot"]["investigation"]["mode"] == "triage"
    assert repository.read_artifact(
        queued["run_id"], "audit", actor_id="hosted-simulator"
    )
    assert [e["event"] for e in repository.events_since(queued["run_id"], 0)][-1] == (
        "run.completed"
    )


def test_model_journal_is_fenced_private_and_source_validated(repository):
    """#297 owns sanitization: hosted stores only its exact Pydantic projection."""
    contracts = pytest.importorskip("capstone.api.model_calls")
    from capstone.api.hosted_runs import HostedSimulatorRuns

    queued = repository.submit(
        RunRequest(seed=98, mode="triage"),
        "model-telemetry-hosted-98",
        actor_id="hosted-simulator",
        effective_config=RunExecutionConfig(),
    )
    claim = repository.claim("model-telemetry-worker")
    assert claim is not None
    repository.publish_model_event(
        claim, "model-telemetry-worker", "model.monitor", {"schema_version": 1}
    )
    repository.publish_model_event(
        claim, "model-telemetry-worker", "model.config",
        {"schema_version": 1, "outcome": "configured"},
    )
    safe_call = contracts.SafeModelCall(
        question_index=1, job="conclude", outcome="no_answer", attempts=(),
    ).model_dump(mode="json")
    repository.publish_model_event(
        claim, "model-telemetry-worker", "model.call", safe_call
    )
    with pytest.raises(ValueError):
        repository.publish_model_event(
            claim, "model-telemetry-worker", "model.call",
            {**safe_call, "provider_response": "DO_NOT_PERSIST"},
        )
    repository.publish_model_event(
        claim, "model-telemetry-worker", "model.monitor.finished",
        {
            "schema_version": 1, "questions_seen": 1,
            "questions_persisted": 1, "write_failures": 0, "complete": True,
        },
    )

    hosted = object.__new__(HostedSimulatorRuns)
    hosted.repository = repository
    view = hosted.model_calls(queued["run_id"])
    assert view["availability"] == "available"
    assert view["configuration"] == "configured"
    assert view["summary"]["complete"] is True
    assert [entry["question_index"] for entry in view["items"]] == [1]
    assert "DO_NOT_PERSIST" not in str(view)
    assert repository.model_events(
        queued["run_id"], "model.call", actor_id="other-actor"
    ) == []

    repository.transition(
        claim, "model-telemetry-worker", "completed", "run.completed",
        {"status": "completed", "mode": "triage"},
    )
    with pytest.raises(LostLease):
        repository.publish_model_event(
            claim, "model-telemetry-worker", "model.call", safe_call
        )


def test_hosted_uses_prior_safe_stage_contract_after_pr294_merge():
    """Never reimplement #296 nested Decide event sanitizer in hosted."""
    from capstone.api import runs
    from capstone.api.run_repository import StagePayload

    if hasattr(runs, "SafeStageSnapshot"):
        assert StagePayload is runs.SafeStageSnapshot
        if "decide_events_recent" in runs.SafeStageSnapshot.model_fields:
            assert "decide_events_recent" in StagePayload.model_fields


def test_queued_run_stays_queued_until_matching_build_can_claim(repository):
    """Never execute on a worker with different immutable strategy/build."""
    configured = RunExecutionConfig(source_revision="a" * 40)
    submitted = repository.submit(
        RunRequest(seed=101), "compatible-queue-revision-101",
        actor_id="hosted-simulator", effective_config=configured,
    )
    assert repository.claim(
        "worker-wrong-build",
        expected_config=RunExecutionConfig(source_revision="b" * 40),
    ) is None
    assert repository.get(submitted["run_id"])["state"] == "queued"
    claimed = repository.claim("worker-right-build", expected_config=configured)
    assert claimed is not None
    assert claimed.attempt == 1
    assert claimed.effective_config == configured


def test_worker_idle_pulse_is_durable_and_never_exposes_revision(repository):
    repository.worker_heartbeat(
        "worker:healthy", source_revision="a" * 40, status="idle"
    )
    metrics = repository.queue_metrics()
    assert metrics["worker_liveness"] == "healthy"
    assert metrics["healthy_workers"] >= 1
    assert metrics["last_worker_pulse_age_seconds"] is not None
    assert "worker:healthy" not in str(metrics)
    assert "a" * 40 not in str(metrics)
    with pytest.raises(ValueError):
        repository.worker_heartbeat(
            "worker:bad", source_revision="private-password", status="idle"
        )


def test_expiry_preserves_last_good_triage_and_never_replays(repository):
    from uuid import uuid4
    from capstone.api.run_repository import StagePayload

    submitted = repository.submit(
        RunRequest(seed=102), "progress-expiry-102-unique",
        actor_id="hosted-simulator", effective_config=RunExecutionConfig(),
    )
    claim = repository.claim("worker-one")
    assert claim is not None
    safe = StagePayload(
        investigation_id=str(uuid4()), mode="triage", stage="investigate",
        iteration_count=1, tool_calls=1, evidence_count=1,
        hypothesis_count=0, unresolved_question_ids=[],
        conclusion_available=False,
    ).model_dump(mode="json")
    repository.publish_progress(claim, "worker-one", safe)
    with repository.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE capstone_private.sim_jobs SET lease_until = "
            "CURRENT_TIMESTAMP - interval '1 second' WHERE run_id = %s",
            (claim.run_id,),
        )
    assert repository.recover_expired() == [submitted["run_id"]]
    view = repository.get(submitted["run_id"])
    assert view["state"] == "interrupted"
    assert view["snapshot"]["progress"]["triage"]["tool_calls"] == 1
    assert repository.claim("worker-two") is None


def test_terminal_progress_is_authoritative_over_late_queue_writer(repository):
    from uuid import uuid4
    from capstone.api.run_repository import StagePayload

    submitted = repository.submit(
        RunRequest(seed=103), "terminal-authoritative-103",
        actor_id="hosted-simulator", effective_config=RunExecutionConfig(),
    )
    claim = repository.claim("worker-one")
    assert claim is not None
    base = {
        "investigation_id": str(uuid4()), "mode": "triage",
        "iteration_count": 1, "tool_calls": 1, "evidence_count": 1,
        "hypothesis_count": 0, "unresolved_question_ids": [],
        "conclusion_available": False,
    }
    early = StagePayload(**base, stage="investigate").model_dump(mode="json")
    final = StagePayload(**{
        **base, "stage": "conclude", "iteration_count": 2,
        "conclusion_available": True,
    }).model_dump(mode="json")
    repository.publish_progress(claim, "worker-one", early)
    repository.transition(
        claim, "worker-one", "completed", "run.completed",
        {"status": "completed", "mode": "triage"},
        final_progress=final,
    )
    with pytest.raises(LostLease):
        repository.publish_progress(claim, "worker-one", early)
    row = repository.get(submitted["run_id"])
    assert row["snapshot"]["progress"]["triage"]["stage"] == "conclude"
    assert [event["event"] for event in repository.events_since(
        submitted["run_id"], 0
    )][-2:] == ["stage.updated", "run.completed"]


def test_worker_liveness_refuses_stale_render_revision(repository, monkeypatch):
    repository.worker_heartbeat(
        "worker:different", source_revision="a" * 40, status="idle"
    )
    monkeypatch.setenv("RENDER_GIT_COMMIT", "b" * 40)
    assert repository.queue_metrics()["worker_liveness"] == "revision_mismatch"
    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    assert repository.queue_metrics()["worker_liveness"] == "healthy"
