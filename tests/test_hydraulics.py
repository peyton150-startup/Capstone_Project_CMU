"""The hydraulic-leak fault pack: only machines that have hydraulics (Future Work 8 D)."""

import pytest

from capstone.faults import BY_KIND, DEFAULT_DRAW
from capstone.simulator.events import ThresholdAlarm
from capstone.simulator.generator import FAULTS, build_scenario
from capstone.simulator.line import HYDRAULIC_POSITIONS, build_line
from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import HydraulicLeak, defect_mark
from capstone.simulator.sensors import HydraulicPressureSensor, SensorReading
from capstone.simulator.state import MachineCondition, MachineState, MachineStatus
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.errors import ToolInputError
from capstone.tools.observation import ObservationTools
from tests.helpers import approve_and_run

REASON = "CNC-02 hydraulic pressure fell below its alarm and rejects rose"


def machine(*, seals=1.0, status=MachineStatus.RUNNING, load=0.5):
    return MachineState(
        id="CNC-02",
        status=status,
        load=load,
        has_hydraulics=True,
        condition=MachineCondition(hydraulic_health=seals),
    )


def exact(m: MachineState) -> float:
    sensor = HydraulicPressureSensor("CNC-02", RandomSource(1), noise_sd=0.0)
    return sensor.read(m, 0).value


def reading(sensor: str, value: float, unit: str) -> SensorReading:
    return SensorReading(
        sensor=sensor, machine_id="CNC-02", tick=1, value=value, unit=unit
    )


def leaking_line(ticks: int, *, machine_id="CNC-02", rate=0.001):
    sim = build_line(42, machines=3)
    sim.add_scenario(
        HydraulicLeak("leak", sim.rng, machine_id=machine_id, start_tick=100, rate=rate)
    )
    for _ in range(ticks):
        sim.step()
    return sim


# --- equipment: an observable fact ---


def test_only_some_positions_have_hydraulics_and_every_line_has_one():
    assert HYDRAULIC_POSITIONS[:3] == (False, True, False)
    for size in range(3, 9):
        sim = build_line(1, machines=size)
        equipped = [m.id for m in sim.state.machines.values() if m.has_hydraulics]
        assert "CNC-02" in equipped
        assert equipped == [
            f"CNC-{i + 1:02d}" for i in range(size) if HYDRAULIC_POSITIONS[i]
        ]


def test_the_agent_sees_which_machines_have_hydraulics():
    sim = build_line(1, machines=5)
    rows = ObservationTools(sim).list_machines()
    assert {row["machine_id"]: row["hydraulics"] for row in rows} == {
        "CNC-01": False,
        "CNC-02": True,
        "CNC-03": False,
        "CNC-04": False,
        "CNC-05": True,
    }


def test_pressure_is_measured_only_where_there_is_hydraulics():
    sim = build_line(1, machines=4)
    for _ in range(5):
        sim.step()
    meters = {r.machine_id for r in sim.readings if r.sensor == "hydraulic_pressure"}
    assert meters == {"CNC-02"}
    look = ObservationTools(sim)
    assert look.get_readings("CNC-02", "hydraulic_pressure", 0, 5)
    with pytest.raises(ToolInputError, match="no hydraulic system"):
        look.get_readings("CNC-01", "hydraulic_pressure", 0, 5)


# --- the leak and the evidence ---


def test_sound_seals_hold_about_seventy_bar_and_a_leak_costs_its_square():
    idle = machine(load=0.0, status=MachineStatus.IDLE)
    assert exact(idle) == pytest.approx(70.0)
    assert exact(machine()) == pytest.approx(70.0 - 2.0 * 0.5)
    assert exact(machine(seals=0.5)) - exact(machine()) == pytest.approx(-40 * 0.25)


def test_a_stopped_machine_sends_no_pressure_and_so_trips_no_alarm():
    sensor = HydraulicPressureSensor("CNC-02", RandomSource(1))
    assert not sensor.available(machine(status=MachineStatus.DOWN))
    assert sensor.available(machine(status=MachineStatus.IDLE))


