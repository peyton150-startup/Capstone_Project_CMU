# Many episodes in a row, their records, their hand labels and the report.
# Responsibility: run seeded cases through the runner and total the results.
"""The experiment harness: the "18/20 root causes" report of MVP section 9.

    uv run python -m capstone.experiment run --name trial-1 --known --out results.jsonl
    uv run python -m capstone.experiment run --name trial-2 --known --hazards --out faults.jsonl
    uv run python -m capstone.experiment run --name tot-1 --known --tree-of-thought --out tot.jsonl
    uv run python -m capstone.experiment run --name report-1 --held-out --out held-out.jsonl
    uv run python -m capstone.experiment label --results results.jsonl --labels labels.jsonl --by me
    uv run python -m capstone.experiment report --results results.jsonl --labels labels.jsonl

`run` puts each case through `run_episode` with the model-backed policy
from settings (DEFAULT_MODEL and the per-question models) and appends one
`ExperimentRecord` per episode. Each record also says what the run's model
questions came to (`CallSummary`: invalid replies, which are the model's own
doing, apart from outages, which are the service's) and how long the
episode took on the wall clock. `label` shows each unlabelled conclusion and
asks a person which cause it names. `report` applies the labels and prints
the totals and one line per run.

With `--hazards` the agent's tools fail on a fixed schedule (timeouts,
rows missing from part of a range, one stale maintenance record; see
`capstone.providers.hazards`), and each record lists the faults that fired
and how many the agent followed with a successful call to the same tool.

With `--memory` each record also keeps what the memory gate did with the
run (`MemoryPromotionRecord`) and each memory the run recalled
(`MemoryUseRecord`), so `report` can say how many lessons were stored, how
many were recalled and cited, and how many came from a wrong diagnosis.

Numbers to report come from `--held-out` (`HELD_OUT_SEEDS`), seeds nothing
was tuned on; `report` says how many runs used them. See the rule beside
`HELD_OUT_SEEDS`.

A results file holds the hidden truth of every run (inside its `Score`). It
is for the experimenter: never give it to an agent, a prompt or memory.
"""

import argparse
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from pydantic import BaseModel, ConfigDict

from capstone.agent.completion import AuditLog, complete
from capstone.agent.model_policy import ModelCall
from capstone.agent.policy import ReasoningPolicy
from capstone.agent.state import Budgets
from capstone.benchmark import MODEL_OUTCOMES
from capstone.episode import (
    Approver,
    EpisodeResult,
    approve_all,
    ask_on_console,
    reject_all,
    run_episode,
)
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.evaluation.labels import Label, LabelBook, apply_label
from capstone.evaluation.memory import (
    MemoryPromotionRecord,
    MemoryUseRecord,
    RecallSearchRecord,
    build_promotion_record,
    build_search_records,
    build_use_records,
)
from capstone.evaluation.scoring import Score, format_summary, summarize
from capstone.memory.service import MemoryService
from capstone.simulator.generator import FAULTS
from capstone.tools.diagnosis import FAULT_KINDS, Diagnosis


@dataclass(frozen=True)
class Case:
    """One episode to run: a seed, the fault to force (None: the seed's own)."""

    scenario_id: str
    seed: int
    fault: str | None = None


def known_cases() -> list[Case]:
    return [Case(c.scenario_id, c.seed, c.fault) for c in KNOWN_CASES]


# The seeds reported numbers come from. Never tune anything on them: not a
# prompt, a budget, a threshold, or which cases to keep (dropping a hard seed
# is tuning too). Tune on seeds 0-999; the tests, the known cases, the
# benchmark and the rule baseline all use 0-60. A held-out failure is
# reproduced and fixed on a tuning seed, never checked here again. Once
# anything has been changed because of these seeds they are spent: they
# become tuning seeds and the next report needs a fresh range (record the
# switch in docs/PROGRESS.md). Memory used in a held-out run must have been
# learned on tuning seeds, or a lesson can name a held-out case's answer.
HELD_OUT_SEEDS: tuple[int, ...] = tuple(range(1000, 1010))


