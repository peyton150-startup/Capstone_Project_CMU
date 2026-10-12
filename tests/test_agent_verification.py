import json

import pytest

from capstone.agent.artifacts import (
    AgentConclusion,
    TerminationReason,
    VerificationCheck,
)
from capstone.agent.investigation import (
    INVESTIGATION_GRAPH,
    NO_ACTION_PREDICTION,
    run_investigation,
)
from capstone.agent.loop import InvestigationDeps
from capstone.agent.policy import ActionRequest, Interpretation
from capstone.contracts.hypotheses import Hypothesis
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.helpers import ScriptedPolicy, ask, new_state

PREDICTION = "vibration on CNC-02 returns to its earlier level"


class Factory:
    """A real simulated line whose CNC-02 is wearing, with its desk and provider."""

    def __init__(self):
        self.sim = build_line(42, machines=3)
        self.sim.add_scenario(
            BearingDegradation(
                "bearing",
                self.sim.rng,
                machine_id="CNC-02",
                start_tick=100,
                rate=0.0006,
            )
        )
        for _ in range(600):
            self.sim.step()
        self.desk = ApprovalDesk(self.sim)
        self.provider = SimulatorFactoryProvider(
            ObservationTools(self.sim), ActionTools(self.sim, self.desk)
        )

    def approve(self, proposal):
        self.desk.approve(proposal.proposal_id, note="go ahead")

    def reject(self, proposal):
        self.desk.reject(proposal.proposal_id, note="not yet")


def vibration(from_tick, to_tick, **extra):
    return ask(
        "get_sensor_summary",
        machine_id="CNC-02",
        sensor="vibration",
        from_tick=from_tick,
        to_tick=to_tick,
        **extra,
    )


def look_again(state):
    """The vibration on CNC-02 since the work finished, or since the conclusion."""
    since = state.action_finish_tick or state.concluded_tick
    return vibration(since + 1, state.last_tick)


def mean(state, evidence_id):
    [evidence] = [e for e in state.evidence if e.id == evidence_id]
    return json.loads(evidence.content)["mean"]


def compare_with_before(state):
    """The agent's own judgement: has the vibration come down from what E2 showed?"""
    latest = state.evidence[-1].id
    fell = mean(state, latest) < mean(state, "E2") - 0.5
    return VerificationCheck(
        outcome="resolved" if fell else "not_resolved",
        prediction="rewritten after the fact",
        evidence_ids=("E2", latest),
        checked_tick=1,
    )


WAIT_THEN_LOOK = (ask("wait", ticks=300), look_again)


def policy(
    *,
    machine_id="CNC-02",
    recommendation="intervene",
    verify=WAIT_THEN_LOOK,
    judge=compare_with_before,
):
    def interpret(state, step, evidence):
        if step.hypothesis_id is None:
            return Interpretation()
        return Interpretation(
            hypotheses=(
                Hypothesis(
                    id="H1",
                    claim="CNC-02 is wearing",
                    confidence=0.95,
                    supporting_evidence_ids=("E2", evidence.id),
                ),
            )
        )

    concluded = AgentConclusion(
        diagnosis="wear on CNC-02",
        confidence=0.95,
        recommendation=recommendation,
        hypothesis_id="H1",
        evidence_ids=("E2", "E3"),
    )
    request = ActionRequest(
        machine_id=machine_id,
        action="replace_bearing",
        reason="vibration has climbed for hundreds of ticks",
        prediction=PREDICTION,
    )
    return ScriptedPolicy(
        {
            "investigate": [vibration(400, 600)],
            "test": [
                ask(
                    "get_events",
                    hypothesis_id="H1",
                    machine_id="CNC-02",
                    from_tick=0,
                    to_tick=600,
                )
            ],
            "verify": list(verify),
        },
        interpret,
        hypothesize=lambda state: Interpretation(
            hypotheses=(
                Hypothesis(
                    id="H1",
                    claim="CNC-02 is wearing",
                    confidence=0.6,
                    supporting_evidence_ids=("E2",),
                ),
            )
        ),
        conclude=lambda state: (concluded, request),
        judge=judge,
    )


