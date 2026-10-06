from datetime import datetime

import pytest

from capstone.simulator.scenarios import BearingDegradation, ProductionLine
from capstone.simulator.sensors import LoadSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState, MachineStatus
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
LINE = ["CNC-01", "CNC-02", "CNC-04"]
BALANCED = (60, 60, 60)
UNEVEN = (60, 70, 55)  # CNC-02 is the slowest step
RATE = 0.001


def factory(seed: int = 42, times: tuple[int, ...] = BALANCED, wear_on: str | None = None) -> Simulator:
    sim = Simulator(seed, START)
    for machine_id, ticks in zip(LINE, times):
        sim.add_machine(MachineState(id=machine_id, ticks_per_job=ticks))
        sim.add_sensor(LoadSensor(machine_id, sim.rng, noise_sd=0.0, friction_gain=0.0))
    sim.add_scenario(ProductionLine("line", sim.rng, machine_ids=LINE))
    if wear_on:
        sim.add_scenario(
            BearingDegradation("bearing", sim.rng, machine_id=wear_on, start_tick=1, rate=RATE, variation=0.0)
        )
    return sim


def snapshot(sim: Simulator) -> dict[str, tuple]:
    """For each machine: (job id or None, status, load) as things stand now."""
    return {m.id: (m.job.id if m.job else None, m.status, m.load) for m in sim.state.machines.values()}


def run(sim: Simulator, ticks: int = 700) -> list[dict[str, tuple]]:
    history = []
    for _ in range(ticks):
        sim.step()
        history.append(snapshot(sim))
    return history


def ticks_holding(history: list[dict], machine_id: str, job_id: int) -> list[int]:
    return [tick for tick, snap in enumerate(history, start=1) if snap[machine_id][0] == job_id]


def idle_ticks(history: list[dict], machine_id: str, first: int, last: int) -> int:
    return sum(1 for snap in history[first - 1 : last] if snap[machine_id][1] is MachineStatus.IDLE)


def test_rejects_nonsense_settings():
    sim = Simulator(42, START)
    with pytest.raises(ValueError):
        ProductionLine("empty", sim.rng, machine_ids=[])
    with pytest.raises(ValueError):
        ProductionLine("twice", sim.rng, machine_ids=["A", "A"])
    with pytest.raises(ValueError):
        ProductionLine("loads", sim.rng, machine_ids=["A"], min_load=0.9, max_load=0.2)


def test_the_line_is_not_a_fault_and_declares_no_ground_truth():
    assert factory().ground_truth() == ()


def test_a_machine_takes_60_ticks_per_job_unless_told_otherwise():
    assert MachineState(id="CNC-01").ticks_per_job == 60


def test_on_the_first_tick_job_1_is_on_the_first_machine_and_the_rest_wait():
    first = run(factory(), 1)[0]
    assert first["CNC-01"][:2] == (1, MachineStatus.RUNNING)
    assert first["CNC-02"] == first["CNC-04"] == (None, MachineStatus.IDLE, 0.0)


def test_the_first_job_spends_each_machines_own_time_on_it_in_line_order():
    history = run(factory(times=UNEVEN))
    stays = [ticks_holding(history, machine_id, 1) for machine_id in LINE]
    assert [len(stay) for stay in stays] == [60, 70, 55]
    assert stays[0] == list(range(1, 61))
    assert stays[1] == list(range(61, 131))
    assert stays[2] == list(range(131, 186))


def test_jobs_enter_and_leave_in_numbered_order():
    sim = factory()
    history = run(sim)
    entered = []
    for snap in history:
        job = snap["CNC-01"][0]
        if job is not None and (not entered or entered[-1] != job):
            entered.append(job)
    assert entered == list(range(1, len(entered) + 1))
    assert sim.state.completed_jobs == list(range(1, len(sim.state.completed_jobs) + 1))
    assert len(sim.state.completed_jobs) >= 8


def test_a_job_is_never_on_two_machines_at_once():
    for snap in run(factory(times=UNEVEN)):
        held = [job for job, _, _ in snap.values() if job is not None]
        assert len(held) == len(set(held))


def test_a_running_machine_carries_its_jobs_load_and_an_idle_one_carries_none():
    sim = factory(times=UNEVEN)
    for _ in range(700):
        sim.step()
        for machine in sim.state.machines.values():
            if machine.status is MachineStatus.RUNNING:
                assert machine.load == machine.job.load and 0.3 <= machine.load <= 0.8
            else:
                assert machine.load == 0.0


