from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from capstone.agent.artifacts import TerminationReason
from capstone.agent.loop import (
    InvestigationDeps,
    diagnosis_supported,
    run_inner_loop,
)
from capstone.agent.policy import Interpretation, Stop
from capstone.agent.state import Budgets, Question
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.tools import ToolResult
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.helpers import (
    INVESTIGATION,
    RUN,
    START,
    FakeProvider,
    ScriptedPolicy,
    ask,
    new_state,
)

HIDDEN_WORDS = ("bearing_health", "defect_risk", "standard_speed", "ground_truth")


def run(decisions, *, respond=None, interpret=None, phase="investigate", state=None):
    state = state or new_state()
    provider = FakeProvider(respond)
    policy = ScriptedPolicy(decisions, interpret)
    deps = InvestigationDeps(provider=provider, policy=policy, clock=lambda: 0.0)
    reason = run_inner_loop(state, deps, phase)
    return state, provider, policy, reason


def worn(confidence, *supporting):
    return Hypothesis(
        id="H1",
        claim="the machine is wearing",
        confidence=confidence,
        supporting_evidence_ids=supporting,
    )


# --- a usable answer becomes evidence -------------------------------------


def test_a_usable_answer_becomes_numbered_evidence_with_its_source_and_tick():
    state, _, _, reason = run([ask("get_events", from_tick=0, to_tick=10)])
    [evidence] = state.evidence
    assert evidence.id == "E1"
    assert evidence.source_id == "fake:get_events"
    assert evidence.source_type == "tool_result"
    assert evidence.observed_tick == 10
    assert evidence.observed_at == START + timedelta(minutes=10)
    assert state.tool_call_count == 1
    assert reason is TerminationReason.NO_USEFUL_ACTION  # the script ran out


def test_every_turn_leaves_a_decision_record():
    state, _, _, _ = run([ask("get_events", from_tick=0, to_tick=10)])
    first, last = state.decisions
    assert (first.sequence, first.tool, first.outcome) == (1, "get_events", "observed")
    assert first.arguments == {"from_tick": 0, "to_tick": 10}
    assert first.evidence_ids == ("E1",)
    assert first.information_needed == "what get_events shows"
    assert (last.sequence, last.outcome) == (2, "stopped")
    assert last.termination_reason is TerminationReason.NO_USEFUL_ACTION


def test_an_answer_closes_the_question_it_was_asked_for():
    state = new_state()
    state.unanswered_questions = [Question(id="Q1", text="Is vibration rising?")]
    run([ask("get_events", question_id="Q1")], state=state)
    assert state.unanswered_questions == []
    assert state.answers == {"Q1": ["E1"]}
    assert state.data_for("Q1") == {"ok": True}


def test_an_observation_changes_the_next_decision():
    def second(state):
        seen = state.data_for("Q1")
        return ask("get_readings", machine_id=seen["machine"])

    state, provider, _, _ = run(
        [ask("list_machines", question_id="Q1"), second],
        respond=lambda request: {"machine": "CNC-03"},
    )
    assert provider.calls[1].arguments == {"machine_id": "CNC-03"}
    assert len(state.evidence) == 2


def test_the_policy_revises_hypotheses_and_revisions_are_counted():
    def interpret(state, step, evidence):
        confidence = 0.4 if evidence.id == "E1" else 0.7
        return Interpretation(hypotheses=(worn(confidence, evidence.id),))

    state, _, _, _ = run([ask("a"), ask("b")], interpret=interpret)
    assert state.confidence == 0.7
    assert state.hypothesis_revisions == 1  # the first set is not a revision
    assert state.decisions[1].confidence == 0.7


def test_the_policy_is_given_a_copy_and_cannot_change_working_memory():
    def cheat(state):
        state.tool_call_count = 0
        state.evidence.clear()
        return ask("b")

    state, _, _, _ = run([ask("a"), cheat])
    assert state.tool_call_count == 2
    assert [e.id for e in state.evidence] == ["E1", "E2"]


# --- answers that are not evidence -----------------------------------------