def held_out_cases() -> list[Case]:
    """Every fault on every held-out seed: the cases a reported number uses."""
    return grid(HELD_OUT_SEEDS, FAULTS)


def grid(seeds: Iterable[int], faults: Sequence[str | None]) -> list[Case]:
    """Every seed with every fault: a balanced experiment."""
    return [
        Case(f"seed-{seed}/{fault or 'any'}", seed, fault)
        for seed in seeds
        for fault in faults
    ]


class CallSummary(BaseModel):
    """What one run's model questions came to. Facts about the model service,
    not about the factory: no hidden truth in it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    questions: int
    answered: int
    # Replies that came back but could not be used: the model's own doing.
    invalid_replies: int
    invalid_by_job: dict[str, int]
    # Questions left with no answer for a service reason (outage, timeout, key).
    unanswered: int
    # Requests that failed for a service reason, retries included, even where
    # a retry or the fallback model then answered.
    outage_attempts: int
    # Why those requests failed, by reason ("the model service timed out",
    # "the model service answered HTTP 429", ...). Empty in older results.
    outage_reasons: dict[str, int] = {}
    # Which model answered how many questions: shows the fallback stepping in.
    answered_by: dict[str, int]
    # Ordered questions and their safe attempt outcomes. None in older files;
    # no prompts, response bodies or credentials are stored here.
    details: tuple[ModelCall, ...] | None = None


def summarize_calls(calls: Sequence[ModelCall]) -> CallSummary:
    answered = [call for call in calls if call.outcome == "answered"]
    invalid = Counter(call.job for call in calls if call.outcome == "invalid_reply")
    by_model = Counter(call.answered_by or "unknown" for call in answered)
    reasons = Counter(
        attempt.outcome
        for call in calls
        for attempt in call.attempts
        if attempt.outcome not in MODEL_OUTCOMES
    )
    return CallSummary(
        questions=len(calls),
        answered=len(answered),
        invalid_replies=sum(invalid.values()),
        invalid_by_job=dict(sorted(invalid.items())),
        # Any other outcome, including ones added later, is a missing answer.
        unanswered=len(calls) - len(answered) - sum(invalid.values()),
        outage_attempts=sum(
            attempt.outcome not in MODEL_OUTCOMES
            for call in calls
            for attempt in call.attempts
        ),
        outage_reasons=dict(sorted(reasons.items())),
        answered_by=dict(sorted(by_model.items())),
        details=tuple(calls),
    )


class ExperimentRecord(BaseModel):
    """One episode for the experimenter. Holds the truth: evaluator-side only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_key: str
    scenario_id: str
    seed: int
    anomaly: str
    conclusion: str | None
    confidence: float | None
    recommendation: str | None
    verification: str | None
    tools_used: list[str]
    score: Score
    # None: the policy keeps no record of model questions (a scripted one).
    model_calls: CallSummary | None = None
    # The whole episode on the wall clock, learning included (and, with a
    # console approver, the human's time). None in results from before it was kept.
    wall_seconds: float | None = None
    # With unreliable tools: the faults that fired, and how many timeouts or
    # gaps the agent followed with a successful call to the same tool.
    # None: the tools were reliable (and in results from before this was kept).
    hazards_fired: list[str] | None = None
    hazards_retried: int | None = None
    # What the memory gate did with this run's investigation, with whether the
    # diagnosis was right (from the truth, filled in after the gate decided).
    # None: nothing reached the gate (no memory, no audit log, or no lesson).
    memory_promotion: MemoryPromotionRecord | None = None
    # One per memory this run recalled. None: the run had no memory.
    memory_uses: list[MemoryUseRecord] | None = None
    # One per memory search the run made: asked, answered or refused, and
    # what came back. None: the run had no memory (or predates this record).
    recall_searches: list[RecallSearchRecord] | None = None


