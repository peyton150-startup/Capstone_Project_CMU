from datetime import datetime
from statistics import mean

import pytest

from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.sensors import TemperatureSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState, MachineStatus
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)


def machine(health: float = 1.0, status: MachineStatus = MachineStatus.RUNNING) -> MachineState:
    return MachineState(id="CNC-04", status=status, condition=MachineCondition(bearing_health=health))


def exact_sensor() -> TemperatureSensor:
    return TemperatureSensor("CNC-04", RandomSource(42), noise_sd=0.0)


def factory(with_temperature: bool = True) -> Simulator:
    sim = Simulator(42, START)
    for machine_id in ("CNC-01", "CNC-04"):
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(VibrationSensor(machine_id, sim.rng))
        if with_temperature:
            sim.add_sensor(TemperatureSensor(machine_id, sim.rng))
    sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-04", start_tick=100, rate=0.001))
    for _ in range(800):
        sim.step()
    return sim


def average(tools: ObservationTools, machine_id: str, sensor: str, first: int, last: int) -> float:
    return mean(r["value"] for r in tools.get_readings(machine_id, sensor, first, last))


def test_reading_carries_identity_unit_and_its_own_stream():
    sensor = TemperatureSensor("CNC-04", RandomSource(42))
    r = sensor.read(machine(), tick=3)
    assert (r.sensor, r.machine_id, r.unit) == ("temperature", "CNC-04", "°F")
    assert sensor.stream_name == "sensor.CNC-04.temperature"


def test_temperature_rises_in_a_straight_line_with_wear():
    readings = [exact_sensor().read(machine(h), 0).value for h in (1.0, 0.5, 0.0)]
    assert readings == pytest.approx([115.0, 137.5, 160.0])


def test_a_machine_that_is_not_running_sits_at_room_temperature():
    for status in (MachineStatus.IDLE, MachineStatus.DOWN):
        assert exact_sensor().read(machine(0.2, status), 0).value == pytest.approx(72.0)


def test_sensor_does_not_change_the_machine():
    m = machine(0.6)
    before = m.model_copy(deep=True)
    TemperatureSensor("CNC-04", RandomSource(42)).read(m, 0)
    assert m == before


def test_adding_temperature_sensors_leaves_vibration_history_untouched():
    def vibration(sim):
        return [r for r in sim.readings if r.sensor == "vibration"]

    assert vibration(factory(with_temperature=True)) == vibration(factory(with_temperature=False))


def test_both_symptoms_rise_together_on_the_faulty_machine_only():
    tools = ObservationTools(factory())
    for sensor in ("vibration", "temperature"):
        assert average(tools, "CNC-04", sensor, 750, 799) > average(tools, "CNC-04", sensor, 50, 99)
    assert average(tools, "CNC-04", "temperature", 750, 799) == pytest.approx(115 + 45 * 0.675, abs=3)
    assert average(tools, "CNC-01", "temperature", 750, 799) == pytest.approx(115, abs=1)
