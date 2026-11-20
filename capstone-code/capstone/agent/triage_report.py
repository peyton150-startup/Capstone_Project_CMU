"""The read-only triage report, built after the Python checks (Block 5).

A rapid triage ends with one model call, `conclude`, and then the Python checks
(`check_conclusion`, `triage_clearance_gaps`, `needs_deep_run`), which may hold
the answer open or escalate it but never choose a cause. This module turns
what survived into one typed, source-linked report for a technician:

- When the model concluded, the report carries its diagnosis as the checks
  left it, the evidence it cited (each item linked to the tool and tick it came
  from), and every reason the checks held it open.
- When no model answered, or the answer broke a rule and was refused, the
  report carries no diagnosis at all: only what was read and when, and the
  escalation. A missing answer is never written up as a cause, and never as
  "nothing wrong".

Nothing here changes what the agent decides; the report is built from state
the investigation already holds. Deep runs never build one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from capstone.contracts import Contract

if TYPE_CHECKING:
    from capstone.agent.state import InvestigationState

# The most characters of a reading's content a finding repeats; the evidence id
# leads to the whole reading.
EXCERPT_CHARS = 160
# The most readings a report without a model conclusion lists; the rest are
# counted in the summary.
MAX_UNCONCLUDED_FINDINGS = 12

ReportOutcome = Literal["model_conclusion", "model_answer_refused", "no_model_answer"]


class ReportRankingPick(Contract):
    """One ranked candidate as a technician reads it: the model's belief only."""

    candidate_id: str
    family: str
    machine_id: str | None = None
    explanation: str
    # The model's own uncalibrated belief, 0-1; never a measured probability.
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    missing_checks: tuple[str, ...] = ()


class ReportRanking(Contract):
    """The checked two-candidate ranking (TRIAGE_RANKING), beside the report.

    It never changed the assessment, recommendation or any action above it.
    `picks` is empty unless the status is "accepted".
    """

    status: Literal["accepted", "abstained", "rejected", "unavailable"]
    reason: str
    abstain_reason: str | None = None
    attempts: tuple[str, ...] = ()
    requests: int = Field(ge=0)
    snapshot_fingerprint: str
    candidate_count: int = Field(ge=0)
    picks: tuple[ReportRankingPick, ...] = ()


def report_ranking(state: InvestigationState) -> ReportRanking | None:
    """The ranking for the report, with each pick's family as shown; None if none."""
    # Variables:
    #   verdict: The checked ranking, or None when TRIAGE_RANKING was off.
    #   shown: Each snapshot candidate by id, so a pick is reported with what
    #     its TC id meant when the model saw it, not a later recompile.
    verdict = state.triage_ranking
    snapshot = state.triage_ranking_snapshot
    if verdict is None or snapshot is None:
        return None
    shown = {c.id: c for c in snapshot.candidates}
    return ReportRanking(
        status=verdict.status,
        reason=verdict.reason,
        abstain_reason=verdict.abstain_reason,
        attempts=state.triage_ranking_attempts,
        requests=state.triage_ranking_requests,
        snapshot_fingerprint=verdict.snapshot_fingerprint,
        candidate_count=len(snapshot.candidates),
        picks=tuple(
            ReportRankingPick(
                candidate_id=p.candidate_id,
                family=shown[p.candidate_id].family,
                machine_id=shown[p.candidate_id].machine_id,
                explanation=shown[p.candidate_id].explanation,
                confidence=p.confidence,
                rationale=p.rationale,
                evidence_ids=p.evidence_ids,
                contradicting_evidence_ids=p.contradicting_evidence_ids,
                missing_checks=p.missing_checks,
            )
            for p in verdict.picks
        ),
    )


class ReportFinding(Contract):
    """One reading the report rests on, linked to where it came from."""

    evidence_id: str
    # The tool that answered, as "simulator:get_sensor_summary" and the like.
    source_id: str
    # "observable" for the factory's own answers; "manual" or "memory" for
    # guidance and past beliefs, which are never readings of this machine now.
    origin: str | None = None
    observed_tick: int | None = Field(default=None, ge=0)
    excerpt: str


class TriageReport(Contract):
    """What a triage found, after the Python checks, as a technician reads it."""

    machine_id: str | None
    alarm: str
    alarm_tick: int = Field(ge=0)
    outcome: ReportOutcome
    # Why the run stopped: "timeout", "model_unavailable" and the like. None
    # when it ended normally.
    termination_reason: str | None = None
    # The model's diagnosis as the checks left it. Always None without a model
    # conclusion: Python never writes a cause.
    diagnosis: str | None = None
    assessment: Literal["supported", "unresolved"]
    # After the checks; and what the model itself said before them.
    recommendation: Literal["intervene", "no_action", "escalate"]
    model_recommendation: str | None = None
    confidence: float = Field(ge=0, le=1)
    deep_recommended: bool
    # Every reason the checks held the answer open, in the order found.
    held_open_because: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    next_check: str | None = None
    # With a model conclusion: the evidence it cited. Without one: what was
    # read from the factory, at most MAX_UNCONCLUDED_FINDINGS.
    findings: tuple[ReportFinding, ...] = ()
    # Why a model answer was refused, when it was.
    refused_because: str | None = None
    summary: str
    # The checked two-candidate ranking when TRIAGE_RANKING was on; None
    # otherwise and in reports saved before it.
    ranking: ReportRanking | None = None


