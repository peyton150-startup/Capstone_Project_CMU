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

The index is built once and reused: the manual is fixed reference, so its
vectors do not change between runs. **When the manual changes, the index must
be rebuilt before the next run** (developer, 2026-10-29). `ready_index` does
that by itself: each section is stored with a fingerprint of its text and
revision (`section_digest`), and before a run the index is rebuilt if it is
empty, if any fingerprint differs or a section was added or removed, or if it
was built by another embedding model. `python -m capstone.manual.index
--rebuild` still rebuilds by hand.
"""

import argparse
import hashlib
import re
from collections.abc import Callable, Sequence

from capstone.manual.sections import ManualSection, load_manual
from capstone.memory.semantic import Embedder, IndexModelMismatch, open_collection

_WORD = re.compile(r"[a-z0-9]+")
# Words too common in the manual to tell sections apart.
_COMMON = frozenset(
    "a an and are as at be by can for from in is it its not of on or the "
    "this to with when what which".split()
)


def section_digest(section: ManualSection) -> str:
    """A fingerprint of what is embedded for a section, and its revision: any
    edit to the title, the text or the revision changes it."""
    # Variables:
    #   content: Exactly what is embedded for the section, plus its revision.
    content = f"{section.revision}\n{section_document(section)}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


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
        # Variables:
        #   query: The words of the question, without common ones.
        #   scored: Matching sections as (negative score, position, section), so a sort
        #     puts the best first.
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
        # Variables:
        #   collection: The manual's own Chroma collection, kept apart from the memory
        #     index.
        #   sections: The manual's sections by number; results come from these, never
        #     from the index.
        #   embed: Turns section text into vectors.
        #   embed_query: Turns a search into a vector; falls back to embed if no
        #     separate one is given.
        self.collection = collection
        self.sections = {s.section_id: s for s in sections}
        self.embed = embed
        self.embed_query = embed_query or embed

    def build(self) -> int:
        """Index every section (again); returns how many."""
        # Variables:
        #   documents: The text embedded for each section: its title and body.
        sections = list(self.sections.values())
        documents = [section_document(s) for s in sections]
        self.collection.upsert(
            ids=[s.section_id for s in sections],
            documents=documents,
            embeddings=[list(v) for v in self.embed(documents)],
            metadatas=[
                {
                    "section_id": s.section_id,
                    "revision": s.revision,
                    "digest": section_digest(s),
                }
                for s in sections
            ],
        )
        return len(sections)

    def is_current(self) -> bool:
        """True when the index holds exactly the manual's sections as they are
        now: the same section numbers, each with today's fingerprint."""
        # Variables:
        #   stored: Each indexed section's fingerprint, by section number; an index
        #     built before fingerprints were kept has none, so it is not current.
        #   wanted: The fingerprint of each section of the manual as it is now.
        result = self.collection.get(include=["metadatas"])
        stored = {
            meta["section_id"]: meta.get("digest") for meta in result["metadatas"]
        }
        wanted = {sid: section_digest(s) for sid, s in self.sections.items()}
        return stored == wanted

    def search(self, text: str, *, limit: int) -> tuple[ManualSection, ...]:
        # Variables:
        #   result: Chroma's nearest matches, with only their section numbers asked for.
        #   found: Section numbers, closest first.
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


def ready_index(
    open_index: Callable[[bool], "ChromaManualIndex"],
) -> tuple["ChromaManualIndex", str | None]:
    """The manual's index, rebuilt first if it does not match the manual.

    `open_index(rebuild)` opens the collection, emptied first when `rebuild`.
    Returns the index and why it was rebuilt, or None when it was reused.
    """
    # Variables:
    #   open_index: Opens the index; with True it empties the collection first.
    #   index: The index as found on disk.
    #   reason: Why it had to be rebuilt, said to whoever runs the experiment.
    try:
        index = open_index(False)
    except IndexModelMismatch:
        reason = "it was built by another embedding model"
    else:
        if index.collection.count() == 0:
            reason = "it was empty"
        elif not index.is_current():
            reason = "the manual changed since it was built"
        else:
            return index, None
    index = open_index(True)
    index.build()
    return index, reason


def ready_manual_index(
    settings, *, sections: Sequence[ManualSection] | None = None
) -> tuple["ChromaManualIndex", str | None]:
    """The configured manual index, rebuilt first if the manual changed."""
    return ready_index(
        lambda rebuild: open_manual_index(settings, sections=sections, rebuild=rebuild)
    )


def open_manual_index(
    settings, *, sections: Sequence[ManualSection] | None = None, rebuild: bool = False
) -> ChromaManualIndex:
    """The manual's index at CHROMA_PATH / MANUAL_COLLECTION, by EMBEDDING_MODEL."""
    # Variables:
    #   sections: The manual's sections; the real manual is loaded if none are given.
    #   rebuild: If True, empty the collection first.
    #   embedders: The passage and query embedders, or None for the local model.
    #   passage: Embeds the sections.
    #   query: Embeds a search.
    #   collection: The Chroma collection for the manual.
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
