# Command line for the read-only MTConnect collector.
# Responsibility: parse options and start collection; all logic lives in collector.py.
"""Collect MTConnect telemetry into a JSONL file.

    uv run python -m capstone.ingestion --url http://<agent-host>:8082 --out ../pilot-data/telemetry.jsonl
    uv run python -m capstone.ingestion --url http://<agent-host>:8082 --save-probe ../pilot-data/probe.xml

Run only against a machine the shop has approved for read-only collection.
Output paths inside a git checkout are refused (see privacy.py).
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from capstone.ingestion.collector import (
    MIN_INTERVAL_SECONDS,
    MTConnectCollector,
    run_collector,
)
from capstone.ingestion.privacy import ALLOW_FLAG, ALLOW_HELP, refusal


def main(argv: Sequence[str] | None = None) -> int:
    """Run the collector until interrupted or --polls is reached."""
    # Variables:
    #   argv: Command-line arguments; None means the real ones (tests pass a list).
    #   args: The parsed options: agent URL, device, output file, interval,
    #     count, poll limit and probe file.
    #   allow_inside_repo: Lets --out or --save-probe sit inside a git checkout;
    #     for synthetic fixtures only, so real shop data is never committed.
    #   option, path: Each output option and the file it names, checked
    #     before anything is fetched.
    #   problem: Why that path is refused, or a false value when it is allowed.
    #   collector: The agent reader built from those options.
    #   written: Records appended, printed as the run's summary.
    parser = argparse.ArgumentParser(prog="python -m capstone.ingestion")
    parser.add_argument("--url", required=True, help="MTConnect agent base URL")
    parser.add_argument("--device", help="only this device on a multi-device agent")
    parser.add_argument("--out", type=Path, help="JSONL file to append records to")
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help=f"seconds between polls (minimum {MIN_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--count", type=int, default=1000, help="max observations per request"
    )
    parser.add_argument("--polls", type=int, help="stop after this many polls")
    parser.add_argument(
        "--save-probe", type=Path, help="save /probe to this file and exit"
    )
    parser.add_argument(ALLOW_FLAG, action="store_true", help=ALLOW_HELP)
    args = parser.parse_args(argv)

    for option, path in (("--out", args.out), ("--save-probe", args.save_probe)):
        problem = path and not args.allow_inside_repo and refusal(path, option)
        if problem:
            parser.error(problem)
    collector = MTConnectCollector(args.url, device=args.device, count=args.count)
    if args.save_probe:
        args.save_probe.write_text(collector.probe(), encoding="utf-8")
        print(f"saved the machine's capability list to {args.save_probe}")
        return 0
    if args.out is None:
        parser.error("--out is required unless --save-probe is given")
    try:
        written = run_collector(
            collector, args.out, interval=args.interval, max_polls=args.polls
        )
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
        return 0
    print(f"wrote {written} records to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