def memory_records(
    result: EpisodeResult,
) -> tuple[MemoryPromotionRecord | None, list[MemoryUseRecord]]:
    """The memory gate's decision and the memories recalled, for the experimenter.

    Built after the gate has decided and the run is scored, and kept only on
    the record: nothing here goes back to the agent, a prompt or memory.
    """
    state = result.state
    if state.conclusion is None or state.termination_reason is None:
        return None, []  # an unfinished investigation has no shared record
    investigation = complete(state)
    learning = result.learning
    promotion = None
    if learning is not None and learning.decision is not None:
        promotion = build_promotion_record(
            investigation,
            learning.decision,
            diagnosis_correct=result.score.fault_correct,
        )
    return promotion, list(build_use_records(investigation))


def record_of(
    case: Case,
    run_key: str,
    result: EpisodeResult,
    *,
    model_calls: CallSummary | None = None,
    wall_seconds: float | None = None,
    with_memory: bool = False,
) -> ExperimentRecord:
    state = result.state
    concluded = state.conclusion
    promotion, uses = memory_records(result) if with_memory else (None, None)
    return ExperimentRecord(
        run_key=run_key,
        scenario_id=case.scenario_id,
        seed=case.seed,
        anomaly=state.anomaly.description,
        conclusion=None if concluded is None else concluded.diagnosis,
        confidence=None if concluded is None else concluded.confidence,
        recommendation=None if concluded is None else concluded.recommendation,
        verification=None if state.verification is None else state.verification.outcome,
        tools_used=[d.tool for d in state.decisions if d.tool is not None],
        score=result.score,
        model_calls=model_calls,
        wall_seconds=wall_seconds,
        hazards_fired=None if result.hazards is None else result.hazards.fired,
        hazards_retried=None if result.hazards is None else result.hazards.retried,
        memory_promotion=promotion,
        memory_uses=uses,
        recall_searches=list(build_search_records(state)) if with_memory else None,
    )


def run_experiment(
    cases: Sequence[Case],
    make_policy: Callable[[], ReasoningPolicy],
    *,
    name: str,
    approver: Approver = approve_all,
    memory: MemoryService | None = None,
    log: AuditLog | None = None,
    budgets: Budgets | None = None,
    on_record: Callable[[ExperimentRecord], None] | None = None,
    clock: Callable[[], float] = monotonic,
    hazards: bool = False,
) -> list[ExperimentRecord]:
    """Run each case once with a fresh policy. `name` makes every run key unique.

    `clock` times each episode for the record only; the agent's own budgets
    run on `run_episode`'s clock.
    """
    records = []
    for number, case in enumerate(cases, start=1):
        run_key = f"{name}/{number}/{case.scenario_id}"
        policy = make_policy()
        started = clock()
        result = run_episode(
            case.seed,
            policy,
            fault=case.fault,
            approver=approver,
            memory=memory,
            log=log,
            budgets=budgets,
            run_key=run_key,
            hazards=hazards,
        )
        wall_seconds = clock() - started
        calls = getattr(policy, "calls", None)  # kept by ModelPolicy only
        record = record_of(
            case,
            run_key,
            result,
            model_calls=None if calls is None else summarize_calls(calls),
            wall_seconds=wall_seconds,
            with_memory=memory is not None,
        )
        records.append(record)
        if on_record is not None:
            on_record(record)
    return records


# --- files ---------------------------------------------------------------------


def append_records(path: Path, records: Iterable[ExperimentRecord]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(record.model_dump_json() + "\n")


def read_records(path: Path) -> list[ExperimentRecord]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ExperimentRecord.model_validate_json(line) for line in lines if line]


def labelled(
    records: Sequence[ExperimentRecord], labels: dict[str, Label]
) -> list[Score]:
    """Each run's score, with its root cause judged where a label exists."""
    return [
        apply_label(r.score, labels[r.run_key].diagnosis)
        if r.run_key in labels
        else r.score
        for r in records
    ]


