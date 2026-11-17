"""Typed private PostgreSQL tables for independently hosted simulator runs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class RunBase(DeclarativeBase):
    """Keep the hosted run schema separate from episodic memory metadata."""


class SimRun(RunBase):
    """One immutable request with its latest safe, versioned result snapshot."""

    __tablename__ = "sim_runs"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_sim_run_actor_key"),
        CheckConstraint(
            "state IN ('queued', 'running', 'awaiting_review', 'completed', "
            "'failed', 'interrupted', 'expired')",
            name="ck_sim_run_state",
        ),
        {"schema": "capstone_private"},
    )

    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(96), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    effective_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SimJob(RunBase):
    """A claimable job whose lease fences writes from old worker processes."""

    __tablename__ = "sim_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'claimed', 'completed', 'failed', 'interrupted')",
            name="ck_sim_job_status",
        ),
        CheckConstraint(
            "status != 'claimed' OR (lease_owner IS NOT NULL AND "
            "lease_token IS NOT NULL AND lease_until IS NOT NULL)",
            name="ck_sim_job_claim_has_lease",
        ),
        Index("ix_sim_jobs_claim", "status", "priority", "enqueued_at", "job_id"),
        {"schema": "capstone_private"},
    )

    job_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("capstone_private.sim_runs.run_id"),
        unique=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SimRunEvent(RunBase):
    """Safe events with an ordered cursor allocated under the run row lock."""

    __tablename__ = "sim_run_events"
    __table_args__ = ({"schema": "capstone_private"},)

    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("capstone_private.sim_runs.run_id"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SimRunReview(RunBase):
    """One persisted decision for the exact proposal the agent presented."""

    __tablename__ = "sim_run_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approve', 'reject', 'expired')",
            name="ck_sim_review_status",
        ),
        {"schema": "capstone_private"},
    )

    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("capstone_private.sim_runs.run_id"),
        primary_key=True,
    )
    proposal_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decision_actor: Mapped[str | None] = mapped_column(String(128))
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SimRunArtifact(RunBase):
    """Private artifact manifest; contents never enter an API response."""

    __tablename__ = "sim_run_artifacts"
    __table_args__ = ({"schema": "capstone_private"},)

    artifact_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("capstone_private.sim_runs.run_id"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
