# The shop visit checklist and the technician's event log (SM-4).
# Responsibility: read the log a person keeps during a capture, line its entries
# up with the capture's collected time, and report what the visit has shown.
"""Shop visit checklist and technician event log (SM-4 in docs/MVP_SCOPE.md).

During the first capture on a real machine, an operator or technician writes
down what happened: program changes, tool changes, warm-up, maintenance and
anything unusual. Without that, a jump in spindle load cannot be told apart
from a new program. The log is a CSV file a person can fill in by hand::

    at,event_type,note,logged_by,until
    2026-11-07T09:02:00-05:00,warm_up,spindle warm-up program,operator A,2026-11-07T09:17:00-05:00
    2026-11-07T09:30:00-05:00,program_change,started part 1142,operator A,

Every time must carry its UTC offset (or Z): a clock time with no zone is
refused rather than guessed, because a one-hour mistake would match an entry
to the wrong part of the capture.

`match_events` places each entry against the capture: inside a stretch that
was collected without a break (`covered`), in a stretch whose data was lost
(`in_gap`), or before or after the capture (`outside`). `check_visit` adds the
saved probe and the capture's own shape, and lists the checklist items only a
person can confirm. The log, like the capture and the probe, holds shop
details, so it stays with the private pilot data, never in this repository.
"""

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from capstone.ingestion.channel_map import parse_probe, read_capture
from capstone.ingestion.privacy import ALLOW_FLAG, ALLOW_HELP, refusal
from capstone.ingestion.record import CollectorMarker, Line, gap_free_runs

EventType = Literal[
    "program_change",
    "tool_change",
    "warm_up",
    "maintenance",
    "unusual",
    "other",
]
Placement = Literal["covered", "in_gap", "outside"]

LOG_COLUMNS = ("at", "event_type", "note", "logged_by", "until")
DEFAULT_TOLERANCE = timedelta(seconds=60)

# The checklist items no file can prove; the report lists them for a person.
CONFIRM_BY_HAND = (
    "the shop approved read-only access in writing",
    "recording while the machine runs had no measurable effect on it",
    "the capture holds several normal operating cycles",
    "past alarm and maintenance history was asked for",
    "technicians said what they check first for common symptoms",
)


class TechnicianEvent(BaseModel):
    """One entry a person wrote in the event log during the capture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   at: When it happened, with its UTC offset; a time with no zone is refused.
    #   event_type: What kind of event it was; "other" when none of the named
    #     kinds fits, so a person is never forced to mislabel one.
    #   note: A short description in the person's words.
    #   logged_by: Who wrote it, so a question about the entry has someone to ask.
    #   until: When a lasting event (a warm-up, a maintenance stop) ended, or
    #     None for an instant one.
    at: datetime
    event_type: EventType
    note: str = Field(min_length=1)
    logged_by: str = Field(min_length=1)
    until: datetime | None = None

    @field_validator("at", "until")
    @classmethod
    def has_a_time_zone(cls, value: datetime | None) -> datetime | None:
        """Refuse a clock time with no UTC offset instead of guessing one."""
        # Variables:
        #   value: The parsed `at` or `until`; it must say which zone its clock
        #     was in, or it could be matched an hour off.
        if value is not None and value.utcoffset() is None:
            raise ValueError("give the time with its UTC offset, e.g. -05:00 or Z")
        return value

    @model_validator(mode="after")
    def ends_after_it_starts(self):
        """Refuse an entry whose end comes before its start."""
        if self.until is not None and self.until < self.at:
            raise ValueError("until is before at")
        return self


class EventMatch(BaseModel):
    """Where one log entry falls in the capture."""

    model_config = ConfigDict(frozen=True)

    # Variables:
    #   event: The log entry.
    #   placement: covered (inside a stretch collected without a break), in_gap
    #     (inside the capture, but where data was lost or the collector was not
    #     running) or outside (before the first or after the last observation).
    #   nearest_observation_at: The machine time of the observation closest to
    #     the entry, or None when the capture has none.
    #   offset_seconds: The entry's time minus that observation's time; a large
    #     value on every entry hints that the two clocks disagree.
    event: TechnicianEvent
    placement: Placement
    nearest_observation_at: datetime | None
    offset_seconds: float | None


class VisitCheck(BaseModel):
    """What the visit's files show, for the three questions of SM-4."""

    model_config = ConfigDict(frozen=True)

    # Variables:
    #   probe_items: How many data items the saved probe describes, or None
    #     when no probe was given or it could not be read.
    #   probe_problem: Why the probe could not be read, if it could not.
    #   observations: Observations in the capture.
    #   channels_with_values: Channels that reported at least one value, as
    #     opposed to only UNAVAILABLE.
    #   runs: Stretches collected without a break (see gap_free_runs).
    #   gaps: Gap markers, each a place where observations were lost.
    #   first_at, last_at: The machine times of the first and last observation.
    #   matches: Each log entry and where it falls in the capture.
    probe_items: int | None
    probe_problem: str | None = None
    observations: int
    channels_with_values: int
    runs: int
    gaps: int
    first_at: datetime | None
    last_at: datetime | None
    matches: list[EventMatch]

    @property
    def unmatched(self) -> list[EventMatch]:
        """The entries that fall where nothing was collected."""
        return [m for m in self.matches if m.placement != "covered"]

    @property
    def ready(self) -> bool:
        """The files answer what files can: a probe, data, and a matched log."""
        return (
            self.probe_items is not None
            and self.observations > 0
            and bool(self.matches)
            and not self.unmatched
        )


