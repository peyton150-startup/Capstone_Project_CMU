import json
from datetime import datetime

import pytest

from capstone.simulator.line import STANDARD_SPEEDS, build_line
from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import (
    BearingDegradation,
    ProductionLine,
    WrongSetting,
    defect_mark,
    working_speed,
)
from capstone.simulator.sensors import TemperatureSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import FactoryState, MachineState
from capstone.simulator.thermal import settling_temperature
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
LINE = ["CNC-01", "CNC-02", "CNC-03"]
TIMES = (60, 70, 55)
FAULT_TICK = 2000


def factory(
    factor: float | None = 1.15, ticks: int = 6000, seed: int = 42
) -> tuple[Simulator, ObservationTools]:
    """The 60/70/55 line with exact job times; CNC-02 is set wrong at tick 2000 unless factor is None."""
    sim = Simulator(seed, START)
    for machine_id, per_job in zip(LINE, TIMES):
        sim.add_machine(MachineState(id=machine_id, ticks_per_job=per_job))
        sim.add_sensor(VibrationSensor(machine_id, sim.rng))
        sim.add_sensor(TemperatureSensor(machine_id, sim.rng))
    sim.add_scenario(
        ProductionLine("line", sim.rng, machine_ids=LINE, jobs_per_batch=25)
    )
    if factor is not None:
        sim.add_scenario(
            WrongSetting(
                "setting",
                sim.rng,
                machine_id="CNC-02",
                start_tick=FAULT_TICK,
                factor=factor,
            )
        )
    for _ in range(ticks):
        sim.step()
    return sim, ObservationTools(sim)


def working_times(
    tools: ObservationTools, machine_id: str, from_tick: int, to_tick: int
) -> list[int]:
    """How long each job took on a machine, for jobs both started and finished in the range."""
    started: dict[int, int] = {}
    taken = []
    for row in tools.get_events(from_tick, to_tick, machine_id):
        if row["message"].endswith("started"):
            started[row["job_id"]] = row["tick"]
        elif row["message"].endswith("finished") and row["job_id"] in started:
            taken.append(row["tick"] - started[row["job_id"]] + 1)
    return taken


def average(
    tools: ObservationTools, sensor: str, from_tick: int, to_tick: int
) -> float:
    running = [
        r["value"]
        for r in tools.get_readings("CNC-02", sensor, from_tick, to_tick)
        if r["value"] > 1.0
    ]
    return sum(running) / len(running)


def failure_rate(sim: Simulator, from_tick: int, to_tick: int) -> float:
    results = [r for r in sim.state.inspections if from_tick <= r.tick <= to_tick]
    return sum(1 for r in results if not r.passed) / len(results)


def test_a_machine_runs_at_its_standard_speed_unless_set_otherwise():
    machine = MachineState(id="X", standard_speed=850.0)
    assert (machine.speed, machine.speed_ratio) == (850.0, 1.0)
    assert working_speed(machine) == 1.0 and defect_mark(machine) == 0.0
    machine.speed_setting = 977.5
    assert machine.speed_ratio == pytest.approx(1.15)


def test_the_scenario_writes_the_setting_once_at_its_start_tick_and_nothing_else():
    state = FactoryState()
    state.add(MachineState(id="CNC-02", standard_speed=850.0))
    untouched = state.machines["CNC-02"].model_dump(exclude={"speed_setting"})
    fault = WrongSetting(
        "setting", RandomSource(42), machine_id="CNC-02", start_tick=10, factor=1.15
    )
    fault.apply(state, 9)
    assert state.machines["CNC-02"].speed_setting is None
    fault.apply(state, 10)
    assert state.machines["CNC-02"].speed_setting == pytest.approx(977.5)
    assert state.machines["CNC-02"].model_dump(exclude={"speed_setting"}) == untouched


def test_a_setting_put_right_afterwards_stays_right():
    state = FactoryState()
    state.add(MachineState(id="CNC-02"))
    fault = WrongSetting(
        "setting", RandomSource(42), machine_id="CNC-02", start_tick=10, factor=1.15
    )
    fault.apply(state, 10)
    state.machines["CNC-02"].speed_setting = None
    fault.apply(state, 11)
    assert state.machines["CNC-02"].speed_ratio == 1.0


def test_set_too_fast_the_machine_finishes_jobs_sooner_in_one_step():
    _, tools = factory()
    assert set(working_times(tools, "CNC-02", 200, FAULT_TICK - 1)) == {70}
    assert set(working_times(tools, "CNC-02", FAULT_TICK + 100, 6000)) == {61}


def test_set_too_slow_the_machine_takes_longer():
    _, tools = factory(factor=0.88)
    assert set(working_times(tools, "CNC-02", FAULT_TICK + 100, 6000)) == {80}


def test_the_other_machines_keep_their_own_working_times():
    _, tools = factory()
    assert set(working_times(tools, "CNC-01", FAULT_TICK + 100, 6000)) == {60}
    assert set(working_times(tools, "CNC-03", FAULT_TICK + 100, 6000)) == {55}


