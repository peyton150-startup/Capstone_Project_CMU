# The inner reasoning loop: decide, call one tool, read the result, update state.
# Responsibility: enforce budgets, repeats, bad results, and every reason to stop.
"""The ReAct-style inner loop of one investigation.

Each turn of the loop does five things in a fixed order:

    1. check whether the loop must stop
    2. ask the policy what information is needed and which tool gets it
    3. call that one tool through the provider
    4. turn a usable answer into evidence and let the policy revise beliefs
    5. write a DecisionRecord of what was chosen and what happened

The policy chooses; this module decides what is allowed. A policy cannot
exceed a budget, repeat a question at the same tick, or count a failed
call as evidence, because none of that is left to it.

With STEP_QUESTIONS=1, the reading of a result also proposes the next
decision. It is held until the next turn's checks pass. The first decision
of each phase is still asked separately, and the last result is interpreted
even when no more tool calls are allowed.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import TypeVar

from capstone.agent.artifacts import ProposalRecord, TerminationReason
from capstone.agent.critic import Critic
from capstone.agent.evidence_brief import verify_numeric_claims
from capstone.agent.policy import (
    CallTool,
    CallTools,
    Interpretation,
    InterpretedStep,
    LoopPhase,
    ReasoningPolicy,
    Stop,
)
from capstone.agent.state import (
    MAX_DECIDE_CALLS,
    BatchTrace,
    DecisionRecord,
    InvestigationState,
    Phase,
    StepOutcome,
)
from capstone.contracts.evidence import Evidence
from capstone.contracts.provenance import (
    MANUAL_SOURCE,
    MEMORY_SOURCE,
    ProvenanceReference,
)
from capstone.contracts.tools import ToolError, ToolRequest, ToolResult
from capstone.observability import EventLogger
from capstone.providers.chat import ModelError
from capstone.providers.factory import FactoryProvider

# What a policy may get wrong without it being a bug in this module:
# an invalid model, a missing key, a value of the wrong type.
POLICY_ERRORS = (ValueError, TypeError, LookupError)

Reply = TypeVar("Reply")


# Answers that are not a look at the factory, by their source.
ORIGINS = {MEMORY_SOURCE: "memory", MANUAL_SOURCE: "manual"}

_log = logging.getLogger(__name__)


class OutOfTime(Exception):
    """A policy question got no answer before its stage's time ran out.

    Neither the policy's mistake nor an outage: the clock ran out. Research
    then stops with TIMEOUT and the investigation goes on to its conclusion
    in the time kept for it.

    `asked` is True when at least one request went out and none answered,
    False when the time was gone before any model could be asked. A triage
    conclusion uses it to tell a dead service from a slow agent.
    """

    def __init__(self, *, asked: bool = False):
        super().__init__()
        self.asked = asked


@dataclass
class InvestigationDeps:
    """Everything the loop needs from outside. None of it is simulator truth."""

    provider: FactoryProvider
    policy: ReasoningPolicy
    # A recorded machine has no simulator healthy-line screening tool.
    # Keep this True for all existing simulator investigations.
    screening_available: bool = True
    # Seconds that only move forward. Injected so that tests control time.
    clock: Callable[[], float] = monotonic
    # The best explanation must be at least this sure, with this much
    # supporting evidence, before the loop calls a diagnosis supported.
    min_diagnosis_confidence: float = 0.9
    min_supporting_evidence: int = 2
    min_action_confidence: float = 0.9
    state_action_bar: bool = True
    # Testing stops when this many results have moved confidence by less than
    # this much: more of the same is not changing the agent's mind.
    stalled_test_results: int = 3
    min_confidence_change: float = 0.05
    # The longest single wait the factory accepts, in ticks.
    max_wait_ticks: int = 480
    # The human's side. Called once with each submitted proposal; the agent
    # is never given the means to approve its own request.
    human_review: Callable[[ProposalRecord], None] | None = field(default=None)
    # Someone watching the run (`capstone.progress`). Called with a copy of the
    # state before each turn, after each stage and before the human's review;
    # it can read what the agent has, never change it. None: nobody watches.
    watch: Callable[[InvestigationState], None] | None = field(default=None)
    step_questions: int = 2
    # The most tool calls one decide answer may list (DECIDE_CALLS). 1, the
    # default, is one call per answer, exactly as before batching.
    decide_calls: int = 1
    # A second model that reviews the two leading hypotheses before the
    # conclusion (`investigation.critique`). None: no critique. Its window
    # is its own, on top of the investigation's time.
    critic: Critic | None = None
    critic_seconds: float = 40.0
    # The critic follow-up (`investigation.recheck`): one reading the critic
    # pointed at, when it objects or agrees and names a check. Off: the
    # critic stays review only.
    critic_followup: bool = False
    # The follow-up's own time window, on top of the investigation's time (as
    # the critic's is), so it can run after research timed out.
    recheck_seconds: float = 90.0
    # The manual step (`investigation.consult_manual`): search the machine
    # manual once on the anomaly before planning. Only with a manual offered.
    manual_step: bool = False
    # The hypothesis reserve: research before the hypothesize question stops
    # this many seconds early, so that question is still asked when research
    # runs long. 0 (the default) keeps no reserve, as every run before it did.
    # The trace audit of 2026-11-05 found 7 of 16 tree-less runs had spent all
    # research time investigating and gone straight to the conclusion.
    hypothesis_seconds: float = 0.0
    # P2 (TOT_REINSTATE): right after tree-of-thought pruning, ask the critic
    # whether one dropped candidate deserves a check (`investigation.reconsider`).
    # It uses the critic's own window. Off: pruned candidates are only shown to
    # the critique later, as before. Needs a critic.
    critic_reinstate: bool = False
    # Opt-in structured logging (`capstone.observability`): identifiers and
    # counts only, never evidence text. Used by the triage evidence packet.
    # None: nothing is logged.
    event_logger: EventLogger | None = None

    def __post_init__(self) -> None:
        if self.step_questions not in (1, 2):
            raise ValueError("step_questions must be 1 or 2")
        if self.hypothesis_seconds < 0:
            raise ValueError("hypothesis_seconds cannot be negative")
        if self.step_questions == 1 and not callable(
            getattr(self.policy, "interpret_and_decide", None)
        ):
            raise ValueError(
                "one-question mode needs a policy with interpret_and_decide"
            )
        if not 1 <= self.decide_calls <= MAX_DECIDE_CALLS:
            raise ValueError(f"decide_calls must be from 1 to {MAX_DECIDE_CALLS}")
        if (
            self.decide_calls > 1
            and self.step_questions == 1
            and not callable(getattr(self.policy, "interpret_and_decide_many", None))
        ):
            raise ValueError(
                "several calls per answer in one-question mode need a policy "
                "with interpret_and_decide_many"
            )


def notify(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Show the watcher, if any, a copy of the state as it is now.

    A copy, so a watcher cannot change the investigation. A watcher that
    raises is logged and ignored: a display fault must never stop a run or
    change what it does.
    """
    if deps.watch is None:
        return
    try:
        deps.watch(state.model_copy(deep=True))
    except Exception:
        # The exception text could quote evidence; log the event only.
        _log.warning("the run's watcher failed; the run goes on")


