# Checkpoint 8c: how each model behaves as the agent's policy, measured.
# Responsibility: run real episodes per model, one model alone, and report the numbers.
"""The provider benchmark: one row per model, from real episodes.

    python -m capstone.benchmark nvidia/nvidia/nemotron-3.5-lightning-30b-a3b \\
        cohere/command-a-03-2025 --seeds 0 2 6 --out docs/benchmarks

For each model, every job is given that model alone, with no fallback, so a
row describes one model: its outages end the episode as "model unavailable"
instead of being covered by another model, and its times are its own. Each
fault is run on each seed through `run_episode`, the same runner as any
other run. A real model may not answer identically twice, even at
temperature 0, which is why each fault gets several seeds.

Each model is asked under the same limits as a real run: the request,
question and retry settings (MODEL_REQUEST_SECONDS, MODEL_QUESTION_SECONDS,
MODEL_RETRIES) and the investigation budget (`--timeout-seconds`, default
`Budgets()`), so a row says how the model does in the agent as configured.

Read from each episode: the policy's `calls` (one per model question, each
attempt timed), the stop reason, the score and the wall-clock time. Written:
a markdown table (`format_table`), the limits the numbers suggest
(`suggested_limits`, `format_limits`), and the raw calls as JSON lines, one
per episode as soon as it ends, so any number can be checked again and a
stopped benchmark keeps what it measured. Nothing here changes the agent or
the simulator.
"""

import argparse
import math
import statistics
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from capstone.agent.model_policy import ModelCall, ModelPolicy
from capstone.agent.state import Budgets
from capstone.contracts import Contract
from capstone.episode import approve_all, run_episode
from capstone.providers.chat import (
    INVALID_REPLY,
    JOBS,
    FallbackClient,
    client_for,
    is_model_outcome,
)
from capstone.providers.factory import research_tools
from capstone.settings import Settings, get_settings
from capstone.simulator.generator import FAULTS

DEFAULT_SEEDS = (0, 2, 6)

# The attempt outcomes that are the model's own doing; anything else is an
# outage. An invalid reply also carries its reason ("invalid reply: ..."), so
# test with `is_model_outcome`, not membership here.
MODEL_OUTCOMES = ("answered", INVALID_REPLY)


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
    # The episode on the wall clock. None in records from before it was kept.
    wall_seconds: float | None = None


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
    # Episodes that ended with a diagnosis other than "undetermined".
    concluded: int = 0
    median_episode_seconds: float | None = None
    # Why requests failed, by reason, most common first.
    outage_reasons: dict[str, int] = {}
    # Why replies were refused (cut off, not JSON, wrong shape), most common first.
    invalid_reasons: dict[str, int] = {}


def single_model_clients(
    reference: str, settings: Settings | None = None, **client_options
) -> dict[str, FallbackClient]:
    """Every job given `reference` alone: no fallback model behind it, with
    the retries and the question limit from settings, as in a real run."""
    settings = settings or get_settings()
    client = client_for(reference, settings, **client_options)
    return {
        job: FallbackClient(
            [client],
            retries=settings.model_retries,
            max_seconds=settings.model_question_seconds,
        )
        for job in JOBS
    }


def run_model(
    model: str,
    policy_for: Callable[[], ModelPolicy],
    *,
    faults: Sequence[str] = FAULTS,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    wall_clock: Callable[[], float] = time.monotonic,
    on_record: Callable[[EpisodeRecord], None] | None = None,
    **episode_options,
) -> list[EpisodeRecord]:
    """Run every fault on every seed with a fresh policy from `policy_for`.

    `on_record` sees each record as soon as its episode ends.
    """
    records = []
    for fault in faults:
        for seed in seeds:
            policy = policy_for()
            started = wall_clock()
            result = run_episode(
                seed,
                policy,
                fault=fault,
                approver=approve_all,
                run_key=f"benchmark/{model}/{fault}/seed-{seed}",
                **episode_options,
            )
            reason = result.state.termination_reason
            record = EpisodeRecord(
                model=model,
                fault=fault,
                seed=seed,
                termination_reason=None if reason is None else str(reason),
                diagnosis=result.conclusion,
                action_correct=result.score.action_correct,
                resolved=result.score.resolved,
                calls=tuple(policy.calls),
                wall_seconds=round(wall_clock() - started, 1),
            )
            records.append(record)
            if on_record is not None:
                on_record(record)
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
        if is_model_outcome(a.outcome) and a.seconds is not None
    ]
    invalid = Counter(call.job for call in calls if call.outcome == "invalid_reply")
    reasons = Counter(record.termination_reason for record in records)
    failed = Counter(a.outcome for a in attempts if not is_model_outcome(a.outcome))
    refused = Counter(
        a.outcome.partition(": ")[2] or "reason not recorded"
        for a in attempts
        if a.outcome.split(":", 1)[0] == INVALID_REPLY
    )
    walls = [r.wall_seconds for r in records if r.wall_seconds is not None]
    episodes = len(records)
    median = statistics.median(answer_times) if answer_times else None
    return ModelReport(
        model=model,
        episodes=episodes,
        questions=len(calls),
        answered=sum(call.outcome == "answered" for call in calls),
        invalid_replies=sum(invalid.values()),
        invalid_by_job=dict(sorted(invalid.items())),
        outages=sum(not is_model_outcome(a.outcome) for a in attempts),
        median_seconds=median,
        p95_seconds=percentile(answer_times, 0.95),
        questions_per_episode=len(calls) / episodes if episodes else 0.0,
        model_unavailable=reasons["model_unavailable"],
        timeouts=reasons["timeout"],
        action_correct=sum(record.action_correct for record in records),
        resolved=sum(record.resolved for record in records),
        concluded=sum(r.diagnosis not in (None, "undetermined") for r in records),
        median_episode_seconds=statistics.median(walls) if walls else None,
        outage_reasons=dict(failed.most_common()),
        invalid_reasons=dict(refused.most_common()),
    )