def report_outcome(state: InvestigationState) -> ReportOutcome:
    """Whether the triage's conclusion came from the model, and if not, why."""
    # Variables:
    #   state.conclusion_rejected: Set when the model answered but broke a rule
    #     (for example cited evidence never gathered), so its answer was refused.
    #   state.policy_recommendation: Set only when a model answer passed into
    #     the checks; None when time ran out or no model answered.
    if state.conclusion_rejected is not None:
        return "model_answer_refused"
    if state.policy_recommendation is None:
        return "no_model_answer"
    return "model_conclusion"


def finding(state: InvestigationState, evidence_id: str) -> ReportFinding | None:
    """One gathered reading as a report finding, or None if it was never gathered."""
    # Variables:
    #   origins: Where each evidence id came from ("observable", "manual",
    #     "memory"), from the provenance kept beside the evidence.
    origins = {p.evidence_id: p.origin for p in state.provenance}
    for evidence in state.evidence:
        if evidence.id == evidence_id:
            text = " ".join(evidence.content.split())
            return ReportFinding(
                evidence_id=evidence.id,
                source_id=evidence.source_id,
                origin=origins.get(evidence.id),
                observed_tick=evidence.observed_tick,
                excerpt=text
                if len(text) <= EXCERPT_CHARS
                else text[: EXCERPT_CHARS - 3] + "...",
            )
    return None


def build_triage_report(state: InvestigationState) -> TriageReport:
    """The triage's report, built from its checked conclusion and evidence."""
    # Variables:
    #   outcome: Whether the model concluded; anything else gets no diagnosis.
    #   conclusion: The checked conclusion; UNDETERMINED ("escalate", no
    #     assessment) when no model answer survived.
    #   gaps: The checks' reasons for holding the answer open, from the
    #     conclusion trace; empty when no answer reached the checks.
    #   observed: Ids of the factory's own readings, in the order gathered;
    #     the findings of a report without a model conclusion.
    #   reason: The termination reason's value, for the summary.
    outcome = report_outcome(state)
    conclusion = state.conclusion
    if conclusion is None:
        raise ValueError("a triage report needs the conclusion stage to have run")
    trace = state.conclusion_trace
    gaps = () if trace is None else tuple(dict.fromkeys(g.text for g in trace.gaps))
    reason = (
        None if state.termination_reason is None else state.termination_reason.value
    )
    anomaly = state.anomaly
    if outcome == "model_conclusion":
        findings = tuple(
            f for f in (finding(state, i) for i in conclusion.evidence_ids) if f
        )
        assessment = conclusion.assessment or "unresolved"
        summary = (
            f"{assessment}: {conclusion.diagnosis} (confidence "
            f"{conclusion.confidence:.2f}); {conclusion.recommendation}"
            + (
                "; a deep investigation should follow."
                if state.deep_recommended
                else "."
            )
        )
        return TriageReport(
            machine_id=anomaly.machine_id,
            alarm=anomaly.description,
            alarm_tick=anomaly.tick,
            outcome=outcome,
            termination_reason=reason,
            diagnosis=conclusion.diagnosis,
            assessment=assessment,
            recommendation=conclusion.recommendation,
            model_recommendation=state.policy_recommendation,
            confidence=conclusion.confidence,
            deep_recommended=bool(state.deep_recommended),
            held_open_because=gaps,
            unresolved_questions=conclusion.unresolved_questions,
            next_check=conclusion.next_check,
            findings=findings,
            summary=summary,
            ranking=report_ranking(state),
        )
    observed = [p.evidence_id for p in state.provenance if p.origin == "observable"]
    findings = tuple(
        f for f in (finding(state, i) for i in observed[:MAX_UNCONCLUDED_FINDINGS]) if f
    )
    why = (
        "the model's answer was refused"
        if outcome == "model_answer_refused"
        else f"no model answered ({reason or 'no reason recorded'})"
    )
    more = len(observed) - len(findings)
    summary = (
        f"No conclusion: {why}. {len(observed)} reading(s) were taken"
        + (f" ({more} not listed)" if more > 0 else "")
        + "; nothing is concluded about the cause, and nothing is cleared. "
        "Escalated for a deep investigation."
    )
    return TriageReport(
        machine_id=anomaly.machine_id,
        alarm=anomaly.description,
        alarm_tick=anomaly.tick,
        outcome=outcome,
        termination_reason=reason,
        assessment="unresolved",
        recommendation="escalate",
        model_recommendation=state.policy_recommendation,
        confidence=0.0,
        deep_recommended=True,
        findings=findings,
        refused_because=state.conclusion_rejected,
        summary=summary,
        ranking=report_ranking(state),
    )