def diagnosis_supported(state: InvestigationState, deps: InvestigationDeps) -> bool:
    """True when the best explanation is confident, backed, not contradicted,
    and no open question still tests any current explanation.

    Any contradicting evidence keeps the loop testing. Counting supporters
    against contradictions would not do: several pieces of evidence can be
    views of one reading (an alarm, the raw readings, their summary). An
    open question that tests an explanation, the leading one or a rival,
    means the evidence the agent itself said it needs is not in yet, so
    confidence alone does not settle it (AgentLoop, arXiv 2609.33315). The
    policy can still stop on its own and conclude, and the usual budgets
    still end research.

    Only supporters the factory itself answered count towards
    `min_supporting_evidence`: a memory is a past belief and the manual is
    general guidance for the machine model, so neither shows that this
    machine has the fault now (the same rule `verify` applies after a fix).
    """
    # Variables:
    #   leading: The explanation the agent currently believes most.
    #   current: Ids of the explanations still in play, used to see if any open question
    #     still tests one.
    #   observed: Ids of evidence the factory answered, from the loop's provenance.
    #   backed: How many of the leading explanation's supporters are observed.
    leading = state.leading_hypothesis
    current = {h.id for h in state.hypotheses}
    observed = {p.evidence_id for p in state.provenance if p.origin == "observable"}
    backed = (
        0 if leading is None else len(set(leading.supporting_evidence_ids) & observed)
    )
    return (
        leading is not None
        and leading.confidence >= deps.min_diagnosis_confidence
        and backed >= deps.min_supporting_evidence
        and not leading.contradicting_evidence_ids
        and not leading.unexplained_evidence_ids
        and not verify_numeric_claims(state, leading.numeric_claims)
        and not any(q.hypothesis_id in current for q in state.unanswered_questions)
    )


