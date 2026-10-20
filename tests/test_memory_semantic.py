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


# --- the agent's recall_memories tool goes through MemoryService.search ---


def test_service_search_uses_semantic_recall_and_returns_safe_views(repository, index):
    from capstone.memory.contracts import RecalledMemory
    from capstone.memory.recall import recalled
    from capstone.memory.service import MemoryService

    service = MemoryService(
        repository,
        index=index,
        recall=MemoryRecall(repository, mode="semantic", index=index),
    )
    memories = promote_all(service)
    found = service.search("machine shaking and running hot", limit=1)
    assert found == (recalled(memories[0]),)
    assert all(type(view) is RecalledMemory for view in found)
    # Without recall the service keeps its word search, which finds nothing here.
    assert MemoryService(repository).search("machine shaking and running hot") == ()


def test_service_search_falls_back_when_chroma_fails(repository):
    from capstone.memory.recall import recalled
    from capstone.memory.service import MemoryService

    class FailingIndex:
        def upsert(self, memories):
            return 0

        def search(self, text, k):
            raise ConnectionError("chroma unreachable")

    failing = FailingIndex()
    service = MemoryService(
        repository,
        index=failing,
        recall=MemoryRecall(repository, mode="semantic", index=failing),
    )
    memories = promote_all(service)
    assert service.search("supplier") == (recalled(memories[1]),)


def test_none_mode_turns_the_recall_tool_off(repository):
    from capstone.memory.service import MemoryService

    service = MemoryService(repository, recall=MemoryRecall(repository, mode="none"))
    promote_all(service)
    assert service.search("bearing") == ()


def test_build_memory_service_shares_one_index_for_writing_and_recall(
    monkeypatch, repository, tmp_path
):
    import capstone.memory.semantic as semantic
    from capstone.memory.recall import recalled
    from capstone.memory.service import build_memory_service

    monkeypatch.setattr(
        semantic,
        "open_configured_index",
        lambda settings: semantic.open_chroma_index(
            settings.chroma_path, settings.chroma_collection, embed=fake_embed
        ),
    )
    settings = Settings(_env_file=None, CHROMA_PATH=str(tmp_path / "shared"))
    service = build_memory_service(repository, settings)
    assert service.index is service.recall.index is not None
    memories = promote_all(service)
    assert service.search("machine shaking and running hot", limit=1) == (
        recalled(memories[0]),
    )


def test_recall_tool_answers_from_semantic_recall(repository, index):
    from capstone.contracts.tools import ToolRequest
    from capstone.memory.service import MemoryService
    from capstone.providers.recall import RecallingProvider
    from tests.helpers import FakeProvider

    service = MemoryService(
        repository,
        index=index,
        recall=MemoryRecall(repository, mode="semantic", index=index),
    )
    memories = promote_all(service)
    provider = RecallingProvider(FakeProvider(lambda r: {"tick": 10}), service)
    result = provider.call(
        ToolRequest(name="recall_memories", arguments={"text": "shaking", "limit": 1})
    )
    assert result.success and result.source == "memory"
    assert [row["memory_id"] for row in result.data] == [str(memories[0].memory_id)]
    assert "fingerprint" not in str(result.data)


# --- the index remembers which embedding model built it -----------------------


def test_a_new_index_records_its_model_and_refuses_another(tmp_path):
    from capstone.memory.semantic import IndexModelMismatch

    path = tmp_path / "chroma"
    open_chroma_index(path, "mixed", embed=fake_embed, model="nvidia/a")
    assert open_chroma_index(path, "mixed", embed=fake_embed, model="nvidia/a")
    with pytest.raises(IndexModelMismatch, match="built by nvidia/a, not nvidia/b"):
        open_chroma_index(path, "mixed", embed=fake_embed, model="nvidia/b")


def test_an_index_from_before_the_record_counts_as_the_local_model(tmp_path):
    from capstone.memory.semantic import IndexModelMismatch

    path = tmp_path / "chroma"
    client = chromadb.PersistentClient(path=str(path))
    client.create_collection("old", embedding_function=None)  # no model recorded
    assert open_chroma_index(path, "old", embed=fake_embed)  # "local"
    with pytest.raises(IndexModelMismatch, match="--rebuild"):
        open_chroma_index(path, "old", embed=fake_embed, model="nvidia/a")


def test_rebuild_empties_the_index_and_takes_the_new_model(tmp_path, repository):
    path = tmp_path / "chroma"
    old = open_chroma_index(path, "swap", embed=fake_embed)
    memories = promote_all(MemoryService(repository, index=old))
    assert old.collection.count() == len(memories)
    new = open_chroma_index(
        path, "swap", embed=fake_embed, model="nvidia/a", rebuild=True
    )
    assert new.collection.count() == 0
    backfill(tuple(memories), new)
    assert new.search("supplier batch", 1) == (memories[1].memory_id,)


def test_memories_and_searches_are_embedded_in_their_own_roles(tmp_path, repository):
    seen = []

    def role(name):
        def embed(texts):
            seen.append((name, len(texts)))
            return fake_embed(texts)

        return embed

    index = open_chroma_index(
        tmp_path / "chroma", "roles", embed=role("passage"), embed_query=role("query")
    )
    promote_all(MemoryService(repository, index=index))  # one upsert per memory
    index.search("vibration", 1)
    assert seen == [("passage", 1)] * len(CANDIDATES) + [("query", 1)]


def test_recall_uses_keyword_search_when_the_index_has_another_model(
    tmp_path, repository, caplog
):
    path = tmp_path / "chroma"
    open_chroma_index(path, "episodic_memories", embed=fake_embed)  # local
    settings = Settings(
        _env_file=None,
        CHROMA_PATH=str(path),
        EMBEDDING_MODEL="nvidia/nvidia/nemotron-3-embed-1b",
        NVIDIA_API_KEY="test-key",
    )
    recall = build_memory_recall(repository, settings)
    assert recall.mode == "semantic" and recall.index is None
    assert recall.recall_memories("anything").fell_back
    assert "--rebuild" in caplog.text and "test-key" not in caplog.text
