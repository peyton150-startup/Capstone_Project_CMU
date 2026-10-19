# Stores and retrieves accepted memories through an explicit database boundary.
# Responsibility: preserve original records and report atomic insert conflicts.
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from capstone.memory.contracts import EpisodicMemory, MemoryQuery
from capstone.memory.policy import normalize
from capstone.memory.schema import episodic_memories
from capstone.memory.semantic import memory_document

_WORD = re.compile(r"\w{3,}")


@dataclass(frozen=True)
class InsertResult:
    stored: bool
    reason: Literal["stored", "duplicate_investigation", "duplicate_lesson"]
    existing_memory_id: UUID | None = None


class SQLMemoryRepository:
    """Caller owns the engine and schema lifecycle; construction does no I/O."""

    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def insert_statement(memory: EpisodicMemory, *, dialect: str):
        builders = {"postgresql": postgres_insert, "sqlite": sqlite_insert}
        if dialect not in builders:
            raise ValueError(f"unsupported memory database dialect: {dialect}")
        return (
            builders[dialect](episodic_memories)
            .values(
                memory_id=memory.memory_id,
                investigation_id=memory.investigation_id,
                category=memory.category,
                source_tick=memory.source_tick,
                fingerprint=memory.fingerprint,
                payload=memory.model_dump(mode="json"),
            )
            .on_conflict_do_nothing()
            .returning(episodic_memories.c.memory_id)
        )

    def insert(self, memory: EpisodicMemory) -> InsertResult:
        statement = self.insert_statement(memory, dialect=self.engine.dialect.name)
        with self.engine.begin() as connection:
            inserted = connection.execute(statement).scalar_one_or_none()
            if inserted is not None:
                return InsertResult(stored=True, reason="stored")
            # The database has already settled the conflict. These reads only
            # identify the original; they do not decide whether insertion is safe.
            for column, value, reason in (
                (
                    episodic_memories.c.investigation_id,
                    memory.investigation_id,
                    "duplicate_investigation",
                ),
                (
                    episodic_memories.c.fingerprint,
                    memory.fingerprint,
                    "duplicate_lesson",
                ),
            ):
                existing = connection.execute(
                    select(episodic_memories.c.memory_id).where(column == value)
                ).scalar_one_or_none()
                if existing is not None:
                    return InsertResult(False, reason, existing)
            # Unexpected conflicts must not masquerade as successful storage.
            raise RuntimeError(
                "memory insert conflicted without an identifiable original"
            )

    def retrieve(self, query: MemoryQuery) -> tuple[EpisodicMemory, ...]:
        statement = select(episodic_memories.c.payload)
        if query.investigation_id is not None:
            statement = statement.where(
                episodic_memories.c.investigation_id == query.investigation_id
            )
        if query.category is not None:
            statement = statement.where(
                episodic_memories.c.category == normalize(query.category)
            )
        statement = statement.order_by(
            episodic_memories.c.source_tick.desc(), episodic_memories.c.memory_id
        ).limit(query.limit)
        with self.engine.connect() as connection:
            return tuple(
                EpisodicMemory.model_validate(payload)
                for payload in connection.execute(statement).scalars()
            )

    def all_memories(self) -> tuple[EpisodicMemory, ...]:
        statement = select(episodic_memories.c.payload).order_by(
            episodic_memories.c.source_tick.desc(), episodic_memories.c.memory_id
        )
        with self.engine.connect() as connection:
            return tuple(
                EpisodicMemory.model_validate(payload)
                for payload in connection.execute(statement).scalars()
            )

    def get_many(self, memory_ids: Sequence[UUID]) -> tuple[EpisodicMemory, ...]:
        """Records for the given IDs in the given order; unknown IDs are skipped."""
        if not memory_ids:
            return ()
        statement = select(episodic_memories.c.payload).where(
            episodic_memories.c.memory_id.in_(memory_ids)
        )
        with self.engine.connect() as connection:
            found = {
                memory.memory_id: memory
                for memory in (
                    EpisodicMemory.model_validate(payload)
                    for payload in connection.execute(statement).scalars()
                )
            }
        return tuple(found[i] for i in memory_ids if i in found)

    def keyword_search(self, text: str, limit: int) -> tuple[EpisodicMemory, ...]:
        """Rank by distinct query words found in each memory's document.

        Scans every stored memory in Python, which is adequate for the MVP's
        small store and identical on SQLite and PostgreSQL.
        """
        words = set(_WORD.findall(normalize(text)))
        if not words:
            return ()
        scored = []
        for memory in self.all_memories():
            document = set(_WORD.findall(normalize(memory_document(memory))))
            score = len(words & document)
            if score:
                scored.append((score, memory))
        # Stable sort keeps the newest-first order among equal scores.
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return tuple(memory for _, memory in scored[:limit])