def test_a_failed_call_is_counted_but_is_not_evidence():
    state, _, _, _ = run([ask("get_events")], respond=lambda request: "error")
    assert state.evidence == []
    assert state.tool_call_count == 1
    assert state.failed_tool_calls == 1
    assert state.decisions[0].outcome == "tool_error"
    assert state.decisions[0].evidence_ids == ()


def test_a_failed_call_records_what_the_tool_said_was_wrong():
    state, _, _, _ = run([ask("get_events")], respond=lambda request: "error")
    failed = state.decisions[0]
    assert failed.outcome == "tool_error"
    assert failed.error.code == "provider_error"


def test_three_unproductive_turns_in_a_row_stop_the_loop():
    decisions = [ask("a"), ask("b"), ask("c"), ask("d")]
    state, provider, _, reason = run(decisions, respond=lambda request: "error")
    assert reason is TerminationReason.NO_USEFUL_ACTION
    assert len(provider.calls) == 3  # the fourth question was never asked
    assert state.failed_tool_calls == 3


def test_a_useful_answer_resets_the_unproductive_count():
    answers = iter(["error", "error", {"ok": True}, "error", "error", {"ok": True}])
    decisions = [ask(name) for name in "abcdef"]
    state, _, _, _ = run(decisions, respond=lambda request: next(answers))
    assert len(state.evidence) == 2
    assert state.failed_tool_calls == 4


@pytest.mark.parametrize(
    "bad_answer",
    [RuntimeError("password=hunter2"), "not a result", None],
    ids=["provider raises", "wrong kind of object", "success with no data"],
)
def test_an_unusable_answer_is_not_evidence_and_does_not_crash(bad_answer):
    state, _, _, _ = run([ask("get_events")], respond=lambda request: bad_answer)
    assert state.evidence == []
    assert state.malformed_results == 1
    assert state.decisions[0].outcome == "malformed_result"
    assert "hunter2" not in state.model_dump_json()


def test_an_answer_for_a_different_tool_is_not_evidence():
    def respond(request):
        return ToolResult(
            success=True,
            tool="get_settings",
            source="fake",
            tick=10,
            timestamp=START,
            run_id=RUN,
            investigation_id=INVESTIGATION,
            data={"ok": True},
        )

    state, _, _, _ = run([ask("get_events")], respond=respond)
    assert state.evidence == []
    assert state.malformed_results == 1


def test_an_answer_for_a_different_investigation_is_not_evidence():
    def respond(request):
        return ToolResult(
            success=True,
            tool=request.name,
            source="fake",
            tick=10,
            timestamp=START,
            run_id=RUN,
            investigation_id=UUID(int=99),
            data={"ok": True},
        )

    state, _, _, _ = run([ask("get_events")], respond=respond)
    assert state.evidence == []
    assert state.malformed_results == 1
    assert state.decisions[0].outcome == "malformed_result"


def test_a_hypothesis_citing_evidence_that_was_never_gathered_is_refused():
    def interpret(state, step, evidence):
        return Interpretation(hypotheses=(worn(0.95, "E1", "E7"),))

    state, _, _, _ = run([ask("get_events")], interpret=interpret)
    assert state.hypotheses == []
    assert state.confidence == 0.0


def test_a_good_answer_is_kept_when_the_policy_fails_to_interpret_it():
    def interpret(state, step, evidence):
        raise ValueError("could not read this")

    state = new_state()
    state.unanswered_questions = [Question(id="Q1", text="Is vibration rising?")]
    run([ask("get_events", question_id="Q1")], interpret=interpret, state=state)
    assert [e.id for e in state.evidence] == ["E1"]  # the factory did answer
    assert state.answers == {"Q1": ["E1"]}
    assert state.hypotheses == []  # but no belief changed
    assert state.malformed_results == 0
    assert state.interpretation_failures == 1
    assert state.decisions[0].outcome == "uninterpreted"
    assert state.decisions[0].evidence_ids == ("E1",)


def test_a_policy_that_never_interprets_cannot_keep_the_loop_going():
    def interpret(state, step, evidence):
        raise ValueError("could not read this")

    decisions = [ask(name) for name in "abcdef"]
    state, provider, _, reason = run(decisions, interpret=interpret)
    assert reason is TerminationReason.NO_USEFUL_ACTION
    assert len(provider.calls) == 3


