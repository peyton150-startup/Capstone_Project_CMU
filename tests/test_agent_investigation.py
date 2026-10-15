from itertools import groupby

import pytest

from capstone.agent.artifacts import AgentConclusion, TerminationReason
from capstone.agent.investigation import INVESTIGATION_GRAPH, run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.agent.policy import ActionRequest, Interpretation, Stop
from capstone.agent.state import Question
from capstone.contracts.hypotheses import Hypothesis
from capstone.providers.chat import ModelError
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.helpers import FakeProvider, ScriptedPolicy, ask, new_state

HIDDEN_WORDS = ("bearing_health", "defect_risk", "standard_speed", "ground_truth")
QUESTIONS = (
    Question(id="Q1", text="Is vibration rising over time?"),
    Question(id="Q2", text="Are the other machines normal?"),
)
REPLACE = ActionRequest(
    machine_id="CNC-02",
    action="replace_bearing",
    reason="vibration has climbed for hundreds of ticks",
    prediction="vibration on CNC-02 returns to its earlier level",
)


def fresh_state(**budgets):
    """An investigation that has not yet learned what time it is."""
    state = new_state(**budgets)
    state.last_tick = None
    return state


def wear(confidence, *supporting):
    return Hypothesis(
        id="H1",
        claim="CNC-02 is wearing",
        confidence=confidence,
        supporting_evidence_ids=supporting,
    )


def interpret_tests_only(state, step, evidence):
    """Beliefs change only when an answer was gathered to test a hypothesis."""
    if step.hypothesis_id is None:
        return Interpretation()
    return Interpretation(hypotheses=(wear(0.92, "E2", evidence.id),))


def conclusion(recommendation="intervene", confidence=0.92, evidence=("E2", "E4")):
    return AgentConclusion(
        diagnosis="wear on CNC-02",
        confidence=confidence,
        recommendation=recommendation,
        hypothesis_id="H1",
        evidence_ids=evidence,
    )


def wear_policy(conclude=None, **overrides):
    """The worked example: two look-ups, one explanation, one test, a conclusion."""
    settings = {
        "decisions": {
            "investigate": [
                ask("get_sensor_summary", question_id="Q1", machine_id="CNC-02"),
                ask("list_machines", question_id="Q2"),
            ],
            "test": [ask("get_readings", hypothesis_id="H1", machine_id="CNC-02")],
        },
        "interpret": interpret_tests_only,
        "questions": QUESTIONS,
        "hypothesize": lambda state: Interpretation(hypotheses=(wear(0.6, "E2"),)),
        "conclude": conclude or (lambda state: (conclusion(), REPLACE)),
    }
    settings.update(overrides)
    decisions = settings.pop("decisions")
    interpret = settings.pop("interpret")
    return ScriptedPolicy(decisions, interpret, **settings)


def investigate(policy, *, respond=None, state=None, clock=None, **settings):
    state = state or fresh_state()
    provider = FakeProvider(respond)
    deps = InvestigationDeps(
        provider=provider, policy=policy, clock=clock or (lambda: 0.0), **settings
    )
    assert run_investigation(state, deps) is state
    return state, provider


def stages(state):
    """The stages the investigation went through, in order."""
    return [phase for phase, _ in groupby(d.phase for d in state.decisions)]


# --- the whole path --------------------------------------------------------


def test_an_investigation_goes_through_the_stages_in_order():
    state, provider = investigate(wear_policy())
    assert stages(state) == [
        "observe",
        "plan",
        "investigate",
        "hypothesize",
        "test",
        "decide",
        "propose",
    ]
    assert [r.name for r in provider.calls] == [
        "get_time",
        "get_sensor_summary",
        "list_machines",
        "get_readings",
        "propose_action",
    ]
    assert [e.id for e in state.evidence] == ["E1", "E2", "E3", "E4", "E5"]
    assert state.termination_reason is TerminationReason.DIAGNOSIS_SUPPORTED
    assert state.conclusion == conclusion()
    assert state.answers == {"Q1": ["E2"], "Q2": ["E3"]}


def test_the_conclusion_s_record_carries_its_evidence_and_the_final_stop_reason():
    state, _ = investigate(wear_policy())
    [decided] = [d for d in state.decisions if d.phase == "decide"]
    assert (decided.outcome, decided.tool) == ("decided", None)
    assert decided.evidence_ids == ("E2", "E4")
    assert decided.termination_reason is TerminationReason.DIAGNOSIS_SUPPORTED
    assert [d.sequence for d in state.decisions] == list(
        range(1, len(state.decisions) + 1)
    )


