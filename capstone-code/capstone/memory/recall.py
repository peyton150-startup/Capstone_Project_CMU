# Finds the memories that match a description, and shows them safely.
# Responsibility: word-overlap search, optional semantic recall on top of it,
# and the view a later investigation may see.
"""Recall by shared words, with optional semantic recall layered on top.

Keyword recall: a memory matches when the query shares words with its category, symptoms,
action, machine or lesson. More shared words rank first; equal scores put
the most recent first, then the memory ID, so a query always returns the
same list. Words differently spelled ("shaking" for "vibration") do not
match: that is the known limit of this search.

Semantic recall (`MemoryRecall`, mode "semantic") asks the Chroma index for
the nearest memory IDs, then loads the full records from the SQL repository.
When the index is missing or a search fails, it falls back to the keyword
search above, unless `fallback=False`: then it raises `SemanticRecallFailed`
instead, so a measurement of semantic recall never measures keyword search.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from capstone.memory.contracts import EpisodicMemory, RecalledMemory
from capstone.memory.policy import normalize

# Words that would match nearly every memory, including the fixed failure sentence.
FILLER = frozenset(
    "a an and are as at be by for from in is it of on or the to was were with".split()
)


def words(text: str) -> set[str]:
    """The searchable words of a text. Tool names split: replace_bearing -> two."""
    return set(normalize(text).replace("_", " ").split()) - FILLER


def recalled(memory: EpisodicMemory) -> RecalledMemory:
    """The view of one memory that is safe to hand to another investigation."""
    action = memory.intervention
    return RecalledMemory(
        memory_id=memory.memory_id,
        category=memory.category,
        symptoms=memory.symptoms,
        diagnosis=memory.diagnosis,
        action=action.action if action else None,
        machine_id=action.machine_id if action else None,
        outcome=memory.outcome,
        lesson=memory.lesson,
        source_tick=memory.source_tick,
    )


def rank_memories(
    memories: Iterable[EpisodicMemory], text: str, *, limit: int = 5
) -> tuple[EpisodicMemory, ...]:
    """The best matches for `text`, as full records. Nothing matches no shared word."""
    if limit < 1:
        raise ValueError("limit must be at least one")
    wanted = words(text)
    scored = []
    for memory in memories:
        view = recalled(memory)
        searchable = " ".join(
            (
                view.category,
                *view.symptoms,
                view.action or "",
                view.machine_id or "",
                view.lesson,
            )
        )
        score = len(wanted & words(searchable))
        if score:
            scored.append((-score, -view.source_tick, str(view.memory_id), memory))
    scored.sort(key=lambda entry: entry[:3])
    return tuple(memory for *_, memory in scored[:limit])


def search_memories(
    memories: Iterable[EpisodicMemory], text: str, *, limit: int = 5
) -> tuple[RecalledMemory, ...]:
    """The best matches for `text`, as safe views. Nothing matches no shared word."""
    return tuple(recalled(m) for m in rank_memories(memories, text, limit=limit))


RetrievalMode = Literal["semantic", "keyword", "none"]
DEFAULT_TOP_K = 5

_log = logging.getLogger(__name__)


class RecallStore(Protocol):
    def get_many(self, memory_ids: tuple[UUID, ...]) -> tuple[EpisodicMemory, ...]: ...

    def keyword_search(self, text: str, limit: int) -> tuple[EpisodicMemory, ...]: ...


class SemanticIndex(Protocol):
    def search(self, text: str, k: int) -> tuple[UUID, ...]: ...


@dataclass(frozen=True)
class RecallResult:
    memories: tuple[EpisodicMemory, ...]
    mode_used: RetrievalMode
    fell_back: bool = False


class SemanticRecallFailed(RuntimeError):
    """Semantic recall could not answer, and keyword fallback is switched off."""


class MemoryRecall:
    def __init__(
        self,
        repository: RecallStore,
        *,
        mode: RetrievalMode = "semantic",
        index: SemanticIndex | None = None,
        fallback: bool = True,
    ):
        self.repository = repository
        self.mode = mode
        self.index = index
        # False: a semantic search that cannot run raises SemanticRecallFailed
        # rather than quietly answering by keyword (the memory comparison).
        self.fallback = fallback

    def recall_memories(self, query: str, k: int = DEFAULT_TOP_K) -> RecallResult:
        if k < 1:
            raise ValueError("k must be at least 1")
        if self.mode == "none":
            return RecallResult((), "none")
        if self.mode == "semantic":
            if self.index is not None:
                try:
                    ids = self.index.search(query, k)
                except Exception:
                    # Exception text could echo memory content; never chain it.
                    if not self.fallback:
                        raise SemanticRecallFailed("semantic search failed") from None
                    _log.warning("semantic recall failed; using keyword search")
                else:
                    return RecallResult(self.repository.get_many(ids), "semantic")
            if not self.fallback:
                raise SemanticRecallFailed("no semantic index")
            return RecallResult(
                self.repository.keyword_search(query, k), "keyword", fell_back=True
            )
        return RecallResult(self.repository.keyword_search(query, k), "keyword")


def build_memory_recall(repository: RecallStore, settings=None) -> MemoryRecall:
    """Build recall from settings; an unopenable Chroma index means fallback."""
    if settings is None:
        from capstone.settings import get_settings

        settings = get_settings()
    index = None
    if settings.memory_retrieval_mode == "semantic":
        from capstone.memory import semantic

        try:
            index = semantic.open_configured_index(settings)
        except semantic.IndexModelMismatch as error:
            # Says which model built the index and how to rebuild; no memory text.
            _log.warning("%s; recall will use keyword search", error)
        except Exception:
            _log.warning("ChromaDB unavailable; recall will use keyword search")
    return MemoryRecall(repository, mode=settings.memory_retrieval_mode, index=index)
