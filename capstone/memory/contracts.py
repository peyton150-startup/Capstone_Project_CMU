# Defines reflection candidates, accepted memories, and retrieval requests.
# Responsibility: retain explicit evidence lineage and reusable lessons.
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from capstone.contracts import Contract
from capstone.contracts.completed_investigations import (
    ActionProposal,
    CompletedInvestigation,
    VerificationResult,
)

# Defined once in the shared contracts; importable from here as before.
from capstone.contracts.provenance import ProvenanceReference  # noqa: F401


class ReusableLesson(Contract):
    text: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    reusable: bool = False
    contains_transient_details: bool = True


class ReflectionCandidate(Contract):
    """Explicit reflection, with correctness assessed only from observations."""

    investigation: CompletedInvestigation
    category: str = Field(min_length=1, max_length=128)
    useful_evidence_ids: tuple[str, ...] = ()
    misleading_evidence_ids: tuple[str, ...] = ()
    unnecessary_tool_calls: tuple[str, ...] = ()
    diagnosis_assessment: Literal["supported", "refuted", "unknown"] = "unknown"
    intervention_worked: bool | None = None
    lesson: ReusableLesson
    confidence: float = Field(ge=0, le=1)
    provenance: tuple[ProvenanceReference, ...] = ()


class EpisodicMemory(Contract):
    """Validated durable lesson. Raw evidence content is intentionally excluded."""

    memory_id: UUID
    run_id: UUID
    investigation_id: UUID
    category: str = Field(min_length=1, max_length=128)
    symptoms: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    diagnosis: str = Field(min_length=1)
    intervention: ActionProposal | None
    outcome: Literal["resolved"]
    verification: VerificationResult
    lesson: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    provenance: tuple[ProvenanceReference, ...]
    source_tick: int = Field(ge=0)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: str = Field(min_length=1)


class PromotionDecision(Contract):
    investigation_id: UUID
    accepted: bool
    reasons: tuple[str, ...] = Field(min_length=1)
    policy_version: str
    memory: EpisodicMemory | None = None
    stored: bool = False
    existing_memory_id: UUID | None = None

    @model_validator(mode="after")
    def consistent_decision(self):
        if self.accepted != (self.memory is not None):
            raise ValueError("only accepted decisions contain a memory")
        if self.stored and not self.accepted:
            raise ValueError("a rejected decision cannot store a memory")
        if self.memory and self.memory.investigation_id != self.investigation_id:
            raise ValueError("decision and memory must name the same investigation")
        return self


class MemoryQuery(Contract):
    """Filtered retrieval boundary; future retrievers can implement this contract."""

    investigation_id: UUID | None = None
    category: str | None = Field(default=None, min_length=1, max_length=128)
    limit: int = Field(default=20, ge=1, le=100)
