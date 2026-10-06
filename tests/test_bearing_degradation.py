from datetime import datetime
from statistics import mean

import pytest

from capstone.simulator.events import ThresholdAlarm
from capstone.simulator.scenarios import BearingDegradation
from capstone.simulator.sensors import VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState, MachineStatus

START = datetime(2026, 1, 5, 6, 0)


def factory(seed: int = 42, *, start_tick: int = 100, rate: float = 0.001, variation: float = 0.5) -> Simulator:
    sim = Simulator(seed, START)
    for machine_id in ("CNC-01", "CNC-04"):
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(VibrationSensor(machine_id, sim.rng))
    sim.add_alarm(ThresholdAlarm("vibration", 4.5))
    sim.add_scenario(
        BearingDegradation(
            "bearing", sim.rng, machine_id="CNC-04", start_tick=start_tick, rate=rate, variation=variation
        )
    )
    return sim


def run(sim: Simulator, ticks: int) -> Simulator:
    for _ in range(ticks):
        sim.step()
    return sim


def health(sim: Simulator, machine_id: str = "CNC-04") -> float:
    return sim.state.machines[machine_id].condition.bearing_health


def vibration(sim: Simulator, first: int, last: int, machine_id: str = "CNC-04") -> float:
    return mean(r.value for r in sim.readings if r.machine_id == machine_id and first <= r.tick <= last)


def test_rejects_nonsense_settings():
    sim = Simulator(42, START)
    with pytest.raises(ValueError):
        BearingDegradation("a", sim.rng, machine_id="CNC-04", start_tick=1, rate=0.0)
    with pytest.raises(ValueError):
        BearingDegradation("b", sim.rng, machine_id="CNC-04", start_tick=1, rate=0.001, variation=1.0)


def test_nothing_happens_before_the_start_tick():
    assert health(run(factory(), 99)) == 1.0


def test_wear_begins_at_the_start_tick():
    assert health(run(factory(), 100)) < 1.0


def test_health_only_ever_falls_while_running():
    sim, seen = factory(), []
    for _ in range(400):
        sim.step()
        seen.append(health(sim))
    assert all(later <= earlier for earlier, later in zip(seen, seen[1:]))


def test_without_variation_the_loss_is_exactly_the_rate():
    assert health(run(factory(variation=0.0), 299)) == pytest.approx(1.0 - 200 * 0.001)


def test_with_variation_the_average_loss_is_still_the_rate():
    assert health(run(factory(), 499)) == pytest.approx(0.6, abs=0.03)


def test_a_machine_that_is_not_running_does_not_wear():
    sim = run(factory(), 200)
    before = health(sim)
    sim.state.machines["CNC-04"].status = MachineStatus.IDLE
    run(sim, 50)
    assert health(sim) == before


def test_only_the_target_machine_is_affected():
    assert health(run(factory(), 500), "CNC-01") == 1.0


def test_health_never_goes_below_zero():
    assert health(run(factory(rate=0.01), 400)) == 0.0


def test_vibration_rises_slowly_then_quickly():
    sim = run(factory(), 800)
    healthy, middle, late = vibration(sim, 50, 99), vibration(sim, 400, 449), vibration(sim, 750, 799)
    assert healthy < middle < late
    assert (late - middle) > (middle - healthy)


def test_the_healthy_machine_stays_flat():
    sim = run(factory(), 800)
    assert vibration(sim, 750, 799, "CNC-01") == pytest.approx(2.0, abs=0.1)


def test_the_alarm_arrives_long_after_the_fault_began():
    sim = run(factory(), 900)
    alarms = [e for e in sim.event_log.events if e.machine_id == "CNC-04"]
    assert alarms and alarms[0].tick > 100 + 400
    assert not [e for e in sim.event_log.events if e.machine_id == "CNC-01"]


def test_same_seed_gives_the_identical_factory():
    def history(seed):
        sim = run(factory(seed), 600)
        return sim.readings, sim.event_log.events, health(sim)

    assert history(42) == history(42)


def test_different_seeds_differ_in_detail_but_tell_the_same_story():
    a, b = run(factory(42), 600), run(factory(43), 600)
    assert health(a) != health(b)
    assert health(a) == pytest.approx(health(b), abs=0.05)
    assert vibration(a, 550, 599) > vibration(a, 50, 99)
    assert vibration(b, 550, 599) > vibration(b, 50, 99)
