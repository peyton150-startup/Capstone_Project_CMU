# The same cases run with no memory, keyword recall and semantic recall.
# Responsibility: run each memory mode over one case list and report them side by side.
"""Does memory make investigations better, not just searchable?

    uv run python -m capstone.memory_comparison run --name cmp-1 --known --out cmp.jsonl
    uv run python -m capstone.memory_comparison report --results cmp.jsonl --labels labels.jsonl

`run` puts the same cases through the experiment harness once per memory
mode (`MODES`):

    none      the agent is not offered recall at all
    keyword   recall_memories answered by shared words (SQL store)
    semantic  recall_memories answered by the Chroma index (NVIDIA
              embeddings), records read back from SQL

Every mode reads the same store, and none of them writes to it: the
comparison runs without an audit log, so nothing reaches the memory gate
and a run in one mode cannot hand a lesson to the next. Fill the store
first (ordinary `experiment run --memory --audit ...` runs on tuning seeds).

`report` prints one line per mode (causes right, resolved, tool calls,
searches, memories recalled and cited) and one line per case with each
mode beside the others. Root cause counts only where a label exists: label
the runs with `python -m capstone.experiment label` first. Every record's
run key holds its mode (`<name>/<mode>/<number>/<case>`).

Semantic mode with no index that opens is refused, not quietly run as
keyword search: the comparison would then report keyword twice.

Live runs need the model keys and DATABASE_URL; the tests run scripted
policies on a local SQLite store and never touch the network.
"""

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import mean

from capstone.agent.policy import ReasoningPolicy
from capstone.evaluation.labels import Label, LabelBook
from capstone.evaluation.scoring import Score
from capstone.experiment import (
    Case,
    ExperimentRecord,
    append_records,
    grid,
    held_out_cases,
    known_cases,
    labelled,
    read_records,
    run_experiment,
    seeds_from,
)
from capstone.memory.recall import MemoryRecall, RecallStore, SemanticIndex
from capstone.memory.service import MemoryService
from capstone.providers.recall import RECALL_TOOL
from capstone.simulator.generator import FAULTS

MODES: tuple[str, ...] = ("none", "keyword", "semantic")


def memory_for(
    mode: str, repository: RecallStore, index: SemanticIndex | None = None
) -> MemoryService | None:
    """The memory one mode's runs read. None for "none": no recall at all.

    Raises ValueError for semantic mode without an index, so it can never
    fall back to keyword search unseen.
    """
    if mode not in MODES:
        raise ValueError(f"unknown memory mode {mode!r}")
    if mode == "none":
        return None
    if mode == "semantic" and index is None:
        raise ValueError("semantic mode needs an index")
    return MemoryService(
        repository, recall=MemoryRecall(repository, mode=mode, index=index)
    )


def mode_of(record: ExperimentRecord) -> str:
    """The memory mode a comparison record ran in, from its run key."""
    return record.run_key.split("/")[1]


def compare_memory(
    cases: Sequence[Case],
    make_policy: Callable[[str], ReasoningPolicy],
    *,
    name: str,
    repository: RecallStore,
    index: SemanticIndex | None = None,
    modes: Sequence[str] = MODES,
    on_record: Callable[[ExperimentRecord], None] | None = None,
    **options,
) -> dict[str, list[ExperimentRecord]]:
    """Run every case once per mode, in the order given. Nothing is learned.

    `make_policy(mode)` returns a fresh policy for one run; it decides
    whether that policy is offered recall. Other options go to
    `run_experiment` (approver, budgets, hazards, clock).
    """
    if "/" in name:
        raise ValueError("a comparison name may not contain '/'")
    services = {mode: memory_for(mode, repository, index) for mode in modes}
    return {
        mode: run_experiment(
            cases,
            lambda mode=mode: make_policy(mode),
            name=f"{name}/{mode}",
            memory=services[mode],
            log=None,  # no audit log: nothing reaches the memory gate
            on_record=on_record,
            **options,
        )
        for mode in modes
    }


# --- the report -------------------------------------------------------------------


def _right(score: Score) -> bool | None:
    """Right cause and right machine or batch; None until judged."""
    if score.fault_correct is None:
        return None
    return bool(score.fault_correct and score.target_correct)


def searches(record: ExperimentRecord) -> int:
    return record.tools_used.count(RECALL_TOOL)


