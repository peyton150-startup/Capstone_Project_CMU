# The working memory of one live investigation.
# Responsibility: hold explicit state, budgets, decision records, and loop metrics.
"""What the agent knows and has done so far in a single investigation.

This is working memory: it lives for one investigation and is then turned
into a `CompletedInvestigation`. Nothing here is stored between runs.

It holds decisions, not thoughts. Every step leaves a `DecisionRecord`
saying what was needed, which tool was chosen and what came back.
"""

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from capstone.agent.artifacts import (
    AgentConclusion,
    DetectedAnomaly,
    ProposalRecord,
    TerminationReason,
    VerificationCheck,
)
from capstone.contracts import Contract
from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.provenance import ProvenanceReference
from capstone.contracts.tools import ToolError

Phase = Literal[
    "observe",
    "plan",
    "investigate",
    "hypothesize",
    "test",
    "decide",
    "propose",
    "execute",
    "verify",
]

StepOutcome = Literal[
    "observed",  # the tool answered and the answer became evidence
    "tool_error",  # the tool refused or failed
    "malformed_result",  # the answer could not be used
    "uninterpreted",  # a good answer the policy failed to make sense of
    "repeated_call",  # skipped: the same question at the same tick
    "invalid_decision",  # the policy did not return a usable decision
    "decided",  # the policy answered a stage without a tool call
    "stopped",  # no tool was called; the loop ended here
]


class Budgets(Contract):
    """Hard limits on one investigation. The loop enforces them, not the policy."""

    max_iterations: int = Field(default=24, ge=1)
    max_tool_calls: int = Field(default=20, ge=1)
    timeout_seconds: float = Field(default=60.0, gt=0)
    # A separate allowance for proposing an action and checking that it worked,
    # so that research can never spend the calls verification needs.
    followup_tool_calls: int = Field(default=14, ge=0)
    # The same for time: research stops this many seconds before the deadline,
    # leaving them for the conclusion, the proposal, the work and the check.
    followup_seconds: float = Field(default=20.0, ge=0)
    max_unproductive_steps: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def research_gets_some_time(self):
        if self.followup_seconds >= self.timeout_seconds:
            raise ValueError("followup_seconds must leave some time for research")
        return self


class Question(Contract):
    """One piece of information the agent still needs."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    hypothesis_id: str | None = None


class DecisionRecord(Contract):
    """What the agent chose at one step and what happened. Not chain-of-thought."""

    sequence: int = Field(ge=1)
    phase: Phase
    tick: int | None = Field(default=None, ge=0)
    information_needed: str
    question_id: str | None = None
    hypothesis_id: str | None = None  # the hypothesis this step was testing
    tool: str | None = None
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    outcome: StepOutcome
    evidence_ids: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)
    termination_reason: TerminationReason | None = None
    # For a failed call: the tool's own account of what was wrong.
    error: ToolError | None = None


class ReasoningMetrics(Contract):
    """Counts that describe how the loop behaved in one investigation."""

    iterations: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    repeated_calls: int = Field(ge=0)
    failed_tool_calls: int = Field(ge=0)
    malformed_results: int = Field(ge=0)
    interpretation_failures: int = Field(ge=0)
    hypothesis_revisions: int = Field(ge=0)
    termination_reason: TerminationReason | None


class InvestigationState(BaseModel):
    """Everything the live loop reads and updates. Mutable; one per investigation."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    run_id: UUID
    investigation_id: UUID
    anomaly: DetectedAnomaly
    budgets: Budgets = Field(default_factory=Budgets)

    evidence: list[Evidence] = Field(default_factory=list)
    # One label per evidence item, written by the loop when it arrived.
    provenance: list[ProvenanceReference] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    unanswered_questions: list[Question] = Field(default_factory=list)
    # Question id to the evidence that answered it, newest last.
    answers: dict[str, list[str]] = Field(default_factory=dict)
    decisions: list[DecisionRecord] = Field(default_factory=list)

    iteration_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    followup_tool_calls_used: int = Field(default=0, ge=0)
    repeated_calls: int = Field(default=0, ge=0)
    failed_tool_calls: int = Field(default=0, ge=0)
    malformed_results: int = Field(default=0, ge=0)
    interpretation_failures: int = Field(default=0, ge=0)
    hypothesis_revisions: int = Field(default=0, ge=0)
    # Steps in a row that moved nothing forward: errors, bad results, repeats,
    # and answers the policy could not interpret.
    unproductive_steps: int = Field(default=0, ge=0)

    # The latest simulation tick any tool result reported.
    last_tick: int | None = Field(default=None, ge=0)
    started_at: float | None = None  # seconds on the injected monotonic clock
    # Calls already made, as "tool|arguments|tick", to spot repeats.
    seen_calls: list[str] = Field(default_factory=list)

    # The stage now running, so a stop that cuts it short is recorded there.
    stage: Phase | None = None
    termination_reason: TerminationReason | None = None
    conclusion: AgentConclusion | None = None
    proposed_action: ProposalRecord | None = None
    # The tick at which the conclusion was reached.
    concluded_tick: int | None = Field(default=None, ge=0)
    # What should change in the factory if the diagnosis is right.
    predicted_effect: str | None = None
    # Set only when the factory confirmed that the approved work started.
    action_started_tick: int | None = Field(default=None, ge=0)
    action_finish_tick: int | None = Field(default=None, ge=0)
    verification: VerificationCheck | None = None

    @property
    def confidence(self) -> float:
        """How sure the agent is of its best explanation so far."""
        return max((h.confidence for h in self.hypotheses), default=0.0)

    @property
    def leading_hypothesis(self) -> Hypothesis | None:
        """The most confident hypothesis; the first one wins a tie."""
        if not self.hypotheses:
            return None
        return max(self.hypotheses, key=lambda h: h.confidence)

    @property
    def action_carried_out(self) -> bool:
        """True only if the factory said the work started. Approval is not enough."""
        return self.action_started_tick is not None

    @property
    def research_tool_calls(self) -> int:
        return self.tool_call_count - self.followup_tool_calls_used

    @property
    def remaining_iterations(self) -> int:
        return max(0, self.budgets.max_iterations - self.iteration_count)

    @property
    def remaining_tool_calls(self) -> int:
        return max(0, self.budgets.max_tool_calls - self.research_tool_calls)

    @property
    def remaining_followup_tool_calls(self) -> int:
        return max(0, self.budgets.followup_tool_calls - self.followup_tool_calls_used)

    def remaining_seconds(self, now: float) -> float:
        """Time left on the whole-investigation deadline, never below zero."""
        if self.started_at is None:
            return self.budgets.timeout_seconds
        return max(0.0, self.budgets.timeout_seconds - (now - self.started_at))

    def evidence_for(self, question_id: str) -> Evidence | None:
        """The newest evidence that answered a question, if any."""
        ids = self.answers.get(question_id)
        if not ids:
            return None
        return next(e for e in reversed(self.evidence) if e.id == ids[-1])

    def data_for(self, question_id: str) -> JsonValue | None:
        """The tool data behind the newest answer to a question."""
        evidence = self.evidence_for(question_id)
        return None if evidence is None else json.loads(evidence.content)

    def metrics(self) -> ReasoningMetrics:
        return ReasoningMetrics(
            iterations=self.iteration_count,
            tool_calls=self.tool_call_count,
            repeated_calls=self.repeated_calls,
            failed_tool_calls=self.failed_tool_calls,
            malformed_results=self.malformed_results,
            interpretation_failures=self.interpretation_failures,
            hypothesis_revisions=self.hypothesis_revisions,
            termination_reason=self.termination_reason,
        )
