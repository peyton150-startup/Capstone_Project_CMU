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
from capstone.ingestion.haas_http import haas_get
from capstone.ingestion.haas_profile import HaasConnectionProfile, verify_haas_probe
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
    parser.add_argument("--url", help="legacy MTConnect agent base URL")
    parser.add_argument(
        "--haas-profile", type=Path,
        help="private Pydantic-validated Haas NGC endpoint/authorization profile",
    )
    parser.add_argument("--device", help="only this device on a multi-device agent")
    parser.add_argument("--out", type=Path, help="JSONL file to append records to")
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
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
    # The shop-pinned path does not allow broad URL/device overrides. The
    # legacy --url path stays available for existing generic MTConnect tests.
    if bool(args.url) == bool(args.haas_profile):
        parser.error("provide exactly one of --url or --haas-profile")
    if args.haas_profile:
        if args.device:
            parser.error("--device is not allowed with a pinned Haas profile")
        if args.count > 1000 or args.count < 1:
            parser.error("Haas --count must be in [1, 1000]")
        profile = HaasConnectionProfile.model_validate_json(
            args.haas_profile.read_text(encoding="utf-8")
        )
        if args.interval is not None and args.interval < profile.poll_seconds:
            parser.error("Haas --interval cannot exceed the approved polling rate")
        interval = profile.poll_seconds if args.interval is None else args.interval
        collector = MTConnectCollector(
            profile.base_url,
            count=args.count,
            fetch=lambda url: haas_get(profile, url),
        )
        # Identity must be checked before any Current/Sample acquisition.
        probe = collector.probe()
        checked = verify_haas_probe(profile, probe)
        print(f"qualified approved Haas probe: {checked.data_item_count} channels")
    else:
        interval = 5.0 if args.interval is None else args.interval
        collector = MTConnectCollector(args.url, device=args.device, count=args.count)
        probe = None
    if args.save_probe:
        args.save_probe.write_text(
            probe if probe is not None else collector.probe(), encoding="utf-8"
        )
        print(f"saved the machine's capability list to {args.save_probe}")
        return 0
    if args.out is None:
        parser.error("--out is required unless --save-probe is given")
    try:
        written = run_collector(
            collector, args.out, interval=interval, max_polls=args.polls
        )
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
        return 0
    print(f"wrote {written} records to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