def mode_line(mode: str, records: Sequence[ExperimentRecord], scores) -> str:
    judged = [s for s in scores if _right(s) is not None]
    uses = [use for r in records for use in r.memory_uses or ()]
    calls = mean(s.tool_calls for s in scores) if scores else 0.0
    return (
        f"{mode:9} runs={len(records)} "
        f"cause_right={sum(_right(s) is True for s in judged)}/{len(judged)} judged "
        f"resolved={sum(s.resolved is True for s in scores)}/{len(scores)} "
        f"tool_calls={calls:.1f} on average "
        f"searches={sum(searches(r) for r in records)} "
        f"recalled={len(uses)} cited={sum(use.used is True for use in uses)}"
    )


def case_line(scenario_id: str, by_mode: Mapping[str, tuple]) -> str:
    cells = []
    for mode, (record, score) in by_mode.items():
        right = _right(score)
        cells.append(
            f"{mode}: cause={'-' if right is None else right!s} "
            f"calls={score.tool_calls} searches={searches(record)}"
        )
    return f"{scenario_id:24} " + " | ".join(cells)


def compare_report(
    records: Sequence[ExperimentRecord], labels: Mapping[str, Label]
) -> str:
    """One line per mode, then one line per case with the modes side by side.

    Says so when the modes did not run the same cases: then the totals are
    not a like-for-like comparison.
    """
    scores = labelled(records, dict(labels))
    by_mode: dict[str, list[tuple[ExperimentRecord, Score]]] = {}
    for record, score in zip(records, scores, strict=True):
        by_mode.setdefault(mode_of(record), []).append((record, score))
    lines = ["memory comparison (root cause counts only labelled runs):"]
    for mode, pairs in by_mode.items():
        lines.append(mode_line(mode, [r for r, _ in pairs], [s for _, s in pairs]))
    case_lists = {
        mode: [r.scenario_id for r, _ in pairs] for mode, pairs in by_mode.items()
    }
    if len({tuple(ids) for ids in case_lists.values()}) > 1:
        lines.append("WARNING: the modes did not run the same cases")
    lines.append("")
    first = next(iter(case_lists.values()), [])
    for number, scenario_id in enumerate(first):
        row = {
            mode: pairs[number]
            for mode, pairs in by_mode.items()
            if number < len(pairs) and pairs[number][0].scenario_id == scenario_id
        }
        lines.append(case_line(scenario_id, row))
    return "\n".join(lines)


# --- command line ---------------------------------------------------------------


def open_store_and_index(modes: Sequence[str]):
    """The configured SQL store, and the Chroma index if semantic mode is asked for.

    Exits with a message, never falls back, when the index cannot be opened.
    """
    from capstone.experiment import open_memory
    from capstone.settings import get_settings

    repository = open_memory().repository
    if "semantic" not in modes:
        return repository, None
    from capstone.memory import semantic

    try:
        index = semantic.open_configured_index(get_settings())
    except Exception as error:
        raise SystemExit(
            f"semantic mode needs the memory index ({type(error).__name__}); "
            "leave it out with --modes none,keyword"
        ) from None
    return repository, index


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m capstone.memory_comparison")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run the cases once per memory mode")
    run.add_argument("--name", required=True, help="unique, without '/'")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--known", action="store_true", help="the known-answer cases")
    which.add_argument("--seeds", help='seeds, "1-5" or "1,4,9"')
    which.add_argument("--held-out", action="store_true", help="the held-out seeds")
    run.add_argument("--modes", default=",".join(MODES), help="comma list of modes")
    run.add_argument("--out", type=Path, required=True)

    rep = commands.add_parser("report", help="the modes side by side")
    rep.add_argument("--results", type=Path, required=True)
    rep.add_argument("--labels", type=Path)

    args = parser.parse_args(argv)
    if args.command == "report":
        labels = LabelBook(args.labels).read() if args.labels else {}
        print(compare_report(read_records(args.results), labels))
        return 0

    modes = args.modes.split(",")
    unknown = [mode for mode in modes if mode not in MODES]
    if unknown:
        parser.error(f"unknown mode(s): {', '.join(unknown)}")
    if args.known:
        cases = known_cases()
    elif args.held_out:
        cases = held_out_cases()
    else:
        cases = grid(seeds_from(args.seeds), list(FAULTS))
    from capstone.experiment import model_policy_factory

    with_recall = model_policy_factory(with_recall=True)
    without = model_policy_factory(with_recall=False)
    repository, index = open_store_and_index(modes)
    results = compare_memory(
        cases,
        lambda mode: (without if mode == "none" else with_recall)(),
        name=args.name,
        repository=repository,
        index=index,
        modes=modes,
        on_record=lambda r: (
            append_records(args.out, [r]),
            print(f"{r.run_key}: {r.conclusion!r}"),
        ),
    )
    print(compare_report([r for rs in results.values() for r in rs], {}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
