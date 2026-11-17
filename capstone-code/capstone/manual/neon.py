"""Versioned, server-side Neon manual retrieval.

The SQL store owns published content. No schema creation, ingestion, or network I/O
occurs on import. Knowledge is never observable machine evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
from collections.abc import Callable, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from capstone.manual.index import section_document
from capstone.manual.sections import (
    DOCUMENT_ID,
    ManualSection,
    check_no_leaks,
    load_manual,
)
from capstone.settings import Settings, get_settings

_log = logging.getLogger(__name__)
_DIMENSIONS = 2048
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_LIST = text("""
    SELECT s.section_id, s.title, s.body, d.revision, d.document_id
    FROM capstone_knowledge.manual_documents AS d
    JOIN capstone_knowledge.manual_sections AS s
      ON s.document_id = d.document_id AND s.revision = d.revision
    WHERE d.document_id = :document_id AND d.source_scope = :scope
      AND d.is_published = TRUE
    ORDER BY s.section_id LIMIT :limit
""")
_KEYWORD = text("""
    SELECT s.section_id, s.title, s.body, d.revision, d.document_id
    FROM capstone_knowledge.manual_documents AS d
    JOIN capstone_knowledge.manual_sections AS s
      ON s.document_id = d.document_id AND s.revision = d.revision
    WHERE d.document_id = :document_id AND d.source_scope = :scope
      AND d.is_published = TRUE
      AND to_tsvector('english', s.title || ' ' || s.body)
          @@ plainto_tsquery('english', :query)
    ORDER BY ts_rank_cd(
        to_tsvector('english', s.title || ' ' || s.body),
        plainto_tsquery('english', :query)
    ) DESC, s.section_id LIMIT :limit
""")
_VECTOR = text("""
    SELECT s.section_id, s.title, s.body, d.revision, d.document_id
    FROM capstone_knowledge.manual_documents AS d
    JOIN capstone_knowledge.manual_sections AS s
      ON s.document_id = d.document_id AND s.revision = d.revision
    WHERE d.document_id = :document_id AND d.source_scope = :scope
      AND d.is_published = TRUE AND s.embedding IS NOT NULL
      AND s.embedding_model = :embedding_model
    ORDER BY s.embedding <=> CAST(:query_vector AS vector), s.section_id
    LIMIT :limit
