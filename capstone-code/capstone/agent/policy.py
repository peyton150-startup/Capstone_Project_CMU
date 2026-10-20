# The interface for the part of the agent that makes choices.
# Responsibility: define what a policy may return. The loop decides what is allowed.
"""The policy is the agent's judgement; the loop is its discipline.

A policy answers seven questions and nothing else: what do I need to know,
what should I do next, what does this observation mean, what explains the
anomaly, what should be done about it, did it work, and what advice is
worth keeping for next time. It never calls a tool itself
and never counts its own budget. A rule-based policy and a model-backed
policy both fit this one interface.

Every answer is an explicit, typed artifact. A policy returns decisions,
not its private reasoning.
"""

from typing import Literal, Protocol

from pydantic import Field

from capstone.agent.artifacts import (
    AgentConclusion,
    TerminationReason,
    VerificationCheck,
)
from capstone.agent.state import InvestigationState, Question
from capstone.contracts import Contract
from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.tools import ToolRequest

LoopPhase = Literal["investigate", "test", "verify"]


class CallTool(Contract):
    """Ask the factory one question through one tool."""

    information_needed: str = Field(min_length=1)
    request: ToolRequest
    question_id: str | None = None  # the open question this call answers
    hypothesis_id: str | None = None  # the hypothesis this call tests


class Stop(Contract):
    """End the current loop. The policy may give only these two reasons.

    Budget, timeout and "diagnosis supported" stops belong to the loop.
    """

    reason: Literal[
        TerminationReason.EVIDENCE_SUFFICIENT, TerminationReason.NO_USEFUL_ACTION
    ]
    information_needed: str = "nothing further"


Decision = CallTool | Stop


class Interpretation(Contract):
    """How one observation changes what the agent believes and still needs."""

    # The full revised set of hypotheses, or None to leave them as they are.
    hypotheses: tuple[Hypothesis, ...] | None = None
    new_questions: tuple[Question, ...] = ()


class ActionRequest(Contract):
    """A change the policy wants a human to approve, with a testable prediction."""

    machine_id: str
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    prediction: str = Field(min_length=1)


class Lesson(Contract):
    """One sentence of advice for a later investigation. Nothing else.

    It has no field for a category, an outcome or evidence: code fills
    those from the finished record, so the sentence cannot change them.
    """

    text: str = Field(min_length=1)


class ReasoningPolicy(Protocol):
    """What the loop asks of any decision-maker. Policies must not change `state`."""

    def plan(self, state: InvestigationState) -> tuple[Question, ...]:
        """The first things worth knowing about this anomaly."""
        ...

    def decide(self, state: InvestigationState, phase: LoopPhase) -> Decision:
        """The next tool call, or a reason to stop."""
        ...

    def interpret(
        self, state: InvestigationState, step: CallTool, evidence: Evidence
    ) -> Interpretation:
        """What the newest evidence means. `state` already contains it."""
        ...

    def hypothesize(self, state: InvestigationState) -> Interpretation:
        """Candidate explanations for the evidence so far, and how to test them."""
        ...

    def conclude(
        self, state: InvestigationState
    ) -> tuple[AgentConclusion, ActionRequest | None]:
        """The final belief, and an action to propose if one is justified."""
        ...

    def judge_verification(self, state: InvestigationState) -> VerificationCheck:
        """Whether the factory changed as predicted after the action."""
        ...

    def write_lesson(self, state: InvestigationState) -> Lesson | None:
        """Advice for a later investigation, or None if nothing is worth keeping."""
        ...
