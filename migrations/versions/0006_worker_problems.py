"""Keep each worker's latest process-level failure on its heartbeat row.

A worker that cannot poll the queue, cannot write its heartbeat, or starts with
missing source contracts has no run to record that on. These three nullable
columns hold one fixed code, when it happened and how many times, so the System
page can show it without the host's ephemeral logs. No exception text is kept.

Revision ID: 0006_worker_problems
Revises: 0005_worker_heartbeats
"""

from alembic import op

revision = "0006_worker_problems"
down_revision = "0005_worker_heartbeats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        ALTER TABLE capstone_private.sim_worker_heartbeats
            ADD COLUMN last_problem_code VARCHAR(32)
                CONSTRAINT ck_sim_worker_heartbeat_problem_code
                CHECK (last_problem_code IS NULL OR last_problem_code IN
                    ('poll_failed', 'worker_pulse_failed', 'contracts_missing')),
            ADD COLUMN last_problem_at TIMESTAMPTZ,
            ADD COLUMN last_problem_count INTEGER
                CONSTRAINT ck_sim_worker_heartbeat_problem_count
                CHECK (last_problem_count IS NULL OR
                    last_problem_count BETWEEN 0 AND 1000000)
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # Health diagnostics only; dropping them loses no investigation evidence.
    op.execute("""
        ALTER TABLE capstone_private.sim_worker_heartbeats
            DROP COLUMN last_problem_count,
            DROP COLUMN last_problem_at,
            DROP COLUMN last_problem_code
    """)
