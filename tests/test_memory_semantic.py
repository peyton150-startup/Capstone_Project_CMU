import re
from uuid import UUID

import pytest

pytest.importorskip("sqlalchemy")
chromadb = pytest.importorskip("chromadb")

from sqlalchemy import create_engine

from capstone.memory.backfill import backfill
from capstone.memory.contracts import ReflectionCandidate
from capstone.memory.recall import MemoryRecall, build_memory_recall
from capstone.memory.repository import SQLMemoryRepository
from capstone.memory.schema import metadata
from capstone.memory.semantic import ChromaMemoryIndex, open_chroma_index
from capstone.memory.service import MemoryService
from capstone.settings import Settings
from tests.test_memory_policy import candidate_data

# Deterministic stand-in for an embedding model: words map to shared concepts,
# so "shaking" lands near "vibration" although the two share no keyword.
CONCEPTS = {
    "vibration": 0, "shaking": 0, "oscillation": 0,
    "temperature": 1, "heat": 1, "hot": 1,
    "bearing": 2, "spindle": 2,
    "material": 3, "batch": 3, "supplier": 3,
    "setting": 4, "configuration": 4, "speed": 4,
}  # fmt: skip


def fake_embed(texts):
    vectors = []
    for text in texts:
        vector = [0.0] * 6
        for word in re.findall(r"\w+", text.lower()):
            vector[CONCEPTS.get(word, 5)] += 1.0 if word in CONCEPTS else 0.01
        vectors.append(vector)
    return vectors


def make_candidate(n, category, symptoms, diagnosis, lesson):
    data = candidate_data()
    data["investigation"]["investigation_id"] = str(UUID(int=1000 + n))
    data["investigation"]["anomaly"]["symptoms"] = symptoms
    data["investigation"]["conclusion"]["diagnosis"] = diagnosis
    data["category"] = category
    data["lesson"]["text"] = lesson
    return ReflectionCandidate.model_validate(data)


CANDIDATES = [
    make_candidate(
        1, "bearing", ["rising vibration"], "bearing degradation",
        "Sustained vibration growth with heat points to spindle bearing wear.",
    ),
    make_candidate(
        2, "material", ["dimension rejects"], "bad material batch",
        "Rejects that follow one supplier batch across machines implicate material.",
    ),
    make_candidate(
        3, "configuration", ["surface finish drift"], "wrong spindle speed setting",
        "Compare the configured speed against the job sheet before blaming wear.",
    ),
]  # fmt: skip


@pytest.fixture
def repository(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'memories.sqlite'}")
    metadata.create_all(engine)
    yield SQLMemoryRepository(engine)
    engine.dispose()


@pytest.fixture
def index(tmp_path):
    return open_chroma_index(tmp_path / "chroma", "test_memories", embed=fake_embed)


def promote_all(service):
    return [service.promote(candidate).memory for candidate in CANDIDATES]


def test_promotion_upserts_memory_with_metadata(repository, index):
    memories = promote_all(MemoryService(repository, index=index))
    stored = index.collection.get(ids=[str(m.memory_id) for m in memories])
    assert sorted(stored["ids"]) == sorted(str(m.memory_id) for m in memories)
    by_id = dict(zip(stored["ids"], stored["metadatas"]))
    for memory in memories:
        assert by_id[str(memory.memory_id)] == {
            "memory_id": str(memory.memory_id),
            "outcome": "resolved",
            "timestamp": memory.source_tick,
        }


def test_rejected_or_duplicate_promotion_does_not_index(repository, index):
    service = MemoryService(repository, index=index)
    service.promote(CANDIDATES[0])
    assert not service.promote(CANDIDATES[0]).stored
    low = candidate_data()
    low["confidence"] = 0.1
    assert not service.promote(ReflectionCandidate.model_validate(low)).accepted
    assert index.collection.count() == 1


def test_index_failure_does_not_block_promotion(repository):
    class BrokenIndex:
        def upsert(self, memories):
            raise RuntimeError("chroma down")

    decision = MemoryService(repository, index=BrokenIndex()).promote(CANDIDATES[0])
    assert decision.stored
    assert repository.get_many((decision.memory.memory_id,)) == (decision.memory,)


def test_semantic_recall_finds_meaning_without_shared_keywords(repository, index):
    memories = promote_all(MemoryService(repository, index=index))
    recall = MemoryRecall(repository, mode="semantic", index=index)
    result = recall.recall_memories("machine shaking and running hot", k=1)
    assert result.mode_used == "semantic" and not result.fell_back
    assert result.memories == (memories[0],)
    # Keyword search has no overlap with this wording.
    assert repository.keyword_search("machine shaking and running hot", 1) == ()


