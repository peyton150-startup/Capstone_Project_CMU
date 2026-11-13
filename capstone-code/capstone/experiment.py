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
from capstone.agent.critic import (
    Critic,
    CritiqueRecord,
    RecheckRecord,
    ReinstatementRecord,
)
from capstone.agent.evidence_packet import EvidencePacket
from capstone.agent.model_policy import ModelCall
from capstone.agent.policy import ReasoningPolicy
from capstone.agent.state import (
    BatchTrace,
    Budgets,
    ConclusionTrace,
    IncidentContext,
    InvestigateAdvice,
    TriageTestRecord,
)
from capstone.agent.tree_of_thought import RevaluationRecord, Thought, TreeOptions
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
from capstone.observability import EventLogger, create_event_logger
from capstone.progress import ProgressView, print_progress, run_header
from capstone.providers.chat import INVALID_REPLY, is_model_outcome
from capstone.providers.hazards import HazardProfile
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
    # This case's own tool faults; None: the run's setting (`run_experiment`).
    hazards: HazardProfile | None = None


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
    # Per question (job), summed over every attempt, failed and fallback ones
    # included: the tokens the services reported and the characters sent.
    # Tokens are a lower bound when some service reports none. Empty in
    # results from before 2026-11-08.
    input_tokens_by_job: dict[str, int] = {}
    output_tokens_by_job: dict[str, int] = {}
    prompt_chars_by_job: dict[str, int] = {}


