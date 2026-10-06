from datetime import datetime

import pytest

from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.sensors import LoadSensor, TemperatureSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import FactoryState, MachineCondition, MachineState
from capstone.simulator.thermal import settle

START = datetime(2026, 1, 5, 6, 0)
RATE = 0.001


def health_after(load: float, ticks: int = 100) -> float:
    state = FactoryState()
    state.add(MachineState(id="CNC-04", load=load))
    wear = BearingDegradation("bearing", RandomSource(42), machine_id="CNC-04", start_tick=1, rate=RATE, variation=0.0)
    for tick in range(1, ticks + 1):
        wear.apply(state, tick)
    assert state.machines["CNC-04"].load == load
    return state.machines["CNC-04"].condition.bearing_health


def load_reading(health: float, load: float = 0.5) -> float:
    m = MachineState(id="CNC-04", load=load, condition=MachineCondition(bearing_health=health))
    return LoadSensor("CNC-04", RandomSource(42), noise_sd=0.0).read(m, 0).value


def two_machines() -> Simulator:
    """Same fault on both from tick 100; A works light, B works heavy."""
    sim = Simulator(42, START)
    for machine_id, load in (("A", 0.3), ("B", 0.8)):
        sim.add_machine(MachineState(id=machine_id, load=load))
        sim.add_sensor(LoadSensor(machine_id, sim.rng))
        sim.add_scenario(BearingDegradation(f"bearing-{machine_id}", sim.rng, machine_id=machine_id, start_tick=100, rate=RATE))
    for _ in range(1000):
        sim.step()
    return sim


def test_at_normal_load_wear_is_exactly_the_rate():
    assert health_after(0.5) == pytest.approx(1.0 - 100 * RATE)


def test_heavy_load_wears_by_the_cube_of_the_load_ratio():
    assert health_after(0.9) == pytest.approx(1.0 - 100 * RATE * 1.8**3)


def test_light_load_wears_much_more_slowly():
    assert health_after(0.3) == pytest.approx(1.0 - 100 * RATE * 0.6**3)


def test_no_load_means_no_wear():
    assert health_after(0.0) == 1.0


def test_the_harder_worked_machine_fails_first():
    sim = two_machines()
    stopped = [e.machine_id for e in sim.event_log.events if e.kind == "status"]
    assert stopped == ["B"]
    assert sim.state.machines["A"].condition.bearing_health > 0.7


def test_wear_never_changes_the_load_itself():
    sim = two_machines()
    assert (sim.state.machines["A"].load, sim.state.machines["B"].load) == (0.3, 0.8)


def test_a_healthy_bearing_adds_nothing_to_the_load_reading():
    assert load_reading(1.0) == pytest.approx(50.0)


def test_friction_is_small_early_and_noticeable_late():
    assert load_reading(0.7) - 50.0 == pytest.approx(0.72)
    assert load_reading(0.3) - 50.0 == pytest.approx(3.92)


def test_wear_is_not_counted_twice_in_vibration_or_temperature():
    m = settle(MachineState(id="CNC-04", condition=MachineCondition(bearing_health=0.7)), 72.0)
    rng = RandomSource(42)
    assert VibrationSensor("CNC-04", rng, noise_sd=0.0).read(m, 0).value == pytest.approx(2.54)
    assert TemperatureSensor("CNC-04", rng, noise_sd=0.0).read(m, 0).value == pytest.approx(128.5)
