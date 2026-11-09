"""SM-5: time-aware statistics for unevenly timed readings, never across a gap.

Synthetic records only; no test touches the network or a machine.
"""

from datetime import UTC, datetime, timedelta

import pytest

from capstone.ingestion.record import CollectorMarker, GapDetail, TelemetryRecord
from capstone.ingestion.time_stats import (
    channel_holds,
    peak_excursion,
    seconds_above,
    slope_per_second,
    summarize,
    time_weighted_mean,
)

T0 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


def obs(second: float, value: str | None, item: str = "S1load"):
    at = T0 + timedelta(seconds=second)
    return TelemetryRecord(
        source="http://agent:8082",
        instance_id="1",
        device="VF2",
        component="Rotary",
        data_item_id=item,
        category="SAMPLE",
        type="Load",
        value=value,
        available=value is not None,
        sequence=int(second * 10) + 1,
        source_timestamp=at,
        received_at=at,
    )


def gap(second: float):
    return CollectorMarker(
        source="http://agent:8082",
        event="gap",
        at=T0 + timedelta(seconds=second),
        gap=GapDetail(cause="buffer_overrun"),
    )


def holds(lines):
    return channel_holds(lines, "VF2", "S1load")


def test_the_mean_is_weighted_by_how_long_each_value_held():
    # The MVP_SCOPE example: 10% for 90 s, then 90% for 10 s.
    lines = [obs(0, "10"), obs(90, "90"), obs(100, "1200", item="S1speed")]
    runs = holds(lines)
    assert [(h.value, h.seconds) for h in runs[0]] == [(10, 90), (90, 10)]
    assert time_weighted_mean(runs) == pytest.approx(18)
    assert (10 + 90) / 2 == 50  # what a plain average of the readings would say


def test_the_last_value_holds_only_until_the_last_collected_reading():
    lines = [obs(0, "10"), obs(30, "1", item="S1speed")]
    (run,) = holds(lines)
    assert [(h.value, h.seconds) for h in run] == [(10, 30)]


def test_no_value_is_carried_across_a_gap():
    lines = [
        obs(0, "10"),
        obs(60, "1", item="S1speed"),
        gap(600),
        obs(600, "90"),
        obs(620, "1", item="S1speed"),
    ]
    runs = holds(lines)
    assert [[(h.value, h.seconds) for h in run] for run in runs] == [
        [(10, 60)],
        [(90, 20)],
    ]
    # Weighted by 60 s and 20 s held, not by the 600 s the gap lasted.
    assert time_weighted_mean(runs) == pytest.approx((10 * 60 + 90 * 20) / 80)


def test_unavailable_cuts_the_previous_value_off_and_is_never_filled():
    lines = [obs(0, "10"), obs(20, None), obs(50, "30"), obs(60, "1", item="S1speed")]
    (run,) = holds(lines)
    assert [(h.value, h.seconds) for h in run] == [(10, 20), (30, 10)]


def test_event_words_are_not_numbers():
    lines = [obs(0, "ACTIVE"), obs(10, "5"), obs(20, "1", item="S1speed")]
    (run,) = holds(lines)
    assert [(h.value, h.seconds) for h in run] == [(5, 10)]


def test_time_above_a_level_and_the_peak_excursion():
    lines = [obs(0, "40"), obs(30, "95"), obs(35, "50"), obs(95, "1", item="S1speed")]
    runs = holds(lines)
    assert seconds_above(runs, 90) == 5
    peak = peak_excursion(runs, reference=45)
    assert (peak.value, peak.distance, peak.held_seconds) == (95, 50, 5)
    assert peak.at == T0 + timedelta(seconds=30)
    assert peak_excursion([], reference=0) is None


def test_the_slope_uses_real_times_not_reading_order():
    # Uneven spacing: a reading-index slope would be 1 per reading.
    lines = [obs(0, "10"), obs(1, "11"), obs(10, "12"), obs(20, "1", item="S1speed")]
    slope = slope_per_second(holds(lines))
    assert slope == pytest.approx(15 / 91)  # least squares on t = 0, 1, 10 s
    assert slope != pytest.approx(1.0)


def test_a_step_between_two_runs_is_not_a_trend():
    flat_low = [obs(0, "10"), obs(10, "10"), obs(20, "10")]
    flat_high = [obs(600, "90"), obs(610, "90"), obs(620, "90")]
    lines = [*flat_low, obs(30, "1", item="S1speed"), gap(600), *flat_high]
    lines.append(obs(630, "1", item="S1speed"))
    assert slope_per_second(holds(lines)) == 0


def test_too_few_readings_give_no_slope_or_mean():
    assert slope_per_second(holds([obs(0, "10"), obs(5, "1", item="S1speed")])) is None
    assert time_weighted_mean([]) is None


def test_the_summary_brings_it_together():
    lines = [obs(0, "10"), obs(90, "90"), obs(100, "1", item="S1speed")]
    stats = summarize(lines, "VF2", "S1load", level=50)
    assert (stats.runs, stats.readings, stats.seconds_covered) == (1, 2, 100)
    assert stats.time_weighted_mean == pytest.approx(18)
    assert (stats.minimum, stats.maximum, stats.seconds_above) == (10, 90, 10)
    empty = summarize(lines, "VF2", "Xload")
    assert (empty.runs, empty.time_weighted_mean, empty.seconds_above) == (
        0,
        None,
        None,
    )
