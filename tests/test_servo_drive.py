"""The servo-drive fault pack: a worn axis drive (Future Work 8 D)."""

from collections import Counter

import pytest

from capstone.faults import BY_KIND, DEFAULT_DRAW
from capstone.simulator.generator import FAULTS, build_scenario
from capstone.simulator.line import build_line
from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import AxisDriveWear, defect_mark, working_speed
from capstone.simulator.sensors import FollowingErrorSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState, MachineStatus
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.helpers import START, approve_and_run

REASON = "CNC-02's following error climbed past its alarm and rejects rose"


def machine(*, axis: float = 1.0, status=MachineStatus.RUNNING, load=0.5):
    return MachineState(
        id="CNC-02",
        status=status,
        load=load,
        condition=MachineCondition(axis_health=axis),
    )


def exact(m: MachineState) -> float:
    return (
        FollowingErrorSensor("CNC-02", RandomSource(1), noise_sd=0.0).read(m, 0).value
    )


def worn_line(ticks: int, *, start: int = 100, rate: float = 0.001):
    sim = build_line(42, machines=3)
    sim.add_scenario(
        AxisDriveWear(
            "servo", sim.rng, machine_id="CNC-02", start_tick=start, rate=rate
        )
    )
    for _ in range(ticks):
        sim.step()
    return sim


# --- the hidden condition and its scenario ---


def test_a_new_drive_is_healthy():
    assert MachineState(id="CNC-01").condition.axis_health == 1.0


def test_the_drive_wears_only_from_its_start_and_only_on_its_machine():
    sim = worn_line(99)
    assert sim.state.machines["CNC-02"].condition.axis_health == 1.0
    sim = worn_line(400)
    assert sim.state.machines["CNC-02"].condition.axis_health < 1.0
    assert sim.state.machines["CNC-01"].condition.axis_health == 1.0
    assert sim.state.machines["CNC-03"].condition.axis_health == 1.0


def test_nonsense_settings_are_refused():
    sim = Simulator(1, START)
    with pytest.raises(ValueError):
        AxisDriveWear("a", sim.rng, machine_id="CNC-02", start_tick=1, rate=0.0)


def test_the_answer_key_names_the_fault_and_machine():
    (truth,) = worn_line(1).ground_truth()
    assert (truth.fault, truth.machine_id, truth.start_tick) == (
        "servo_drive_wear",
        "CNC-02",
        100,
    )


# --- the evidence ---


def test_following_error_is_small_on_a_healthy_running_axis_and_tiny_when_holding():
    assert exact(machine()) == pytest.approx(4.0)
    assert exact(machine(status=MachineStatus.IDLE, load=0.0)) == pytest.approx(1.0)
    assert exact(machine(status=MachineStatus.DOWN, load=0.0)) == pytest.approx(1.0)


def test_a_worn_drive_raises_following_error_with_the_square_of_wear():
    assert exact(machine(axis=0.5)) - exact(machine()) == pytest.approx(40 * 0.25)


def test_a_heavy_cut_raises_it_only_a_little():
    assert exact(machine(load=0.8)) - exact(machine()) == pytest.approx(4 * 0.3)


def test_reading_it_changes_nothing():
    m = machine(axis=0.6)
    before = m.model_dump()
    FollowingErrorSensor("CNC-02", RandomSource(2)).read(m, 1)
    assert m.model_dump() == before


def test_the_controller_alarms_on_a_worn_axis_and_not_on_healthy_ones():
    sim = worn_line(1500)
    alarms = [
        e
        for e in sim.event_log.events
        if e.kind == "alarm" and "following_error" in e.message
    ]
    assert alarms and {e.machine_id for e in alarms} == {"CNC-02"}


def test_a_worn_drive_adds_no_vibration_and_no_slowdown_unlike_a_bearing():
    healthy, worn = machine(), machine(axis=0.3)
    vib = VibrationSensor("CNC-02", RandomSource(1), noise_sd=0.0)
    assert vib.read(worn, 0).value == vib.read(healthy, 0).value
    assert working_speed(worn) == working_speed(healthy)


def test_a_worn_drive_makes_parts_more_likely_to_fail_inspection():
    assert defect_mark(machine()) == 0.0
    assert defect_mark(machine(axis=0.5)) == pytest.approx(0.35 * 0.25)


# --- the repair ---


def test_an_approved_drive_replacement_restores_the_axis_and_says_what_was_found():
    sim = worn_line(900)
    m = sim.state.machines["CNC-02"]
    assert m.condition.axis_health < 0.9
    desk = ApprovalDesk(sim)
    act = ActionTools(sim, desk)
    approve_and_run(
        desk, act, act.propose_action("CNC-02", "replace_servo_drive", REASON)["id"]
    )
    assert m.status is MachineStatus.DOWN and m.maintenance_until == 960
    for _ in range(61):
        sim.step()
    assert m.condition.axis_health == 1.0 and m.axis_replaced_tick == 960
    found = [
        e["message"]
        for e in ObservationTools(sim).get_events(0, 10_000, "CNC-02")
        if e["kind"] == "maintenance"
    ]
    assert found[-1].startswith("servo drive replacement finished: old drive")
    assert "worn" in found[-1]
    for _ in range(300):
        sim.step()
    assert m.condition.axis_health == 1.0  # the fault was in the old drive


def test_a_new_drive_on_a_healthy_machine_is_found_in_good_condition():
    sim = build_line(42, machines=3)
    for _ in range(50):
        sim.step()
    desk = ApprovalDesk(sim)
    act = ActionTools(sim, desk)
    approve_and_run(
        desk, act, act.propose_action("CNC-01", "replace_servo_drive", REASON)["id"]
    )
    for _ in range(61):
        sim.step()
    messages = [e.message for e in sim.event_log.events if e.kind == "maintenance"]
    assert (
        messages[-1] == "servo drive replacement finished: old drive in good condition"
    )


# --- the pack and the seed contract ---


def test_seeds_never_draw_the_servo_fault_by_themselves():
    assert "servo_drive_wear" not in DEFAULT_DRAW and FAULTS == DEFAULT_DRAW
    drawn = Counter(build_scenario(s).ground_truth()[0].fault for s in range(200))
    assert "servo_drive_wear" not in drawn


def test_forcing_the_servo_fault_keeps_the_seeds_machine_and_start():
    for seed in range(5):
        (servo,) = build_scenario(seed, fault="servo_drive_wear").ground_truth()
        (bearing,) = build_scenario(seed, fault="bearing_degradation").ground_truth()
        assert (servo.machine_id, servo.start_tick) == (
            bearing.machine_id,
            bearing.start_tick,
        )
        assert servo.fault == "servo_drive_wear"


def test_the_pack_asks_for_the_drive_replacement_and_counts_as_a_cause():
    pack = BY_KIND["servo_drive_wear"]
    assert pack.agent.action == "replace_servo_drive"
    assert pack.evaluator.correct_action == "replace_servo_drive"
    assert pack.evaluator.is_cause and not pack.in_default_draw
