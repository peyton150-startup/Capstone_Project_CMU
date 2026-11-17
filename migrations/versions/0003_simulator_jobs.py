"""Add a separate durable queue and safe hosted run journal.

Revision ID: 0003_simulator_jobs
Revises: 0002_simulator_journal

The older runs tables remain available for the opt-in single-host runner.
"""

from alembic import op
from sqlalchemy import text

revision = "0003_simulator_jobs"
down_revision = "0002_simulator_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create private hosted-run tables without altering the legacy journal."""
    # Variables:
    #   table: Each new server-only table receives restricted grants and RLS.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        CREATE TABLE capstone_private.sim_runs (
            run_id UUID PRIMARY KEY,
            actor_id VARCHAR(128) NOT NULL,
            idempotency_key VARCHAR(96) NOT NULL,
            request_hash VARCHAR(64) NOT NULL,
            request JSONB NOT NULL,
            effective_config JSONB NOT NULL,
            state VARCHAR(32) NOT NULL CHECK (state IN
                ('queued', 'running', 'awaiting_review', 'completed',
                 'failed', 'interrupted', 'expired')),
            snapshot JSONB NOT NULL,
            version INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_sim_run_actor_key UNIQUE (actor_id, idempotency_key)
        )
    """)
    op.execute("""
        CREATE TABLE capstone_private.sim_jobs (
            job_id UUID PRIMARY KEY,
            run_id UUID NOT NULL UNIQUE REFERENCES capstone_private.sim_runs(run_id),
            status VARCHAR(32) NOT NULL CHECK (status IN
                ('queued', 'claimed', 'completed', 'failed', 'interrupted')),
            enqueued_at TIMESTAMPTZ NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            lease_owner VARCHAR(128),
            lease_token UUID,
            lease_until TIMESTAMPTZ,
            heartbeat_at TIMESTAMPTZ,
            attempt INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT ck_sim_job_claim_has_lease CHECK (
                status != 'claimed' OR (lease_owner IS NOT NULL
                    AND lease_token IS NOT NULL AND lease_until IS NOT NULL))
        )
    """)
    op.execute("""
        CREATE INDEX ix_sim_jobs_claim ON capstone_private.sim_jobs
        (status, priority, enqueued_at, job_id)
    """)
    op.execute("""
        CREATE TABLE capstone_private.sim_run_events (
            run_id UUID NOT NULL REFERENCES capstone_private.sim_runs(run_id),
            seq INTEGER NOT NULL CHECK (seq > 0),
            event_name VARCHAR(128) NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (run_id, seq)
        )
    """)
    op.execute("""
        CREATE TABLE capstone_private.sim_run_reviews (
            run_id UUID NOT NULL REFERENCES capstone_private.sim_runs(run_id),
            proposal_id INTEGER NOT NULL,
            proposal JSONB NOT NULL,
            status VARCHAR(16) NOT NULL CHECK (status IN
                ('pending', 'approve', 'reject', 'expired')),
            decision_actor VARCHAR(128),
            decision_at TIMESTAMPTZ,
            deadline_at TIMESTAMPTZ NOT NULL,
            version INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, proposal_id)
        )
    """)
    op.execute("""
        CREATE TABLE capstone_private.sim_run_artifacts (
            artifact_id UUID PRIMARY KEY,
            run_id UUID NOT NULL REFERENCES capstone_private.sim_runs(run_id),
            kind VARCHAR(32) NOT NULL,
            storage_key VARCHAR(512) NOT NULL,
            sha256 VARCHAR(64) NOT NULL CHECK (length(sha256) = 64),
            byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
            visibility VARCHAR(16) NOT NULL,
            retention_until TIMESTAMPTZ
        )
    """)
    for table in (
        "sim_runs",
        "sim_jobs",
        "sim_run_events",
        "sim_run_reviews",
        "sim_run_artifacts",
    ):
        op.execute(f"REVOKE ALL ON TABLE capstone_private.{table} FROM PUBLIC")
        op.execute(f"ALTER TABLE capstone_private.{table} ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA capstone_private FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA capstone_private FROM authenticated;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA capstone_private FROM service_role;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    """Drop only empty new tables; never erase hosted run history implicitly."""
    # Variables:
    #   count: Existing hosted runs that make automatic rollback destructive.
    if op.get_bind().dialect.name != "postgresql":
        return
    count = (
        op.get_bind()
        .execute(text("SELECT COUNT(*) FROM capstone_private.sim_runs"))
        .scalar_one()
    )
    if count:
        raise RuntimeError("Export hosted simulator runs before an explicit downgrade")
    for table in (
        "sim_run_artifacts",
        "sim_run_reviews",
        "sim_run_events",
        "sim_jobs",
        "sim_runs",
    ):
        op.execute(f"DROP TABLE capstone_private.{table}")
