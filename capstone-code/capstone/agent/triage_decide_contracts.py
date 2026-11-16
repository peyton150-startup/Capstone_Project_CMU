"""Typed read, stop and audit records for deterministic triage Decide."""

from typing import Annotated, Literal

from pydantic import Field

from capstone.agent.policy import CallTool
from capstone.contracts import Contract

TriageStopReason = Literal[
    "requirements_complete",
    "no_eligible_read",
    "capability_unavailable",
    "data_insufficient",
    "retries_exhausted",
    "max_tool_calls",
    "max_iterations",
    "timeout",
]


class TriageReadDecision(Contract):
    """One authorized read selected to address one or more requirements."""

    kind: Literal["read"] = "read"
    step: CallTool
    requirement_ids: tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)


class TriageStopDecision(Contract):
    """An explicit collection stop, preserving every unresolved requirement."""

    kind: Literal["stop"] = "stop"
    reason: TriageStopReason
    unresolved_requirement_ids: tuple[str, ...] = ()


TriageDecision = Annotated[
    TriageReadDecision | TriageStopDecision, Field(discriminator="kind")
]