# --- observe ---------------------------------------------------------------


def test_the_first_thing_asked_is_the_time_and_the_timer_starts():
    state, provider = investigate(wear_policy(), clock=lambda: 50.0)
    assert provider.calls[0].name == "get_time"
    first = state.decisions[0]
    assert (first.phase, first.outcome, first.evidence_ids) == (
        "observe",
        "observed",
        ("E1",),
    )
    assert state.started_at == 50.0
    assert state.evidence[0].observed_tick == 10
    assert state.research_tool_calls == 4  # asking the time is a counted call


def test_a_repeat_is_caught_from_the_policy_s_very_first_question():
    same = ask("get_events", from_tick=0, to_tick=10)
    policy = wear_policy(
        decisions={"investigate": [ask("get_time"), same, same]},
        conclude=lambda state: (conclusion("no_action", 0.5, ("E2",)), None),
        hypothesize=None,
    )
    state, provider = investigate(policy)
    assert [r.name for r in provider.calls] == ["get_time", "get_events"]
    assert state.repeated_calls == 2  # the time again, then the same events again


def test_an_investigation_survives_the_factory_not_telling_the_time():
    def respond(request):
        return "error" if request.name == "get_time" else {"ok": True}

    state, _ = investigate(wear_policy(), respond=respond)
    assert state.decisions[0].outcome == "tool_error"
    assert state.conclusion is not None
    assert "investigate" in stages(state)


# --- plan ------------------------------------------------------------------


def test_the_plan_becomes_the_open_questions():
    policy = wear_policy(decisions={})
    state, _ = investigate(policy)
    assert state.unanswered_questions == list(QUESTIONS)
    assert state.decisions[1].phase == "plan"
    assert state.decisions[1].outcome == "decided"


def failing_plan(state):
    raise ValueError("no plan")


@pytest.mark.parametrize(
    "questions",
    [lambda state: ["find the fault"], failing_plan],
    ids=["not questions", "policy fails"],
)
def test_a_bad_plan_is_recorded_and_the_investigation_carries_on(questions):
    state, _ = investigate(wear_policy(questions=questions))
    assert state.decisions[1].phase == "plan"
    assert state.decisions[1].outcome == "invalid_decision"
    assert state.unanswered_questions == []
    assert state.conclusion == conclusion()  # the rest still ran


# --- shortcuts to the conclusion -------------------------------------------


def test_with_nothing_gathered_it_goes_straight_to_the_conclusion():
    policy = wear_policy(decisions={})
    state, provider = investigate(policy)
    assert stages(state) == ["observe", "plan", "investigate", "decide"]
    assert policy.asked == ["plan", "conclude"]  # no explanations were asked for
    assert [r.name for r in provider.calls] == ["get_time"]
    assert state.conclusion.diagnosis == "undetermined"  # it cited E2 and E4


def test_a_timeout_while_investigating_goes_straight_to_the_conclusion():
    now = [0.0]

    def respond(request):
        now[0] += 40.0
        return {"ok": True}

    policy = wear_policy()
    state, _ = investigate(
        policy, respond=respond, clock=lambda: now[0], state=fresh_state()
    )
    assert state.termination_reason is TerminationReason.TIMEOUT
    assert "hypothesize" not in stages(state)
    assert "test" not in stages(state)
    assert state.conclusion is not None


def test_with_no_explanation_there_is_nothing_to_test():
    policy = wear_policy(hypothesize=lambda state: Interpretation())
    state, provider = investigate(policy)
    assert stages(state) == ["observe", "plan", "investigate", "hypothesize", "decide"]
    assert "get_readings" not in [r.name for r in provider.calls]


def test_an_explanation_citing_evidence_that_was_never_gathered_is_refused():
    policy = wear_policy(
        hypothesize=lambda state: Interpretation(hypotheses=(wear(0.9, "E2", "E9"),))
    )
    state, _ = investigate(policy)
    assert state.hypotheses == []
    assert state.decisions[-2].phase == "hypothesize"
    assert state.decisions[-2].outcome == "invalid_decision"
    assert "test" not in stages(state)


# --- the conclusion is checked ---------------------------------------------


def undetermined(state):
    last = state.decisions[-1]
    return (
        state.conclusion.diagnosis == "undetermined"
        and state.conclusion.confidence == 0.0
        and state.conclusion.recommendation == "escalate"
        and state.conclusion.evidence_ids == ()
        and state.proposed_action is None
        and (last.phase, last.outcome) == ("decide", "invalid_decision")
    )


