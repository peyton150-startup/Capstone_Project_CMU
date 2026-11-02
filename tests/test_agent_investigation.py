from itertools import groupby

import pytest

from capstone.agent.artifacts import (
    AgentConclusion,
    CritiqueRecord,
    TerminationReason,
)
from capstone.agent.investigation import (
    INVESTIGATION_GRAPH,
    critique,
    recheck,
    recheck_trigger,
    run_investigation,
)
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
from tests.helpers import (
    FakeCritic,
    FakeProvider,
    ScriptedPolicy,
    ask,
    critique_result,
    new_state,
)

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
        policy,
        respond=respond,
        clock=lambda: now[0],
        state=fresh_state(timeout_seconds=180.0, followup_seconds=60.0),
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
    assert state.policy_recommendation == "intervene"  # what the policy said
    assert state.recommendation_lowered is not None  # and why it was overruled
    assert state.conclusion.diagnosis == "wear on CNC-02"  # the belief is kept
    assert state.proposed_action is None
    assert state.predicted_effect is None


@pytest.mark.parametrize(
    ("concluded", "why"),
    [
        ((conclusion(confidence=0.8), REPLACE), "confidence 0.80 below 0.90"),
        ((conclusion(evidence=()), REPLACE), "no evidence cited"),
        ((conclusion(), None), "no action named"),
    ],
    ids=["not confident enough", "cites nothing", "names no action"],
)
def test_the_reason_an_intervention_was_lowered_is_recorded(concluded, why):
    state, _ = investigate(wear_policy(conclude=lambda state: concluded))
    assert state.recommendation_lowered == why


def test_an_accepted_or_unchanged_recommendation_records_no_lowering():
    state, _ = investigate(wear_policy(), state=fresh_state(followup_tool_calls=0))
    assert state.policy_recommendation == "intervene"
    assert state.recommendation_lowered is None
    chose = (conclusion("escalate", 0.5, ("E2",)), None)
    state, _ = investigate(wear_policy(conclude=lambda state: chose))
    assert state.policy_recommendation == "escalate"  # its own choice
    assert state.recommendation_lowered is None


def test_the_policy_is_shown_the_bar_it_must_meet_to_act():
    seen = []

    def conclude(state):
        seen.append(state.action_confidence_needed)
        return conclusion(), REPLACE

    investigate(wear_policy(conclude=conclude), min_action_confidence=0.75)
    assert seen == [0.75]


@pytest.mark.parametrize("visible", [True, False])
@pytest.mark.parametrize(
    "confidence, expected", [(0.7, "escalate"), (0.9, "intervene")]
)
def test_hiding_the_bar_changes_visibility_but_not_enforcement(
    visible, confidence, expected
):
    seen = []

    def conclude(state):
        seen.append(state.action_confidence_needed)
        return conclusion(confidence=confidence), REPLACE

    state, _ = investigate(
        wear_policy(conclude=conclude),
        state_action_bar=visible,
        min_action_confidence=0.8,
    )
    assert seen == [0.8 if visible else None]
    assert state.conclusion.recommendation == expected
    assert state.policy_recommendation == "intervene"
    assert (state.recommendation_lowered is not None) == (confidence < 0.8)


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
        "observe --> manual",
        "manual --> plan",
        "plan --> investigate",
        "investigate --> anything_to_explain",
        "anything_to_explain --> hypothesize",
        "anything_to_explain --> critique",
        "hypothesize --> anything_to_test",
        "anything_to_test --> test",
        "anything_to_test --> critique",
        "test --> critique",
        "critique --> recheck",
        "recheck --> conclude",
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


# --- the critic: review only -----------------------------------------------


def test_no_critic_changes_nothing():
    state, _ = investigate(wear_policy())
    assert state.critique is None
    assert state.conclusion == conclusion()
    assert stages(state)[-3:] == ["test", "decide", "propose"]


