from datetime import datetime

import pytest

from capstone.simulator.scenarios import BearingDegradation, ProductionLine
from capstone.simulator.sensors import LoadSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState, MachineStatus
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
LINE = ["CNC-01", "CNC-02", "CNC-04"]
RATE = 0.001


def factory(seed: int = 42, wear_on: str | None = None) -> Simulator:
    sim = Simulator(seed, START)
    for machine_id in LINE:
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(LoadSensor(machine_id, sim.rng, noise_sd=0.0, friction_gain=0.0))
    sim.add_scenario(ProductionLine("line", sim.rng, machine_ids=LINE))
    if wear_on:
        sim.add_scenario(
            BearingDegradation("bearing", sim.rng, machine_id=wear_on, start_tick=1, rate=RATE, variation=0.0)
        )
    return sim


def snapshot(sim: Simulator) -> dict[str, tuple]:
    """For each machine: (job id or None, status, load) as things stand now."""
    return {
        m.id: (m.job.id if m.job else None, m.status, m.load) for m in sim.state.machines.values()
    }


def run(sim: Simulator, ticks: int = 600) -> list[dict[str, tuple]]:
    history = []
    for _ in range(ticks):
        sim.step()
        history.append(snapshot(sim))
    return history


def ticks_holding(history: list[dict], machine_id: str, job_id: int) -> list[int]:
    return [tick for tick, snap in enumerate(history, start=1) if snap[machine_id][0] == job_id]


def test_rejects_nonsense_settings():
    sim = Simulator(42, START)
    for bad in ({"machine_ids": []}, {"machine_ids": ["A", "A"]}, {"machine_ids": ["A"], "min_ticks": 9, "max_ticks": 3}):
        with pytest.raises(ValueError):
            ProductionLine(f"line{len(bad)}{bad.get('min_ticks', 0)}{len(bad['machine_ids'])}", sim.rng, **bad)


def test_the_line_is_not_a_fault_and_declares_no_ground_truth():
    assert factory().ground_truth() == ()


def test_on_the_first_tick_job_1_is_on_the_first_machine_and_the_rest_wait():
    first = run(factory(), 1)[0]
    assert first["CNC-01"][:2] == (1, MachineStatus.RUNNING)
    assert first["CNC-02"] == first["CNC-04"] == (None, MachineStatus.IDLE, 0.0)


def test_the_first_job_spends_its_working_time_on_each_machine_in_line_order():
    sim = factory()
    history = run(sim)
    stays = [ticks_holding(history, machine_id, 1) for machine_id in LINE]
    length = len(stays[0])
    assert 30 <= length <= 90
    for stay in stays:
        assert stay == list(range(stay[0], stay[0] + length))
    assert stays[1][0] == stays[0][-1] + 1 and stays[2][0] == stays[1][-1] + 1


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
    assert len(sim.state.completed_jobs) >= 3


def test_a_job_is_never_on_two_machines_at_once():
    for snap in run(factory()):
        held = [job for job, _, _ in snap.values() if job is not None]
        assert len(held) == len(set(held))


def test_a_running_machine_carries_its_jobs_load_and_an_idle_one_carries_none():
    sim = factory()
    for _ in range(600):
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
    history_first = ticks_holding(run(factory()), "CNC-01", 1)
    job_load = load[("CNC-01", history_first[0])]
    length = len(history_first)
    assert load[("CNC-02", history_first[0] + length)] == pytest.approx(job_load)
    assert load[("CNC-04", history_first[0] + 2 * length)] == pytest.approx(job_load)


def test_a_finished_job_waits_when_the_next_machine_is_still_busy():
    waited = [
        snap
        for snap in run(factory())
        if snap["CNC-01"][0] is not None and snap["CNC-01"][1] is MachineStatus.IDLE
    ]
    assert waited
    assert all(snap["CNC-02"][0] is not None for snap in waited)


def test_a_breakdown_in_the_middle_stops_the_whole_line():
    sim = factory()
    run(sim, 300)
    sim.state.machines["CNC-02"].status = MachineStatus.DOWN
    stuck_job, done_before = sim.state.machines["CNC-02"].job, None
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
    sim = factory()
    history = run(sim)
    events = [e for e in sim.event_log.events if e.kind == "job"]
    assert (events[0].tick, events[0].machine_id, events[0].message) == (1, "CNC-01", "job 1 started")
    for event in events:
        job_id = int(event.message.split()[1])
        assert event.message == f"job {job_id} started"
        assert ticks_holding(history, event.machine_id, job_id)[0] == event.tick
    assert len(events) == len({(e.machine_id, e.message) for e in events})


def test_wear_follows_the_work_actually_done():
    sim = factory(wear_on="CNC-02")
    expected = 1.0
    for _ in range(400):
        sim.step()
        machine = sim.state.machines["CNC-02"]
        if machine.status is MachineStatus.RUNNING:
            expected -= RATE * (machine.load / 0.5) ** 3
    assert sim.state.machines["CNC-02"].condition.bearing_health == pytest.approx(expected)
    assert expected < 1.0


def test_the_agent_still_sees_only_id_and_status_for_each_machine():
    sim = factory()
    run(sim, 50)
    assert all(set(row) == {"machine_id", "status"} for row in ObservationTools(sim).list_machines())