def confidence_stalled(state: InvestigationState, deps: InvestigationDeps) -> bool:
    """True when the latest test results have barely moved the agent's confidence.

    Looks at the last `stalled_test_results` results the policy interpreted
    while testing. Rewording a claim or nudging a number by a hundredth is
    not progress; moving confidence by `min_confidence_change` is.
    """
    # Variables:
    #   recent: Confidence after each of the latest test results, oldest first.
    recent = [
        d.confidence
        for d in state.decisions
        if d.phase == "test" and d.outcome == "observed"
    ][-deps.stalled_test_results :]
    return (
        len(recent) == deps.stalled_test_results
        and max(recent) - min(recent) < deps.min_confidence_change
    )


def check_termination(
    state: InvestigationState,
    deps: InvestigationDeps,
    phase: LoopPhase,
    phase_iterations: int,
) -> TerminationReason | None:
    """The reason the loop must stop now, or None to carry on.

    The order is a contract. Running out of time beats everything; a
    supported diagnosis beats a budget, so a loop that reaches its answer
    on its last allowed call reports success, not exhaustion. Research
    also stops while `followup_seconds` remain, so that the conclusion,
    the proposal, the work and the check keep the time they need, and,
    before the hypotheses, while `hypothesis_seconds` remain on top of that
    (`held_for_hypotheses`), so the hypothesize question still gets asked.
    """
    # Variables:
    #   phase: Which loop is asking; the hypothesis reserve is held only in
    #     the stages before the hypotheses.
    #   phase_iterations: Turns this phase has already taken, used only for the verify
    #     limit.
    #   budgets: The limits for this run (time, calls, turns).
    #   now: The clock reading, taken once so every check uses the same moment.
    budgets = state.budgets
    now = deps.clock()
    if state.remaining_seconds(now) <= 0:
        return TerminationReason.TIMEOUT
    if phase == "test" and diagnosis_supported(state, deps):
        return TerminationReason.DIAGNOSIS_SUPPORTED
    if (
        phase != "verify"
        and state.research_seconds(now) - held_for_hypotheses(state, deps) <= 0
    ):
        return TerminationReason.TIMEOUT
    if state.unproductive_steps >= budgets.max_unproductive_steps:
        return TerminationReason.NO_USEFUL_ACTION
    if phase == "test" and confidence_stalled(state, deps):
        return TerminationReason.NO_USEFUL_ACTION
    if phase == "verify":
        # Verification spends its own allowance, never the research budget.
        if phase_iterations >= 2 * budgets.followup_tool_calls:
            return TerminationReason.MAX_ITERATIONS
        if state.remaining_followup_tool_calls == 0:
            return TerminationReason.MAX_TOOL_CALLS
        return None
    if state.remaining_iterations == 0:
        return TerminationReason.MAX_ITERATIONS
    if state.remaining_tool_calls == 0:
        return TerminationReason.MAX_TOOL_CALLS
    return None


# The stages that run before the hypothesize question, and so keep the reserve.
BEFORE_HYPOTHESES = frozenset({"observe", "plan", "investigate"})


