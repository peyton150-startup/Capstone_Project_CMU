# The triage Test stage's deterministic checks (Block 3, TRIAGE_EVIDENCE_TESTS).
# Responsibility: judge measured predicates and count independent sources; never pick a cause.
"""Deterministic evidence tests for rapid triage.

Used only when `state.mode == "triage"` and the run's `triage_evidence_tests`
setting is on (TRIAGE_EVIDENCE_TESTS, on by default). A deep run never
reaches them.

- `physical_root`: which machine sensor a piece of evidence measured. A raw
  read and a summary of one sensor share a root, so they count as one
  supporter, not two (TRI-04).
- `open_rival_questions`: open questions that name no live primary
  hypothesis but are meant to tell live hypotheses apart (TRI-03).
- `evaluate`: a measured predicate's verdict, `true`, `false`, `insufficient`,
  `stale` or `unavailable`, from observable readings only. A question with a
  predicate closes only on `true` or `false`, so a successful call by itself
  never settles it. Missing data is `unavailable` or `insufficient`, never
  `false` and never "normal".
- `note`: keeps a `TriageTestRecord` once per distinct finding, so a run's
  records show each time these rules changed an outcome (for tracing whether
  the setting helps).

Nothing here reads hidden truth or calls a model.
"""

import json
from statistics import fmean

from capstone.agent.state import (
    InvestigationState,
    Predicate,
    PredicateResult,
    Question,
    TriageTestRecord,
)
from capstone.contracts.evidence import Evidence

# Tools whose answers are readings of one machine sensor, named in the request.
SENSOR_TOOLS = frozenset(
    {"get_readings", "get_sensor_summary", "get_sensor_trend", "get_factory_readings"}
)
# How definite each verdict is; the evaluator reports the most definite one.
RANK = {"unavailable": 0, "stale": 1, "insufficient": 2, "false": 3, "true": 3}


def root_of(machine_id: object, sensor: object) -> str | None:
    """`machine:sensor`, `factory:sensor` for a factory sensor, or None."""
    # Variables:
    #   machine_id: The machine named, or None for a factory-wide sensor.
    #   sensor: The sensor named; without one there is no physical root.
    if not isinstance(sensor, str):
        return None
    if machine_id is None:
        return f"factory:{sensor}"
    return f"{machine_id}:{sensor}" if isinstance(machine_id, str) else None


def physical_root(state: InvestigationState, evidence: Evidence) -> str | None:
    """The one machine sensor this evidence measured, or None when it is not one.

    The request that fetched it is read first (its machine and sensor
    arguments). Without that, the answer's own `machine_id` and `sensor`, or
    rows that all name the same pair. Events, screenings and text give None.
    """
    # Variables:
    #   decision: The step that gathered this evidence, whose arguments name
    #     the machine and sensor that were asked about.
    #   data: The answer as the tool gave it, parsed.
    #   roots: The distinct roots named by a list answer's rows.
    decision = next(
        (d for d in state.decisions if evidence.id in d.evidence_ids and d.tool), None
    )
    if decision is not None and decision.tool in SENSOR_TOOLS:
        return root_of(
            decision.arguments.get("machine_id"), decision.arguments.get("sensor")
        )
    try:
        data = json.loads(evidence.content)
    except ValueError:
        return None
    if isinstance(data, dict):
        return root_of(data.get("machine_id"), data.get("sensor"))
    if isinstance(data, list) and data and all(isinstance(r, dict) for r in data):
        roots = {root_of(r.get("machine_id"), r.get("sensor")) for r in data}
        if len(roots) == 1:
            return roots.pop()
    return None


def source_roots(state: InvestigationState, evidence_ids: set[str]) -> tuple[str, ...]:
    """The distinct independent sources behind some evidence, sorted.

    Evidence with a physical root adds its root; evidence without one (an
    event list, a screening) counts as its own source, as before.
    """
    # Variables:
    #   by_id: The evidence itself, by id.
    #   sources: One key per independent source: a root, or "evidence:<id>".
    by_id = {e.id: e for e in state.evidence}
    sources = set()
    for evidence_id in evidence_ids:
        evidence = by_id.get(evidence_id)
        root = None if evidence is None else physical_root(state, evidence)
        sources.add(root or f"evidence:{evidence_id}")
    return tuple(sorted(sources))


def open_rival_questions(
    state: InvestigationState, current: set[str]
) -> list[Question]:
    """Open questions with no live primary hypothesis that separate live rivals."""
    # Variables:
    #   current: Ids of the explanations still in play.
    return [
        q
        for q in state.unanswered_questions
        if q.hypothesis_id not in current
        and set(q.distinguishes_hypothesis_ids) & current
    ]