def test_semantic_recall_defaults_to_top_five_from_full_collection(
    repository, tmp_path
):
    index = open_chroma_index(tmp_path / "c", "many", embed=fake_embed)
    service = MemoryService(repository, index=index)
    for n in range(7):
        service.promote(
            make_candidate(
                10 + n, f"bearing-{n}", ["vibration"], "bearing wear",
                f"Bearing lesson number {n} about vibration trend {n}.",
            )
        )  # fmt: skip
    result = MemoryRecall(repository, index=index).recall_memories("vibration")
    assert len(result.memories) == 5
    assert len({m.memory_id for m in result.memories}) == 5


def test_results_are_hydrated_from_sql_and_skip_index_only_ids(repository, index):
    memories = promote_all(MemoryService(repository, index=index))
    orphan = make_candidate(9, "bearing", ["vibration"], "bearing", "Orphan lesson.")
    orphan_memory = MemoryService(repository).policy.evaluate(orphan).memory
    index.upsert((orphan_memory,))  # in Chroma only, never stored in SQL
    result = MemoryRecall(repository, index=index).recall_memories("vibration", k=4)
    ids = {m.memory_id for m in result.memories}
    assert orphan_memory.memory_id not in ids
    assert memories[0].memory_id in ids
    assert all(m in memories for m in result.memories)


def test_falls_back_to_keyword_when_index_missing_or_failing(repository):
    memories = promote_all(MemoryService(repository))

    class FailingIndex:
        def search(self, text, k):
            raise ConnectionError("chroma unreachable")

    for index in (None, FailingIndex()):
        result = MemoryRecall(repository, index=index).recall_memories("supplier")
        assert result.mode_used == "keyword" and result.fell_back
        assert result.memories == (memories[1],)


def test_keyword_and_none_modes(repository, index):
    memories = promote_all(MemoryService(repository, index=index))
    keyword = MemoryRecall(repository, mode="keyword", index=index)
    result = keyword.recall_memories("spindle speed setting")
    assert result.mode_used == "keyword" and not result.fell_back
    assert result.memories[0] == memories[2]
    none = MemoryRecall(repository, mode="none", index=index)
    assert none.recall_memories("vibration").memories == ()


def test_backfill_indexes_existing_memories_idempotently(repository, index):
    memories = promote_all(MemoryService(repository))
    assert index.collection.count() == 0
    assert backfill(repository.all_memories(), index) == 3
    assert backfill(repository.all_memories(), index) == 3
    assert index.collection.count() == 3
    recall = MemoryRecall(repository, index=index)
    assert recall.recall_memories("supplier batch", k=1).memories == (memories[1],)


def test_index_persists_across_reopen(repository, tmp_path):
    path = tmp_path / "persist"
    service = MemoryService(
        repository, index=open_chroma_index(path, "persisted", embed=fake_embed)
    )
    memories = promote_all(service)
    reopened = open_chroma_index(path, "persisted", embed=fake_embed)
    assert isinstance(reopened, ChromaMemoryIndex)
    assert reopened.search("supplier batch", 1) == (memories[1].memory_id,)


def test_settings_retrieval_mode(monkeypatch, tmp_path, repository):
    assert Settings(_env_file=None).memory_retrieval_mode == "semantic"
    settings = Settings(
        _env_file=None,
        MEMORY_RETRIEVAL_MODE="keyword",
        CHROMA_PATH=str(tmp_path / "x"),
        CHROMA_COLLECTION="abc",
    )
    assert settings.memory_retrieval_mode == "keyword"
    assert settings.chroma_collection == "abc"
    with pytest.raises(ValueError):
        Settings(_env_file=None, MEMORY_RETRIEVAL_MODE="vector")
    recall = build_memory_recall(repository, settings)
    assert recall.mode == "keyword" and recall.index is None


def test_build_recall_falls_back_when_chroma_cannot_open(monkeypatch, repository):
    import capstone.memory.semantic as semantic

    def broken(*args, **kwargs):
        raise RuntimeError("cannot open")

    monkeypatch.setattr(semantic, "open_chroma_index", broken)
    recall = build_memory_recall(repository, Settings(_env_file=None))
    assert recall.mode == "semantic" and recall.index is None
    assert recall.recall_memories("anything").fell_back