def held_for_hypotheses(state: InvestigationState, deps: InvestigationDeps) -> float:
    """Seconds the current stage must leave for the hypothesize question.

    The reserve (`deps.hypothesis_seconds`) is held only before that question:
    from the hypothesize stage on it is part of research time again, so the
    question and the tests after it can spend it.
    """
    # Variables:
    #   state.stage: The stage now running; only the early ones keep the reserve.
    #   deps.hypothesis_seconds: The reserve; 0 keeps none.
    if state.stage in BEFORE_HYPOTHESES:
        return deps.hypothesis_seconds
    return 0.0


def seconds_left(
    state: InvestigationState, deps: InvestigationDeps, *, research: bool
) -> float:
    """The time a stage has left: research ends where the follow-up time begins.

    Before the hypothesize question, research also stops short of the
    hypothesis reserve (`held_for_hypotheses`), so that question keeps it.
    """
    # Variables:
    #   research: True for research stages, which stop early to keep time for the
    #     follow-up.
    now = deps.clock()
    if not research:
        return state.remaining_seconds(now)
    return max(0.0, state.research_seconds(now) - held_for_hypotheses(state, deps))


def ask_policy(
    state: InvestigationState,
    deps: InvestigationDeps,
    question: Callable[[InvestigationState], Reply],
    *,
    research: bool,
) -> Reply:
    """Put one question to the policy, on a copy of state, within its stage's time.

    The copy says how long the answer may take (`seconds_for_question`), so a
    model-backed policy can stop waiting when the stage's time is up. If no
    model answered and that time has run out, raises OutOfTime: the clock,
    not the model services, is why there is no answer. So is a ModelError
    marked `out_of_time`: the client gave up because the time it was given
    ran out, with less left than a retry would need. A ModelError with time
    still left is an outage and goes on up unchanged.
    """
    # Variables:
    #   question: The policy method to ask, e.g. decide or conclude.
    #   research: True if the question draws on research time, False if it may use all
    #     remaining time.
    #   view: A deep copy of the state; the policy sees it, but changing it changes
    #     nothing real.
    #   error.attempts: Requests the client really sent before it gave up;
    #     passed on as OutOfTime's `asked`.
    view = state.model_copy(deep=True)
    view.state_action_bar = deps.state_action_bar
    view.action_confidence_needed = None
    if state.started_at is not None:
        view.seconds_for_question = seconds_left(state, deps, research=research)
        if deps.state_action_bar:
            view.action_confidence_needed = deps.min_action_confidence
    try:
        return question(view)
    except ModelError as error:
        if state.started_at is not None and (
            getattr(error, "out_of_time", False)
            or seconds_left(state, deps, research=research) <= 0
        ):
            raise OutOfTime(asked=getattr(error, "attempts", 0) > 0) from None
        raise


def call_tool(
    state: InvestigationState,
    deps: InvestigationDeps,
    request: ToolRequest,
    *,
    followup: bool = False,
    critic_check: bool = False,
) -> ToolResult | None:
    """Make one counted tool call. Returns None when the answer cannot be trusted.

    A provider that raises, returns the wrong kind of object, or answers
    for a different tool or a different investigation is treated as having
    given no answer. The agent carries on; it does not crash and it does
    not guess.
    """
    # Variables:
    #   followup: True if the call spends the follow-up allowance, not the research one.
    #   critic_check: Charges the separate diagnostic allowance, never verification.
    #   result: The provider's answer, or None if it cannot be trusted.
    state.tool_call_count += 1
    if followup:
        state.followup_tool_calls_used += 1
    if critic_check:
        state.critic_tool_calls_used += 1
    try:
        result = deps.provider.call(
            request, run_id=state.run_id, investigation_id=state.investigation_id
        )
    except Exception:
        # Provider errors may carry secrets or driver detail; never keep them.
        return None
    if not isinstance(result, ToolResult) or result.tool != request.name:
        return None
    if (result.run_id, result.investigation_id) != (
        state.run_id,
        state.investigation_id,
    ):
        # An answer addressed to someone else is not this investigation's evidence.
        return None
    state.last_tick = result.tick
    return result