def test_critic_answer_is_recorded_and_changes_nothing():
    plain, _ = investigate(wear_policy())
    critic = FakeCritic(critique_result("object"))
    state, _ = investigate(wear_policy(), critic=critic, critic_seconds=33.0)
    assert state.critique.outcome == "answered"
    assert state.critique.result.verdict == "object"
    assert state.critique.shown_hypotheses == ("H1",)
    assert critic.reviewed[0][1] == 33.0
    assert state.conclusion == plain.conclusion
    assert state.proposed_action == plain.proposed_action
    assert state.termination_reason == plain.termination_reason
    assert state.hypotheses == plain.hypotheses
    assert [d.outcome for d in state.decisions] == [d.outcome for d in plain.decisions]


def test_critic_is_shown_a_copy_of_the_state():
    seen = []
    critic = FakeCritic(on_review=lambda: seen.append(1))
    state, _ = investigate(wear_policy(), critic=critic)
    shown_state = critic.reviewed[0][0]
    assert shown_state is not state
    assert shown_state.conclusion is None  # reviewed before the conclusion


def test_critic_outage_does_not_end_the_run():
    critic = FakeCritic(ModelError("no model answered"))
    state, _ = investigate(wear_policy(), critic=critic)
    assert state.critique.outcome == "no_answer"
    assert state.critique.result is None
    assert state.conclusion == conclusion()
    assert state.termination_reason is not TerminationReason.MODEL_UNAVAILABLE


def test_invalid_critique_does_not_end_the_run():
    critic = FakeCritic(ValueError("cited E99"))
    state, _ = investigate(wear_policy(), critic=critic)
    assert state.critique.outcome == "invalid_reply"
    assert state.critique.result is None
    assert state.conclusion == conclusion()


def test_critic_time_does_not_shorten_the_investigation():
    now = [0.0]
    remaining = []

    def watch(state):
        remaining.append((state.critique, state.remaining_seconds(now[0])))

    critic = FakeCritic(on_review=lambda: now.__setitem__(0, now[0] + 30.0))
    state, _ = investigate(
        wear_policy(), critic=critic, clock=lambda: now[0], watch=watch
    )
    before = [r for c, r in remaining if c is None][-1]  # after the test stage
    after = [r for c, r in remaining if c is not None][0]  # after the critique
    assert after == before
    assert state.critique.seconds == 30.0
    assert now[0] == 30.0


def test_critic_after_deadline_still_runs():
    state = fresh_state(timeout_seconds=100.0, followup_seconds=10.0)
    state.started_at = 0.0
    state.hypotheses = [wear(0.6, "E2")]
    now = [500.0]
    critic = FakeCritic(on_review=lambda: now.__setitem__(0, now[0] + 7.0))
    deps = InvestigationDeps(
        provider=FakeProvider(),
        policy=wear_policy(),
        clock=lambda: now[0],
        critic=critic,
    )
    assert state.remaining_seconds(now[0]) == 0.0
    critique(state, deps)
    assert len(critic.reviewed) == 1
    assert state.critique.seconds == 7.0
    assert state.remaining_seconds(now[0]) == 0.0


def test_critic_skipped_without_hypotheses():
    critic = FakeCritic()
    policy = wear_policy(hypothesize=lambda state: Interpretation())
    state, _ = investigate(policy, critic=critic)
    assert critic.reviewed == []
    assert state.critique is None


def test_critique_writes_nothing_without_a_critic():
    state = fresh_state()
    state.hypotheses = [wear(0.6)]
    deps = InvestigationDeps(provider=FakeProvider(), policy=wear_policy())
    critique(state, deps)
    assert state.critique is None


def test_critique_records_which_model_answered():
    state, _ = investigate(wear_policy(), critic=FakeCritic())
    assert state.critique.answered_by == "fake"


def test_critique_with_no_answer_names_no_model():
    state, _ = investigate(wear_policy(), critic=FakeCritic(ModelError("none")))
    assert state.critique.outcome == "no_answer"
    assert state.critique.answered_by is None


def test_a_critic_without_a_call_record_still_works():
    class Bare:
        def review(self, state, *, max_seconds):
            return critique_result()

    state, _ = investigate(wear_policy(), critic=Bare())
    assert state.critique.outcome == "answered"
    assert state.critique.answered_by is None