def investigate(agent, human="approve", *, factory=None, state=None):
    factory = factory or Factory()
    state = state or new_state()
    state.last_tick = None
    deps = InvestigationDeps(
        provider=factory.provider,
        policy=agent,
        clock=lambda: 0.0,
        human_review=getattr(factory, human) if human else None,
    )
    return run_investigation(state, deps), factory


def verify_record(state):
    return [d for d in state.decisions if d.phase == "verify"][-1]


# --- the agent finds out for itself whether the fix worked -----------------


def test_a_fix_that_worked_is_found_by_looking_again():
    state, factory = investigate(policy())
    check = state.verification
    latest = state.evidence[-1]
    assert check.outcome == "resolved"
    assert check.evidence_ids == ("E2", latest.id)
    assert mean(state, latest.id) < mean(state, "E2") - 0.5
    assert latest.observed_tick == 945 > state.action_finish_tick == 645
    assert factory.sim.state.machines["CNC-02"].condition.bearing_health == 1.0


def test_a_fix_on_the_wrong_machine_is_found_not_to_have_worked():
    state, factory = investigate(policy(machine_id="CNC-01"))
    assert state.action_carried_out  # the repair really was done, on CNC-01
    assert state.proposed_action.machine_id == "CNC-01"
    assert state.verification.outcome == "not_resolved"
    assert mean(state, state.evidence[-1].id) > mean(state, "E2")
    # Nobody told the agent: it used the same judgement as in the test above.
    assert factory.sim.state.machines["CNC-02"].condition.bearing_health < 1.0


def test_no_answer_key_is_involved_in_the_judgement():
    state, factory = investigate(policy())
    text = state.model_dump_json().lower()
    hidden = ("bearing_health", "defect_risk", "standard_speed", "ground_truth")
    assert not [word for word in hidden if word in text]
    assert factory.sim.ground_truth()


# --- what the policy cannot adjust afterwards ------------------------------


def test_the_prediction_is_the_one_recorded_before_the_action():
    state, _ = investigate(policy())
    assert state.verification.prediction == PREDICTION


def test_the_tick_of_the_check_comes_from_the_evidence_not_from_the_policy():
    state, _ = investigate(policy())
    assert state.verification.checked_tick == state.evidence[-1].observed_tick == 945


# --- a judgement needs evidence from after the work ------------------------


def cite(*evidence_ids, outcome="resolved"):
    return lambda state: VerificationCheck(
        outcome=outcome, prediction="x", evidence_ids=evidence_ids
    )


@pytest.mark.parametrize("claimed", ["resolved", "not_resolved"])
def test_a_judgement_resting_only_on_earlier_evidence_is_inconclusive(claimed):
    state, _ = investigate(policy(judge=cite("E2", outcome=claimed)))
    check = state.verification
    assert check.outcome == "inconclusive"
    assert check.evidence_ids == ("E2",)
    # The agent did look afterwards; it just did not rest its judgement on that.
    assert check.checked_tick == 945
    assert verify_record(state).outcome == "decided"


def test_the_wait_for_the_work_to_finish_is_not_evidence_of_the_result():
    state, _ = investigate(policy(verify=()))
    waited = [e for e in state.evidence if e.source_id == "simulator:wait"]
    assert waited[-1].observed_tick == state.action_finish_tick
    assert state.verification.outcome == "not_performed"


def test_looking_without_letting_time_pass_after_the_work_does_not_count():
    look_at_once = (lambda state: vibration(400, state.last_tick),)
    state, _ = investigate(policy(verify=look_at_once, judge=cite("E8")))
    assert state.evidence[-1].observed_tick == state.action_finish_tick
    assert state.verification.outcome == "not_performed"


def test_with_nothing_looked_at_the_check_was_not_performed():
    agent = policy(verify=())
    state, _ = investigate(agent)
    check = state.verification
    assert (check.outcome, check.evidence_ids, check.checked_tick) == (
        "not_performed",
        (),
        None,
    )
    assert check.prediction == PREDICTION
    assert "judge" not in agent.asked  # there was nothing to judge
    assert state.action_carried_out  # the repair itself still happened


def failing_judge(state):
    raise ValueError("cannot tell")