def load_event_log(path: Path) -> list[TechnicianEvent]:
    """Read a technician's CSV event log, oldest entry first.

    Raises ValueError naming the line of the first entry that cannot be read,
    so the person who wrote it can fix that line.
    """
    # Variables:
    #   reader: The CSV rows as dictionaries keyed by the header.
    #   missing: Required columns the header lacks.
    #   number: The row's line number in the file, for the error message.
    #   fields: The row with empty cells dropped, so a blank `until` is None.
    events: list[TechnicianEvent] = []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = [c for c in LOG_COLUMNS[:4] if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: the header lacks {', '.join(missing)}")
        for number, row in enumerate(reader, start=2):
            fields = {k: v.strip() for k, v in row.items() if k and v and v.strip()}
            if not fields:
                continue
            try:
                events.append(TechnicianEvent.model_validate(fields))
            except ValueError as error:
                raise ValueError(f"{path}, line {number}: {error}") from error
    return sorted(events, key=lambda event: event.at)


def match_events(
    events: Iterable[TechnicianEvent],
    lines: Iterable[Line],
    tolerance: timedelta = DEFAULT_TOLERANCE,
) -> list[EventMatch]:
    """Place each log entry against the capture's collected time.

    A collected stretch runs from its first to its last observation's machine
    time, widened by `tolerance` on each side, because a person writing down
    a tool change notes the time a little before or after the machine does.
    """
    # Variables:
    #   lines: The capture, observations and collector markers in file order.
    #   tolerance: How far outside a collected stretch an entry may fall and
    #     still count as covered; it allows for a person's rounding and a
    #     small difference between the two clocks.
    #   spans: Each gap-free run's first and last machine time.
    #   times: Every observation's machine time, sorted, to find the nearest.
    #   start, end: The whole capture's first and last observation times; an
    #     entry between them that no stretch covers is in a gap.
    #   nearest: The observation time closest to the entry, reported so a
    #     person can see how far apart the log and the machine are.
    #   placement: The verdict for the entry: covered, in_gap or outside.
    runs = gap_free_runs(lines)
    spans = [
        (min(r.source_timestamp for r in run), max(r.source_timestamp for r in run))
        for run in runs
    ]
    times = sorted(r.source_timestamp for run in runs for r in run)
    matches: list[EventMatch] = []
    for event in events:
        if not times:
            matches.append(
                EventMatch(
                    event=event,
                    placement="outside",
                    nearest_observation_at=None,
                    offset_seconds=None,
                )
            )
            continue
        nearest = min(times, key=lambda t: abs(t - event.at))
        start, end = times[0], times[-1]
        if any(lo - tolerance <= event.at <= hi + tolerance for lo, hi in spans):
            placement: Placement = "covered"
        elif start <= event.at <= end:
            placement = "in_gap"
        else:
            placement = "outside"
        matches.append(
            EventMatch(
                event=event,
                placement=placement,
                nearest_observation_at=nearest,
                offset_seconds=(event.at - nearest).total_seconds(),
            )
        )
    return matches


def check_visit(
    probe_xml: str | None,
    lines: Sequence[Line],
    events: Sequence[TechnicianEvent],
    tolerance: timedelta = DEFAULT_TOLERANCE,
) -> VisitCheck:
    """Report what the saved probe, the capture and the event log show."""
    # Variables:
    #   probe_xml: The saved /probe document, or None if none was saved yet.
    #   probe_items: Data items the probe describes; None when it is missing
    #     or unreadable, which keeps the check from reporting ready.
    #   probe_problem: Why there is no item count, shown on the checklist.
    #   observations: The capture's observation lines, markers left out.
    probe_items: int | None = None
    probe_problem: str | None = None
    if probe_xml is None:
        probe_problem = "no probe was given"
    else:
        try:
            probe_items = len(parse_probe(probe_xml))
        except (ValueError, ET.ParseError) as error:
            probe_problem = str(error)
    observations = [line for line in lines if not isinstance(line, CollectorMarker)]
    return VisitCheck(
        probe_items=probe_items,
        probe_problem=probe_problem,
        observations=len(observations),
        channels_with_values=len(
            {(r.device, r.data_item_id) for r in observations if r.available}
        ),
        runs=len(gap_free_runs(lines)),
        gaps=sum(
            1
            for line in lines
            if isinstance(line, CollectorMarker) and line.event == "gap"
        ),
        first_at=min((r.source_timestamp for r in observations), default=None),
        last_at=max((r.source_timestamp for r in observations), default=None),
        matches=match_events(events, lines, tolerance),
    )


def report_lines(check: VisitCheck) -> list[str]:
    """The visit check as the checklist a person reads, one line per item."""
    # Variables:
    #   mark: "[x]" when the files show an item, "[ ]" when they do not.
    #   covered: How many log entries fall in collected time.
    #   out: The checklist lines, grouped under SM-4's three questions and
    #     ending with the items only a person can confirm.

    def mark(done: bool) -> str:
        return "[x]" if done else "[ ]"

    covered = len(check.matches) - len(check.unmatched)
    out = ["Can we read it?"]
    if check.probe_items is not None:
        out.append(f"  [x] probe saved: {check.probe_items} data items")
    else:
        out.append(f"  [ ] probe saved: {check.probe_problem}")
    out.append("Can we interpret it?")
    out.append(
        f"  {mark(check.observations > 0)} capture: {check.observations} observations"
        f" from {check.channels_with_values} channels with values"
    )
    if check.first_at is not None and check.last_at is not None:
        out.append(
            f"      from {check.first_at.isoformat()} to {check.last_at.isoformat()}"
        )
    out.append(f"      {check.runs} unbroken stretch(es), {check.gaps} gap marker(s)")
    out.append("Can we verify it?")
    out.append(
        f"  {mark(bool(check.matches) and not check.unmatched)} event log:"
        f" {covered} of {len(check.matches)} entries fall in collected time"
    )
    for match in check.unmatched:
        event = match.event
        out.append(
            f"      {match.placement}: {event.at.isoformat()} {event.event_type}"
            f" ({event.note})"
        )
    out.append("Confirm by hand:")
    out.extend(f"  [ ] {item}" for item in CONFIRM_BY_HAND)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Write an empty event log, or check a visit's probe, capture and log."""
    # Variables:
    #   argv: Command-line arguments; None means the real ones.
    #   args: The chosen command and its files.
    #   check: What the files show, printed as the checklist.
    #   outcome: 0 when the files answer everything files can (see
    #     VisitCheck.ready), 1 otherwise, so a script can stop on it.
    parser = argparse.ArgumentParser(prog="python -m capstone.ingestion.visit_log")
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template", help="write an empty event log")
    template.add_argument("--out", type=Path, required=True)
    template.add_argument(ALLOW_FLAG, action="store_true", help=ALLOW_HELP)
    check_cmd = commands.add_parser("check", help="check a visit's files")
    check_cmd.add_argument("--probe", type=Path, help="the saved /probe document")
    check_cmd.add_argument("--capture", type=Path, required=True)
    check_cmd.add_argument("--events", type=Path, required=True)
    check_cmd.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE.total_seconds(),
        help="seconds an entry may fall outside collected time (default 60)",
    )
    args = parser.parse_args(argv)

    if args.command == "template":
        problem = not args.allow_inside_repo and refusal(args.out, "--out")
        if problem:
            parser.error(problem)
        if args.out.exists():
            parser.error(f"--out {args.out} already exists; it may hold a log")
        args.out.write_text(",".join(LOG_COLUMNS) + "\n", encoding="utf-8")
        print(f"wrote an empty event log to {args.out}")
        return 0

    try:
        events = load_event_log(args.events)
    except ValueError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    check = check_visit(
        args.probe.read_text(encoding="utf-8") if args.probe else None,
        read_capture(args.capture),
        events,
        timedelta(seconds=args.tolerance),
    )
    print("\n".join(report_lines(check)))
    return 0 if check.ready else 1


if __name__ == "__main__":
    sys.exit(main())
