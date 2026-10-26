from datetime import datetime

import pytest

from capstone.contracts.tools import ToolRequest
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.line import build_line
from capstone.simulator.rng import RandomSource
from capstone.simulator.sensors import PowerSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState, MachineStatus
from capstone.tools.actions import ActionTools
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)


def machine(
    *,
    status: MachineStatus = MachineStatus.RUNNING,
    load: float = 0.5,
    health: float = 1.0,
    speed: float | None = None,
) -> MachineState:
    return MachineState(
        id="CNC-04",
        status=status,
        load=load,
        standard_speed=1000.0,
        speed_setting=speed,
        condition=MachineCondition(bearing_health=health),
    )


def exact(m: MachineState) -> float:
    """A noise-free power reading, in kW."""
    return PowerSensor("CNC-04", RandomSource(42), noise_sd=0.0).read(m, 0).value


def test_a_stopped_machine_draws_nothing():
    assert exact(machine(status=MachineStatus.DOWN)) == 0.0


def test_an_idle_machine_draws_only_its_idle_power():
    assert exact(machine(status=MachineStatus.IDLE, load=0.0)) == pytest.approx(2.0)


def test_a_running_machine_adds_spindle_power_in_proportion_to_its_load():
    assert exact(machine(load=0.5)) == pytest.approx(2.0 + 15.0 * 0.5)
    assert exact(machine(load=0.8)) - exact(machine(load=0.4)) == pytest.approx(
        15.0 * 0.4
    )


def test_the_same_work_at_a_higher_speed_draws_more_power():
    standard = exact(machine(load=0.5))
    fast = exact(machine(load=0.5, speed=1200.0))
    assert fast - standard == pytest.approx(15.0 * 0.5 * 0.2)


def test_a_worn_bearing_adds_a_little_friction_power():
    assert exact(machine(health=0.5)) - exact(machine()) == pytest.approx(1.5 * 0.5**2)


def test_more_power_alone_does_not_single_out_a_worn_bearing():
    """A heavier job raises power far more than a badly worn bearing does."""
    worn = exact(machine(load=0.5, health=0.2)) - exact(machine(load=0.5))
    heavier_job = exact(machine(load=0.6)) - exact(machine(load=0.5))
    assert heavier_job > worn


def test_reading_power_changes_nothing_in_the_machine():
    m = machine(health=0.6)
    before = m.model_dump()
    PowerSensor("CNC-04", RandomSource(1)).read(m, 5)
    assert m.model_dump() == before


def test_the_reading_is_in_kilowatts_and_never_negative():
    sensor = PowerSensor("CNC-04", RandomSource(3), noise_sd=1.0)
    readings = [sensor.read(machine(status=MachineStatus.DOWN), t) for t in range(200)]
    assert {r.unit for r in readings} == {"kW"}
    assert min(r.value for r in readings) >= 0.0


def test_adding_a_power_meter_changes_no_other_reading():
    """Power has its own stream: the other sensors read exactly as before."""

    def vibration(with_power: bool):
        sim = Simulator(7, START)
        sim.add_machine(MachineState(id="CNC-01"))
        sim.add_sensor(VibrationSensor("CNC-01", sim.rng))
        if with_power:
            sim.add_sensor(PowerSensor("CNC-01", sim.rng))
        for _ in range(100):
            sim.step()
        return [r for r in sim.readings if r.sensor == "vibration"]

    assert vibration(True) == vibration(False)


def test_the_standard_line_has_a_power_meter_on_every_machine():
    sim = build_line(11, machines=4)
    sim.step()
    meters = {r.machine_id for r in sim.readings if r.sensor == "power"}
    assert meters == set(sim.state.machines)


def test_same_seed_gives_the_same_power_readings():
    def power(seed: int):
        sim = build_line(seed, machines=3)
        for _ in range(200):
            sim.step()
        return [r for r in sim.readings if r.sensor == "power"]

    assert power(5) == power(5)
    assert power(5) != power(6)


def test_the_agent_can_ask_for_power_through_the_tools():
    sim = build_line(42, machines=3)
    for _ in range(10):
        sim.step()
    factory = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim))
    arguments = {"machine_id": "CNC-01", "from_tick": 1, "to_tick": 10}
    readings = factory.call(
        ToolRequest(name="get_readings", arguments=arguments | {"sensor": "power"})
    )
    assert readings.error is None and readings.data
    assert {row["unit"] for row in readings.data} == {"kW"}
    summary = factory.call(
        ToolRequest(
            name="get_sensor_summary", arguments=arguments | {"sensor": "power"}
        )
    )
    assert summary.error is None and summary.data["unit"] == "kW"
    refused = factory.call(
        ToolRequest(name="get_readings", arguments=arguments | {"sensor": "current"})
    )
    assert refused.error is not None
