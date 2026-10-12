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
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic

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
from capstone.contracts.tools import ToolRequest, ToolResult
from capstone.providers.factory import FactoryProvider

# What a policy may get wrong without it being a bug in this module:
# an invalid model, a missing key, a value of the wrong type.
POLICY_ERRORS = (ValueError, TypeError, LookupError)


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
    # The human's side. Called once with each submitted proposal; the agent
    # is never given the means to approve its own request.
    human_review: Callable[[ProposalRecord], None] | None = field(default=None)


def diagnosis_supported(state: InvestigationState, deps: InvestigationDeps) -> bool:
    """True when the best explanation is confident enough and backed by evidence."""
    leading = state.leading_hypothesis
    return (
        leading is not None
        and leading.confidence >= deps.min_diagnosis_confidence
        and len(leading.supporting_evidence_ids) >= deps.min_supporting_evidence
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
    on its last allowed call reports success, not exhaustion.
    """
    budgets = state.budgets
    if state.remaining_seconds(deps.clock()) <= 0:
        return TerminationReason.TIMEOUT
    if phase == "test" and diagnosis_supported(state, deps):
        return TerminationReason.DIAGNOSIS_SUPPORTED
    if state.unproductive_steps >= budgets.max_unproductive_steps:
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


def call_tool(
    state: InvestigationState,
    deps: InvestigationDeps,
    request: ToolRequest,
    *,
    followup: bool = False,
) -> ToolResult | None:
    """Make one counted tool call. Returns None when the answer cannot be trusted.

    A provider that raises, returns the wrong kind of object, or answers
    for a different tool is treated as having given no answer. The agent
    carries on; it does not crash and it does not guess.
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
        )
    )


def gather(
    state: InvestigationState,
    deps: InvestigationDeps,
    phase: Phase,
    step: CallTool,
    *,
    followup: bool = False,
) -> Evidence | None:
    """Call one tool and keep its answer as evidence. Always leaves a record.

    Returns the new evidence, or None if the step produced nothing usable.
    """
    signature = "|".join(
        (
            step.request.name,
            json.dumps(step.request.arguments, sort_keys=True),
            str(state.last_tick),
        )
    )
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
            state, phase, outcome, information_needed=step.information_needed, step=step
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
    answered = [q for q in state.unanswered_questions if q.id == step.question_id]
    state.evidence.append(evidence)
    if step.question_id is not None:
        state.answers.setdefault(step.question_id, []).append(evidence.id)
        state.unanswered_questions = [
            q for q in state.unanswered_questions if q.id != step.question_id
        ]
    try:
        apply_interpretation(
            state,
            deps.policy.interpret(state.model_copy(deep=True), step, evidence),
        )
    except POLICY_ERRORS:
        # The answer had the right envelope but the wrong contents. Undo it:
        # something the agent could not read is not evidence.
        state.evidence.pop()
        if step.question_id is not None:
            state.answers[step.question_id].pop()
            if not state.answers[step.question_id]:
                del state.answers[step.question_id]
            state.unanswered_questions.extend(answered)
        state.malformed_results += 1
        state.unproductive_steps += 1
        record(
            state,
            phase,
            "malformed_result",
            information_needed=step.information_needed,
            step=step,
        )
        return None
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
    state.unproductive_steps = 0
    phase_iterations = 0
    while True:
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
            decision = deps.policy.decide(state.model_copy(deep=True), phase)
            if not isinstance(decision, CallTool | Stop):
                raise ValueError("a policy must return CallTool or Stop")
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
