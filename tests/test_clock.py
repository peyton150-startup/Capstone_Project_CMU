from datetime import datetime, timedelta

import pytest

from capstone.simulator.clock import SimulationClock

START = datetime(2026, 1, 5, 6, 0)


def test_starts_at_tick_zero_and_start_time():
    clock = SimulationClock(start=START)
    assert clock.tick == 0
    assert clock.now == START


def test_advance_one_tick_moves_now_by_tick_duration():
    clock = SimulationClock(start=START, tick_duration=timedelta(minutes=1))
    clock.advance()
    assert clock.tick == 1
    assert clock.now == START + timedelta(minutes=1)


def test_advance_many_ticks():
    clock = SimulationClock(start=START, tick_duration=timedelta(seconds=30))
    returned = clock.advance(10)
    assert returned == 10
    assert clock.tick == 10
    assert clock.now == START + timedelta(minutes=5)


def test_time_at_maps_any_tick_without_moving_the_clock():
    clock = SimulationClock(start=START)
    assert clock.time_at(90) == START + timedelta(minutes=90)
    assert clock.tick == 0


def test_time_never_moves_backward_or_stands_still():
    clock = SimulationClock(start=START)
    with pytest.raises(ValueError):
        clock.advance(0)
    with pytest.raises(ValueError):
        clock.advance(-5)
    assert clock.tick == 0


def test_negative_tick_has_no_time():
    clock = SimulationClock(start=START)
    with pytest.raises(ValueError):
        clock.time_at(-1)


def test_tick_duration_must_be_positive():
    with pytest.raises(ValueError):
        SimulationClock(start=START, tick_duration=timedelta(0))


def test_two_clocks_with_same_config_and_same_advances_agree():
    a = SimulationClock(start=START)
    b = SimulationClock(start=START)
    for _ in range(250):
        a.advance()
        b.advance()
    assert a.tick == b.tick
    assert a.now == b.now
