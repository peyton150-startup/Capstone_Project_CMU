from datetime import datetime

import pytest

from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation, ProductionLine
from capstone.simulator.sensors import VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState, MachineStatus

START = datetime(2026, 1, 5, 6, 0)
LINE = ["CNC-01", "CNC-02", "CNC-03"]
TIMES = (60, 70, 55)


def factory(rate: float | None = 0.0008, fault_start: int = 1) -> Simulator:
    """The three-machine line, exact times, with a wear fault on CNC-02 unless rate is None."""
    sim = Simulator(42, START)
    for machine_id, per_job in zip(LINE, TIMES):
        sim.add_machine(MachineState(id=machine_id, ticks_per_job=per_job))
    sim.add_sensor(VibrationSensor("CNC-02", sim.rng, noise_sd=0.0))
    sim.add_scenario(ProductionLine("line", sim.rng, machine_ids=LINE))
    if rate is not None:
        sim.add_scenario(
            BearingDegradation(
                "bearing",
                sim.rng,
                machine_id="CNC-02",
                start_tick=fault_start,
                rate=rate,
                variation=0.0,
            )
        )
    return sim


def run(sim: Simulator, ticks: int) -> Simulator:
    for _ in range(ticks):
        sim.step()
    return sim


def cnc02(sim: Simulator) -> MachineState:
    return sim.state.machines["CNC-02"]


def maintenance(sim: Simulator) -> list[tuple[int, str, str]]:
    return [
        (e.tick, e.machine_id, e.message)
        for e in sim.event_log.events
        if e.kind == "maintenance"
    ]


def test_an_unknown_machine_is_refused():
    with pytest.raises(ValueError):
        factory().start_bearing_replacement("CNC-99")


def test_a_machine_already_under_repair_is_refused():
    sim = run(factory(), 100)
    sim.start_bearing_replacement("CNC-02")
    with pytest.raises(ValueError):
        sim.start_bearing_replacement("CNC-02")


def test_a_planned_replacement_takes_the_machine_down_for_exactly_45_ticks():
    sim = run(factory(), 400)
    assert sim.start_bearing_replacement("CNC-02") == 445
    assert cnc02(sim).status is MachineStatus.DOWN
    run(sim, 44)
    assert cnc02(sim).status is MachineStatus.DOWN
    run(sim, 1)
    assert cnc02(sim).status is not MachineStatus.DOWN
    started, finished = maintenance(sim)
    assert started == (400, "CNC-02", "bearing replacement started")
    assert finished[:2] == (445, "CNC-02") and finished[2].startswith(
        "bearing replacement finished: old bearing "
    )


@pytest.mark.parametrize(
    "rate, repair_at, finding",
    [
        (None, 300, "in good condition"),  # nothing was wrong with it
        (0.0008, 300, "worn"),
        (0.0008, 700, "badly worn"),
        (0.004, 600, "had failed"),
    ],
)
def test_the_technician_reports_the_state_of_the_bearing_that_came_out(
    rate, repair_at, finding
):
    sim = run(factory(rate=rate), repair_at)
    health = cnc02(sim).condition.bearing_health
    done = sim.start_bearing_replacement("CNC-02")
    assert not [
        m for m in maintenance(sim) if "old bearing" in m[2]
    ]  # nothing is known until it is out
    run(sim, done - repair_at)
    assert (
        maintenance(sim)[-1][2]
        == f"bearing replacement finished: old bearing {finding}"
    )
    assert (
        f"{health:.2f}" not in maintenance(sim)[-1][2]
    )  # a description, never the number


def test_a_machine_that_already_broke_down_takes_three_times_as_long():
    sim = run(factory(rate=0.004), 600)
    assert (
        cnc02(sim).status is MachineStatus.DOWN and cnc02(sim).maintenance_until is None
    )  # it failed
    assert sim.start_bearing_replacement("CNC-02") == 600 + 135
    run(sim, 134)
    assert cnc02(sim).status is MachineStatus.DOWN
    run(sim, 1)
    assert cnc02(sim).status is not MachineStatus.DOWN


