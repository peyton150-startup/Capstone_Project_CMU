"""Nothing in the simulator assumes a single line. We only build one today;
these tests keep the door open for a second."""

from datetime import datetime

import pytest

from capstone.simulator.scenarios import ProductionLine
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState, MachineStatus

START = datetime(2026, 1, 5, 6, 0)
LINE_A = ["A-01", "A-02", "A-03"]
LINE_B = ["B-01", "B-02", "B-03"]
TIMES = (60, 70, 55)


def factory(ticks: int = 0) -> Simulator:
    sim = Simulator(42, START)
    for names in (LINE_A, LINE_B):
        for machine_id, per_job in zip(names, TIMES):
            sim.add_machine(MachineState(id=machine_id, ticks_per_job=per_job))
    sim.add_scenario(ProductionLine("line-a", sim.rng, machine_ids=LINE_A))
    sim.add_scenario(ProductionLine("line-b", sim.rng, machine_ids=LINE_B))
    for _ in range(ticks):
        sim.step()
    return sim


def test_both_lines_are_recorded_by_name():
    assert factory(1).state.lines == {"line-a": LINE_A, "line-b": LINE_B}


def test_both_lines_finish_jobs_and_no_two_jobs_share_a_number():
    sim = factory(900)
    started = [e for e in sim.event_log.events if e.message.endswith("started")]
    on_a = {e.job_id for e in started if e.machine_id in LINE_A}
    on_b = {e.job_id for e in started if e.machine_id in LINE_B}
    assert on_a and on_b and not on_a & on_b
    assert len(sim.state.completed_jobs) == len(set(sim.state.completed_jobs)) >= 16


def test_a_job_stays_on_the_line_it_entered():
    sim = factory(900)
    for job_id in sim.state.completed_jobs:
        visited = [
            e.machine_id
            for e in sim.event_log.events
            if e.job_id == job_id and e.message.endswith("started")
        ]
        assert visited in (LINE_A, LINE_B)


def test_a_held_up_job_names_the_next_machine_on_its_own_line():
    sim = factory(900)
    blocked = {
        (e.machine_id, e.message.split("blocked by ")[1])
        for e in sim.event_log.events
        if "blocked" in e.message
    }
    assert blocked == {("A-01", "A-02"), ("B-01", "B-02")}


def test_a_breakdown_on_one_line_leaves_the_other_running():
    sim = factory(300)
    sim.state.machines["A-02"].status = MachineStatus.DOWN
    for _ in range(300):
        sim.step()
    before = list(sim.state.completed_jobs)
    for _ in range(300):
        sim.step()
    finished_since = [job for job in sim.state.completed_jobs if job not in before]
    last_machine = {
        e.job_id: e.machine_id
        for e in sim.event_log.events
        if e.message.endswith("finished")
    }
    assert finished_since and {last_machine[job] for job in finished_since} == {"B-03"}


def test_a_machine_cannot_be_on_two_lines():
    sim = Simulator(42, START)
    for machine_id in ("X-01", "X-02", "X-03"):
        sim.add_machine(MachineState(id=machine_id))
    sim.add_scenario(ProductionLine("first", sim.rng, machine_ids=["X-01", "X-02"]))
    sim.add_scenario(ProductionLine("second", sim.rng, machine_ids=["X-02", "X-03"]))
    with pytest.raises(ValueError):
        sim.step()
