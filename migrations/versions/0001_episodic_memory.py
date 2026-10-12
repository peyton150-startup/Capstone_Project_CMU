"""Create the accepted episodic-memory table and duplicate constraints.

Revision ID: 0001_episodic_memory
Revises: none
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_episodic_memory"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create storage structure; insert no investigation or lesson records."""
    # Freeze the initial schema here rather than importing evolving application
    # metadata, so later schema edits cannot change this historical revision.
    op.create_table(
        "episodic_memories",
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("source_tick", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("memory_id"),
        sa.UniqueConstraint("investigation_id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index("ix_episodic_memories_category", "episodic_memories", ["category"])


def downgrade() -> None:
    """Remove this storage table, including any lessons it contains."""
    op.drop_index("ix_episodic_memories_category", table_name="episodic_memories")
    op.drop_table("episodic_memories")