""")


def _vector(values: Sequence[float]) -> str:
    """Validate provider vectors before SQL; no NaN, infinity, or dimension drift."""
    if len(values) != _DIMENSIONS:
        raise ValueError("manual embedding dimension does not match Neon schema")
    if any(not math.isfinite(float(v)) for v in values):
        raise ValueError("manual embedding contains non-finite values")
    return "[" + ",".join(str(float(v)) for v in values) + "]"


def _digest(sections: Sequence[ManualSection]) -> str:
    """Content-address a full revision; editing a revision requires a new name."""
    payload = [
        (s.document_id, s.revision, s.section_id, s.title, s.text) for s in sections
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class NeonManualSearch:
    """Scoped published manual with semantic search and SQL keyword degradation.

    Only the named document and scope are visible. No cross-plant or draft search.
    An unavailable database raises, rather than silently sourcing another manual.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        document_id: str = DOCUMENT_ID,
        scope: str = "simulator",
        embedding_model: str | None = None,
        embed_query: Callable[[Sequence[str]], Sequence[Sequence[float]]] | None = None,
    ):
        if not _ID.fullmatch(document_id):
            raise ValueError("invalid manual document identifier")
        if scope != "simulator":
            raise ValueError("pilot manual retrieval requires separate authorization")
        self.engine = engine
        self.document_id = document_id
        self.scope = scope
        self.embedding_model = embedding_model
        self.embed_query = embed_query

    def _rows(self, query, **params) -> tuple[ManualSection, ...]:
        try:
            with self.engine.connect() as connection:
                rows = (
                    connection.execute(
                        query,
                        {
                            "document_id": self.document_id,
                            "scope": self.scope,
                            **params,
                        },
                    )
                    .mappings()
                    .all()
                )
        except SQLAlchemyError:
            _log.warning("neon_manual_database_unavailable")
            raise RuntimeError("Approved manual database unavailable") from None
        return tuple(
            ManualSection(
                document_id=row["document_id"],
                revision=row["revision"],
                section_id=row["section_id"],
                title=row["title"],
                text=row["body"],
            )
            for row in rows
        )

    def list_sections(self, *, limit: int = 35) -> tuple[ManualSection, ...]:
        if not 1 <= limit <= 35:
            raise ValueError("manual browse limit out of bounds")
        return self._rows(_LIST, limit=limit)

    def search(self, text: str, *, limit: int) -> tuple[ManualSection, ...]:
        if not 1 <= limit <= 5:
            raise ValueError("manual search limit out of bounds")
        query = text.strip()
        if not query:
            return ()
        if len(query) > 500:
            raise ValueError("manual search query too long")
        # Embeddings are optional at runtime; a provider outage degrades to
        # in-database keyword retrieval, not to a different document/plant.
        if self.embed_query is not None and self.embedding_model is not None:
            try:
                vector = _vector(self.embed_query([query])[0])
            except Exception:
                _log.warning("neon_manual_embedding_unavailable")
            else:
                results = self._rows(
                    _VECTOR,
                    query_vector=vector,
                    embedding_model=self.embedding_model,
                    limit=limit,
                )
                if results:
                    return results
                _log.info("neon_manual_vector_index_empty_or_model_mismatch")
        return self._rows(_KEYWORD, query=query, limit=limit)

    def publish_simulator(
        self,
        sections: Sequence[ManualSection],
        *,
        embed_passage: Callable[[Sequence[str]], Sequence[Sequence[float]]] | None,
        embedding_model: str | None,
    ) -> int:
        """Explicit, atomic simulator-only seed. No OEM/pilot document ingestion."""
        sections = tuple(sections)
        if not sections or any(
            s.document_id != DOCUMENT_ID or s.revision != sections[0].revision
            for s in sections
        ):
            raise ValueError("simulator sections must share document and revision")
        if len({s.section_id for s in sections}) != len(sections):
            raise ValueError("duplicate manual section")
        check_no_leaks(sections)
        checksum = _digest(sections)
        if embed_passage is None:
            embeddings: list[str | None] = [None] * len(sections)
            embedding_model = None
        else:
            if not embedding_model:
                raise ValueError("embedding model is required for vectors")
            produced = embed_passage([section_document(s) for s in sections])
            if len(produced) != len(sections):
                raise ValueError("embedding count differs from section count")
            embeddings = [_vector(v) for v in produced]
        try:
            with self.engine.begin() as connection:
                # Serialize publication per document, including competing seed jobs.
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))"),
                    {"id": DOCUMENT_ID},
                )
                existing = (
                    connection.execute(
                        text("""
                        SELECT source_sha256, is_published
                        FROM capstone_knowledge.manual_documents
                        WHERE document_id = :id AND revision = :revision
                    """),
                        {"id": DOCUMENT_ID, "revision": sections[0].revision},
                    )
                    .mappings()
                    .first()
                )
                if existing is not None:
                    if existing["source_sha256"] != checksum:
                        raise ValueError(
                            "manual revision changed: assign a new revision first"
                        )
                    count = connection.execute(
                        text("""
                            SELECT count(*) FROM capstone_knowledge.manual_sections
                            WHERE document_id = :id AND revision = :revision
                        """),
                        {"id": DOCUMENT_ID, "revision": sections[0].revision},
                    ).scalar_one()
                    if count != len(sections):
                        raise ValueError("published manual has incomplete sections")
                    if existing["is_published"]:
                        return count  # Idempotent, never replace vectors in place.
                else:
                    connection.execute(
                        text("""
                            INSERT INTO capstone_knowledge.manual_documents
                            (document_id, revision, source_scope, title,
                             source_sha256, is_published)
                            VALUES (:id, :revision, 'simulator', :title,
                                    :digest, FALSE)
                        """),
                        {
                            "id": DOCUMENT_ID,
                            "revision": sections[0].revision,
                            "title": "Synthetic CNC simulator manual",
                            "digest": checksum,
                        },
                    )
                    for section, vector in zip(sections, embeddings, strict=True):
                        connection.execute(
                            text("""
                                INSERT INTO capstone_knowledge.manual_sections
                                (document_id, revision, section_id, title, body,
                                 embedding_model, embedding)
                                VALUES (:id, :revision, :section_id, :title, :body,
                                        :model, CAST(:vector AS vector))
                            """),
                            {
                                "id": DOCUMENT_ID,
                                "revision": section.revision,
                                "section_id": section.section_id,
                                "title": section.title,
                                "body": section.text,
                                "model": embedding_model,
                                "vector": vector,
                            },
                        )
                connection.execute(
                    text("""
                        UPDATE capstone_knowledge.manual_documents
                        SET is_published = FALSE
                        WHERE document_id = :id AND is_published = TRUE
                    """),
                    {"id": DOCUMENT_ID},
                )
                connection.execute(
                    text("""
                        UPDATE capstone_knowledge.manual_documents
                        SET is_published = TRUE
                        WHERE document_id = :id AND revision = :revision
                    """),
                    {"id": DOCUMENT_ID, "revision": sections[0].revision},
                )
        except SQLAlchemyError:
            _log.warning("neon_manual_publish_failed")
            raise RuntimeError(
                "Manual publication failed; transaction rolled back"
            ) from None
        return len(sections)


