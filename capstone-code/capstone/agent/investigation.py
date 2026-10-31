# The outer sequence of one investigation, from the first look to the finished work.
# Responsibility: order the stages and check what the policy hands back at each one.
"""The stages of an investigation, and which stage may follow which.

The inner loop in `loop.py` knows how to take turns. This module decides
what the turns are for:

    observe      ask the factory the time, start the timer
    manual       optionally, search the machine manual on the anomaly's words
    plan         the policy lists what is worth finding out first
    investigate  the inner loop gathers evidence
    hypothesize  the policy proposes explanations for that evidence
    test         the inner loop gathers evidence until one is supported
    critique     an optional second model judges the hypotheses; every path
                 into the conclusion passes through it
    recheck      optionally, one reading the critic pointed at (see `recheck`)
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
    CritiqueRecord,
    ProposalRecord,
    RecheckRecord,
    TerminationReason,
    VerificationCheck,
)
from capstone.agent.critic import shown_hypotheses, verdict_mismatch
from capstone.agent.evidence_brief import verify_numeric_claims
from capstone.agent.loop import (
    POLICY_ERRORS,
    InvestigationDeps,
    OutOfTime,
    apply_interpretation,
    ask_policy,
    call_signature,
    gather,
    notify,
    record,
    run_inner_loop,
)
from capstone.agent.policy import ActionRequest, CallTool, Interpretation, Stop
from capstone.agent.state import InvestigationState, Phase, Question
from capstone.contracts.tools import ToolRequest
from capstone.providers.chat import ModelError
from capstone.providers.factory import research_tools
from capstone.providers.manual import MANUAL_TOOL

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
    # Variables:
    #   step: The get_time call the loop makes itself, not one the policy chose.
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


# How many manual sections the manual step asks for.
MANUAL_STEP_LIMIT = 3


def manual_query(state: InvestigationState) -> str:
    """The words the manual step searches on: what monitoring noticed.

    Only the anomaly is known this early (no hypotheses yet), so its kind and
    description are the query. Both are observations, never the hidden truth.
    """
    # Variables:
    #   kind: The anomaly's kind as words ("vibration_alarm" -> "vibration alarm").
    anomaly = state.anomaly
    kind = anomaly.kind.replace("_", " ")
    return f"{kind}: {anomaly.description}"


def consult_manual(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Search the machine manual once, on the anomaly, before the agent plans.

    Off unless `deps.manual_step` (set only when the run offers a manual).
    The loop makes the call itself, as it does for the time, through the
    normal tool path: the answer becomes evidence labelled `manual` (general
    guidance for the machine model, never a look at the factory now), it
    counts as one of the manual's searches and as a tool call, and the policy
    is not asked to read it here; it sees the sections in every later prompt.
    The `search_manual` tool stays open for the agent's own searches.
    """
    # Variables:
    #   step: The manual search the loop makes itself, not one the policy chose.
    if not deps.manual_step:
        return
    state.stage = "observe"
    step = CallTool(
        information_needed="what the machine manual says about this anomaly",
        request=ToolRequest(
            name=MANUAL_TOOL,
            arguments={"text": manual_query(state), "limit": MANUAL_STEP_LIMIT},
        ),
    )
    gather(state, deps, "observe", step, interpret=False)