def test_the_low_pressure_alarm_fires_below_its_threshold_only():
    alarm = ThresholdAlarm("hydraulic_pressure", 55.0, below=True)
    assert alarm.check(reading("hydraulic_pressure", 60.0, "bar")) is None
    fired = alarm.check(reading("hydraulic_pressure", 54.0, "bar"))
    assert fired is not None and fired.message.endswith("below 55.00")
    high = ThresholdAlarm("vibration", 4.5).check(reading("vibration", 5.0, "mm/s"))
    assert high is not None and high.message.endswith("above 4.50")


def test_the_leak_grows_from_its_start_and_only_on_its_machine():
    sim = leaking_line(99)
    assert sim.state.machines["CNC-02"].condition.hydraulic_health == 1.0
    sim = leaking_line(600)
    assert sim.state.machines["CNC-02"].condition.hydraulic_health < 1.0
    assert sim.state.machines["CNC-01"].condition.hydraulic_health == 1.0


def test_a_machine_without_hydraulics_cannot_leak():
    with pytest.raises(ValueError, match="no hydraulic system"):
        leaking_line(2, machine_id="CNC-01")


def test_a_leak_trips_the_low_pressure_alarm_on_its_machine():
    sim = leaking_line(1500)
    alarms = [e for e in sim.event_log.events if "hydraulic_pressure" in e.message]
    assert alarms and {e.machine_id for e in alarms} == {"CNC-02"}


def test_a_weak_clamp_makes_parts_more_likely_to_fail_inspection():
    assert defect_mark(machine()) == 0.0
    assert defect_mark(machine(seals=0.5)) == pytest.approx(0.30 * 0.25)


# --- the repair ---


def test_a_hydraulic_repair_restores_the_seals_and_says_what_was_found():
    sim = leaking_line(900)
    m = sim.state.machines["CNC-02"]
    assert m.condition.hydraulic_health < 0.9
    desk = ApprovalDesk(sim)
    act = ActionTools(sim, desk)
    approve_and_run(
        desk, act, act.propose_action("CNC-02", "repair_hydraulics", REASON)["id"]
    )
    assert m.status is MachineStatus.DOWN and m.maintenance_until == 940
    for _ in range(41):
        sim.step()
    assert m.condition.hydraulic_health == 1.0 and m.hydraulics_repaired_tick == 940
    messages = [e.message for e in sim.event_log.events if e.kind == "maintenance"]
    assert messages[-1].startswith("hydraulic repair finished: old seals leaking")
    for _ in range(300):
        sim.step()
    assert m.condition.hydraulic_health == 1.0


def test_a_hydraulic_repair_is_refused_on_a_machine_without_hydraulics():
    sim = build_line(42, machines=3)
    act = ActionTools(sim, ApprovalDesk(sim))
    with pytest.raises(ToolInputError, match="no hydraulic system"):
        act.propose_action("CNC-01", "repair_hydraulics", REASON)
    with pytest.raises(ValueError, match="no hydraulic system"):
        sim.start_hydraulic_repair("CNC-03")


# --- the pack and the seed contract ---


def test_seeds_never_draw_the_leak_by_themselves():
    assert "hydraulic_leak" not in DEFAULT_DRAW and FAULTS == DEFAULT_DRAW
    for seed in range(200):
        assert build_scenario(seed).ground_truth()[0].fault != "hydraulic_leak"


def test_a_forced_leak_lands_on_a_machine_with_hydraulics_at_the_seeds_start():
    for seed in range(12):
        sim = build_scenario(seed, fault="hydraulic_leak")
        (leak,) = sim.ground_truth()
        (bearing,) = build_scenario(seed, fault="bearing_degradation").ground_truth()
        assert sim.state.machines[leak.machine_id].has_hydraulics
        assert leak.start_tick == bearing.start_tick
        if sim.state.machines[bearing.machine_id].has_hydraulics:
            assert leak.machine_id == bearing.machine_id


def test_the_pack_asks_for_the_hydraulic_repair_and_counts_as_a_cause():
    pack = BY_KIND["hydraulic_leak"]
    assert pack.agent.action == "repair_hydraulics"
    assert pack.evaluator.correct_action == "repair_hydraulics"
    assert pack.evaluator.is_cause and pack.difficulty == "hard"
    assert not pack.in_default_draw
