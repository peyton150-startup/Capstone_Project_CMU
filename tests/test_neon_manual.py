"""Offline Neon knowledge tests. Never contact a hosted Neon project."""

from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
from sqlalchemy.exc import SQLAlchemyError

from capstone.api.config import UiConfig
from capstone.manual.neon import NeonManualSearch, _digest, _vector, open_neon_manual
from capstone.manual.sections import DOCUMENT_ID, load_manual
from capstone.settings import Settings

SECTIONS = load_manual()


class Result:
    def __init__(self, rows=(), count=0):
        self.rows = rows
        self.count = count

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def scalar_one(self):
        return self.count


class Engine:
    """Captures parameters and query contracts rather than running SQL."""

    def __init__(self, *, vector_rows=(), keyword_rows=(), fail=False):
        self.vector_rows = vector_rows
        self.keyword_rows = keyword_rows
        self.fail = fail
        self.calls = []

    def connect(self):
        return self

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters):
        sql = str(statement)
        self.calls.append((sql, parameters))
        if self.fail:
            raise SQLAlchemyError("postgresql://user:private-password@host/db")
        if "ORDER BY s.embedding" in sql:
            return Result(self.vector_rows)
        if "plainto_tsquery" in sql:
            return Result(self.keyword_rows)
        return Result()


def row(section=SECTIONS[0]):
    return {
        "document_id": section.document_id,
        "revision": section.revision,
        "section_id": section.section_id,
        "title": section.title,
        "body": section.text,
    }


def test_neon_keyword_only_returns_published_scoped_manual_sections():
    engine = Engine(keyword_rows=[row()])
    found = NeonManualSearch(engine).search("spindle vibration", limit=3)
    assert len(found) == 1 and found[0] == SECTIONS[0]
    sql, parameters = engine.calls[0]
    assert "d.is_published = TRUE" in sql
    assert "d.source_scope = :scope" in sql
    assert parameters == {
        "document_id": DOCUMENT_ID,
        "scope": "simulator",
        "query": "spindle vibration",
        "limit": 3,
    }
    assert "spindle vibration" not in sql  # Never interpolate query text into SQL.


def test_neon_semantic_uses_matching_model_and_valid_2048_vector():
    engine = Engine(vector_rows=[row(SECTIONS[1])])
    search = NeonManualSearch(
        engine,
        embedding_model="nvidia/test",
        embed_query=lambda texts: [[0.01] * 2048],
    )
    assert search.search("unusual heat", limit=2)[0] == SECTIONS[1]
    assert len(engine.calls) == 1
    sql, params = engine.calls[0]
    assert "s.embedding_model = :embedding_model" in sql
    assert "d.is_published = TRUE" in sql
    assert params["embedding_model"] == "nvidia/test"
    assert params["query_vector"].startswith("[0.01,0.01")
    assert params["scope"] == "simulator"


def test_embedding_timeout_or_missing_vectors_degrades_within_same_document():
    engine = Engine(keyword_rows=[row()])

    def offline(_texts):
        raise TimeoutError("NVIDIA unavailable")

    search = NeonManualSearch(
        engine,
        embedding_model="nvidia/test",
        embed_query=offline,
    )
    assert search.search("vibration", limit=3)[0] == SECTIONS[0]
    assert len(engine.calls) == 1
    assert "plainto_tsquery" in engine.calls[0][0]
    empty = Engine(keyword_rows=[row()])
    search = NeonManualSearch(
        empty,
        embedding_model="nvidia/test",
        embed_query=lambda _texts: [[0.0] * 2048],
    )
    assert search.search("vibration", limit=3)[0] == SECTIONS[0]
    assert len(empty.calls) == 2  # No matching model vector -> keyword.


def test_db_outage_fails_closed_without_leaking_connection_strings():
    store = NeonManualSearch(Engine(fail=True))
    with pytest.raises(RuntimeError) as error:
        store.search("heat", limit=2)
    assert "private-password" not in str(error.value)
    assert "postgresql://" not in str(error.value)


@pytest.mark.parametrize("invalid", [[0.1] * 2047, [float("nan")] * 2048])
def test_embedding_integrity_refuses_bad_vectors(invalid):
    with pytest.raises(ValueError):
        _vector(invalid)


def test_no_pilot_or_other_document_scope_can_be_retrieved():
    with pytest.raises(ValueError, match="pilot"):
        NeonManualSearch(Engine(), document_id="OEM-MANUAL", scope="pilot")
    with pytest.raises(ValueError, match="identifier"):
        NeonManualSearch(Engine(), document_id="../file")


def test_search_bounds_and_browse_limit_are_checked_before_database():
    engine = Engine()
    store = NeonManualSearch(engine)
    with pytest.raises(ValueError):
        store.search("a" * 501, limit=3)
    with pytest.raises(ValueError):
        store.search("x", limit=40)
    with pytest.raises(ValueError):
        store.list_sections(limit=40)
    assert not engine.calls


def test_publication_rejects_revision_mismatch_before_network():
    engine = Engine()
    store = NeonManualSearch(engine)
    sections = list(SECTIONS)
    sections[0] = sections[0].model_copy(update={"revision": "different"})
    with pytest.raises(ValueError, match="revision"):
        store.publish_simulator(sections, embed_passage=None, embedding_model=None)
    with pytest.raises(ValueError, match="dimension"):
        store.publish_simulator(
            SECTIONS,
            embed_passage=lambda texts: [[1.0] * 5 for _ in texts],
            embedding_model="nvidia/test",
        )
    assert engine.calls == []
    assert len(_digest(SECTIONS)) == 64


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///tmp/memory.sqlite",
        "postgresql://user:secret@host/db?sslmode=disable",
        "postgresql://user:secret@host/db",
    ],
)
def test_neon_url_requires_tls_and_does_not_leak_secret(url):
    settings = Settings(_env_file=None, NEON_KNOWLEDGE_DATABASE_URL=url)
    with pytest.raises(ValueError) as error:
        open_neon_manual(settings)
    assert "secret" not in str(error.value)


def test_no_implicit_fallback_to_database_url():
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://user:secret@host/db?sslmode=require",
    )
    with pytest.raises(ValueError, match="NEON_KNOWLEDGE_DATABASE_URL"):
        open_neon_manual(settings)


def test_ui_neon_optin_requires_private_token():
    with pytest.raises(ValueError, match="CAPSTONE_UI_TOKEN"):
        UiConfig(neon_manual_enabled=True)
    cfg = UiConfig(neon_manual_enabled=True, token="z" * 32)
    assert cfg.neon_manual_enabled
    assert not UiConfig().neon_manual_enabled


def test_isolated_sql_migration_has_no_browser_or_data_api_grants():
    sql = (
        Path(__file__).resolve().parents[1]
        / "migrations/neon/0001_manual_knowledge.sql"
    ).read_text()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "embedding vector(2048)" in sql
    assert "manual_one_published_revision" in sql
    assert "REVOKE ALL ON ALL TABLES" in sql
    assert "source_scope IN ('simulator', 'pilot')" in sql
