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