def test_critique_keeps_the_claim_it_judged_as_worded_then():
    state, _ = investigate(wear_policy(), critic=FakeCritic())
    # The fake favours H1; at the critique H1 is wear(0.92) from the test stage.
    assert state.critique.favoured_claim == "CNC-02 is wearing"


def test_critique_claim_is_none_when_the_critic_favoured_none():
    critic = FakeCritic(critique_result(favoured="none"))
    state, _ = investigate(wear_policy(), critic=critic)
    assert state.critique.favoured_claim is None


def test_critique_claim_is_none_without_an_answer():
    state, _ = investigate(wear_policy(), critic=FakeCritic(ModelError("none")))
    assert state.critique.favoured_claim is None


def test_later_rewording_does_not_change_the_recorded_claim():
    state = fresh_state()
    state.started_at = 0.0
    state.hypotheses = [wear(0.8, "E2")]
    deps = InvestigationDeps(
        provider=FakeProvider(), policy=wear_policy(), critic=FakeCritic()
    )
    critique(state, deps)
    state.hypotheses = [
        Hypothesis(
            id="H1", claim="the bearing was replaced and it worked", confidence=0.99
        )
    ]
    assert state.critique.favoured_claim == "CNC-02 is wearing"


# --- the critic follow-up: one reading where the critic pointed --------------


def settled_at(confidence, confirmed=None):
    """Tests leave the leader at `confidence`; the critic's check moves it to
    `confirmed` (or leaves it where it was)."""

    def interpret(state, step, evidence):
        if step.question_id == "K1":
            return Interpretation(
                hypotheses=(wear(confirmed or confidence, "E2", evidence.id),)
            )
        if step.hypothesis_id is None:
            return Interpretation()
        return Interpretation(hypotheses=(wear(confidence, "E2", evidence.id),))

    return interpret


def as_sure_as_the_agent(state):
    """Ask to intervene at whatever confidence the agent has reached."""
    return conclusion("intervene", state.confidence, ("E2",)), REPLACE


CHECK = ask("get_settings", question_id="K1", machine_id="CNC-02")


def follow_up_policy(confidence, confirmed=None, check=CHECK):
    """The worked example, plus an answer for the critic's question (K1) that
    the policy gives only while that question is open."""
    policy = wear_policy(
        interpret=settled_at(confidence, confirmed), conclude=as_sure_as_the_agent
    )
    plain = policy.decide

    def decide(state, phase):
        if any(q.id == "K1" for q in state.unanswered_questions):
            return check(state) if callable(check) else check
        return plain(state, phase)

    policy.decide = decide
    return policy


def agreeing(favoured="H1"):
    return FakeCritic(critique_result("no_objection", favoured=favoured))


def test_follow_up_is_off_by_default():
    state, provider = investigate(wear_policy(), critic=FakeCritic())
    assert state.recheck is None
    assert "get_settings" not in [r.name for r in provider.calls]


def test_follow_up_without_a_critic_does_nothing():
    state, _ = investigate(wear_policy(), critic_followup=True)
    assert state.critique is None and state.recheck is None


def test_an_objection_earns_exactly_one_reading_where_the_critic_pointed():
    state, provider = investigate(
        follow_up_policy(0.95), critic=FakeCritic(), critic_followup=True
    )
    names = [r.name for r in provider.calls]
    assert names.count("get_settings") == 1
    assert names.index("get_settings") < names.index("propose_action")
    record = state.recheck
    assert record.outcome == "observed" and record.trigger == "objection"
    assert record.tool == "get_settings"
    assert record.question == "The critic's check: get_readings on CNC-02"
    assert record.leading_before == "H1" and record.evidence_id is not None
    # The answer is an observation like any other: labelled by its real source.
    origin = {p.evidence_id: p.origin for p in state.provenance}
    assert origin[record.evidence_id] == "observable"
    assert state.answers["K1"] == [record.evidence_id]
    assert all(q.id != "K1" for q in state.unanswered_questions)


def test_the_follow_up_never_loops():
    critic = FakeCritic()
    # This call does not answer K1, so K1 stays open and the policy would
    # keep calling it if it were asked again. It is asked once.
    more = ask("get_events", machine_id="CNC-02")
    state, provider = investigate(
        follow_up_policy(0.95, check=more), critic=critic, critic_followup=True
    )
    assert len(critic.reviewed) == 1
    names = [r.name for r in provider.calls]
    assert names.count("get_events") == 1


