from collections import Counter

import pytest

from capstone.simulator.generator import FAULTS, build_scenario


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
            assert truth.machine_id in sim.state.machines and 200 <= truth.start_tick <= 600
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
