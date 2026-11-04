# Live crash detection for the collector, kept apart from the deterministic monitor.
# Responsibility: notice, while it is happening, that the telemetry file stopped growing.
"""Collector watchdog: the one telemetry component that reads the wall clock.

    uv run python -m capstone.watchdog --input telemetry.jsonl --alerts watchdog.jsonl

It looks only at the last line of the collector's file. If that line is
older than `--silent-after` seconds and is not a clean `stopped` marker, the
collector (or its connection to the machine) is down, and it says so once.
The collector writes a heartbeat at least every 60 s while polls succeed, so
a quiet machine is not mistaken for a dead collector.

Its alerts depend on when it runs, so they are live-only: they are never
replayed and are kept in their own file, apart from the monitor's alerts.
Plain code: no model or agent takes part.
"""

from capstone.watchdog.watchdog import Watchdog, WatchdogAlert, last_line

__all__ = ["Watchdog", "WatchdogAlert", "last_line"]
