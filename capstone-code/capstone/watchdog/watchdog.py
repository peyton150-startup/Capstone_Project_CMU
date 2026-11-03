# Decides, from the file's last line and the current time, whether the collector is down.
# Responsibility: the silence rule and reading the last line; the clock comes from the caller.
"""The watchdog's rule, kept free of the clock so it can be tested exactly.

`Watchdog.check(line, now)` is given the time; only `__main__` reads the
wall clock. That keeps the rule testable while the process stays live-only.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from capstone.ingestion.record import CollectorMarker, Line, parse_line

# How far back from the end of the file to look for the last complete line.
TAIL_BYTES = 65_536


class WatchdogAlert(BaseModel):
    """One thing the watchdog noticed. Live-only: it depends on when it ran."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   kind: "silent" when the file stopped growing without a clean stop,
    #     "recovered" when new lines arrive again.
    #   input: The telemetry file being watched.
    #   at: The wall-clock time of the check that raised it.
    #   last_line_at: The time of the newest line at that check.
    #   live_only: Always True; marks these alerts as not reproducible by replay.
    kind: Literal["silent", "recovered"]
    severity: Literal["info", "warning"]
    input: str
    message: str
    at: datetime
    last_line_at: datetime | None
    live_only: Literal[True] = True


def line_time(line: Line) -> datetime:
    """When a line was written: a marker's time, or a record's receive time."""
    return line.at if isinstance(line, CollectorMarker) else line.received_at


def last_line(path: Path) -> Line | None:
    """The file's last complete, readable line, or None if there is none.

    Reads only the end of the file, so a week of telemetry costs nothing.
    A half-written final line is ignored; the line before it is used.
    """
    # Variables:
    #   tail: The last TAIL_BYTES of the file, enough to hold several lines.
    #   texts: The complete lines in that tail, newest last.
    if not path.exists():
        return None
    with path.open("rb") as source:
        source.seek(0, os.SEEK_END)
        size = source.tell()
        source.seek(max(0, size - TAIL_BYTES))
        tail = source.read()
    end = tail.rfind(b"\n")
    if end < 0:
        return None
    texts = tail[:end].decode("utf-8", errors="replace").splitlines()
    for text in reversed(texts):
        try:
            return parse_line(text)
        except ValueError:
            continue
    return None


class Watchdog:
    """Raises one alert when the collector goes silent, and one when it is back."""

    def __init__(self, path: Path, *, silent_after: float = 180.0) -> None:
        # Variables:
        #   path: The telemetry file the collector writes.
        #   silent_after: Seconds without a new line before the collector is
        #     called silent; keep it above the 60 s heartbeat plus the poll
        #     interval, or a quiet machine looks like a crash.
        #   _silent: True while an alert is outstanding, so it is raised once.
        self.path = path
        self.silent_after = silent_after
        self._silent = False

    def check(self, line: Line | None, now: datetime) -> list[WatchdogAlert]:
        """Compare the newest line with `now` and return any alert."""
        # Variables:
        #   line: The file's newest line, or None if it has none yet.
        #   stopped: True when that line is a clean stop: silence is expected.
        #   age: Seconds since the newest line was written.
        if line is None:
            return []
        written = line_time(line)
        stopped = isinstance(line, CollectorMarker) and line.event == "stopped"
        age = (now - written).total_seconds()
        if not stopped and age > self.silent_after:
            if self._silent:
                return []
            self._silent = True
            return [
                self._alert(
                    "silent",
                    "warning",
                    f"no new line for {age:.0f} s and no clean stop: the collector "
                    "or its connection to the machine may be down",
                    now,
                    written,
                )
            ]
        if self._silent:
            self._silent = False
            message = "collector stopped cleanly" if stopped else "new lines again"
            return [self._alert("recovered", "info", message, now, written)]
        return []

    def _alert(
        self,
        kind: Literal["silent", "recovered"],
        severity: Literal["info", "warning"],
        message: str,
        now: datetime,
        written: datetime,
    ) -> WatchdogAlert:
        """An alert about the watched file."""
        return WatchdogAlert(
            kind=kind,
            severity=severity,
            input=str(self.path),
            message=message,
            at=now,
            last_line_at=written,
        )
