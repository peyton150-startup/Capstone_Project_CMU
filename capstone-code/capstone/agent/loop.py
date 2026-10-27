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
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import TypeVar

from capstone.agent.artifacts import ProposalRecord, TerminationReason
from capstone.agent.policy import (
    CallTool,
    Interpretation,
    LoopPhase,
    ReasoningPolicy,
    Stop,
)
from capstone.agent.state import DecisionRecord, InvestigationState, Phase, StepOutcome
from capstone.contracts.evidence import Evidence
from capstone.contracts.provenance import (
    MANUAL_SOURCE,
    MEMORY_SOURCE,
    ProvenanceReference,
)
from capstone.contracts.tools import ToolError, ToolRequest, ToolResult
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
    """


@dataclass
class InvestigationDeps:
    """Everything the loop needs from outside. None of it is simulator truth."""

    provider: FactoryProvider
    policy: ReasoningPolicy
    # Seconds that only move forward. Injected so that tests control time.
    clock: Callable[[], float] = monotonic
    # The best explanation must be at least this sure, with this much
    # supporting evidence, before the loop calls a diagnosis supported.
    min_diagnosis_confidence: float = 0.9
    min_supporting_evidence: int = 2
    min_action_confidence: float = 0.9
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
    """
    leading = state.leading_hypothesis
    current = {h.id for h in state.hypotheses}
    return (
        leading is not None
        and leading.confidence >= deps.min_diagnosis_confidence
        and len(leading.supporting_evidence_ids) >= deps.min_supporting_evidence
        and not leading.contradicting_evidence_ids
        and not any(q.hypothesis_id in current for q in state.unanswered_questions)
    )


def confidence_stalled(state: InvestigationState, deps: InvestigationDeps) -> bool:
    """True when the latest test results have barely moved the agent's confidence.

    Looks at the last `stalled_test_results` results the policy interpreted
    while testing. Rewording a claim or nudging a number by a hundredth is
    not progress; moving confidence by `min_confidence_change` is.
    """
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
    the proposal, the work and the check keep the time they need.
    """
    budgets = state.budgets
    now = deps.clock()
    if state.remaining_seconds(now) <= 0:
        return TerminationReason.TIMEOUT
    if phase == "test" and diagnosis_supported(state, deps):
        return TerminationReason.DIAGNOSIS_SUPPORTED
    if phase != "verify" and state.research_seconds(now) <= 0:
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


def seconds_left(
    state: InvestigationState, deps: InvestigationDeps, *, research: bool
) -> float:
    """The time a stage has left: research ends where the follow-up time begins."""
    now = deps.clock()
    return state.research_seconds(now) if research else state.remaining_seconds(now)


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
    view = state.model_copy(deep=True)
    if state.started_at is not None:
        view.seconds_for_question = seconds_left(state, deps, research=research)
        view.action_confidence_needed = deps.min_action_confidence
    try:
        return question(view)
    except ModelError as error:
        if state.started_at is not None and (
            getattr(error, "out_of_time", False)
            or seconds_left(state, deps, research=research) <= 0
        ):
            raise OutOfTime() from None
        raise


def call_tool(
    state: InvestigationState,
    deps: InvestigationDeps,
    request: ToolRequest,
    *,
    followup: bool = False,
) -> ToolResult | None:
    """Make one counted tool call. Returns None when the answer cannot be trusted.

    A provider that raises, returns the wrong kind of object, or answers
    for a different tool or a different investigation is treated as having
    given no answer. The agent carries on; it does not crash and it does
    not guess.
    """
    state.tool_call_count += 1
    if followup:
        state.followup_tool_calls_used += 1
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
            )
            if not known.issuperset(cited):
                raise ValueError("a hypothesis cites evidence that was not gathered")
        if state.hypotheses:
            # The first set is a starting point, not a revision.
            before = {h.id: h for h in state.hypotheses}
            after = {h.id: h for h in revised}
            state.hypothesis_revisions += sum(
                before.get(key) != after.get(key) for key in before.keys() | after
            )
        state.hypotheses = list(revised)
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
    interpret: bool = True,
) -> Evidence | None:
    """Call one tool and keep its answer as evidence. Always leaves a record.

    Returns the new evidence, or None if the factory gave nothing usable.
    With `interpret=False`, for calls the loop makes itself, the policy is
    not asked what the answer means.
    """
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

    result = call_tool(state, deps, step.request, followup=followup)
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


def run_inner_loop(
    state: InvestigationState, deps: InvestigationDeps, phase: LoopPhase
) -> TerminationReason:
    """Run decide-act-observe turns until there is a reason to stop.

    Always ends: every turn either stops or uses up an iteration, and
    iterations are limited. The reason is returned and also written as
    the last DecisionRecord of the loop.
    """
    if state.started_at is None:
        # The deadline covers the whole investigation, so only the first loop
        # starts the timer. Without this the timeout could never fire.
        state.started_at = deps.clock()
    state.unproductive_steps = 0
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
            decision = ask_policy(
                state,
                deps,
                lambda view: deps.policy.decide(view, phase),
                research=phase != "verify",
            )
            if not isinstance(decision, CallTool | Stop):
                raise ValueError("a policy must return CallTool or Stop")
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
        gather(state, deps, phase, decision, followup=phase == "verify")