def apply_interpretation(
    state: InvestigationState, interpretation: Interpretation
) -> None:
    """Check a policy's revised beliefs, then make them the state's beliefs.

    Raises ValueError, changing nothing, if a hypothesis cites evidence
    that does not exist: a belief must point at something that was seen.
    """
    # Variables:
    #   revised: The policy's new set of explanations, or None if it left them
    #     unchanged.
    #   ids: Ids of the revised explanations, which must all be different.
    #   known: Ids of all evidence gathered so far; a belief may cite only these.
    #   cited: Every evidence id one revised explanation relies on, for or against.
    #   before: The old explanations by id, to count how many changed.
    #   after: The new explanations by id, to count how many changed.
    #   open_ids: Ids of questions still open, so a question is never added twice.
    #   interpretation.pruned: Only on tree-of-thought's hypothesize answer: the
    #     candidates it ruled out, kept in the state's trace for the critic.
    #   hypothesis.numeric_claims: Arithmetic checked before any revised belief is applied.
    if not isinstance(interpretation, Interpretation):
        raise ValueError("a policy must return an Interpretation")
    revised = interpretation.hypotheses
    if revised is not None:
        ids = [h.id for h in revised]
        if len(ids) != len(set(ids)):
            raise ValueError("hypothesis ids must be unique")
        known = {e.id for e in state.evidence}
        for hypothesis in revised:
            cited = (
                *hypothesis.supporting_evidence_ids,
                *hypothesis.contradicting_evidence_ids,
                *hypothesis.unexplained_evidence_ids,
            )
            if not known.issuperset(cited):
                raise ValueError("a hypothesis cites evidence that was not gathered")
            verify_numeric_claims(state, hypothesis.numeric_claims)
        if state.hypotheses:
            # The first set is a starting point, not a revision.
            before = {h.id: h for h in state.hypotheses}
            after = {h.id: h for h in revised}
            state.hypothesis_revisions += sum(
                before.get(key) != after.get(key) for key in before.keys() | after
            )
        state.hypotheses = list(revised)
    # What tree-of-thought ruled out goes into the trace as it is; `prune`
    # already dropped any candidate that cited evidence never gathered.
    state.pruned_candidates.extend(getattr(interpretation, "pruned", ()))
    open_ids = {q.id for q in state.unanswered_questions}
    for question in interpretation.new_questions:
        if question.id not in open_ids and question.id not in state.answers:
            state.unanswered_questions.append(question)
            open_ids.add(question.id)


def record(
    state: InvestigationState,
    phase: Phase,
    outcome: StepOutcome,
    *,
    information_needed: str,
    step: CallTool | None = None,
    evidence_ids: tuple[str, ...] = (),
    termination_reason: TerminationReason | None = None,
    error: ToolError | None = None,
) -> None:
    """Append one decision artifact: what was chosen and what came of it."""
    state.decisions.append(
        DecisionRecord(
            sequence=len(state.decisions) + 1,
            phase=phase,
            tick=state.last_tick,
            information_needed=information_needed,
            question_id=step.question_id if step else None,
            hypothesis_id=step.hypothesis_id if step else None,
            tool=step.request.name if step else None,
            arguments=dict(step.request.arguments) if step else {},
            outcome=outcome,
            evidence_ids=evidence_ids,
            confidence=state.confidence,
            termination_reason=termination_reason,
            error=error,
        )
    )


def call_signature(request: ToolRequest, tick: int | None) -> str:
    """One question at one moment, as text, so a repeat can be recognised."""
    return "|".join(
        (request.name, json.dumps(request.arguments, sort_keys=True), str(tick))
    )