def note(state: InvestigationState, record: TriageTestRecord) -> None:
    """Keep a record once: the same finding seen again adds nothing."""
    # Variables:
    #   key: The finding without its stage and tick, so a check repeated on
    #     every loop turn is recorded once.
    key = record.model_dump(exclude={"stage", "tick"})
    if all(
        r.model_dump(exclude={"stage", "tick"}) != key
        for r in state.triage_test_records
    ):
        state.triage_test_records.append(record)


def reading_rows(data: object) -> list[tuple[int, float]] | None:
    """(tick, value) rows from a get_readings answer, or None for another shape."""
    # Variables:
    #   value: One row's reading; a non-number makes the answer not readings.
    if not isinstance(data, list):
        return None
    rows = []
    for row in data:
        if not isinstance(row, dict) or type(row.get("tick")) is not int:
            return None
        value = row.get("value")
        if type(value) not in (int, float):
            return None
        rows.append((row["tick"], float(value)))
    return rows


def statistic_of(values: list[float], statistic: str) -> float:
    """One summary number of some readings in tick order."""
    # Variables:
    #   values: The readings inside the predicate's window, oldest first, so
    #     the last one is the end value.
    #   statistic: Which number the predicate compares with its threshold.
    if statistic == "mean":
        return fmean(values)
    if statistic == "minimum":
        return min(values)
    if statistic == "maximum":
        return max(values)
    return values[-1]


def judge(predicate: Predicate, evidence: Evidence, data: object) -> PredicateResult:
    """One piece of evidence of the predicate's sensor, judged on its own."""
    # Variables:
    #   p: The predicate: window, statistic, comparison, threshold, samples.
    #   rows: Raw readings, or None when the answer is a summary.
    #   window: A summary's own tick window; it must lie inside the predicate's.
    #   count: Valid samples behind the measured value.
    #   value: The measured statistic compared with the threshold.
    p = predicate
    ids = (evidence.id,)
    rows = reading_rows(data)
    if rows is not None:
        inside = sorted((t, v) for t, v in rows if p.from_tick <= t <= p.to_tick)
        if not inside:
            verdict = "stale" if rows else "unavailable"
            reason = "no readings inside the window" if rows else "no readings"
            return PredicateResult(verdict=verdict, reason=reason, evidence_ids=ids)
        count = len(inside)
        value = statistic_of([v for _, v in inside], p.statistic)
    elif isinstance(data, dict) and "sample_count" in data:
        window = (data.get("from_tick"), data.get("to_tick"))
        count = data.get("sample_count")
        if not all(type(t) is int for t in window) or type(count) is not int:
            return PredicateResult(
                verdict="unavailable",
                reason="summary without a window",
                evidence_ids=ids,
            )
        if window[0] < p.from_tick or window[1] > p.to_tick:
            return PredicateResult(
                verdict="stale",
                reason="summary window is not inside the predicate's window",
                evidence_ids=ids,
            )
        measured = data.get(p.statistic)
        if count == 0 or type(measured) not in (int, float):
            return PredicateResult(
                verdict="unavailable",
                reason="no samples in the summary",
                evidence_ids=ids,
            )
        value = float(measured)
    else:
        return PredicateResult(
            verdict="unavailable",
            reason="answer is not readings or a summary",
            evidence_ids=ids,
        )
    if count < p.min_samples:
        return PredicateResult(
            verdict="insufficient",
            reason=f"{count} samples, {p.min_samples} needed",
            sample_count=count,
            evidence_ids=ids,
        )
    holds = value > p.threshold if p.comparison == "above" else value < p.threshold
    return PredicateResult(
        verdict="true" if holds else "false",
        reason=f"{p.statistic} {value:g} {p.comparison} {p.threshold:g}",
        value=value,
        sample_count=count,
        evidence_ids=ids,
    )


def evaluate(predicate: Predicate, state: InvestigationState) -> PredicateResult:
    """The predicate's verdict from the observable evidence gathered so far.

    Only evidence the factory answered counts (never memory or the manual),
    and only evidence of the predicate's own machine sensor. The newest of the
    most definite verdicts wins.
    """
    # Variables:
    #   root: The machine sensor the predicate is about.
    #   observed: Ids of evidence the factory itself answered.
    #   best: The verdict so far; a later one of equal or higher rank replaces it.
    root = root_of(predicate.machine_id, predicate.sensor)
    observed = {p.evidence_id for p in state.provenance if p.origin == "observable"}
    best = PredicateResult(
        verdict="unavailable", reason=f"no observed reading of {root}"
    )
    for evidence in state.evidence:
        if evidence.id not in observed or physical_root(state, evidence) != root:
            continue
        try:
            data = json.loads(evidence.content)
        except ValueError:
            continue
        result = judge(predicate, evidence, data)
        if RANK[result.verdict] >= RANK[best.verdict]:
            best = result
    return best
