import json

import pytest

from capstone.agent.artifacts import AgentConclusion, TerminationReason
from capstone.agent.investigation import run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.agent.policy import ActionRequest, Interpretation
from capstone.contracts.hypotheses import Hypothesis
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.state import MachineStatus
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.helpers import ScriptedPolicy, ask, new_state

RESEARCH = [
    "simulator:get_time",
    "simulator:get_sensor_summary",
    "simulator:get_events",
]
ASKED = ["simulator:propose_action", "simulator:get_proposals"]


class Factory:
    """A real simulated line with a worn machine, its desk, and the agent's provider."""

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
        self.machine = self.sim.state.machines["CNC-02"]

    def approve(self, note=""):
        return lambda proposal: self.desk.approve(proposal.proposal_id, note=note)

    def reject(self, note=""):
        return lambda proposal: self.desk.reject(proposal.proposal_id, note=note)

    def maintenance(self):
        return [e.message for e in self.sim.event_log.events if e.kind == "maintenance"]


def wear(confidence, *supporting):
    return Hypothesis(
        id="H1",
        claim="CNC-02 is wearing",
        confidence=confidence,
        supporting_evidence_ids=supporting,
    )


def interpret(state, step, evidence):
    if step.hypothesis_id is None:
        return Interpretation()
    return Interpretation(hypotheses=(wear(0.95, "E2", evidence.id),))


