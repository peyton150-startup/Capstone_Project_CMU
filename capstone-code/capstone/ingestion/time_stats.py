# Statistics for unevenly timed machine readings that never span a collection gap.
# Responsibility: turn one channel's recorded readings into time-aware numbers.
"""Time-aware statistics for unevenly sampled data (SM-5 in docs/MVP_SCOPE.md).

Controller data often arrives only when a value changes, so readings are not
evenly spaced. Averaging the readings themselves is then wrong. Spindle load
at 10% for 90 s and then 90% for 10 s averages to 50% over the two readings,
but the machine spent most of the time at 10%: the time-weighted mean is 18%.

So each numeric reading is treated as a **hold**: the value stood from its
own time until the channel's next record. Every statistic here is built from
holds:

- `time_weighted_mean`: each value weighted by how long it held.
- `seconds_above`: how long the value stood above a level.
- `peak_excursion`: the value furthest from a reference, and when it began.
- `slope_per_second`: a least-squares slope on the readings' real times.

Two rules keep the numbers honest:

1. **No hold crosses a break in collection.** Readings are split into the
   runs of `gap_free_runs` (at gap and started markers), and the last value in
   a run holds only until the run's last collected reading, never into the
   gap. A slope over several runs is fitted within each run and pooled, so
   no line is drawn across missing time.
2. **UNAVAILABLE is not a value.** An UNAVAILABLE record ends the previous
   hold and starts none, so a known hole is never filled with the last value.
   A non-numeric value (an event word) is treated the same way.

Times are the machine's own (`source_timestamp`).
"""

from collections.abc import Iterable, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from capstone.ingestion.record import Line, TelemetryRecord, gap_free_runs


class Hold(BaseModel):
    """One value as it stood over a stretch of time."""

    model_config = ConfigDict(frozen=True)

    # Variables:
    #   start: The machine time of the reading.
    #   end: When the next record of the channel arrived, or the run's last
    #     collected reading if there was none; never later than collection.
    #   value: The reading as a number.
    start: datetime
    end: datetime
    value: float

    @property
    def seconds(self) -> float:
        """How long the value held."""
        return (self.end - self.start).total_seconds()


class Excursion(BaseModel):
    """The value furthest from a reference."""

    model_config = ConfigDict(frozen=True)

    # Variables:
    #   value: The reading furthest from the reference.
    #   at: When that reading began to hold.
    #   distance: How far it was from the reference, always positive.
    #   held_seconds: How long it held, so a one-reading spike can be told
    #     apart from a lasting change.
    value: float
    at: datetime
    distance: float
    held_seconds: float


class ChannelStats(BaseModel):
    """One channel's time-aware summary over a capture."""

    model_config = ConfigDict(frozen=True)

    # Variables:
    #   device, data_item_id: The channel.
    #   runs: Collected runs that held at least one of its values.
    #   readings: Numeric readings used; UNAVAILABLE and words are left out.
    #   seconds_covered: Total time its values held, gaps and holes excluded.
    #   time_weighted_mean: See time_weighted_mean; None with nothing held.
    #   minimum, maximum: The lowest and highest value that held.
    #   slope_per_second: See slope_per_second; None with too few readings.
    #   seconds_above: Time above `level`, or None when no level was given.
    device: str
    data_item_id: str
    runs: int
    readings: int
    seconds_covered: float
    time_weighted_mean: float | None
    minimum: float | None
    maximum: float | None
    slope_per_second: float | None
    seconds_above: float | None = None


def holds_in_run(
    run: Sequence[TelemetryRecord], device: str, data_item_id: str
) -> list[Hold]:
    """One channel's holds within one gap-free run, oldest first."""
    # Variables:
    #   run: One run from gap_free_runs: every channel's observations between
    #     two breaks in collection.
    #   run_end: The run's last collected reading of any channel; the last
    #     value holds until then, and no later.
    #   records: This channel's records in the run, in time order.
    #   value: The record as a number; None for UNAVAILABLE or a word, which
    #     then starts no hold.
    #   follower: The record after each one; whatever it says, it ends the
    #     hold, so an UNAVAILABLE record cuts the previous value off.
    if not run:
        return []
    run_end = max(record.source_timestamp for record in run)
    records = sorted(
        (r for r in run if r.device == device and r.data_item_id == data_item_id),
        key=lambda r: (r.source_timestamp, r.sequence),
    )
    holds: list[Hold] = []
    for index, record in enumerate(records):
        value = record.number() if record.available else None
        if value is None:
            continue
        follower = records[index + 1] if index + 1 < len(records) else None
        end = follower.source_timestamp if follower is not None else run_end
        if end > record.source_timestamp:
            holds.append(Hold(start=record.source_timestamp, end=end, value=value))
    return holds


