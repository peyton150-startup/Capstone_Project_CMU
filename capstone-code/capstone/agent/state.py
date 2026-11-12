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
    CritiqueRecord,
    DetectedAnomaly,
    ProposalRecord,
    RecheckRecord,
    ReinstatementRecord,
    RevaluationRecord,
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
    # Set from the benchmark of 2026-10-20 (docs/benchmarks/2026-10-20.md):
    # the default model asked 33.5 questions an episode at a median of 14 s,
    # which suggests 948 s, and two of its four episodes ran out at 900 s, one
    # while checking a fix that had worked. 1,200 s leaves that room.
    timeout_seconds: float = Field(default=1200.0, gt=0)
    # A separate allowance for proposing an action and checking that it worked,
    # so that research can never spend the calls verification needs.
    followup_tool_calls: int = Field(default=14, ge=0)
    # At most one separate diagnostic read when critic follow-up is enabled.
    critic_tool_calls: int = Field(default=1, ge=0, le=1)
    # The same for time: research stops this many seconds before the deadline,
    # leaving them for the conclusion, the proposal, the work and the check.
    followup_seconds: float = Field(default=400.0, ge=0)
    max_unproductive_steps: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def research_gets_some_time(self):
        if self.followup_seconds >= self.timeout_seconds:
            raise ValueError("followup_seconds must leave some time for research")
        return self


# Rapid triage (MVP_SCOPE.md, "Split rapid triage from deep investigation"):
# a short, read-only first look. These limits are starting points, not a
# measured response-time target: that has to come from live provider latency.
TRIAGE_SECONDS = 90.0
# Of those, the seconds research leaves for the conclusion.
TRIAGE_CONCLUDE_SECONDS = 20.0
TRIAGE_TOOL_CALLS = 6
TRIAGE_ITERATIONS = 8

# Which kind of investigation this is. "deep" is the full workflow and the
# default; "triage" never proposes, executes or verifies anything.
Mode = Literal["deep", "triage"]


def triage_budgets(
    seconds: float = TRIAGE_SECONDS, tool_calls: int = TRIAGE_TOOL_CALLS
) -> Budgets:
    """The limits for a rapid triage: short, with nothing kept for a fix.

    No follow-up calls (triage proposes nothing, so there is nothing to
    verify) and no critic reading. Research stops `TRIAGE_CONCLUDE_SECONDS`
    before the deadline, or a quarter of it when the deadline is shorter, so
    the conclusion always has time.
    """
    # Variables:
    #   seconds: The whole triage's wall-clock deadline.
    #   tool_calls: The most factory calls research may make.
    #   kept: The seconds research leaves for the conclusion.
    kept = min(TRIAGE_CONCLUDE_SECONDS, seconds / 4)
    return Budgets(
        max_iterations=TRIAGE_ITERATIONS,
        max_tool_calls=tool_calls,
        timeout_seconds=seconds,
        followup_tool_calls=0,
        critic_tool_calls=0,
        followup_seconds=kept,
    )


class PrunedCandidate(Contract):
    """An explanation tree-of-thought considered and dropped, kept in the trace.

    Not a hypothesis: nothing tests it, and the agent's beliefs do not include
    it. Kept so the critic can see what was ruled out, and why, and say if a
    dropped cause deserves another look.
    """

    id: str = Field(min_length=1)  # the candidate id (C1, C2, ...)
    claim: str = Field(min_length=1)
    reason: str = Field(min_length=1)  # why `prune` dropped it
    # contradicted: factory evidence was cited against it. deferred: dropped
    # for another reason (ranked out, never rated): untested, not shown false.
    status: Literal["contradicted", "deferred"] = "deferred"
    # The model's rating, if it gave one (an unrated candidate has none).
    verdict: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()


class IncidentContext(Contract):
    """Observed line context and references to its original tool answers."""

    trigger_tick: int = Field(ge=0)
    as_of_tick: int | None = Field(default=None, ge=0)
    from_tick: int = Field(ge=0)
    machine_ids: tuple[str, ...] = ()
    neighbor_ids: tuple[str, ...] = ()
    evidence_by_tool: dict[str, str] = Field(default_factory=dict)
    summary_evidence: dict[str, str] = Field(default_factory=dict)
    unavailable: tuple[str, ...] = ()


