# The outer sequence of one investigation, from the first look to the finished work.
# Responsibility: order the stages and check what the policy hands back at each one.
"""The stages of an investigation, and which stage may follow which.

The inner loop in `loop.py` knows how to take turns. This module decides
what the turns are for:

    observe      ask the factory the time, start the timer
    plan         the policy lists what is worth finding out first
    investigate  the inner loop gathers evidence
    hypothesize  the policy proposes explanations for that evidence
    test         the inner loop gathers evidence until one is supported
    conclude     the policy states a diagnosis; this module checks it
    propose      ask a human for the change, then read their decision back
    execute      start the approved work and wait for it to finish
    verify       look again and judge whether the problem went away

The stages are steps in a graph. A stage can only be followed by a stage
the graph connects it to, so the sequence cannot be entered half-way or
left by a path that was never drawn.

Every investigation ends with a conclusion. If the policy cannot give a
usable one, this module writes an honest "undetermined" itself.

From `propose` on, the policy makes no calls. Asking, reading the
decision and starting the work are a fixed procedure, so a policy can
neither skip a step nor claim a permission it was not given. Nor is it
asked to interpret the answers to calls the loop makes itself (the time,
the proposal, the work): with a model behind the policy, that would be a
model request spent on nothing it chose.
"""

import json
from typing import Literal

from pydantic import JsonValue
from pydantic_graph import GraphBuilder, StepContext

from capstone.agent.artifacts import (
    AgentConclusion,
    ProposalRecord,
    TerminationReason,
    VerificationCheck,
)
from capstone.agent.loop import (
    POLICY_ERRORS,
    InvestigationDeps,
    apply_interpretation,
    call_signature,
    gather,
    record,
    run_inner_loop,
)
from capstone.agent.policy import ActionRequest, CallTool, Interpretation
from capstone.agent.state import InvestigationState, Phase, Question
from capstone.contracts.tools import ToolRequest
from capstone.providers.chat import ModelError

# Where a stage sends the investigation next.
Route = Literal["continue", "conclude"]
# Where the later stages send it: on to the work, to the check, or to the end.
ActionRoute = Literal["execute", "verify", "finish"]

# What is expected when the conclusion is that nothing needs doing.
NO_ACTION_PREDICTION = "the symptoms clear without any change to the factory"
NO_PREDICTION = "no prediction was recorded"

UNDETERMINED = AgentConclusion(
    diagnosis="undetermined", confidence=0.0, recommendation="escalate"
)


def gathered_in(state: InvestigationState, phase: Phase) -> int:
    """How many pieces of evidence a stage added."""
    return sum(len(d.evidence_ids) for d in state.decisions if d.phase == phase)


