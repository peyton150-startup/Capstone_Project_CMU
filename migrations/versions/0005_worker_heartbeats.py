"""Record live/idle Render worker health without exposing graph or provider data.

Revision ID: 0005_worker_heartbeats
Revises: 0004_worker_artifacts
"""

from alembic import op

revision = "0005_worker_heartbeats"
down_revision = "0004_worker_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        CREATE TABLE capstone_private.sim_worker_heartbeats (
            worker_id VARCHAR(128) PRIMARY KEY,
            source_revision VARCHAR(40),
            status VARCHAR(16) NOT NULL
                CONSTRAINT ck_sim_worker_heartbeat_status
                CHECK (status IN ('idle', 'running')),
            last_seen_at TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute("REVOKE ALL ON TABLE capstone_private.sim_worker_heartbeats FROM PUBLIC")
    op.execute(
        "ALTER TABLE capstone_private.sim_worker_heartbeats ENABLE ROW LEVEL SECURITY"
    )
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON capstone_private.sim_worker_heartbeats FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON capstone_private.sim_worker_heartbeats FROM authenticated;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
                REVOKE ALL ON capstone_private.sim_worker_heartbeats FROM service_role;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # Health pulses may be dropped; they are not investigation evidence.
    op.execute("DROP TABLE capstone_private.sim_worker_heartbeats")