@pytest.mark.parametrize(
    "judge",
    [failing_judge, cite("E99"), lambda state: "resolved", cite(outcome="resolved")],
    ids=["policy fails", "cites missing evidence", "not a check", "cites nothing"],
)
def test_an_unusable_judgement_is_inconclusive(judge):
    state, _ = investigate(policy(judge=judge))
    assert state.verification.outcome == "inconclusive"
    assert state.verification.checked_tick == 945
    assert state.verification.prediction == PREDICTION


def test_a_policy_that_looked_cannot_report_that_it_did_not():
    state, _ = investigate(policy(judge=cite("E9", outcome="not_performed")))
    assert state.verification.outcome == "inconclusive"


def test_the_policy_may_honestly_say_it_cannot_tell():
    agent = policy(
        judge=lambda state: VerificationCheck(
            outcome="inconclusive",
            prediction="x",
            evidence_ids=(state.evidence[-1].id,),
        )
    )
    state, _ = investigate(agent)
    assert state.verification.outcome == "inconclusive"
    assert state.verification.evidence_ids == (state.evidence[-1].id,)


# --- doing nothing is checked too ------------------------------------------


def test_a_no_action_conclusion_is_checked_by_waiting_and_looking_again():
    agent = policy(
        recommendation="no_action",
        verify=(ask("wait", ticks=60), look_again),
        judge=lambda state: VerificationCheck(
            outcome="not_resolved",
            prediction="x",
            evidence_ids=(state.evidence[-1].id,),
        ),
    )
    state, factory = investigate(agent)
    assert state.proposed_action is None and not state.action_carried_out
    assert factory.desk.proposals() == []
    check = state.verification
    assert check.prediction == NO_ACTION_PREDICTION
    assert check.outcome == "not_resolved"  # the wear was still there
    assert check.checked_tick == 660 > state.concluded_tick == 600


def test_a_no_action_check_also_needs_time_to_have_passed():
    agent = policy(
        recommendation="no_action",
        verify=(lambda state: vibration(500, state.last_tick),),
        judge=cite("E4"),
    )
    state, _ = investigate(agent)
    assert state.verification.outcome == "not_performed"


# --- when there is nothing of the agent's to check -------------------------


@pytest.mark.parametrize(
    "human, recommendation, status",
    [
        ("reject", "intervene", "rejected"),
        (None, "intervene", "pending"),
        ("approve", "escalate", None),
    ],
    ids=["rejected", "no answer", "escalated"],
)
def test_nothing_is_verified_when_nothing_was_done(human, recommendation, status):
    agent = policy(recommendation=recommendation)
    state, _ = investigate(agent, human)
    assert state.verification is None
    assert "judge" not in agent.asked
    assert "verify" not in {d.phase for d in state.decisions}
    assert (state.proposed_action.status if state.proposed_action else None) == status


def test_an_approval_that_was_never_carried_out_is_not_verified():
    agent = policy()
    state, _ = investigate(agent, state=new_state(followup_tool_calls=2))
    assert state.proposed_action.status == "approved"
    assert not state.action_carried_out
    assert state.verification is None
    assert "judge" not in agent.asked


def test_work_that_was_started_but_not_seen_to_finish_is_not_verified():
    agent = policy()
    state, _ = investigate(agent, state=new_state(followup_tool_calls=3))
    assert state.action_carried_out
    assert state.last_tick < state.action_finish_tick
    assert state.verification is None


# --- limits ----------------------------------------------------------------


def test_checking_uses_the_follow_up_allowance_and_leaves_the_stop_reason():
    state, _ = investigate(policy())
    assert state.research_tool_calls == 3
    assert state.followup_tool_calls_used == 6  # ask, read, start, wait, wait, look
    assert state.termination_reason is TerminationReason.DIAGNOSIS_SUPPORTED


def test_with_the_allowance_used_up_before_looking_the_check_was_not_performed():
    state, _ = investigate(policy(), state=new_state(followup_tool_calls=4))
    assert state.action_carried_out
    assert state.last_tick == state.action_finish_tick
    assert state.verification.outcome == "not_performed"


# --- the shape of the graph ------------------------------------------------


def test_the_check_is_reached_only_after_finished_work_or_a_no_action_conclusion():
    arrows = {
        line.strip()
        for line in INVESTIGATION_GRAPH.render().splitlines()
        if "verify" in line and "-->" in line
    }
    assert arrows == {
        "approved --> verify",
        "work_finished --> verify",
        "verify --> [*]",
    }
