# Where tree-of-thought runs lost the tree, read from saved experiment records.
# Responsibility: measure reachability of the hypothesize step; never run anything.
"""How far each saved run got towards a tree-of-thought tree, and why not further.

    uv run python -m capstone.tree_reach results.records.jsonl [more.jsonl ...]
    uv run python -m capstone.tree_reach results.records.jsonl --json

The trace audit of 2026-11-05 (docs/benchmarks/2026-11-05-tot-trace-audit.md)
found 19 of 52 episodes with no saved tree, most of them because the run ended
before the hypothesize question was asked. This report makes that measurement
repeatable for any records file, so a change meant to fix it (the hypothesis
reserve, `HYPOTHESIS_RESERVE_SECONDS`) can be checked the same way.

It reads only what the records already hold: the model-call log (each
question's job, outcome and per-attempt seconds), the agent's steps and the
saved trees. It reads no hidden truth and makes no model calls.

Each run falls in one group:

    tree              a tree was saved (at least one candidate generated)
    skipped           adaptive branching chose the ordinary hypothesize step
    no_answer         the hypothesize question was asked but not answered
    before_<reason>   the run ended before the question, by stop reason
                      (before_timeout, before_model_unavailable, ...)
"""

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

from capstone.contracts import Contract
from capstone.experiment import ExperimentRecord, read_records


class Reach(Contract):
    """How far one run got towards a tree, and where its time went before it."""

    run_key: str
    scenario_id: str
    group: str
    # The stage the run's last decision was made in, and why the run stopped.
    last_stage: str | None
    termination_reason: str | None
    # Before the first hypothesize question (or in the whole run, if none):
    # seconds spent waiting on each job's attempts, and failed attempts per job.
    seconds_by_job: dict[str, float]
    failed_attempts_by_job: dict[str, int]
    research_tool_calls: int
    wall_seconds: float | None
    hypothesis_reserve_used: bool | None = None


def group_of(record: ExperimentRecord) -> str:
    """The run's group: tree, skipped, no_answer or before_<stop reason>."""
    # Variables:
    #   trees: The trees the policy saved; empty for the ordinary policy.
    #   asked: Whether any hypothesize question appears in the model-call log.
    trees = record.thoughts or []
    if any(t.candidates for t in trees):
        return "tree"
    if any(getattr(t, "branching", None) == "skipped" for t in trees):
        return "skipped"
    details = [] if record.model_calls is None else record.model_calls.details or []
    asked = any(call.job == "hypothesize" for call in details)
    if asked:
        return "no_answer"
    return f"before_{record.score.termination_reason or 'unknown'}"


def reach_of(record: ExperimentRecord) -> Reach:
    """Measure one record: its group, where it stopped, and the time before the tree."""
    # Variables:
    #   details: The model-call log, oldest first; empty for a scripted policy.
    #   seconds, failed: Per job, summed over the calls before the first
    #     hypothesize question, which is where reachability is lost.
    #   decisions: The agent's own steps (not model questions), in order.
    details = [] if record.model_calls is None else record.model_calls.details or []
    seconds: Counter[str] = Counter()
    failed: Counter[str] = Counter()
    for call in details:
        if call.job == "hypothesize":
            break
        for attempt in call.attempts:
            seconds[call.job] += attempt.seconds or 0.0
            if attempt.outcome != "answered":
                failed[call.job] += 1
    decisions = [s for s in record.agent_steps or [] if s.kind == "decision"]
    return Reach(
        run_key=record.run_key,
        scenario_id=record.scenario_id,
        group=group_of(record),
        last_stage=decisions[-1].phase if decisions else None,
        termination_reason=record.score.termination_reason,
        seconds_by_job={job: round(s, 1) for job, s in sorted(seconds.items())},
        failed_attempts_by_job=dict(sorted(failed.items())),
        research_tool_calls=sum(
            1
            for s in decisions
            if s.tool is not None and s.phase in ("investigate", "test")
        ),
        wall_seconds=record.wall_seconds,
        hypothesis_reserve_used=record.hypothesis_reserve_used,
    )


def summarize(reaches: Sequence[Reach]) -> dict:
    """Counts per group, and per group the seconds and failures before the tree."""
    # Variables:
    #   by_group: The runs of each group, to total their time and failures.
    by_group: dict[str, list[Reach]] = {}
    for reach in reaches:
        by_group.setdefault(reach.group, []).append(reach)
    groups = {}
    for name, members in sorted(by_group.items()):
        seconds: Counter[str] = Counter()
        failed: Counter[str] = Counter()
        for member in members:
            seconds.update(member.seconds_by_job)
            failed.update(member.failed_attempts_by_job)
        groups[name] = {
            "runs": len(members),
            "seconds_by_job": {k: round(v, 1) for k, v in sorted(seconds.items())},
            "failed_attempts_by_job": dict(sorted(failed.items())),
            "reserve_used": sum(m.hypothesis_reserve_used is True for m in members),
        }
    return {"runs": len(reaches), "groups": groups}


def read_all(paths: Iterable[Path]) -> list[ExperimentRecord]:
    """Every record of every file, in file order."""
    records: list[ExperimentRecord] = []
    for path in paths:
        records += read_records(path)
    return records


def main(argv: Sequence[str] | None = None) -> int:
    """Print the reachability report for the given records files."""
    # Variables:
    #   args.json: Print the per-run rows and the summary as JSON instead of text.
    parser = argparse.ArgumentParser(prog="python -m capstone.tree_reach")
    parser.add_argument("records", type=Path, nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    reaches = [reach_of(r) for r in read_all(args.records)]
    summary = summarize(reaches)
    if args.json:
        rows = [r.model_dump(mode="json") for r in reaches]
        print(json.dumps({"summary": summary, "runs": rows}, indent=1))
        return 0
    print(f"{summary['runs']} run(s)")
    for name, group in summary["groups"].items():
        print(
            f"  {name}: {group['runs']} run(s); before the tree, seconds by job "
            f"{group['seconds_by_job']}, failed attempts {group['failed_attempts_by_job']}"
        )
    for reach in reaches:
        if reach.group != "tree":
            print(
                f"  - {reach.run_key}: {reach.group}, last stage {reach.last_stage}, "
                f"{reach.research_tool_calls} research call(s), "
                f"wall {reach.wall_seconds or 0:.0f} s"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