def test_a_conclusion_citing_evidence_that_was_never_gathered_is_refused():
    policy = wear_policy(
        conclude=lambda state: (
            conclusion(confidence=0.95, evidence=("E2", "E9")),
            REPLACE,
        )
    )
    state, _ = investigate(policy)
    assert undetermined(state)


def test_a_conclusion_resting_on_misleading_but_real_evidence_is_accepted():
    state, _ = investigate(wear_policy())
    # Both items exist. Whether E4 misleads is the policy's to weigh.
    assert state.conclusion.evidence_ids == ("E2", "E4")
    [decided] = [d for d in state.decisions if d.phase == "decide"]
    assert decided.outcome == "decided"


def test_a_conclusion_naming_a_hypothesis_that_was_never_formed_is_refused():
    wrong = conclusion().model_copy(update={"hypothesis_id": "H7"})
    state, _ = investigate(wear_policy(conclude=lambda state: (wrong, REPLACE)))
    assert undetermined(state)


@pytest.mark.parametrize(
    "answer",
    [
        lambda state: 1 / 0,
        lambda state: ("wear on CNC-02", None),
        lambda state: conclusion(),
        lambda state: (conclusion(), "replace the bearing"),
    ],
    ids=["policy fails", "not a conclusion", "not a pair", "action is not a request"],
)
def test_an_unusable_conclusion_becomes_an_honest_undetermined(answer):
    def conclude(state):
        try:
            return answer(state)
        except ZeroDivisionError as error:
            raise ValueError("could not conclude") from error

    state, _ = investigate(wear_policy(conclude=conclude))
    assert undetermined(state)
    assert state.termination_reason is TerminationReason.DIAGNOSIS_SUPPORTED


def test_every_investigation_ends_with_a_conclusion_and_a_stop_reason():
    always_failing = ScriptedPolicy([Stop(reason=TerminationReason.NO_USEFUL_ACTION)])
    state, _ = investigate(always_failing, respond=lambda request: "error")
    assert undetermined(state)
    assert state.termination_reason is TerminationReason.NO_USEFUL_ACTION


# --- asking for a change ---------------------------------------------------


def test_a_justified_action_is_recorded_with_what_the_agent_expects_to_change():
    state, _ = investigate(wear_policy(), state=fresh_state(followup_tool_calls=0))
    assert state.conclusion.recommendation == "intervene"
    assert state.proposed_action.model_dump() == {
        "proposal_id": None,
        "machine_id": "CNC-02",
        "action": "replace_bearing",
        "reason": "vibration has climbed for hundreds of ticks",
        "status": "not_submitted",
    }
    assert state.predicted_effect == "vibration on CNC-02 returns to its earlier level"


@pytest.mark.parametrize(
    "concluded",
    [
        (conclusion(confidence=0.7), REPLACE),
        (conclusion(evidence=()), REPLACE),
        (conclusion(), None),
    ],
    ids=["not confident enough", "cites nothing", "names no action"],
)
def test_an_unjustified_intervention_is_lowered_to_escalate(concluded):
    state, _ = investigate(wear_policy(conclude=lambda state: concluded))
    assert state.conclusion.recommendation == "escalate"
    assert state.conclusion.diagnosis == "wear on CNC-02"  # the belief is kept
    assert state.proposed_action is None
    assert state.predicted_effect is None


def test_the_confidence_needed_to_act_is_a_setting():
    concluded = (conclusion(confidence=0.7), REPLACE)
    state, _ = investigate(
        wear_policy(conclude=lambda state: concluded), min_action_confidence=0.6
    )
    assert state.conclusion.recommendation == "intervene"
    assert state.proposed_action is not None


@pytest.mark.parametrize("recommendation", ["no_action", "escalate"])
def test_an_action_is_dropped_when_the_conclusion_does_not_recommend_one(
    recommendation,
):
    concluded = (conclusion(recommendation), REPLACE)
    state, _ = investigate(wear_policy(conclude=lambda state: concluded))
    assert state.conclusion.recommendation == recommendation
    assert state.proposed_action is None


# --- the final stop reason -------------------------------------------------


def test_the_final_stop_reason_is_the_last_research_loop_s():
    policy = wear_policy(decisions={"investigate": [ask("list_machines")]})
    state, _ = investigate(policy)
    loops = [d for d in state.decisions if d.outcome == "stopped"]
    assert [d.phase for d in loops] == ["investigate", "test"]
    assert state.termination_reason is loops[-1].termination_reason


