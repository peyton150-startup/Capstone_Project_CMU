import json

import pytest

from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.simulator import Simulator
from capstone.tools.actions import ActionTools
from capstone.tools.observation import ObservationTools


def factory(fault: bool = False) -> tuple[Simulator, ObservationTools, ActionTools]:
    sim = build_line(42, machines=3)
    if fault:
        sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-02", start_tick=1, rate=0.004))
    return sim, ObservationTools(sim), ActionTools(sim)


def look_around(look: ObservationTools) -> None:
    look.list_machines()
    look.get_readings("CNC-02", "vibration", 0, 10_000)
    look.get_events(0, 10_000)
    look.get_factory_readings("air_temperature", 0, 10_000)


def test_wait_is_one_of_the_agents_action_tools():
    assert "wait" in {name for name in dir(ActionTools) if not name.startswith("_")}


def test_wait_moves_the_clock_by_exactly_that_many_ticks_and_reports_the_time():
    sim, _, act = factory()
    assert act.wait(90) == {"tick": 90, "time": "2026-01-05T07:30:00"}
    assert act.wait(1)["tick"] == 91 == sim.clock.tick


def test_waiting_is_the_same_as_the_factory_running_by_itself():
    waited, _, act = factory()
    act.wait(200)
    stepped, _, _ = factory()
    for _ in range(200):
        stepped.step()
    assert waited.readings == stepped.readings
    assert waited.event_log.events == stepped.event_log.events


def test_every_waited_tick_leaves_its_readings_behind():
    _, look, act = factory()
    act.wait(60)
    assert [r["tick"] for r in look.get_readings("CNC-01", "vibration", 0, 60)] == list(range(1, 61))


@pytest.mark.parametrize("ticks", (0, -5, 481, 2.5, "10", True))
def test_bad_waits_are_refused_and_nothing_moves(ticks):
    sim, _, act = factory()
    with pytest.raises(ValueError):
        act.wait(ticks)
    assert sim.clock.tick == 0


def test_the_limit_per_wait_can_be_set():
    sim = build_line(42, machines=3)
    act = ActionTools(sim, max_wait=30)
    act.wait(30)
    with pytest.raises(ValueError):
        act.wait(31)


def test_looking_is_free_however_often_the_agent_looks():
    _, glance, act_a = factory()
    for _ in range(5):
        look_around(glance)
    act_a.wait(60)

    _, stare, act_b = factory()
    for _ in range(50):
        look_around(stare)
    act_b.wait(60)

    assert glance.get_time() == stare.get_time() == {"tick": 60, "time": "2026-01-05T07:00:00"}
    assert glance.get_events(0, 60) == stare.get_events(0, 60)
    assert glance.get_readings("CNC-02", "temperature", 0, 60) == stare.get_readings("CNC-02", "temperature", 0, 60)


def test_the_factory_does_not_wait_for_the_agent_a_fault_keeps_developing():
    _, look, act = factory(fault=True)
    act.wait(100)
    assert not [e for e in look.get_events(0, 100) if e["kind"] == "status"]
    act.wait(400)
    stops = [e for e in look.get_events(0, 500) if e["kind"] == "status"]
    assert [e["machine_id"] for e in stops] == ["CNC-02"]
    assert look.get_time()["tick"] == 500  # the wait runs its full length, breakdown or not


def test_the_answer_is_plain_data():
    _, _, act = factory()
    answer = act.wait(10)
    assert json.loads(json.dumps(answer)) == answer
