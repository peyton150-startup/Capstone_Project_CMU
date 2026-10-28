# Connects promotion checks to durable storage and bounded retrieval.
# Responsibility: write only qualifying lessons and return explicit outcomes.
import logging
from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from capstone.memory.contracts import (
    EpisodicMemory,
    MemoryQuery,
    PromotionDecision,
    RecalledMemory,
    ReflectionCandidate,
)
from capstone.memory.policy import MemoryPromotionPolicy
from capstone.memory.recall import (
    MemoryRecall,
    build_memory_recall,
    recalled,
    search_memories,
)

_log = logging.getLogger(__name__)


class StorageResult(Protocol):
    @property
    def stored(self) -> bool: ...

    @property
    def reason(self) -> str: ...

    @property
    def existing_memory_id(self) -> UUID | None: ...


class MemoryStore(Protocol):
    """Structural boundary; importing this service needs no SQLAlchemy."""

    def insert(self, memory: EpisodicMemory) -> StorageResult: ...

    def retrieve(self, query: MemoryQuery) -> tuple[EpisodicMemory, ...]: ...


class MemoryIndex(Protocol):
    def upsert(self, memories: Iterable[EpisodicMemory]) -> int: ...


class MemoryService:
    def __init__(
        self,
        repository: MemoryStore,
        *,
        policy: MemoryPromotionPolicy | None = None,
        index: MemoryIndex | None = None,
        recall: MemoryRecall | None = None,
    ):
        # Variables:
        #   repository: The SQL store, which is the authoritative copy of every memory.
        #   policy: The checks a lesson must pass before it is kept.
        #   index: The similarity index written to on promotion; None if there is none.
        #   recall: How free-text searches are answered (semantic, keyword or none).
        self.repository = repository
        self.policy = policy if policy is not None else MemoryPromotionPolicy()
        self.index = index
        # Free-text recall by the configured mode (semantic / keyword / none).
        # None: the shared-word search below, as before.
        self.recall = recall

    def promote(self, candidate: ReflectionCandidate) -> PromotionDecision:
        # Variables:
        #   decision: The policy's verdict, before anything is stored.
        #   result: What the store reported: stored, or the kind of duplicate it found.
        decision = self.policy.evaluate(candidate)
        if not decision.accepted:
            return decision
        result = self.repository.insert(decision.memory)
        if result.stored and self.index is not None:
            # The SQL row is already committed and authoritative. A failed index
            # write only delays semantic recall until the backfill is rerun.
            try:
                self.index.upsert((decision.memory,))
            except Exception:
                _log.warning("semantic index upsert failed; run the memory backfill")
        return PromotionDecision(
            investigation_id=decision.investigation_id,
            accepted=result.stored,
            reasons=decision.reasons if result.stored else (result.reason,),
            policy_version=decision.policy_version,
            memory=decision.memory if result.stored else None,
            stored=result.stored,
            existing_memory_id=result.existing_memory_id,
        )

    def retrieve(self, query: MemoryQuery) -> tuple[EpisodicMemory, ...]:
        return self.repository.retrieve(query)

    def search(self, text: str, *, limit: int = 5) -> tuple[RecalledMemory, ...]:
        """The best matches for `text`, always as the safe view.

        With `recall`, its mode decides: semantic (Chroma's nearest memories,
        read back from SQL, falling back to keyword search), keyword, or none.
        Without it, word search over the most recent memories the store
        returns (at most 100).
        """
        # Variables:
        #   found: Full memory records the recall mode matched to the text.
        #   candidates: The most recent stored memories, used when no recall mode is
        #     set.
        if self.recall is not None:
            found = self.recall.recall_memories(text, k=limit).memories
            return tuple(recalled(memory) for memory in found)
        candidates = self.repository.retrieve(MemoryQuery(limit=100))
        return search_memories(candidates, text, limit=limit)


def build_memory_service(repository, settings=None, **options) -> MemoryService:
    """A service set up from MEMORY_RETRIEVAL_MODE and the Chroma settings.

    One index serves both sides: new memories are written to it on promotion
    and recall searches it. Chroma that cannot be opened leaves no index, so
    promotion writes SQL only and recall falls back to keyword search.
    """
    recall = build_memory_recall(repository, settings)
    return MemoryService(repository, index=recall.index, recall=recall, **options)
