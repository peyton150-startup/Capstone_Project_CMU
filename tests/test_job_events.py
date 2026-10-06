from datetime import datetime

import pytest

from capstone.simulator.events import ThresholdAlarm
from capstone.simulator.scenarios import BearingDegradation, Workload
from capstone.simulator.sensors import LoadSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)


def factory(workload: bool = True, start_job: int = 0) -> Simulator:
    sim = Simulator(42, START)
    sim.add_machine(MachineState(id="CNC-04", job_number=start_job))
    sim.add_sensor(VibrationSensor("CNC-04", sim.rng))
    sim.add_sensor(LoadSensor("CNC-04", sim.rng, noise_sd=0.0))
    sim.add_alarm(ThresholdAlarm("vibration", 4.5))
    if workload:
        sim.add_scenario(Workload("workload.CNC-04", sim.rng, machine_id="CNC-04"))
    return sim


def run(sim: Simulator, ticks: int = 400) -> list[tuple[float, int]]:
    """Step the factory, returning (load, job_number) as it stood after each tick."""
    seen = []
    for _ in range(ticks):
        sim.step()
        machine = sim.state.machines["CNC-04"]
        seen.append((machine.load, machine.job_number))
    return seen


def job_events(sim: Simulator) -> list:
    return [e for e in sim.event_log.events if e.kind == "job"]


def test_a_new_machine_has_started_no_jobs():
    assert MachineState(id="CNC-04").job_number == 0


def test_no_workload_means_no_job_events():
    sim = factory(workload=False)
    run(sim)
    assert job_events(sim) == []


def test_a_machine_that_starts_mid_job_does_not_report_a_new_one():
    sim = factory(workload=False, start_job=7)
    run(sim, 5)
    assert job_events(sim) == []


def test_the_job_number_rises_exactly_when_the_load_changes():
    seen = run(factory())
    for (load_a, job_a), (load_b, job_b) in zip(seen, seen[1:]):
        assert (load_a != load_b) == (job_b == job_a + 1)
        assert job_b in (job_a, job_a + 1)


def test_each_new_job_is_recorded_once_on_the_tick_it_starts():
    sim = factory()
    seen = run(sim)
    started = [1] + [tick for tick, (a, b) in enumerate(zip(seen, seen[1:]), start=2) if a[1] != b[1]]
    assert [e.tick for e in job_events(sim)] == started
    assert len(job_events(sim)) == seen[-1][1]


def test_the_event_says_a_job_started_and_not_how_heavy_it_is():
    sim = factory()
    run(sim)
    assert {(e.machine_id, e.message) for e in job_events(sim)} == {("CNC-04", "new job started")}


def test_the_load_reading_changes_on_the_same_tick_as_the_event():
    sim = factory()
    run(sim)
    load = {r.tick: r.value for r in sim.readings if r.sensor == "load"}
    for event in job_events(sim)[1:]:
        assert load[event.tick] != pytest.approx(load[event.tick - 1])
        assert load[event.tick] == pytest.approx(load[event.tick + 1]) or event.tick == 400


def test_job_events_sit_alongside_alarms_and_stops_in_tick_order():
    sim = factory()
    sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-04", start_tick=50, rate=0.002))
    run(sim, 900)
    events = sim.event_log.events
    assert {e.kind for e in events} == {"job", "alarm", "status"}
    assert [e.tick for e in events] == sorted(e.tick for e in events)


def test_the_agent_can_read_job_events_through_the_tools():
    sim = factory()
    run(sim)
    seen = [e for e in ObservationTools(sim).get_events(0, 400) if e["kind"] == "job"]
    assert seen[0] == {"tick": 1, "machine_id": "CNC-04", "kind": "job", "message": "new job started"}