class AgentStep(BaseModel):
    """A model question or loop decision attributed to its producing agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    agent: str
    kind: str
    phase: str
    outcome: str
    tool: str | None = None
    # With DECIDE_CALLS above 1: which decide answer chose this call, and its
    # place in that answer. None otherwise (and in older records).
    batch: int | None = None
    batch_position: int | None = None


# The request sizes an attempt records, totalled by job in `CallSummary`.
REQUEST_SIZES = ("input_tokens", "output_tokens", "prompt_chars")


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
    #   sizes: For each recorded request size (input tokens, output tokens,
    #     characters sent), its total by job over every attempt that reported it.
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
    sizes = {field: Counter() for field in REQUEST_SIZES}
    for call in calls:
        for attempt in call.attempts:
            for field, totals in sizes.items():
                value = getattr(attempt, field)
                if value is not None:
                    totals[call.job] += value
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
        input_tokens_by_job=dict(sorted(sizes["input_tokens"].items())),
        output_tokens_by_job=dict(sorted(sizes["output_tokens"].items())),
        prompt_chars_by_job=dict(sorted(sizes["prompt_chars"].items())),
    )


class TriageRecord(BaseModel):
    """What a rapid triage answered before any deep run, for the experimenter.

    Its latency is wall-clock seconds, kept apart from simulation ticks.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    seconds: float
    conclusion: str | None
    confidence: float | None
    # The checked recommendation, and the one the model gave before the check
    # (a triage never proposes, so "intervene" here only asks for a deep run).
    recommendation: str | None
    policy_recommendation: str | None = None
    assessment: str | None = None
    termination_reason: str | None = None
    tool_calls: int = 0
    # Calls charged to the research budget: tool_calls less the line
    # screening (its own allowance), so 7 tool calls can be 6 research.
    # None in records from before it was kept.
    research_tool_calls: int | None = None
    # TRIAGE_INVESTIGATE: each turn the request compiler ran, with the
    # model's choice beside it. None in records from before it was kept.
    investigate_advice: list[InvestigateAdvice] | None = None
    # The triage evidence packet (TRIAGE_PACKET): every item, missing reason
    # and call outcome Observe recorded. None: no packet was built (and in
    # records from before it was kept).
    packet: EvidencePacket | None = None
    # TRIAGE_EVIDENCE_TESTS: whether the triage used the Block 3 rules, and
    # each time they withheld support, held a conclusion open or judged a
    # question. None in records from before they were kept.
    evidence_tests: bool | None = None
    test_records: list[TriageTestRecord] | None = None
    # Set by code from the conclusion: whether a deep run should follow, and
    # whether one did (TRIAGE_THEN_DEEP=off stops after the triage).
    deep_recommended: bool
    deep_ran: bool


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
    # Why the final answer was refused, so the conclusion fell back to
    # "undetermined". None when it was accepted, and in older results.
    conclusion_rejected: str | None = None
    # The final check's gaps by kind, for replaying other gap rules offline
    # (`python -m capstone.evaluation.gap_replay`). None in older results.
    conclusion_trace: ConclusionTrace | None = None
    assessment: str | None = None
    unresolved_questions: tuple[str, ...] = ()
    next_check: str | None = None
    action_rationale: str | None = None
    critic_tool_calls_used: int = 0
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
    # With a blackout: sensor calls it refused, and whether the agent read the
    # machine's sensors again once the feed was back. None: no blackout (and
    # in results from before these were kept).
    hazards_blocked: int | None = None
    blackout_recovered: bool | None = None
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
    # None for older runs; the packet references observable evidence only.
    line_context_enabled: bool | None = None
    incident_context: IncidentContext | None = None
    # None in older records; specialists can identify themselves on each step.
    agent_steps: list[AgentStep] | None = None
    # What the critic said about the two leading hypotheses, or why it said
    # nothing. None: no critic ran (and in records from before it was kept).
    critique: CritiqueRecord | None = None
    # The claim of the hypothesis the critic favoured, so it can be labelled
    # as a cause the way a conclusion is. None: no pick (or an older record).
    critic_favoured_claim: str | None = None
    # What the critic follow-up did (one reading, or why none). None: the
    # follow-up was off (and in records from before it was kept).
    recheck: RecheckRecord | None = None
    # With --tree-of-thought: one tree per hypothesize step, in order (the
    # candidates, their ratings, which were kept and why the rest were dropped).
    # None: the run used the ordinary step (or predates this record).
    thoughts: list[Thought] | None = None
    # The hypothesis reserve (HYPOTHESIS_RESERVE_SECONDS): True when it let
    # the hypothesize question be asked after research ran out of time, False
    # when it was kept but not needed. None: no reserve (and older records).
    hypothesis_reserve_used: bool | None = None
    # The tree-of-thought options the run's policy used (P1-P5 switches).
    # None: the ordinary policy, or a record from before they were kept.
    tree_options: TreeOptions | None = None
    # P2 (TOT_REINSTATE): what the critic's reinstatement question did. None:
    # it was off or had nothing to offer (and in older records).
    reinstatement: ReinstatementRecord | None = None
    # P5 (TOT_REVALUE): what the tree's second rating pass did. None: it was
    # off, or an older record.
    revaluation: RevaluationRecord | None = None
    # With triage on: the rapid triage that ran first. The fields above then
    # describe the deep run that followed, or the triage when none did.
    # None: triage was off (and in records from before it was kept).
    triage: TriageRecord | None = None
    # DECIDE_CALLS for this run, and what batching did (answers, calls chosen
    # and run, and the cuts). None in records from before it was kept; the
    # trace is also None when DECIDE_CALLS was 1.
    decide_calls: int | None = Field(default=None, ge=1)
    decide_batches: BatchTrace | None = None
    # STAGE_CONTEXT for this run: whether judge_verification and write_lesson
    # had their own views. None in records from before it was kept.
    stage_context: bool | None = None


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


def rejected_text(record: ExperimentRecord) -> str:
    """For the report: why the final answer was refused; else nothing."""
    if record.conclusion_rejected is None:
        return ""
    return f" conclude_refused=({record.conclusion_rejected})"


def favoured_claim(state) -> str | None:
    """The claim the critic favoured, as worded when it judged it; None if none.

    Read from the critique record, never from the final hypotheses: the agent
    keeps rewording them after the critique, even with what the fix showed.
    """
    # Variables:
    #   state: The finished investigation, which holds the critique record.
    return None if state.critique is None else state.critique.favoured_claim