def format_model_calls(records: Sequence[ExperimentRecord]) -> str:
    """One line on the model questions of every run, invalid apart from outage."""
    kept = [r.model_calls for r in records if r.model_calls is not None]
    timed = [r.wall_seconds for r in records if r.wall_seconds is not None]
    if not kept:
        line = "model questions: not recorded"
    else:
        line = (
            f"model questions: {sum(c.questions for c in kept)} "
            f"({sum(c.answered for c in kept)} answered, "
            f"{sum(c.invalid_replies for c in kept)} invalid replies, "
            f"{sum(c.unanswered for c in kept)} unanswered, "
            f"{sum(c.outage_attempts for c in kept)} failed attempts)"
        )
        reasons = Counter()
        for c in kept:
            reasons.update(c.outage_reasons)
        if reasons:
            line += "; failed because: " + ", ".join(
                f"{reason.removeprefix('the model service ')} {n}"
                for reason, n in reasons.most_common()
            )
    if timed:
        line += f"; {sum(timed) / len(timed):.0f} s per episode on average"
    return line


def _right(score: Score) -> bool | None:
    """Right cause and right machine or batch; None until judged."""
    if score.fault_correct is None:
        return None
    return bool(score.fault_correct and score.target_correct)


def format_memory(
    records: Sequence[ExperimentRecord], scores: Sequence[Score]
) -> str | None:
    """One line on what memory kept and what was recalled; None without memory.

    A lesson is traced to the run that made it only within these records, so
    a lesson stored by an earlier experiment counts as recalled but not judged.
    """
    if all(r.memory_uses is None for r in records):
        return None
    made_by: dict = {}  # stored memory id -> whether its run was right
    for record, score in zip(records, scores, strict=True):
        kept = record.memory_promotion
        if kept is not None and kept.stored and kept.memory_id is not None:
            made_by[kept.memory_id] = _right(score)
    stored = list(made_by.values())
    uses = [use for r in records for use in r.memory_uses or ()]
    return (
        f"memory: {len(stored)} lesson(s) stored ({stored.count(True)} from right "
        f"diagnoses, {stored.count(False)} from wrong, {stored.count(None)} not "
        f"judged); {len(uses)} recalled in {sum(bool(r.memory_uses) for r in records)}"
        f" run(s), {sum(use.used is True for use in uses)} cited by the agent; "
        f"{sum(made_by.get(use.memory_id) is False for use in uses)} recalled "
        "lesson(s) came from a wrong diagnosis"
    )


def _lesson(record: ExperimentRecord) -> str:
    kept = record.memory_promotion
    if kept is None:
        return "-"
    if kept.stored:
        return "stored"
    return "known" if kept.existing_memory_id is not None else "refused"


def _searches(record: ExperimentRecord) -> str:
    """Memory searches made and refused, where they were recorded."""
    found = record.recall_searches
    if found is None:
        return ""
    refused = sum(s.outcome in ("repeated", "budget_spent") for s in found)
    return f" searches={len(found)} refused={refused}"


def _run_line(record: ExperimentRecord, score: Score) -> str:
    judged = "-" if score.fault_correct is None else score.fault_correct
    calls = record.model_calls
    asked = (
        "questions=-"
        if calls is None
        else f"questions={calls.questions} invalid={calls.invalid_replies} "
        f"unanswered={calls.unanswered}"
    )
    seconds = "-" if record.wall_seconds is None else f"{record.wall_seconds:.0f}"
    faults = (
        ""
        if record.hazards_fired is None
        else f" faults={len(record.hazards_fired)} retried={record.hazards_retried}"
    )
    uses = record.memory_uses
    memory = (
        ""
        if uses is None
        else f" lesson={_lesson(record)} recalled={len(uses)} "
        f"cited={sum(use.used is True for use in uses)}{_searches(record)}"
    )
    several = len(score.causes) > 1
    causes = (
        f"causes={'-' if score.causes_found is None else score.causes_found}/"
        f"{len(score.causes)} fixed={score.causes_resolved}/{len(score.causes)} "
        if several
        else ""
    )
    return (
        f"{record.scenario_id:24} cause={judged!s:5} {causes}"
        f"asked={score.recommendation_correct!s:5} "
        f"extra={len(score.unnecessary_actions)} "
        f"acted={score.action_correct!s:5} resolved={score.resolved!s:5} "
        f"evidence={len(score.relevant_evidence_collected)}/"
        f"{len(score.relevant_evidence)} miss={score.miss_kind or '-'} "
        f"calls={score.tool_calls} "
        f"stop={score.termination_reason} {asked} s={seconds}{faults}{memory}"
    )


