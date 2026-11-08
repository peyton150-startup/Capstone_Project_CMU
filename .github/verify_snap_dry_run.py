"""Verify a complete offline SNAP evaluation, not model correctness.

Used by CI after running the real full_evaluation CLI with --provider snap.
Never imports a provider transport and never initiates a network request.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

FAMILIES = {"FN", "TS", "TL", "RUN", "BT"}
OUTPUTS = ("report.json", "report.md", "scope_manifest.json", "ledger.jsonl")


def verify(out: Path, expected_episodes: int, commit: str) -> dict:
    missing = [name for name in OUTPUTS if not (out / name).is_file()]
    if missing:
        raise ValueError(f"missing full-evaluation outputs: {missing}")
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    scope = json.loads((out / "scope_manifest.json").read_text(encoding="utf-8"))

    provenance = report["provenance"]
    if provenance["commit_checked_out"] != commit:
        raise ValueError("report is not pinned to the checked-out commit")
    if not provenance["inventory_source_hashes_verified"]:
        raise ValueError("inventory source hashes were not verified")
    if scope["unexplained"] or scope["stale"]:
        raise ValueError("scope manifest has unexplained or stale files")
    evidence = report["evidence"]
    if evidence["episodes"] != expected_episodes:
        raise ValueError(
            f"expected {expected_episodes} archived episodes, got {evidence['episodes']}"
        )
    if evidence["full_traces"] + evidence["record_only_traces"] != evidence["episodes"]:
        raise ValueError("trace-completeness counts do not reconcile")
    if report["reliability"]["packets_refused_by_truth_check"]:
        raise ValueError("archived evidence packets were refused by the truth check")
    counts = report["correctness"]
    if min(counts["functions"], counts["tests"], counts["tools"]) < 1:
        raise ValueError("inventory did not enumerate every project area")

    rows = [
        json.loads(line)
        for line in (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != report["judging"]["rows"]:
        raise ValueError("ledger rows disagree with the report")
    seen = set()
    families = Counter()
    statuses = Counter()
    for row in rows:
        identity = (
            row["family"], row["item_id"], row["provider"], row["question_id"]
        )
        if identity in seen:
            raise ValueError(f"duplicate question ledger row: {identity}")
        seen.add(identity)
        families[row["family"]] += 1
        statuses[row["status"]] += 1
        if row["provider"] != "snap":
            raise ValueError("SNAP-only smoke test included another provider")
    if set(families) != FAMILIES:
        raise ValueError(f"missing question families: {sorted(FAMILIES - set(families))}")
    if dict(statuses) != report["judging"]["by_status"]:
        raise ValueError("judging status counts do not reconcile")
    if statuses.get("answered", 0):
        raise ValueError("dry run unexpectedly contains answered model requests")
    if not report["budget"]["requests"]:
        raise ValueError("evaluation generated no answerable requests")

    requests = list((out / "requests").glob("*.request.json"))
    if not requests:
        raise ValueError("no SNAP request files were prepared")
    if list((out / "requests").glob("*.answers.json")):
        raise ValueError("dry run must never produce paid model answers")
    if report.get("live_budget") is not None:
        raise ValueError("the evaluation sent requests instead of preparing them")

    return {
        "commit": commit,
        "episodes": evidence["episodes"],
        "full_traces": evidence["full_traces"],
        "record_only_traces": evidence["record_only_traces"],
        "functions": counts["functions"],
        "tests": counts["tests"],
        "tools": counts["tools"],
        "ledger_rows": len(rows),
        "question_families": dict(sorted(families.items())),
        "requests_planned": report["budget"]["requests"],
        "request_files": len(requests),
        "estimated_input_usd": report["budget"]["cost_usd_estimate"],
        "live_requests_sent": 0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-episodes", type=int, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    summary = verify(args.out, args.expected_episodes, args.commit)
    (args.out / "readiness-check.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
