import json

import pytest

from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineStatus
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools

REASON = "vibration and job times rising for 300 ticks"


def factory(
    ticks: int = 600, fault: bool = True
) -> tuple[Simulator, ObservationTools, ActionTools, ApprovalDesk]:
    sim = build_line(42, machines=3)
    if fault:
        sim.add_scenario(
            BearingDegradation(
                "bearing", sim.rng, machine_id="CNC-02", start_tick=50, rate=0.0006
            )
        )
    for _ in range(ticks):
        sim.step()
    desk = ApprovalDesk(sim)
    return sim, ObservationTools(sim), ActionTools(sim, desk), desk


def public(cls) -> set[str]:
    return {name for name in dir(cls) if not name.startswith("_")}


def test_the_agent_can_wait_propose_check_and_execute_but_not_decide():
    assert public(ActionTools) == {
        "wait",
        "propose_action",
        "get_proposals",
        "execute_action",
    }
    assert {"approve", "reject"} <= public(ApprovalDesk)
    assert not {"approve", "reject"} & (public(ActionTools) | public(ObservationTools))


def test_proposing_changes_nothing_in_the_factory():
    sim, _, act, _ = factory()
    before = (
        sim.clock.tick,
        sim.state.model_copy(deep=True),
        sim.readings,
        sim.event_log.events,
    )
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
        "executed_tick": None,
        "finish_tick": None,
    }
    assert act.propose_action("CNC-01", "replace_bearing", "second opinion")["id"] == 2
    assert [p["id"] for p in desk.pending()] == [1, 2]


@pytest.mark.parametrize(
    "machine_id, action, reason",
    [
        ("CNC-99", "replace_bearing", REASON),
        ("CNC-02", "set_on_fire", REASON),
        ("CNC-02", "replace_bearing", "   "),
    ],
)
def test_bad_proposals_are_refused_and_not_recorded(machine_id, action, reason):
    _, _, act, desk = factory()
    with pytest.raises(ValueError):
        act.propose_action(machine_id, action, reason)
    assert desk.proposals() == []


def test_approving_is_permission_and_changes_nothing_in_the_factory():
    sim, _, act, desk = factory()
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    before = (sim.state.model_copy(deep=True), sim.event_log.events)
    decided = desk.approve(proposal["id"], note="go ahead at shift change")
    assert (decided["status"], decided["decided_tick"], decided["note"]) == (
        "approved",
        600,
        "go ahead at shift change",
    )
    assert (decided["executed_tick"], decided["finish_tick"]) == (None, None)
    assert (sim.state, sim.event_log.events) == before  # still running, still worn
    assert desk.pending() == []


def test_executing_an_approved_proposal_starts_the_repair_and_says_when_it_ends():
    sim, look, act, desk = factory()
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    desk.approve(proposal["id"])
    started = act.execute_action(proposal["id"])
    assert started == {
        "proposal_id": 1,
        "machine_id": "CNC-02",
        "action": "replace_bearing",
        "started_tick": 600,
        "finish_tick": sim.state.machines["CNC-02"].maintenance_until,
    }
    assert started["finish_tick"] > 600
    assert sim.state.machines["CNC-02"].status is MachineStatus.DOWN
    assert (
        look.get_events(600, 600, "CNC-02")[-1]["message"]
        == "bearing replacement started"
    )
    [seen] = act.get_proposals()
    assert (seen["status"], seen["executed_tick"], seen["finish_tick"]) == (
        "approved",
        600,
        started["finish_tick"],
    )


@pytest.mark.parametrize("decision", ["none", "reject"])
def test_the_agent_cannot_execute_what_a_human_has_not_approved(decision):
    sim, _, act, desk = factory()
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    if decision == "reject":
        desk.reject(proposal["id"], note="not enough evidence yet")
    with pytest.raises(ValueError, match="not approved"):
        act.execute_action(proposal["id"])
    assert sim.state.machines["CNC-02"].maintenance_until is None
    assert not [e for e in sim.event_log.events if e.kind == "maintenance"]
    assert act.get_proposals()[0]["executed_tick"] is None