def test_agreement_below_the_bar_and_a_confirming_reading_lets_the_agent_act():
    state, provider = investigate(
        follow_up_policy(0.8, confirmed=0.95), critic=agreeing(), critic_followup=True
    )
    assert state.recheck.trigger == "agreement"
    assert state.recheck.confidence_before == 0.8
    assert state.recheck.confidence_after == 0.95
    assert state.conclusion.recommendation == "intervene"
    assert "propose_action" in [r.name for r in provider.calls]


def test_agreement_without_a_confirming_reading_still_escalates():
    # The critic agrees, but the reading did not raise the agent's own
    # confidence: the bar applies to the agent, not to the critic's opinion.
    state, provider = investigate(
        follow_up_policy(0.8), critic=agreeing(), critic_followup=True
    )
    assert state.recheck.outcome == "observed"
    assert state.recheck.confidence_after == 0.8
    assert state.conclusion.recommendation == "escalate"
    assert "propose_action" not in [r.name for r in provider.calls]


def test_without_the_follow_up_the_same_agreement_escalates():
    state, provider = investigate(
        follow_up_policy(0.8, confirmed=0.95), critic=agreeing()
    )
    assert state.recheck is None
    assert state.conclusion.recommendation == "escalate"
    assert "get_settings" not in [r.name for r in provider.calls]


def test_a_policy_that_stops_makes_no_call():
    stop = Stop(reason=TerminationReason.NO_USEFUL_ACTION)
    policy = follow_up_policy(0.8, check=stop)
    state, provider = investigate(policy, critic=agreeing(), critic_followup=True)
    assert state.recheck.outcome == "policy_stopped"
    assert "get_settings" not in [r.name for r in provider.calls]


def test_a_bad_decision_is_recorded_and_the_run_goes_on():
    policy = follow_up_policy(0.8, check=lambda state: "not a decision")
    state, _ = investigate(policy, critic=agreeing(), critic_followup=True)
    assert state.recheck.outcome == "invalid_decision"
    assert state.conclusion is not None


def recheck_state(confidence=0.8, **budgets):
    state = fresh_state(**budgets)
    state.started_at = 0.0
    state.hypotheses = [wear(confidence, "E2")]
    return state


def with_critique(state, reply):
    state.critique = CritiqueRecord(
        outcome="answered" if reply else "no_answer",
        result=reply,
        shown_hypotheses=("H1",),
        seconds=1.0,
    )
    return state


def trigger(state, **settings):
    deps = InvestigationDeps(
        provider=FakeProvider(), policy=wear_policy(), clock=lambda: 0.0, **settings
    )
    return recheck_trigger(state, deps)


def test_trigger_reasons():
    assert trigger(with_critique(recheck_state(), critique_result())) == (
        "objection",
        None,
    )
    agree = critique_result("no_objection")
    assert trigger(with_critique(recheck_state(0.8), agree)) == ("agreement", None)
    assert trigger(with_critique(recheck_state(0.9), agree)) == (
        "agreement",
        None,
    )
    other = critique_result("no_objection", favoured="H2")
    assert trigger(with_critique(recheck_state(), other))[0] is None
    assert trigger(with_critique(recheck_state(), None)) == (
        None,
        "the critic gave no usable answer",
    )
    # The bar is the run's own setting.
    assert trigger(
        with_critique(recheck_state(0.9), agree), min_action_confidence=0.95
    ) == ("agreement", None)


def test_trigger_needs_a_tool_call_and_a_window_but_not_research_time():
    # Research ran out (the live hard cases): the follow-up still runs.
    late = recheck_state(timeout_seconds=100.0, followup_seconds=10.0)
    late.started_at = -500.0
    assert trigger(with_critique(late, critique_result())) == ("objection", None)
    assert trigger(with_critique(late, critique_result()), recheck_seconds=0) == (
        None,
        "the follow-up has no time window",
    )
    spent = recheck_state(max_tool_calls=1)
    spent.tool_call_count = 1
    assert trigger(with_critique(spent, critique_result())) == ("objection", None)
    spent.critic_tool_calls_used = 1
    assert (
        trigger(with_critique(spent, critique_result()))[1]
        == "no critic diagnostic calls left"
    )


