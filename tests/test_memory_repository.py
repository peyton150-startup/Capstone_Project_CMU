from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from capstone.memory.contracts import MemoryQuery, ReflectionCandidate
from capstone.memory.policy import MemoryPromotionPolicy
from capstone.memory.repository import SQLMemoryRepository
from capstone.memory.schema import episodic_memories, metadata
from capstone.memory.service import MemoryService
from tests.test_memory_policy import candidate_data


@pytest.fixture
def repository(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'memories.sqlite'}")
    metadata.create_all(engine)
    yield SQLMemoryRepository(engine)
    engine.dispose()


def candidate(**changes):
    data = candidate_data()
    data.update(changes)
    return ReflectionCandidate.model_validate(data)


def test_promote_store_retrieve_and_reopen(repository):
    service = MemoryService(repository)
    decision = service.promote(candidate())
    assert decision.accepted and decision.stored
    url = repository.engine.url
    repository.engine.dispose()
    fresh_engine = create_engine(url)
    try:
        reopened = SQLMemoryRepository(fresh_engine)
        memories = reopened.retrieve(MemoryQuery(investigation_id=UUID(int=2)))
        assert memories == (decision.memory,)
        assert memories[0].provenance == decision.memory.provenance
        assert reopened.retrieve(MemoryQuery(category="bearing")) == memories
        assert reopened.retrieve(MemoryQuery(category="material")) == ()
    finally:
        fresh_engine.dispose()


def test_same_investigation_cannot_store_duplicate(repository):
    service = MemoryService(repository)
    first = service.promote(candidate())
    data = candidate_data()
    data["lesson"]["text"] = "A different supported lesson from the same incident"
    second = service.promote(ReflectionCandidate.model_validate(data))
    assert not second.stored and not second.accepted
    assert second.reasons == ("duplicate_investigation",)
    assert second.existing_memory_id == first.memory.memory_id
    assert len(service.retrieve(MemoryQuery())) == 1


def test_similar_lesson_across_investigations_is_deduplicated(repository):
    service = MemoryService(repository)
    first = service.promote(candidate())
    data = candidate_data()
    data["investigation"]["investigation_id"] = str(UUID(int=3))
    data["lesson"]["text"] = (
        "  COMPARE sustained vibration trends and repair findings before attributing recovery to a bearing replacement!!!  "
    )
    second = service.promote(ReflectionCandidate.model_validate(data))
    assert second.reasons == ("duplicate_lesson",)
    assert second.existing_memory_id == first.memory.memory_id
    assert not second.stored
    assert (
        service.retrieve(MemoryQuery(investigation_id=UUID(int=2)))[0].provenance
        == first.memory.provenance
    )


def test_rejected_candidate_never_persisted(repository):
    decision = MemoryService(repository).promote(candidate(confidence=0.5))
    assert not decision.stored
    assert repository.retrieve(MemoryQuery()) == ()


def test_distinct_lessons_categories_and_retrieval_limit(repository):
    service = MemoryService(repository)
    service.promote(candidate())
    data = candidate_data()
    data["category"] = "material"
    data["investigation"]["investigation_id"] = str(UUID(int=3))
    assert service.promote(ReflectionCandidate.model_validate(data)).stored
    assert len(service.retrieve(MemoryQuery(limit=1))) == 1
    assert len(service.retrieve(MemoryQuery(category=" MATERIAL "))) == 1
    assert (
        service.retrieve(MemoryQuery(investigation_id=UUID(int=3), category="bearing"))
        == ()
    )


def test_database_rejects_duplicate_even_bypassing_service(repository):
    memory = MemoryService(repository).promote(candidate()).memory
    with repository.engine.connect() as connection:
        row = dict(connection.execute(select(episodic_memories)).mappings().one())
    row["memory_id"] = UUID(int=99)
    with pytest.raises(IntegrityError), repository.engine.begin() as connection:
        connection.execute(insert(episodic_memories).values(**row))
    assert repository.retrieve(MemoryQuery()) == (memory,)


def test_insert_conflict_is_atomic_and_does_not_overwrite(repository):
    memory = MemoryPromotionPolicy().evaluate(candidate()).memory
    first = repository.insert(memory)
    second = SQLMemoryRepository(repository.engine).insert(memory)
    assert first.stored
    assert not second.stored
    assert second.reason == "duplicate_investigation"
    assert second.existing_memory_id == memory.memory_id


def test_postgresql_insert_uses_conflict_handling_and_returning(repository):
    memory = MemoryPromotionPolicy().evaluate(candidate()).memory
    statement = repository.insert_statement(memory, dialect="postgresql")
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT DO NOTHING" in sql
    assert "RETURNING episodic_memories.memory_id" in sql


def test_unsupported_dialect_is_explicit(repository):
    memory = MemoryPromotionPolicy().evaluate(candidate()).memory
    with pytest.raises(ValueError, match="dialect"):
        repository.insert_statement(memory, dialect="mysql")


def test_competing_connections_store_one_lesson_and_preserve_winner(repository):
    data = candidate_data()
    data["investigation"]["investigation_id"] = str(UUID(int=3))
    policy = MemoryPromotionPolicy()
    memories = (
        policy.evaluate(candidate()).memory,
        policy.evaluate(ReflectionCandidate.model_validate(data)).memory,
    )
    barrier = Barrier(2)

    def store(memory):
        engine = create_engine(repository.engine.url)
        try:
            barrier.wait(timeout=10)
            return SQLMemoryRepository(engine).insert(memory)
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(store, memories))
    winner = next(memory for memory, result in zip(memories, results) if result.stored)
    loser = next(result for result in results if not result.stored)
    assert sum(result.stored for result in results) == 1
    assert loser.reason == "duplicate_lesson"
    assert loser.existing_memory_id == winner.memory_id
    assert repository.retrieve(MemoryQuery()) == (winner,)
