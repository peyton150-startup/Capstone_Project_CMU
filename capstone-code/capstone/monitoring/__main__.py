# Command line for the deterministic telemetry monitor.
# Responsibility: parse options, then replay or follow; the rules live in monitor.py.
"""Monitor collected telemetry and write alerts.

    uv run python -m capstone.monitoring --input telemetry.jsonl
    uv run python -m capstone.monitoring --input telemetry.jsonl --alerts alerts.jsonl \
        --follow --threshold LS1load=0:120 --stale-after 180

Deterministic: the alerts are a function of the file's records and the
options only. The wall clock is never read, so following a file live and
replaying it later give the same alerts. No model or agent takes part.
"""

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from capstone.monitoring.monitor import Monitor, Threshold
from capstone.monitoring.runner import JsonlFollower, append_alerts, replay


def parse_threshold(text: str) -> tuple[str, Threshold]:
    """Parse NAME=LOW:HIGH into a channel key and its range."""
    try:
        key, bounds = text.split("=", 1)
        low, high = (float(part) for part in bounds.split(":", 1))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"expected NAME=LOW:HIGH, got {text!r}"
        ) from error
    if low > high:
        raise argparse.ArgumentTypeError(f"LOW is above HIGH in {text!r}")
    return key, Threshold(low=low, high=high)


def main(argv: Sequence[str] | None = None) -> int:
    """Replay the file once, or with --follow keep reading it as it grows."""
    # Variables:
    #   follow: When set, keep reading new lines until interrupted; otherwise
    #     replay the file once and exit. Either way the same records give the
    #     same alerts.
    #   interval: Only how often the file is re-read; it never changes an alert.
    parser = argparse.ArgumentParser(prog="python -m capstone.monitoring")
    parser.add_argument(
        "--input", type=Path, required=True, help="collector JSONL file"
    )
    parser.add_argument("--alerts", type=Path, help="JSONL file to append alerts to")
    parser.add_argument(
        "--follow", action="store_true", help="keep reading as the file grows"
    )
    parser.add_argument(
        "--interval", type=float, default=2.0, help="seconds between reads"
    )
    parser.add_argument(
        "--stale-after",
        type=float,
        default=180.0,
        help="seconds of silence (above the 60 s heartbeat plus the poll interval)",
    )
    parser.add_argument(
        "--threshold",
        type=parse_threshold,
        action="append",
        default=[],
        help="safe range for a channel, NAME=LOW:HIGH (repeatable)",
    )
    args = parser.parse_args(argv)

    monitor = Monitor(thresholds=dict(args.threshold), stale_after=args.stale_after)
    follower = JsonlFollower(args.input)
    append_alerts(args.alerts, replay(follower.read_new(), monitor))
    if not args.follow:
        return 0
    try:
        while True:
            time.sleep(args.interval)
            append_alerts(args.alerts, replay(follower.read_new(), monitor))
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