def test_a_disabled_critic_allowance_says_why_and_calls_nothing():
    state = with_critique(
        recheck_state(0.95, critic_tool_calls=0), critique_result("no_objection")
    )
    provider = FakeProvider()
    deps = InvestigationDeps(
        provider=provider,
        policy=wear_policy(),
        clock=lambda: 0.0,
        critic=FakeCritic(),
        critic_followup=True,
    )
    recheck(state, deps)
    assert state.recheck.outcome == "skipped"
    assert state.recheck.reason == "no critic diagnostic calls left"
    assert provider.calls == []


# --- the critic before every conclusion ----------------------------------------


def believing_from_the_start(state, step, evidence):
    """Every answer, from the first look on, supports the same explanation."""
    return Interpretation(hypotheses=(wear(0.6, evidence.id),))


def test_the_critic_reviews_a_run_that_timed_out_before_testing():
    now = [0.0]

    def respond(request):
        now[0] += 40.0
        return {"ok": True}

    critic = FakeCritic()
    state, _ = investigate(
        wear_policy(interpret=believing_from_the_start),
        respond=respond,
        clock=lambda: now[0],
        state=fresh_state(timeout_seconds=180.0, followup_seconds=60.0),
        critic=critic,
    )
    assert state.termination_reason is TerminationReason.TIMEOUT
    assert "test" not in stages(state)
    assert len(critic.reviewed) == 1
    assert state.critique.outcome == "answered"
    assert state.critique.after_stage == "investigate"
    assert state.conclusion is not None


def test_after_a_test_round_the_critique_says_so():
    state, _ = investigate(wear_policy(), critic=FakeCritic())
    assert state.critique.after_stage == "test"


def test_after_stage_is_read_before_the_follow_up_changes_the_stage():
    state = fresh_state()
    state.started_at = 0.0
    state.stage = "hypothesize"
    state.hypotheses = [wear(0.6, "E2")]
    deps = InvestigationDeps(
        provider=FakeProvider(),
        policy=wear_policy(),
        critic=FakeCritic(),
        critic_followup=True,
        clock=lambda: 0.0,
    )
    critique(state, deps)
    recheck(state, deps)
    assert state.stage == "test"  # the follow-up runs as a test step
    assert state.critique.after_stage == "hypothesize"


def stopping_policy():
    policy = wear_policy()
    policy.decide = lambda state, phase: Stop(
        reason=TerminationReason.EVIDENCE_SUFFICIENT, information_needed="enough"
    )
    return policy


def test_the_follow_up_tests_the_critic_s_pick_when_it_is_not_the_leader():
    state = fresh_state()
    state.started_at = 0.0
    state.stage = "test"
    state.hypotheses = [
        wear(0.8, "E2"),
        Hypothesis(id="H2", claim="the failed jobs share one batch", confidence=0.3),
    ]
    critic = FakeCritic(critique_result("object", favoured="H2"))
    deps = InvestigationDeps(
        provider=FakeProvider(),
        policy=stopping_policy(),
        critic=critic,
        critic_followup=True,
        clock=lambda: 0.0,
    )
    critique(state, deps)
    recheck(state, deps)
    [question] = [q for q in state.unanswered_questions if q.id == "K1"]
    assert question.hypothesis_id == "H2"
    assert "H2" in question.text and "H1" in question.text
    assert state.recheck.question == question.text


def test_the_follow_up_still_tests_the_leader_when_the_critic_picked_it():
    state = fresh_state()
    state.started_at = 0.0
    state.stage = "test"
    state.hypotheses = [wear(0.8, "E2")]
    deps = InvestigationDeps(
        provider=FakeProvider(),
        policy=stopping_policy(),
        critic=FakeCritic(critique_result("object", favoured="H1")),
        critic_followup=True,
        clock=lambda: 0.0,
    )
    critique(state, deps)
    recheck(state, deps)
    [question] = [q for q in state.unanswered_questions if q.id == "K1"]
    assert question.hypothesis_id == "H1"
    assert question.text == "The critic's check: get_readings on CNC-02"