def test_an_approval_can_be_used_only_once():
    sim, _, act, desk = factory()
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    desk.approve(proposal["id"])
    started = act.execute_action(proposal["id"])
    act.wait(started["finish_tick"] - started["started_tick"] + 1)
    assert sim.state.machines["CNC-02"].maintenance_until is None  # work is done
    with pytest.raises(ValueError, match="already carried out"):
        act.execute_action(proposal["id"])
    assert sim.state.machines["CNC-02"].maintenance_until is None


@pytest.mark.parametrize("proposal_id", [99, 0, "1", 1.0, True, None])
def test_unknown_or_malformed_proposal_ids_are_refused(proposal_id):
    sim, _, act, desk = factory()
    desk.approve(act.propose_action("CNC-02", "replace_bearing", REASON)["id"])
    with pytest.raises(ValueError):
        act.execute_action(proposal_id)
    assert sim.state.machines["CNC-02"].maintenance_until is None


def test_work_that_cannot_start_leaves_the_proposal_approved_and_not_carried_out():
    _, _, act, desk = factory()
    first = act.propose_action("CNC-02", "replace_bearing", REASON)
    second = act.propose_action("CNC-02", "replace_bearing", "asking again")
    desk.approve(first["id"])
    desk.approve(second["id"])
    act.execute_action(first["id"])
    with pytest.raises(ValueError, match="already under maintenance"):
        act.execute_action(second["id"])
    done = [(p["status"], p["executed_tick"]) for p in desk.proposals()]
    assert done == [("approved", 600), ("approved", None)]


def test_an_edited_copy_of_a_proposal_does_not_unlock_execution():
    sim, _, act, _ = factory()
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    act.get_proposals()[0]["status"] = "approved"
    with pytest.raises(ValueError, match="not approved"):
        act.execute_action(proposal["id"])
    assert sim.state.machines["CNC-02"].maintenance_until is None


def test_rejecting_leaves_the_factory_alone():
    sim, _, act, desk = factory()
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    decided = desk.reject(proposal["id"], note="not enough evidence yet")
    assert (decided["status"], decided["note"]) == (
        "rejected",
        "not enough evidence yet",
    )
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


def test_the_agent_gets_copies_it_cannot_use_to_approve_itself():
    sim, _, act, _ = factory()
    act.propose_action("CNC-02", "replace_bearing", REASON)
    act.get_proposals()[0]["status"] = "approved"
    assert act.get_proposals()[0]["status"] == "pending"
    assert sim.state.machines["CNC-02"].maintenance_until is None


def test_the_whole_loop_propose_approve_execute_wait_verify():
    sim, look, act, desk = factory()
    before = [
        r["value"]
        for r in look.get_readings("CNC-02", "vibration", 500, 600)
        if r["value"] > 1.0
    ]
    proposal = act.propose_action("CNC-02", "replace_bearing", REASON)
    desk.approve(proposal["id"])
    started = act.execute_action(proposal["id"])
    act.wait(started["finish_tick"] - started["started_tick"])
    finished = [
        e for e in look.get_events(600, 645, "CNC-02") if e["kind"] == "maintenance"
    ][-1]
    assert finished["message"] in (
        "bearing replacement finished: old bearing worn",
        "bearing replacement finished: old bearing badly worn",
    )
    act.wait(300)
    after = [
        r["value"]
        for r in look.get_readings("CNC-02", "vibration", 700, 945)
        if r["value"] > 1.0
    ]
    assert sum(after) / len(after) < sum(before) / len(before) - 0.3
    assert sim.state.machines["CNC-02"].condition.bearing_health == 1.0


def test_answers_are_plain_data():
    _, _, act, desk = factory()
    act.propose_action("CNC-02", "replace_bearing", REASON)
    for answer in (act.get_proposals(), desk.pending()):
        assert json.loads(json.dumps(answer)) == answer
