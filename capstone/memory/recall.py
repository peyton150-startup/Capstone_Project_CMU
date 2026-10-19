# Answers free-text memory recall with semantic, keyword, or no retrieval.
# Responsibility: pick the configured mode and fall back to keyword search.
"""Free-text recall over episodic memories.

Semantic mode asks the Chroma index for the nearest memory IDs, then hydrates
full records from the SQL repository. When the index is missing or a search
fails, recall falls back to keyword search over the same repository.
"""

import logging
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from capstone.memory.contracts import EpisodicMemory

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


class MemoryRecall:
    def __init__(
        self,
        repository: RecallStore,
        *,
        mode: RetrievalMode = "semantic",
        index: SemanticIndex | None = None,
    ):
        self.repository = repository
        self.mode = mode
        self.index = index

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
                    # Exception text could echo memory content; log the event only.
                    _log.warning("semantic recall failed; using keyword search")
                else:
                    return RecallResult(self.repository.get_many(ids), "semantic")
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
        try:
            from capstone.memory.semantic import open_chroma_index

            index = open_chroma_index(settings.chroma_path, settings.chroma_collection)
        except Exception:
            _log.warning("ChromaDB unavailable; recall will use keyword search")
    return MemoryRecall(repository, mode=settings.memory_retrieval_mode, index=index)