def test_the_new_bearing_is_perfect_and_the_symptoms_go_away():
    sim = run(factory(), 700)
    worn_health = cnc02(sim).condition.bearing_health
    worn_vibration = max(r.value for r in sim.readings if 600 <= r.tick <= 700)
    sim.start_bearing_replacement("CNC-02")
    run(sim, 400)
    assert worn_health < 0.7
    assert cnc02(sim).condition.bearing_health == 1.0
    assert cnc02(sim).bearing_replaced_tick == 745
    after = max(r.value for r in sim.readings if 800 <= r.tick <= 1100)
    assert after < worn_vibration - 0.4
    assert (
        after <= 2.0 + 1.5 * 0.3
    )  # no more than a healthy machine on the heaviest job


def test_the_fault_does_not_come_back_after_the_repair():
    sim = run(factory(), 700)
    sim.start_bearing_replacement("CNC-02")
    run(sim, 1500)
    assert cnc02(sim).condition.bearing_health == 1.0
    assert not [e for e in sim.event_log.events if e.kind == "status"]


def test_a_fault_that_begins_after_the_repair_still_happens():
    sim = run(factory(fault_start=600), 100)
    sim.start_bearing_replacement(
        "CNC-02"
    )  # replaced at tick 145, before the fault starts
    run(sim, 1200)
    assert cnc02(sim).bearing_replaced_tick == 145
    assert cnc02(sim).condition.bearing_health < 1.0


def test_the_machine_keeps_its_job_through_the_repair_and_carries_on():
    sim = run(factory(), 400)
    held, progress = cnc02(sim).job, cnc02(sim).job_progress
    sim.start_bearing_replacement("CNC-02")
    run(sim, 45)
    assert (cnc02(sim).job, cnc02(sim).job_progress) == (held, progress)
    run(sim, 1)
    assert (
        cnc02(sim).status is MachineStatus.RUNNING
        and cnc02(sim).job_progress > progress
    )


def test_the_line_backs_up_during_the_repair_and_flows_again_after():
    sim = run(factory(), 400)
    sim.start_bearing_replacement("CNC-02")
    run(sim, 44)
    assert sim.state.machines["CNC-03"].status is MachineStatus.IDLE
    done_during = len(sim.state.completed_jobs)
    run(sim, 300)
    assert len(sim.state.completed_jobs) > done_during
    assert all(m.status is not MachineStatus.DOWN for m in sim.state.machines.values())


def test_replacing_a_healthy_bearing_costs_production_and_changes_nothing_else():
    untouched = run(factory(rate=None), 1200)
    repaired = run(factory(rate=None), 300)
    repaired.start_bearing_replacement("CNC-02")
    run(repaired, 900)
    assert (
        cnc02(repaired).condition.bearing_health
        == cnc02(untouched).condition.bearing_health
        == 1.0
    )
    assert len(repaired.state.completed_jobs) < len(untouched.state.completed_jobs)
    vibration = [r.value for r in repaired.readings if r.value > 1.0]  # while running
    assert max(v for v in vibration) <= 2.0 + 1.5 * 0.3


def test_the_repair_does_not_rewrite_the_answer_key():
    sim = run(factory(), 700)
    before = sim.ground_truth()
    sim.start_bearing_replacement("CNC-02")
    run(sim, 200)
    assert sim.ground_truth() == before


def test_on_the_standard_line_the_machine_cools_during_the_repair():
    sim = run(build_line(42, machines=3), 500)
    warm = sim.state.machines["CNC-02"].temperature
    sim.start_bearing_replacement("CNC-02")
    run(sim, 45)
    assert sim.state.machines["CNC-02"].temperature < warm - 20.0
    assert (
        abs(sim.state.machines["CNC-02"].temperature - sim.state.air_temperature) < 6.0
    )


def test_same_seed_and_same_repair_give_the_same_history():
    def history():
        sim = run(factory(), 700)
        sim.start_bearing_replacement("CNC-02")
        run(sim, 300)
        return sim.readings, sim.event_log.events

    assert history() == history()