def format_call_failures(record: ExperimentRecord) -> list[str]:
    """Show unanswered questions and service failures, including recovered ones."""
    summary = record.model_calls
    if summary is None:
        return []
    if summary.details is None:
        return (
            ["  model failure details: not recorded in this results file"]
            if summary.unanswered or summary.outage_attempts
            else []
        )
    lines = []
    for number, call in enumerate(summary.details, start=1):
        if call.outcome != "no_answer" and not any(
            a.outcome not in MODEL_OUTCOMES for a in call.attempts
        ):
            continue
        lines.append(f"  question {number} {call.job}: {call.outcome}")
        for attempt in call.attempts:
            elapsed = "" if attempt.seconds is None else f" ({attempt.seconds:.3f} s)"
            lines.append(f"    {attempt.model}: {attempt.outcome}{elapsed}")
        if not call.attempts:
            lines.append("    no request attempt was recorded")
    return lines


def report(records: Sequence[ExperimentRecord], labels: dict[str, Label]) -> str:
    scores = labelled(records, labels)
    held = sum(r.seed in HELD_OUT_SEEDS for r in records)
    lines = [
        format_summary(summarize(scores)),
        format_model_calls(records),
        f"held-out seeds: {held}/{len(records)} runs",
    ]
    memory = format_memory(records, scores)
    lines += ([] if memory is None else [memory]) + [""]
    for record, score in zip(records, scores, strict=True):
        lines.append(_run_line(record, score))
        lines.extend(format_call_failures(record))
    return "\n".join(lines)


# --- labelling at the console ----------------------------------------------------


def ask_label(
    record: ExperimentRecord, ask: Callable[[str], str] | None = None
) -> Diagnosis | None | str:
    """Ask which cause a conclusion names. Returns "skip" to leave it unlabelled.

    The person sees the conclusion only, not the truth, so the label is a
    reading of the words, not a correction of them.
    """
    ask = ask or input
    print(f"\n{record.run_key}\n  conclusion: {record.conclusion!r}")
    choices = ", ".join(f"{n}={kind}" for n, kind in enumerate(FAULT_KINDS, start=1))
    answer = ask(f"  cause named? {choices}, 0=none recognisable, s=skip: ").strip()
    if answer.lower() == "s":
        return "skip"
    if answer == "0":
        return None
    fault = FAULT_KINDS[int(answer) - 1]
    if fault == "bad_material_batch":
        batch = ask("  batch number named (blank: none): ").strip()
        return Diagnosis(fault=fault, batch_id=int(batch) if batch else None)
    machine = ask("  machine named, e.g. CNC-02 (blank: none): ").strip()
    return Diagnosis(fault=fault, machine_id=machine or None)


# --- command line ------------------------------------------------------------------


def seeds_from(text: str) -> list[int]:
    """ "1-5" or "1,4,9"."""
    if "-" in text:
        low, high = text.split("-")
        return list(range(int(low), int(high) + 1))
    return [int(part) for part in text.split(",")]


def model_policy_factory(
    with_recall: bool, *, tree_of_thought: bool = False
) -> Callable[[], ReasoningPolicy]:
    """A fresh model-backed policy per run, from settings. Needs the API keys.

    With `tree_of_thought`, the hypothesize step branches, values and prunes
    (`capstone.agent.tree_of_thought`); everything else is the same policy.
    """
    from capstone.agent.model_policy import ModelPolicy
    from capstone.agent.tree_of_thought import TreeOfThoughtPolicy
    from capstone.providers.chat import clients_for_jobs
    from capstone.providers.factory import research_tools

    tools = research_tools()
    if with_recall:
        from capstone.providers.recall import RECALL_SPEC

        tools = (*tools, RECALL_SPEC)
    kind = TreeOfThoughtPolicy if tree_of_thought else ModelPolicy
    return lambda: kind(clients_for_jobs(), tools)


