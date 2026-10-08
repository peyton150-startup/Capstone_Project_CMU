from datetime import datetime

import pytest
from pydantic import ValidationError

from capstone.simulator.events import Event, EventLog, ThresholdAlarm
from capstone.simulator.sensors import SensorReading, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState

START = datetime(2026, 1, 5, 6, 0)


def reading(value: float, sensor: str = "vibration", tick: int = 7) -> SensorReading:
    return SensorReading(
        sensor=sensor, machine_id="CNC-04", tick=tick, value=value, unit="mm/s"
    )


def event(tick: int) -> Event:
    return Event(tick=tick, machine_id="CNC-04", kind="alarm", message="x")


def one_machine(health: float = 1.0, seed: int = 42, **sensor_kwargs) -> Simulator:
    sim = Simulator(seed, START)
    sim.add_machine(
        MachineState(id="CNC-04", condition=MachineCondition(bearing_health=health))
    )
    sim.add_sensor(VibrationSensor("CNC-04", sim.rng, **sensor_kwargs))
    sim.add_alarm(ThresholdAlarm("vibration", 4.5))
    return sim


def test_event_is_immutable():
    with pytest.raises(ValidationError):
        event(1).tick = 2


def test_log_keeps_events_oldest_first():
    log = EventLog()
    for tick in (1, 1, 3):
        log.record(event(tick))
    assert [e.tick for e in log.events] == [1, 1, 3]


def test_log_refuses_an_event_older_than_its_latest():
    log = EventLog()
    log.record(event(5))
    with pytest.raises(ValueError):
        log.record(event(4))


def test_alarm_fires_only_above_the_threshold():
    alarm = ThresholdAlarm("vibration", 4.5)
    assert alarm.check(reading(4.5)) is None
    fired = alarm.check(reading(4.62))
    assert (fired.tick, fired.machine_id, fired.kind) == (7, "CNC-04", "alarm")
    assert fired.message == "vibration 4.62 mm/s above 4.50"


def test_alarm_ignores_other_sensor_types():
    assert (
        ThresholdAlarm("vibration", 4.5).check(reading(90.0, sensor="temperature"))
        is None
    )


def test_step_records_the_alarm_at_the_tick_of_the_reading():
    sim = one_machine(health=0.2, noise_sd=0.0)
    sim.step()
    sim.step()
    assert [e.tick for e in sim.event_log.events] == [1, 2]


def test_alarm_follows_the_evidence_not_the_hidden_truth():
    healthy_but_loud = one_machine(health=1.0, noise_sd=0.0, baseline=5.0)
    damaged_but_quiet = one_machine(health=0.5, noise_sd=0.0)
    healthy_but_loud.step()
    damaged_but_quiet.step()
    assert len(healthy_but_loud.event_log.events) == 1
    assert damaged_but_quiet.event_log.events == ()


def test_noise_makes_the_alarm_flicker_near_the_threshold():
    sim = one_machine(health=1.0, baseline=4.5)
    for _ in range(200):
        sim.step()
    assert 0 < len(sim.event_log.events) < 200


def test_same_seed_gives_identical_event_history():
    def history(seed):
        sim = one_machine(seed=seed, baseline=4.5)
        for _ in range(200):
            sim.step()
        return sim.event_log.events

    assert history(42) == history(42)
    assert history(42) != history(43)
