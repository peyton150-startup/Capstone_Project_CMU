from datetime import datetime

import pytest

from capstone.simulator.scenarios import AmbientTemperature, LoadingDoor
from capstone.simulator.sensors import TemperatureSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import FactoryState, MachineState
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
DAY = 1440


def factory(seed: int = 42, door_first: bool = False, ambient: bool = True) -> Simulator:
    sim = Simulator(seed, START)
    scenarios = []
    if ambient:
        scenarios.append(AmbientTemperature("ambient", sim.rng))
    scenarios.append(LoadingDoor("door", sim.rng))
    for scenario in reversed(scenarios) if door_first else scenarios:
        sim.add_scenario(scenario)
    for machine_id in ("CNC-01", "CNC-04"):
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(TemperatureSensor(machine_id, sim.rng, noise_sd=0.0))
        sim.add_sensor(VibrationSensor(machine_id, sim.rng, noise_sd=0.0))
    return sim


def day(sim: Simulator) -> list[tuple[bool, float, float]]:
    """(door_open, door_cooling, air_temperature) after each tick of one day."""
    seen = []
    for _ in range(DAY):
        sim.step()
        seen.append((sim.state.door_open, sim.state.door_cooling, sim.state.air_temperature))
    return seen


def door_events(sim: Simulator) -> list:
    return [e for e in sim.event_log.events if e.kind == "door"]


def test_the_door_starts_closed_and_the_air_is_the_building_temperature():
    state = FactoryState()
    assert (state.door_open, state.door_cooling) == (False, 0.0)
    assert state.air_temperature == state.ambient_temperature


def test_rejects_nonsense_settings():
    sim = Simulator(42, START)
    with pytest.raises(ValueError):
        LoadingDoor("a", sim.rng, min_open=10, max_open=5)
    with pytest.raises(ValueError):
        LoadingDoor("b", sim.rng, cooling=-1.0)


def test_the_door_is_not_a_fault_and_declares_no_ground_truth():
    assert factory().ground_truth() == ()


def test_the_door_opens_a_few_times_a_day_for_a_few_minutes_each():
    sim = factory()
    day(sim)
    events = door_events(sim)
    opened = [e.tick for e in events if e.message == "loading door opened"]
    closed = [e.tick for e in events if e.message == "loading door closed"]
    assert 1 <= len(opened) <= 15
    assert all(5 <= c - o <= 20 for o, c in zip(opened, closed))


def test_door_events_alternate_and_belong_to_no_machine():
    sim = factory()
    day(sim)
    events = door_events(sim)
    assert [e.message for e in events[:2]] == ["loading door opened", "loading door closed"]
    assert all(a.message != b.message for a, b in zip(events, events[1:]))
    assert {e.machine_id for e in events} == {None}


def test_events_fall_on_the_tick_the_door_actually_changed():
    sim = factory()
    seen = day(sim)
    changed = [tick for tick, (a, b) in enumerate(zip([(False,)] + seen, seen), start=1) if a[0] != b[0]]
    assert [e.tick for e in door_events(sim)] == changed


def test_cooling_builds_gradually_never_exceeds_five_degrees_and_fades_after():
    seen = day(factory())
    cooling = [c for _, c, _ in seen]
    assert 0.0 < max(cooling) <= 5.0
    assert all(abs(b - a) <= 0.5 + 1e-9 for a, b in zip(cooling, cooling[1:]))
    assert all(b >= a for (door, _, _), a, b in zip(seen[1:], cooling, cooling[1:]) if door)
    assert all(b <= a for (door, _, _), a, b in zip(seen[1:], cooling, cooling[1:]) if not door)
    assert cooling.count(0.0) > DAY // 2


def test_the_air_is_the_building_temperature_less_the_door_cooling():
    sim = factory()
    for _ in range(DAY):
        sim.step()
        assert sim.state.air_temperature == sim.state.ambient_temperature - sim.state.door_cooling


def test_it_does_not_matter_which_of_the_two_scenarios_runs_first():
    assert day(factory(door_first=False)) == day(factory(door_first=True))


def test_without_a_daily_cycle_the_air_still_returns_to_72():
    seen = day(factory(ambient=False))
    assert min(air for _, _, air in seen) < 72.0
    assert max(air for _, _, air in seen) == 72.0


def test_every_machine_dips_together_and_vibration_is_untouched():
    sim = factory()
    day(sim)
    temperature = {m: [r.value for r in sim.readings if r.machine_id == m and r.sensor == "temperature"] for m in ("CNC-01", "CNC-04")}
    assert temperature["CNC-01"] == pytest.approx(temperature["CNC-04"])
    assert {r.value for r in sim.readings if r.sensor == "vibration"} == {2.0}


def test_same_seed_gives_the_same_door_history():
    assert day(factory(42)) == day(factory(42))
    assert day(factory(42)) != day(factory(43))


def test_the_agent_sees_door_events_unless_it_filters_to_one_machine():
    sim = factory()
    day(sim)
    tools = ObservationTools(sim)
    seen = [e for e in tools.get_events(0, DAY) if e["kind"] == "door"]
    assert seen and seen[0]["machine_id"] is None
    assert [e for e in tools.get_events(0, DAY, "CNC-04") if e["kind"] == "door"] == []
