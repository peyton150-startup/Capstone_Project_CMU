import json
from datetime import datetime

import pytest

from capstone.simulator.events import ThresholdAlarm
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.sensors import VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
TOOLS = {"get_time", "list_machines", "get_readings", "get_factory_readings", "get_events", "get_job_history"}
HIDDEN_WORDS = ("bearing", "health", "condition", "degradation", "fault", "scenario", "start_tick", "ground")


def factory(ticks: int) -> tuple[Simulator, ObservationTools]:
    sim = Simulator(42, START)
    for machine_id in ("CNC-01", "CNC-04"):
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(VibrationSensor(machine_id, sim.rng))
    sim.add_alarm(ThresholdAlarm("vibration", 4.5))
    sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-04", start_tick=100, rate=0.001))
    for _ in range(ticks):
        sim.step()
    return sim, ObservationTools(sim)


def everything(tools: ObservationTools, last_tick: int) -> list:
    return [
        tools.get_time(),
        tools.list_machines(),
        tools.get_events(0, last_tick),
        *[tools.get_readings(m["machine_id"], "vibration", 0, last_tick) for m in tools.list_machines()],
    ]


def test_the_tools_are_exactly_the_six_we_decided_on():
    assert {name for name in dir(ObservationTools) if not name.startswith("_")} == TOOLS


def test_get_time_reports_tick_and_clock_time():
    _, tools = factory(90)
    assert tools.get_time() == {"tick": 90, "time": "2026-01-05T07:30:00"}


def test_list_machines_shows_id_status_and_current_job_only():
    _, tools = factory(1200)
    assert tools.list_machines() == [
        {"machine_id": "CNC-01", "status": "running", "job_id": None},
        {"machine_id": "CNC-04", "status": "down", "job_id": None},
    ]


def test_get_readings_returns_one_machine_one_sensor_in_the_tick_range():
    sim, tools = factory(50)
    got = tools.get_readings("CNC-04", "vibration", 10, 12)
    assert [r["tick"] for r in got] == [10, 11, 12]
    assert {r["machine_id"] for r in got} == {"CNC-04"}
    assert got[0]["value"] == next(r.value for r in sim.readings if r.machine_id == "CNC-04" and r.tick == 10)


def test_get_events_can_be_narrowed_to_one_machine():
    _, tools = factory(1200)
    assert {e["machine_id"] for e in tools.get_events(0, 1200)} == {"CNC-04"}
    assert tools.get_events(0, 1200, "CNC-01") == []
    assert tools.get_events(0, 1200, "CNC-04")[-1]["message"] == "machine stopped"


def test_bad_requests_are_refused():
    _, tools = factory(10)
    with pytest.raises(ValueError):
        tools.get_readings("CNC-99", "vibration", 0, 10)
    with pytest.raises(ValueError):
        tools.get_events(10, 5)


def test_looking_does_not_advance_time_or_change_the_factory():
    sim, tools = factory(300)
    before = (sim.clock.tick, sim.state.model_copy(deep=True), sim.readings, sim.event_log.events)
    everything(tools, 300)
    assert (sim.clock.tick, sim.state, sim.readings, sim.event_log.events) == before


def test_editing_an_answer_does_not_edit_the_factory():
    sim, tools = factory(50)
    tools.list_machines()[1]["status"] = "down"
    tools.get_readings("CNC-04", "vibration", 1, 50)[0]["value"] = 99.0
    assert tools.list_machines()[1]["status"] == "running"
    assert sim.readings[1].value != 99.0


def test_answers_are_plain_data():
    _, tools = factory(1200)
    assert json.loads(json.dumps(everything(tools, 1200))) == everything(tools, 1200)


def test_nothing_hidden_leaks_through_any_tool_over_a_full_run():
    sim, tools = factory(1200)
    text = json.dumps(everything(tools, 1200)).lower()
    assert not [word for word in HIDDEN_WORDS if word in text]
    keys = {key for answer in everything(tools, 1200) for row in (answer if isinstance(answer, list) else [answer]) for key in row}
    assert keys == {"tick", "time", "machine_id", "status", "job_id", "sensor", "value", "unit", "kind", "message"}
    assert sim.ground_truth()  # the truth exists; it just is not reachable from here
