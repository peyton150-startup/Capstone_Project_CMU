# Checkpoint 8c: how each model behaves as the agent's policy, measured.
# Responsibility: run real episodes per model, one model alone, and report the numbers.
"""The provider benchmark: one row per model, from real episodes.

    python -m capstone.benchmark nvidia/nvidia/nemotron-3.5-lightning-30b-a3b \\
        groq/<model> --seeds 0 2 6 --out docs/benchmarks

For each model, every job is given that model alone, with no fallback, so a
row describes one model: its outages end the episode as "model unavailable"
instead of being covered by another model, and its times are its own. Each
fault is run on each seed through `run_episode`, the same runner as any
other run. A real model may not answer identically twice, even at
temperature 0, which is why each fault gets several seeds.

Read from each episode: the policy's `calls` (one per model question, each
attempt timed), the stop reason, and the score. Written: a markdown table
(`format_table`) and the raw calls as JSON lines, so any number can be
checked again. Nothing here changes the agent or the simulator.

The numbers set the budgets: a question's limit from the slowest 5% of
answer times, an investigation's from questions per episode times that.
"""

import argparse
import math
import statistics
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from capstone.agent.model_policy import ModelCall, ModelPolicy
from capstone.contracts import Contract
from capstone.episode import approve_all, run_episode
from capstone.providers.chat import JOBS, FallbackClient, client_for
from capstone.providers.factory import research_tools
from capstone.settings import Settings
from capstone.simulator.generator import FAULTS

DEFAULT_SEEDS = (0, 2, 6)

# The attempt outcomes that are the model's own doing; anything else is an outage.
MODEL_OUTCOMES = ("answered", "invalid reply")


class EpisodeRecord(Contract):
    """What one benchmark episode showed about the model, for the raw log."""

    model: str
    fault: str
    seed: int
    termination_reason: str | None
    diagnosis: str | None
    action_correct: bool
    resolved: bool
    calls: tuple[ModelCall, ...]


class ModelReport(Contract):
    """One row of the benchmark table."""

    model: str
    episodes: int
    questions: int
    answered: int
    invalid_replies: int
    invalid_by_job: dict[str, int]
    outages: int
    median_seconds: float | None
    p95_seconds: float | None
    questions_per_episode: float
    model_unavailable: int
    timeouts: int
    action_correct: int
    resolved: int


def single_model_clients(
    reference: str, settings: Settings | None = None, **client_options
) -> dict[str, FallbackClient]:
    """Every job given `reference` alone: no fallback model behind it."""
    client = client_for(reference, settings, **client_options)
    return {job: FallbackClient([client]) for job in JOBS}


def run_model(
    model: str,
    policy_for: Callable[[], ModelPolicy],
    *,
    faults: Sequence[str] = FAULTS,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    **episode_options,
) -> list[EpisodeRecord]:
    """Run every fault on every seed with a fresh policy from `policy_for`."""
    records = []
    for fault in faults:
        for seed in seeds:
            policy = policy_for()
            result = run_episode(
                seed,
                policy,
                fault=fault,
                approver=approve_all,
                run_key=f"benchmark/{model}/{fault}/seed-{seed}",
                **episode_options,
            )
            reason = result.state.termination_reason
            records.append(
                EpisodeRecord(
                    model=model,
                    fault=fault,
                    seed=seed,
                    termination_reason=None if reason is None else str(reason),
                    diagnosis=result.conclusion,
                    action_correct=result.score.action_correct,
                    resolved=result.score.resolved,
                    calls=tuple(policy.calls),
                )
            )
    return records


def percentile(values: Sequence[float], share: float) -> float | None:
    """The nearest-rank percentile: the smallest value with `share` at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def summarize(model: str, records: Sequence[EpisodeRecord]) -> ModelReport:
    calls = [call for record in records for call in record.calls]
    attempts = [attempt for call in calls for attempt in call.attempts]
    answer_times = [
        a.seconds
        for a in attempts
        if a.outcome in MODEL_OUTCOMES and a.seconds is not None
    ]
    invalid = Counter(call.job for call in calls if call.outcome == "invalid_reply")
    reasons = Counter(record.termination_reason for record in records)
    episodes = len(records)
    median = statistics.median(answer_times) if answer_times else None
    return ModelReport(
        model=model,
        episodes=episodes,
        questions=len(calls),
        answered=sum(call.outcome == "answered" for call in calls),
        invalid_replies=sum(invalid.values()),
        invalid_by_job=dict(sorted(invalid.items())),
        outages=sum(a.outcome not in MODEL_OUTCOMES for a in attempts),
        median_seconds=median,
        p95_seconds=percentile(answer_times, 0.95),
        questions_per_episode=len(calls) / episodes if episodes else 0.0,
        model_unavailable=reasons["model_unavailable"],
        timeouts=reasons["timeout"],
        action_correct=sum(record.action_correct for record in records),
        resolved=sum(record.resolved for record in records),
    )


def seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def format_table(reports: Sequence[ModelReport]) -> str:
    """The benchmark as a markdown table, one row per model."""
    rows = [
        "| Model | Episodes | Valid answers | Invalid replies (by job) | Outages "
        "| Median s | Slowest-5% s | Questions / episode | Model unavailable "
        "| Timed out | Right action | Resolved |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        by_job = ", ".join(f"{job} {n}" for job, n in r.invalid_by_job.items())
        rows.append(
            f"| {r.model} | {r.episodes} | {r.answered}/{r.questions} "
            f"| {r.invalid_replies}{f' ({by_job})' if by_job else ''} | {r.outages} "
            f"| {seconds(r.median_seconds)} | {seconds(r.p95_seconds)} "
            f"| {r.questions_per_episode:.1f} | {r.model_unavailable} "
            f"| {r.timeouts} | {r.action_correct}/{r.episodes} "
            f"| {r.resolved}/{r.episodes} |"
        )
    return "\n".join(rows)


def save_records(path: Path, records: Sequence[EpisodeRecord]) -> None:
    with path.open("a", encoding="utf-8") as out:
        for record in records:
            out.write(record.model_dump_json() + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m capstone.benchmark")
    parser.add_argument("models", nargs="+", help="provider/model, one or more")
    parser.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS))
    parser.add_argument("--faults", nargs="+", choices=FAULTS, default=list(FAULTS))
    parser.add_argument("--out", type=Path, default=Path("docs/benchmarks"))
    options = parser.parse_args(argv)
    options.out.mkdir(parents=True, exist_ok=True)
    reports = []
    for model in options.models:
        clients = single_model_clients(model)
        records = run_model(
            model,
            lambda clients=clients: ModelPolicy(clients, research_tools()),
            faults=options.faults,
            seeds=options.seeds,
        )
        save_records(options.out / "calls.jsonl", records)
        reports.append(summarize(model, records))
        print(format_table(reports[-1:]).splitlines()[-1], flush=True)
    table = format_table(reports)
    (options.out / "results.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