def gather(
    state: InvestigationState,
    deps: InvestigationDeps,
    phase: Phase,
    step: CallTool,
    *,
    followup: bool = False,
    critic_check: bool = False,
    interpret: bool = True,
) -> Evidence | None:
    """Call one tool and keep its answer as evidence. Always leaves a record.

    Returns the new evidence, or None if the factory gave nothing usable.
    With `interpret=False`, for calls the loop makes itself, the policy is
    not asked what the answer means.
    """
    # Variables:
    #   signature: This question at this tick as text, used to spot a repeat.
    #   result: The tool's answer, or None if it cannot be trusted.
    #   outcome: observed, malformed_result or tool_error; anything but observed is a
    #     wasted step.
    #   evidence: The answer saved as a new piece of evidence, numbered E1, E2 and so
    #     on.
    #   critic_check: The controller's bounded read, excluded from research call usage.
    signature = call_signature(step.request, state.last_tick)
    if signature in state.seen_calls:
        # Looking is free in the simulator, so the same question at the same
        # tick can only return what is already known. Do not spend a call.
        state.repeated_calls += 1
        state.unproductive_steps += 1
        record(
            state,
            phase,
            "repeated_call",
            information_needed=step.information_needed,
            step=step,
        )
        return None
    state.seen_calls.append(signature)

    result = call_tool(
        state, deps, step.request, followup=followup, critic_check=critic_check
    )
    outcome: StepOutcome = "observed"
    if result is None or (result.success and result.data is None):
        state.malformed_results += 1
        outcome = "malformed_result"
    elif not result.success:
        state.failed_tool_calls += 1
        outcome = "tool_error"
    if outcome != "observed":
        state.unproductive_steps += 1
        record(
            state,
            phase,
            outcome,
            information_needed=step.information_needed,
            step=step,
            # What the tool said was wrong, so the next decision can correct it.
            error=result.error if result is not None else None,
        )
        return None

    evidence = Evidence(
        id=f"E{len(state.evidence) + 1}",
        source_id=f"{result.source}:{result.tool}",
        source_type="tool_result",
        content=json.dumps(result.data, sort_keys=True),
        observed_tick=result.tick,
        observed_at=result.timestamp,
    )
    state.evidence.append(evidence)
    # Written here, from the same tool answer, and never by the policy.
    # Everything the factory provider offers is something an operator
    # could see, so its answers are observable. An answer from memory is a
    # past investigation's belief, so it is labelled memory instead; one from
    # the machine manual is general guidance, labelled manual.
    state.provenance.append(
        ProvenanceReference(
            evidence_id=evidence.id,
            source_id=evidence.source_id,
            source_type=evidence.source_type,
            origin=ORIGINS.get(result.source, "observable"),
            observed_tick=evidence.observed_tick,
        )
    )
    if step.question_id is not None:
        state.answers.setdefault(step.question_id, []).append(evidence.id)
        state.unanswered_questions = [
            q for q in state.unanswered_questions if q.id != step.question_id
        ]
    if interpret:
        try:
            apply_interpretation(
                state,
                ask_policy(
                    state,
                    deps,
                    lambda view: deps.policy.interpret(view, step, evidence),
                    research=phase != "verify",
                ),
            )
        except OutOfTime:
            # The evidence stays and no belief changes. Not the policy's
            # failure, so nothing is counted against it; the next turn's
            # check stops the loop on time.
            record(
                state,
                phase,
                "uninterpreted",
                information_needed=step.information_needed,
                step=step,
                evidence_ids=(evidence.id,),
            )
            return evidence
        except POLICY_ERRORS:
            # The factory did answer, so the evidence stays. What failed is the
            # policy's reading of it: no belief changes, and the turn counts as
            # unproductive so a policy that never interprets cannot run forever.
            state.interpretation_failures += 1
            state.unproductive_steps += 1
            record(
                state,
                phase,
                "uninterpreted",
                information_needed=step.information_needed,
                step=step,
                evidence_ids=(evidence.id,),
            )
            return evidence
    state.unproductive_steps = 0
    record(
        state,
        phase,
        "observed",
        information_needed=step.information_needed,
        step=step,
        evidence_ids=(evidence.id,),
    )
    return evidence