def test_running_out_of_calls_is_reported_as_the_reason():
    policy = wear_policy(
        decisions={"investigate": [ask(name) for name in "abcdef"]},
        hypothesize=lambda state: Interpretation(hypotheses=(wear(0.5, "E2"),)),
        conclude=lambda state: (conclusion("escalate", 0.5, ("E2",)), None),
    )
    state, provider = investigate(policy, state=fresh_state(max_tool_calls=4))
    assert state.termination_reason is TerminationReason.MAX_TOOL_CALLS
    assert len(provider.calls) == 4  # the time, then three look-ups
    assert state.conclusion.recommendation == "escalate"


# --- the shape of the graph ------------------------------------------------


def test_the_graph_draws_only_the_allowed_order():
    lines = {line.strip() for line in INVESTIGATION_GRAPH.render().splitlines()}
    arrows = {line for line in lines if "-->" in line}
    assert arrows == {
        "[*] --> observe",
        "observe --> plan",
        "plan --> investigate",
        "investigate --> anything_to_explain",
        "anything_to_explain --> hypothesize",
        "anything_to_explain --> conclude",
        "hypothesize --> anything_to_test",
        "anything_to_test --> test",
        "anything_to_test --> conclude",
        "test --> conclude",
        "conclude --> propose",
        "propose --> approved",
        "approved --> execute",
        "approved --> verify",
        "approved --> [*]",
        "execute --> work_finished",
        "work_finished --> verify",
        "work_finished --> [*]",
        "verify --> [*]",
    }


def test_the_work_can_only_be_reached_through_the_proposal():
    arrows = [
        line.strip()
        for line in INVESTIGATION_GRAPH.render().splitlines()
        if line.strip().endswith("--> execute")
    ]
    assert arrows == ["approved --> execute"]


# --- against the real factory boundary -------------------------------------


def test_research_through_the_real_provider_changes_nothing_in_the_factory():
    sim = build_line(42, machines=3)
    sim.add_scenario(
        BearingDegradation(
            "bearing", sim.rng, machine_id="CNC-02", start_tick=100, rate=0.0006
        )
    )
    for _ in range(600):
        sim.step()
    desk = ApprovalDesk(sim)
    provider = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim, desk))
    summary = {
        "machine_id": "CNC-02",
        "sensor": "vibration",
        "from_tick": 0,
        "to_tick": 600,
    }
    policy = wear_policy(
        decisions={
            "investigate": [
                ask("get_sensor_summary", question_id="Q1", **summary),
                ask("list_machines", question_id="Q2"),
            ],
            "test": [
                ask(
                    "get_events",
                    hypothesis_id="H1",
                    machine_id="CNC-02",
                    from_tick=0,
                    to_tick=600,
                )
            ],
        }
    )
    before = (sim.clock.tick, sim.state.model_copy(deep=True), sim.event_log.events)
    state = fresh_state()
    deps = InvestigationDeps(provider=provider, policy=policy, clock=lambda: 0.0)
    run_investigation(state, deps)

    assert state.last_tick == 600
    assert [e.source_id for e in state.evidence] == [
        "simulator:get_time",
        "simulator:get_sensor_summary",
        "simulator:list_machines",
        "simulator:get_events",
        "simulator:propose_action",
        "simulator:get_proposals",
    ]
    assert state.conclusion == conclusion()
    # Nobody answered, so the request is still waiting and nothing was started.
    assert state.proposed_action.status == "pending"
    assert [p["status"] for p in desk.proposals()] == ["pending"]
    assert not state.action_carried_out
    assert (sim.clock.tick, sim.state, sim.event_log.events) == before
    text = state.model_dump_json().lower()
    assert not [word for word in HIDDEN_WORDS if word in text]


# --- no model service answers ------------------------------------------------


def unavailable(*args):
    raise ModelError("no model service answered")


def test_an_outage_ends_the_investigation_with_its_own_reason():
    state, provider = investigate(wear_policy(hypothesize=unavailable))
    assert state.termination_reason is TerminationReason.MODEL_UNAVAILABLE
    assert state.conclusion.diagnosis == "undetermined"
    last = state.decisions[-1]
    assert last.outcome == "stopped"
    assert last.phase == "hypothesize"  # the stage it cut short
    assert last.termination_reason is TerminationReason.MODEL_UNAVAILABLE
    # Nothing was proposed: the run stopped before it reached a conclusion.
    assert "propose_action" not in [r.name for r in provider.calls]


def test_an_outage_inside_the_research_loop_is_not_an_unproductive_turn():
    policy = wear_policy()
    policy.decide = unavailable
    state, _ = investigate(policy)
    assert state.termination_reason is TerminationReason.MODEL_UNAVAILABLE
    assert [d.outcome for d in state.decisions].count("invalid_decision") == 0
