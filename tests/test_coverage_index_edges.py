"""Offline edge-path coverage for semantic indexes and memory utilities.

These tests use synthetic records and fake collections; no model, SQL service,
network endpoint, or factory is accessed.
"""

import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from capstone.manual import index as manual
from capstone.memory import backfill as backfill_module
from capstone.memory import duplicate_threshold as threshold


@pytest.mark.parametrize(
    "size, batches",
    [(0, []), (1, [1]), (100, [100]), (101, [100, 1]), (205, [100, 100, 5])],
)
def test_backfill_batches_are_bounded_and_preserve_every_record(size, batches):
    """A derived search index receives each row exactly once in bounded batches."""
    written = []
    index = SimpleNamespace(upsert=lambda rows: written.append(tuple(rows)))
    assert backfill_module.backfill(tuple(range(size)), index) == size
    assert [len(batch) for batch in written] == batches
    assert [item for batch in written for item in batch] == list(range(size))


def test_memory_backfill_cli_requires_a_database_url(monkeypatch):
    from capstone import settings

    monkeypatch.setattr(
        settings,
        "get_settings",
        lambda: SimpleNamespace(database_url=None),
    )
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        backfill_module.main([])


@pytest.mark.parametrize(
    "url, driver, rebuild",
    [
        ("postgresql://user:pass@localhost/mem", "postgresql+psycopg", True),
        ("sqlite:///local.db", "sqlite", False),
    ],
)
def test_memory_backfill_cli_reads_only_disposes_and_rebuilds(
    monkeypatch, capsys, url, driver, rebuild
):
    """Database access ends before the derived Chroma index is touched."""
    import sqlalchemy
    from capstone import settings
    from capstone.memory import repository, semantic

    events = []
    engine = SimpleNamespace(dispose=lambda: events.append("dispose"))
    monkeypatch.setattr(
        sqlalchemy,
        "create_engine",
        lambda parsed: (events.append(("engine", parsed.drivername)), engine)[1],
    )

    class Stored:
        def __init__(self, source):
            assert source is engine

        def all_memories(self):
            events.append("read")
            return tuple(range(101))

    class Index:
        def upsert(self, rows):
            events.append(("upsert", len(rows)))

    def index_factory(_settings, *, rebuild):
        events.append(("index", rebuild))
        return Index()

    monkeypatch.setattr(repository, "SQLMemoryRepository", Stored)
    monkeypatch.setattr(semantic, "open_configured_index", index_factory)
    monkeypatch.setattr(
        settings,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=SecretStr(url),
            chroma_collection="test",
            embedding_model="offline",
        ),
    )
    backfill_module.main(["--rebuild"] if rebuild else [])
    assert events == [
        ("engine", driver),
        "read",
        "dispose",
        ("index", rebuild),
        ("upsert", 100),
        ("upsert", 1),
    ]
    assert "Indexed 101 memories" in capsys.readouterr().out


def test_memory_backfill_disposes_engine_after_read_failure(monkeypatch):
    import sqlalchemy
    from capstone import settings
    from capstone.memory import repository

    disposed = []
    engine = SimpleNamespace(dispose=lambda: disposed.append(True))
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda _url: engine)

    class BrokenRepository:
        def __init__(self, _engine):
            pass

        def all_memories(self):
            raise RuntimeError("read failed")

    monkeypatch.setattr(repository, "SQLMemoryRepository", BrokenRepository)
    monkeypatch.setattr(
        settings,
        "get_settings",
        lambda: SimpleNamespace(database_url=SecretStr("sqlite:///fake.db")),
    )
    with pytest.raises(RuntimeError, match="read failed"):
        backfill_module.main([])
    assert disposed == [True]


def test_duplicate_similarity_rejects_mismatched_vectors_and_handles_no_negatives():
    with pytest.raises(ValueError):
        threshold.cosine([1.0, 2.0], [1.0])
    assert threshold.choose_threshold([(-0.5, "same"), (0.8, "unsure")]) is None
    assert threshold.evaluate([(0.8, "same"), (0.4, "different")], 0.5) == {
        "same_pairs": 1,
        "same_caught": 1,
        "different_pairs": 1,
        "different_refused": 0,
    }


def test_duplicate_measure_refuses_to_invent_a_threshold_without_different_pairs():
    row = {
        "id": "x",
        "category": "alarm",
        "outcome": "resolved",
        "label": "same",
        "held_out": False,
        "a": {"diagnosis": "bearing", "lesson": "check current"},
        "b": {"diagnosis": "bearing", "lesson": "check current"},
    }
    result = threshold.measure([row], lambda texts: [[1, 0]] * len(texts))
    assert result["threshold"] is None
    assert result["train"] is None and result["held_out"] is None
    assert result["pairs"][0]["score"] == 1.0


