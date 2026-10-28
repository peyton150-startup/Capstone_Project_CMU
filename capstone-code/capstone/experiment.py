# Many episodes in a row, their records, their hand labels and the report.
# Responsibility: run seeded cases through the runner and total the results.
"""The experiment harness: the "18/20 root causes" report of MVP section 9.

    uv run python -m capstone.experiment run --name trial-1 --known --out results.jsonl
    uv run python -m capstone.experiment run --name trial-2 --known --hazards --out faults.jsonl
    uv run python -m capstone.experiment run --name tot-1 --known --tree-of-thought --out tot.jsonl
    uv run python -m capstone.experiment run --name report-1 --held-out --out held-out.jsonl
    uv run python -m capstone.experiment run --name hard-1 --challenge 1-5 --out hard.jsonl
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

With `--challenge` each seed builds the compound challenge
(`simulator/challenge.py`: a worn bearing and a wrong speed setting on one
machine, three distractors elsewhere) instead of a one-fault line; the
known-answer cases include one such case. `report` totals and lists runs
with one fault and runs with several faults apart.

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

from pydantic import BaseModel, ConfigDict, Field

from capstone.agent.completion import AuditLog, complete
from capstone.agent.critic import Critic, CritiqueRecord
from capstone.agent.model_policy import ModelCall
from capstone.agent.policy import ReasoningPolicy
from capstone.agent.state import Budgets
from capstone.agent.tree_of_thought import Thought
from capstone.console import safe_console
from capstone.episode import (
    CHALLENGE,
    STANDARD,
    Approver,
    EpisodeResult,
    approve_all,
    ask_on_console,
    reject_all,
    run_episode,
)
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.evaluation.labels import Label, LabelBook, apply_label
from capstone.evaluation.manual import ManualSearchRecord, build_manual_records
from capstone.evaluation.memory import (
    MemoryPromotionRecord,
    MemoryUseRecord,
    RecallSearchRecord,
    build_promotion_record,
    build_search_records,
    build_use_records,
)
from capstone.evaluation.scoring import COMPOUND, Score, format_summary, summarize
from capstone.memory.service import MemoryService
from capstone.progress import ProgressView
from capstone.providers.chat import INVALID_REPLY, is_model_outcome
from capstone.providers.manual import MANUAL_TOOL, ManualSearch
from capstone.providers.recall import RECALL_TOOL
from capstone.simulator.generator import FAULTS
from capstone.tools.diagnosis import FAULT_KINDS, Diagnosis


@dataclass(frozen=True)
class Case:
    """One episode to run: a seed, the fault to force (None: the seed's own),
    and the kind of factory (`capstone.episode.SCENARIO_KINDS`)."""

    scenario_id: str
    seed: int
    fault: str | None = None
    kind: str = STANDARD


def known_cases() -> list[Case]:
    return [Case(c.scenario_id, c.seed, c.fault, c.kind) for c in KNOWN_CASES]


def challenge_cases(seeds: Iterable[int]) -> list[Case]:
    """The compound challenge on each seed."""
    return [Case(f"seed-{seed}/challenge", seed, None, CHALLENGE) for seed in seeds]


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
    # Variables:
    #   seeds: The seeds to run.
    #   faults: The faults to force; None for a case lets the seed choose.
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
    # Why replies were refused, by reason ("cut off at the output-token limit",
    # "not valid JSON", "wrong shape: <field>: ..."). Empty in older results.
    invalid_reasons: dict[str, int] = {}
    # Which model answered how many questions: shows the fallback stepping in.
    answered_by: dict[str, int]
    # Ordered questions and their safe attempt outcomes. None in older files;
    # no prompts, response bodies or credentials are stored here.
    details: tuple[ModelCall, ...] | None = None


class AgentStep(BaseModel):
    """A model question or loop decision attributed to its producing agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    agent: str
    kind: str
    phase: str
    outcome: str
    tool: str | None = None


def summarize_calls(calls: Sequence[ModelCall]) -> CallSummary:
    # Variables:
    #   calls: Every model question the run asked, with how each ended.
    #   answered: The questions a model answered.
    #   invalid: Count of unusable replies, by which question.
    #   by_model: Count of answers, by which model gave them; shows the fallback
    #     stepping in.
    #   reasons: Why requests failed for a service reason, such as a timeout or HTTP
    #     429.
    #   refused: Why replies were refused, such as cut off or not JSON.
    answered = [call for call in calls if call.outcome == "answered"]
    invalid = Counter(call.job for call in calls if call.outcome == "invalid_reply")
    by_model = Counter(call.answered_by or "unknown" for call in answered)
    reasons = Counter(
        attempt.outcome
        for call in calls
        for attempt in call.attempts
        if not is_model_outcome(attempt.outcome)
    )
    refused = Counter(
        attempt.outcome.partition(": ")[2] or "reason not recorded"
        for call in calls
        for attempt in call.attempts
        if attempt.outcome.split(":", 1)[0] == INVALID_REPLY
    )
    return CallSummary(
        questions=len(calls),
        answered=len(answered),
        invalid_replies=sum(invalid.values()),
        invalid_by_job=dict(sorted(invalid.items())),
        # Any other outcome, including ones added later, is a missing answer.
        unanswered=len(calls) - len(answered) - sum(invalid.values()),
        outage_attempts=sum(
            not is_model_outcome(attempt.outcome)
            for call in calls
            for attempt in call.attempts
        ),
        outage_reasons=dict(sorted(reasons.items())),
        invalid_reasons=dict(sorted(refused.items())),
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
    # The policy's own recommendation before the check, and why an
    # intervention was lowered to escalate. None in older results.
    policy_recommendation: str | None = None
    recommendation_lowered: str | None = None
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
    # One per machine-manual search: asked, answered or refused, and which
    # sections came back. None: the run had no manual (or predates this record).
    manual_searches: list[ManualSearchRecord] | None = None
    # The counted tool calls that went to the factory: `score.tool_calls`
    # without memory and manual searches. None in results from before it was kept.
    factory_calls: int | None = None
    # Unknown in older results; this controls prompt visibility, not enforcement.
    state_action_bar: bool | None = None
    # None in records made before this setting was introduced.
    step_questions: int | None = Field(default=None, ge=1, le=2)
    # None in older records; specialists can identify themselves on each step.
    agent_steps: list[AgentStep] | None = None
    # What the critic said about the two leading hypotheses, or why it said
    # nothing. None: no critic ran (and in records from before it was kept).
    critique: CritiqueRecord | None = None
    # The claim of the hypothesis the critic favoured, so it can be labelled
    # as a cause the way a conclusion is. None: no pick (or an older record).
    critic_favoured_claim: str | None = None
    # With --tree-of-thought: one tree per hypothesize step, in order (the
    # candidates, their ratings, which were kept and why the rest were dropped).
    # None: the run used the ordinary step (or predates this record).
    thoughts: list[Thought] | None = None


# Tools answered by something other than the factory.
NOT_FACTORY = frozenset({RECALL_TOOL, MANUAL_TOOL})


def count_factory_calls(state) -> int:
    """Counted calls to the factory's own tools.

    A call the loop skipped as a repeat is not counted (it never reached a
    provider, as in `tool_calls`); a call the factory refused or failed is.
    """
    return sum(
        d.tool is not None
        and d.tool not in NOT_FACTORY
        and d.outcome != "repeated_call"
        for d in state.decisions
    )


def memory_records(
    result: EpisodeResult,
) -> tuple[MemoryPromotionRecord | None, list[MemoryUseRecord]]:
    """The memory gate's decision and the memories recalled, for the experimenter.

    Built after the gate has decided and the run is scored, and kept only on
    the record: nothing here goes back to the agent, a prompt or memory.
    """
    # Variables:
    #   result: The finished episode.
    #   state: The agent's final working memory.
    #   investigation: The shared record of the finished investigation.
    #   learning: What the memory gate decided, if memory was used.
    #   promotion: The gate's decision with whether the diagnosis was right, for the
    #     experimenter only.
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


def overruled_text(record: ExperimentRecord) -> str:
    """For the report: an intervention the check lowered, and why; else nothing."""
    if record.recommendation_lowered is None:
        return ""
    return f" overruled=intervene->{record.recommendation} ({record.recommendation_lowered})"


def favoured_claim(state) -> str | None:
    """The claim the critic favoured, as worded when it judged it; None if none.

    Read from the critique record, never from the final hypotheses: the agent
    keeps rewording them after the critique, even with what the fix showed.
    """
    # Variables:
    #   state: The finished investigation, which holds the critique record.
    return None if state.critique is None else state.critique.favoured_claim


def record_of(
    case: Case,
    run_key: str,
    result: EpisodeResult,
    *,
    model_calls: CallSummary | None = None,
    wall_seconds: float | None = None,
    with_memory: bool = False,
    with_manual: bool = False,
    thoughts: Sequence[Thought] | None = None,
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
        policy_recommendation=state.policy_recommendation,
        recommendation_lowered=state.recommendation_lowered,
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
        manual_searches=list(build_manual_records(state)) if with_manual else None,
        factory_calls=count_factory_calls(state),
        state_action_bar=state.state_action_bar,
        step_questions=state.step_questions,
        critique=state.critique,
        critic_favoured_claim=favoured_claim(state),
        agent_steps=[
            AgentStep(
                agent=decision.agent,
                kind="decision",
                phase=decision.phase,
                outcome=decision.outcome,
                tool=decision.tool,
            )
            for decision in state.decisions
        ]
        + [
            AgentStep(
                agent=call.agent,
                kind="model_question",
                phase=call.job,
                outcome=call.outcome,
            )
            for call in (
                ()
                if model_calls is None or model_calls.details is None
                else model_calls.details
            )
        ],
        thoughts=None if thoughts is None else list(thoughts),
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
    manual: ManualSearch | None = None,
    start: int = 1,
    watch: Callable[[str], None] | None = None,
    make_critic: Callable[[], Critic] | None = None,
) -> list[ExperimentRecord]:
    """Run each case once with a fresh policy. `name` makes every run key unique.

    `clock` times each episode for the record only; the agent's own budgets
    run on `run_episode`'s clock. `start` is the first case's number in the
    run keys, for a caller that runs one long list a case at a time.

    With `watch`, each case is followed live: a header, then the progress
    view's lines (`capstone.progress.ProgressView`) as the agent works. The
    truth is not printed: conclusions are labelled by hand afterwards, and
    seeing the answer first would bias the labels. It stays in the record.

    With `make_critic`, each case gets a fresh critic; without it, the
    episode builds one from settings when CRITIC is on. The critic's
    questions are counted after the policy's, tagged agent="critic".
    """
    # Variables:
    #   cases: The seeds and faults to run, one episode each.
    #   make_policy: Builds a fresh decision-maker for each case.
    #   name: Starts every run key, so two experiments never share one.
    #   on_record: Called with each finished record, so results can be saved as they
    #     come.
    #   start: The number of the first case in the run keys.
    #   watch: Prints a live view of each case; the hidden truth is never printed.
    #   make_critic: Builds a fresh critic for each case; None leaves it to settings.
    #   records: One record per case, in order.
    #   run_key: A unique name for this case's run.
    #   policy: A fresh decision-maker, so no case learns from another's state.
    #   started: The clock reading when the case began.
    #   result: The finished episode, including the simulator and its hidden truth.
    #   wall_seconds: How long the episode took on the wall clock.
    #   calls: The model questions asked; only model-backed policies keep them,
    #     followed by the critic's, if one ran.
    #   calls: The model questions asked; only model-backed policies keep them.
    #   thoughts: The tree-of-thought trees; only the tree policy keeps them.
    #   record: The case's result for the experimenter.
    records = []
    for number, case in enumerate(cases, start=start):
        run_key = f"{name}/{number}/{case.scenario_id}"
        policy = make_policy()
        if watch is not None:
            watch(f"=== case {number}: {case.scenario_id} ===")
        started = clock()
        result = run_episode(
            case.seed,
            policy,
            kind=case.kind,
            fault=case.fault,
            approver=approver,
            memory=memory,
            log=log,
            budgets=budgets,
            run_key=run_key,
            hazards=hazards,
            manual=manual,
            watch=None if watch is None else ProgressView(watch),
            critic=None if make_critic is None else make_critic(),
        )
        wall_seconds = clock() - started
        calls = getattr(policy, "calls", None)  # kept by ModelPolicy only
        thoughts = getattr(policy, "thoughts", None)  # kept by TreeOfThoughtPolicy only
        if result.critic_calls:
            calls = [*(calls or ()), *result.critic_calls]
        record = record_of(
            case,
            run_key,
            result,
            model_calls=None if calls is None else summarize_calls(calls),
            wall_seconds=wall_seconds,
            with_memory=memory is not None,
            with_manual=manual is not None,
            thoughts=thoughts,
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
    # Variables:
    #   kept: The model-question summaries of the runs that have one.
    #   timed: Wall-clock seconds of the runs that were timed.
    #   reasons: Why requests failed, added up across runs.
    #   refused: Why replies were refused, added up across runs.
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
        refused = Counter()
        for c in kept:
            refused.update(c.invalid_reasons)
        if refused:
            line += "; invalid because: " + ", ".join(
                f"{reason} {n}" for reason, n in refused.most_common()
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
    # Variables:
    #   made_by: For each lesson stored in these runs, whether its run's diagnosis was
    #     right.
    #   stored: Those results as a list, to count right, wrong and not judged.
    #   uses: Every memory any run recalled.
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


def format_manual(records: Sequence[ExperimentRecord]) -> str | None:
    """One line on what the runs looked up in the manual; None without it."""
    # Variables:
    #   kept: The manual searches of each run that had the manual.
    #   searches: All those searches together.
    #   given: How often each manual section was returned.
    #   refused: Searches turned down as repeats or over the allowance.
    #   most: The five sections returned most often.
    kept = [r.manual_searches for r in records if r.manual_searches is not None]
    if not kept:
        return None
    searches = [s for found in kept for s in found]
    given = Counter(section for s in searches for section in s.sections)
    refused = sum(s.outcome in ("repeated", "budget_spent") for s in searches)
    most = ", ".join(f"{section} {n}" for section, n in given.most_common(5))
    return (
        f"manual: {len(searches)} search(es) in {sum(bool(f) for f in kept)} of "
        f"{len(kept)} run(s), {refused} refused; sections given: {most or 'none'}"
    )


def _searches(record: ExperimentRecord) -> str:
    """Memory searches made and refused, where they were recorded."""
    found = record.recall_searches
    if found is None:
        return ""
    refused = sum(s.outcome in ("repeated", "budget_spent") for s in found)
    return f" searches={len(found)} refused={refused}"


def _run_line(record: ExperimentRecord, score: Score) -> str:
    # Variables:
    #   judged: Whether the cause was right; a dash if not judged.
    #   asked: The model-question counts for this run.
    #   several: True if the run had more than one true cause.
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
    looked = record.manual_searches
    manual = (
        ""
        if looked is None
        else " manual="
        + (",".join(sec for s in looked for sec in s.sections[:1]) or "none")
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
        f"{manual}{overruled_text(record)}"
    )


def several_faults(score: Score) -> bool:
    """A run with several true faults (the compound challenge)."""
    return score.true_fault == COMPOUND


def format_call_failures(record: ExperimentRecord) -> list[str]:
    """Show unanswered questions and service failures, including recovered ones."""
    # Variables:
    #   summary: The run's model-question summary.
    #   lines: The report lines, one per failed or recovered question.
    #   elapsed: How long an attempt took, if it was timed.
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
            not is_model_outcome(a.outcome) for a in call.attempts
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
    """Totals, then one line per run. When runs with one fault and runs with
    several are mixed, each group is also totalled and listed on its own, so
    a hard case does not hide inside the one-fault numbers."""
    # Variables:
    #   records: Every run to report on.
    #   labels: Hand labels that say which cause each conclusion names.
    #   scores: Each run's score, with its cause judged where a label exists.
    #   held: How many runs used the held-out seeds.
    #   pairs: Each record with its score.
    #   one: Runs with a single true fault.
    #   many: Runs with several true faults.
    #   mixed: True if both kinds are present, so each is also totalled on its own.
    #   lines: The report, built line by line.
    #   memory: The memory section, if any run used memory.
    #   manual: The manual section, if any run used the manual.
    scores = labelled(records, labels)
    held = sum(r.seed in HELD_OUT_SEEDS for r in records)
    pairs = list(zip(records, scores, strict=True))
    one = [(r, s) for r, s in pairs if not several_faults(s)]
    many = [(r, s) for r, s in pairs if several_faults(s)]
    mixed = bool(one and many)
    lines = [format_summary(summarize(scores))]
    if mixed:
        lines += [
            "one fault: " + format_summary(summarize([s for _, s in one])),
            "several faults: " + format_summary(summarize([s for _, s in many])),
        ]
    lines += [
        format_model_calls(records),
        f"held-out seeds: {held}/{len(records)} runs",
    ]
    memory = format_memory(records, scores)
    lines += [] if memory is None else [memory]
    manual = format_manual(records)
    lines += ([] if manual is None else [manual]) + [""]

    def lines_for(group):
        # Variables:
        #   out: The lines for one group of runs.
        out = []
        for record, score in group:
            out.append(_run_line(record, score))
            out.extend(format_call_failures(record))
        return out

    if mixed:
        lines += ["runs with one fault:", *lines_for(one)]
        lines += ["", "runs with several faults:", *lines_for(many)]
    else:
        lines += lines_for(pairs)
    return "\n".join(lines)


# --- labelling at the console ----------------------------------------------------


def ask_label(
    record: ExperimentRecord, ask: Callable[[str], str] | None = None
) -> Diagnosis | None | str:
    """Ask which cause a conclusion names. Returns "skip" to leave it unlabelled.

    The person sees the conclusion only, not the truth, so the label is a
    reading of the words, not a correction of them.
    """
    # Variables:
    #   record: The run whose conclusion is being labelled.
    #   ask: How to ask the person; input by default, replaced in tests.
    #   choices: The numbered list of fault kinds shown to the person.
    #   allowed: The answers that count: a choice number, 0 for none, or s to skip.
    #   answer: The person's latest answer, asked again until it is allowed.
    #   fault: The fault kind the person picked.
    #   batch: The batch number the person named, if the fault is a bad batch.
    #   machine: The machine the person named.
    ask = ask or input
    print(f"\n{record.run_key}\n  conclusion: {record.conclusion!r}")
    choices = ", ".join(f"{n}={kind}" for n, kind in enumerate(FAULT_KINDS, start=1))
    allowed = {str(n) for n in range(len(FAULT_KINDS) + 1)} | {"s"}
    # An answer that is not one of the choices (an empty Enter, a typo) is
    # asked again, never read as a label or allowed to stop the command.
    answer = ""
    while answer not in allowed:
        answer = ask(f"  cause named? {choices}, 0=none recognisable, s=skip: ")
        answer = answer.strip().lower()
    if answer == "s":
        return "skip"
    if answer == "0":
        return None
    fault = FAULT_KINDS[int(answer) - 1]
    if fault == "bad_material_batch":
        while True:
            batch = ask("  batch number named (blank: none): ").strip()
            if not batch or batch.isdigit():
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
    with_recall: bool, *, tree_of_thought: bool = False, with_manual: bool = False
) -> Callable[[], ReasoningPolicy]:
    """A fresh model-backed policy per run, from settings. Needs the API keys.

    With `tree_of_thought`, the hypothesize step branches, values and prunes
    (`capstone.agent.tree_of_thought`); everything else is the same policy.
    """
    # Variables:
    #   with_recall: Offer the memory search tool.
    #   tree_of_thought: Use the policy that generates, rates and prunes explanations.
    #   with_manual: Offer the manual search tool.
    #   tools: The tools the policy may choose from.
    #   kind: Which policy class to build.
    from capstone.agent.model_policy import ModelPolicy
    from capstone.agent.tree_of_thought import TreeOfThoughtPolicy
    from capstone.providers.chat import clients_for_jobs
    from capstone.providers.factory import research_tools

    tools = research_tools()
    if with_recall:
        from capstone.providers.recall import RECALL_SPEC

        tools = (*tools, RECALL_SPEC)
    if with_manual:
        from capstone.providers.manual import MANUAL_SPEC

        tools = (*tools, MANUAL_SPEC)
    kind = TreeOfThoughtPolicy if tree_of_thought else ModelPolicy
    return lambda: kind(clients_for_jobs(), tools)


def open_manual(mode: str) -> ManualSearch:
    """The machine manual, searched by meaning ("semantic": the Chroma index built
    by `python -m capstone.manual.index`) or by shared words ("keyword")."""
    # Variables:
    #   mode: semantic searches by meaning, keyword by shared words.
    #   sections: The manual's checked sections.
    #   index: The built semantic index; an empty one stops the run with a hint to build
    #     it.
    from capstone.manual.index import (
        REBUILD_HINT,
        KeywordManualSearch,
        open_manual_index,
    )
    from capstone.manual.sections import load_manual
    from capstone.settings import get_settings

    sections = load_manual()
    if mode == "keyword":
        return KeywordManualSearch(sections)
    index = open_manual_index(get_settings(), sections=sections)
    if index.collection.count() == 0:
        raise SystemExit(f"the manual index is empty; build it first: {REBUILD_HINT}")
    return index


def open_memory() -> MemoryService:
    """The configured memory store (DATABASE_URL) with the configured recall."""
    # Variables:
    #   settings: The project settings, read for DATABASE_URL.
    #   url: The database address, with the driver set to psycopg for PostgreSQL.
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
    safe_console()  # a conclusion with "→" must not stop the run
    parser = argparse.ArgumentParser(prog="python -m capstone.experiment")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run episodes with the model policy")
    run.add_argument("--name", required=True, help="unique name for this execution")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--known", action="store_true", help="the known-answer cases")
    which.add_argument("--seeds", help='seeds, "1-5" or "1,4,9"')
    which.add_argument(
        "--challenge",
        metavar="SEEDS",
        help='the compound challenge (several faults) on seeds "1-5" or "1,4,9"',
    )
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
    run.add_argument(
        "--manual",
        nargs="?",
        const="semantic",
        choices=("semantic", "keyword"),
        help="let the agent search the machine manual (default: by meaning)",
    )
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
    run.add_argument(
        "--quiet",
        action="store_true",
        help="no live progress view: one line per finished case (the view is on by default)",
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
        elif args.challenge:
            cases = challenge_cases(seeds_from(args.challenge))
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
        manual = open_manual(args.manual) if args.manual else None
        log = AuditLog(args.audit) if args.audit else None

        def live_line(line: str) -> None:
            print(line, flush=True)

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
                with_manual=manual is not None,
            ),
            name=args.name,
            approver=APPROVERS[args.approve],
            memory=memory,
            log=log,
            budgets=budgets,
            hazards=args.hazards,
            manual=manual,
            on_record=save_record,
            watch=None if args.quiet else live_line,
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
