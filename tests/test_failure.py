from datetime import datetime

import pytest

from capstone.simulator.events import ThresholdAlarm
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.sensors import VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState, MachineStatus

START = datetime(2026, 1, 5, 6, 0)


def one_machine(health: float, status: MachineStatus = MachineStatus.RUNNING) -> Simulator:
    sim = Simulator(42, START)
    sim.add_machine(MachineState(id="CNC-04", status=status, condition=MachineCondition(bearing_health=health)))
    sim.add_sensor(VibrationSensor("CNC-04", sim.rng, noise_sd=0.0))
    return sim


def degrading(seed: int = 42) -> Simulator:
    sim = Simulator(seed, START)
    for machine_id in ("CNC-01", "CNC-04"):
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(VibrationSensor(machine_id, sim.rng))
    sim.add_alarm(ThresholdAlarm("vibration", 4.5))
    sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-04", start_tick=100, rate=0.001))
    for _ in range(1200):
        sim.step()
    return sim


def stops(sim: Simulator) -> list:
    return [e for e in sim.event_log.events if e.kind == "status"]


def test_running_machine_at_the_failure_level_goes_down():
    sim = one_machine(health=0.1)
    sim.step()
    assert sim.state.machines["CNC-04"].status is MachineStatus.DOWN


def test_machine_just_above_the_failure_level_keeps_running():
    sim = one_machine(health=0.11)
    sim.step()
    assert sim.state.machines["CNC-04"].status is MachineStatus.RUNNING
    assert stops(sim) == []


def test_an_idle_machine_does_not_fail():
    sim = one_machine(health=0.05, status=MachineStatus.IDLE)
    sim.step()
    assert sim.state.machines["CNC-04"].status is MachineStatus.IDLE


def test_the_stop_is_recorded_once_and_does_not_say_why():
    sim = one_machine(health=0.05)
    for _ in range(5):
        sim.step()
    (stop,) = stops(sim)
    assert (stop.tick, stop.machine_id, stop.message) == (1, "CNC-04", "machine stopped")
    assert "bearing" not in stop.message and "health" not in stop.message


def test_the_reading_at_the_failure_tick_already_shows_a_stopped_machine():
    sim = one_machine(health=0.05)
    assert sim.step()[0].value == pytest.approx(0.1)


def test_degradation_ends_in_failure_after_the_alarms():
    sim = degrading()
    (stop,) = stops(sim)
    alarms = [e for e in sim.event_log.events if e.kind == "alarm"]
    assert stop.machine_id == "CNC-04"
    assert 100 < alarms[0].tick < stop.tick
    assert sim.state.machines["CNC-01"].status is MachineStatus.RUNNING


def test_after_failure_wear_and_alarms_stop():
    sim = degrading()
    (stop,) = stops(sim)
    assert not [e for e in sim.event_log.events if e.kind == "alarm" and e.tick >= stop.tick]
    assert sim.state.machines["CNC-04"].condition.bearing_health == pytest.approx(0.1, abs=0.002)
    late = [r.value for r in sim.readings if r.machine_id == "CNC-04" and r.tick > stop.tick]
    assert max(late) < 1.0


def test_same_seed_fails_at_the_same_tick():
    assert stops(degrading(42)) == stops(degrading(42))
    assert stops(degrading(42))[0].tick != stops(degrading(7))[0].tick