def observe(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Start the timer and learn the current tick before anything else is asked.

    The repeat check compares "same question, same tick", so the tick
    has to be known before the policy asks its first question.
    """
    if state.started_at is None:
        state.started_at = deps.clock()
    step = CallTool(
        information_needed="the current factory time",
        request=ToolRequest(name="get_time"),
    )
    gather(state, deps, "observe", step, interpret=False)
    # That call was made before the tick was known. Note it under the tick
    # it reported too, so asking the time again straight away is a repeat.
    state.seen_calls.append(call_signature(step.request, state.last_tick))


def plan(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Ask the policy what is worth finding out first, and keep its questions open."""
    state.stage = "plan"
    try:
        questions = tuple(deps.policy.plan(state.model_copy(deep=True)))
        if not all(isinstance(q, Question) for q in questions):
            raise ValueError("a plan is a list of questions")
        apply_interpretation(state, Interpretation(new_questions=questions))
    except POLICY_ERRORS:
        # No plan is not fatal: the policy can still choose its next step.
        record(
            state,
            "plan",
            "invalid_decision",
            information_needed="what to find out first",
        )
        return
    record(state, "plan", "decided", information_needed="what to find out first")


def investigate(state: InvestigationState, deps: InvestigationDeps) -> Route:
    """Gather evidence. Go straight to the conclusion if there is nothing to explain."""
    state.stage = "investigate"
    reason = run_inner_loop(state, deps, "investigate")
    state.termination_reason = reason
    if reason is TerminationReason.TIMEOUT or not gathered_in(state, "investigate"):
        return "conclude"
    return "continue"


def hypothesize(state: InvestigationState, deps: InvestigationDeps) -> Route:
    """Ask the policy for explanations. With none to test, go to the conclusion."""
    state.stage = "hypothesize"
    outcome = "decided"
    try:
        apply_interpretation(
            state, deps.policy.hypothesize(state.model_copy(deep=True))
        )
    except POLICY_ERRORS:
        outcome = "invalid_decision"
    record(
        state,
        "hypothesize",
        outcome,
        information_needed="what could explain the evidence",
    )
    return "continue" if state.hypotheses else "conclude"


def test(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Gather evidence that tells the explanations apart."""
    state.stage = "test"
    state.termination_reason = run_inner_loop(state, deps, "test")


def check_conclusion(
    state: InvestigationState,
    deps: InvestigationDeps,
    conclusion: AgentConclusion,
    request: ActionRequest | None,
) -> tuple[AgentConclusion, ActionRequest | None]:
    """Accept a conclusion only if it points at things that exist.

    Raises ValueError for a conclusion that cites evidence which was
    never gathered or a hypothesis which was never formed. A
    recommendation to intervene that is not confident enough, cites
    nothing, or names no action is lowered to "escalate": a human
    should look, but the agent may not ask for a change.
    """
    if not isinstance(conclusion, AgentConclusion):
        raise ValueError("a policy must return a conclusion")
    if request is not None and not isinstance(request, ActionRequest):
        raise ValueError("an action must be an ActionRequest")
    if not {e.id for e in state.evidence}.issuperset(conclusion.evidence_ids):
        raise ValueError("the conclusion cites evidence that was not gathered")
    known_hypotheses = {h.id for h in state.hypotheses}
    if (
        conclusion.hypothesis_id is not None
        and conclusion.hypothesis_id not in known_hypotheses
    ):
        raise ValueError("the conclusion names a hypothesis that was never formed")
    if conclusion.recommendation != "intervene":
        return conclusion, None
    justified = (
        request is not None
        and conclusion.evidence_ids
        and conclusion.confidence >= deps.min_action_confidence
    )
    if not justified:
        return conclusion.model_copy(update={"recommendation": "escalate"}), None
    return conclusion, request


def conclude(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Record the final belief. Always leaves a conclusion, even a failed one."""
    state.stage = "decide"
    outcome = "decided"
    try:
        conclusion, request = deps.policy.conclude(state.model_copy(deep=True))
        conclusion, request = check_conclusion(state, deps, conclusion, request)
    except POLICY_ERRORS:
        conclusion, request, outcome = UNDETERMINED, None, "invalid_decision"
    state.conclusion = conclusion
    state.concluded_tick = state.last_tick
    if conclusion.recommendation == "no_action":
        state.predicted_effect = NO_ACTION_PREDICTION
    if request is not None:
        # Wanted, not yet asked for. The propose stage submits it.
        state.proposed_action = ProposalRecord(
            machine_id=request.machine_id,
            action=request.action,
            reason=request.reason,
            status="not_submitted",
        )
        state.predicted_effect = request.prediction
    record(
        state,
        "decide",
        outcome,
        information_needed="the diagnosis and what to do about it",
        evidence_ids=conclusion.evidence_ids,
        termination_reason=state.termination_reason,
    )


def followup_call(
    state: InvestigationState,
    deps: InvestigationDeps,
    phase: Phase,
    tool: str,
    information_needed: str,
    **arguments,
) -> JsonValue | None:
    """Make one call the loop itself decided on, from the follow-up allowance.

    Returns the tool's answer, or None if the call could not be made or
    gave nothing usable. Either way a record is left. The loop reads the
    answer itself; the policy is not asked to interpret it.
    """
    out_of_time = state.remaining_seconds(deps.clock()) <= 0
    if out_of_time or state.remaining_followup_tool_calls == 0:
        reason = (
            TerminationReason.TIMEOUT
            if out_of_time
            else TerminationReason.MAX_TOOL_CALLS
        )
        record(
            state,
            phase,
            "stopped",
            information_needed=information_needed,
            termination_reason=reason,
        )
        return None
    step = CallTool(
        information_needed=information_needed,
        request=ToolRequest(name=tool, arguments=arguments),
    )
    evidence = gather(state, deps, phase, step, followup=True, interpret=False)
    return None if evidence is None else json.loads(evidence.content)


def factory_changed(state: InvestigationState) -> None:
    """Forget which questions were asked: the answers may no longer be the same.

    The repeat check assumes nothing changes unless time passes. A
    proposal, a human's decision and the start of a repair all change
    what the factory would answer without the clock moving.
    """
    state.seen_calls.clear()


def propose(state: InvestigationState, deps: InvestigationDeps) -> ActionRoute:
    """Ask a human for the change, let them decide, and read their decision back.

    The policy takes no part: it said what it wanted in its conclusion.
    The decision is whatever the factory reports for this proposal, never
    what the agent assumes.
    """
    wanted = state.proposed_action
    if wanted is None:
        # Doing nothing is also a claim that can be checked later.
        nothing_needed = state.conclusion.recommendation == "no_action"
        return "verify" if nothing_needed else "finish"
    answer = followup_call(
        state,
        deps,
        "propose",
        "propose_action",
        "a human's permission for the action",
        machine_id=wanted.machine_id,
        action=wanted.action,
        reason=wanted.reason,
    )
    factory_changed(state)
    try:
        submitted = wanted.model_copy(update={"status": "pending"})
        submitted = ProposalRecord.model_validate(
            {**submitted.model_dump(), "proposal_id": answer["id"]}, strict=True
        )
    except POLICY_ERRORS:
        return "finish"  # the factory did not take the proposal
    state.proposed_action = submitted
    if deps.human_review is not None:
        deps.human_review(submitted)
        factory_changed(state)
    proposals = followup_call(
        state, deps, "propose", "get_proposals", "the human's decision on the proposal"
    )
    rows = proposals if isinstance(proposals, list) else []
    mine = next(
        (
            row
            for row in rows
            if isinstance(row, dict) and row.get("id") == submitted.proposal_id
        ),
        {},
    )
    if mine.get("status") in ("approved", "rejected"):
        state.proposed_action = submitted.model_copy(update={"status": mine["status"]})
    return "execute" if state.proposed_action.status == "approved" else "finish"


def execute(state: InvestigationState, deps: InvestigationDeps) -> ActionRoute:
    """Start the approved work, then wait until the factory says it is done.

    The action counts as carried out only if the factory confirms it
    started. If that call fails, nothing is waited for. The work is
    checked only once it has finished.
    """
    started = followup_call(
        state,
        deps,
        "execute",
        "execute_action",
        "start the approved work",
        proposal_id=state.proposed_action.proposal_id,
    )
    factory_changed(state)
    ticks = started if isinstance(started, dict) else {}
    start, finish = ticks.get("started_tick"), ticks.get("finish_tick")
    if type(start) is not int or type(finish) is not int:
        return "finish"
    state.action_started_tick, state.action_finish_tick = start, finish
    while state.last_tick is not None and state.last_tick < finish:
        before = state.last_tick
        waited = followup_call(
            state,
            deps,
            "execute",
            "wait",
            "the work to finish",
            ticks=min(finish - before, deps.max_wait_ticks),
        )
        if waited is None or state.last_tick <= before:
            return "finish"  # could not wait, or time did not move
    return "verify"


def verify(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Look again after the work, or after doing nothing, and record what was found.

    Nothing tells the agent whether a fix worked. The policy chooses what
    to look at and judges it; this function decides whether that judgement
    can stand. "Resolved" and "not resolved" need evidence observed after
    the work finished (or, with no action, after the conclusion), whose data
    also starts after it, and only
    evidence labelled observable counts as observed: never a memory. Without
    it the result is "inconclusive"; with nothing looked at, "not performed".

    The prediction is the one recorded before the action and the tick is
    taken from the evidence, so neither can be adjusted afterwards.
    """
    state.stage = "verify"
    since = (
        state.action_finish_tick if state.action_carried_out else state.concluded_tick
    )
    prediction = state.predicted_effect or NO_PREDICTION
    run_inner_loop(state, deps, "verify")

    def later(evidence_id: str) -> bool:
        """A look at the factory after `since`, at data from after `since`.

        A recalled memory never is one: it is stamped with the tick it was
        recalled, but it describes the past. Nor is a look made late at a
        tick range that starts at or before `since`: its data is from before
        the work, so it says nothing about the work. A tool with no range
        reports the factory as it is when asked.
        """
        tick = known[evidence_id].observed_tick
        observed = origins.get(evidence_id) == "observable"
        if not observed or since is None or tick is None:
            return False
        return tick > since and starts.get(evidence_id, tick) > since

    known = {e.id: e for e in state.evidence}
    origins = {p.evidence_id: p.origin for p in state.provenance}
    # Where each answer's data begins: the from_tick its request asked for,
    # taken from the loop's own decision records, never from the policy.
    starts = {
        evidence_id: decision.arguments["from_tick"]
        for decision in state.decisions
        if isinstance(decision.arguments.get("from_tick"), int)
        for evidence_id in decision.evidence_ids
    }
    looked = [evidence_id for evidence_id in known if later(evidence_id)]
    if not looked:
        state.verification = VerificationCheck(
            outcome="not_performed", prediction=prediction
        )
        record(
            state,
            "verify",
            "stopped",
            information_needed="whether the factory changed as predicted",
        )
        return

    step_outcome, cited, outcome = "decided", (), "inconclusive"
    try:
        judged = deps.policy.judge_verification(state.model_copy(deep=True))
        if not isinstance(judged, VerificationCheck):
            raise ValueError("a policy must return a verification check")
        if not known.keys() >= set(judged.evidence_ids):
            raise ValueError("the check cites evidence that was not gathered")
    except POLICY_ERRORS:
        step_outcome = "invalid_decision"
    else:
        cited = judged.evidence_ids
        supported = any(later(evidence_id) for evidence_id in cited)
        decisive = judged.outcome in ("resolved", "not_resolved")
        outcome = judged.outcome if decisive and supported else "inconclusive"
    after = [evidence_id for evidence_id in cited if later(evidence_id)] or looked
    state.verification = VerificationCheck(
        outcome=outcome,
        prediction=prediction,
        evidence_ids=cited,
        checked_tick=max(known[evidence_id].observed_tick for evidence_id in after),
    )
    record(
        state,
        "verify",
        step_outcome,
        information_needed="whether the factory changed as predicted",
        evidence_ids=cited,
    )


def build_graph():
    """Wire the stages together. The edges are the only allowed order."""
    Context = StepContext[InvestigationState, InvestigationDeps, object]
    builder = GraphBuilder(
        name="investigation",
        state_type=InvestigationState,
        deps_type=InvestigationDeps,
        auto_instrument=False,
    )

    @builder.step(node_id="observe")
    async def observe_step(ctx: Context) -> None:
        observe(ctx.state, ctx.deps)

    @builder.step(node_id="plan")
    async def plan_step(ctx: Context) -> None:
        plan(ctx.state, ctx.deps)

    @builder.step(node_id="investigate")
    async def investigate_step(ctx: Context) -> Route:
        return investigate(ctx.state, ctx.deps)

    @builder.step(node_id="hypothesize")
    async def hypothesize_step(ctx: Context) -> Route:
        return hypothesize(ctx.state, ctx.deps)

    @builder.step(node_id="test")
    async def test_step(ctx: Context) -> None:
        test(ctx.state, ctx.deps)

    @builder.step(node_id="conclude")
    async def conclude_step(ctx: Context) -> None:
        conclude(ctx.state, ctx.deps)

    @builder.step(node_id="propose")
    async def propose_step(ctx: Context) -> ActionRoute:
        return propose(ctx.state, ctx.deps)

    @builder.step(node_id="execute")
    async def execute_step(ctx: Context) -> ActionRoute:
        return execute(ctx.state, ctx.deps)

    @builder.step(node_id="verify")
    async def verify_step(ctx: Context) -> None:
        verify(ctx.state, ctx.deps)

    def choose(node_id: str, destinations: dict):
        """A fork: each value a stage can return, and the stage it leads to."""
        decision = builder.decision(node_id=node_id)
        for value, destination in destinations.items():
            decision = decision.branch(
                builder.match(str, matches=lambda r, value=value: r == value).to(
                    destination
                )
            )
        return decision

    def route(node_id: str, onward):
        """Send "continue" onward and "conclude" to the conclusion."""
        return choose(node_id, {"continue": onward, "conclude": conclude_step})

    builder.add(
        builder.edge_from(builder.start_node).to(observe_step),
        builder.edge_from(observe_step).to(plan_step),
        builder.edge_from(plan_step).to(investigate_step),
        builder.edge_from(investigate_step).to(
            route("anything_to_explain", hypothesize_step)
        ),
        builder.edge_from(hypothesize_step).to(route("anything_to_test", test_step)),
        builder.edge_from(test_step).to(conclude_step),
        builder.edge_from(conclude_step).to(propose_step),
        builder.edge_from(propose_step).to(
            choose(
                "approved",
                {
                    "execute": execute_step,
                    "verify": verify_step,
                    "finish": builder.end_node,
                },
            )
        ),
        builder.edge_from(execute_step).to(
            choose(
                "work_finished",
                {"verify": verify_step, "finish": builder.end_node},
            )
        ),
        builder.edge_from(verify_step).to(builder.end_node),
    )
    return builder.build()


INVESTIGATION_GRAPH = build_graph()


def run_investigation(
    state: InvestigationState, deps: InvestigationDeps
) -> InvestigationState:
    """Run one investigation from its anomaly to the check of what was done."""
    try:
        INVESTIGATION_GRAPH.run_sync(state=state, deps=deps)
    except ModelError:
        stop_without_a_model(state)
    return state


def stop_without_a_model(state: InvestigationState) -> None:
    """End the run where no model service answered, after retries and fallback.

    This is not the agent reasoning badly, so it is neither an invalid
    decision nor an unproductive turn: it gets its own stop reason, and the
    stage it cut short. A conclusion already reached is kept; otherwise
    the honest one is "undetermined".
    """
    state.termination_reason = TerminationReason.MODEL_UNAVAILABLE
    if state.conclusion is None:
        state.conclusion = UNDETERMINED
    record(
        state,
        state.stage or "observe",
        "stopped",
        information_needed="a model service that answers",
        termination_reason=TerminationReason.MODEL_UNAVAILABLE,
    )