# --- repeated questions ----------------------------------------------------


def test_the_same_question_at_the_same_tick_is_skipped_without_a_call():
    same = ask("get_events", from_tick=0, to_tick=10)
    state, provider, _, _ = run([same, same])
    assert len(provider.calls) == 1
    assert state.tool_call_count == 1
    assert state.repeated_calls == 1
    assert state.decisions[1].outcome == "repeated_call"


def test_the_same_question_is_allowed_again_once_time_has_passed():
    same = ask("get_events", from_tick=0, to_tick=10)
    state, provider, _, _ = run([same, ask("wait", ticks=5), same])
    assert len(provider.calls) == 3
    assert state.repeated_calls == 0
    assert state.last_tick == 15


def test_argument_order_does_not_hide_a_repeat():
    state, provider, _, _ = run(
        [ask("get_events", from_tick=0, to_tick=10), ask(to_tick=10, from_tick=0)]
    )
    assert len(provider.calls) == 1
    assert state.repeated_calls == 1


# --- decisions the loop will not accept ------------------------------------


def test_a_policy_cannot_claim_a_stop_reason_that_belongs_to_the_loop():
    for reason in (
        TerminationReason.TIMEOUT,
        TerminationReason.MAX_TOOL_CALLS,
        TerminationReason.DIAGNOSIS_SUPPORTED,
    ):
        with pytest.raises(ValidationError):
            Stop(reason=reason)


def test_an_unusable_decision_uses_a_turn_and_is_recorded():
    def broken(state):
        raise ValueError("no idea")

    state, provider, _, reason = run(["call something", broken, None])
    assert provider.calls == []
    assert state.iteration_count == 3
    assert [d.outcome for d in state.decisions[:3]] == ["invalid_decision"] * 3
    assert reason is TerminationReason.NO_USEFUL_ACTION


def test_enough_evidence_with_no_evidence_is_not_accepted_as_a_reason():
    _, _, _, reason = run([Stop(reason=TerminationReason.EVIDENCE_SUFFICIENT)])
    assert reason is TerminationReason.NO_USEFUL_ACTION


def test_the_policy_may_stop_once_it_has_evidence():
    _, _, _, reason = run(
        [ask("get_events"), Stop(reason=TerminationReason.EVIDENCE_SUFFICIENT)]
    )
    assert reason is TerminationReason.EVIDENCE_SUFFICIENT


# --- limits ----------------------------------------------------------------


def test_the_tool_call_limit_stops_the_loop():
    decisions = [ask(name) for name in "abcdef"]
    state, provider, _, reason = run(decisions, state=new_state(max_tool_calls=3))
    assert reason is TerminationReason.MAX_TOOL_CALLS
    assert len(provider.calls) == 3
    assert state.remaining_tool_calls == 0


def test_the_iteration_limit_stops_the_loop():
    decisions = [ask(name) for name in "abcdef"]
    state, _, _, reason = run(decisions, state=new_state(max_iterations=2))
    assert reason is TerminationReason.MAX_ITERATIONS
    assert state.iteration_count == 2


def test_a_policy_that_always_has_another_question_still_ends():
    numbers = iter(range(10_000))

    class Endless(ScriptedPolicy):
        def decide(self, state, phase):
            return ask("get_events", from_tick=next(numbers))

    state = new_state()
    deps = InvestigationDeps(
        provider=FakeProvider(), policy=Endless([]), clock=lambda: 0.0
    )
    reason = run_inner_loop(state, deps, "investigate")
    assert reason is TerminationReason.MAX_TOOL_CALLS
    assert state.tool_call_count == state.budgets.max_tool_calls


def test_the_timer_starts_with_the_loop_and_a_timeout_stops_it():
    now = [100.0]

    def respond(request):
        now[0] += 30.0  # each call takes thirty seconds
        return {"ok": True}

    state = new_state(timeout_seconds=60.0)
    deps = InvestigationDeps(
        provider=FakeProvider(respond),
        policy=ScriptedPolicy([ask(name) for name in "abcdef"]),
        clock=lambda: now[0],
    )
    reason = run_inner_loop(state, deps, "investigate")
    assert state.started_at == 100.0
    assert reason is TerminationReason.TIMEOUT
    assert state.tool_call_count == 2