class Limits(Contract):
    """Limits one model's numbers suggest; None where nothing was measured."""

    request_seconds: float | None
    question_seconds: float | None
    investigation_seconds: float | None


def suggested_limits(report: ModelReport) -> Limits:
    """From one model's numbers: a request may wait as long as the slowest 5%
    of its answers took; a question twice that (room for one retry or the
    fallback); an investigation its questions at the median time, twice
    over for the slow ones and the tool calls."""
    if report.p95_seconds is None or report.median_seconds is None:
        return Limits(
            request_seconds=None, question_seconds=None, investigation_seconds=None
        )
    request = math.ceil(report.p95_seconds)
    return Limits(
        request_seconds=request,
        question_seconds=2 * request,
        investigation_seconds=math.ceil(
            2 * report.questions_per_episode * report.median_seconds
        ),
    )


def seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def format_table(reports: Sequence[ModelReport]) -> str:
    """The benchmark as a markdown table, one row per model."""
    rows = [
        "| Model | Episodes | Valid answers | Invalid replies (by job) | Outages "
        "| Median s | Slowest-5% s | Questions / episode | Model unavailable "
        "| Timed out | Concluded | Right action | Resolved | Median episode s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        by_job = ", ".join(f"{job} {n}" for job, n in r.invalid_by_job.items())
        rows.append(
            f"| {r.model} | {r.episodes} | {r.answered}/{r.questions} "
            f"| {r.invalid_replies}{f' ({by_job})' if by_job else ''} | {r.outages} "
            f"| {seconds(r.median_seconds)} | {seconds(r.p95_seconds)} "
            f"| {r.questions_per_episode:.1f} | {r.model_unavailable} "
            f"| {r.timeouts} | {r.concluded}/{r.episodes} "
            f"| {r.action_correct}/{r.episodes} "
            f"| {r.resolved}/{r.episodes} | {seconds(r.median_episode_seconds)} |"
        )
    return "\n".join(rows)


def format_limits(reports: Sequence[ModelReport]) -> str:
    """The limits each model's numbers suggest, and why its requests failed."""
    lines = []
    for r in reports:
        limits = suggested_limits(r)
        why = ", ".join(
            f"{reason.removeprefix('the model service ')} {n}"
            for reason, n in r.outage_reasons.items()
        )
        refused = ", ".join(f"{reason} {n}" for reason, n in r.invalid_reasons.items())
        lines.append(
            f"- {r.model}: request {seconds(limits.request_seconds)} s, question "
            f"{seconds(limits.question_seconds)} s, investigation "
            f"{seconds(limits.investigation_seconds)} s; failed requests: "
            f"{why or 'none'}; invalid replies: {refused or 'none'}"
        )
    return "\n".join(lines)


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
    parser.add_argument(
        "--timeout-seconds", type=float, help="per investigation (default: Budgets)"
    )
    options = parser.parse_args(argv)
    options.out.mkdir(parents=True, exist_ok=True)
    budgets = None
    if options.timeout_seconds is not None:
        budgets = Budgets(
            timeout_seconds=options.timeout_seconds,
            followup_seconds=options.timeout_seconds / 3,
        )
    reports = []
    for model in options.models:
        clients = single_model_clients(model)
        records = run_model(
            model,
            lambda clients=clients: ModelPolicy(clients, research_tools()),
            faults=options.faults,
            seeds=options.seeds,
            budgets=budgets,
            on_record=lambda r: save_records(options.out / "calls.jsonl", [r]),
        )
        reports.append(summarize(model, records))
        print(format_table(reports[-1:]).splitlines()[-1], flush=True)
    text = f"{format_table(reports)}\n\nSuggested limits:\n{format_limits(reports)}\n"
    (options.out / "results.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
