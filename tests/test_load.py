from datetime import datetime

import pytest
from pydantic import ValidationError

from capstone.simulator.rng import RandomSource
from capstone.simulator.sensors import LoadSensor, TemperatureSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState, MachineStatus
from capstone.simulator.thermal import settle
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)


def machine(load: float = 0.5, health: float = 1.0, status: MachineStatus = MachineStatus.RUNNING) -> MachineState:
    return MachineState(id="CNC-04", status=status, load=load, condition=MachineCondition(bearing_health=health))


def exact(m: MachineState) -> dict[str, float]:
    """Noise-free vibration, temperature and load readings for one machine."""
    rng = RandomSource(42)
    settle(m, 72.0)
    sensors = (VibrationSensor, TemperatureSensor, LoadSensor)
    return {s.name: s("CNC-04", rng, noise_sd=0.0).read(m, 0).value for s in sensors}


def test_a_new_machine_runs_at_normal_load():
    assert MachineState(id="CNC-04").load == 0.5


def test_load_must_be_between_zero_and_one():
    with pytest.raises(ValidationError):
        machine(load=1.2)
    with pytest.raises(ValidationError):
        MachineState(id="CNC-04").load = -0.1


def test_at_normal_load_the_readings_are_what_they_were_before():
    assert exact(machine()) == pytest.approx({"vibration": 2.0, "temperature": 115.0, "load": 50.0})


def test_heavier_load_raises_vibration_and_temperature_on_a_healthy_machine():
    assert exact(machine(load=0.9)) == pytest.approx({"vibration": 2.6, "temperature": 127.0, "load": 90.0})


def test_lighter_load_lowers_them():
    light = exact(machine(load=0.2))
    assert light["vibration"] < 2.0 and light["temperature"] < 115.0


def test_load_and_wear_add_up():
    both = exact(machine(load=0.9, health=0.7))
    assert both == pytest.approx({"vibration": 2.0 + 0.6 + 0.54, "temperature": 115.0 + 12.0 + 13.5, "load": 90.72})


def test_hard_work_and_a_worn_bearing_look_alike_except_on_the_load_sensor():
    working_hard, worn = exact(machine(load=0.9)), exact(machine(health=0.7))
    assert working_hard["vibration"] == pytest.approx(worn["vibration"], abs=0.1)
    assert working_hard["temperature"] == pytest.approx(worn["temperature"], abs=2.0)
    assert working_hard["load"] - worn["load"] == pytest.approx(40.0, abs=1.0)


def test_a_machine_that_is_not_running_reports_no_load():
    assert exact(machine(load=0.9, status=MachineStatus.IDLE))["load"] == 0.0


def test_reading_the_sensors_does_not_change_the_load():
    m = machine(load=0.8)
    exact(m)
    assert m.load == 0.8


def test_the_agent_sees_load_only_through_the_load_sensor():
    sim = Simulator(42, START)
    sim.add_machine(machine(load=0.9))
    sim.add_sensor(LoadSensor("CNC-04", sim.rng))
    sim.step()
    tools = ObservationTools(sim)
    assert tools.list_machines() == [{"machine_id": "CNC-04", "status": "running"}]
    assert tools.get_readings("CNC-04", "load", 1, 1)[0]["value"] == pytest.approx(90.0, abs=8.0)
