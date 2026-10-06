from datetime import datetime
from itertools import groupby
from statistics import mean

import pytest

from capstone.simulator.scenarios import BearingDegradation, Workload
from capstone.simulator.sensors import LoadSensor, TemperatureSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState

START = datetime(2026, 1, 5, 6, 0)
RATE = 0.001


def factory(seed: int = 42, machines: tuple[str, ...] = ("CNC-01", "CNC-04")) -> Simulator:
    sim = Simulator(seed, START)
    for machine_id in machines:
        sim.add_machine(MachineState(id=machine_id))
        for sensor in (VibrationSensor, TemperatureSensor, LoadSensor):
            sim.add_sensor(sensor(machine_id, sim.rng))
        sim.add_scenario(Workload(f"workload.{machine_id}", sim.rng, machine_id=machine_id))
    return sim


def load_history(sim: Simulator, machine_id: str, ticks: int = 600) -> list[float]:
    history = []
    for _ in range(ticks):
        sim.step()
        history.append(sim.state.machines[machine_id].load)
    return history


def blocks(history: list[float]) -> list[tuple[float, int]]:
    return [(load, len(list(run))) for load, run in groupby(history)]


def test_rejects_nonsense_settings():
    sim = Simulator(42, START)
    with pytest.raises(ValueError):
        Workload("a", sim.rng, machine_id="CNC-04", min_block=10, max_block=5)
    with pytest.raises(ValueError):
        Workload("b", sim.rng, machine_id="CNC-04", min_load=0.2, max_load=1.5)


def test_workload_is_not_a_fault_and_declares_no_ground_truth():
    sim = factory()
    sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-04", start_tick=100, rate=RATE))
    assert [g.scenario for g in sim.ground_truth()] == ["bearing"]


def test_load_changes_in_blocks_within_the_set_limits():
    history = load_history(factory(), "CNC-04")
    assert all(0.3 <= load <= 0.8 for load in history)
    complete = blocks(history)[:-1]
    assert len(complete) >= 5
    assert all(30 <= length <= 90 for _, length in complete)


def test_same_seed_gives_the_same_working_day():
    assert load_history(factory(42), "CNC-04") == load_history(factory(42), "CNC-04")
    assert load_history(factory(42), "CNC-04") != load_history(factory(43), "CNC-04")


def test_each_machine_has_its_own_schedule():
    assert load_history(factory(), "CNC-01") != load_history(factory(), "CNC-04")


def test_adding_a_machine_does_not_change_another_machines_schedule():
    alone = load_history(factory(machines=("CNC-04",)), "CNC-04")
    assert load_history(factory(machines=("CNC-01", "CNC-04", "CNC-07")), "CNC-04") == alone


def test_workload_changes_load_and_nothing_else():
    sim = factory()
    load_history(sim, "CNC-04")
    for machine in sim.state.machines.values():
        assert machine.condition.bearing_health == 1.0
        assert machine.status == "running"


def test_all_three_readings_follow_the_work_on_a_healthy_machine():
    sim = factory()
    history = load_history(sim, "CNC-01")
    cut = sorted(history)[len(history) // 2]

    def average(sensor: str, heavy: bool) -> float:
        return mean(
            r.value
            for r in sim.readings
            if r.machine_id == "CNC-01" and r.sensor == sensor and (history[r.tick - 1] > cut) == heavy
        )

    for sensor in ("vibration", "temperature", "load"):
        assert average(sensor, heavy=True) > average(sensor, heavy=False)


def test_wear_uses_the_load_of_the_same_tick():
    sim = factory(machines=("CNC-04",))
    sim.add_scenario(
        BearingDegradation("bearing", sim.rng, machine_id="CNC-04", start_tick=1, rate=RATE, variation=0.0)
    )
    history = load_history(sim, "CNC-04", ticks=200)
    expected = 1.0 - sum(RATE * (load / 0.5) ** 3 for load in history)
    assert sim.state.machines["CNC-04"].condition.bearing_health == pytest.approx(expected)
