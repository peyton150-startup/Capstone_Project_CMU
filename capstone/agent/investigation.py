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

The stages are steps in a graph. A stage can only be followed by a stage
the graph connects it to, so the sequence cannot be entered half-way or
left by a path that was never drawn.

Every investigation ends with a conclusion. If the policy cannot give a
usable one, this module writes an honest "undetermined" itself.

From `propose` on, the policy makes no calls. Asking, reading the
decision and starting the work are a fixed procedure, so a policy can
neither skip a step nor claim a permission it was not given.
"""

import json
from typing import Literal

from pydantic import JsonValue
from pydantic_graph import GraphBuilder, StepContext

from capstone.agent.artifacts import AgentConclusion, ProposalRecord, TerminationReason
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

# Where a stage sends the investigation next.
Route = Literal["continue", "conclude"]
# Where the proposal stage sends it: on to the work, or to the end.
ActionRoute = Literal["execute", "finish"]

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
    gather(state, deps, "observe", step)
    # That call was made before the tick was known. Note it under the tick
    # it reported too, so asking the time again straight away is a repeat.
    state.seen_calls.append(call_signature(step.request, state.last_tick))


def plan(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Ask the policy what is worth finding out first, and keep its questions open."""
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
    reason = run_inner_loop(state, deps, "investigate")
    state.termination_reason = reason
    if reason is TerminationReason.TIMEOUT or not gathered_in(state, "investigate"):
        return "conclude"
    return "continue"


def hypothesize(state: InvestigationState, deps: InvestigationDeps) -> Route:
    """Ask the policy for explanations. With none to test, go to the conclusion."""
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
    outcome = "decided"
    try:
        conclusion, request = deps.policy.conclude(state.model_copy(deep=True))
        conclusion, request = check_conclusion(state, deps, conclusion, request)
    except POLICY_ERRORS:
        conclusion, request, outcome = UNDETERMINED, None, "invalid_decision"
    state.conclusion = conclusion
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
    gave nothing usable. Either way a record is left.
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
    evidence = gather(state, deps, phase, step, followup=True)
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
        return "finish"
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


def execute(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Start the approved work, then wait until the factory says it is done.

    The action counts as carried out only if the factory confirms it
    started. If that call fails, nothing is waited for.
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
        return
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
            return  # could not wait, or time did not move


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
    async def execute_step(ctx: Context) -> None:
        execute(ctx.state, ctx.deps)

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
                {"execute": execute_step, "finish": builder.end_node},
            )
        ),
        builder.edge_from(execute_step).to(builder.end_node),
    )
    return builder.build()


INVESTIGATION_GRAPH = build_graph()


def run_investigation(
    state: InvestigationState, deps: InvestigationDeps
) -> InvestigationState:
    """Run one investigation from its anomaly to the end of any approved work."""
    INVESTIGATION_GRAPH.run_sync(state=state, deps=deps)
    return state