def batch_steps(
    decision: CallTool | CallTools, limit: int, budget: int
) -> tuple[list[CallTool], int, int, int]:
    """The calls to run from one decide answer, and how many were cut, by reason.

    In order: at most `limit` calls; then a cut at the first `wait` (a wait
    listed first runs alone; one listed later is dropped with everything
    after it, so the policy sees the reads before choosing to let time pass);
    then at most `budget` calls, never fewer than one.
    """
    # Variables:
    #   limit: DECIDE_CALLS, the most calls one answer may run.
    #   budget: The tool calls this phase has left; the loop's checks already
    #     ensured at least one before the policy was asked.
    #   steps: The calls still to run, cut down step by step.
    #   over: Calls dropped for being past the limit.
    #   keep: How many calls run before the first wait (or 1 when wait is first).
    #   at_wait: Calls dropped at the wait.
    #   for_budget: Calls dropped because the budget is spent.
    steps = [decision] if isinstance(decision, CallTool) else list(decision.steps)
    over = max(0, len(steps) - limit)
    steps = steps[:limit]
    keep = next(
        (max(1, i) for i, step in enumerate(steps) if step.request.name == "wait"),
        len(steps),
    )
    at_wait = len(steps) - keep
    steps = steps[:keep]
    room = max(1, budget)
    for_budget = max(0, len(steps) - room)
    return steps[:room], at_wait, over, for_budget


def run_batch(
    state: InvestigationState,
    deps: InvestigationDeps,
    phase: LoopPhase,
    decision: CallTool | CallTools,
) -> list[tuple[CallTool, Evidence, int]]:
    """Run the calls of one decide answer in order; return those that gave evidence.

    With one call this is exactly `gather`, as before batching. With
    DECIDE_CALLS above 1 it also numbers the answer, marks each call's record
    with that number and its place, and counts the cuts in the trace.
    """
    # Variables:
    #   budget: The tool calls this phase has left (follow-up calls in verify).
    #   steps: The calls left after the cuts, in the policy's order.
    #   trace: The run's batch counts; None when batching is off.
    #   batch: This answer's number, written on each of its calls' records.
    #   read: Each call that produced evidence, with that evidence and the
    #     index of its record, so the reading can update those records.
    budget = (
        state.remaining_followup_tool_calls
        if phase == "verify"
        else state.remaining_tool_calls
    )
    steps, at_wait, over, for_budget = batch_steps(decision, deps.decide_calls, budget)
    trace = state.decide_batches
    batch = None
    if trace is not None:
        trace = trace.model_copy(
            update={
                "answers": trace.answers + 1,
                "chosen": trace.chosen + len(steps) + at_wait + over + for_budget,
                "run": trace.run + len(steps),
                "cut_at_wait": trace.cut_at_wait + at_wait,
                "cut_over_limit": trace.cut_over_limit + over,
                "cut_for_budget": trace.cut_for_budget + for_budget,
            }
        )
        state.decide_batches = trace
        batch = trace.answers
    read = []
    for position, step in enumerate(steps, start=1):
        evidence = gather(
            state,
            deps,
            phase,
            step,
            followup=phase == "verify",
            interpret=deps.step_questions == 2,
        )
        if batch is not None:
            state.decisions[-1] = state.decisions[-1].model_copy(
                update={"batch": batch, "batch_position": position}
            )
        if evidence is not None:
            read.append((step, evidence, len(state.decisions) - 1))
    return read


def mark_read(
    state: InvestigationState,
    read: list[tuple[CallTool, Evidence, int]],
    update: dict,
) -> None:
    """Apply one update (its outcome or confidence) to the records of every call read."""
    # Variables:
    #   read: The calls that produced evidence this turn, with their record indexes.
    #   update: The fields to change on each of those records.
    for _, _, index in read:
        state.decisions[index] = state.decisions[index].model_copy(update=update)