def open_neon_manual(settings: Settings | None = None) -> NeonManualSearch:
    """Explicit Neon URL, never the Supabase journal URL or implicit DATABASE_URL."""
    settings = settings or get_settings()
    if settings.neon_knowledge_database_url is None:
        raise ValueError("Set NEON_KNOWLEDGE_DATABASE_URL for Neon manuals")
    try:
        url = make_url(settings.neon_knowledge_database_url.get_secret_value())
        if url.drivername in ("postgres", "postgresql"):
            url = url.set(drivername="postgresql+psycopg")
        if url.drivername != "postgresql+psycopg" or url.query.get("sslmode") not in (
            "require",
            "verify-ca",
            "verify-full",
        ):
            raise ValueError("Neon manuals require PostgreSQL with TLS")
    except (ValueError, TypeError):
        raise ValueError(
            "Invalid Neon knowledge URL (PostgreSQL TLS required)"
        ) from None

    # The hosted provider is optional: keyword SQL still works without an API key.
    from capstone.providers.embeddings import embedders_for

    embed_query = None
    model = None
    if settings.nvidia_api_key is not None and settings.embedding_model != "local":
        _, embed_query = embedders_for(settings)
        model = settings.embedding_model
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=0,
        pool_timeout=5,
        connect_args={"connect_timeout": 5},
    )
    return NeonManualSearch(
        engine,
        embedding_model=model,
        embed_query=embed_query,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly seed synthetic manual in Neon; no OEM uploads."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--keyword-only", action="store_true")
    args = parser.parse_args()
    sections = load_manual()
    print(
        f"manual={DOCUMENT_ID} revision={sections[0].revision} "
        f"sections={len(sections)} digest={_digest(sections)}"
    )
    if not args.apply:
        print("preview only; Neon unchanged (pass --apply to publish)")
        return 0

    settings = get_settings()
    passage = None
    model = None
    if not args.keyword_only:
        from capstone.providers.embeddings import embedders_for

        embedders = embedders_for(settings)
        if embedders is None:
            parser.error("NVIDIA embedding model required, or pass --keyword-only")
        passage = embedders[0]
        model = settings.embedding_model
    store = open_neon_manual(settings)
    try:
        written = store.publish_simulator(
            sections, embed_passage=passage, embedding_model=model
        )
        print(
            f"published {written} sections of {DOCUMENT_ID} revision {sections[0].revision}"
        )
    finally:
        store.engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
