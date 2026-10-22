# Searching the machine manual: by meaning (Chroma) or by words (no services).
# Responsibility: return the manual sections that best match a query.
"""Two ways to search the manual, with the same `search(text, limit)`.

    python -m capstone.manual.index --rebuild    # build the semantic index once

`ChromaManualIndex` searches by meaning, with the configured embedding model
(EMBEDDING_MODEL), in its own Chroma collection (MANUAL_COLLECTION, default
"cnc_machine_manual_v1") beside the memory index but never inside it: a
manual section is fixed reference, a memory is a past run's belief, and one
search over both would let a wrong old lesson pass as manual text. The index
stores only each section's number and text; sections are returned from the
manual itself, so a stale index cannot invent a section.

`KeywordManualSearch` ranks sections by shared words. It needs no service,
so tests use it, and so does a run whose Chroma index has not been built.

The manual is written once and indexed once, not on every investigation.
Rebuild after editing the manual or changing the embedding model.
"""

import argparse
import re
from collections.abc import Sequence

from capstone.manual.sections import ManualSection, load_manual
from capstone.memory.semantic import Embedder, open_collection

_WORD = re.compile(r"[a-z0-9]+")
# Words too common in the manual to tell sections apart.
_COMMON = frozenset(
    "a an and are as at be by can for from in is it its not of on or the "
    "this to with when what which".split()
)


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _COMMON}


def section_document(section: ManualSection) -> str:
    """The text that represents a section for embedding."""
    return f"{section.title}. {section.text}"


class KeywordManualSearch:
    """Sections ranked by words shared with the query; a title word counts double."""

    def __init__(self, sections: Sequence[ManualSection]):
        self.sections = tuple(sections)

    def search(self, text: str, *, limit: int) -> tuple[ManualSection, ...]:
        query = _words(text)
        scored = []
        for order, section in enumerate(self.sections):
            score = 2 * len(query & _words(section.title)) + len(
                query & _words(section.text)
            )
            if score:
                scored.append((-score, order, section))
        return tuple(section for _, _, section in sorted(scored)[:limit])


class ChromaManualIndex:
    """The manual's own Chroma collection, searched by meaning."""

    def __init__(
        self,
        collection,
        sections: Sequence[ManualSection],
        embed: Embedder,
        embed_query: Embedder | None = None,
    ):
        self.collection = collection
        self.sections = {s.section_id: s for s in sections}
        self.embed = embed
        self.embed_query = embed_query or embed

    def build(self) -> int:
        """Index every section (again); returns how many."""
        sections = list(self.sections.values())
        documents = [section_document(s) for s in sections]
        self.collection.upsert(
            ids=[s.section_id for s in sections],
            documents=documents,
            embeddings=[list(v) for v in self.embed(documents)],
            metadatas=[
                {"section_id": s.section_id, "revision": s.revision} for s in sections
            ],
        )
        return len(sections)

    def search(self, text: str, *, limit: int) -> tuple[ManualSection, ...]:
        if self.collection.count() == 0:
            return ()
        result = self.collection.query(
            query_embeddings=[list(self.embed_query([text])[0])],
            n_results=min(limit, self.collection.count()),
            include=["metadatas"],
        )
        found = (meta["section_id"] for meta in result["metadatas"][0])
        # Only sections the manual has now: an old index cannot add one.
        return tuple(self.sections[i] for i in found if i in self.sections)


REBUILD_HINT = "python -m capstone.manual.index --rebuild"


def open_manual_index(
    settings, *, sections: Sequence[ManualSection] | None = None, rebuild: bool = False
) -> ChromaManualIndex:
    """The manual's index at CHROMA_PATH / MANUAL_COLLECTION, by EMBEDDING_MODEL."""
    from capstone.memory.semantic import default_embedder
    from capstone.providers.embeddings import embedders_for

    embedders = embedders_for(settings)
    passage, query = embedders if embedders is not None else (None, None)
    collection = open_collection(
        settings.chroma_path,
        settings.manual_collection,
        model=settings.embedding_model,
        rebuild=rebuild,
        rebuild_hint=REBUILD_HINT,
    )
    return ChromaManualIndex(
        collection,
        sections if sections is not None else load_manual(),
        passage or default_embedder(),
        query,
    )


def main(argv: Sequence[str] | None = None) -> int:
    from capstone.console import safe_console
    from capstone.settings import get_settings

    safe_console()
    parser = argparse.ArgumentParser(prog="python -m capstone.manual.index")
    parser.add_argument(
        "--rebuild", action="store_true", help="delete the collection and index again"
    )
    options = parser.parse_args(argv)
    settings = get_settings()
    index = open_manual_index(settings, rebuild=options.rebuild)
    print(
        f"indexed {index.build()} sections into '{settings.manual_collection}' "
        f"with {settings.embedding_model}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
