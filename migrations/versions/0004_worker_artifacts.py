"""Add private bounded audit bytes without modifying R1's applied queue migration.

Revision ID: 0004_worker_artifacts
Revises: 0003_simulator_jobs
"""

from alembic import op
from sqlalchemy import text

revision = "0004_worker_artifacts"
down_revision = "0003_simulator_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep existing manifests readable, mark only new worker uploads complete."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE capstone_private.sim_run_artifacts ADD COLUMN content BYTEA"
    )


def downgrade() -> None:
    """Never silently drop privately persisted run evidence."""
    if op.get_bind().dialect.name != "postgresql":
        return
    existing = (
        op.get_bind()
        .execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM capstone_private.sim_run_artifacts "
                "WHERE content IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if existing:
        raise RuntimeError("Export private hosted audit artifacts before downgrade")
    op.execute("ALTER TABLE capstone_private.sim_run_artifacts DROP COLUMN content")
