from datetime import datetime

import pytest

from capstone.simulator.sensors import VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import FactoryState, MachineState

START = datetime(2026, 1, 5, 6, 0)
MACHINES = ("CNC-01", "CNC-04")


def factory(seed: int = 42, **sensor_kwargs) -> Simulator:
    sim = Simulator(seed, START)
    for machine_id in MACHINES:
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(VibrationSensor(machine_id, sim.rng, **sensor_kwargs))
    return sim


def test_factory_state_rejects_duplicate_machine():
    state = FactoryState()
    state.add(MachineState(id="CNC-04"))
    with pytest.raises(ValueError):
        state.add(MachineState(id="CNC-04"))


def test_sensor_needs_an_existing_machine():
    sim = Simulator(42, START)
    with pytest.raises(ValueError):
        sim.add_sensor(VibrationSensor("CNC-04", sim.rng))


def test_duplicate_sensor_is_rejected():
    sim = factory()
    with pytest.raises(ValueError):
        sim.add_sensor(VibrationSensor("CNC-04", sim.rng))


def test_step_advances_the_clock_by_exactly_one_tick():
    sim = factory()
    sim.step()
    sim.step()
    assert sim.clock.tick == 2


def test_step_returns_one_reading_per_sensor_stamped_with_the_new_tick():
    readings = factory().step()
    assert [(r.machine_id, r.tick) for r in readings] == [("CNC-01", 1), ("CNC-04", 1)]


def test_log_accumulates_every_reading_oldest_first():
    sim = factory()
    for _ in range(3):
        sim.step()
    assert [r.tick for r in sim.readings] == [1, 1, 2, 2, 3, 3]


def test_same_seed_gives_identical_factory_history():
    def history(seed):
        sim = factory(seed)
        for _ in range(50):
            sim.step()
        return sim.readings

    assert history(42) == history(42)
    assert history(42) != history(43)


def test_stepping_does_not_change_reality_when_nothing_acts_on_it():
    sim = factory()
    before = sim.state.model_copy(deep=True)
    for _ in range(20):
        sim.step()
    assert sim.state == before
