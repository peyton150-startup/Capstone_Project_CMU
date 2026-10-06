import json
from datetime import datetime

import pytest

from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import ProductionLine
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
LINE = ["CNC-01", "CNC-02", "CNC-03"]


def factory(healths: tuple[float, ...] = (1.0, 1.0, 1.0), ticks: int = 6000, seed: int = 42) -> Simulator:
    """A balanced three-machine line with each machine's bearing fixed at the given health."""
    sim = Simulator(seed, START)
    for machine_id, health in zip(LINE, healths):
        sim.add_machine(MachineState(id=machine_id, condition=MachineCondition(bearing_health=health)))
    sim.add_scenario(ProductionLine("line", sim.rng, machine_ids=LINE))
    for _ in range(ticks):
        sim.step()
    return sim


def failure_rate(sim: Simulator) -> float:
    results = sim.state.inspections
    return sum(1 for r in results if not r.passed) / len(results)


def test_every_job_that_leaves_the_line_is_inspected_once_in_order_on_the_tick_it_left():
    sim = factory(ticks=1500)
    assert [r.job_id for r in sim.state.inspections] == sim.state.completed_jobs
    left = {e.job_id: e.tick + 1 for e in sim.event_log.events if e.machine_id == "CNC-03" and e.message.endswith("finished")}
    assert all(r.tick == left[r.job_id] for r in sim.state.inspections)


def test_a_healthy_line_fails_about_one_job_in_a_hundred():
    sim = factory()
    assert len(sim.state.inspections) >= 95
    assert failure_rate(sim) <= 0.05


def test_a_healthy_machine_leaves_no_mark_on_a_job():
    sim = factory(ticks=150)
    assert sim.state.machines["CNC-03"].job.defect_risk == 0.0


def test_a_worn_machine_marks_each_job_once_as_it_finishes_its_part():
    sim = factory(healths=(1.0, 0.3, 1.0), ticks=150)
    job_past_the_worn_machine = sim.state.machines["CNC-03"].job
    assert job_past_the_worn_machine.defect_risk == pytest.approx(0.45 * 0.7**2)
    job_not_there_yet = sim.state.machines["CNC-01"].job
    assert job_not_there_yet.defect_risk == 0.0


def test_two_worn_machines_add_their_marks_together():
    sim = factory(healths=(0.5, 0.5, 1.0), ticks=150)
    assert sim.state.machines["CNC-03"].job.defect_risk == pytest.approx(2 * 0.45 * 0.5**2)


def test_a_badly_worn_machine_fails_roughly_one_job_in_four():
    sim = factory(healths=(1.0, 0.3, 1.0))
    assert len(sim.state.inspections) >= 60
    assert 0.12 <= failure_rate(sim) <= 0.36


def test_more_wear_means_more_failures():
    rates = [failure_rate(factory(healths=(1.0, health, 1.0))) for health in (1.0, 0.5, 0.2)]
    assert rates[0] < rates[1] < rates[2]


def test_each_result_is_reported_once_as_a_factory_event_naming_the_job():
    sim = factory(healths=(1.0, 0.3, 1.0), ticks=1500)
    events = [e for e in sim.event_log.events if e.kind == "inspection"]
    assert len(events) == len(sim.state.inspections)
    for event, result in zip(events, sim.state.inspections):
        word = "passed" if result.passed else "failed"
        assert (event.tick, event.machine_id, event.job_id) == (result.tick, None, result.job_id)
        assert event.message == f"job {result.job_id} {word} inspection"


def test_the_inspection_is_the_last_entry_in_a_jobs_history():
    tools = ObservationTools(factory(ticks=1500))
    history = tools.get_job_history(3)
    assert history[-1]["message"] in ("job 3 passed inspection", "job 3 failed inspection")
    assert history[-2]["message"] == "job 3 finished"


def test_get_inspections_returns_results_in_a_tick_range_as_plain_data():
    sim = factory(healths=(1.0, 0.3, 1.0), ticks=1500)
    tools = ObservationTools(sim)
    everything = tools.get_inspections(0, 1500)
    assert [(r["job_id"], r["result"] == "passed") for r in everything] == [
        (r.job_id, r.passed) for r in sim.state.inspections
    ]
    assert set(everything[0]) == {"tick", "job_id", "batch_id", "result"}
    assert tools.get_inspections(0, everything[0]["tick"] - 1) == []
    assert json.loads(json.dumps(everything)) == everything


def test_the_agent_sees_pass_or_fail_and_never_the_risk():
    tools = ObservationTools(factory(healths=(1.0, 0.3, 1.0), ticks=1500))
    seen = json.dumps([tools.list_machines(), tools.get_events(0, 1500), tools.get_inspections(0, 1500)])
    assert "risk" not in seen and "0.22" not in seen
    assert all(set(row) == {"machine_id", "status", "job_id"} for row in tools.list_machines())


def test_inspections_use_their_own_stream_so_job_loads_are_what_they_always_were():
    sim = factory(ticks=1)
    expected_first_load = RandomSource(42).stream("scenario.line").uniform(0.3, 0.8)
    assert sim.state.machines["CNC-01"].job.load == expected_first_load


def test_same_seed_gives_the_same_results_and_another_seed_different_ones():
    def results(seed):
        return [r.passed for r in factory(healths=(1.0, 0.3, 1.0), seed=seed).state.inspections]

    assert results(42) == results(42)
    assert results(42) != results(43)
