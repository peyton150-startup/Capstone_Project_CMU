# The live investigation's own records: anomaly, conclusion, proposal, check.
# Responsibility: hold what the loop needs while running. Not the shared hand-off.
"""Runtime records that exist only while one investigation is running.

These carry more detail than the finished report needs: which machine,
whether a proposal is still pending, what the agent predicted. The loop
reads them to decide its next step, so they may change as the loop does.

The shared hand-off is `capstone.contracts.completed_investigations`.
Nothing outside `capstone.agent` should import this module; the facts
held here reach other code as evidence and plain text in that hand-off.

Everything here is belief and observation. No field holds simulator truth.
"""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from capstone.contracts import Contract


class TerminationReason(StrEnum):
    """Why the research loop stopped. Exactly one applies to an investigation."""

    MAX_ITERATIONS = "max_iterations"
    MAX_TOOL_CALLS = "max_tool_calls"
    TIMEOUT = "timeout"
    EVIDENCE_SUFFICIENT = "evidence_sufficient"
    DIAGNOSIS_SUPPORTED = "diagnosis_supported"
    NO_USEFUL_ACTION = "no_useful_action"
    # No model service answered, even after the retry and the fallback. Not
    # a reasoning failure: the agent never got the chance to reason.
    MODEL_UNAVAILABLE = "model_unavailable"


class DetectedAnomaly(Contract):
    """What was noticed that started the investigation. An observation, not a cause."""

    tick: int = Field(ge=0)
    machine_id: str | None = None  # None for something about the whole factory
    kind: str = Field(min_length=1)
    description: str = Field(min_length=1)


class AgentConclusion(Contract):
    """The agent's final belief and what it recommends doing about it."""

    diagnosis: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    recommendation: Literal["intervene", "no_action", "escalate"]
    hypothesis_id: str | None = None
    evidence_ids: tuple[str, ...] = ()


class ProposalRecord(Contract):
    """A change the agent asked a human to approve, and what the human decided."""

    proposal_id: int | None = Field(default=None, ge=1)
    machine_id: str
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    status: Literal["pending", "approved", "rejected", "not_submitted"]


class VerificationCheck(Contract):
    """Whether the factory changed the way the agent predicted after the action."""

    outcome: Literal["resolved", "not_resolved", "inconclusive", "not_performed"]
    prediction: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    checked_tick: int | None = Field(default=None, ge=0)


class Objection(Contract):
    """One thing a critic found wrong with a hypothesis the agent holds."""

    kind: Literal[
        "contradiction",
        "unsupported_claim",
        "missing_evidence",
        "alternative",
        "overconfidence",
    ] = Field(
        description=(
            "contradiction: the evidence cited says the opposite of the claim. "
            "unsupported_claim: the claim says something no evidence shown backs. "
            "missing_evidence: a check the claim needs was never made. "
            "alternative: the evidence fits another explanation as well or better. "
            "overconfidence: the confidence is higher than the evidence allows."
        )
    )
    text: str = Field(
        min_length=1, description="One sentence saying what is wrong, in plain words."
    )
    evidence_ids: tuple[str, ...] = Field(
        default=(),
        description="The ids of the evidence shown that this objection rests on.",
    )


class CritiqueResult(Contract):
    """A second model's judgement of the two leading hypotheses. A belief, not evidence."""

    favoured: str = Field(
        description=(
            "The id of the shown hypothesis the evidence supports better than the "
            "other, not one proven beyond doubt. Use none only if the evidence "
            "supports neither."
        )
    )
    why: str = Field(
        description="One or two sentences: the evidence that makes it the better fit."
    )
    discriminating_check: str = Field(
        description=(
            "One call the agent could make with a tool from the list shown, with its "
            "arguments, whose answer would tell the two hypotheses apart."
        )
    )
    objections: tuple[Objection, ...] = Field(
        default=(),
        description="Problems found with the favoured hypothesis or the other one.",
    )
    verdict: Literal["object", "no_objection"] = Field(
        description=(
            "object if the agent should doubt its leading hypothesis; "
            "no_objection if the evidence supports it and nothing above undermines it."
        )
    )
    favoured_confidence: float = Field(
        ge=0,
        le=1,
        description="How sure you are the favoured hypothesis is right, from 0 to 1.",
    )
    supports_action: bool = Field(
        description=(
            "True only if the evidence justifies acting on the favoured hypothesis "
            "now, without more checking."
        )
    )


class CritiqueRecord(Contract):
    """What the critic stage produced for one investigation, or why it produced nothing."""

    outcome: Literal["answered", "invalid_reply", "no_answer"]
    result: CritiqueResult | None = None
    shown_hypotheses: tuple[str, ...]
    seconds: float = Field(ge=0)
    # The model that gave the reply (also one that was refused), so results can
    # be split by model. None: no model answered, or an older record.
    answered_by: str | None = None
