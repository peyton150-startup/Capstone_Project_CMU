"""Add a private PostgreSQL journal for the managed simulator.

Revision ID: 0002_simulator_journal
Revises: 0001_episodic_memory

All private tables are intentionally outside the Supabase Data API's public
schema. Local SQLite continues to use SimulatorRuns' existing journal.
"""

from alembic import op

revision = "0002_simulator_journal"
down_revision = "0001_episodic_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a private, server-only run/event/review/artifact journal."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE SCHEMA IF NOT EXISTS capstone_private")
    op.execute("REVOKE ALL ON SCHEMA capstone_private FROM PUBLIC")
    op.execute("""
        CREATE TABLE capstone_private.runs (
            run_id TEXT PRIMARY KEY,
            request_key TEXT UNIQUE,
            requested TEXT NOT NULL,
            state TEXT NOT NULL
                CHECK (state IN ('queued', 'running', 'awaiting_review',
                                'completed', 'failed', 'interrupted')),
            snapshot TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX one_active_simulator_run
        ON capstone_private.runs ((1))
        WHERE state IN ('queued', 'running', 'awaiting_review')
    """)
    op.execute("""
        CREATE TABLE capstone_private.run_events (
            run_id TEXT NOT NULL REFERENCES capstone_private.runs(run_id),
            seq INTEGER NOT NULL CHECK (seq > 0),
            event TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, seq)
        )
    """)
    op.execute("""
        CREATE TABLE capstone_private.run_reviews (
            run_id TEXT NOT NULL REFERENCES capstone_private.runs(run_id),
            proposal_id INTEGER NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('pending', 'approve', 'reject', 'expired')),
            details TEXT NOT NULL,
            PRIMARY KEY (run_id, proposal_id)
        )
    """)
    op.execute("""
        CREATE INDEX run_reviews_pending
        ON capstone_private.run_reviews (run_id)
        WHERE status = 'pending'
    """)
    op.execute("""
        CREATE TABLE capstone_private.run_artifacts (
            run_id TEXT NOT NULL REFERENCES capstone_private.runs(run_id),
            artifact_type TEXT NOT NULL
                CHECK (artifact_type IN ('audit', 'observability')),
            content BYTEA NOT NULL,
            sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (run_id, artifact_type)
        )
    """)
    for name in ("runs", "run_events", "run_reviews", "run_artifacts"):
        op.execute(f"REVOKE ALL ON TABLE capstone_private.{name} FROM PUBLIC")
        op.execute(f"ALTER TABLE capstone_private.{name} ENABLE ROW LEVEL SECURITY")
    # The previously existing memory table is in public; explicitly protect it
    # even if a Supabase project's default public grants change in the future.
    op.execute("ALTER TABLE public.episodic_memories ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.episodic_memories FROM PUBLIC")
    # Supabase-specific roles may not exist on ordinary PostgreSQL/Neon.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON SCHEMA capstone_private FROM anon;
                REVOKE ALL ON ALL TABLES IN SCHEMA capstone_private FROM anon;
                REVOKE ALL ON TABLE public.episodic_memories FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON SCHEMA capstone_private FROM authenticated;
                REVOKE ALL ON ALL TABLES IN SCHEMA capstone_private FROM authenticated;
                REVOKE ALL ON TABLE public.episodic_memories FROM authenticated;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
                REVOKE ALL ON SCHEMA capstone_private FROM service_role;
                REVOKE ALL ON ALL TABLES IN SCHEMA capstone_private FROM service_role;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    """Never delete production investigation history through an automatic rollback."""
    if op.get_bind().dialect.name == "postgresql":
        raise RuntimeError(
            "Private simulator history downgrade requires an audited export and "
            "explicit destructive migration."
        )
