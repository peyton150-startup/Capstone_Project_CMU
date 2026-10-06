from datetime import datetime

import pytest

from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import AmbientTemperature, BearingDegradation
from capstone.simulator.sensors import LoadSensor, TemperatureSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import FactoryState, MachineState, MachineStatus
from capstone.simulator.thermal import settle

START = datetime(2026, 1, 5, 6, 0)
DAY = 1440


def air(seed: int = 42, days: int = 2) -> list[float]:
    """Ambient temperature at every tick, index 0 = tick 1."""
    state, scenario = FactoryState(), AmbientTemperature("ambient", RandomSource(seed))
    history = []
    for tick in range(1, days * DAY + 1):
        scenario.apply(state, tick)
        history.append(state.ambient_temperature)
    return history


def factory(fault: bool = False) -> Simulator:
    sim = Simulator(42, START)
    sim.add_scenario(AmbientTemperature("ambient", sim.rng))
    for machine_id in ("CNC-01", "CNC-04"):
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(TemperatureSensor(machine_id, sim.rng, noise_sd=0.0))
        sim.add_sensor(VibrationSensor(machine_id, sim.rng, noise_sd=0.0))
        sim.add_sensor(LoadSensor(machine_id, sim.rng, noise_sd=0.0))
    if fault:
        sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-04", start_tick=100, rate=0.0005))
    for _ in range(DAY):
        sim.step()
    return sim


def series(sim: Simulator, machine_id: str, sensor: str) -> list[float]:
    return [r.value for r in sim.readings if r.machine_id == machine_id and r.sensor == sensor]


def test_the_air_starts_at_72_until_something_changes_it():
    assert FactoryState().ambient_temperature == 72.0


def test_ambient_is_not_a_fault_and_declares_no_ground_truth():
    assert factory().ground_truth() == ()


def test_the_day_is_warmest_mid_afternoon_and_coolest_before_dawn():
    day = air()[:DAY]
    warmest, coolest = day.index(max(day)) + 1, day.index(min(day)) + 1
    assert abs(warmest - 600) < 120  # around 4 pm for a 6 am start
    assert abs(coolest - 1320) < 120  # around 4 am
    assert 66.0 < min(day) < 71.0 and 75.0 < max(day) < 80.0


def test_no_two_days_are_quite_alike_but_they_keep_the_same_shape():
    history = air(days=3)
    peaks = [max(history[d * DAY : (d + 1) * DAY]) for d in range(3)]
    assert len(set(peaks)) == 3
    assert max(peaks) - min(peaks) < 4.0


def test_same_seed_gives_the_same_weather():
    assert air(42) == air(42)
    assert air(42) != air(43)


def test_every_machine_moves_with_the_air_together():
    sim = factory()
    a, b = series(sim, "CNC-01", "temperature"), series(sim, "CNC-04", "temperature")
    assert max(a) - min(a) > 6.0
    assert a == pytest.approx(b)


def test_a_healthy_machine_reads_43_degrees_above_the_air():
    sim = factory()
    assert series(sim, "CNC-01", "temperature")[-1] == pytest.approx(sim.state.ambient_temperature + 43.0)


def test_a_stopped_machine_reads_the_air_temperature():
    m = settle(MachineState(id="CNC-04", status=MachineStatus.DOWN), 65.0)
    sensor = TemperatureSensor("CNC-04", RandomSource(42), noise_sd=0.0)
    assert sensor.read(m, 0).value == pytest.approx(65.0)


def test_the_air_does_not_touch_vibration_or_load():
    sim = factory()
    assert set(series(sim, "CNC-01", "vibration")) == {2.0}
    assert set(series(sim, "CNC-01", "load")) == {50.0}


def test_wear_shows_as_a_growing_gap_over_a_healthy_neighbour():
    sim = factory(fault=True)
    gap = [w - h for w, h in zip(series(sim, "CNC-04", "temperature"), series(sim, "CNC-01", "temperature"))]
    assert gap[50] == pytest.approx(0.0)
    assert gap[400] < gap[800] < gap[1200]
    wear = 1.0 - sim.state.machines["CNC-04"].condition.bearing_health
    assert gap[-1] == pytest.approx(45.0 * wear, abs=0.1)