class Question(Contract):
    """One piece of information the agent still needs."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    hypothesis_id: str | None = None
    distinguishes_hypothesis_ids: tuple[str, ...] = ()
    signal_reliability: Literal["direct", "indirect", "unknown"] = "unknown"
    estimated_calls: int = Field(default=1, ge=1, le=3)


GapKind = Literal[
    "model_question",
    "unanswered_question",
    "no_observable_evidence",
    "selected_has_conflict",
    "unverified_number",
]
# How an open question bears on the chosen explanation: it tells the chosen
# one from a rival, it only checks the chosen one, it names no explanation,
# or (for the model's own wording) it matches no question the agent tracked.
GapRole = Literal["rival_test", "selected_check", "side", "unlinked"]


class GapRecord(Contract):
    """One reason the final check found the diagnosis not yet settled."""

    kind: GapKind
    text: str
    # For questions only: the tracked question it is (or matches) and how it
    # bears on the chosen explanation. None for the other kinds.
    question_id: str | None = None
    role: GapRole | None = None


class ConclusionTrace(Contract):
    """What the final check saw and did, kept so other gap rules can be replayed.

    Record only: nothing reads it to decide anything.
    """

    # The model's own completion claim and recommendation, before the check
    # could change them.
    model_assessment: Literal["supported", "unresolved"] | None
    model_recommendation: str
    # The model's own confidence, before an unresolved answer was capped
    # (UNRESOLVED_MAX_CONFIDENCE). None in traces saved before it was kept.
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # The fix the model asked for, as "action machine", and why the action
    # rules alone (confidence, evidence, a named action) would refuse it,
    # whatever the gaps. None when no fix was asked for or nothing refuses it.
    wanted_action: str | None = None
    action_blocked: str | None = None
    selected_hypothesis_id: str | None = None
    # The explanations still standing when the check ran.
    current_hypothesis_ids: tuple[str, ...] = ()
    gaps: tuple[GapRecord, ...] = ()
    # True when the check made it "unresolved" although the model said
    # "supported": the check, not the model, held the diagnosis open.
    forced_unresolved: bool = False


# The most tool calls one decide answer may list (DECIDE_CALLS).
MAX_DECIDE_CALLS = 5


class BatchTrace(Contract):
    """What batching did in one investigation (DECIDE_CALLS above 1).

    Counts only, filled by the loop. Each call's own DecisionRecord also says
    which answer chose it (`batch`) and its place in that answer.
    """

    # Decide answers that chose at least one tool call.
    answers: int = Field(default=0, ge=0)
    # Tool calls those answers listed, before any cut.
    chosen: int = Field(default=0, ge=0)
    # Tool calls the loop then ran (a repeat still counts as run; it is
    # recorded as repeated_call and costs no call).
    run: int = Field(default=0, ge=0)
    # Calls dropped at a `wait`: a wait listed after reads and everything
    # after it, or everything after a wait listed first (which runs alone).
    cut_at_wait: int = Field(default=0, ge=0)
    # Calls dropped because the answer listed more than DECIDE_CALLS.
    cut_over_limit: int = Field(default=0, ge=0)
    # Calls dropped because the tool-call budget had run out.
    cut_for_budget: int = Field(default=0, ge=0)
    # Answers whose results were read together in one question.
    read_together: int = Field(default=0, ge=0)


class DecisionRecord(Contract):
    """What the agent chose at one step and what happened. Not chain-of-thought."""

    sequence: int = Field(ge=1)
    agent: str = "research_agent"
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
    # With DECIDE_CALLS above 1: which decide answer chose this call (1, 2, ...)
    # and its place in that answer's list (1 is first). None otherwise.
    batch: int | None = Field(default=None, ge=1)
    batch_position: int | None = Field(default=None, ge=1)


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
    # "triage": a read-only first look that never proposes a change; "deep":
    # the full workflow. See `triage_budgets`.
    mode: Mode = "deep"
    # On a deep run started from a triage: that triage's investigation id,
    # so the two can be traced. Only the reference: the deep run is not shown
    # the triage's conclusion.
    follows_triage: UUID | None = None
    # Whether prompts state the action threshold; kept for experiment records.
    state_action_bar: bool = True
    # The configured loop mode, kept for experiment records. The loop sets it.
    step_questions: int = Field(default=2, ge=1, le=2)
    # Opt-in comparison arm: gather bounded line context before planning.
    line_context_enabled: bool = False
    incident_context: IncidentContext | None = None
    # The most tool calls one decide answer may list (DECIDE_CALLS). The loop
    # sets it; a policy reads it to know whether it may answer with a list.
    decide_calls: int = Field(default=1, ge=1, le=MAX_DECIDE_CALLS)
    # What batching did, for the record; None when decide_calls is 1.
    decide_batches: BatchTrace | None = None
    # STAGE_CONTEXT: judge_verification and write_lesson get views made for
    # them instead of the shared one. Set when the run starts; a policy reads it.
    stage_context: bool = False

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
    critic_tool_calls_used: int = Field(default=0, ge=0)
    # The loop's own line screening at the start; never charged to research.
    screening_tool_calls_used: int = Field(default=0, ge=0)
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
    # The recommendation the policy itself gave, before `check_conclusion`,
    # and, if an intervention was lowered to escalate, why. The conclusion
    # above holds the final one. For measurement: "chose escalate" and
    # "overruled" look the same in the conclusion alone.
    policy_recommendation: str | None = None
    recommendation_lowered: str | None = None
    # Why the policy's final answer was refused (it broke a rule, for example
    # cited evidence that was never gathered), so the conclusion fell back to
    # "undetermined". None when an answer was accepted or none came.
    conclusion_rejected: str | None = None
    # The final check's gaps, each with its kind, for replaying other gap
    # rules offline. None when the answer made no completion claim.
    conclusion_trace: ConclusionTrace | None = None
    proposed_action: ProposalRecord | None = None
    # The tick at which the conclusion was reached.
    concluded_tick: int | None = Field(default=None, ge=0)
    # What should change in the factory if the diagnosis is right.
    predicted_effect: str | None = None
    # Set only when the factory confirmed that the approved work started.
    action_started_tick: int | None = Field(default=None, ge=0)
    action_finish_tick: int | None = Field(default=None, ge=0)
    verification: VerificationCheck | None = None
    # Triage only: whether a deep investigation should follow. Set by code
    # from the conclusion (`investigation.needs_deep_run`), never by the model.
    # None on a deep run.
    deep_recommended: bool | None = None
    # What the critic said about the two leading hypotheses, or why it said
    # nothing. Review only: nothing else in the run reads it.
    critique: CritiqueRecord | None = None
    # What tree-of-thought ruled out at the hypothesize step, and why. Empty
    # without tree-of-thought. Shown to the critic; never tested or believed.
    pruned_candidates: list[PrunedCandidate] = Field(default_factory=list)
    # What the critic follow-up did (`investigation.recheck`), or why it did
    # nothing. None: the follow-up is off, or no critic ran.
    recheck: RecheckRecord | None = None
    # The hypothesis reserve (`InvestigationDeps.hypothesis_seconds`): None
    # when none was kept; True when research ran out of time and the reserve
    # let the hypothesize question be asked anyway; False when it was kept
    # but research ended for another reason.
    hypothesis_reserve_used: bool | None = None
    # P2 (TOT_REINSTATE): what the critic's reinstatement question did right
    # after pruning. None: it was off, or there was nothing pruned to offer.
    reinstatement: ReinstatementRecord | None = None
    # P5 (TOT_REVALUE): what the tree's second rating pass, after the test
    # stage, did. None: it was off, or the policy is not the tree.
    revaluation: RevaluationRecord | None = None
    # Set by the loop only on the copy a policy is given: how long the policy
    # may take to answer, the time its stage has left. None on the loop's own
    # state, and outside a running investigation.
    seconds_for_question: float | None = Field(default=None, ge=0)
    # Also set only on the policy's copy: the confidence an intervention
    # needs to be accepted (the loop's `min_action_confidence`), so the
    # prompt states the bar actually in force.
    action_confidence_needed: float | None = Field(default=None, ge=0, le=1)

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
        """Calls charged to research: all but the checking allowances and the line screening."""
        # Variables:
        #   tool_call_count: Every real call, including verification, critic reads
        #     and the loop's own line screening, none of which research pays for.
        return (
            self.tool_call_count
            - self.followup_tool_calls_used
            - self.critic_tool_calls_used
            - self.screening_tool_calls_used
        )

    @property
    def remaining_critic_tool_calls(self) -> int:
        """The single diagnostic read research cannot spend, or zero once used."""
        return max(0, self.budgets.critic_tool_calls - self.critic_tool_calls_used)

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
        # Variables:
        #   now: The clock reading to measure from, passed in so tests control time.
        if self.started_at is None:
            return self.budgets.timeout_seconds
        return max(0.0, self.budgets.timeout_seconds - (now - self.started_at))

    def research_seconds(self, now: float) -> float:
        """Time left for research: the deadline less what is kept for afterwards."""
        # Variables:
        #   now: The clock reading to measure from, passed in so tests control time.
        return max(0.0, self.remaining_seconds(now) - self.budgets.followup_seconds)

    def evidence_for(self, question_id: str) -> Evidence | None:
        """The newest evidence that answered a question, if any."""
        # Variables:
        #   ids: Evidence ids that answered this question, newest last.
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
