import json
from datetime import datetime

import pytest

from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BadMaterialBatch, ProductionLine
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
LINE = ["CNC-01", "CNC-02", "CNC-03"]
PER_BATCH = 25
BAD = 3  # jobs 51 to 75
RISK = 0.40


def factory(
    bad_batch: int | None = BAD,
    healths: tuple[float, ...] = (1.0, 1.0, 1.0),
    jobs_per_batch: int = PER_BATCH,
    seed: int = 42,
) -> Simulator:
    """A balanced three-machine line cutting jobs from batches, with one bad batch unless told otherwise."""
    sim = Simulator(seed, START)
    for machine_id, health in zip(LINE, healths):
        sim.add_machine(MachineState(id=machine_id, condition=MachineCondition(bearing_health=health)))
    sim.add_scenario(ProductionLine("line", sim.rng, machine_ids=LINE, jobs_per_batch=jobs_per_batch))
    if bad_batch is not None:
        sim.add_scenario(BadMaterialBatch("bad-batch", sim.rng, batch_number=bad_batch, added_risk=RISK))
    return sim


def run(sim: Simulator, ticks: int = 9000) -> Simulator:
    for _ in range(ticks):
        sim.step()
    return sim


def run_until_first_machine_holds_batch(sim: Simulator, batch_id: int) -> Simulator:
    while (job := sim.state.machines["CNC-01"].job) is None or job.batch_id != batch_id:
        sim.step()
    return sim


def failures(sim: Simulator, in_bad_batch: bool) -> list[bool]:
    return [not r.passed for r in sim.state.inspections if (r.batch_id == BAD) == in_bad_batch]


def test_each_job_carries_the_number_of_the_batch_it_was_cut_from():
    sim = run(factory(bad_batch=None))
    assert len(sim.state.inspections) > 3 * PER_BATCH
    assert all(r.batch_id == (r.job_id - 1) // PER_BATCH + 1 for r in sim.state.inspections)


def test_a_line_that_does_not_use_batches_has_none():
    sim = run(factory(bad_batch=None, jobs_per_batch=0), ticks=500)
    assert sim.state.batch is None
    assert all(r.batch_id is None for r in sim.state.inspections)
    assert not [e for e in sim.event_log.events if e.kind == "batch"]


def test_a_good_batch_adds_nothing_to_a_job():
    sim = run(factory(bad_batch=None), ticks=150)
    assert sim.state.machines["CNC-01"].job.defect_risk == 0.0


def test_the_scenario_changes_only_the_bad_batchs_hidden_quality():
    sim = factory()
    seen: dict[int, float] = {}
    for _ in range(9000):
        sim.step()
        seen[sim.state.batch.id] = max(seen.get(sim.state.batch.id, 0.0), sim.state.batch.defect_risk)
    assert seen[BAD] == RISK
    assert all(risk == 0.0 for batch_id, risk in seen.items() if batch_id != BAD)
    assert all(m.condition.bearing_health == 1.0 for m in sim.state.machines.values())


def test_every_job_cut_from_the_bad_batch_starts_with_its_risk_including_the_first():
    sim = run_until_first_machine_holds_batch(factory(), BAD)
    first = sim.state.machines["CNC-01"].job
    assert first.id == (BAD - 1) * PER_BATCH + 1
    assert first.defect_risk == RISK


def test_the_fault_ends_by_itself_when_the_batch_runs_out():
    sim = run_until_first_machine_holds_batch(factory(), BAD + 1)
    assert sim.state.machines["CNC-01"].job.defect_risk == 0.0


def test_failures_cluster_in_the_bad_batch_and_nowhere_else():
    sim = run(factory())
    bad, others = failures(sim, True), failures(sim, False)
    assert len(bad) == PER_BATCH and len(others) >= 3 * PER_BATCH
    assert sum(bad) >= 5
    assert sum(others) / len(others) <= 0.05


def test_not_every_job_from_the_bad_batch_fails():
    assert sum(failures(run(factory()), True)) < PER_BATCH


def test_a_bad_batch_and_a_worn_machine_add_up_on_the_same_job():
    sim = run_until_first_machine_holds_batch(factory(healths=(0.5, 1.0, 1.0)), BAD)
    job = sim.state.machines["CNC-01"].job
    while sim.state.machines["CNC-02"].job is not job:
        sim.step()
    assert job.defect_risk == pytest.approx(RISK + 0.45 * 0.5**2)


def test_no_sensor_reading_and_no_job_load_changes_because_of_a_bad_batch():
    def day(with_fault: bool) -> Simulator:
        sim = build_line(42, machines=3)
        if with_fault:
            sim.add_scenario(BadMaterialBatch("bad-batch", sim.rng, batch_number=2))
        return run(sim, ticks=6000)

    clean, faulty = day(False), day(True)
    assert faulty.readings == clean.readings
    assert [r.passed for r in faulty.state.inspections] != [r.passed for r in clean.state.inspections]


def test_each_batch_is_announced_once_as_a_factory_event_before_its_first_job():
    sim = run(factory())
    opened = [e for e in sim.event_log.events if e.kind == "batch"]
    assert [e.message for e in opened[:3]] == [f"material batch {n} opened" for n in (1, 2, 3)]
    assert all(e.machine_id is None and e.job_id is None for e in opened)
    first_job_of_batch_3 = (BAD - 1) * PER_BATCH + 1
    started = next(e.tick for e in sim.event_log.events if e.job_id == first_job_of_batch_3)
    assert opened[2].tick < started


def test_the_ground_truth_names_the_batch_and_no_machine():
    (truth,) = factory().ground_truth()
    assert (truth.fault, truth.batch_id, truth.machine_id) == ("bad_material_batch", BAD, None)


def test_the_agent_sees_batch_numbers_and_never_the_quality():
    sim = run(factory())
    tools = ObservationTools(sim)
    results = tools.get_inspections(0, 9000)
    assert [r["batch_id"] for r in results] == [r.batch_id for r in sim.state.inspections]
    seen = json.dumps([tools.list_machines(), tools.get_events(0, 9000), results])
    assert "risk" not in seen and "0.4" not in seen and "bad" not in seen


def test_the_first_batch_cannot_be_the_bad_one_and_the_risk_must_be_real():
    sim = Simulator(42, START)
    with pytest.raises(ValueError):
        BadMaterialBatch("a", sim.rng, batch_number=1)
    with pytest.raises(ValueError):
        BadMaterialBatch("b", sim.rng, batch_number=2, added_risk=0.0)


def test_same_seed_gives_the_same_results_and_another_seed_different_ones():
    def results(seed):
        return [r.passed for r in run(factory(seed=seed)).state.inspections]

    assert results(42) == results(42)
    assert results(42) != results(43)
