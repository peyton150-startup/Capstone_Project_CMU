import json

import pytest

from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineStatus
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools

REASON = "vibration and job times rising for 300 ticks"


def factory(ticks: int = 600, fault: bool = True) -> tuple[Simulator, ObservationTools, ActionTools, ApprovalDesk]:
    sim = build_line(42, machines=3)
    if fault:
        sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-02", start_tick=50, rate=0.0006))
    for _ in range(ticks):
        sim.step()
    desk = ApprovalDesk(sim)
    return sim, ObservationTools(sim), ActionTools(sim, desk), desk


def public(cls) -> set[str]:
    return {name for name in dir(cls) if not name.startswith("_")}


def test_the_agent_can_wait_propose_and_check_but_not_decide():
    assert public(ActionTools) == {"wait", "propose_action", "get_proposals"}
    assert {"approve", "reject"} <= public(ApprovalDesk)
    assert not {"approve", "reject"} & (public(ActionTools) | public(ObservationTools))


def test_proposing_changes_nothing_in_the_factory():
    sim, _, act, _ = factory()
    before = (sim.clock.tick, sim.state.model_copy(deep=True), sim.readings, sim.event_log.events)
    act.propose_action("CNC-02", "replace_bearing", REASON)
    assert (sim.clock.tick, sim.state, sim.readings, sim.event_log.events) == before


def test_a_proposal_is_recorded_as_pending_with_its_reason_and_tick():
    _, _, act, desk = factory()
    first = act.propose_action("CNC-02", "replace_bearing", f"  {REASON}  ")
    assert first == {
        "id": 1,
        "machine_id": "CNC-02",
        "action": "replace_bearing",
        "reason": REASON,
        "proposed_tick": 600,
        "status": "pending",
        "decided_tick": None,
        "note": "",
    }
    assert act.propose_action("CNC-01", "replace_bearing", "second opinion")["id"] == 2
    assert [p["id"] for p in desk.pending()] == [1, 2]


@pytest.mark.parametrize(
    "machine_id, action, reason",
    [("CNC-99", "replace_bearing", REASON), ("CNC-02", "set_on_fire", REASON), ("CNC-02", "replace_bearing", "   ")],
)
def test_bad_proposals_are_refused_and_not_recorded(machine_id, action, reason):
    _, _, act, desk = factory()
    with pytest.raises(ValueError):
        act.propose_action(machine_id, action, reason)
    assert desk.proposals() == []


def test_approving_starts_the_repair_and_marks_the_proposal():
    sim, look, act, desk = factory()
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    assert sim.state.machines["CNC-02"].status is not MachineStatus.DOWN  # still in service
    decided = desk.approve(proposal["id"], note="go ahead at shift change")
    assert (decided["status"], decided["decided_tick"], decided["note"]) == ("approved", 600, "go ahead at shift change")
    assert sim.state.machines["CNC-02"].status is MachineStatus.DOWN
    assert look.get_events(600, 600, "CNC-02")[-1]["message"] == "bearing replacement started"
    assert act.get_proposals()[0]["status"] == "approved"
    assert desk.pending() == []


def test_rejecting_leaves_the_factory_alone():
    sim, _, act, desk = factory()
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    decided = desk.reject(proposal["id"], note="not enough evidence yet")
    assert (decided["status"], decided["note"]) == ("rejected", "not enough evidence yet")
    assert sim.state.machines["CNC-02"].maintenance_until is None
    assert not [e for e in sim.event_log.events if e.kind == "maintenance"]


def test_a_proposal_is_decided_once_and_unknown_ones_are_refused():
    _, _, act, desk = factory()
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    desk.reject(proposal["id"])
    for decide in (desk.approve, desk.reject):
        with pytest.raises(ValueError):
            decide(proposal["id"])
        with pytest.raises(ValueError):
            decide(99)


def test_an_approval_that_cannot_start_leaves_the_proposal_pending():
    _, _, act, desk = factory()
    first = act.propose_action("CNC-02", "replace_bearing", REASON)
    second = act.propose_action("CNC-02", "replace_bearing", "asking again")
    desk.approve(first["id"])
    with pytest.raises(ValueError):
        desk.approve(second["id"])  # the machine is already under repair
    assert [p["status"] for p in desk.proposals()] == ["approved", "pending"]


def test_the_agent_gets_copies_it_cannot_use_to_approve_itself():
    sim, _, act, _ = factory()
    act.propose_action("CNC-02", "replace_bearing", REASON)
    act.get_proposals()[0]["status"] = "approved"
    assert act.get_proposals()[0]["status"] == "pending"
    assert sim.state.machines["CNC-02"].maintenance_until is None


def test_the_whole_loop_propose_approve_wait_verify():
    sim, look, act, desk = factory()
    before = [r["value"] for r in look.get_readings("CNC-02", "vibration", 500, 600) if r["value"] > 1.0]
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    desk.approve(proposal["id"])
    act.wait(45)
    finished = [e for e in look.get_events(600, 645, "CNC-02") if e["kind"] == "maintenance"][-1]
    assert finished["message"] in (
        "bearing replacement finished: old bearing worn",
        "bearing replacement finished: old bearing badly worn",
    )
    act.wait(300)
    after = [r["value"] for r in look.get_readings("CNC-02", "vibration", 700, 945) if r["value"] > 1.0]
    assert sum(after) / len(after) < sum(before) / len(before) - 0.3
    assert sim.state.machines["CNC-02"].condition.bearing_health == 1.0


def test_answers_are_plain_data():
    _, _, act, desk = factory()
    act.propose_action("CNC-02", "replace_bearing", REASON)
    for answer in (act.get_proposals(), desk.pending()):
        assert json.loads(json.dumps(answer)) == answer
