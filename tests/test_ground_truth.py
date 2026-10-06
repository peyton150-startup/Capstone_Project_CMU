from datetime import datetime

import pytest
from pydantic import ValidationError

from capstone.simulator.events import Event, ThresholdAlarm
from capstone.simulator.ground_truth import GroundTruth
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.sensors import SensorReading, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState

START = datetime(2026, 1, 5, 6, 0)
BEARING = GroundTruth(scenario="bearing", fault="bearing_degradation", machine_id="CNC-04", start_tick=100)


def factory() -> Simulator:
    sim = Simulator(42, START)
    for machine_id in ("CNC-01", "CNC-04"):
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(VibrationSensor(machine_id, sim.rng))
    sim.add_alarm(ThresholdAlarm("vibration", 4.5))
    sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-04", start_tick=100, rate=0.001))
    return sim


def test_ground_truth_is_immutable():
    with pytest.raises(ValidationError):
        BEARING.start_tick = 5


def test_no_scenarios_means_no_ground_truth():
    assert Simulator(42, START).ground_truth() == ()


def test_bearing_degradation_declares_its_own_story():
    assert factory().ground_truth() == (BEARING,)


def test_records_come_in_the_order_scenarios_were_added():
    sim = factory()
    sim.add_scenario(BearingDegradation("second", sim.rng, machine_id="CNC-01", start_tick=300, rate=0.001))
    assert [g.scenario for g in sim.ground_truth()] == ["bearing", "second"]


def test_ground_truth_does_not_depend_on_how_the_run_went():
    sim = factory()
    before = sim.ground_truth()
    for _ in range(1200):
        sim.step()
    assert sim.ground_truth() == before


def test_reading_ground_truth_changes_nothing():
    a, b = factory(), factory()
    for _ in range(300):
        a.step()
        b.step()
        b.ground_truth()
    assert a.readings == b.readings and a.state == b.state


def test_evidence_records_have_no_field_that_could_carry_hidden_truth():
    hidden = set(MachineCondition.model_fields) | set(GroundTruth.model_fields) - {"machine_id"}
    assert not hidden & set(SensorReading.model_fields)
    assert not hidden & set(Event.model_fields)


def test_no_event_in_a_full_run_names_the_cause():
    sim = factory()
    for _ in range(1200):
        sim.step()
    text = " ".join(e.message for e in sim.event_log.events)
    assert "bearing" not in text and "degradation" not in text and "health" not in text
