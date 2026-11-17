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

from capstone.api.run_models import (
    SimJob,
    SimRun,
    SimRunArtifact,
    SimRunEvent,
    SimRunReview,
)
from capstone.api.runs import ReviewDecision, RunRequest

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
    queue_wait_ms: int = 0
    attempt: int = 1


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



class SafeRequirementProgress(BaseModel):
    """Exact safe requirement identity and disposition; no evidence payload."""

    model_config = ConfigDict(extra="forbid", strict=True)
    requirement_id: str = Field(
        pattern=r"^Q[0-9]{1,3}:(?:[a-z_]{1,24}|job:[0-9]{1,8})$"
    )
    status: Literal[
        "pending", "satisfied", "partial", "insufficient", "stale",
        "unavailable", "unsupported", "failed",
    ]
    evidence_count: int = Field(ge=0, le=100_000)


class StagePayload(BaseModel):
    """Source-matched safe progress for #294, with legacy fields optional."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    investigation_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    mode: Literal["triage", "deep"]
    stage: Literal[
        "observe", "manual", "plan", "investigate", "hypothesize",
        "test", "critique", "recheck", "conclude", "decide",
        "propose", "execute", "verify",
    ] | None = None
    iteration_count: int = Field(ge=0, le=100_000)
    tool_calls: int = Field(ge=0, le=100_000)
    evidence_count: int = Field(ge=0, le=100_000)
    hypothesis_count: int = Field(ge=0, le=100_000)
    unresolved_question_ids: list[str] = Field(max_length=25)
    unresolved_question_count: int = Field(default=0, ge=0)
    termination_reason: str | None = Field(
        default=None, pattern=r"^[a-z][a-z_]{0,63}$"
    )
    conclusion_available: bool

    # The following are only Graph-derived counts and booleans. Raw tool
    # responses, provider content and simulator ground truth are excluded.
    answered_question_count: int = Field(default=0, ge=0)
    decision_count: int = Field(default=0, ge=0)
    remaining_iterations: int = Field(default=0, ge=0)
    remaining_tool_calls: int = Field(default=0, ge=0)
    repeated_calls: int = Field(default=0, ge=0)
    failed_tool_calls: int = Field(default=0, ge=0)
    malformed_results: int = Field(default=0, ge=0)
    interpretation_failures: int = Field(default=0, ge=0)
    unproductive_steps: int = Field(default=0, ge=0)
    followup_tool_calls: int = Field(default=0, ge=0)
    screening_tool_calls: int = Field(default=0, ge=0)
    observe_tool_calls: int = Field(default=0, ge=0)
    last_observed_tick: int | None = Field(default=None, ge=0)
    observation_cutoff_tick: int | None = Field(default=None, ge=0)
    clock_verified: bool | None = None
    triage_requirement_total: int = Field(default=0, ge=0)
    triage_requirement_satisfied: int = Field(default=0, ge=0)
    triage_requirement_open: int = Field(default=0, ge=0)
    triage_question_gaps: int = Field(default=0, ge=0)
    triage_evidence_accepted: int = Field(default=0, ge=0)
    triage_evidence_rejected: int = Field(default=0, ge=0)
    triage_decide_reads: int = Field(default=0, ge=0)
    triage_decide_stops: int = Field(default=0, ge=0)
    triage_candidates: int = Field(default=0, ge=0)
    triage_test_requirements: int = Field(default=0, ge=0)
    triage_trace_events: int = Field(default=0, ge=0)
    triage_logging_failures: int = Field(default=0, ge=0)
    deep_recommended: bool | None = None
    packet_roster_verified: bool | None = None
    packet_roster_size: int = Field(default=0, ge=0)
    packet_screened_machines: int = Field(default=0, ge=0)
    packet_missing_machines: int = Field(default=0, ge=0)
    packet_calls_mandatory: int = Field(default=0, ge=0)
    packet_calls_optional: int = Field(default=0, ge=0)
    packet_calls_qualified: int = Field(default=0, ge=0)
    packet_calls_unavailable: int = Field(default=0, ge=0)
    packet_items_qualified: int = Field(default=0, ge=0)
    packet_items_missing: int = Field(default=0, ge=0)
    triage_test_records: int = Field(default=0, ge=0)
    requirement_statuses: list[SafeRequirementProgress] = Field(
        default_factory=list, max_length=32
    )
    requirement_statuses_truncated: bool = False

    @model_validator(mode="after")
    def check_ids(self) -> "StagePayload":
        if any(
            not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", item)
            for item in self.unresolved_question_ids
        ):
            raise ValueError("Unapproved question identifier")
        return self


# Durable event allowlist evolves with the exact typed safe contract.
# No raw state/model dumps are accepted, even when the frontend expands.
_EVENT_FIELDS["stage.updated"] = frozenset(StagePayload.model_fields)


class ReviewProposal(BaseModel):
    """Bounded, machine-facing proposal for the authorized reviewer."""

    model_config = ConfigDict(extra="forbid", strict=True)
    proposal_id: int = Field(ge=1)
    machine_id: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=160)
    reason: str = Field(max_length=600)
    predicted_effect: str = Field(max_length=600)
    note: str = Field(default="", max_length=200)

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
        if not all(table is not None for table in tables):
            return False
        with self.engine.connect() as connection:
            from sqlalchemy import text

            return bool(
                connection.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_schema='capstone_private' "
                        "AND table_name='sim_run_artifacts' "
                        "AND column_name='content'"
                    )
                ).scalar_one_or_none()
            )

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
                max(0, int((now - job.enqueued_at).total_seconds() * 1000)),
                job.attempt,
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
            # Retain the live phase counters on completion and failure.
            # The public event payload remains the original allowlisted snapshot.
            previous_progress = (run.snapshot or {}).get("progress")
            run.state = state
            run.snapshot = {
                **snapshot,
                **(
                    {"progress": previous_progress}
                    if state in _TERMINAL and previous_progress
                    else {}
                ),
            }
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


    @staticmethod
    def _fenced_job(session: Session, claim: JobClaim, owner: str) -> SimJob:
        """Validate the committed lease before every worker-owned mutation."""
        # Variables:
        #   claim: Immutable job and fencing token from the atomic queue claim.
        #   owner: Expected process identity; the same owner heartbeats the lease.
        job = session.scalar(
            select(SimJob).where(SimJob.job_id == claim.job_id).with_for_update()
        )
        if (
            job is None
            or job.run_id != claim.run_id
            or job.status != "claimed"
            or job.lease_owner != owner
            or job.lease_token != claim.lease_token
            or job.lease_until is None
            or job.lease_until <= datetime.now(timezone.utc)
        ):
            raise LostLease("Worker lease is no longer current")
        return job

    def publish_progress(
        self, claim: JobClaim, owner: str, progress: dict[str, Any]
    ) -> None:
        """Commit a typed phase update and replay event with the active lease."""
        # Variables:
        #   safe: The only graph-derived payload allowed into the public journal.
        #   phase_progress: Previous other-phase progress, preserved during updates.
        safe = StagePayload.model_validate(progress).model_dump(
            mode="json", exclude_unset=True
        )
        with Session(self.engine) as session, session.begin():
            self._fenced_job(session, claim, owner)
            run = session.scalar(
                select(SimRun).where(SimRun.run_id == claim.run_id).with_for_update()
            )
            if run is None or run.state not in {"running", "awaiting_review"}:
                raise LostLease("Run cannot receive progress")
            phase_progress = dict(run.snapshot.get("progress") or {})
            phase_progress[safe["mode"]] = safe
            phase_progress["latest"] = safe
            run.snapshot = {**run.snapshot, "progress": phase_progress}
            run.version += 1
            run.updated_at = datetime.now(timezone.utc)
            self._append(session, run, "stage.updated", safe)

    def publish_resync(
        self, claim: JobClaim, owner: str, dropped_count: int
    ) -> None:
        """Record lost UI messages without exception or provider text."""
        # Variables:
        #   dropped_count: Bounded number of failed live progress updates.
        if type(dropped_count) is not int or not 1 <= dropped_count <= 1_000_000:
            raise ValueError("Invalid dropped progress count")
        with Session(self.engine) as session, session.begin():
            self._fenced_job(session, claim, owner)
            run = session.scalar(
                select(SimRun).where(SimRun.run_id == claim.run_id).with_for_update()
            )
            if run is None or run.state != "running":
                raise LostLease("Cannot mark resync on inactive run")
            self._append(
                session, run, "resync.required",
                {"dropped_ui_updates": dropped_count, "mode": claim.request.mode},
            )

    def request_review(
        self,
        claim: JobClaim,
        owner: str,
        proposal: ReviewProposal,
        *,
        timeout_seconds: int = 240,
    ) -> None:
        """Persist exact proposal and review event before human polling starts."""
        # Variables:
        #   proposal: Typed reviewer-facing text, not the raw graph or model trace.
        #   timeout_seconds: Absolute database-visible approval deadline.
        if not 10 <= timeout_seconds <= 1800:
            raise ValueError("Approval timeout out of range")
        safe = proposal.model_dump(mode="json")
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            self._fenced_job(session, claim, owner)
            run = session.scalar(
                select(SimRun).where(SimRun.run_id == claim.run_id).with_for_update()
            )
            if run is None or run.state != "running":
                raise ValueError("Run not available for review")
            if session.get(SimRunReview, (claim.run_id, proposal.proposal_id)):
                raise ValueError("Proposal review already exists")
            session.add(
                SimRunReview(
                    run_id=claim.run_id,
                    proposal_id=proposal.proposal_id,
                    proposal=safe,
                    status="pending",
                    decision_actor=None,
                    decision_at=None,
                    deadline_at=now + timedelta(seconds=timeout_seconds),
                    version=0,
                )
            )
            run.state = "awaiting_review"
            run.snapshot = {**run.snapshot, "status": "awaiting_review"}
            run.version += 1
            run.updated_at = now
            self._append(session, run, "review.requested", safe)

    def review_status(
        self, claim: JobClaim, owner: str, proposal_id: int
    ) -> str:
        """Read a durable verdict only while the original worker still owns work."""
        with Session(self.engine) as session, session.begin():
            self._fenced_job(session, claim, owner)
            row = session.get(SimRunReview, (claim.run_id, proposal_id))
            if row is None:
                raise LookupError("Proposal review missing")
            if row.status == "pending" and row.deadline_at <= datetime.now(timezone.utc):
                # Polling never treats a late approval as permission to execute.
                row.status = "expired"
                row.version += 1
            return row.status

    def resume_review(self, claim: JobClaim, owner: str) -> None:
        """Resume the graph without discarding the persisted phase snapshots."""
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            self._fenced_job(session, claim, owner)
            run = session.scalar(
                select(SimRun).where(SimRun.run_id == claim.run_id).with_for_update()
            )
            if run is None or run.state != "awaiting_review":
                raise ValueError("Run is not awaiting review")
            run.state = "running"
            run.snapshot = {**run.snapshot, "status": "running"}
            run.version += 1
            run.updated_at = now
            self._append(
                session, run, "run.started",
                {"status": "running", "mode": claim.request.mode},
            )

    def pending_reviews(
        self, *, actor_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return only still-pending proposals owned by the authorized actor."""
        with Session(self.engine) as session:
            items = session.execute(
                select(SimRunReview, SimRun)
                .join(SimRun, SimRun.run_id == SimRunReview.run_id)
                .where(
                    SimRun.actor_id == actor_id,
                    SimRun.state == "awaiting_review",
                    SimRunReview.status == "pending",
                    SimRunReview.deadline_at > datetime.now(timezone.utc),
                )
                .order_by(SimRunReview.deadline_at)
                .limit(min(max(limit, 1), 100))
            ).all()
            return [
                {
                    "run_id": str(run.run_id),
                    **review.proposal,
                    "status": "pending",
                }
                for review, run in items
            ]

    def decide_review(
        self,
        run_id: str,
        decision: "ReviewDecision",
        *,
        actor_id: str,
        reviewer_id: str,
    ) -> dict[str, Any]:
        """Commit a reviewer verdict once; duplicates or expired approvals fail."""
        # Variables:
        #   actor_id: Server-authorized owner; never browser-supplied.
        #   reviewer_id: Safe, server-provided reviewer principal, not a credential.
        if not _ACTOR.fullmatch(reviewer_id):
            raise ValueError("Invalid reviewer identity")
        try:
            ident = uuid.UUID(run_id)
        except ValueError:
            raise LookupError("Run not found") from None
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            run = session.scalar(
                select(SimRun)
                .where(SimRun.run_id == ident, SimRun.actor_id == actor_id)
                .with_for_update()
            )
            if run is None:
                raise LookupError("Run not found")
            review = session.scalar(
                select(SimRunReview)
                .where(
                    SimRunReview.run_id == ident,
                    SimRunReview.proposal_id == decision.proposal_id,
                )
                .with_for_update()
            )
            active_job = session.scalar(
                select(SimJob).where(SimJob.run_id == ident)
            )
            if (
                review is None
                or run.state != "awaiting_review"
                or review.status != "pending"
                or review.deadline_at <= now
                or active_job is None
                or active_job.status != "claimed"
                or active_job.lease_until is None
                or active_job.lease_until <= now
            ):
                raise ValueError("Review is no longer pending")
            review.status = decision.decision
            review.decision_actor = reviewer_id
            review.decision_at = now
            review.version += 1
            # Reviewer note stays private. Never emit raw supplied text in SSE.
            review.proposal = {
                **review.proposal,
                "note": decision.note,
            }
            self._append(
                session, run, "review.decided",
                {
                    "proposal_id": decision.proposal_id,
                    "decision": decision.decision,
                    "status": "decided_not_executed",
                    "mode": run.request["mode"],
                },
            )
            run.version += 1
            run.updated_at = now
            return {
                "run_id": run_id,
                "proposal_id": decision.proposal_id,
                "decision": decision.decision,
            }

    def store_artifacts(
        self, claim: JobClaim, owner: str, artifacts: dict[str, bytes]
    ) -> None:
        """Store bounded private audits under the lease before declaring success."""
        # Variables:
        #   artifacts: Audit and operational JSONL bytes, never streamed to a browser.
        #   digest: Content checksum for detecting corrupted private storage.
        if set(artifacts) != {"audit", "observability"}:
            raise ValueError("Both private artifacts are required")
        for data in artifacts.values():
            if not isinstance(data, bytes) or not 0 < len(data) <= 8_388_608:
                raise ValueError("Private artifact is empty or exceeds 8 MiB")
        with Session(self.engine) as session, session.begin():
            self._fenced_job(session, claim, owner)
            run = session.scalar(
                select(SimRun).where(SimRun.run_id == claim.run_id).with_for_update()
            )
            if run is None or run.state != "running":
                raise LostLease("Run cannot persist artifacts")
            existing = session.scalars(
                select(SimRunArtifact)
                .where(SimRunArtifact.run_id == claim.run_id)
            ).all()
            if existing:
                raise ValueError("Run artifacts already persisted")
            for kind, data in artifacts.items():
                session.add(
                    SimRunArtifact(
                        artifact_id=uuid.uuid4(),
                        run_id=claim.run_id,
                        kind=kind,
                        storage_key=f"postgres-private/{claim.run_id}/{kind}",
                        sha256=hashlib.sha256(data).hexdigest(),
                        byte_count=len(data),
                        visibility="private",
                        retention_until=None,
                        content=data,
                    )
                )

    def read_artifact(
        self, run_id: str, kind: Literal["audit", "observability"], *,
        actor_id: str,
    ) -> bytes | None:
        """Read a private blob for server-side safe projection only."""
        try:
            ident = uuid.UUID(run_id)
        except ValueError:
            return None
        with Session(self.engine) as session:
            row = session.scalar(
                select(SimRunArtifact)
                .join(SimRun, SimRun.run_id == SimRunArtifact.run_id)
                .where(
                    SimRunArtifact.run_id == ident,
                    SimRunArtifact.kind == kind,
                    SimRun.actor_id == actor_id,
                )
            )
            if row is None or row.content is None:
                return None
            body = bytes(row.content)
            if hashlib.sha256(body).hexdigest() != row.sha256:
                raise RuntimeError("Private artifact checksum mismatch")
            return body

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
