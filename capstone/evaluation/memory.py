# Records memory promotion and attributed assessments of later memory use.
# Responsibility: report explicit outcomes without feeding evaluator truth to memory.
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from capstone.contracts import Contract
from capstone.contracts.completed_investigations import CompletedInvestigation
from capstone.memory.contracts import EpisodicMemory, PromotionDecision

Effect = Literal["helped", "hurt", "neutral", "unknown"]
AssessmentSource = Literal["agent_report", "human_review", "evaluator"]


class MemoryPromotionRecord(Contract):
    """Evaluator-side report; correctness never grants promotion eligibility."""

    run_id: UUID
    investigation_id: UUID
    accepted: bool
    stored: bool
    reasons: tuple[str, ...] = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    memory_id: UUID | None = None
    existing_memory_id: UUID | None = None
    diagnosis_correct: bool | None = None

    @model_validator(mode="after")
    def consistent_storage(self):
        if self.accepted != (self.memory_id is not None):
            raise ValueError("only accepted decisions identify a proposed new memory")
        if self.stored and (not self.accepted or self.existing_memory_id is not None):
            raise ValueError("stored records must identify an accepted new memory")
        return self


class MemoryUseRecord(Contract):
    """An attributed assessment, not proof that memory caused the outcome."""

    consumer_run_id: UUID
    consumer_investigation_id: UUID
    memory_id: UUID
    retrieved: bool = True
    used: bool | None = None
    effect: Effect = "unknown"
    assessment_source: AssessmentSource | None = None
    evidence_ids: tuple[str, ...] = ()
    explanation: str | None = None

    @model_validator(mode="after")
    def supported_assessment(self):
        if self.used is True and not self.retrieved:
            raise ValueError("a used memory must have been retrieved")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("assessment evidence references must be unique")
        if self.effect != "unknown" and (
            self.used is not True
            or self.assessment_source is None
            or not self.evidence_ids
            or not self.explanation
            or not self.explanation.strip()
        ):
            raise ValueError(
                "a known effect needs an attributed, supported use assessment"
            )
        return self


def build_promotion_record(
    investigation: CompletedInvestigation,
    decision: PromotionDecision,
    *,
    diagnosis_correct: bool | None = None,
) -> MemoryPromotionRecord:
    """Associate a decision with its completed report without changing either."""
    if decision.investigation_id != investigation.investigation_id:
        raise ValueError("promotion and investigation identities must match")
    memory = decision.memory
    if memory is not None:
        if memory.run_id != investigation.run_id:
            raise ValueError(
                "promotion memory and investigation run identities must match"
            )
        if memory.policy_version != decision.policy_version:
            raise ValueError("promotion memory and decision policy versions must match")
    return MemoryPromotionRecord(
        run_id=investigation.run_id,
        investigation_id=investigation.investigation_id,
        accepted=decision.accepted,
        stored=decision.stored,
        reasons=decision.reasons,
        policy_version=decision.policy_version,
        memory_id=memory.memory_id if memory is not None else None,
        existing_memory_id=decision.existing_memory_id,
        diagnosis_correct=diagnosis_correct,
    )


def build_use_record(
    investigation: CompletedInvestigation,
    memory: EpisodicMemory,
    *,
    retrieved: bool = True,
    used: bool | None = None,
    effect: Effect = "unknown",
    assessment_source: AssessmentSource | None = None,
    evidence_ids: tuple[str, ...] = (),
    explanation: str | None = None,
) -> MemoryUseRecord:
    """Record supplied use observations; never infer benefit from run success."""
    if not set(evidence_ids) <= {e.id for e in investigation.evidence}:
        raise ValueError(
            "assessment references evidence absent from the consumer report"
        )
    return MemoryUseRecord(
        consumer_run_id=investigation.run_id,
        consumer_investigation_id=investigation.investigation_id,
        memory_id=memory.memory_id,
        retrieved=retrieved,
        used=used,
        effect=effect,
        assessment_source=assessment_source,
        evidence_ids=evidence_ids,
        explanation=explanation,
    )
