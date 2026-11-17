"""Transactional run queue shared by a web process and independent workers.

This module stores simulator requests and safe progress only. It imports no
agent, model provider, simulator, or pilot capture code. Starting an episode
requires a later worker claim with a live fencing token.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from capstone.api.run_models import SimJob, SimRun, SimRunEvent, SimRunReview
from capstone.api.runs import RunRequest

_IDEMPOTENCY = re.compile(r"[A-Za-z0-9_-]{16,96}\Z")
_ACTOR = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_OWNER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_EVENT = re.compile(r"[a-z][a-z0-9_.]{1,127}\Z")
_EVENT_FIELDS = {
    "run.queued": frozenset({"stage", "mode", "status"}),
    "run.started": frozenset({"mode", "status"}),
    "stage.updated": frozenset(
        {
            "investigation_id",
            "mode",
            "stage",
            "iteration_count",
            "tool_calls",
            "evidence_count",
            "hypothesis_count",
            "unresolved_question_ids",
            "termination_reason",
            "conclusion_available",
        }
    ),
    "review.requested": frozenset(
        {
            "proposal_id",
            "machine_id",
            "action",
            "reason",
            "predicted_effect",
            "note",
        }
    ),
    "review.decided": frozenset({"proposal_id", "decision", "status", "mode"}),
    "resync.required": frozenset({"dropped_ui_updates", "mode"}),
    "run.completed": frozenset(
        {
            "status",
            "mode",
            "investigation",
            "triage_report",
            "diagnosis",
            "recommendation",
            "action_executed",
            "verification_outcome",
            "deep_ran",
            "review_count",
        }
    ),
    "run.failed": frozenset({"status", "error_class", "mode"}),
    "run.interrupted": frozenset({"status", "reason"}),
}
_TERMINAL = frozenset({"completed", "failed", "interrupted", "expired"})
_TRANSITIONS = {
    "queued": frozenset({"running", "interrupted"}),
    "running": frozenset({"awaiting_review", "completed", "failed", "interrupted"}),
    "awaiting_review": frozenset({"running", "failed", "interrupted", "expired"}),
}


@dataclass(frozen=True)
class JobClaim:
    """The immutable worker authority for one already started episode."""

    run_id: uuid.UUID
    job_id: uuid.UUID
    lease_token: uuid.UUID
    request: RunRequest
    effective_config: RunExecutionConfig


class LostLease(RuntimeError):
    """The worker may no longer write or execute a run's pending action."""


