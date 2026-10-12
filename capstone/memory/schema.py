# Defines the relational table for accepted investigation lessons.
# Responsibility: enforce durable identity and duplicate constraints.
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, Uuid
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
episodic_memories = Table(
    "episodic_memories",
    metadata,
    Column("memory_id", Uuid, primary_key=True),
    Column("investigation_id", Uuid, nullable=False, unique=True),
    Column("category", String(128), nullable=False, index=True),
    Column("source_tick", Integer, nullable=False),
    Column("fingerprint", String(64), nullable=False, unique=True),
    Column("payload", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
)
