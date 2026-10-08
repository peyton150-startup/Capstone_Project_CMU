from datetime import datetime

import pytest

from capstone.simulator.line import STANDARD_TICKS_PER_JOB, build_line, machine_names
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineStatus
from capstone.tools.observation import ObservationTools

DAY = 1440


def run(sim: Simulator, ticks: int = DAY) -> Simulator:
    for _ in range(ticks):
        sim.step()
    return sim


def test_machines_are_named_in_order():
    assert machine_names(3) == ["CNC-01", "CNC-02", "CNC-03"]
    assert machine_names(8)[-1] == "CNC-08"


def test_the_seed_decides_the_size_when_none_is_given():
    sizes = [len(build_line(seed).state.machines) for seed in range(60)]
    assert set(sizes) == {3, 4, 5, 6, 7, 8}
    assert sizes == [len(build_line(seed).state.machines) for seed in range(60)]


def test_a_given_size_overrides_the_seed_and_changes_nothing_else():
    chosen = len(build_line(42).state.machines)
    by_seed = run(build_line(42), 300)
    by_hand = run(build_line(42, machines=chosen), 300)
    assert by_seed.readings == by_hand.readings
    assert len(build_line(42, machines=3).state.machines) == 3


@pytest.mark.parametrize("machines", range(3, 9))
def test_any_size_from_three_to_eight_builds_and_runs(machines):
    sim = run(build_line(42, machines=machines), 200)
    assert (
        list(sim.state.machines) == machine_names(machines) == sim.state.lines["line"]
    )
    assert [m.ticks_per_job for m in sim.state.machines.values()] == list(
        STANDARD_TICKS_PER_JOB[:machines]
    )
    # vibration, temperature and load on every machine, plus the thermometer
    assert len(sim.readings) == 200 * (3 * machines + 1)


@pytest.mark.parametrize("machines", (0, 2, 9))
def test_sizes_outside_three_to_eight_are_refused(machines):
    with pytest.raises(ValueError):
        build_line(42, machines=machines)


def test_working_times_can_be_set_and_must_match_the_number_of_machines():
    sim = build_line(42, machines=4, ticks_per_job=(60, 60, 60, 60))
    assert {m.ticks_per_job for m in sim.state.machines.values()} == {60}
    with pytest.raises(ValueError):
        build_line(42, machines=4, ticks_per_job=(60, 60))


def test_a_healthy_day_has_work_door_openings_and_no_trouble():
    sim = run(build_line(42, machines=3))
    kinds = {e.kind for e in sim.event_log.events}
    assert kinds == {"job", "door", "inspection", "batch"}  # no alarms, no stops
    assert sim.ground_truth() == ()
    assert len(sim.state.completed_jobs) >= 15
    assert all(m.condition.bearing_health == 1.0 for m in sim.state.machines.values())
    assert sim.thermal_lag_ticks == 20.0


def test_jobs_reach_the_end_of_the_longest_line():
    sim = run(build_line(42, machines=8))
    history = ObservationTools(sim).get_job_history(1)
    assert [
        row["machine_id"] for row in history if row["message"].endswith("started")
    ] == machine_names(8)
    assert sim.state.completed_jobs[:3] == [1, 2, 3]


def test_the_second_machine_is_the_slowest_step_so_the_first_is_held_up():
    sim = run(build_line(42, machines=3))
    blocked = {
        (e.machine_id, e.message.split("blocked by ")[1])
        for e in sim.event_log.events
        if "blocked" in e.message
    }
    assert blocked == {("CNC-01", "CNC-02")}


def test_the_afternoon_peak_follows_the_clock_whatever_time_the_run_starts():
    for start_hour in (6, 9, 22):
        sim = build_line(42, start=datetime(2026, 1, 5, start_hour, 0))
        warmest, warmest_at = -1.0, None
        for _ in range(DAY):
            sim.step()
            if sim.state.ambient_temperature > warmest:
                warmest, warmest_at = sim.state.ambient_temperature, sim.clock.now
        assert 14 <= warmest_at.hour <= 17


def test_same_seed_gives_the_same_day_and_a_different_seed_a_different_one():
    def day(seed):
        sim = run(build_line(seed), 600)
        return sim.readings, sim.event_log.events

    assert day(42) == day(42)
    assert day(42) != day(43)


def test_a_fault_added_afterwards_sees_the_lines_work_and_stops_the_line():
    sim = build_line(42, machines=5)
    sim.add_scenario(
        BearingDegradation(
            "bearing", sim.rng, machine_id="CNC-03", start_tick=100, rate=0.002
        )
    )
    run(sim, 2000)
    assert [g.machine_id for g in sim.ground_truth()] == ["CNC-03"]
    stops = [e for e in sim.event_log.events if e.kind == "status"]
    assert [e.machine_id for e in stops] == ["CNC-03"]
    statuses = {m.id: m.status for m in sim.state.machines.values()}
    assert statuses["CNC-03"] is MachineStatus.DOWN
    assert all(
        status is MachineStatus.IDLE
        for name, status in statuses.items()
        if name != "CNC-03"
    )
    assert sim.state.machines["CNC-01"].condition.bearing_health == 1.0


def test_the_agents_tools_work_on_the_standard_line():
    tools = ObservationTools(run(build_line(42, machines=6), 300))
    assert [row["machine_id"] for row in tools.list_machines()] == machine_names(6)
    assert len(tools.get_factory_readings("air_temperature", 1, 300)) == 300
    assert len(tools.get_readings("CNC-06", "temperature", 1, 300)) == 300