def test_a_second_loop_does_not_restart_the_timer():
    now = [100.0]
    state = new_state(timeout_seconds=60.0)
    deps = InvestigationDeps(
        provider=FakeProvider(), policy=ScriptedPolicy([]), clock=lambda: now[0]
    )
    run_inner_loop(state, deps, "investigate")
    now[0] = 170.0
    assert run_inner_loop(state, deps, "test") is TerminationReason.TIMEOUT
    assert state.started_at == 100.0


def test_research_stops_early_to_leave_time_for_what_follows():
    now = [100.0]

    def respond(request):
        now[0] += 10.0  # each call takes ten seconds
        return {"ok": True}

    state = new_state(timeout_seconds=60.0, followup_seconds=20.0)
    deps = InvestigationDeps(
        provider=FakeProvider(respond),
        policy=ScriptedPolicy([ask(name) for name in "abcdef"]),
        clock=lambda: now[0],
    )
    assert run_inner_loop(state, deps, "investigate") is TerminationReason.TIMEOUT
    assert state.tool_call_count == 4  # forty seconds used, twenty kept back
    assert state.remaining_seconds(now[0]) == 20.0


def test_checking_may_use_the_time_research_left():
    now = [100.0]
    state = new_state(timeout_seconds=60.0, followup_seconds=20.0)
    state.started_at = 55.0  # fifteen seconds left: too few to research
    deps = InvestigationDeps(
        provider=FakeProvider(),
        policy=ScriptedPolicy([ask("get_events")]),
        clock=lambda: now[0],
    )
    assert run_inner_loop(state, deps, "test") is TerminationReason.TIMEOUT
    assert state.tool_call_count == 0
    assert run_inner_loop(state, deps, "verify") is not TerminationReason.TIMEOUT
    assert state.tool_call_count == 1


def test_the_time_kept_back_must_leave_research_some_time():
    assert Budgets(timeout_seconds=20.0, followup_seconds=19.0).followup_seconds == 19
    with pytest.raises(ValidationError, match="followup_seconds"):
        Budgets(timeout_seconds=20.0, followup_seconds=20.0)


# --- a supported diagnosis -------------------------------------------------


def supporting(state, step, evidence):
    cited = tuple(e.id for e in state.evidence)
    return Interpretation(hypotheses=(worn(0.95, *cited),))


def test_a_supported_diagnosis_stops_the_test_phase():
    decisions = [ask(name) for name in "abcdef"]
    state, provider, _, reason = run(decisions, interpret=supporting, phase="test")
    assert reason is TerminationReason.DIAGNOSIS_SUPPORTED
    assert len(provider.calls) == 2  # two supporting items are required
    assert state.leading_hypothesis.supporting_evidence_ids == ("E1", "E2")


def test_confidence_alone_is_not_a_supported_diagnosis():
    def confident_without_support(state, step, evidence):
        return Interpretation(hypotheses=(worn(0.99, "E1"),))

    _, _, _, reason = run(
        [ask("a"), ask("b")], interpret=confident_without_support, phase="test"
    )
    assert reason is not TerminationReason.DIAGNOSIS_SUPPORTED


def test_reaching_the_answer_on_the_last_allowed_call_is_success_not_exhaustion():
    decisions = [ask(name) for name in "abcdef"]
    _, _, _, reason = run(
        decisions,
        interpret=supporting,
        phase="test",
        state=new_state(max_tool_calls=2),
    )
    assert reason is TerminationReason.DIAGNOSIS_SUPPORTED


def test_the_investigate_phase_does_not_stop_on_a_supported_diagnosis():
    decisions = [ask(name) for name in "abc"]
    state, provider, _, reason = run(decisions, interpret=supporting)
    assert len(provider.calls) == 3
    assert reason is TerminationReason.NO_USEFUL_ACTION  # the script ran out


