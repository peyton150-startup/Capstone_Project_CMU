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
            "capstone_private.sim_jobs, capstone_private.sim_runs"
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