def open_memory() -> MemoryService:
    """The configured memory store (DATABASE_URL) with the configured recall."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    from capstone.memory.repository import SQLMemoryRepository
    from capstone.memory.service import build_memory_service
    from capstone.settings import get_settings

    settings = get_settings()
    if settings.database_url is None:
        raise SystemExit("--memory needs DATABASE_URL in the local .env or environment")
    url = make_url(settings.database_url.get_secret_value())
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    return build_memory_service(SQLMemoryRepository(create_engine(url)), settings)


APPROVERS = {"all": approve_all, "none": reject_all, "console": ask_on_console}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m capstone.experiment")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run episodes with the model policy")
    run.add_argument("--name", required=True, help="unique name for this execution")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--known", action="store_true", help="the known-answer cases")
    which.add_argument("--seeds", help='seeds, "1-5" or "1,4,9"')
    which.add_argument(
        "--held-out",
        action="store_true",
        help="every fault on the held-out seeds: for reported numbers only",
    )
    run.add_argument(
        "--faults", default="all", help='comma list, "all", or "any" (the seed\'s own)'
    )
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--approve", choices=sorted(APPROVERS), default="all")
    run.add_argument("--memory", action="store_true", help="recall and learn")
    run.add_argument("--audit", type=Path, help="audit log (needed to learn)")
    run.add_argument("--timeout-seconds", type=float, help="per investigation")
    run.add_argument(
        "--hazards",
        action="store_true",
        help="tools time out, drop rows and show a stale record on a fixed schedule",
    )
    run.add_argument(
        "--tree-of-thought",
        action="store_true",
        help="hypothesize by generating, valuing and pruning candidates (opt-in)",
    )

    label = commands.add_parser("label", help="label conclusions by hand")
    label.add_argument("--results", type=Path, required=True)
    label.add_argument("--labels", type=Path, required=True)
    label.add_argument("--by", required=True, help="who is labelling")

    rep = commands.add_parser("report", help="totals and one line per run")
    rep.add_argument("--results", type=Path, required=True)
    rep.add_argument("--labels", type=Path)

    args = parser.parse_args(argv)

    if args.command == "run":
        if args.known:
            cases = known_cases()
        elif args.held_out:
            cases = held_out_cases()
        else:
            if args.faults == "all":
                faults: list[str | None] = list(FAULTS)
            elif args.faults == "any":
                faults = [None]
            else:
                faults = args.faults.split(",")
            cases = grid(seeds_from(args.seeds), faults)
        budgets = None
        if args.timeout_seconds is not None:
            budgets = Budgets(
                timeout_seconds=args.timeout_seconds,
                followup_seconds=args.timeout_seconds / 3,
            )
        memory = open_memory() if args.memory else None
        log = AuditLog(args.audit) if args.audit else None

        def save_record(record: ExperimentRecord) -> None:
            append_records(args.out, [record])
            print(f"{record.scenario_id}: {record.conclusion!r}", flush=True)
            for line in format_call_failures(record):
                print(line, flush=True)

        records = run_experiment(
            cases,
            model_policy_factory(
                with_recall=memory is not None,
                tree_of_thought=args.tree_of_thought,
            ),
            name=args.name,
            approver=APPROVERS[args.approve],
            memory=memory,
            log=log,
            budgets=budgets,
            hazards=args.hazards,
            on_record=save_record,
        )
        print(report(records, {}))
        return 0

    records = read_records(args.results)
    if args.command == "label":
        book = LabelBook(args.labels)
        done = book.read()
        for record in records:
            if record.run_key in done or record.conclusion is None:
                continue
            answer = ask_label(record)
            if answer != "skip":
                book.add(
                    Label(run_key=record.run_key, diagnosis=answer, labelled_by=args.by)
                )
        return 0

    labels = LabelBook(args.labels).read() if args.labels else {}
    print(report(records, labels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
