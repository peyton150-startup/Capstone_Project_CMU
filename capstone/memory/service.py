# Connects promotion checks to durable storage and bounded retrieval.
# Responsibility: write only qualifying lessons and return explicit outcomes.
from typing import Protocol
from uuid import UUID

from capstone.memory.contracts import (
    EpisodicMemory,
    MemoryQuery,
    PromotionDecision,
    ReflectionCandidate,
)
from capstone.memory.policy import MemoryPromotionPolicy


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


class MemoryService:
    def __init__(
        self, repository: MemoryStore, *, policy: MemoryPromotionPolicy | None = None
    ):
        self.repository = repository
        self.policy = policy if policy is not None else MemoryPromotionPolicy()

    def promote(self, candidate: ReflectionCandidate) -> PromotionDecision:
        decision = self.policy.evaluate(candidate)
        if not decision.accepted:
            return decision
        result = self.repository.insert(decision.memory)
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
