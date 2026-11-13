# Per-stage measurements of one rapid triage, read after it has finished.
# Responsibility: count and time what the triage did; never judge whether it was right.
"""Triage stage metrics: where a triage spent its model time, and what it got.

The A0 triage baseline (docs/benchmarks/2026-11-12-triage-a0.md) could not
say which stage used the 90 seconds, because a model question was recorded
only by its job, and "decide" is asked in both investigate and test. Since
2026-11-13 each `ModelCall` also carries the stage and mode it was asked in,
and the state records when the first hypothesis appeared, so these numbers
can be computed after the run for every triage branch compared with A0.

Everything here is read from the finished investigation and the model calls.
Nothing in it reaches the agent, and it holds no hidden truth: whether the
diagnosis was right is scoring's job, not this module's.
"""

from collections import Counter, defaultdict
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from capstone.agent.model_policy import ModelCall
from capstone.agent.state import InvestigationState


class TriageMetrics(BaseModel):
    """Where one triage spent its model questions and what evidence it got."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Model questions by the stage they were asked in ("decide" is the
    # conclusion), and the seconds their requests took on the client's clock.
    calls_by_stage: dict[str, int]
    model_seconds_by_stage: dict[str, float]
    # Questions a fallback model answered because the first model asked did not.
    fallback_answers: int
    # Seconds from the triage's start until it first held a hypothesis; None
    # when it never formed one.
    first_hypothesis_seconds: float | None
    final_hypotheses: int
    # How many hypotheses a successful read tested, and whether one of them
    # was not the hypothesis concluded on (False when none was chosen).
    hypotheses_tested: int
    rival_tested: bool
    # Tool reads by how they ended.
    reads_observed: int
    reads_uninterpreted: int
    reads_failed: int
    reads_repeated: int
    # Open questions the checked conclusion reported; 0 with no conclusion.
    unknowns_reported: int


def triage_metrics(
    state: InvestigationState, calls: Sequence[ModelCall]
) -> TriageMetrics:
    """The metrics of a finished triage, from its state and its model calls.

    `calls` may hold a deep run's questions too; only those asked in triage
    mode count. Calls recorded before stages were kept count as "unknown".
    """
    # Variables:
    #   ours: The model questions this triage asked, told apart from a
    #     following deep run's by their recorded mode; in records from before
    #     modes were kept, every call (a triage-only run has no others).
    #   tested: Hypotheses at least one successful read was testing.
    #   by_stage: Questions per stage.
    #   seconds: Request seconds per stage, summed over every attempt.
    #   fallback: Answered questions whose answer came from a model other than
    #     the first one tried.
    #   concluded_on: The hypothesis the conclusion chose; a read testing any
    #     other hypothesis tested a rival. None: no rival can be named.
    #   outcomes: How many tool reads ended each way, from the decision trace.
    if any(c.mode is not None for c in calls):
        ours = [c for c in calls if c.mode == "triage"]
    else:
        ours = list(calls)
    by_stage = Counter(c.stage or "unknown" for c in ours)
    seconds: dict[str, float] = defaultdict(float)
    for call in ours:
        seconds[call.stage or "unknown"] += sum(a.seconds or 0.0 for a in call.attempts)
    fallback = sum(
        c.outcome == "answered"
        and bool(c.attempts)
        and c.answered_by is not None
        and c.answered_by != c.attempts[0].model
        for c in ours
    )
    concluded_on = None if state.conclusion is None else state.conclusion.hypothesis_id
    outcomes = Counter(d.outcome for d in state.decisions if d.tool is not None)
    tested = {
        d.hypothesis_id
        for d in state.decisions
        if d.outcome == "observed" and d.hypothesis_id is not None
    }
    return TriageMetrics(
        calls_by_stage=dict(sorted(by_stage.items())),
        model_seconds_by_stage={k: round(v, 3) for k, v in sorted(seconds.items())},
        fallback_answers=fallback,
        first_hypothesis_seconds=state.first_hypothesis_seconds,
        final_hypotheses=len(state.hypotheses),
        hypotheses_tested=len(tested),
        rival_tested=concluded_on is not None and bool(tested - {concluded_on}),
        reads_observed=outcomes["observed"],
        reads_uninterpreted=outcomes["uninterpreted"],
        reads_failed=outcomes["tool_error"] + outcomes["malformed_result"],
        reads_repeated=outcomes["repeated_call"],
        unknowns_reported=0
        if state.conclusion is None
        else len(state.conclusion.unresolved_questions),
    )