def test_an_open_contradiction_blocks_the_automatic_stop():
    deps = InvestigationDeps(provider=FakeProvider(), policy=ScriptedPolicy([]))
    state = new_state()
    state.hypotheses = [worn(0.95, "E1", "E2", "E3")]
    assert diagnosis_supported(state, deps)
    # One alarm, its raw readings and their summary can all "support" a claim
    # while a single independent reading contradicts it: that is not settled.
    state.hypotheses = [
        worn(0.95, "E1", "E2", "E3").model_copy(
            update={"contradicting_evidence_ids": ("E4",)}
        )
    ]
    assert not diagnosis_supported(state, deps)


# --- testing that no longer changes the agent's mind ------------------------


def nudging(*confidences):
    """An interpretation that sets the confidence, one value per answer."""
    values = iter(confidences)

    def interpret(state, step, evidence):
        return Interpretation(hypotheses=(worn(next(values), evidence.id),))

    return interpret


def test_testing_stops_when_three_results_barely_move_confidence():
    decisions = [ask(name) for name in "abcdef"]
    _, provider, _, reason = run(
        decisions, interpret=nudging(0.70, 0.72, 0.73, 0.9, 0.9, 0.9), phase="test"
    )
    assert reason is TerminationReason.NO_USEFUL_ACTION
    assert len(provider.calls) == 3


def test_testing_continues_while_confidence_moves():
    decisions = [ask(name) for name in "abcd"]
    _, provider, _, _ = run(
        decisions, interpret=nudging(0.5, 0.6, 0.7, 0.8), phase="test"
    )
    assert len(provider.calls) == 4  # then the script ran out


def test_investigating_is_not_cut_short_by_flat_confidence():
    decisions = [ask(name) for name in "abcd"]
    _, provider, _, _ = run(decisions, interpret=nudging(0.7, 0.7, 0.7, 0.7))
    assert len(provider.calls) == 4


# --- checking afterwards has its own allowance -----------------------------


def test_verification_spends_its_own_allowance_not_the_research_budget():
    state = new_state(max_tool_calls=2, followup_tool_calls=2)
    run([ask("a"), ask("b"), ask("c")], state=state)
    assert state.remaining_tool_calls == 0

    decisions = [ask(name) for name in "defg"]
    _, provider, _, reason = run(decisions, phase="verify", state=state)
    assert reason is TerminationReason.MAX_TOOL_CALLS
    assert len(provider.calls) == 2
    assert state.followup_tool_calls_used == 2
    assert state.research_tool_calls == 2
    assert state.tool_call_count == 4


# --- what the loop leaves to whoever runs it -------------------------------


def test_the_loop_reports_its_reason_but_does_not_set_the_final_one():
    state, _, _, reason = run([ask("get_events")])
    assert reason is TerminationReason.NO_USEFUL_ACTION
    assert state.decisions[-1].termination_reason is reason
    assert state.termination_reason is None  # the outer sequence decides this
    assert state.metrics().tool_calls == 1


# --- against the real factory boundary -------------------------------------


def test_the_loop_gathers_evidence_through_the_real_provider_without_hidden_truth():
    sim = build_line(42, machines=3)
    sim.add_scenario(
        BearingDegradation(
            "bearing", sim.rng, machine_id="CNC-02", start_tick=100, rate=0.0006
        )
    )
    for _ in range(600):
        sim.step()
    provider = SimulatorFactoryProvider(
        ObservationTools(sim), ActionTools(sim, ApprovalDesk(sim))
    )
    state = new_state()
    state.last_tick = 600
    policy = ScriptedPolicy(
        [
            ask("list_machines"),
            ask(
                "get_sensor_summary",
                machine_id="CNC-02",
                sensor="vibration",
                from_tick=0,
                to_tick=600,
            ),
            ask("read_answer_key"),
            ask("wait", ticks=5),
        ]
    )
    deps = InvestigationDeps(provider=provider, policy=policy, clock=lambda: 0.0)
    run_inner_loop(state, deps, "investigate")

    assert [e.source_id for e in state.evidence] == [
        "simulator:list_machines",
        "simulator:get_sensor_summary",
        "simulator:wait",
    ]
    assert state.failed_tool_calls == 1  # there is no answer-key tool to call
    assert state.last_tick == 605 == sim.clock.tick
    text = state.model_dump_json().lower()
    assert not [word for word in HIDDEN_WORDS if word in text]
    assert sim.ground_truth()  # the truth exists; the loop simply cannot reach it
