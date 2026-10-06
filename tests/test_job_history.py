import json
import re
from datetime import datetime

from capstone.simulator.scenarios import ProductionLine
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState, MachineStatus
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
LINE = ["CNC-01", "CNC-02", "CNC-04"]
BALANCED = (60, 60, 60)
UNEVEN = (60, 70, 55)  # CNC-02 is the slowest step


def factory(times: tuple[int, ...] = UNEVEN, ticks: int = 900, seed: int = 42) -> tuple[Simulator, ObservationTools]:
    sim = Simulator(seed, START)
    for machine_id, per_job in zip(LINE, times):
        sim.add_machine(MachineState(id=machine_id, ticks_per_job=per_job))
    sim.add_scenario(ProductionLine("line", sim.rng, machine_ids=LINE))
    for _ in range(ticks):
        sim.step()
    return sim, ObservationTools(sim)


def trail(tools: ObservationTools, job_id: int) -> list[tuple[int, str, str]]:
    return [(row["tick"], row["machine_id"], row["message"]) for row in tools.get_job_history(job_id)]


def test_the_line_order_is_part_of_the_factory_state():
    sim, _ = factory(ticks=1)
    assert sim.state.line == LINE


def test_job_1_on_an_empty_line_is_never_held_up():
    _, tools = factory()
    assert trail(tools, 1) == [
        (1, "CNC-01", "job 1 started"),
        (60, "CNC-01", "job 1 finished"),
        (61, "CNC-02", "job 1 started"),
        (130, "CNC-02", "job 1 finished"),
        (131, "CNC-04", "job 1 started"),
        (185, "CNC-04", "job 1 finished"),
    ]


def test_started_to_finished_is_always_the_machines_own_working_time():
    _, tools = factory()
    for job_id in range(1, 9):
        ticks = {(m, msg.split()[-1]): t for t, m, msg in trail(tools, job_id) if "blocked" not in msg}
        for machine_id, per_job in zip(LINE, UNEVEN):
            assert ticks[(machine_id, "finished")] - ticks[(machine_id, "started")] + 1 == per_job


def test_on_a_balanced_line_no_job_is_ever_held_up():
    sim, _ = factory(times=BALANCED)
    assert not [e for e in sim.event_log.events if "blocked" in e.message]


def test_the_machine_before_the_slow_one_is_held_up_on_every_job_once_the_line_is_full():
    _, tools = factory()
    for job_id in range(2, 9):
        held = [(t, m, msg) for t, m, msg in trail(tools, job_id) if "blocked" in msg]
        assert len(held) == 1
        tick, machine_id, message = held[0]
        assert (machine_id, message) == ("CNC-01", f"job {job_id} blocked by CNC-02")
        ticks = {(m, msg.split()[-1]): t for t, m, msg in trail(tools, job_id) if "blocked" not in msg}
        assert tick == ticks[("CNC-01", "finished")] + 1
        assert ticks[("CNC-02", "started")] - tick == 10  # the normal wait on this line


def test_a_breakdown_ahead_holds_the_job_with_no_end():
    sim, _ = factory(ticks=300)
    sim.state.machines["CNC-02"].status = MachineStatus.DOWN
    for _ in range(400):
        sim.step()
    tools = ObservationTools(sim)
    waiting = sim.state.machines["CNC-01"].job.id
    assert trail(tools, waiting)[-1][1:] == ("CNC-01", f"job {waiting} blocked by CNC-02")
    assert tools.get_events(650, 700) == []


def test_job_events_never_say_why_or_how_heavy():
    sim, _ = factory()
    allowed = re.compile(r"^job \d+ (started|finished|blocked by CNC-\d\d)$")
    job_events = [e for e in sim.event_log.events if e.kind == "job"]
    assert job_events and all(allowed.match(e.message) for e in job_events)
    assert all(e.job_id == int(e.message.split()[1]) for e in job_events)


def test_list_machines_shows_who_is_holding_what():
    sim, tools = factory(ticks=1)
    assert tools.list_machines() == [
        {"machine_id": "CNC-01", "status": "running", "job_id": 1},
        {"machine_id": "CNC-02", "status": "idle", "job_id": None},
        {"machine_id": "CNC-04", "status": "idle", "job_id": None},
    ]


def test_an_idle_machine_holding_a_job_looks_different_from_an_idle_empty_one():
    sim, _ = factory(ticks=0)
    seen = set()
    for _ in range(900):
        sim.step()
        for row in ObservationTools(sim).list_machines():
            if row["status"] == "idle":
                seen.add((row["machine_id"], row["job_id"] is not None))
    assert ("CNC-01", True) in seen and ("CNC-01", False) not in seen
    assert ("CNC-04", False) in seen and ("CNC-04", True) not in seen


def test_history_of_an_unknown_job_is_empty_and_answers_are_plain_data():
    _, tools = factory()
    assert tools.get_job_history(9999) == []
    assert json.loads(json.dumps(tools.get_job_history(3))) == tools.get_job_history(3)
    assert set(tools.get_job_history(3)[0]) == {"tick", "machine_id", "kind", "message", "job_id"}


def test_same_seed_gives_the_same_history():
    assert factory()[1].get_events(0, 900) == factory()[1].get_events(0, 900)
