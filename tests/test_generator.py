from collections import Counter

import pytest

from capstone.simulator.generator import (
    BEARING_PROFILES,
    FAULTS,
    THREE_DAY_ONSET_HEALTH,
    build_scenario,
)


def run(seed: int, ticks: int = 300, **kwargs):
    sim = build_scenario(seed, **kwargs)
    for _ in range(ticks):
        sim.step()
    return sim


def test_one_fault_per_scenario_and_the_clock_not_yet_started():
    sim = build_scenario(7)
    assert sim.clock.tick == 0
    (truth,) = sim.ground_truth()
    assert truth.fault in FAULTS


def test_the_same_seed_gives_the_same_fault_and_the_same_day():
    a, b = run(11), run(11)
    assert a.ground_truth() == b.ground_truth()
    assert a.readings == b.readings and a.event_log.events == b.event_log.events


def test_every_fault_appears_across_seeds_and_names_what_it_is_about():
    seen = Counter()
    for seed in range(60):
        (truth,) = build_scenario(seed).ground_truth()
        seen[truth.fault] += 1
        if truth.fault == "bad_material_batch":
            assert truth.batch_id in (2, 3) and truth.machine_id is None
        else:
            sim = build_scenario(seed)
            assert (
                truth.machine_id in sim.state.machines
                and 200 <= truth.start_tick <= 600
            )
    assert set(seen) == set(FAULTS)


@pytest.mark.parametrize("fault", FAULTS)
def test_a_fault_can_be_forced_and_the_rest_still_comes_from_the_seed(fault):
    (truth,) = build_scenario(3, fault=fault).ground_truth()
    assert truth.fault == fault
    assert build_scenario(3, fault=fault).ground_truth() == (truth,)


def test_choosing_the_fault_shifts_no_other_stream():
    """The line's own life is the same whichever fault the seed picked, until the fault starts."""
    a = run(5, ticks=150, fault="false_alarm")
    b = run(5, ticks=150, fault="wrong_setting")
    assert a.readings == b.readings


def test_an_unknown_fault_is_refused():
    with pytest.raises(ValueError, match="unknown fault"):
        build_scenario(1, fault="gremlins")


def test_an_unknown_bearing_profile_is_refused():
    with pytest.raises(ValueError, match="unknown bearing profile"):
        build_scenario(1, bearing_profile="instant")


def test_the_compressed_profile_is_the_default():
    a = run(4, ticks=900, fault="bearing_degradation")
    b = run(4, ticks=900, fault="bearing_degradation", bearing_profile="compressed")
    assert a.readings == b.readings and a.ground_truth() == b.ground_truth()


@pytest.mark.parametrize("profile", BEARING_PROFILES)
def test_the_bearing_profile_moves_no_stream(profile):
    """Same fault, machine and start; the factory's life is the same until the fault starts."""
    plain = run(9, ticks=150, fault="bearing_degradation")
    other = run(9, ticks=150, fault="bearing_degradation", bearing_profile=profile)
    assert plain.ground_truth() == other.ground_truth()
    assert plain.readings == other.readings


@pytest.mark.parametrize("fault", [f for f in FAULTS if f != "bearing_degradation"])
def test_the_bearing_profile_changes_nothing_for_other_faults(fault):
    a = run(6, ticks=700, fault=fault)
    b = run(6, ticks=700, fault=fault, bearing_profile="three_day")
    assert a.readings == b.readings and a.event_log.events == b.event_log.events


def onset_to_failure(seed: int, profile: str) -> tuple[int, int]:
    """Running ticks from fault start to onset, and from onset to failure."""
    sim = build_scenario(seed, fault="bearing_degradation", bearing_profile=profile)
    (truth,) = sim.ground_truth()
    machine = sim.state.machines[truth.machine_id]
    running, onset = 0, None
    for _ in range(20_000):
        sim.step()
        if sim.clock.tick > truth.start_tick and machine.status.name == "RUNNING":
            running += 1
        health = machine.condition.bearing_health
        if onset is None and health <= THREE_DAY_ONSET_HEALTH:
            onset = running
        if health <= 0.1:
            return onset, running - onset
    raise AssertionError("the bearing never failed")


def test_three_day_ramp_is_quiet_first_then_takes_days():
    """One seed, checked against the spread measured on seeds 1-40.

    The calibration itself (median 4,294 running ticks from onset to failure,
    target 4,320) is in docs/benchmarks/2026-10-26-bearing-three-day.md; a
    40-seed run is too slow for every test run.
    """
    quiet, ramp = onset_to_failure(1, "three_day")
    _, fast_ramp = onset_to_failure(1, "compressed")
    assert quiet > 1_000  # a quiet stretch before onset
    assert 2_600 <= ramp <= 6_300  # inside the 40-seed range (2,683-6,241)
    assert fast_ramp < ramp / 3
