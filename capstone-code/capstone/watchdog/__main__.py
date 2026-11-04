# Command line for the collector watchdog; the only telemetry process that reads the clock.
# Responsibility: read the wall clock on a timer and report what Watchdog.check decides.
"""Watch the collector's file and say when it stops growing.

uv run python -m capstone.watchdog --input telemetry.jsonl --alerts watchdog.jsonl
"""

import argparse
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from capstone.watchdog.watchdog import Watchdog, WatchdogAlert, last_line


def report(alerts: list[WatchdogAlert], path: Path | None) -> None:
    """Print alerts and, if a path is given, append them to a JSONL file."""
    # Variables:
    #   alerts: What this check raised; usually empty.
    #   path: The watchdog's own alerts file, kept apart from the monitor's
    #     replayable alerts; None means print only.
    for alert in alerts:
        print(
            f"{alert.at.isoformat()} {alert.severity.upper():7} {alert.kind}: {alert.message}"
        )
    if path is None or not alerts:
        return
    with path.open("a", encoding="utf-8") as sink:
        for alert in alerts:
            sink.write(alert.model_dump_json() + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Check the file every --interval seconds until interrupted (or --checks)."""
    # Variables:
    #   args: The parsed options: input file, alerts file, silence limit,
    #     check interval and check limit.
    #   checks: Stop after this many checks; None runs until interrupted.
    #   watchdog: Remembers whether a silence is already reported.
    #   done: Checks made so far, compared with --checks.
    parser = argparse.ArgumentParser(prog="python -m capstone.watchdog")
    parser.add_argument(
        "--input", type=Path, required=True, help="collector JSONL file"
    )
    parser.add_argument("--alerts", type=Path, help="JSONL file for watchdog alerts")
    parser.add_argument(
        "--silent-after",
        type=float,
        default=180.0,
        help="seconds without a new line (above the 60 s heartbeat plus poll interval)",
    )
    parser.add_argument(
        "--interval", type=float, default=10.0, help="seconds between checks"
    )
    parser.add_argument("--checks", type=int, help="stop after this many checks")
    args = parser.parse_args(argv)

    watchdog = Watchdog(args.input, silent_after=args.silent_after)
    done = 0
    try:
        while args.checks is None or done < args.checks:
            done += 1
            report(
                watchdog.check(last_line(args.input), datetime.now(UTC)), args.alerts
            )
            if args.checks is None or done < args.checks:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
