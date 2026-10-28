# Defines the additive handoff from investigation runtime to post-run consumers.
# Responsibility: validate completed artifacts without controlling live reasoning.
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from capstone.contracts import Contract
from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis


class Anomaly(Contract):
    summary: str = Field(min_length=1)
    symptoms: tuple[str, ...] = ()


class Conclusion(Contract):
    diagnosis: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: tuple[str, ...] = ()


class ActionProposal(Contract):
    """A recommendation, not evidence that the intervention was executed."""

    action: str = Field(min_length=1)
    machine_id: str | None = None
    reason: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()


class VerificationResult(Contract):
    """An observation-based outcome, never an evaluator's hidden answer key."""

    status: Literal["verified", "failed", "unverified"]
    outcome: Literal["resolved", "unresolved", "unknown"]
    summary: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    observed_tick: int = Field(ge=0)


class CompletedInvestigation(Contract):
    """Shared handoff v1. Additive; changes need both workstreams' agreement."""

    run_id: UUID
    investigation_id: UUID
    anomaly: Anomaly
    evidence: tuple[Evidence, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    conclusion: Conclusion
    proposed_action: ActionProposal | None = None
    verification: VerificationResult | None = None
    iterations_used: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    # Owned by runtime: consumers do not prescribe allowed termination choices.
    termination_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_evidence(self):
        # Variables:
        #   ids: The id of every piece of evidence, which must all be different.
        ids = [e.id for e in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique within an investigation")
        return self