def policy(*, recommendation="intervene", machine_id="CNC-02", extra_research=()):
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
        prediction="vibration on CNC-02 returns to its earlier level",
    )
    return ScriptedPolicy(
        {
            "investigate": [
                ask(
                    "get_sensor_summary",
                    machine_id="CNC-02",
                    sensor="vibration",
                    from_tick=0,
                    to_tick=600,
                ),
                *extra_research,
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
        },
        interpret,
        hypothesize=lambda state: Interpretation(hypotheses=(wear(0.6, "E2"),)),
        conclude=lambda state: (concluded, request),
    )


def investigate(factory, human=None, *, agent=None, state=None, **settings):
    state = state or new_state()
    state.last_tick = None
    deps = InvestigationDeps(
        provider=factory.provider,
        policy=agent or policy(),
        clock=lambda: 0.0,
        human_review=human,
        **settings,
    )
    return run_investigation(state, deps)


def sources(state):
    return [e.source_id for e in state.evidence]


def content(state, source):
    """What the factory answered for the last call to one tool."""
    answers = [e for e in state.evidence if e.source_id == f"simulator:{source}"]
    return json.loads(answers[-1].content)


# --- approved: asked, decided, read back, started, finished ----------------


def test_an_approved_action_is_asked_for_read_back_started_and_waited_out():
    factory = Factory()
    state = investigate(factory, factory.approve("go ahead at shift change"))

    assert sources(state) == [
        *RESEARCH,
        *ASKED,
        "simulator:execute_action",
        "simulator:wait",
    ]
    assert state.proposed_action.model_dump() == {
        "proposal_id": 1,
        "machine_id": "CNC-02",
        "action": "replace_bearing",
        "reason": "vibration has climbed for hundreds of ticks",
        "status": "approved",
    }
    started = content(state, "execute_action")
    assert state.action_carried_out
    assert (state.action_started_tick, state.action_finish_tick) == (
        600,
        started["finish_tick"],
    )
    assert state.last_tick == started["finish_tick"] == factory.sim.clock.tick
    assert factory.maintenance()[0] == "bearing replacement started"
    assert factory.maintenance()[-1].startswith("bearing replacement finished")
    assert factory.machine.condition.bearing_health == 1.0


def test_the_human_s_note_is_kept_as_evidence():
    factory = Factory()
    state = investigate(factory, factory.approve("go ahead at shift change"))
    [mine] = content(state, "get_proposals")
    assert (mine["id"], mine["status"], mine["note"]) == (
        1,
        "approved",
        "go ahead at shift change",
    )


def test_the_loop_makes_the_calls_not_the_policy():
    factory = Factory()
    agent = policy()
    state = investigate(factory, factory.approve(), agent=agent)
    followup = [d for d in state.decisions if d.phase in ("propose", "execute")]
    assert [d.tool for d in followup] == [
        "propose_action",
        "get_proposals",
        "execute_action",
        "wait",
    ]
    # After concluding, the policy was asked nothing until the check.
    assert agent.asked == ["plan", "hypothesize", "conclude"]
    asked_after = [s for s in agent.seen_states if s.proposed_action]
    assert all(s.action_carried_out for s in asked_after)


def test_follow_up_calls_use_their_own_allowance_and_leave_the_stop_reason_alone():
    factory = Factory()
    state = investigate(factory, factory.approve())
    assert state.followup_tool_calls_used == 4
    assert state.research_tool_calls == 3
    assert state.termination_reason is TerminationReason.DIAGNOSIS_SUPPORTED


def test_a_long_repair_is_waited_out_in_steps_the_factory_accepts():
    factory = Factory()
    state = investigate(factory, factory.approve(), max_wait_ticks=20)
    waits = [d.arguments["ticks"] for d in state.decisions if d.tool == "wait"]
    assert len(waits) > 1 and max(waits) <= 20
    assert sum(waits) == state.action_finish_tick - state.action_started_tick
    assert factory.maintenance()[-1].startswith("bearing replacement finished")


# --- not approved: nothing is started --------------------------------------


def untouched(factory, state):
    return (
        not state.action_carried_out
        and state.action_finish_tick is None
        and factory.machine.maintenance_until is None
        and factory.machine.status is not MachineStatus.DOWN
        and factory.maintenance() == []
        and factory.sim.clock.tick == 600
        and "simulator:execute_action" not in sources(state)
        and "simulator:wait" not in sources(state)
    )


def test_a_rejection_stops_after_the_read_back_and_keeps_the_reason():
    factory = Factory()
    state = investigate(factory, factory.reject("bearing was replaced last week"))
    assert sources(state) == [*RESEARCH, *ASKED]
    assert state.proposed_action.status == "rejected"
    [mine] = content(state, "get_proposals")
    assert mine["note"] == "bearing was replaced last week"
    assert untouched(factory, state)


def test_with_no_human_answer_the_proposal_stays_pending():
    factory = Factory()
    state = investigate(factory, human=None)
    assert sources(state) == [*RESEARCH, *ASKED]
    assert state.proposed_action.status == "pending"
    assert [p["status"] for p in factory.desk.proposals()] == ["pending"]
    assert untouched(factory, state)


@pytest.mark.parametrize("recommendation", ["no_action", "escalate"])
def test_nothing_is_asked_when_the_conclusion_wants_no_change(recommendation):
    factory = Factory()
    state = investigate(
        factory, factory.approve(), agent=policy(recommendation=recommendation)
    )
    assert sources(state) == RESEARCH
    assert state.proposed_action is None
    assert factory.desk.proposals() == []
    assert state.followup_tool_calls_used == 0
    assert untouched(factory, state)


def test_a_proposal_the_factory_refuses_is_never_put_to_the_human():
    factory = Factory()
    asked = []
    state = investigate(factory, asked.append, agent=policy(machine_id="CNC-99"))
    assert asked == []
    assert state.proposed_action.status == "not_submitted"
    assert state.proposed_action.proposal_id is None
    assert factory.desk.proposals() == []
    assert [d.outcome for d in state.decisions if d.phase == "propose"] == [
        "tool_error"
    ]
    assert untouched(factory, state)


# --- approved but not carried out ------------------------------------------


def test_an_approval_with_no_calls_left_is_not_a_fix():
    factory = Factory()
    state = new_state(followup_tool_calls=2)
    investigate(factory, factory.approve(), state=state)
    assert state.proposed_action.status == "approved"
    last = state.decisions[-1]
    assert (last.phase, last.outcome) == ("execute", "stopped")
    assert last.termination_reason is TerminationReason.MAX_TOOL_CALLS
    assert untouched(factory, state)


def test_with_no_allowance_at_all_the_action_is_never_submitted():
    factory = Factory()
    state = new_state(followup_tool_calls=0)
    investigate(factory, factory.approve(), state=state)
    assert state.proposed_action.status == "not_submitted"
    assert factory.desk.proposals() == []
    assert untouched(factory, state)


def test_work_that_cannot_start_is_recorded_as_approved_and_not_carried_out():
    factory = Factory()

    def approve_then_someone_else_starts_a_repair(proposal):
        factory.desk.approve(proposal.proposal_id, note="go ahead")
        factory.sim.start_bearing_replacement("CNC-02")

    state = investigate(factory, approve_then_someone_else_starts_a_repair)
    assert state.proposed_action.status == "approved"
    assert not state.action_carried_out
    assert [(d.tool, d.outcome) for d in state.decisions if d.phase == "execute"] == [
        ("execute_action", "tool_error")
    ]
    assert "simulator:execute_action" not in sources(state)
    assert "simulator:wait" not in sources(state)  # nothing of its own to wait for
    assert content(state, "get_proposals")[0]["note"] == "go ahead"


# --- the decision is read from the factory ---------------------------------


def test_the_decision_is_read_even_if_the_same_question_was_asked_this_tick():
    factory = Factory()
    agent = policy(extra_research=[ask("get_proposals")])
    state = investigate(factory, factory.approve(), agent=agent)
    assert state.repeated_calls == 0
    assert state.proposed_action.status == "approved"
    assert state.action_carried_out


def test_a_human_hook_that_decides_nothing_does_not_count_as_approval():
    factory = Factory()
    seen = []
    state = investigate(factory, seen.append)
    assert [p.proposal_id for p in seen] == [1]
    assert seen[0].status == "pending"
    assert state.proposed_action.status == "pending"
    assert untouched(factory, state)


def test_the_proposal_handed_to_the_human_cannot_be_used_to_approve():
    factory = Factory()

    def tamper(proposal):
        with pytest.raises(Exception):
            proposal.status = "approved"

    state = investigate(factory, tamper)
    assert state.proposed_action.status == "pending"
    assert untouched(factory, state)


def test_no_hidden_truth_reaches_working_memory_on_the_action_path():
    factory = Factory()
    state = investigate(factory, factory.approve())
    text = state.model_dump_json().lower()
    hidden = ("bearing_health", "defect_risk", "standard_speed", "ground_truth")
    assert not [word for word in hidden if word in text]
    assert factory.sim.ground_truth()