def plan(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Ask the policy what is worth finding out first, and keep its questions open."""
    # Variables:
    #   questions: What the policy says is worth finding out first, kept open until
    #     answered.
    state.stage = "plan"
    try:
        questions = tuple(ask_policy(state, deps, deps.policy.plan, research=True))
        if not all(isinstance(q, Question) for q in questions):
            raise ValueError("a plan is a list of questions")
        apply_interpretation(state, Interpretation(new_questions=questions))
    except OutOfTime:
        # Research time is up before it began; the next stage stops on time.
        record(
            state,
            "plan",
            "stopped",
            information_needed="what to find out first",
            termination_reason=TerminationReason.TIMEOUT,
        )
        return
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
    # Variables:
    #   reason: Why the inner loop stopped, also saved as the run's termination reason.
    state.stage = "investigate"
    reason = run_inner_loop(state, deps, "investigate")
    state.termination_reason = reason
    if reason is TerminationReason.TIMEOUT or not gathered_in(state, "investigate"):
        return "conclude"
    return "continue"


def hypothesize(state: InvestigationState, deps: InvestigationDeps) -> Route:
    """Ask the policy for explanations. With none to test, go to the conclusion."""
    # Variables:
    #   outcome: How the question ended: decided, stopped (out of time) or
    #     invalid_decision.
    #   reason: Set only when time ran out, so the record can say why it stopped.
    state.stage = "hypothesize"
    outcome, reason = "decided", None
    try:
        apply_interpretation(
            state, ask_policy(state, deps, deps.policy.hypothesize, research=True)
        )
    except OutOfTime:
        outcome, reason = "stopped", TerminationReason.TIMEOUT
        state.termination_reason = reason
    except POLICY_ERRORS:
        outcome = "invalid_decision"
    record(
        state,
        "hypothesize",
        outcome,
        information_needed="what could explain the evidence",
        termination_reason=reason,
    )
    return "continue" if state.hypotheses else "conclude"


def test(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Gather evidence that tells the explanations apart."""
    state.stage = "test"
    state.termination_reason = run_inner_loop(state, deps, "test")


def critique(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Ask the critic to judge the agent's hypotheses before it concludes.

    Nothing in the run reads the answer. Whatever happens (no answer, an
    unusable reply), the run goes on to the conclusion. The critic has its
    own time window, so the investigation's deadline is moved back by the
    seconds it used: research and the follow-up reserve keep what they had.
    """
    # Variables:
    #   deps.critic: The second reviewer; None means the stage does nothing.
    #   deps.critic_seconds: The critic's own window, separate from the
    #     investigation's deadline.
    #   shown_claims: Each shown hypothesis's claim as worded now, so the record
    #     keeps what the critic judged even if the agent rewords it later.
    #   shown: The ids of the hypotheses the critic is shown, kept in the record.
    #   after_stage: The stage this critique followed, read now, before the
    #     follow-up (`recheck`) sets the stage to test for its own call.
    #   began: The clock when the question started, to measure the critic's time.
    #   outcome: answered, no_answer (no model replied in time) or invalid_reply
    #     (a reply was refused); none of the three stops the run.
    #   result: The critic's reply, or None unless it was answered.
    #   answered_by: The model that gave the reply, read from the critic's own
    #     latest call record; None when no model replied.
    #   deps.critic.last_sections: The manual sections the critic was shown
    #     (Option B), kept on the record; None when the run offered no manual.
    #   used: Seconds the critic took, added to started_at so the investigation's
    #     time left is the same after this stage as before it.
    if deps.critic is None or not state.hypotheses:
        return
    shown_claims = {h.id: h.claim for h in shown_hypotheses(state)}
    shown = tuple(shown_claims)
    after_stage = (
        state.stage if state.stage in ("investigate", "hypothesize", "test") else None
    )
    began = deps.clock()
    outcome = "answered"
    result = None
    try:
        result = deps.critic.review(
            state.model_copy(deep=True), max_seconds=deps.critic_seconds
        )
    except ModelError:
        outcome = "no_answer"
    except POLICY_ERRORS:
        outcome = "invalid_reply"
    used = max(0.0, deps.clock() - began)
    if state.started_at is not None:
        state.started_at += used
    calls = getattr(deps.critic, "calls", None)
    answered_by = calls[-1].answered_by if calls else None
    state.critique = CritiqueRecord(
        outcome=outcome,
        result=result,
        shown_hypotheses=shown,
        seconds=used,
        answered_by=answered_by,
        manual_sections=getattr(deps.critic, "last_sections", None),
        verdict_mismatch=(
            None
            if result is None
            else verdict_mismatch(result, shown[0] if shown else None)
        ),
        favoured_claim=None if result is None else shown_claims.get(result.favoured),
        after_stage=after_stage,
    )


def recheck_trigger(
    state: InvestigationState, deps: InvestigationDeps
) -> tuple[str | None, str | None]:
    """Why the critic follow-up runs (objection or agreement), or why it does not.

    Returns (trigger, None) to run, or (None, reason) to skip. It runs when the
    critic objected, or when it favours the leading hypothesis and names a
    check. Confidence alone never skips that check. The separate critic-call
    allowance must remain; research calls and research time need not remain,
    because the follow-up has its own allowance and window (`recheck`).
    """
    # Variables:
    #   result: The critic's reply, if it gave a usable one.
    #   leading: The agent's best explanation now.
    #   preferred: True when the critic favours another current hypothesis; that
    #     is an objection to the leader even under a "no_objection" verdict.
    critique = state.critique
    result = None if critique is None else critique.result
    if result is None:
        return None, "the critic gave no usable answer"
    leading = state.leading_hypothesis
    if leading is None:
        return None, "no hypothesis to test"
    if not result.discriminating_check.strip():
        return None, "the critic named no check"
    preferred = result.favoured != leading.id and any(
        h.id == result.favoured for h in state.hypotheses
    )
    if result.verdict == "object" or preferred:
        # Favouring another hypothesis is an objection to the leader, whatever
        # the verdict says (a "no_objection" pick of H6 was skipped live).
        trigger = "objection"
    elif result.favoured != leading.id:
        return None, "the critic neither objected nor favoured the leading hypothesis"
    else:
        trigger = "agreement"
    if deps.recheck_seconds <= 0:
        return None, "the follow-up has no time window"
    if state.remaining_critic_tool_calls == 0:
        return None, "no critic diagnostic calls left"
    return trigger, None


def recheck(state: InvestigationState, deps: InvestigationDeps) -> None:
    """One reading the critic pointed at, made by the agent's own policy.

    Off unless `deps.critic_followup`. The critic's check becomes an open
    question tied to a hypothesis. A structured check is executed directly;
    a legacy unstructured check uses one policy decision. At most one
    read-only call is made through the
    normal tool path (so its answer is labelled by its real source), and the
    policy reads it once. Then the run goes on to the conclusion, where the
    action bar applies to the agent's own confidence as before: the critic's
    agreement, confidence and `supports_action` never count there. There is
    no way back to the critic, so this cannot loop.

    It has its own window, `deps.recheck_seconds`, even when research has run
    out of time (live runs of 2026-10-30: every batch and setting case timed
    out, and the follow-up skipped the very check the critic named). The
    seconds it uses are added to `started_at` afterwards, so the conclusion,
    the proposal and the check keep the time they had.
    """
    # Variables:
    #   trigger: objection or agreement, or None when the stage does not run.
    #   reason: Why it did not run, for the record.
    #   began: The clock when the follow-up's window opened.
    #   started: The investigation's real start, restored (moved by the seconds
    #     used) when the window closes.
    if not deps.critic_followup or deps.critic is None or state.critique is None:
        return
    state.stage = "test"
    trigger, reason = recheck_trigger(state, deps)
    if trigger is None:
        state.recheck = RecheckRecord(outcome="skipped", reason=reason)
        return
    began = deps.clock()
    started = state.started_at
    if started is not None:
        # Open the window: research time left is now exactly recheck_seconds.
        budgets = state.budgets
        state.started_at = began - (
            budgets.timeout_seconds - budgets.followup_seconds - deps.recheck_seconds
        )
    try:
        follow_up(state, deps, trigger)
    finally:
        if started is not None:
            # Close it: the deadline moves by the seconds used, so the time
            # left afterwards is what it was before the follow-up began.
            state.started_at = started + max(0.0, deps.clock() - began)


def follow_up(state: InvestigationState, deps: InvestigationDeps, trigger: str) -> None:
    """The follow-up itself: one question, at most one call, one reading."""
    # Variables:
    #   trigger: objection or agreement, why the follow-up runs.
    #   leading: The agent's best explanation before the reading.
    #   favoured: The hypothesis the critic picked; the question tests it when it
    #     is not the leader.
    #   target, text: The hypothesis the question tests, and its wording.
    #   question: The critic's check as an open question for the policy.
    #   summary: What every record of a run that went ahead shares.
    #   decision: The policy's one choice: a tool call or a stop.
    #   evidence: The reading, or None if the call gave nothing usable.
    #   after: The agent's best explanation after reading the answer.
    #   structured: The critic's typed request, executed without a policy veto.
    #   allowed: Existing read-only research tools; excludes time advancement/actions.
    #   previous: An exact check already observed at this tick; safe to reuse.
    #   observable: IDs assigned observable provenance by the loop, not the policy.
    leading = state.leading_hypothesis
    check = state.critique.result.discriminating_check.strip()
    favoured = state.critique.result.favoured
    # The critic sees every hypothesis, so its check may be meant to separate
    # another one (its pick) from the leader: then the question tests its pick.
    if favoured != leading.id and any(h.id == favoured for h in state.hypotheses):
        target = favoured
        text = (
            f"The critic's check, to tell {favoured} (the critic's pick) from "
            f"{leading.id} (the agent's leading explanation): {check}"
        )
    else:
        target, text = leading.id, f"The critic's check: {check}"
    question = Question(id="K1", text=text, hypothesis_id=target)
    state.unanswered_questions.append(question)
    summary = {
        "trigger": trigger,
        "question": question.text,
        "leading_before": leading.id,
        "confidence_before": leading.confidence,
    }
    need = "the reading the critic's check names"
    try:
        structured = state.critique.result.check_request
        decision = (
            CallTool(
                information_needed=need,
                request=structured,
                question_id="K1",
                hypothesis_id=target,
            )
            if structured is not None
            else ask_policy(
                state,
                deps,
                lambda view: deps.policy.decide(view, "test"),
                research=True,
            )
        )
        if not isinstance(decision, CallTool | Stop):
            raise ValueError("a policy must return CallTool or Stop")
    except OutOfTime:
        record(state, "test", "stopped", information_needed=need)
        state.recheck = RecheckRecord(outcome="out_of_time", **summary)
        return
    except POLICY_ERRORS:
        record(state, "test", "invalid_decision", information_needed=need)
        state.recheck = RecheckRecord(outcome="invalid_decision", **summary)
        return
    if isinstance(decision, Stop):
        record(state, "test", "stopped", information_needed=decision.information_needed)
        observable = {
            p.evidence_id for p in state.provenance if p.origin == "observable"
        }
        answered = decision.answered_evidence_ids
        if answered and observable.issuperset(answered):
            state.unanswered_questions = [
                q for q in state.unanswered_questions if q.id != "K1"
            ]
            state.answers["K1"] = list(answered)
            state.recheck = RecheckRecord(
                outcome="already_answered",
                evidence_id=answered[0],
                reason="Policy cites existing observations answering the critic check; semantic adequacy is unverified.",
                **summary,
            )
            return
        state.recheck = RecheckRecord(
            outcome="policy_stopped", reason=decision.information_needed, **summary
        )
        return
    allowed = {tool.name for tool in research_tools()} - {"wait"}
    if decision.request.name not in allowed:
        state.recheck = RecheckRecord(
            outcome="invalid_decision",
            reason="critic checks must use an observable read-only factory tool",
            **summary,
        )
        return
    observable = {p.evidence_id for p in state.provenance if p.origin == "observable"}
    previous = next(
        (
            d
            for d in reversed(state.decisions)
            if d.tool == decision.request.name
            and d.arguments == decision.request.arguments
            and d.tick == state.last_tick
            and d.evidence_ids
            and observable.issuperset(d.evidence_ids)
        ),
        None,
    )
    if previous is not None:
        state.unanswered_questions = [
            q for q in state.unanswered_questions if q.id != "K1"
        ]
        state.answers["K1"] = list(previous.evidence_ids)
        state.recheck = RecheckRecord(
            outcome="already_answered",
            tool=decision.request.name,
            evidence_id=previous.evidence_ids[0],
            reason="This exact check already returned observable evidence at the current tick.",
            **summary,
        )
        return
    evidence = gather(state, deps, "test", decision, critic_check=True)
    after = state.leading_hypothesis
    state.recheck = RecheckRecord(
        outcome="no_evidence" if evidence is None else "observed",
        tool=decision.request.name,
        evidence_id=None if evidence is None else evidence.id,
        leading_after=None if after is None else after.id,
        confidence_after=None if after is None else after.confidence,
        **summary,
    )


def why_not_acted(
    deps: InvestigationDeps,
    conclusion: AgentConclusion,
    request: ActionRequest | None,
) -> str | None:
    """Why a recommendation to intervene cannot stand, or None if it can.

    The first unmet condition, in words, for the record: an action is
    named, evidence is cited, and the confidence reaches the bar.
    """
    # Variables:
    #   request: The action the model asked for, or None if it named no action.
    if request is None:
        return "no action named"
    if not conclusion.evidence_ids:
        return "no evidence cited"
    if conclusion.confidence < deps.min_action_confidence:
        return (
            f"confidence {conclusion.confidence:.2f} below "
            f"{deps.min_action_confidence:.2f}"
        )
    return None


def check_conclusion(
    state: InvestigationState,
    deps: InvestigationDeps,
    conclusion: AgentConclusion,
    request: ActionRequest | None,
) -> tuple[AgentConclusion, ActionRequest | None]:
    """Check references, arithmetic and declared completion without proving a cause.

    Raises ValueError for a conclusion that cites evidence which was
    never gathered or a hypothesis which was never formed. A
    recommendation to intervene that is not confident enough, cites
    nothing, or names no action is lowered to "escalate": a human
    should look, but the agent may not ask for a change.
    """
    # Variables:
    #   conclusion: The policy's raw answer, before this check can lower it.
    #   request: The action the policy asked for with that answer, if any.
    #   known_hypotheses: Ids of the explanations the agent actually formed.
    #   unverified: Structured arithmetic that observable data cannot establish.
    #   gaps: Declared/open diagnostic questions and explicit conflicts, kept for review.
    #   selected: The explanation claimed by the conclusion, if one was named.
    #   observed: Only current-factory evidence can support a declared completion.
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
    unverified = verify_numeric_claims(state, conclusion.numeric_claims)
    if conclusion.assessment is not None:
        current = {h.id for h in state.hypotheses}
        gaps = list(conclusion.unresolved_questions)
        observed = {p.evidence_id for p in state.provenance if p.origin == "observable"}
        if not observed.intersection(conclusion.evidence_ids):
            gaps.append("No current observable evidence was cited for this diagnosis.")
        gaps.extend(
            q.text for q in state.unanswered_questions if q.hypothesis_id in current
        )
        selected = next(
            (h for h in state.hypotheses if h.id == conclusion.hypothesis_id), None
        )
        if selected and (
            selected.contradicting_evidence_ids or selected.unexplained_evidence_ids
        ):
            gaps.append(
                "The selected hypothesis still has conflicting or unexplained evidence."
            )
        gaps.extend(unverified)
        if gaps or conclusion.assessment == "unresolved":
            conclusion = conclusion.model_copy(
                update={
                    "assessment": "unresolved",
                    "recommendation": "escalate",
                    "unresolved_questions": tuple(dict.fromkeys(gaps)),
                    "next_check": conclusion.next_check
                    or (
                        gaps[0] if gaps else "Gather evidence to resolve the diagnosis."
                    ),
                }
            )
    if conclusion.recommendation != "intervene":
        return conclusion, None
    if why_not_acted(deps, conclusion, request) is not None:
        return conclusion.model_copy(update={"recommendation": "escalate"}), None
    return conclusion, request


def conclude(state: InvestigationState, deps: InvestigationDeps) -> None:
    """Record the final belief. Always leaves a conclusion, even a failed one."""
    # Variables:
    #   outcome: How the question ended: decided, stopped or invalid_decision.
    #   answer: The model's raw conclusion, before the check.
    #   wanted: The action the model asked for with that answer, before the check.
    #   conclusion: What survived the check; this is what the agent now believes.
    #   request: The action that survived the check, or None if it was lowered or never
    #     named.
    state.stage = "decide"
    outcome = "decided"
    try:
        answer, wanted = ask_policy(state, deps, deps.policy.conclude, research=False)
        conclusion, request = check_conclusion(state, deps, answer, wanted)
        # For the record only; nothing below changes what the agent does.
        # `answer, wanted` is the model's raw reply; `conclusion, request` is
        # what survived check_conclusion.
        #
        # "Lowered" means the model recommended "intervene" but the check
        # turned it into "escalate" (no action named, no evidence cited, or
        # confidence below MIN_ACTION_CONFIDENCE), so no fix is proposed.
        #
        # Reading a record whose final recommendation is "escalate":
        #   policy_recommendation="escalate", lowered=None -> the model chose it
        #   policy_recommendation="intervene", lowered=<why> -> the check lowered it
        #   policy_recommendation=None -> these lines never ran: time ran out or
        #     the reply was unusable, and UNDETERMINED (escalate) was used
        #
        # The reason uses the raw `answer, wanted`: after the check `request`
        # is always None, so the checked pair would always say "no action named".
        state.policy_recommendation = answer.recommendation
        if answer.recommendation == "intervene" and request is None:
            state.recommendation_lowered = (
                "investigation unresolved: "
                + "; ".join(conclusion.unresolved_questions)
                if conclusion.assessment == "unresolved"
                else why_not_acted(deps, answer, wanted)
            )
    except OutOfTime:
        conclusion, request, outcome = UNDETERMINED, None, "stopped"
        state.termination_reason = TerminationReason.TIMEOUT
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
    # Variables:
    #   out_of_time: True when the whole investigation's time is spent.
    #   reason: Why no call was made: out of time, or no follow-up calls left.
    #   step: The call as the loop's own CallTool, with no policy involved.
    #   evidence: The new evidence from the call, or None if it gave nothing usable.
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
    # Variables:
    #   wanted: The action the conclusion asked for, saved earlier as not_submitted.
    #   answer: The factory's reply to propose_action, which carries the proposal id.
    #   submitted: The proposal as the factory now holds it, with its id and pending
    #     status.
    #   proposals: The factory's list of proposals, read back to see the human's
    #     decision.
    #   mine: This investigation's own proposal row, or {} if the factory did not list
    #     it.
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
        notify(state, deps)  # the watcher sees the proposal before the human decides
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
    # Variables:
    #   started: The factory's reply to execute_action, holding the start and finish
    #     ticks.
    #   ticks: Same reply, or {} if it was not a dict.
    #   start: The tick the work began at; must be a real int.
    #   finish: The tick the work will end at; the wait loop runs until this tick.
    #   before: The tick before this wait, to check that time actually moved.
    #   waited: The factory's reply to wait, or None if the call failed.
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
    evidence labelled observable counts as observed: never a memory or the
    machine manual. Without
    it the result is "inconclusive"; with nothing looked at, "not performed".

    The prediction is the one recorded before the action and the tick is
    taken from the evidence, so neither can be adjusted afterwards.
    """
    # Variables:
    #   since: The tick after which a look counts: when the work finished, or the
    #     conclusion if no work was done.
    #   prediction: What the agent said would happen, recorded before the action so it
    #     cannot be edited later.
    #   known: Every piece of evidence by id.
    #   origins: Where each piece of evidence came from (observable, memory or manual).
    #   starts: The from_tick each look asked for, read from the loop's records, never
    #     from the policy.
    #   looked: Ids of looks that count as observed after the work.
    #   step_outcome: How the judging question ended: decided, stopped or
    #     invalid_decision.
    #   cited: The evidence ids the policy's judgement relied on.
    #   outcome: The verdict that stands; inconclusive unless supported by a later look.
    #   judged: The policy's own verification verdict, before this function decides if
    #     it can stand.
    #   supported: True if at least one cited look is later than the work.
    #   decisive: True if the policy said resolved or not_resolved rather than
    #     inconclusive.
    #   after: The cited looks that count, or all the counting looks if none were cited.
    state.stage = "verify"
    since = (
        state.action_finish_tick if state.action_carried_out else state.concluded_tick
    )
    prediction = state.predicted_effect or NO_PREDICTION
    run_inner_loop(state, deps, "verify")

    def later(evidence_id: str) -> bool:
        """A look at the factory after `since`, at data from after `since`.

        A recalled memory never is one: it is stamped with the tick it was
        recalled, but it describes the past. Nor is a manual section: it is
        stamped with the tick it was read, but it describes the machine type,
        not this factory now. Nor is a look made late at a
        tick range that starts at or before `since`: its data is from before
        the work, so it says nothing about the work. A tool with no range
        reports the factory as it is when asked.
        """
        # Variables:
        #   tick: The tick the evidence was observed at.
        #   observed: True only for answers that came from the factory, never memory or
        #     the manual.
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
        judged = ask_policy(state, deps, deps.policy.judge_verification, research=False)
        if not isinstance(judged, VerificationCheck):
            raise ValueError("a policy must return a verification check")
        if not known.keys() >= set(judged.evidence_ids):
            raise ValueError("the check cites evidence that was not gathered")
    except OutOfTime:
        # No judgement in time: the evidence was looked at but not weighed.
        step_outcome = "stopped"
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
    # Variables:
    #   Context: The type every stage receives: the state, the deps, and no extra data.
    #   builder: Collects the stages (nodes) and edges; the edges are the only allowed
    #     order.
    Context = StepContext[InvestigationState, InvestigationDeps, object]

    def staged(stage, ctx: Context):
        """Run one stage, then show the watcher (if any) where it left things."""
        # Variables:
        #   result: What the stage returned, passed on as the route to the next stage.
        result = stage(ctx.state, ctx.deps)
        notify(ctx.state, ctx.deps)
        return result

    builder = GraphBuilder(
        name="investigation",
        state_type=InvestigationState,
        deps_type=InvestigationDeps,
        auto_instrument=False,
    )

    @builder.step(node_id="observe")
    async def observe_step(ctx: Context) -> None:
        return staged(observe, ctx)

    @builder.step(node_id="manual")
    async def manual_step(ctx: Context) -> None:
        return staged(consult_manual, ctx)

    @builder.step(node_id="plan")
    async def plan_step(ctx: Context) -> None:
        return staged(plan, ctx)

    @builder.step(node_id="investigate")
    async def investigate_step(ctx: Context) -> Route:
        return staged(investigate, ctx)

    @builder.step(node_id="hypothesize")
    async def hypothesize_step(ctx: Context) -> Route:
        return staged(hypothesize, ctx)

    @builder.step(node_id="test")
    async def test_step(ctx: Context) -> None:
        return staged(test, ctx)

    @builder.step(node_id="critique")
    async def critique_step(ctx: Context) -> None:
        return staged(critique, ctx)

    @builder.step(node_id="recheck")
    async def recheck_step(ctx: Context) -> None:
        return staged(recheck, ctx)

    @builder.step(node_id="conclude")
    async def conclude_step(ctx: Context) -> None:
        return staged(conclude, ctx)

    @builder.step(node_id="propose")
    async def propose_step(ctx: Context) -> ActionRoute:
        return staged(propose, ctx)

    @builder.step(node_id="execute")
    async def execute_step(ctx: Context) -> ActionRoute:
        return staged(execute, ctx)

    @builder.step(node_id="verify")
    async def verify_step(ctx: Context) -> None:
        return staged(verify, ctx)

    def choose(node_id: str, destinations: dict):
        """A fork: each value a stage can return, and the stage it leads to."""
        # Variables:
        #   destinations: Maps each value a stage can return to the stage that follows
        #     it.
        decision = builder.decision(node_id=node_id)
        for value, destination in destinations.items():
            decision = decision.branch(
                builder.match(str, matches=lambda r, value=value: r == value).to(
                    destination
                )
            )
        return decision

    def route(node_id: str, onward):
        """Send "continue" onward and "conclude" to the critique, which every
        path into the conclusion passes through (it does nothing without a
        critic or a hypothesis)."""
        return choose(node_id, {"continue": onward, "conclude": critique_step})

    builder.add(
        builder.edge_from(builder.start_node).to(observe_step),
        builder.edge_from(observe_step).to(manual_step),
        builder.edge_from(manual_step).to(plan_step),
        builder.edge_from(plan_step).to(investigate_step),
        builder.edge_from(investigate_step).to(
            route("anything_to_explain", hypothesize_step)
        ),
        builder.edge_from(hypothesize_step).to(route("anything_to_test", test_step)),
        builder.edge_from(test_step).to(critique_step),
        builder.edge_from(critique_step).to(recheck_step),
        builder.edge_from(recheck_step).to(conclude_step),
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
        notify(state, deps)  # the stop record, which no stage was left to show
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
