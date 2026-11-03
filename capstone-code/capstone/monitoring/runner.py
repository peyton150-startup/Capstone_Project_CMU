# Feeds stored telemetry into the monitor, once (replay) or as it grows (follow).
# Responsibility: read the collector's JSONL safely and call the monitor in order.
"""Read the collector's JSONL file and run the monitor over it."""

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO

from capstone.ingestion.record import CollectorMarker, Line, parse_line
from capstone.monitoring.monitor import Alert, Monitor


class JsonlFollower:
    """Reads observations and collector markers added to a JSONL file.

    Only complete lines are read, so a line the collector is still writing is
    picked up on the next read instead of being parsed half-written.
    """

    def __init__(self, path: Path, *, log: TextIO | None = None) -> None:
        # Variables:
        #   _offset: The byte position after the last complete line read.
        #   log: Where unreadable lines are reported (they are skipped, not fatal).
        self.path = path
        self.log = log
        self._offset = 0

    def read_new(self) -> list[Line]:
        """Lines (observations and markers) completed since the last call."""
        if not self.path.exists():
            return []
        with self.path.open("rb") as source:
            source.seek(self._offset)
            data = source.read()
        # Variables:
        #   data: Every byte written since the last read, maybe ending in a
        #     half-written line.
        #   end: Where the last complete line ends; bytes after it wait for the
        #     next read.
        end = data.rfind(b"\n") + 1
        self._offset += end
        lines: list[Line] = []
        for text in data[:end].decode("utf-8").splitlines():
            if not text.strip():
                continue
            try:
                lines.append(parse_line(text))
            except ValueError as error:
                print(
                    f"skipped unreadable line: {type(error).__name__}",
                    file=self.log or sys.stderr,
                )
        return lines


def replay(records: Iterable[Line], monitor: Monitor) -> list[Alert]:
    """Run the monitor over stored records; the same input gives the same alerts.

    Staleness is checked against each record's receive time, so a silence in
    the recording is found without looking at the wall clock. Reading a file
    in several pieces (follow mode) gives the same alerts as reading it whole.
    """
    # Variables:
    #   record: An observation, or a collector marker (timed by its `at`).
    alerts: list[Alert] = []
    for record in records:
        if isinstance(record, CollectorMarker):
            alerts += monitor.check_stale(record.at)
            alerts += monitor.observe_marker(record)
        else:
            alerts += monitor.check_stale(record.received_at)
            alerts += monitor.observe(record)
    return alerts


def append_alerts(
    path: Path | None, alerts: list[Alert], *, echo: TextIO | None = None
) -> None:
    """Print alerts and, if a path is given, append them to a JSONL file."""
    # Variables:
    #   path: The alerts JSONL file; None means print only.
    #   echo: Where the readable line goes; None means standard output.
    for alert in alerts:
        print(
            f"{alert.at.isoformat()} {alert.severity.upper():7} {alert.kind:13} "
            f"{alert.device}/{alert.data_item_id or '-'}: {alert.message}",
            file=echo,
        )
    if path is None or not alerts:
        return
    with path.open("a", encoding="utf-8") as sink:
        for alert in alerts:
            sink.write(alert.model_dump_json() + "\n")