def test_vibration_steps_up_a_little_and_then_stays_level():
    _, tools = factory()
    before = average(tools, "vibration", 500, FAULT_TICK - 1)
    soon_after = average(tools, "vibration", FAULT_TICK + 100, 4000)
    much_later = average(tools, "vibration", 4001, 6000)
    assert soon_after - before == pytest.approx(0.30, abs=0.1)
    assert much_later == pytest.approx(soon_after, abs=0.1)  # a step, not a climb


def test_a_machine_set_fifteen_percent_fast_settles_six_degrees_warmer():
    right, fast = MachineState(id="X"), MachineState(id="X", speed_setting=1150.0)
    assert settling_temperature(fast, 72.0) - settling_temperature(
        right, 72.0
    ) == pytest.approx(6.0)


def test_set_too_slow_vibration_goes_down_not_up():
    _, tools = factory(factor=0.88)
    assert average(tools, "vibration", FAULT_TICK + 100, 6000) < average(
        tools, "vibration", 500, FAULT_TICK - 1
    )


def test_the_vibration_alarm_never_fires_and_the_machine_never_breaks_down():
    sim, _ = factory()
    assert {e.kind for e in sim.event_log.events} <= {"job", "inspection", "batch"}
    assert sim.state.machines["CNC-02"].condition.bearing_health == 1.0


def test_each_job_the_machine_finishes_picks_up_the_same_extra_risk():
    assert defect_mark(MachineState(id="X", speed_setting=1150.0)) == pytest.approx(
        0.18
    )
    assert defect_mark(MachineState(id="X", speed_setting=880.0)) == pytest.approx(
        8.0 * 0.12**2
    )
    sim, _ = factory(ticks=2600)
    assert sim.state.machines["CNC-03"].job.defect_risk == pytest.approx(0.18)


def test_rejects_rise_after_the_change_and_carry_on_across_batches():
    sim, _ = factory(ticks=9000)
    assert failure_rate(sim, 0, FAULT_TICK) <= 0.06
    assert failure_rate(sim, FAULT_TICK + 200, 9000) >= 0.10
    failed_batches = {
        r.batch_id
        for r in sim.state.inspections
        if not r.passed and r.tick > FAULT_TICK + 200
    }
    assert len(failed_batches) >= 3


def test_more_parts_but_fewer_good_ones():
    wrong, _ = factory(ticks=9000)
    right, _ = factory(factor=None, ticks=9000)
    assert len(wrong.state.completed_jobs) > len(right.state.completed_jobs)
    assert sum(r.passed for r in wrong.state.inspections) < sum(
        r.passed for r in right.state.inspections
    )


def test_a_wrong_setting_alone_wears_nothing_but_speeds_up_wear_that_is_under_way():
    def health_after(speed_setting):
        state = FactoryState()
        state.add(MachineState(id="CNC-02", speed_setting=speed_setting))
        wear = BearingDegradation(
            "bearing",
            RandomSource(42),
            machine_id="CNC-02",
            start_tick=1,
            rate=0.001,
            variation=0.0,
        )
        for tick in range(1, 101):
            wear.apply(state, tick)
        return state.machines["CNC-02"].condition.bearing_health

    assert 1.0 - health_after(None) == pytest.approx(0.1)
    assert 1.0 - health_after(1150.0) == pytest.approx(0.1 * 1.15**3)


def test_the_agent_can_read_each_machines_speed_but_not_what_it_should_be():
    sim = build_line(42, machines=3)
    sim.add_scenario(
        WrongSetting("setting", sim.rng, machine_id="CNC-02", start_tick=5, factor=1.15)
    )
    tools = ObservationTools(sim)
    assert tools.get_settings() == [
        {"machine_id": name, "speed_rpm": speed}
        for name, speed in zip(LINE, STANDARD_SPEEDS)
    ]
    for _ in range(10):
        sim.step()
    settings = tools.get_settings()
    assert settings[1] == {"machine_id": "CNC-02", "speed_rpm": pytest.approx(977.5)}
    seen = json.dumps([settings, tools.list_machines(), tools.get_events(0, 10)])
    assert "standard" not in seen and "ratio" not in seen and "850" not in seen
    assert not [
        e
        for e in sim.event_log.events
        if "setting" in e.message or "speed" in e.message
    ]


def test_the_ground_truth_names_the_machine_and_the_tick():
    sim, _ = factory(ticks=1)
    (truth,) = sim.ground_truth()
    assert (truth.fault, truth.machine_id, truth.start_tick) == (
        "wrong_setting",
        "CNC-02",
        FAULT_TICK,
    )


def test_a_factor_of_one_or_less_than_nothing_is_refused():
    for bad in (1.0, 0.0, -0.5):
        with pytest.raises(ValueError):
            WrongSetting(
                "s", RandomSource(1), machine_id="CNC-02", start_tick=1, factor=bad
            )


def test_same_seed_gives_the_same_results_and_another_seed_different_ones():
    def results(seed):
        return [r.passed for r in factory(seed=seed)[0].state.inspections]

    assert results(42) == results(42)
    assert results(42) != results(43)