@pytest.mark.parametrize("use_provider", [False, True])
def test_duplicate_measure_cli_chooses_offline_or_provider_embedder(
    monkeypatch, tmp_path, capsys, use_provider
):
    from capstone import settings
    from capstone.memory import semantic
    from capstone.providers import embeddings

    calls = []
    embed = lambda texts: [[1.0, 0.0] for _ in texts]
    monkeypatch.setattr(
        settings,
        "get_settings",
        lambda: SimpleNamespace(embedding_model="test-embedder"),
    )
    monkeypatch.setattr(
        semantic,
        "default_embedder",
        lambda: (calls.append("local"), embed)[1],
    )
    monkeypatch.setattr(
        embeddings,
        "embedders_for",
        lambda _settings: (embed, embed) if use_provider else None,
    )
    pair = {
        "id": "one",
        "label": "different",
        "category": "sensor",
        "outcome": "resolved",
        "held_out": False,
        "a": {"diagnosis": "fault a", "lesson": "a"},
        "b": {"diagnosis": "fault b", "lesson": "b"},
    }
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text(json.dumps(pair) + "\n", encoding="utf-8")
    target = tmp_path / "scores.json"
    threshold.main(["--pairs", str(pairs), "--out", str(target)])
    result = json.loads(target.read_text())
    assert result["model"] == "test-embedder"
    assert result["train"]["different_pairs"] == 1
    assert ("local" in calls) is (not use_provider)
    assert json.loads(capsys.readouterr().out)["model"] == "test-embedder"


def test_manual_semantic_index_filters_removed_sections_and_empty_collections():
    section = SimpleNamespace(
        section_id="1", title="Spindle", text="Bearing", revision="1"
    )
    requested = []

    class Collection:
        size = 0

        def count(self):
            return self.size

        def query(self, **kwargs):
            requested.append(kwargs)
            return {"metadatas": [[{"section_id": "old"}, {"section_id": "1"}]]}

    collection = Collection()
    index = manual.ChromaManualIndex(
        collection, [section], lambda texts: [[1.0, 2.0] for _ in texts]
    )
    assert index.search("bearing", limit=5) == ()
    collection.size = 1
    assert index.search("bearing", limit=5) == (section,)
    assert requested[0]["n_results"] == 1


def test_manual_semantic_index_builds_revision_fingerprints():
    section = SimpleNamespace(
        section_id="1", title="Spindle", text="Bearing", revision="1"
    )
    stored = []

    class Collection:
        def upsert(self, **kwargs):
            stored.append(kwargs)

        def get(self, *, include):
            return {"metadatas": stored[0]["metadatas"]}

    index = manual.ChromaManualIndex(
        Collection(), [section], lambda texts: [[0.1] for _ in texts]
    )
    assert index.build() == 1
    assert index.is_current()
    section.text = "Changed"
    assert not index.is_current()
    assert stored[0]["ids"] == ["1"]


@pytest.mark.parametrize("provided", [False, True])
def test_manual_open_index_supports_local_and_separate_query_embeddings(
    monkeypatch, provided
):
    from capstone.memory import semantic
    from capstone.providers import embeddings

    local_calls = []
    local_embed = lambda texts: [[1.0] for _ in texts]
    passage = lambda texts: [[2.0] for _ in texts]
    query = lambda texts: [[3.0] for _ in texts]
    monkeypatch.setattr(
        semantic,
        "default_embedder",
        lambda: (local_calls.append(True), local_embed)[1],
    )
    monkeypatch.setattr(
        embeddings,
        "embedders_for",
        lambda _settings: (passage, query) if provided else None,
    )
    seen = []
    monkeypatch.setattr(
        manual,
        "open_collection",
        lambda *args, **kwargs: (seen.append((args, kwargs)), object())[1],
    )
    section = SimpleNamespace(
        section_id="1", title="Spindle", text="Bearing", revision="1"
    )
    settings = SimpleNamespace(
        chroma_path="/tmp/unused",
        manual_collection="manual_test",
        embedding_model="synthetic",
    )
    opened = manual.open_manual_index(settings, sections=[section], rebuild=True)
    assert opened.embed is (passage if provided else local_embed)
    assert opened.embed_query is (query if provided else local_embed)
    assert seen[0][1]["rebuild"] is True
    assert bool(local_calls) is (not provided)


def test_manual_cli_passes_rebuild_and_prints_indexed_count(monkeypatch, capsys):
    from capstone import console, settings

    config = SimpleNamespace(manual_collection="manual_test", embedding_model="offline")
    monkeypatch.setattr(settings, "get_settings", lambda: config)
    monkeypatch.setattr(console, "safe_console", lambda: None)
    calls = []
    monkeypatch.setattr(
        manual,
        "open_manual_index",
        lambda _settings, *, rebuild: (
            calls.append(rebuild),
            SimpleNamespace(build=lambda: 3),
        )[1],
    )
    assert manual.main(["--rebuild"]) == 0
    assert calls == [True]
    assert "indexed 3 sections" in capsys.readouterr().out