class RunExecutionConfig(BaseModel):
    """Safe, resolved strategy fields persisted with a submitted run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    triage_plan: Literal["model", "fixed"] = "model"
    triage_investigate: Literal["off", "advisory", "on", "deterministic"] = "advisory"
    triage_hypothesize: Literal["model", "deterministic"] = "model"
    triage_evidence_tests: bool = True
    source_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{7,40}$")

    @model_validator(mode="after")
    def validate_strategy(self) -> "RunExecutionConfig":
        """Keep the persisted triage strategy internally consistent."""
        if self.triage_investigate == "deterministic" and self.triage_plan != "fixed":
            raise ValueError("Deterministic investigate requires a fixed plan")
        if self.triage_hypothesize == "deterministic" and (
            self.triage_plan != "fixed"
            or self.triage_investigate != "deterministic"
            or not self.triage_evidence_tests
        ):
            raise ValueError(
                "Deterministic hypothesize requires fixed deterministic triage"
            )
        return self


class RunRepository:
    """A short-transaction Postgres queue with idempotency and lease fencing."""

    def __init__(self, database_url: str, *, engine: Engine | None = None):
        """Validate the private database and create a bounded connection pool."""
        # Variables:
        #   database_url: Server-side Postgres connection string, never logged.
        #   engine: Optional test-owned engine; production builds its own pool.
        #   sslmode: TLS floor; preserve a caller's stronger certificate check.
        url = make_url(database_url)
        if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError("Hosted run repository requires PostgreSQL")
        sslmode = url.query.get("sslmode", "require")
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("Hosted run repository requires PostgreSQL TLS")
        if engine is None:
            connect_args = {"connect_timeout": 10}
            if "sslmode" not in url.query:
                connect_args["sslmode"] = "require"
            self.engine = create_engine(
                url.set(drivername="postgresql+psycopg"),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=0,
                pool_timeout=5,
                connect_args=connect_args,
            )
            self._owns_engine = True
        else:
            self.engine = engine
            self._owns_engine = False

    def close(self) -> None:
        """Release only the pool this repository created."""
        if self._owns_engine:
            self.engine.dispose()

    def ready(self) -> bool:
        """Check that the durable hosted schema is reachable and migrated."""
        # Variables:
        #   tables: All five hosted tables must exist before accepting work.
        from sqlalchemy import text

        with self.engine.connect() as connection:
            tables = connection.execute(
                text("""
                    SELECT to_regclass('capstone_private.sim_runs'),
                           to_regclass('capstone_private.sim_jobs'),
                           to_regclass('capstone_private.sim_run_events'),
                           to_regclass('capstone_private.sim_run_reviews'),
                           to_regclass('capstone_private.sim_run_artifacts')
                """)
            ).one()
        return all(table is not None for table in tables)

    @staticmethod
    def _view(run: SimRun) -> dict[str, Any]:
        """Return the public contract without actor, hash or private config."""
        return {
            "run_id": str(run.run_id),
            "requested": run.request,
            "state": run.state,
            "snapshot": run.snapshot,
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
        }

    @staticmethod
    def _append(
        session: Session, run: SimRun, event_name: str, payload: dict[str, Any]
    ) -> None:
        """Append an event while the caller holds the run row lock."""
        # Variables:
        #   session: The caller's open transaction, shared with its state change.
        #   run: Locked parent row that serializes event cursor allocation.
        #   seq: Next per-run cursor; row locking makes this allocation serial.
        if not _EVENT.fullmatch(event_name) or event_name not in _EVENT_FIELDS:
            raise ValueError("Invalid event name")
        if not payload.keys() <= _EVENT_FIELDS[event_name]:
            raise ValueError("Run event contains unapproved fields")
        if len(json.dumps(payload, separators=(",", ":")).encode("utf-8")) > 16_384:
            raise ValueError("Run event exceeds safe size limit")
        seq = session.scalar(
            select(func.coalesce(func.max(SimRunEvent.seq), 0) + 1).where(
                SimRunEvent.run_id == run.run_id
            )
        )
        session.add(
            SimRunEvent(
                run_id=run.run_id,
                seq=seq,
                event_name=event_name,
                payload=payload,
                created_at=datetime.now(timezone.utc),
            )
        )

    def submit(
        self,
        request: RunRequest,
        idempotency_key: str,
        *,
        actor_id: str,
        effective_config: RunExecutionConfig,
    ) -> dict[str, Any]:
        """Atomically create one run and job, or return the actor's same request."""
        # Variables:
        #   actor_id: Stable submitting identity; keys are scoped to this actor.
        #   idempotency_key: Retry identity for one immutable request.
        #   digest: Canonical request identity for conflict detection.
        #   existing: Row locked by the unique actor/key pair when replayed.
        #   effective_config: Safe resolved execution settings fixed at submit time.
        if not _IDEMPOTENCY.fullmatch(idempotency_key):
            raise ValueError("Invalid idempotency key")
        if not _ACTOR.fullmatch(actor_id):
            raise ValueError("Invalid actor identifier")
        encoded = json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        resolved_config = effective_config.model_dump(mode="json")
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            # This transaction lock is scoped to one actor/key. It prevents
            # racing duplicate submissions from observing a half-created job.
            from sqlalchemy import text

            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
                {"identity": actor_id + ":" + idempotency_key},
            )
            existing = session.scalar(
                select(SimRun)
                .where(
                    SimRun.actor_id == actor_id,
                    SimRun.idempotency_key == idempotency_key,
                )
                .with_for_update()
            )
            if existing is not None:
                if existing.request_hash != digest:
                    raise ValueError("Idempotency key belongs to another request")
                return self._view(existing)
            run = SimRun(
                run_id=uuid.uuid4(),
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                request_hash=digest,
                request=json.loads(encoded),
                effective_config=resolved_config,
                state="queued",
                snapshot={"stage": None, "mode": request.mode, "status": "queued"},
                version=0,
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            session.flush()
            session.add(
                SimJob(
                    job_id=uuid.uuid4(),
                    run_id=run.run_id,
                    status="queued",
                    enqueued_at=now,
                    priority=0,
                    attempt=0,
                )
            )
            self._append(session, run, "run.queued", run.snapshot)
            return self._view(run)

    def get(self, run_id: str, *, actor_id: str | None = None) -> dict[str, Any] | None:
        """Read one safe snapshot, optionally restricted to its submitting actor."""
        # Variables:
        #   actor_id: Optional owner filter; hosted API callers must supply it.
        try:
            parsed = uuid.UUID(run_id)
        except ValueError:
            return None
        with Session(self.engine) as session:
            query = select(SimRun).where(SimRun.run_id == parsed)
            if actor_id is not None:
                query = query.where(SimRun.actor_id == actor_id)
            run = session.scalar(query)
            return None if run is None else self._view(run)

    def list_runs(
        self, *, actor_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List bounded, newest-first safe snapshots for an authorized actor."""
        # Variables:
        #   actor_id: Optional owner filter; hosted API callers must supply it.
        with Session(self.engine) as session:
            query = (
                select(SimRun)
                .order_by(SimRun.created_at.desc())
                .limit(min(max(limit, 1), 100))
            )
            if actor_id is not None:
                query = query.where(SimRun.actor_id == actor_id)
            return [self._view(run) for run in session.scalars(query)]

    def events_since(
        self, run_id: str, seq: int, *, actor_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Replay ordered safe events after the client's last cursor."""
        # Variables:
        #   seq: Last event the client observed; replay begins after it.
        #   actor_id: Optional owner filter; hosted API callers must supply it.
        if self.get(run_id, actor_id=actor_id) is None:
            return []
        parsed = uuid.UUID(run_id)
        with Session(self.engine) as session:
            events = session.scalars(
                select(SimRunEvent)
                .where(SimRunEvent.run_id == parsed, SimRunEvent.seq > seq)
                .order_by(SimRunEvent.seq)
                .limit(min(max(limit, 1), 100))
            )
            return [
                {"seq": item.seq, "event": item.event_name, "data": item.payload}
                for item in events
            ]

    def claim(self, owner: str, *, lease_seconds: int = 60) -> JobClaim | None:
        """Claim one queued job without blocking another worker's claim."""
        # Variables:
        #   owner: Stable identity of this worker process for lease checks.
        #   lease_seconds: Bounded interval before an abandoned claim expires.
        #   token: New authority every time a worker claims an untouched job.
        #   job: Oldest available row locked with SKIP LOCKED for this transaction.
        if not _OWNER.fullmatch(owner) or not 15 <= lease_seconds <= 600:
            raise ValueError("Invalid worker identity or lease duration")
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            job = session.scalar(
                select(SimJob)
                .where(SimJob.status == "queued")
                .order_by(SimJob.priority.desc(), SimJob.enqueued_at, SimJob.job_id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            run = session.scalar(
                select(SimRun).where(SimRun.run_id == job.run_id).with_for_update()
            )
            if run is None or run.state != "queued":
                raise RuntimeError("Queued job has no queued run")
            token = uuid.uuid4()
            job.status = "claimed"
            job.lease_owner = owner
            job.lease_token = token
            job.lease_until = now + timedelta(seconds=lease_seconds)
            job.heartbeat_at = now
            job.attempt += 1
            run.state = "running"
            run.snapshot = {"status": "running", "mode": run.request["mode"]}
            run.version += 1
            run.updated_at = now
            self._append(session, run, "run.started", run.snapshot)
            return JobClaim(
                run.run_id,
                job.job_id,
                token,
                RunRequest.model_validate(run.request),
                RunExecutionConfig.model_validate(run.effective_config),
            )

    def heartbeat(
        self, claim: JobClaim, owner: str, *, lease_seconds: int = 60
    ) -> bool:
        """Renew only a still-current, unexpired lease."""
        # Variables:
        #   claim: Original fencing token issued to this worker.
        #   owner: Worker identity that must still match the stored lease.
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            job = session.scalar(
                select(SimJob).where(SimJob.job_id == claim.job_id).with_for_update()
            )
            if (
                job is None
                or job.status != "claimed"
                or job.lease_owner != owner
                or job.lease_token != claim.lease_token
                or job.lease_until is None
                or job.lease_until <= now
            ):
                return False
            job.lease_until = now + timedelta(seconds=lease_seconds)
            job.heartbeat_at = now
            return True

    def transition(
        self,
        claim: JobClaim,
        owner: str,
        state: str,
        event_name: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Commit a fenced state and event in the same short transaction."""
        # Variables:
        #   claim: Token issued at claim time; a stale worker cannot publish.
        #   owner: Worker identity checked together with the fencing token.
        #   state: Destination constrained by the current persisted state.
        #   snapshot: Safe new view committed with the matching event.
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            job = session.scalar(
                select(SimJob).where(SimJob.job_id == claim.job_id).with_for_update()
            )
            if (
                job is None
                or job.status != "claimed"
                or job.lease_owner != owner
                or job.lease_token != claim.lease_token
                or job.lease_until is None
                or job.lease_until <= now
            ):
                raise LostLease("Worker lease is no longer current")
            run = session.scalar(
                select(SimRun).where(SimRun.run_id == claim.run_id).with_for_update()
            )
            if run is None or state not in _TRANSITIONS.get(run.state, ()):
                raise ValueError("Invalid run state transition")
            run.state = state
            run.snapshot = snapshot
            run.version += 1
            run.updated_at = now
            if state in _TERMINAL:
                job.status = (
                    state
                    if state in {"completed", "failed", "interrupted"}
                    else "failed"
                )
                job.lease_until = None
            self._append(session, run, event_name, snapshot)
            return self._view(run)

    def recover_expired(self) -> list[str]:
        """Interrupt expired started jobs without replaying their episodes."""
        # Variables:
        #   job: Claimed work whose owning process stopped renewing its lease.
        #   interrupted: Run IDs changed to terminal interrupted for monitoring.
        now = datetime.now(timezone.utc)
        interrupted = []
        with Session(self.engine) as session, session.begin():
            jobs = session.scalars(
                select(SimJob)
                .where(SimJob.status == "claimed", SimJob.lease_until <= now)
                .with_for_update(skip_locked=True)
            ).all()
            for job in jobs:
                run = session.scalar(
                    select(SimRun).where(SimRun.run_id == job.run_id).with_for_update()
                )
                if run is None or run.state in _TERMINAL:
                    continue
                job.status = "interrupted"
                job.lease_until = None
                run.state = "interrupted"
                run.snapshot = {
                    "status": "interrupted",
                    "reason": "worker_lease_expired",
                }
                run.version += 1
                run.updated_at = now
                for review in session.scalars(
                    select(SimRunReview)
                    .where(
                        SimRunReview.run_id == run.run_id,
                        SimRunReview.status == "pending",
                    )
                    .with_for_update()
                ):
                    review.status = "expired"
                    review.version += 1
                self._append(session, run, "run.interrupted", run.snapshot)
                interrupted.append(str(run.run_id))
        return interrupted