def triage_record(result: EpisodeResult) -> TriageRecord | None:
    """The triage's answer and timing; None when triage was off."""
    # Variables:
    #   first: The triage investigation.
    #   concluded: The triage's checked conclusion, if it reached one.
    #   first.triage_packet: The Observe packet, kept whole for tracing.
    #   first.research_tool_calls: Calls charged to research, without the
    #     screening's own call, beside tool_calls.
    #   first.investigate_advice: Each turn the request compiler ran.
    #   evidence_tests: The TRIAGE_EVIDENCE_TESTS setting the run used.
    #   first.triage_test_records: What those rules changed, kept for tracing.
    first = result.triage
    if first is None or result.triage_seconds is None:
        return None
    from capstone.settings import get_settings

    evidence_tests = get_settings().triage_evidence_tests
    concluded = first.conclusion
    return TriageRecord(
        seconds=result.triage_seconds,
        conclusion=None if concluded is None else concluded.diagnosis,
        confidence=None if concluded is None else concluded.confidence,
        recommendation=None if concluded is None else concluded.recommendation,
        policy_recommendation=first.policy_recommendation,
        assessment=None if concluded is None else concluded.assessment,
        termination_reason=(
            None if first.termination_reason is None else first.termination_reason.value
        ),
        tool_calls=first.tool_call_count,
        packet=first.triage_packet,
        research_tool_calls=first.research_tool_calls,
        investigate_advice=list(first.investigate_advice),
        evidence_tests=evidence_tests,
        test_records=list(first.triage_test_records),
        deep_recommended=bool(first.deep_recommended),
        deep_ran=result.state is not first,
    )


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
    tree_options: TreeOptions | None = None,
) -> ExperimentRecord:
    """Save the episode and its completion/action audit without rerunning any reasoning."""
    # Variables:
    #   concluded: The controller-checked belief, including unresolved gaps and next check.
    #   state: Includes the critic diagnostic-call count, distinct from verification calls.
    #   promotion, uses: Optional memory audit; never converted into present factory facts.
    #   state.incident_context: The optional observable packet and its source IDs,
    #     copied to the experiment record for the A/B comparison.
    #   state.stage_context: Whether the stage views were on, kept so runs with
    #     and without them can be compared.
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
        conclusion_rejected=state.conclusion_rejected,
        conclusion_trace=state.conclusion_trace,
        assessment=None if concluded is None else concluded.assessment,
        unresolved_questions=()
        if concluded is None
        else concluded.unresolved_questions,
        next_check=None if concluded is None else concluded.next_check,
        action_rationale=None if concluded is None else concluded.action_rationale,
        critic_tool_calls_used=state.critic_tool_calls_used,
        verification=None if state.verification is None else state.verification.outcome,
        tools_used=[d.tool for d in state.decisions if d.tool is not None],
        score=result.score,
        model_calls=model_calls,
        wall_seconds=wall_seconds,
        hazards_fired=None if result.hazards is None else result.hazards.fired,
        hazards_retried=None if result.hazards is None else result.hazards.retried,
        hazards_blocked=(
            None
            if result.hazards is None or result.hazards.blackout_recovered is None
            else result.hazards.blocked
        ),
        blackout_recovered=(
            None if result.hazards is None else result.hazards.blackout_recovered
        ),
        memory_promotion=promotion,
        memory_uses=uses,
        recall_searches=list(build_search_records(state)) if with_memory else None,
        manual_searches=list(build_manual_records(state)) if with_manual else None,
        factory_calls=count_factory_calls(state),
        state_action_bar=state.state_action_bar,
        step_questions=state.step_questions,
        line_context_enabled=state.line_context_enabled,
        incident_context=state.incident_context,
        decide_calls=state.decide_calls,
        decide_batches=state.decide_batches,
        stage_context=state.stage_context,
        critique=state.critique,
        critic_favoured_claim=favoured_claim(state),
        recheck=state.recheck,
        agent_steps=[
            AgentStep(
                agent=decision.agent,
                kind="decision",
                phase=decision.phase,
                outcome=decision.outcome,
                tool=decision.tool,
                batch=decision.batch,
                batch_position=decision.batch_position,
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
        hypothesis_reserve_used=state.hypothesis_reserve_used,
        tree_options=tree_options,
        reinstatement=state.reinstatement,
        revaluation=state.revaluation,
        triage=triage_record(result),
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
    hazards: bool | HazardProfile = False,
    manual: ManualSearch | None = None,
    start: int = 1,
    watch: Callable[[str], None] | None = None,
    make_critic: Callable[[], Critic] | None = None,
    triage: bool | None = None,
    stage_context: bool | None = None,
    event_logger: EventLogger | None = None,
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
    #   triage: Run a rapid triage before each deep run; None leaves it to settings.
    #   stage_context: Force the stage views on or off for every case; None leaves
    #     it to STAGE_CONTEXT in settings.
    #   event_logger: Optional JSON-line trace shared by every case; each event
    #     carries its run and investigation id, so cases can be told apart.
    #   records: One record per case, in order.
    #   run_key: A unique name for this case's run.
    #   policy: A fresh decision-maker, so no case learns from another's state.
    #   started: The clock reading when the case began.
    #   result: The finished episode, including the simulator and its hidden truth.
    #   wall_seconds: How long the episode took on the wall clock.
    #   calls: The model questions asked; only model-backed policies keep them,
    #     followed by the critic's, if one ran.
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
            hazards=case.hazards or hazards,
            manual=manual,
            watch=None if watch is None else ProgressView(watch),
            critic=None if make_critic is None else make_critic(),
            triage=triage,
            stage_context=stage_context,
            event_logger=event_logger,
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
            # Kept by TreeOfThoughtPolicy only, like its thoughts.
            tree_options=getattr(policy, "options", None),
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


def nearest_rank(values: Sequence[float], share: float) -> float:
    """The value at `share` (0.5 for the median, 0.95 for p95) by nearest rank."""
    # Variables:
    #   ordered: The values from smallest to largest.
    #   rank: The 1-based position of the value that covers `share` of them.
    ordered = sorted(values)
    rank = max(1, -(-int(share * 100) * len(ordered) // 100))
    return ordered[min(rank, len(ordered)) - 1]


def format_stage_context(records: Sequence[ExperimentRecord]) -> str:
    """One line saying whether the stage views were on, counted from the records.

    Counts what each run recorded rather than what was asked for, so a run
    that did not get the setting shows here. Runs from before the setting was
    kept say "not recorded".
    """
    # Variables:
    #   on, off, unknown: How many runs recorded the views as on, off, or nothing.
    on = sum(1 for r in records if r.stage_context is True)
    off = sum(1 for r in records if r.stage_context is False)
    unknown = len(records) - on - off
    parts = [
        f"{count} {name}"
        for count, name in ((on, "on"), (off, "off"), (unknown, "not recorded"))
        if count
    ]
    return "stage views: " + (", ".join(parts) if parts else "no runs")


def stage_context_mismatches(
    records: Sequence[ExperimentRecord], wanted: bool | None
) -> list[str]:
    """Run keys whose recorded stage views differ from what the run asked for.

    The check that a run set to on really ran on, and off really ran off.
    Nothing was asked for (None): nothing can differ.
    """
    # Variables:
    #   wanted: True (on) or False (off) as set on the command line; None when
    #     the run left it to STAGE_CONTEXT in the environment.
    if wanted is None:
        return []
    return [r.run_key for r in records if r.stage_context is not wanted]


def format_investigate(records: Sequence[ExperimentRecord]) -> str | None:
    """One line on the request compiler (TRIAGE_INVESTIGATE); None if it never ran.

    Counts each outcome over every triage, so an advisory run shows how often
    the model agreed with the compiled read, and an "on" run shows how many
    decide questions the compiler replaced and how often the model was still
    needed.
    """
    # Variables:
    #   advice: Every turn the compiler ran, over all triages.
    #   outcomes: How many turns ended each way.
    #   compared: Turns where both had a choice to compare.
    #   agreed: Of those, where the model chose the same sensor read.
    advice = [
        a
        for r in records
        if r.triage is not None
        for a in r.triage.investigate_advice or ()
    ]
    if not advice:
        return None
    outcomes = Counter(a.outcome for a in advice)
    compared = sum(
        outcomes[k]
        for k in ("same_request", "same_target", "different", "model_stopped")
    )
    agreed = outcomes["same_request"] + outcomes["same_target"]
    modes = "/".join(sorted({a.mode for a in advice}))
    return (
        f"investigate compiler ({modes}): {len(advice)} turn(s); decide "
        f"replaced {outcomes['compiled']}; model agreed {agreed} of {compared} "
        f"compared ({outcomes['same_request']} same read, "
        f"{outcomes['same_target']} same sensor); different "
        f"{outcomes['different']}, model stopped {outcomes['model_stopped']}, "
        f"model failed {outcomes['model_failed']}; no candidate "
        f"{outcomes['no_candidate']}"
    )


def format_evidence_tests(records: Sequence[ExperimentRecord]) -> str | None:
    """One line on what TRIAGE_EVIDENCE_TESTS changed; None when no triage kept it.

    Counts each kind of record, so a run with the setting on can be compared
    with one where it is off: how often support was withheld, conclusions
    held open, and questions kept open or closed by a measured verdict.
    """
    # Variables:
    #   kept: Triages that recorded whether the rules were on.
    #   on: Those that ran with the rules on.
    #   kinds: How many records of each kind the triages left.
    #   changed: Triages where the rules changed at least one outcome.
    kept = [
        r.triage for r in records if r.triage and r.triage.evidence_tests is not None
    ]
    if not kept:
        return None
    on = [t for t in kept if t.evidence_tests]
    kinds = Counter(rec.kind for t in on for rec in t.test_records or ())
    changed = sum(
        any(rec.kind != "question_closed" for rec in t.test_records or ()) for t in on
    )
    return (
        f"evidence tests: on in {len(on)} of {len(kept)} triage(s), changed an "
        f"outcome in {changed}; support withheld "
        f"{kinds['support_withheld_rival_question']} (open rival question), "
        f"{kinds['support_withheld_shared_root']} (one sensor counted twice); "
        f"conclusions held open by a rival question {kinds['rival_question_gap']}; "
        f"questions kept open {kinds['question_kept_open']}, closed by a measured "
        f"verdict {kinds['question_closed']}"
    )


def format_triage(records: Sequence[ExperimentRecord]) -> str | None:
    """One line on the rapid triages; None when no run had one.

    Counts time-outs and unresolved answers rather than hiding them: a triage
    that did not answer is reported as such.
    """
    # Variables:
    #   kept: The triage of each run that had one.
    #   seconds: How long each triage took on the wall clock.
    #   answered: Triages that ended with a supported conclusion.
    #   timed_out: Triages stopped by their deadline.
    #   unavailable: Triages whose conclusion no model answered although
    #     models were asked; scoring leaves these out.
    kept = [r.triage for r in records if r.triage is not None]
    if not kept:
        return None
    seconds = [t.seconds for t in kept]
    answered = sum(t.assessment == "supported" for t in kept)
    timed_out = sum(t.termination_reason == "timeout" for t in kept)
    unavailable = sum(t.termination_reason == "model_unavailable" for t in kept)
    return (
        f"triage: {len(kept)} run(s), p50 {nearest_rank(seconds, 0.5):.0f} s, "
        f"p95 {nearest_rank(seconds, 0.95):.0f} s; {answered} supported, "
        f"{len(kept) - answered} not ({timed_out} timed out, "
        f"{unavailable} no model answered); "
        f"deep run asked for {sum(t.deep_recommended for t in kept)}, "
        f"ran {sum(t.deep_ran for t in kept)}; "
        f"{sum(t.tool_calls for t in kept)} triage tool calls"
    )


def format_batches(records: Sequence[ExperimentRecord]) -> str | None:
    """One line on several tool calls per decide answer; None when no run batched."""
    # Variables:
    #   kept: The batch trace of each run that had DECIDE_CALLS above 1.
    #   answers: Decide answers that chose at least one call, over those runs.
    #   run: Tool calls the loop ran from those answers.
    kept = [r.decide_batches for r in records if r.decide_batches is not None]
    if not kept:
        return None
    answers = sum(t.answers for t in kept)
    run = sum(t.run for t in kept)
    per_answer = run / answers if answers else 0.0
    return (
        f"decide batches: {len(kept)} run(s), {answers} answers chose "
        f"{sum(t.chosen for t in kept)} calls and ran {run} ({per_answer:.1f} per "
        f"answer); {sum(t.read_together for t in kept)} read together; cut "
        f"{sum(t.cut_at_wait for t in kept)} at a wait, "
        f"{sum(t.cut_over_limit for t in kept)} over the limit, "
        f"{sum(t.cut_for_budget for t in kept)} for budget"
    )


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
        f"{manual}{overruled_text(record)}{rejected_text(record)}"
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
    #   triaged: The triage line, if any run had a rapid triage.
    #   batched: The decide-batches line, if any run had DECIDE_CALLS above 1.
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
    lines += [] if manual is None else [manual]
    triaged = format_triage(records)
    lines += [] if triaged is None else [triaged]
    advised = format_investigate(records)
    lines += [] if advised is None else [advised]
    tested = format_evidence_tests(records)
    lines += [] if tested is None else [tested]
    lines.append(format_stage_context(records))
    batched = format_batches(records)
    lines += ([] if batched is None else [batched]) + [""]

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
    #   late_seconds: LATE_MODEL_SECONDS: a decide question with less time than
    #     this goes to LATE_MODEL, when one is set (`ModelPolicy.client_for`).
    #   options: The tree's switches from the TOT_* settings, read once so every
    #     case of the experiment uses the same ones.
    from capstone.agent.model_policy import ModelPolicy
    from capstone.agent.tree_of_thought import TreeOfThoughtPolicy
    from capstone.providers.chat import clients_for_jobs, late_clients
    from capstone.providers.factory import research_tools
    from capstone.settings import get_settings

    late_seconds = get_settings().late_model_seconds
    tools = research_tools()
    if with_recall:
        from capstone.providers.recall import RECALL_SPEC

        tools = (*tools, RECALL_SPEC)
    if with_manual:
        from capstone.providers.manual import MANUAL_SPEC

        tools = (*tools, MANUAL_SPEC)
    if tree_of_thought:
        options = tree_options_from(get_settings())
        from capstone.providers.chat import value_client

        def tree() -> TreeOfThoughtPolicy:
            # Variables:
            #   clients: The seven jobs' clients, plus `value` for P5 when
            #     VALUE_MODEL names a model for the second rating.
            #   second: That client, or None (the hypothesize client answers).
            clients = {**clients_for_jobs(), **late_clients()}
            second = value_client() if options.revalue else None
            if second is not None:
                clients["value"] = second  # VALUE_MODEL: the faster rating model
            return TreeOfThoughtPolicy(
                clients, tools, options=options, late_seconds=late_seconds
            )

        return tree
    return lambda: ModelPolicy(
        {**clients_for_jobs(), **late_clients()}, tools, late_seconds=late_seconds
    )


def preflight_models(print_line: Callable[[str], None] = print) -> bool:
    """Before a triage run, ask each model one tiny question; False if none answers.

    Models that do not answer are set aside for a while (`ModelHealth`), so
    the first triage questions skip them instead of waiting on them.
    """
    # Variables:
    #   print_line: Where each model's result is shown.
    #   results: Each distinct model and what came of its check.
    from capstone.providers.chat import check_models, clients_for_jobs, late_clients

    results = check_models(list({**clients_for_jobs(), **late_clients()}.values()))
    for model, outcome in results:
        print_line(f"model check: {model}: {outcome}")
    return any(outcome == "answered" for _, outcome in results)


def tree_options_from(settings) -> TreeOptions:
    """The tree's switches, read from the TOT_* settings (all off by default)."""
    return TreeOptions(
        revalue=settings.tot_revalue,
        retain=settings.tot_retain,
        rank=settings.tot_rank,
        rotate=settings.tot_rotate,
        adaptive=settings.tot_adaptive,
    )


def add_manual_options(parser: argparse.ArgumentParser) -> None:
    """The manual is offered by default, searched by meaning; `--no-manual`
    runs without it (developer, 2026-10-29). Shared by experiment and evals."""
    # Variables:
    #   choice: Either --manual [semantic|keyword] or --no-manual, not both.
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument(
        "--manual",
        nargs="?",
        const="semantic",
        default="semantic",
        choices=("semantic", "keyword"),
        help="how the agent searches the machine manual (default: by meaning)",
    )
    choice.add_argument(
        "--no-manual",
        dest="manual",
        action="store_const",
        const=None,
        help="run without the machine manual",
    )


def open_manual(mode: str) -> ManualSearch:
    """The machine manual, searched by meaning ("semantic": its Chroma index) or
    by shared words ("keyword").

    Before a semantic run the index is checked against the manual and rebuilt
    first if it is empty, out of date (the manual changed) or built by another
    embedding model, so a run never searches an old manual.
    """
    # Variables:
    #   mode: semantic searches by meaning, keyword by shared words.
    #   sections: The manual's checked sections.
    #   index: The semantic index, ready for the run.
    #   rebuilt: Why the index was rebuilt first, or None when it was reused.
    from capstone.manual.index import KeywordManualSearch, ready_manual_index
    from capstone.manual.sections import load_manual
    from capstone.settings import get_settings

    sections = load_manual()
    if mode == "keyword":
        return KeywordManualSearch(sections)
    index, rebuilt = ready_manual_index(get_settings(), sections=sections)
    if rebuilt is not None:
        print(f"rebuilt the manual index before the run: {rebuilt}", flush=True)
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


def default_audit_path(out: Path) -> Path:
    """Place a run's audit beside its records with the archive's expected name."""
    # Variables:
    #   stem: The shared run name used to pair records and audits on import.
    name = out.name
    stem = (
        name.removesuffix(".records.jsonl")
        if name.endswith(".records.jsonl")
        else name.removesuffix(".jsonl")
    )
    return out.with_name(f"{stem}.audit.jsonl")


def main(argv: Sequence[str] | None = None) -> int:
    """The command line: run cases, label their conclusions, or report them."""
    # Variables:
    #   argv: The command-line words; None reads the real command line, and
    #     tests pass their own.
    #   args.command: Which subcommand was chosen, "run", "label" or "report";
    #     it decides which branch below runs.
    #   cases: The cases to run, from exactly one of --known, --held-out,
    #     --challenge or --seeds (with --faults).
    #   budgets: Time limits for each investigation; None keeps the defaults
    #     unless --timeout-seconds was given.
    #   memory, manual: Optional memory store and operator manual.
    #   audit_path, log: The chosen audit file and writer; new CLI runs use a
    #     companion file unless --no-audit was given.
    #   args.triage: True with --triage, otherwise None so the TRIAGE setting
    #     decides; passed through to run_experiment.
    #   packet_log, packet_logger: With --packet-log, the open trace file and the
    #     JSON-line logger writing to it; each triage's evidence packet logs its
    #     calls, missing items and counts there. None without the flag.
    #   triage_on: Whether this run triages; if so, every model is checked
    #     first (`preflight_models`) and the run does not start when none
    #     answers.
    #   wanted: The stage views asked for with --stage-context: True (on), False
    #     (off), or None when left out and STAGE_CONTEXT in the environment decides.
    #   wrong: Run keys whose recorded stage views differ from `wanted`; any makes
    #     the command exit 1.
    #   records: The finished results, saved as each case ends; for "label" and
    #     "report", the results read back from --results.
    #   done: The run keys already labelled, so labelling skips them.
    #   labels: Hand labels to score conclusions against; empty without --labels.
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
    add_manual_options(run)
    audit = run.add_mutually_exclusive_group()
    audit.add_argument(
        "--audit", type=Path, help="audit log path (default: beside --out)"
    )
    audit.add_argument("--no-audit", action="store_true", help="omit the audit log")
    run.add_argument("--timeout-seconds", type=float, help="per investigation")
    run.add_argument(
        "--hazards",
        nargs="?",
        const="standard",
        default=False,
        choices=("standard", "blackout"),
        help=(
            "standard (the default when given alone): tools time out, drop rows "
            "and show a stale record on a fixed schedule; blackout: the alarmed "
            "machine's sensor feed is down for a seeded 10-50 ticks"
        ),
    )
    run.add_argument(
        "--tree-of-thought",
        action="store_true",
        help="hypothesize by generating, valuing and pruning candidates (opt-in)",
    )
    run.add_argument(
        "--triage",
        action="store_true",
        default=None,
        help=(
            "a short read-only triage before each deep run (opt-in; also TRIAGE=on); "
            "the deep run follows only when the triage leaves work for it"
        ),
    )
    run.add_argument(
        "--packet-log",
        type=Path,
        default=None,
        help=(
            "append a JSON-line trace of each triage evidence packet (its calls, "
            "missing items and counts; identifiers only, never evidence text)"
        ),
    )
    run.add_argument(
        "--stage-context",
        choices=("on", "off"),
        default=None,
        help=(
            "on: judge_verification and write_lesson get their own views; "
            "off: every question sees the shared view. Overrides STAGE_CONTEXT in "
            ".env for this run. Left out, the .env value is used (off if unset)."
        ),
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
        audit_path = (
            None if args.no_audit else (args.audit or default_audit_path(args.out))
        )
        if audit_path == args.out:
            parser.error("audit and records paths must differ")
        log = AuditLog(audit_path) if audit_path else None
        packet_log = (
            None
            if args.packet_log is None
            else args.packet_log.open("a", encoding="utf-8")
        )
        packet_logger = None if packet_log is None else create_event_logger(packet_log)

        def live_line(line: str) -> None:
            # Variables:
            #   line: The progress text, colored only for an interactive terminal.
            print_progress(line)

        def save_record(record: ExperimentRecord) -> None:
            append_records(args.out, [record])
            print(f"{record.scenario_id}: {record.conclusion!r}", flush=True)
            for line in format_call_failures(record):
                print(line, flush=True)

        wanted = None if args.stage_context is None else args.stage_context == "on"
        from capstone.settings import get_settings

        triage_on = get_settings().triage if args.triage is None else args.triage
        if triage_on and not preflight_models():
            print("ERROR: no model answered the check; the run was not started")
            return 1
        if not args.quiet:
            from capstone.settings import get_settings

            for line in run_header(
                get_settings(),
                manual=args.manual,
                tree_of_thought=args.tree_of_thought,
                hazards=args.hazards,
                stage_context=(
                    get_settings().stage_context if wanted is None else wanted
                ),
            ):
                live_line(line)

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
            triage=args.triage,
            stage_context=wanted,
            event_logger=packet_logger,
        )
        if packet_log is not None:
            packet_log.close()
        print(report(records, {}))
        wrong = stage_context_mismatches(records, wanted)
        if wrong:
            print(
                f"ERROR: --stage-context {args.stage_context} was asked for but "
                f"{len(wrong)} run(s) recorded otherwise: {', '.join(wrong)}",
                flush=True,
            )
            return 1
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
