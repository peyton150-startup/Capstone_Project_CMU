"""Run experiment cases while recording which project functions each one executes.

    uv run python -m evaltools.traced_run --config evals/scenarios.json \\
        --name master-x --out results.jsonl --audit audit.jsonl --trace trace.json

The same cases, policy and records as `python -m capstone.evals` (it calls
`capstone.experiment.run_experiment` one case at a time), with the run options
of `capstone.experiment run` (`--manual`/`--no-manual`, `--hazards`,
`--tree-of-thought`, `--timeout-seconds`) so it can match a master run's
configuration, under the coverage
tracer with one dynamic context per run key. Afterwards `trace.json` maps
each run key to the `capstone` functions that ran during it, by the ids the
function inventory uses, so implementation-level verification and the
end-to-end runs share one vocabulary.

`--scripted` runs the known-answer stand-in from the test suite instead of a
model, for an offline check of the tracer itself. It is never a measurement
of the agent.

Nothing in the run itself changes: coverage observes, it does not act.
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "capstone-code"))
sys.path.insert(0, str(REPO))


def function_spans(package: Path) -> dict[str, list[tuple[str, int, int]]]:
    """Per file: (function id, first line, last line), same ids as the inventory."""
    from evaltools.build_inventory import collect_functions

    spans: dict[str, list[tuple[str, int, int]]] = {}
    for path in sorted(package.rglob("*.py")):
        spans[str(path)] = [(f.id, f.line, f.end_line) for f in collect_functions(path)]
    return spans


def functions_hit(coverage_file: Path) -> dict[str, list[str]]:
    """Run key -> function ids executed under that context."""
    from coverage import CoverageData

    data = CoverageData(basename=str(coverage_file))
    data.read()
    spans = function_spans(REPO / "capstone-code" / "capstone")
    hit: dict[str, set[str]] = {}
    for measured in data.measured_files():
        if measured not in spans:
            continue
        by_line = data.contexts_by_lineno(measured)
        for function_id, first, last in spans[measured]:
            for line in range(first + 1, last + 1):
                for context in by_line.get(line, ()):
                    if context:
                        hit.setdefault(context, set()).add(function_id)
    return {key: sorted(ids) for key, ids in sorted(hit.items())}


def start_tracer(coverage_file: Path):
    """A coverage tracer over `capstone`, started before the package is imported."""
    import coverage

    cov = coverage.Coverage(
        data_file=str(coverage_file), source=["capstone"], branch=False
    )
    cov.erase()
    cov.start()
    return cov


def run_traced(cases, make_policy, *, name: str, cov, on_record=None, **options):
    """`run_experiment` one case at a time, each under its own coverage context."""
    from capstone.experiment import run_experiment

    records = []
    try:
        for number, case in enumerate(cases, start=1):
            cov.switch_context(f"{name}/{number}/{case.scenario_id}")
            records += run_experiment(
                [case],
                make_policy,
                name=name,
                start=number,
                on_record=on_record,
                **options,
            )
    finally:
        cov.stop()
        cov.save()
    return records


def main(argv=None) -> int:
    """Run the configured cases under the tracer and write records and the trace."""
    # Variables:
    #   args.manual: semantic or keyword search of the manual, or None
    #     (`--no-manual`); the same options and default as `capstone.experiment run`.
    #   args.hazards: False, standard or blackout, as `experiment run --hazards`.
    #   budgets: The per-investigation time limit when `--timeout-seconds` is
    #     given, split as `experiment run` splits it; None keeps the default.
    #   manual: The opened manual search, or None when not offered or scripted.
    parser = argparse.ArgumentParser(prog="python -m evaltools.traced_run")
    parser.add_argument(
        "--config", type=Path, default=REPO / "evals" / "scenarios.json"
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--out", type=Path, required=True, help="records JSONL")
    parser.add_argument("--audit", type=Path, help="audit log (recommended)")
    parser.add_argument("--trace", type=Path, required=True, help="function trace")
    parser.add_argument("--coverage-file", type=Path, default=Path(".coverage.trace"))
    parser.add_argument("--scripted", action="store_true", help="offline stand-in")
    # The run options of `capstone.experiment run`, so a traced run can be
    # configured like the master run it is meant to explain. Defined here, not
    # imported, so the tracer starts before any `capstone` module is loaded.
    manual = parser.add_mutually_exclusive_group()
    manual.add_argument(
        "--manual",
        nargs="?",
        const="semantic",
        default="semantic",
        choices=("semantic", "keyword"),
    )
    manual.add_argument("--no-manual", dest="manual", action="store_const", const=None)
    parser.add_argument(
        "--hazards",
        nargs="?",
        const="standard",
        default=False,
        choices=("standard", "blackout"),
    )
    parser.add_argument("--tree-of-thought", action="store_true")
    parser.add_argument("--timeout-seconds", type=float)
    args = parser.parse_args(argv)
    # Appending to an earlier file would give two records the same run key.
    for path in (args.out, args.audit):
        if path is not None and path.exists() and path.stat().st_size:
            parser.error(f"{path} already has records; choose a new file")

    cov = start_tracer(args.coverage_file)

    from capstone.agent.completion import AuditLog
    from capstone.agent.state import Budgets
    from capstone.evals import load_scenarios
    from capstone.experiment import append_records, model_policy_factory, open_manual

    config = load_scenarios(args.config)
    cases = [s.as_case() for s in config.cases]
    budgets = None
    if args.timeout_seconds is not None:
        budgets = Budgets(
            timeout_seconds=args.timeout_seconds,
            followup_seconds=args.timeout_seconds / 3,
        )
    if args.scripted:
        from tests.test_known_answers import stand_in

        make_policy = stand_in
        manual = None
    else:
        manual = None if args.manual is None else open_manual(args.manual)
        make_policy = model_policy_factory(
            False,
            tree_of_thought=args.tree_of_thought,
            with_manual=manual is not None,
        )

    def save(record) -> None:
        append_records(args.out, [record])
        print(f"completed {record.scenario_id}", flush=True)

    run_traced(
        cases,
        make_policy,
        name=args.name,
        cov=cov,
        on_record=save,
        log=AuditLog(args.audit) if args.audit else None,
        manual=manual,
        budgets=budgets,
        hazards=args.hazards,
    )
    trace = functions_hit(args.coverage_file)
    args.trace.write_text(json.dumps(trace, indent=1) + "\n", encoding="utf-8")
    print(f"{len(trace)} run(s) traced into {args.trace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