def test_the_same_job_brings_the_same_load_to_every_machine():
    sim = factory()
    run(sim)
    load = {(r.machine_id, r.tick): r.value for r in sim.readings}
    assert load[("CNC-01", 30)] == pytest.approx(load[("CNC-02", 90)])
    assert load[("CNC-02", 90)] == pytest.approx(load[("CNC-04", 150)])
    assert load[("CNC-01", 30)] != pytest.approx(load[("CNC-01", 90)])  # job 2 is different work


def test_a_balanced_line_is_never_idle_once_it_has_filled_up():
    history = run(factory(times=BALANCED))
    assert [idle_ticks(history, machine_id, 1, 700) for machine_id in LINE] == [0, 60, 120]
    assert [idle_ticks(history, machine_id, 121, 700) for machine_id in LINE] == [0, 0, 0]


def test_an_uneven_line_waits_in_a_steady_pattern_around_its_slowest_machine():
    history = run(factory(times=UNEVEN), 900)
    # One full cycle of the slowest machine (70 ticks), well after start-up.
    per_cycle = [idle_ticks(history, machine_id, 481, 550) for machine_id in LINE]
    assert per_cycle == [10, 0, 15]
    assert per_cycle == [idle_ticks(history, machine_id, 551, 620) for machine_id in LINE]


def test_the_machine_before_the_slow_one_waits_holding_a_finished_job():
    waiting = [
        snap
        for snap in run(factory(times=UNEVEN))[200:]
        if snap["CNC-01"][1] is MachineStatus.IDLE
    ]
    assert waiting
    assert all(snap["CNC-01"][0] is not None and snap["CNC-02"][0] is not None for snap in waiting)


def test_the_machine_after_the_slow_one_waits_empty():
    waiting = [
        snap
        for snap in run(factory(times=UNEVEN))[200:]
        if snap["CNC-04"][1] is MachineStatus.IDLE
    ]
    assert waiting
    assert all(snap["CNC-04"][0] is None for snap in waiting)


def test_a_breakdown_in_the_middle_stops_the_whole_line():
    sim = factory()
    run(sim, 300)
    sim.state.machines["CNC-02"].status = MachineStatus.DOWN
    stuck_job = sim.state.machines["CNC-02"].job
    run(sim, 200)
    done_before = len(sim.state.completed_jobs)
    after = run(sim, 200)[-1]
    assert sim.state.machines["CNC-02"].job == stuck_job
    assert after["CNC-02"][1] is MachineStatus.DOWN
    assert after["CNC-01"][1] is MachineStatus.IDLE and after["CNC-01"][0] is not None  # blocked
    assert after["CNC-04"] == (None, MachineStatus.IDLE, 0.0)  # starved
    assert len(sim.state.completed_jobs) == done_before


def test_same_seed_gives_the_same_production_day():
    assert run(factory(42)) == run(factory(42))
    assert run(factory(42)) != run(factory(43))


def test_each_arrival_is_logged_once_and_names_the_job():
    sim = factory(times=UNEVEN)
    history = run(sim)
    events = [e for e in sim.event_log.events if e.kind == "job" and e.message.endswith("started")]
    assert (events[0].tick, events[0].machine_id, events[0].message) == (1, "CNC-01", "job 1 started")
    for event in events:
        job_id = int(event.message.split()[1])
        assert event.message == f"job {job_id} started"
        assert ticks_holding(history, event.machine_id, job_id)[0] == event.tick
    assert len(events) == len({(e.machine_id, e.message) for e in events})


def test_wear_follows_the_work_actually_done():
    sim = factory(times=UNEVEN, wear_on="CNC-04")
    expected, ran, waited = 1.0, 0, 0
    for _ in range(400):
        sim.step()
        machine = sim.state.machines["CNC-04"]
        if machine.status is MachineStatus.RUNNING:
            expected -= RATE * (machine.load / 0.5) ** 3
            ran += 1
        else:
            waited += 1
    assert sim.state.machines["CNC-04"].condition.bearing_health == pytest.approx(expected)
    assert ran > 0 and waited > 0


def test_the_agent_sees_id_status_and_current_job_for_each_machine_and_no_more():
    sim = factory()
    run(sim, 50)
    assert all(set(row) == {"machine_id", "status", "job_id"} for row in ObservationTools(sim).list_machines())
