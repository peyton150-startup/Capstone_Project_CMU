import pytest

from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation, WrongSetting
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineStatus
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.helpers import approve_and_run

REASON = "CNC-02's jobs got quicker in one step at tick 200 and rejects rose"


def factory(
    ticks: int = 600, fault: bool = True
) -> tuple[Simulator, ObservationTools, ActionTools, ApprovalDesk]:
    sim = build_line(42, machines=3)
    if fault:
        sim.add_scenario(
            WrongSetting(
                "setting", sim.rng, machine_id="CNC-02", start_tick=200, factor=1.15
            )
        )
    for _ in range(ticks):
        sim.step()
    desk = ApprovalDesk(sim)
    return sim, ObservationTools(sim), ActionTools(sim, desk), desk


def maintenance_messages(tools: ObservationTools) -> list[str]:
    return [
        e["message"]
        for e in tools.get_events(0, 10_000, "CNC-02")
        if e["kind"] == "maintenance"
    ]


def test_an_approved_reset_stops_the_machine_for_ten_ticks_then_restores_the_standard_speed():
    sim, look, act, desk = factory()
    machine = sim.state.machines["CNC-02"]
    assert machine.speed_ratio == pytest.approx(1.15)
    approve_and_run(
        desk, act, act.propose_action("CNC-02", "reset_setting", REASON)["id"]
    )
    assert machine.status is MachineStatus.DOWN and machine.maintenance_until == 610
    act.wait(9)
    assert (
        machine.status is MachineStatus.DOWN
        and machine.speed_ratio == pytest.approx(1.15)
    )
    act.wait(1)
    assert machine.speed_setting is None and machine.maintenance_until is None
    assert maintenance_messages(look) == [
        "setting reset started",
        "setting reset finished: setting was off standard",
    ]
    act.wait(5)
    assert machine.status is MachineStatus.RUNNING


def test_a_needless_reset_says_the_setting_was_already_standard():
    _, look, act, desk = factory(fault=False)
    approve_and_run(
        desk,
        act,
        act.propose_action("CNC-02", "reset_setting", "checking a hunch")["id"],
    )
    act.wait(10)
    assert (
        maintenance_messages(look)[-1]
        == "setting reset finished: setting was already standard"
    )


def test_the_reset_stays_reset_because_the_fault_wrote_only_once():
    sim, look, act, desk = factory()
    approve_and_run(
        desk, act, act.propose_action("CNC-02", "reset_setting", REASON)["id"]
    )
    act.wait(400)
    assert sim.state.machines["CNC-02"].speed_setting is None
    assert {
        row["speed_rpm"] for row in look.get_settings() if row["machine_id"] == "CNC-02"
    } == {850.0}


def test_a_reset_does_not_touch_the_bearing_and_a_bearing_replacement_does_not_touch_the_setting():
    sim, _, act, desk = factory()
    sim.state.machines["CNC-02"].condition.bearing_health = 0.6
    approve_and_run(
        desk, act, act.propose_action("CNC-02", "reset_setting", REASON)["id"]
    )
    act.wait(10)
    assert sim.state.machines["CNC-02"].condition.bearing_health == 0.6

    sim, _, act, desk = factory()
    approve_and_run(
        desk, act, act.propose_action("CNC-02", "replace_bearing", REASON)["id"]
    )
    act.wait(45)
    assert sim.state.machines["CNC-02"].speed_ratio == pytest.approx(1.15)


def test_rejects_return_to_normal_after_the_reset():
    sim, _, act, desk = factory(ticks=2600)
    approve_and_run(
        desk, act, act.propose_action("CNC-02", "reset_setting", REASON)["id"]
    )
    act.wait(10)
    for _ in range(5):
        act.wait(480)

    def rate(start: int, end: int) -> float:
        results = [i for i in sim.state.inspections if start <= i.tick <= end]
        return sum(not i.passed for i in results) / len(results)

    assert rate(400, 2600) > 0.10  # 15% off standard adds about 0.18
    assert rate(2800, 5010) < 0.08


def test_a_broken_down_machine_cannot_be_reset_and_a_busy_one_cannot_start_twice():
    sim = build_line(42, machines=3)
    sim.add_scenario(
        BearingDegradation(
            "bearing", sim.rng, machine_id="CNC-02", start_tick=10, rate=0.01
        )
    )
    while sim.state.machines["CNC-02"].status is not MachineStatus.DOWN:
        sim.step()
    with pytest.raises(ValueError, match="broken down"):
        sim.start_setting_reset("CNC-02")

    sim, _, act, desk = factory()
    approve_and_run(
        desk, act, act.propose_action("CNC-02", "reset_setting", REASON)["id"]
    )
    with pytest.raises(ValueError, match="already under maintenance"):
        sim.start_setting_reset("CNC-02")


def test_the_reset_is_offered_to_the_agent_by_name():
    _, _, act, _ = factory(ticks=10, fault=False)
    assert (
        act.propose_action("CNC-01", "reset_setting", "r")["action"] == "reset_setting"
    )
    with pytest.raises(ValueError, match="reset_setting"):
        act.propose_action("CNC-01", "recalibrate", "r")
