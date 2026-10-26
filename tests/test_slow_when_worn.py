from datetime import datetime

import pytest

from capstone.simulator.events import ThresholdAlarm
from capstone.simulator.line import build_line
from capstone.simulator.scenarios import (
    BearingDegradation,
    ProductionLine,
    working_speed,
)
from capstone.simulator.sensors import VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
LINE = ["CNC-01", "CNC-02", "CNC-03"]
TIMES = (60, 70, 55)


def factory(
    worn_health: float = 1.0,
    variation: int = 0,
    degrade: bool = False,
    ticks: int = 1500,
    seed: int = 42,
) -> tuple[Simulator, ObservationTools]:
    """The standard three-machine line, with CNC-02's bearing at `worn_health`."""
    sim = Simulator(seed, START)
    for machine_id, per_job in zip(LINE, TIMES):
        health = worn_health if machine_id == "CNC-02" else 1.0
        sim.add_machine(
            MachineState(
                id=machine_id,
                ticks_per_job=per_job,
                condition=MachineCondition(bearing_health=health),
            )
        )
        sim.add_sensor(VibrationSensor(machine_id, sim.rng))
    sim.add_alarm(ThresholdAlarm("vibration", 4.5))
    sim.add_scenario(
        ProductionLine("line", sim.rng, machine_ids=LINE, time_variation=variation)
    )
    if degrade:
        sim.add_scenario(
            BearingDegradation(
                "bearing", sim.rng, machine_id="CNC-02", start_tick=1, rate=0.0006
            )
        )
    for _ in range(ticks):
        sim.step()
    return sim, ObservationTools(sim)


def times(tools: ObservationTools, job_id: int) -> dict[tuple[str, str], int]:
    """(machine, 'started' | 'finished' | 'blocked') -> tick, for one job."""
    return {
        (row["machine_id"], row["message"].split()[2]): row["tick"]
        for row in tools.get_job_history(job_id)
    }


def working_time(tools: ObservationTools, job_id: int, machine_id: str) -> int:
    seen = times(tools, job_id)
    return seen[(machine_id, "finished")] - seen[(machine_id, "started")] + 1


def wait_on_first_machine(tools: ObservationTools, job_id: int) -> int:
    seen = times(tools, job_id)
    return seen[("CNC-02", "started")] - seen[("CNC-01", "finished")] - 1


def test_a_healthy_machine_works_at_full_speed_and_wear_slows_it_gently_then_sharply():
    def speed(health):
        return working_speed(
            MachineState(id="X", condition=MachineCondition(bearing_health=health))
        )

    assert speed(1.0) == 1.0
    assert speed(0.7) == pytest.approx(0.964)
    assert speed(0.5) == pytest.approx(0.9)
    assert speed(0.1) == pytest.approx(0.676)
    assert (speed(1.0) - speed(0.7)) < (speed(0.7) - speed(0.4))


def test_a_healthy_line_keeps_its_exact_times():
    _, tools = factory()
    assert [working_time(tools, 5, m) for m in LINE] == [60, 70, 55]
    assert wait_on_first_machine(tools, 5) == 10


def test_a_half_worn_machine_takes_78_ticks_instead_of_70():
    _, tools = factory(worn_health=0.5)
    assert [working_time(tools, job, "CNC-02") for job in range(2, 8)] == [78] * 6


def test_its_neighbours_keep_their_own_working_times():
    _, tools = factory(worn_health=0.5)
    assert {working_time(tools, job, "CNC-01") for job in range(2, 8)} == {60}
    assert {working_time(tools, job, "CNC-03") for job in range(2, 8)} == {55}


def test_the_machine_before_it_waits_longer_holding_finished_jobs():
    _, tools = factory(worn_health=0.5)
    assert [wait_on_first_machine(tools, job) for job in range(3, 8)] == [18] * 5


def test_the_machine_after_it_waits_longer_empty():
    _, tools = factory(worn_health=0.5)
    gaps = []
    for job in range(3, 8):
        finished_previous = times(tools, job - 1)[("CNC-03", "finished")]
        gaps.append(times(tools, job)[("CNC-03", "started")] - finished_previous - 1)
    assert gaps == [78 - 55] * 5


def test_a_worn_machine_means_fewer_finished_jobs():
    healthy, _ = factory()
    worn, _ = factory(worn_health=0.3)
    assert len(worn.state.completed_jobs) < len(healthy.state.completed_jobs)


def test_as_the_bearing_wears_each_job_takes_at_least_as_long_as_the_last():
    sim, tools = factory(degrade=True, ticks=1400)
    done = [job for job in range(1, 30) if ("CNC-02", "finished") in times(tools, job)]
    taken = [working_time(tools, job, "CNC-02") for job in done]
    assert taken[0] <= 71  # barely worn yet when the first job reaches it
    assert all(later >= earlier for earlier, later in zip(taken, taken[1:]))
    assert taken[-1] >= 78
    alarms = [e.tick for e in sim.event_log.events if e.kind == "alarm"]
    assert alarms  # prove the installed alarm actually detects the later symptoms
    slowed_finishes = [
        times(tools, job)[("CNC-02", "finished")]
        for job, duration in zip(done, taken)
        if duration > 72  # beyond the standard line's ordinary 68-72 tick variation
    ]
    assert slowed_finishes and min(slowed_finishes) < min(alarms)


def test_natural_variation_keeps_each_job_within_two_ticks_of_normal():
    _, tools = factory(variation=2)
    for machine_id, normal in zip(LINE, TIMES):
        taken = [working_time(tools, job, machine_id) for job in range(1, 15)]
        assert all(abs(t - normal) <= 2 for t in taken)
        assert len(set(taken)) > 1


def test_with_variation_a_slightly_worn_machine_hides_among_normal_jobs():
    _, healthy = factory(variation=2)
    _, worn = factory(worn_health=0.8, variation=2)  # costs about one tick per job
    healthy_times = [working_time(healthy, job, "CNC-02") for job in range(1, 15)]
    worn_times = [working_time(worn, job, "CNC-02") for job in range(1, 15)]
    assert max(worn_times) <= max(healthy_times) + 2
    assert set(healthy_times) & set(worn_times)
    assert sum(worn_times) > sum(healthy_times)  # only the average gives it away


def test_same_seed_gives_the_same_times_and_another_seed_different_ones():
    def all_times(seed):
        _, tools = factory(variation=2, seed=seed)
        return [working_time(tools, job, m) for job in range(1, 12) for m in LINE]

    assert all_times(42) == all_times(42)
    assert all_times(42) != all_times(43)


def test_nothing_about_speed_or_progress_reaches_the_agent_directly():
    _, tools = factory(worn_health=0.3)
    assert all(
        set(row) == {"machine_id", "status", "job_id", "hydraulics"}
        for row in tools.list_machines()
    )
    text = " ".join(row["message"] for row in tools.get_events(0, 1500))
    assert "slow" not in text and "worn" not in text and "speed" not in text


def test_the_standard_line_has_natural_variation_switched_on():
    sim = build_line(42, machines=3)
    for _ in range(900):
        sim.step()
    tools = ObservationTools(sim)
    taken = [working_time(tools, job, "CNC-02") for job in range(1, 10)]
    assert all(68 <= t <= 72 for t in taken) and len(set(taken)) > 1
