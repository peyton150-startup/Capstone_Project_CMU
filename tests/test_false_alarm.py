import json

import pytest

from capstone.simulator.line import build_line
from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import FalseAlarm
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import FactoryState, MachineState
from capstone.tools.observation import ObservationTools

START, LENGTH = 300, 5


def factory(fault: bool = True, ticks: int = 800) -> tuple[Simulator, ObservationTools]:
    sim = build_line(42, machines=3)
    if fault:
        sim.add_scenario(FalseAlarm("glitch", sim.rng, machine_id="CNC-02", start_tick=START, duration=LENGTH))
    for _ in range(ticks):
        sim.step()
    return sim, ObservationTools(sim)


def alarms(tools: ObservationTools) -> list[dict]:
    return [e for e in tools.get_events(0, 10_000) if e["kind"] == "alarm"]


def test_the_scenario_writes_only_the_sensor_offset_and_takes_it_away_again():
    state = FactoryState()
    state.add(MachineState(id="CNC-02"))
    fault = FalseAlarm("glitch", RandomSource(1), machine_id="CNC-02", start_tick=10, duration=3, offset=5.0)
    before = state.model_dump()
    fault.apply(state, 9)
    assert state.model_dump() == before
    offsets = []
    for tick in range(10, 15):
        fault.apply(state, tick)
        offsets.append(state.machines["CNC-02"].condition.vibration_sensor_offset)
        dump = state.model_dump()
        dump["machines"]["CNC-02"]["condition"]["vibration_sensor_offset"] = 0.0
        assert dump == before
    assert offsets == [5.0, 5.0, 5.0, 0.0, 0.0]


def test_the_spike_trips_the_vibration_alarm_on_that_machine_only_while_it_lasts():
    _, look = factory()
    _, clean = factory(fault=False)
    extra = [a for a in alarms(look) if a not in alarms(clean)]
    assert extra and {a["machine_id"] for a in extra} == {"CNC-02"}
    assert {a["tick"] for a in extra} == set(range(START, START + LENGTH))


def test_only_the_vibration_readings_in_the_window_differ_from_the_same_day_without_it():
    sim, _ = factory()
    twin, _ = factory(fault=False)
    differ = [(a.machine_id, a.sensor, a.tick) for a, b in zip(sim.readings, twin.readings) if a != b]
    assert differ == [("CNC-02", "vibration", t) for t in range(START, START + LENGTH)]
    assert sim.state.model_dump() == twin.state.model_dump()  # the machine itself never changed
    assert sim.event_log.events[-1] == twin.event_log.events[-1]


def test_the_ground_truth_names_a_false_alarm_and_the_tool_view_does_not():
    sim, look = factory()
    (truth,) = sim.ground_truth()
    assert (truth.fault, truth.machine_id, truth.start_tick) == ("false_alarm", "CNC-02", START)
    seen = json.dumps([look.list_machines(), look.get_settings(), look.get_events(0, 800)])
    assert "offset" not in seen and "false_alarm" not in seen


@pytest.mark.parametrize("kwargs", [{"duration": 0}, {"offset": 0.0}])
def test_bad_settings_are_refused(kwargs):
    with pytest.raises(ValueError):
        FalseAlarm("glitch", RandomSource(1), machine_id="CNC-02", start_tick=1, **kwargs)
