"""Optional PostgreSQL backend for the existing single-host simulator runner.

The SQL contract remains identical to the SQLite journal. A database-level
session lock deliberately prevents multiple FastAPI processes from hosting
independent in-memory approval desks against one journal. A separate worker
service will need an explicit queue and redesigned review dispatch.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from capstone.api.runs import SimulatorRuns

_OWNER_LOCK = (704120, 20261116)
_SUBMIT_LOCK = (704120, 20261117)
_MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


class _PostgresDB:
    """Restricted adapter for the already parameterized SQLite journal SQL."""

    def __init__(self, connection: Any):
        self.connection = connection

    def execute(self, query: str, parameters: tuple[Any, ...] = ()) -> Any:
        # The runner only uses positional placeholders; no user SQL is accepted.
        return self.connection.cursor().execute(query.replace("%", "%%").replace("?", "%s"), parameters)


class PostgresSimulatorRuns(SimulatorRuns):
    """Run journal on Supabase PostgreSQL, with a single live worker owner.

    Connection strings and database exceptions are never returned to clients.
    The Render process must use a direct or *session* pooler connection, not
    transaction pooling, because ownership uses a session advisory lock.
    """

    def __init__(
        self,
        database_url: str,
        artifact_root: Path,
        *,
        approval_timeout_seconds: float = 240,
        recover_existing: bool = True,
    ):
        self._recover_existing = recover_existing
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.engine import make_url

            url = make_url(database_url)
            if url.drivername not in (
                "postgres",
                "postgresql",
                "postgresql+psycopg",
            ):
                raise ValueError("Simulator PostgreSQL requires a PostgreSQL URL")
            if url.port == 6543:
                raise ValueError(
                    "Simulator PostgreSQL requires direct or session pooling, "
                    "not the transaction pooler on port 6543"
                )
            url = url.set(drivername="postgresql+psycopg")
            self._engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_size=4,
                max_overflow=0,
                pool_timeout=5,
                pool_recycle=300,
                connect_args={"connect_timeout": 10, "sslmode": "require"},
            )
        except ValueError as error:
            if str(error).startswith(("Simulator PostgreSQL requires",)):
                raise
            raise RuntimeError("PostgreSQL journal URL is invalid") from None
        except Exception:
            raise RuntimeError(
                "PostgreSQL journal configuration invalid or database extra missing"
            ) from None

        self._ownership_lock = threading.Lock()
        self._owner: Any = None
        try:
            self._owner = self._engine.raw_connection()
            cursor = self._owner.cursor()
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", _OWNER_LOCK)
            held = cursor.fetchone()[0]
            cursor.close()
            self._owner.commit()
            if not held:
                raise RuntimeError(
                    "Another simulator API process owns the PostgreSQL journal"
                )
            # The filename is never used as SQLite; only its directory is the
            # private, bounded local audit staging area.
            super().__init__(
                artifact_root / "managed-simulator-postgres",
                approval_timeout_seconds=approval_timeout_seconds,
            )
        except Exception:
            self.close()
            raise

    def _assert_owner(self) -> None:
        # Session locking is useless if the owning connection silently dies.
        # Refuse subsequent operations; do not elect ourselves again.
        with self._ownership_lock:
            try:
                cursor = self._owner.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                self._owner.commit()
            except Exception:
                raise RuntimeError(
                    "Simulator database ownership has been lost"
                ) from None

    @contextmanager
    def _db(self):
        self._assert_owner()
        try:
            connection = self._engine.raw_connection()
        except Exception:
            raise RuntimeError("PostgreSQL run journal unavailable") from None
        try:
            cursor = connection.cursor()
            cursor.execute("SET LOCAL search_path TO capstone_private, pg_catalog")
            cursor.close()
            yield _PostgresDB(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_store(self) -> None:
        """Require explicit migration and recover only after exclusive ownership."""
        with self._db() as db:
            for name in ("runs", "run_events", "run_reviews", "run_artifacts"):
                row = db.execute(
                    "SELECT to_regclass(%s)",
                    (f"capstone_private.{name}",),
                ).fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError(
                        "PostgreSQL simulator schema missing; apply Alembic head "
                        "before enabling the remote journal"
                    )
            if self._recover_existing:
                db.execute(
                    "UPDATE runs SET state='interrupted', updated_at=? "
                    "WHERE state IN ('queued', 'running', 'awaiting_review')",
                    (self._now(),),
                )
                db.execute(
                    "UPDATE run_reviews SET status='expired' WHERE status='pending'"
                )

    @staticmethod
    def _now() -> str:
        from capstone.api.runs import utc_now

        return utc_now()

    def _lock_submission(self, db: Any) -> None:
        db.execute("SELECT pg_advisory_xact_lock(%s, %s)", _SUBMIT_LOCK)

    def _store_has_active_run(self, db: Any) -> bool:
        return (
            db.execute(
                "SELECT 1 FROM runs WHERE state IN "
                "('queued', 'running', 'awaiting_review') LIMIT 1"
            ).fetchone()
            is not None
        )

    def _lock_event_sequence(self, db: Any, run_id: str) -> None:
        row = db.execute(
            "SELECT run_id FROM runs WHERE run_id=? FOR UPDATE", (run_id,)
        ).fetchone()
        if row is None:
            raise LookupError("Run not found")

    def _persist_artifacts(self, run_id: str) -> None:
        """Atomically copy bounded audit artifacts into private durable storage."""
        content = []
        for kind, path in (
            ("audit", super().investigation_audit_path(run_id)),
            ("observability", super().investigation_event_path(run_id)),
        ):
            try:
                if path.is_symlink():
                    raise RuntimeError("Symlinked simulator artifacts are prohibited")
                with path.open("rb") as stream:
                    data = stream.read(_MAX_ARTIFACT_BYTES + 1)
            except OSError:
                raise RuntimeError("Required simulator artifact missing") from None
            if not data or len(data) > _MAX_ARTIFACT_BYTES:
                raise RuntimeError("Simulator artifact missing or over size limit")
            content.append((kind, data, hashlib.sha256(data).hexdigest()))

        with self._db() as db:
            for kind, data, digest in content:
                db.execute(
                    "INSERT INTO run_artifacts (run_id, artifact_type, content, sha256) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (run_id, artifact_type) DO UPDATE "
                    "SET content=EXCLUDED.content, sha256=EXCLUDED.sha256, "
                    "recorded_at=CURRENT_TIMESTAMP",
                    (run_id, kind, data, digest),
                )

    def _restore_artifact(self, run_id: str, kind: str, path: Path) -> None:
        if path.is_symlink():
            raise RuntimeError("Symlinked simulator artifacts are prohibited")
        if path.is_file():
            return
        with self._db() as db:
            row = db.execute(
                "SELECT content, sha256 FROM run_artifacts "
                "WHERE run_id=? AND artifact_type=?",
                (run_id, kind),
            ).fetchone()
        if row is None:
            return
        data = bytes(row[0])
        if (
            len(data) > _MAX_ARTIFACT_BYTES
            or hashlib.sha256(data).hexdigest() != row[1]
        ):
            raise RuntimeError("Saved simulator artifact failed integrity check")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        name = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
                name = tmp.name
                os.chmod(name, 0o600)
                tmp.write(data)
            os.replace(name, path)
        finally:
            if name is not None and os.path.exists(name):
                os.unlink(name)

    def investigation_audit_path(self, run_id: str) -> Path:
        path = super().investigation_audit_path(run_id)
        self._restore_artifact(run_id, "audit", path)
        return path

    def investigation_event_path(self, run_id: str) -> Path:
        path = super().investigation_event_path(run_id)
        self._restore_artifact(run_id, "observability", path)
        return path

    def close(self) -> None:
        owner = getattr(self, "_owner", None)
        if owner is not None:
            try:
                owner.close()
            finally:
                self._owner = None
        engine = getattr(self, "_engine", None)
        if engine is not None:
            engine.dispose()