def channel_holds(
    lines: Iterable[Line], device: str, data_item_id: str
) -> list[list[Hold]]:
    """One channel's holds, one list per gap-free run that has any."""
    # Variables:
    #   lines: The capture, observations and markers in file order; the
    #     markers decide where the runs split.
    runs = [holds_in_run(run, device, data_item_id) for run in gap_free_runs(lines)]
    return [run for run in runs if run]


def _flat(runs: Iterable[Sequence[Hold]]) -> list[Hold]:
    return [hold for run in runs for hold in run]


def time_weighted_mean(runs: Iterable[Sequence[Hold]]) -> float | None:
    """The mean value with each reading weighted by how long it held."""
    # Variables:
    #   total: Seconds held across all runs; zero gives None, never 0.
    holds = _flat(runs)
    total = sum(hold.seconds for hold in holds)
    if total == 0:
        return None
    return sum(hold.value * hold.seconds for hold in holds) / total


def seconds_above(runs: Iterable[Sequence[Hold]], level: float) -> float:
    """How long the value stood strictly above `level`."""
    # Variables:
    #   level: The line to measure against, such as a load limit; a value
    #     exactly at it does not count.
    return sum(hold.seconds for hold in _flat(runs) if hold.value > level)


def peak_excursion(
    runs: Iterable[Sequence[Hold]], reference: float
) -> Excursion | None:
    """The held value furthest from `reference`; the longer one wins a tie."""
    # Variables:
    #   reference: What "normal" is taken to be, such as a baseline mean.
    #   peak: The hold furthest from it.
    holds = _flat(runs)
    if not holds:
        return None
    peak = max(holds, key=lambda hold: (abs(hold.value - reference), hold.seconds))
    return Excursion(
        value=peak.value,
        at=peak.start,
        distance=abs(peak.value - reference),
        held_seconds=peak.seconds,
    )


def slope_per_second(runs: Iterable[Sequence[Hold]]) -> float | None:
    """A least-squares slope on the readings' real times, fitted within runs.

    Each run is centred on its own mean time and value, and the runs' sums
    are pooled. A level shift between two runs therefore does not count as
    a trend, and no line is drawn across a gap. Readings are the hold start
    times, so uneven spacing is used as it was, not assumed even.
    """
    # Variables:
    #   covariance, variance: The pooled within-run sums of time times value
    #     and of time squared, after centring each run.
    #   origin: The run's first reading time; times are counted from it so the
    #     sums stay small.
    #   points: One run's readings as (seconds from origin, value).
    covariance = 0.0
    variance = 0.0
    for run in runs:
        if len(run) < 2:
            continue
        origin = run[0].start
        points = [((hold.start - origin).total_seconds(), hold.value) for hold in run]
        mean_t = sum(t for t, _ in points) / len(points)
        mean_v = sum(v for _, v in points) / len(points)
        covariance += sum((t - mean_t) * (v - mean_v) for t, v in points)
        variance += sum((t - mean_t) ** 2 for t, _ in points)
    if variance == 0:
        return None
    return covariance / variance


def summarize(
    lines: Sequence[Line],
    device: str,
    data_item_id: str,
    level: float | None = None,
) -> ChannelStats:
    """One channel's time-aware summary over a capture."""
    # Variables:
    #   level: An optional level for seconds_above, such as a load limit.
    #   runs: The channel's holds, one list per gap-free run.
    #   values: Every value that held, for the minimum and maximum.
    runs = channel_holds(lines, device, data_item_id)
    holds = _flat(runs)
    values = [hold.value for hold in holds]
    return ChannelStats(
        device=device,
        data_item_id=data_item_id,
        runs=len(runs),
        readings=len(holds),
        seconds_covered=sum(hold.seconds for hold in holds),
        time_weighted_mean=time_weighted_mean(runs),
        minimum=min(values, default=None),
        maximum=max(values, default=None),
        slope_per_second=slope_per_second(runs),
        seconds_above=None if level is None else seconds_above(runs, level),
    )