def run_inner_loop(
    state: InvestigationState, deps: InvestigationDeps, phase: LoopPhase
) -> TerminationReason:
    """Run decide-act-observe turns until there is a reason to stop.

    Always ends: every turn either stops or uses up an iteration, and
    iterations are limited. The reason is returned and also written as
    the last DecisionRecord of the loop.
    """
    # Variables:
    #   pending_decision: In one-question mode, the next step proposed with the last
    #     reading, held until the next turn's checks pass.
    #   phase_iterations: How many turns this phase has taken so far.
    #   reason: Why the loop must stop, or None to carry on.
    #   decision: What the policy chose this turn: a tool call, a list of calls
    #     (DECIDE_CALLS above 1) or a stop.
    #   before_unproductive: The unproductive-step count before this turn, restored if
    #     the reading fails.
    #   read: The calls this turn that produced evidence, with that evidence and
    #     the index of each call's record; empty if none gave anything usable.
    #   pairs: With several results, each call and its evidence, read together
    #     in one question.
    #   reply: In one-question mode, the combined reading and next decision.
    if state.started_at is None:
        # The deadline covers the whole investigation, so only the first loop
        # starts the timer. Without this the timeout could never fire.
        state.started_at = deps.clock()
    state.unproductive_steps = 0
    state.step_questions = deps.step_questions
    state.decide_calls = deps.decide_calls
    if deps.decide_calls > 1 and state.decide_batches is None:
        state.decide_batches = BatchTrace()
    pending_decision = None
    phase_iterations = 0
    while True:
        # Before the policy is asked (the slow part), show the last turn.
        notify(state, deps)
        reason = check_termination(state, deps, phase, phase_iterations)
        if reason is not None:
            record(
                state,
                phase,
                "stopped",
                information_needed="nothing further",
                termination_reason=reason,
            )
            return reason
        state.iteration_count += 1
        phase_iterations += 1
        try:
            decision = pending_decision
            pending_decision = None
            if decision is None:
                decision = ask_policy(
                    state,
                    deps,
                    lambda view: deps.policy.decide(view, phase),
                    research=phase != "verify",
                )
            if not isinstance(decision, CallTool | CallTools | Stop):
                raise ValueError("a policy must return CallTool, CallTools or Stop")
        except OutOfTime:
            record(
                state,
                phase,
                "stopped",
                information_needed="an answer before the time ran out",
                termination_reason=TerminationReason.TIMEOUT,
            )
            return TerminationReason.TIMEOUT
        except POLICY_ERRORS:
            state.unproductive_steps += 1
            record(
                state,
                phase,
                "invalid_decision",
                information_needed="a usable decision from the policy",
            )
            continue
        if isinstance(decision, Stop):
            reason = decision.reason
            if reason is TerminationReason.EVIDENCE_SUFFICIENT and not state.evidence:
                # "Enough evidence" with no evidence is not a real stop.
                reason = TerminationReason.NO_USEFUL_ACTION
            record(
                state,
                phase,
                "stopped",
                information_needed=decision.information_needed,
                termination_reason=reason,
            )
            return reason
        before_unproductive = state.unproductive_steps
        read = run_batch(state, deps, phase, decision)
        if deps.step_questions == 1 and read:
            # Interpret even the last permitted tool result. The next step is
            # cached, never executed until the next turn's budget checks pass.
            # Several results from one answer are read in one question.
            try:
                if seconds_left(state, deps, research=phase != "verify") <= 0:
                    raise OutOfTime()
                if len(read) == 1:
                    [(step, evidence, _)] = read
                    reply = ask_policy(
                        state,
                        deps,
                        lambda view: deps.policy.interpret_and_decide(
                            view, phase, step, evidence
                        ),
                        research=phase != "verify",
                    )
                else:
                    pairs = tuple((step, evidence) for step, evidence, _ in read)
                    reply = ask_policy(
                        state,
                        deps,
                        lambda view: deps.policy.interpret_and_decide_many(
                            view, phase, pairs
                        ),
                        research=phase != "verify",
                    )
                    trace = state.decide_batches
                    if trace is not None:
                        state.decide_batches = trace.model_copy(
                            update={"read_together": trace.read_together + 1}
                        )
                if not isinstance(reply, InterpretedStep):
                    raise ValueError("a combined reply must be an InterpretedStep")
                apply_interpretation(state, reply.interpretation)
                pending_decision = reply.decision
            except OutOfTime:
                mark_read(state, read, {"outcome": "uninterpreted"})
                record(
                    state,
                    phase,
                    "stopped",
                    information_needed="an answer before the time ran out",
                    termination_reason=TerminationReason.TIMEOUT,
                )
                return TerminationReason.TIMEOUT
            except POLICY_ERRORS:
                state.interpretation_failures += 1
                state.unproductive_steps = before_unproductive + 1
                mark_read(state, read, {"outcome": "uninterpreted"})
                continue
            mark_read(state, read, {"confidence": state.confidence})