# --- the critic's manual sections (Option B) are kept on the record ----------


def test_the_record_keeps_which_manual_sections_the_critic_saw():
    critic = FakeCritic()
    critic.last_sections = ("§2.9", "§2.1")
    state, _ = investigate(wear_policy(), critic=critic)
    assert state.critique.manual_sections == ("§2.9", "§2.1")


def test_a_critic_without_a_manual_records_none():
    state, _ = investigate(wear_policy(), critic=FakeCritic())
    assert state.critique.manual_sections is None
    old = state.critique.model_dump(exclude={"manual_sections"})
    assert type(state.critique).model_validate(old).manual_sections is None


def test_the_follow_up_runs_in_its_own_window_after_research_timed_out():
    """Live, 2026-10-30: the critic named get_settings on a timed-out case and
    the follow-up skipped it. Now it gets its own window and the follow-up
    reserve keeps exactly the time it had."""
    now = [1000.0]
    seen = []
    state = with_critique(
        recheck_state(0.8, timeout_seconds=1200.0, followup_seconds=400.0),
        critique_result(),
    )
    state.started_at = 0.0  # 1,000 s in: research is over, 200 s of reserve left
    assert state.research_seconds(now[0]) == 0
    before = state.remaining_seconds(now[0])

    class Policy:
        def decide(self, view, phase):
            seen.append(view.seconds_for_question)
            now[0] += 30.0  # the question takes 30 s
            return CHECK

        def interpret(self, view, step, evidence):
            now[0] += 20.0
            return Interpretation()

    deps = InvestigationDeps(
        provider=FakeProvider(),
        policy=Policy(),
        clock=lambda: now[0],
        critic=FakeCritic(),
        critic_followup=True,
        recheck_seconds=90.0,
    )
    recheck(state, deps)
    assert state.recheck.outcome == "observed"
    assert seen == [90.0]  # the question was given the follow-up's window
    assert state.remaining_seconds(now[0]) == before  # the reserve is untouched
    assert state.research_seconds(now[0]) == 0


def test_a_follow_up_slower_than_its_window_stops_on_time():
    now = [1000.0]
    state = with_critique(
        recheck_state(0.8, timeout_seconds=1200.0, followup_seconds=400.0),
        critique_result(),
    )
    state.started_at = 0.0
    before = state.remaining_seconds(now[0])

    class Slow:
        def decide(self, view, phase):
            now[0] += 120.0  # longer than the 90 s window
            raise ModelError("no model answered in time")

    deps = InvestigationDeps(
        provider=FakeProvider(),
        policy=Slow(),
        clock=lambda: now[0],
        critic=FakeCritic(),
        critic_followup=True,
        recheck_seconds=90.0,
    )
    recheck(state, deps)
    assert state.recheck.outcome == "out_of_time"
    assert state.remaining_seconds(now[0]) == before


# --- a critic that favours another hypothesis is an objection to the leader ---


def test_a_no_objection_that_prefers_another_hypothesis_still_gets_tested():
    """Live 2026-10-30 (KA-03): the critic said no_objection but favoured H6,
    not the leader, and the follow-up skipped it. Its pick is now tested."""
    state = recheck_state(0.8)
    state.hypotheses.append(
        Hypothesis(id="H2", claim="the batch is bad", confidence=0.3)
    )
    reply = critique_result("no_objection", favoured="H2")
    assert trigger(with_critique(state, reply)) == ("objection", None)


def test_the_record_names_a_verdict_that_disagrees_with_the_pick():
    critic = FakeCritic(critique_result("object", favoured="H1"))
    state, _ = investigate(wear_policy(), critic=critic)
    assert state.critique.verdict_mismatch == (
        "object while favouring the leading H1, with no contradiction or "
        "alternative raised"
    )
    agrees = FakeCritic(critique_result("no_objection", favoured="H1"))
    state, _ = investigate(wear_policy(), critic=agrees)
    assert state.critique.verdict_mismatch is None
