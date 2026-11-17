"""PostgreSQL journal contract and opt-in localhost integration checks."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from capstone.api.config import UiConfig
from capstone.api.postgres_runs import _PostgresDB
from capstone.api.runs import RunRequest

TOKEN = "viewer-abcdefghijklmnopqrstuvwxyz"
OPERATOR = "operator-abcdefghijklmnopqrstuvwxyz"
REVIEWER = "reviewer-abcdefghijklmnopqrstuvwxyz"


def remote_config(tmp_path, url="postgresql://tester:secret@localhost/capstone_test"):
    return UiConfig(
        token=TOKEN,
        run_token=OPERATOR,
        review_token=REVIEWER,
        run_db=tmp_path / "journal.sqlite",
        runs_enabled=True,
        run_backend="postgres",
        run_database_url=url,
    )


def test_remote_configuration_requires_url_and_staging_directory(tmp_path):
    with pytest.raises(ValueError, match="PostgreSQL journal"):
        remote_config(tmp_path, url="")
    with pytest.raises(ValueError, match="database"):
        UiConfig(
            token=TOKEN,
            run_token=OPERATOR,
            review_token=REVIEWER,
            runs_enabled=True,
            run_backend="postgres",
            run_database_url="postgresql://test:secret@localhost/capstone_test",
        )
    assert "secret" not in repr(remote_config(tmp_path))


def test_remote_backend_does_not_open_a_database_by_default(tmp_path):
    c = UiConfig(
        token=TOKEN,
        run_token=OPERATOR,
        review_token=REVIEWER,
        run_db=tmp_path / "local.sqlite",
        runs_enabled=True,
    )
    assert c.run_backend == "sqlite"
    assert c.run_database_url is None


def test_postgres_adapter_preserves_parameterized_sql_without_interpolating():
    calls = []

    class Cursor:
        def execute(self, sql, params):
            calls.append((sql, params))
            return self

    db = _PostgresDB(SimpleNamespace(cursor=lambda: Cursor()))
    db.execute(
        "SELECT run_id FROM runs WHERE run_id=? AND request_key=?",
        ("run-a", "quote' or 1=1 --"),
    )
    assert calls == [
        (
            "SELECT run_id FROM runs WHERE run_id=%s AND request_key=%s",
            ("run-a", "quote' or 1=1 --"),
        )
    ]


def test_sqlite_import_preview_is_read_only_and_includes_private_artifacts(tmp_path):
    import json
    import uuid

    from capstone.api.import_sqlite import preview
    from capstone.api.runs import SimulatorRuns

    db_path = tmp_path / "local-runs.sqlite"
    source = SimulatorRuns(db_path)
    run_id = str(uuid.uuid4())
    with source._db() as db:
        db.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, "preview-import-key-0001", '{"seed":1}', "running",
                '{"status":"running"}', "2026-11-16T00:00:00Z",
                "2026-11-16T00:00:00Z",
            ),
        )
        db.execute(
            "INSERT INTO run_events VALUES (?, ?, ?, ?, ?)",
            (
                run_id, 1, "run.started", json.dumps({"status": "running"}),
                "2026-11-16T00:00:00Z",
            ),
        )
        db.execute(
            "INSERT INTO run_reviews VALUES (?, ?, ?, ?)",
            (run_id, 1, "pending", '{"proposal_id":1}'),
        )
    path = source.investigation_audit_path(run_id)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"record_type":"audit"}\\n')
    before = hashlib.sha256(db_path.read_bytes()).digest()
    result = preview(db_path)
    assert result == {
        "runs": 1, "events": 1, "reviews": 1, "artifacts": 1,
        "missing_artifacts": 1, "will_interrupt_incomplete_runs": 1,
        "source_unchanged": True,
    }
    assert hashlib.sha256(db_path.read_bytes()).digest() == before
    assert source.get(run_id)["state"] == "running"


@pytest.fixture
def localhost_postgres(monkeypatch, tmp_path):
    url = os.environ.get("CAPSTONE_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Optional ephemeral PostgreSQL integration environment missing")
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("psycopg")
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    if parsed.host not in ("localhost", "127.0.0.1") or parsed.database != "capstone_test":
        pytest.fail("Integration database must be localhost/capstone_test, never hosted")
    from alembic import command
    from alembic.config import Config

    import capstone.settings as settings_module
    from capstone.settings import Settings

    settings = Settings(_env_file=None, DATABASE_URL=url)
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    from capstone.api.postgres_runs import PostgresSimulatorRuns

    instance = PostgresSimulatorRuns(url, tmp_path)
    yield instance
    instance.close()


def test_remote_idempotency_events_and_reopen(localhost_postgres, monkeypatch):
    from capstone.api.postgres_runs import PostgresSimulatorRuns

    journal = localhost_postgres
    # A second server with live ownership must fail closed.
    with pytest.raises(RuntimeError, match="owns"):
        PostgresSimulatorRuns(
            os.environ["CAPSTONE_TEST_POSTGRES_URL"], journal.artifact_root
        )

    def finish(self, run_id, request):
        self._emit(run_id, "run.completed", {"status": "completed"}, state="completed")
        with self.lock:
            self.active.discard(run_id)

    monkeypatch.setattr(PostgresSimulatorRuns, "_execute", finish)
    key = "idempotent-postgres-001"
    first = journal.submit(RunRequest(seed=7), key)
    run_id = first["run_id"]
    for _ in range(200):
        if journal.get(run_id)["state"] == "completed":
            break
        time.sleep(0.01)
    assert journal.get(run_id)["state"] == "completed"
    assert journal.submit(RunRequest(seed=7), key)["run_id"] == run_id
    with pytest.raises(ValueError, match="idempotency"):
        journal.submit(RunRequest(seed=8), key)
    assert journal.events_since(run_id, 0)[0]["event"] == "run.completed"
    assert journal.events_since(run_id, 1) == []


def test_remote_artifacts_are_private_durable_and_checked(localhost_postgres):
    journal = localhost_postgres
    with journal._db() as db:
        db.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "import-test",
                "artifact-postgres-0001",
                '{"seed":1}',
                "completed",
                '{"status":"completed"}',
                "2026-11-16T00:00:00+00:00",
                "2026-11-16T00:00:00+00:00",
            ),
        )
    # The journal's file method requires a UUID; use a legitimate run for the test.
    import uuid

    run_id = str(uuid.uuid4())
    with journal._db() as db:
        db.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                "artifact-postgres-0002",
                '{"seed":1}',
                "completed",
                '{"status":"completed"}',
                "2026-11-16T00:00:00+00:00",
                "2026-11-16T00:00:00+00:00",
            ),
        )
    audit = journal.investigation_audit_path(run_id)
    events = journal.investigation_event_path(run_id)
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_bytes(b'{"record_type":"audit"}\n')
    events.write_bytes(b'{"record_type":"event"}\n')
    journal._persist_artifacts(run_id)
    expected = hashlib.sha256(audit.read_bytes()).hexdigest()
    with journal._db() as db:
        row = db.execute(
            "SELECT sha256 FROM run_artifacts WHERE run_id=? AND artifact_type='audit'",
            (run_id,),
        ).fetchone()
    assert row[0] == expected
    audit.unlink()
    events.unlink()
    assert journal.investigation_audit_path(run_id).read_bytes() == b'{"record_type":"audit"}\n'
    assert journal.investigation_event_path(run_id).read_bytes() == b'{"record_type":"event"}\n'
