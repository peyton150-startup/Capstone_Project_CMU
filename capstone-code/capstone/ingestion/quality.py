# Per-channel data quality in a recorded capture: UNAVAILABLE stretches and staleness.
# Responsibility: say where each channel's data cannot be trusted; no interpretation.
"""Per-channel data quality for a recorded capture (the rest of SM-2).

Gap markers (PR #204) say where the whole collection broke. Two things can
still go wrong for one channel while collection runs fine:

- **UNAVAILABLE stretches.** MTConnect reports UNAVAILABLE when a value is
  indeterminate, so the time from an UNAVAILABLE record to the channel's next
  real value is a hole in that channel, not a value. `unavailable_spans`
  lists those holes. A hole that is still open when collection breaks (a gap
  or a restart) or ends is closed at the last observation before the break,
  because nothing after that was collected.
- **Staleness.** A regularly sampled channel that stops updating is stale.
  Many channels only report when their value changes (Execution, a program
  name), and those can be silent for hours with nothing wrong, so a channel
  is only checked when a person gives it an age limit. `stale_channels`
  reports the channels whose last record is older than their limit, and says
  when collection broke after that record, so silence caused by the collector
  is not blamed on the channel.

Every time used here is the machine's own (`source_timestamp`), the same
clock the records carry.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from capstone.ingestion.channel_map import read_capture
from capstone.ingestion.record import CollectorMarker, Line, TelemetryRecord

SpanEnd = Literal["available_again", "collection_broke", "capture_end"]
Channel = tuple[str, str]


class UnavailableSpan(BaseModel):
    """A stretch of time in which one channel reported no value."""

    model_config = ConfigDict(frozen=True)

    # Variables:
    #   device, data_item_id: The channel.
    #   start: The machine time of the UNAVAILABLE record that opened it.
    #   end: The machine time it closed: the channel's next real value, or the
    #     last observation before collection broke or ended.
    #   ended_by: available_again (a real value came back), collection_broke (a
    #     gap or restart came first, so nobody knows when it came back) or
    #     capture_end (the capture ended while it was still unavailable).
    device: str
    data_item_id: str
    start: datetime
    end: datetime
    ended_by: SpanEnd

    @property
    def seconds(self) -> float:
        """How long the channel had no value."""
        return (self.end - self.start).total_seconds()


class ChannelAge(BaseModel):
    """How long ago one channel last reported, measured at a given time."""

    model_config = ConfigDict(frozen=True)

    # Variables:
    #   device, data_item_id: The channel.
    #   last_at: The machine time of its last record, value or UNAVAILABLE.
    #   age_seconds: How long before the check time that was.
    #   limit_seconds: The age a person allowed it; None means not checked.
    #   broke_since: True when collection broke (a gap or restart marker)
    #     after its last record, so the silence may be the collector's.
    device: str
    data_item_id: str
    last_at: datetime
    age_seconds: float
    limit_seconds: float | None
    broke_since: bool

    @property
    def stale(self) -> bool:
        """Older than its limit; never true for a channel with no limit."""
        return self.limit_seconds is not None and self.age_seconds > self.limit_seconds


def _channel(record: TelemetryRecord) -> Channel:
    return (record.device, record.data_item_id)


def _breaks(line: Line) -> bool:
    """A marker after which nothing before it can be joined to what follows."""
    return isinstance(line, CollectorMarker) and line.event in ("gap", "started")


def unavailable_spans(lines: Iterable[Line]) -> list[UnavailableSpan]:
    """Every stretch in which a channel reported UNAVAILABLE, oldest first."""
    # Variables:
    #   open_spans: For each channel now UNAVAILABLE, when that began.
    #   last_seen: The machine time of the latest observation of any channel
    #     since collection last broke; a span still open at a break closes here.
    #   spans: The finished stretches.
    open_spans: dict[Channel, datetime] = {}
    last_seen: datetime | None = None
    spans: list[UnavailableSpan] = []

    def close_all(ended_by: SpanEnd) -> None:
        """Close every open stretch at the last collected reading."""
        # Variables:
        #   ended_by: Why they close: collection broke, or the capture ended.
        for (device, item), start in open_spans.items():
            spans.append(
                UnavailableSpan(
                    device=device,
                    data_item_id=item,
                    start=start,
                    end=max(start, last_seen or start),
                    ended_by=ended_by,
                )
            )
        open_spans.clear()

    for line in lines:
        if isinstance(line, CollectorMarker):
            if _breaks(line):
                close_all("collection_broke")
                last_seen = None
            continue
        last_seen = line.source_timestamp
        key = _channel(line)
        if not line.available:
            open_spans.setdefault(key, line.source_timestamp)
        elif key in open_spans:
            spans.append(
                UnavailableSpan(
                    device=key[0],
                    data_item_id=key[1],
                    start=open_spans.pop(key),
                    end=line.source_timestamp,
                    ended_by="available_again",
                )
            )
    close_all("capture_end")
    return sorted(spans, key=lambda span: (span.start, span.device, span.data_item_id))


def channel_ages(
    lines: Sequence[Line],
    limits: Mapping[str, float] | None = None,
    at: datetime | None = None,
) -> list[ChannelAge]:
    """How long ago each channel last reported, oldest report first.

    `at` defaults to the capture's latest observation time, so a capture is
    judged on its own clock, not on when someone reads the file.
    """
    # Variables:
    #   limits: Allowed age in seconds per data item id, from a person; a
    #     channel missing from it is listed but never called stale.
    #   at: The check time; None means the latest observation in the capture.
    #   last: Each channel's last record, and its position in the file.
    #   last_break: The position of the latest gap or started marker, to tell
    #     whether collection broke after a channel's last record.
    limits = limits or {}
    last: dict[Channel, tuple[int, TelemetryRecord]] = {}
    last_break = -1
    for position, line in enumerate(lines):
        if isinstance(line, CollectorMarker):
            if _breaks(line):
                last_break = position
            continue
        last[_channel(line)] = (position, line)
    if not last:
        return []
    check_at = at or max(record.source_timestamp for _, record in last.values())
    ages = [
        ChannelAge(
            device=record.device,
            data_item_id=record.data_item_id,
            last_at=record.source_timestamp,
            age_seconds=(check_at - record.source_timestamp).total_seconds(),
            limit_seconds=limits.get(record.data_item_id),
            broke_since=position < last_break,
        )
        for position, record in last.values()
    ]
    return sorted(ages, key=lambda age: (age.last_at, age.device, age.data_item_id))


def stale_channels(
    lines: Sequence[Line],
    limits: Mapping[str, float],
    at: datetime | None = None,
) -> list[ChannelAge]:
    """The channels given a limit whose last report is older than it."""
    # Variables:
    #   limits: Allowed age in seconds per data item id; only these are checked.
    return [age for age in channel_ages(lines, limits, at) if age.stale]


def load_limits(path: Path) -> dict[str, float]:
    """Read {data item id: seconds} from a JSON file, refusing a bad limit."""
    # Variables:
    #   data: The file's JSON object.
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected an object of data item id to seconds")
    limits: dict[str, float] = {}
    for item, seconds in data.items():
        if isinstance(seconds, bool) or not isinstance(seconds, int | float):
            raise ValueError(f"{path}: the limit for {item} is not a number")
        if seconds <= 0:
            raise ValueError(f"{path}: the limit for {item} must be positive")
        limits[item] = float(seconds)
    return limits


def main(argv: Sequence[str] | None = None) -> int:
    """Print a capture's UNAVAILABLE stretches and stale channels."""
    # Variables:
    #   argv: Command-line arguments; None means the real ones.
    #   limits: Per-channel age limits from --limits, or none.
    #   stale: Channels older than their limit; any makes the exit code 1.
    parser = argparse.ArgumentParser(prog="python -m capstone.ingestion.quality")
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument(
        "--limits", type=Path, help="JSON file: {data item id: seconds}"
    )
    parser.add_argument(
        "--at",
        type=datetime.fromisoformat,
        help="check time with its UTC offset (default: the capture's last reading)",
    )
    args = parser.parse_args(argv)
    if args.at is not None and args.at.utcoffset() is None:
        parser.error("--at needs its UTC offset, e.g. 2026-11-07T14:00:00Z")
    try:
        limits = load_limits(args.limits) if args.limits else {}
    except ValueError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    lines = read_capture(args.capture)
    spans = unavailable_spans(lines)
    print(f"{len(spans)} UNAVAILABLE stretch(es)")
    for span in spans:
        print(
            f"  {span.device}/{span.data_item_id}: {span.start.isoformat()}"
            f" for {span.seconds:.0f} s ({span.ended_by})"
        )
    stale = stale_channels(lines, limits, args.at)
    print(f"{len(stale)} stale of {len(limits)} channel(s) with a limit")
    for age in stale:
        note = ", collection broke since" if age.broke_since else ""
        print(
            f"  {age.device}/{age.data_item_id}: last report {age.age_seconds:.0f} s"
            f" ago, limit {age.limit_seconds:.0f} s{note}"
        )
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
