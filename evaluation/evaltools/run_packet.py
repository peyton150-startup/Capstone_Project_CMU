"""Build one run evidence packet per saved experiment record.

    uv run python -m evaltools.run_packet --records results.jsonl \\
        --labels labels.jsonl --audit audit.jsonl --commit <sha> --out packets/

A packet has two halves, kept apart on purpose:

- `snap_view`: what a judge may see. An opaque run reference, the
  configuration, the anomaly, the trace (evidence, hypotheses, decisions, critique, conclusion,
  verification), and the code-computed facts that need no hidden truth.
  It never holds the true fault, the true machine or batch, or any score
  field derived from hidden state, so a judge of investigation quality
  cannot anchor on the answer. The run key and scenario id sit in `meta`,
  which is never sent: scenario ids name the fault (`KA-01-bearing`).
- `evaluator_only`: the deterministic metrics that compare the run with the
  hidden truth (root-cause correctness from the label, the right action,
  resolution, evidence share, miss kind, verification calibration). Code
  computes them; Snap is never asked to.

The trace half is complete only when the run was made with `--audit`
(`capstone.agent.completion.AuditLog`): an `ExperimentRecord` alone keeps
tool names, counts, the conclusion and the scores, not the evidence or the
hypotheses. A packet built without an audit log says so in
`trace.completeness` and the judge questions that need the trace are
expected to answer "unknown".

The JSON schema committed as `evaluation/RUN_EVIDENCE_SCHEMA.json` is
generated from `RunEvidencePacket.model_json_schema()`; a test keeps the two
in step.
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "capstone-code"))

from capstone.agent.completion import AuditLog, AuditRecord  # noqa: E402
from capstone.contracts.investigations import run_id_for  # noqa: E402
from capstone.evaluation.labels import Label, LabelBook, apply_label  # noqa: E402
from capstone.experiment import ExperimentRecord, read_records  # noqa: E402

# 1.1.0: what a record-only trace does not keep (decision arguments,
# confidence, information needed; machines and sensors read) is null, not 0.0,
# "" or empty.
PACKET_SCHEMA_VERSION = "1.1.0"
RUBRIC_VERSION = "1.0.0"

# A committed answer at least this sure that is wrong is "confident and
# wrong" (the same line `capstone.evals.CONFIDENT` draws).
CONFIDENT = 0.8
# How much of each evidence item's content a packet keeps. The full audit
# record stays on disk; the packet is what a judge reads.
EVIDENCE_CHARS = 1500


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PacketMeta(Strict):
    packet_schema_version: str = PACKET_SCHEMA_VERSION
    rubric_version: str = RUBRIC_VERSION
    # The run's key and scenario id stay here, never in `snap_view`: scenario
    # ids name the fault (`KA-01-bearing`, `KA-07-false-alarm`), so a judge who
    # saw them would know the answer it is meant to judge the agent on.
    run_key: str
    scenario_id: str
    commit_sha: str | None = None
    records_file: str
    audit_file: str | None = None
    labels_file: str | None = None
    # SHA-256 of the record line the packet was built from, so a packet can
    # be traced to its exact source row.
    record_digest: str


class Configuration(Strict):
    """What the run was configured with, as far as the record says."""

    step_questions: int | None = None
    state_action_bar: bool | None = None
    critic: Literal["off", "anchored", "blind"] | None = None
    critic_followup_on: bool | None = None
    manual_offered: bool | None = None
    manual_step: bool | None = None
    memory_offered: bool | None = None
    tree_of_thought: bool | None = None
    hazards: str | None = None
    models_answering: dict[str, int] = Field(default_factory=dict)


class EvidenceItem(Strict):
    id: str
    tool: str | None
    arguments: dict[str, Any] = Field(default_factory=dict)
    origin: str
    observed_tick: int | None
    content: str
    truncated: bool = False


class HypothesisView(Strict):
    id: str
    claim: str
    confidence: float
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    unexplained_evidence_ids: list[str] = Field(default_factory=list)
    expected_observations: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    discriminating_check: str | None = None


class DecisionView(Strict):
    """One decision; in a record-only trace the fields the record does not
    keep (arguments, confidence, information needed) are None, never a
    made-up value a judge could read as the agent's."""

    sequence: int
    agent: str
    phase: str
    tick: int | None
    tool: str | None
    arguments: dict[str, Any] | None = Field(default_factory=dict)
    outcome: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None
    information_needed: str | None
    error: str | None = None


class ConclusionView(Strict):
    diagnosis: str
    confidence: float
    recommendation: str
    policy_recommendation: str | None = None
    recommendation_lowered: str | None = None
    assessment: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    next_check: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    hypothesis_id: str | None = None


class CritiqueView(Strict):
    outcome: str
    blind: bool = False
    verdict: str | None = None
    favoured: str | None = None
    favoured_claim: str | None = None
    why: str | None = None
    discriminating_check: str | None = None
    objections: list[dict[str, Any]] = Field(default_factory=list)
    verdict_mismatch: str | None = None
    manual_sections: list[str] | None = None
    seconds: float | None = None


class RecheckView(Strict):
    outcome: str
    trigger: str | None = None
    reason: str | None = None
    # The open question the critic's check became, as shown to the policy.
    question: str | None = None
    tool: str | None = None
    evidence_id: str | None = None
    leading_before: str | None = None
    confidence_before: float | None = None
    leading_after: str | None = None
    confidence_after: float | None = None


class VerificationView(Strict):
    outcome: str | None
    prediction: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    checked_tick: int | None = None
    action_started_tick: int | None = None
    action_finish_tick: int | None = None


class Trace(Strict):
    completeness: Literal["full", "record_only"]
    anomaly: str
    anomaly_kind: str | None = None
    anomaly_machine: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    hypotheses: list[HypothesisView] = Field(default_factory=list)
    pruned_candidates: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[DecisionView] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    conclusion: ConclusionView | None = None
    critique: CritiqueView | None = None
    recheck: RecheckView | None = None
    verification: VerificationView | None = None
    proposal: dict[str, Any] | None = None
    manual_searches: list[dict[str, Any]] = Field(default_factory=list)
    recall_searches: list[dict[str, Any]] = Field(default_factory=list)


class ObservableFacts(Strict):
    """Code-computed facts that need no hidden truth."""

    termination_reason: str | None
    finished_on_time: bool | None
    tool_calls: int
    factory_calls: int | None
    iterations: int
    ticks_elapsed: int
    wall_seconds: float | None
    model_questions: int | None
    model_answered: int | None
    invalid_replies: int | None
    unanswered: int | None
    outage_attempts: int | None
    # None when the trace is record-only: the record keeps no tool arguments,
    # so which machines and sensors were read is unknown, not "none".
    machines_examined: list[str] | None = Field(default_factory=list)
    sensors_read: dict[str, list[str]] | None = Field(default_factory=dict)
    repeated_calls: int = 0
    failed_tool_calls: int = 0
    committed: bool | None = None
    confidence: float | None = None
    evidence_cited_by_conclusion: int | None = None
    observable_evidence_cited: int | None = None
    # How many cited items came from each origin (observable, manual, memory):
    # the deterministic half of "was the manual used, not only retrieved".
    cited_by_origin: dict[str, int] = Field(default_factory=dict)
    hazards_fired: list[str] | None = None
    hazards_retried: int | None = None
    blackout_recovered: bool | None = None


class SnapView(Strict):
    # An opaque reference to the run (the first 12 hex digits of the SHA-256
    # of its key), so a judge's answer can be traced without naming the case.
    run_ref: str
    configuration: Configuration
    trace: Trace
    facts: ObservableFacts


class EvaluatorOnly(Strict):
    """Deterministic truth comparisons. Never sent to a judge of quality."""

    true_faults: list[dict[str, Any]]
    distractors: list[dict[str, Any]]
    label: dict[str, Any] | None
    labelled_by: str | None
    root_cause_correct: bool | None
    target_correct: bool | None
    fully_right: bool | None
    causes_found: int | None
    wrong_causes: int | None
    recommendation_correct: bool
    action_correct: bool
    resolved: bool
    unnecessary_interventions: list[str]
    false_intervention: bool
    relevant_evidence: list[str]
    relevant_evidence_collected: list[str]
    evidence_share: float | None
    miss_kind: str | None
    abstained: bool | None
    confident_wrong: bool | None
    # The agent's own verification verdict against the truth of resolution.
    verification_calibration: Literal[
        "true_resolved",
        "true_unresolved",
        "false_resolved",
        "false_unresolved",
        "inconclusive",
        "not_performed",
        "no_verdict",
    ]
    model_unavailable: bool
    critic_pick_label: dict[str, Any] | None = None
    critic_pick_correct: bool | None = None


class RunEvidencePacket(Strict):
    meta: PacketMeta
    snap_view: SnapView
    evaluator_only: EvaluatorOnly


# --- building ---------------------------------------------------------------------------


def configuration_of(record: ExperimentRecord) -> Configuration:
    """What the run was configured with, as far as the record says (None: unknown)."""
    # Variables:
    #   critic: blind or anchored from the critique record; None without one.
    #     The record keeps no critic setting, and a critic-on run that timed out
    #     or lost its model before the critique has no record either, so "off"
    #     cannot be told from "never reached" and is never claimed.
    #   hazards: blackout when the blackout fields were kept or a blackout fired
    #     (the same reading `capstone.evals.report_of` uses), else standard;
    #     None when the tools were reliable.
    critique = record.critique
    critic = None
    if critique is not None:
        critic = "blind" if critique.blind else "anchored"
    hazards = None
    if record.hazards_fired is not None:
        blackout = record.blackout_recovered is not None or any(
            fired.startswith("blackout on ") for fired in record.hazards_fired
        )
        hazards = "blackout" if blackout else "standard"
    return Configuration(
        step_questions=record.step_questions,
        state_action_bar=record.state_action_bar,
        critic=critic,
        critic_followup_on=None if record.recheck is None else True,
        manual_offered=record.manual_searches is not None,
        manual_step=(
            None
            if record.manual_searches is None
            else any(s.automatic for s in record.manual_searches)
        ),
        memory_offered=record.memory_uses is not None,
        tree_of_thought=None if record.thoughts is None else True,
        hazards=hazards,
        models_answering=dict(record.model_calls.answered_by)
        if record.model_calls is not None
        else {},
    )


def trace_from_audit(record: ExperimentRecord, audit: AuditRecord) -> Trace:
    origins = {p.evidence_id: p.origin for p in audit.provenance}
    asked: dict[str, tuple[str | None, dict]] = {}
    for decision in audit.decisions:
        for evidence_id in decision.evidence_ids:
            asked.setdefault(evidence_id, (decision.tool, dict(decision.arguments)))
    evidence = []
    for item in audit.completed.evidence:
        tool, arguments = asked.get(item.id, (None, {}))
        content = item.content
        evidence.append(
            EvidenceItem(
                id=item.id,
                tool=tool,
                arguments=arguments,
                origin=origins.get(item.id, "unknown"),
                observed_tick=item.observed_tick,
                content=content[:EVIDENCE_CHARS],
                truncated=len(content) > EVIDENCE_CHARS,
            )
        )
    conclusion = audit.conclusion
    critique = record.critique
    critique_view = None
    if critique is not None:
        result = critique.result
        critique_view = CritiqueView(
            outcome=critique.outcome,
            blind=critique.blind,
            verdict=None if result is None else result.verdict,
            favoured=None if result is None else result.favoured,
            favoured_claim=critique.favoured_claim,
            why=None if result is None else result.why,
            discriminating_check=(
                None if result is None else result.discriminating_check
            ),
            objections=[]
            if result is None
            else [o.model_dump() for o in result.objections],
            verdict_mismatch=critique.verdict_mismatch,
            manual_sections=(
                None
                if critique.manual_sections is None
                else list(critique.manual_sections)
            ),
            seconds=critique.seconds,
        )
    recheck = record.recheck
    verification = audit.verification
    return Trace(
        completeness="full",
        anomaly=audit.anomaly.description,
        anomaly_kind=audit.anomaly.kind,
        anomaly_machine=audit.anomaly.machine_id,
        evidence=evidence,
        hypotheses=[
            HypothesisView(
                id=h.id,
                claim=h.claim,
                confidence=h.confidence,
                supporting_evidence_ids=list(h.supporting_evidence_ids),
                contradicting_evidence_ids=list(h.contradicting_evidence_ids),
                unexplained_evidence_ids=list(h.unexplained_evidence_ids),
                expected_observations=list(h.expected_observations),
                assumptions=list(h.assumptions),
                discriminating_check=h.discriminating_check,
            )
            for h in audit.completed.hypotheses
        ],
        pruned_candidates=[p.model_dump() for p in audit.pruned_candidates],
        decisions=[
            DecisionView(
                sequence=d.sequence,
                agent=d.agent,
                phase=d.phase,
                tick=d.tick,
                tool=d.tool,
                arguments=dict(d.arguments),
                outcome=d.outcome,
                evidence_ids=list(d.evidence_ids),
                confidence=d.confidence,
                information_needed=d.information_needed,
                error=None if d.error is None else f"{d.error.code}: {d.error.message}",
            )
            for d in audit.decisions
        ],
        tools_used=list(record.tools_used),
        conclusion=ConclusionView(
            diagnosis=conclusion.diagnosis,
            confidence=conclusion.confidence,
            recommendation=conclusion.recommendation,
            policy_recommendation=record.policy_recommendation,
            recommendation_lowered=record.recommendation_lowered,
            assessment=conclusion.assessment,
            unresolved_questions=list(conclusion.unresolved_questions),
            next_check=conclusion.next_check,
            evidence_ids=list(conclusion.evidence_ids),
            hypothesis_id=conclusion.hypothesis_id,
        ),
        critique=critique_view,
        recheck=None if recheck is None else RecheckView(**recheck.model_dump()),
        verification=VerificationView(
            outcome=None if verification is None else verification.outcome,
            prediction=None if verification is None else verification.prediction,
            evidence_ids=[]
            if verification is None
            else list(verification.evidence_ids),
            checked_tick=None if verification is None else verification.checked_tick,
            action_started_tick=audit.action_started_tick,
            action_finish_tick=audit.action_finish_tick,
        ),
        proposal=None if audit.proposal is None else audit.proposal.model_dump(),
        manual_searches=[s.model_dump() for s in record.manual_searches or ()],
        recall_searches=[s.model_dump() for s in record.recall_searches or ()],
    )


def trace_from_record(record: ExperimentRecord) -> Trace:
    """The trace an `ExperimentRecord` alone allows, marked `record_only`."""
    # Variables:
    #   decisions: The record's decision steps; tool and outcome are kept, while
    #     arguments, confidence and information needed are None (not recorded).
    critique = record.critique
    critique_view = None
    if critique is not None:
        result = critique.result
        critique_view = CritiqueView(
            outcome=critique.outcome,
            blind=critique.blind,
            verdict=None if result is None else result.verdict,
            favoured=None if result is None else result.favoured,
            favoured_claim=critique.favoured_claim,
            why=None if result is None else result.why,
            discriminating_check=(
                None if result is None else result.discriminating_check
            ),
            objections=[]
            if result is None
            else [o.model_dump() for o in result.objections],
            verdict_mismatch=critique.verdict_mismatch,
            manual_sections=(
                None
                if critique.manual_sections is None
                else list(critique.manual_sections)
            ),
            seconds=critique.seconds,
        )
    conclusion = None
    if record.conclusion is not None:
        conclusion = ConclusionView(
            diagnosis=record.conclusion,
            confidence=record.confidence or 0.0,
            recommendation=record.recommendation or "unknown",
            policy_recommendation=record.policy_recommendation,
            recommendation_lowered=record.recommendation_lowered,
            assessment=record.assessment,
            unresolved_questions=list(record.unresolved_questions),
            next_check=record.next_check,
        )
    decisions = [
        DecisionView(
            sequence=number,
            agent=step.agent,
            phase=step.phase,
            tick=None,
            tool=step.tool,
            arguments=None,
            outcome=step.outcome,
            confidence=None,
            information_needed=None,
        )
        for number, step in enumerate(
            (s for s in record.agent_steps or () if s.kind == "decision"), start=1
        )
    ]
    return Trace(
        completeness="record_only",
        anomaly=record.anomaly,
        decisions=decisions,
        tools_used=list(record.tools_used),
        conclusion=conclusion,
        critique=critique_view,
        recheck=(
            None
            if record.recheck is None
            else RecheckView(**record.recheck.model_dump())
        ),
        verification=VerificationView(outcome=record.verification),
        manual_searches=[s.model_dump() for s in record.manual_searches or ()],
        recall_searches=[s.model_dump() for s in record.recall_searches or ()],
    )


def facts_of(record: ExperimentRecord, trace: Trace) -> ObservableFacts:
    """The code-computed facts of one run that need no hidden truth."""
    # Variables:
    #   full: True when the trace came from an audit log; only then are the
    #     decisions' arguments, and so the machines and sensors read, known.
    #   machines, sensors: What the decisions' arguments name, by machine.
    #   repeated, failed: Decisions refused as repeats, and tool calls that failed;
    #     the record keeps outcomes, so these are known either way.
    #   origins: Each evidence item's origin, for counting what the conclusion cites.
    score = record.score
    calls = record.model_calls
    full = trace.completeness == "full"
    machines: set[str] = set()
    sensors: dict[str, set[str]] = {}
    repeated = failed = 0
    for decision in trace.decisions:
        arguments = decision.arguments or {}
        machine = arguments.get("machine_id")
        if isinstance(machine, str):
            machines.add(machine)
            sensor = arguments.get("sensor")
            if isinstance(sensor, str):
                sensors.setdefault(machine, set()).add(sensor)
        repeated += decision.outcome == "repeated_call"
        failed += decision.outcome == "tool_error"
    conclusion = trace.conclusion
    origins = {item.id: item.origin for item in trace.evidence}
    observable_ids = {e for e, origin in origins.items() if origin == "observable"}
    cited = None if conclusion is None else conclusion.evidence_ids
    return ObservableFacts(
        termination_reason=score.termination_reason,
        finished_on_time=(
            None
            if score.termination_reason is None
            else score.termination_reason != "timeout"
        ),
        tool_calls=score.tool_calls,
        factory_calls=record.factory_calls,
        iterations=score.iterations,
        ticks_elapsed=score.ticks_elapsed,
        wall_seconds=record.wall_seconds,
        model_questions=None if calls is None else calls.questions,
        model_answered=None if calls is None else calls.answered,
        invalid_replies=None if calls is None else calls.invalid_replies,
        unanswered=None if calls is None else calls.unanswered,
        outage_attempts=None if calls is None else calls.outage_attempts,
        machines_examined=sorted(machines) if full else None,
        sensors_read=(
            {m: sorted(s) for m, s in sorted(sensors.items())} if full else None
        ),
        repeated_calls=repeated,
        failed_tool_calls=failed,
        committed=None,  # filled from the label below
        confidence=record.confidence,
        evidence_cited_by_conclusion=None if cited is None else len(cited),
        observable_evidence_cited=(
            None
            if cited is None or trace.completeness != "full"
            else len(set(cited) & observable_ids)
        ),
        cited_by_origin=(
            {}
            if cited is None or trace.completeness != "full"
            else dict(
                sorted(Counter(origins[e] for e in cited if e in origins).items())
            )
        ),
        hazards_fired=record.hazards_fired,
        hazards_retried=record.hazards_retried,
        blackout_recovered=record.blackout_recovered,
    )


def calibration(record: ExperimentRecord) -> str:
    verdict = record.verification
    truth = record.score.resolved
    if verdict is None:
        return "no_verdict"
    if verdict in ("inconclusive", "not_performed"):
        return verdict
    if verdict == "resolved":
        return "true_resolved" if truth else "false_resolved"
    return "true_unresolved" if not truth else "false_unresolved"


def evaluator_only_of(
    record: ExperimentRecord, label: Label | None, critic_label: Label | None
) -> EvaluatorOnly:
    score = record.score
    scored = score if label is None else apply_label(score, label.diagnosis)
    judged = label is not None
    committed = None if not judged else label.diagnosis is not None
    correct = scored.fully_right if judged else None
    if judged and correct is None:  # older rows without causes
        correct = bool(scored.fault_correct and scored.target_correct)
    confident_wrong = (
        None
        if committed is None
        else bool(
            committed and correct is False and (record.confidence or 0) >= CONFIDENT
        )
    )
    share = (
        len(score.relevant_evidence_collected) / len(score.relevant_evidence)
        if score.relevant_evidence
        else None
    )
    critic_correct = None
    if critic_label is not None:
        critic_correct = apply_label(score, critic_label.diagnosis).fully_right
    return EvaluatorOnly(
        true_faults=[c.model_dump() for c in score.causes]
        or [
            {
                "fault": score.true_fault,
                "machine_id": score.true_machine_id,
                "batch_id": score.true_batch_id,
            }
        ],
        distractors=[c.model_dump() for c in score.distractors],
        label=None if label is None else json.loads(label.model_dump_json()),
        labelled_by=None if label is None else label.labelled_by,
        root_cause_correct=scored.fault_correct if judged else None,
        target_correct=scored.target_correct if judged else None,
        fully_right=correct,
        causes_found=scored.causes_found if judged else None,
        wrong_causes=scored.wrong_causes if judged else None,
        recommendation_correct=score.recommendation_correct,
        action_correct=score.action_correct,
        resolved=score.resolved,
        unnecessary_interventions=list(score.unnecessary_actions),
        false_intervention=bool(score.recommended_actions)
        and not score.recommendation_correct,
        relevant_evidence=list(score.relevant_evidence),
        relevant_evidence_collected=list(score.relevant_evidence_collected),
        evidence_share=share,
        miss_kind=scored.miss_kind if judged else None,
        abstained=None if committed is None else not committed,
        confident_wrong=confident_wrong,
        verification_calibration=calibration(record),
        model_unavailable=score.model_unavailable,
        critic_pick_label=(
            None if critic_label is None else json.loads(critic_label.model_dump_json())
        ),
        critic_pick_correct=critic_correct,
    )


def audit_by_run(path: Path | None) -> dict[str, AuditRecord]:
    if path is None:
        return {}
    return {str(r.completed.run_id): r for r in AuditLog(path).read()}


def build_packet(
    record: ExperimentRecord,
    line: str,
    *,
    label: Label | None,
    critic_label: Label | None,
    audit: AuditRecord | None,
    records_file: str,
    audit_file: str | None,
    labels_file: str | None,
    commit_sha: str | None,
) -> RunEvidencePacket:
    trace = (
        trace_from_record(record) if audit is None else trace_from_audit(record, audit)
    )
    facts = facts_of(record, trace)
    evaluator = evaluator_only_of(record, label, critic_label)
    facts = facts.model_copy(
        update={"committed": None if label is None else not evaluator.abstained}
    )
    return RunEvidencePacket(
        meta=PacketMeta(
            run_key=record.run_key,
            scenario_id=record.scenario_id,
            commit_sha=commit_sha,
            records_file=records_file,
            audit_file=audit_file,
            labels_file=labels_file,
            record_digest=hashlib.sha256(line.encode("utf-8")).hexdigest(),
        ),
        snap_view=SnapView(
            run_ref=run_ref(record.run_key),
            configuration=configuration_of(record),
            trace=trace,
            facts=facts,
        ),
        evaluator_only=evaluator,
    )


# Field names that exist only on the truth side (`Score`, `GroundTruth`, the
# packet's own `evaluator_only` half). None may appear anywhere in a judge's
# view, in any letter case. Prose words such as "distractor" are not listed:
# a model may write them in a hypothesis, and that is belief, not truth.
HIDDEN_WORDS = (
    "true_fault",
    "true_machine_id",
    "true_batch_id",
    "ground_truth",
    "evaluator_only",
    "expected_action",
    "wanted_actions",
    "relevant_evidence_collected",
    "causes_found",
    "wrong_causes",
)


def run_ref(run_key: str) -> str:
    """The judge-side name of a run: a hash, since the key names the scenario."""
    return hashlib.sha256(run_key.encode("utf-8")).hexdigest()[:12]


def check_no_truth_in_view(packet: RunEvidencePacket) -> None:
    """ValueError if the judge's half carries a truth field name, whatever its
    case, or the run's scenario id (which names the fault)."""
    # Variables:
    #   text: The judge's half as JSON, lower-cased so a name in another case is
    #     caught too.
    text = packet.snap_view.model_dump_json().lower()
    if packet.meta.scenario_id.lower() in text:
        raise ValueError(
            f"snap_view carries the scenario id {packet.meta.scenario_id!r}"
        )
    for word in HIDDEN_WORDS:
        if word in text:
            raise ValueError(f"snap_view carries {word!r}")


def build_all(
    records_path: Path,
    *,
    labels_path: Path | None = None,
    critic_labels_path: Path | None = None,
    audit_path: Path | None = None,
    commit_sha: str | None = None,
    refused: list[dict] | None = None,
) -> list[RunEvidencePacket]:
    """One packet per record, each checked for truth in the judge's view.

    With `refused` given, a packet that fails the check is left out and
    named there (run key and reason) so the rest of the batch is still
    built; without it the first failure raises, as a library call should.
    """
    # Variables:
    #   lines: The non-empty record lines, for each packet's record digest.
    #   audits: Audit records by run id; a run without one gets a record-only trace.
    #   refused: Where packets that failed the truth check are listed, or None
    #     to raise on the first.
    lines = [
        line for line in records_path.read_text(encoding="utf-8").splitlines() if line
    ]
    records = read_records(records_path)
    labels = LabelBook(labels_path).read() if labels_path else {}
    critic_labels = LabelBook(critic_labels_path).read() if critic_labels_path else {}
    audits = audit_by_run(audit_path)
    packets = []
    for line, record in zip(lines, records, strict=True):
        audit = audits.get(str(run_id_for(record.run_key)))
        packet = build_packet(
            record,
            line,
            label=labels.get(record.run_key),
            critic_label=critic_labels.get(record.run_key),
            audit=audit,
            # Forward slashes, so a packet built on Windows names its sources
            # the same way as one built anywhere else.
            records_file=records_path.as_posix(),
            audit_file=None if audit_path is None else audit_path.as_posix(),
            labels_file=None if labels_path is None else labels_path.as_posix(),
            commit_sha=commit_sha,
        )
        try:
            check_no_truth_in_view(packet)
        except ValueError as problem:
            if refused is None:
                raise
            refused.append({"run_key": record.run_key, "reason": str(problem)})
            continue
        packets.append(packet)
    return packets


def packet_file_name(run_key: str) -> str:
    """A packet's file name, valid on every operating system."""
    return re.sub(r'[<>:"\\|?*]', "_", run_key.replace("/", "__")) + ".json"


def batch_summary(packets: list[RunEvidencePacket]) -> dict:
    """Deterministic totals over a batch, with the denominators stated.

    Evidence share is reported two ways, as the rubric (section 6) and
    `capstone.evaluation.scoring.summarize` define it: pooled, every relevant
    item collected over every relevant item available across the reasoned
    runs; and as the mean of the per-run shares over the runs that had any
    relevant evidence (a run with none has no share and is left out, never
    counted as zero).
    """
    # Variables:
    #   reasoned: Packets where a model answered; outage runs are left out of
    #     every reasoning total, as `summarize` does (its `judged` counts only
    #     these too). An outage run's "no_conclusion" label would otherwise
    #     count as an abstention.
    #   judged: Reasoned packets whose label exists, so `fully_right` is True
    #     or False.
    #   committed: Judged packets whose label names a cause.
    #   cal: How many packets fall in each verification-calibration class.
    #   available, collected: Relevant evidence items that existed, and that were
    #     looked at, pooled over the reasoned runs.
    #   shares: The per-run evidence shares of the runs that had relevant evidence.
    #   timed: The reasoned runs whose wall time was recorded.
    reasoned = [p for p in packets if not p.evaluator_only.model_unavailable]
    judged = [p for p in reasoned if p.evaluator_only.fully_right is not None]
    committed = [p for p in judged if p.evaluator_only.abstained is False]
    cal = Counter(p.evaluator_only.verification_calibration for p in reasoned)
    available = sum(len(p.evaluator_only.relevant_evidence) for p in reasoned)
    collected = sum(len(p.evaluator_only.relevant_evidence_collected) for p in reasoned)
    shares = [
        p.evaluator_only.evidence_share
        for p in reasoned
        if p.evaluator_only.evidence_share is not None
    ]
    timed = [
        p.snap_view.facts.wall_seconds
        for p in reasoned
        if p.snap_view.facts.wall_seconds is not None
    ]
    return {
        "runs": len(packets),
        "model_unavailable": len(packets) - len(reasoned),
        "judged": len(judged),
        "root_cause_correct": sum(p.evaluator_only.fully_right is True for p in judged),
        "accuracy_when_committed": (
            sum(p.evaluator_only.fully_right is True for p in committed)
            / len(committed)
            if committed
            else None
        ),
        "abstained": sum(p.evaluator_only.abstained is True for p in judged),
        "confident_wrong": sum(
            p.evaluator_only.confident_wrong is True for p in judged
        ),
        "recommendation_correct": sum(
            p.evaluator_only.recommendation_correct for p in reasoned
        ),
        "action_correct": sum(p.evaluator_only.action_correct for p in reasoned),
        "resolved": sum(p.evaluator_only.resolved for p in reasoned),
        "false_interventions": sum(
            p.evaluator_only.false_intervention for p in reasoned
        ),
        "evidence_available": available,
        "evidence_collected": collected,
        "evidence_share": collected / available if available else None,
        "evidence_share_runs": len(shares),
        "evidence_share_mean": sum(shares) / len(shares) if shares else None,
        "miss_kinds": dict(
            Counter(
                p.evaluator_only.miss_kind for p in judged if p.evaluator_only.miss_kind
            )
        ),
        "verification_calibration": dict(sorted(cal.items())),
        "timeouts": sum(p.snap_view.facts.finished_on_time is False for p in reasoned),
        "mean_tool_calls": (
            sum(p.snap_view.facts.tool_calls for p in reasoned) / len(reasoned)
            if reasoned
            else None
        ),
        "timed_runs": len(timed),
        "mean_wall_seconds": sum(timed) / len(timed) if timed else None,
        "traces_complete": sum(
            p.snap_view.trace.completeness == "full" for p in packets
        ),
    }


def main(argv=None) -> int:
    """Build a batch's packets, its summary and, optionally, the packet schema."""
    # Variables:
    #   refused: Packets the truth check left out; listed in the summary so a
    #     smaller batch is never mistaken for the whole run.
    parser = argparse.ArgumentParser(prog="python -m evaltools.run_packet")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--critic-labels", type=Path)
    parser.add_argument("--audit", type=Path, help="audit log from --audit")
    parser.add_argument("--commit", help="the commit the run was made on")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--write-schema",
        type=Path,
        help="also write the JSON schema of a packet to this path",
    )
    args = parser.parse_args(argv)
    refused: list[dict] = []
    packets = build_all(
        args.records,
        labels_path=args.labels,
        critic_labels_path=args.critic_labels,
        audit_path=args.audit,
        commit_sha=args.commit,
        refused=refused,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    for packet in packets:
        (args.out / packet_file_name(packet.meta.run_key)).write_text(
            packet.model_dump_json(indent=1) + "\n", encoding="utf-8"
        )
    summary = batch_summary(packets)
    # A refused run is out of every total above, so the summary says so.
    summary["refused"] = refused
    if refused:
        print(f"{len(refused)} packet(s) refused by the truth check", file=sys.stderr)
    (args.out / "BATCH_SUMMARY.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8"
    )
    if args.write_schema is not None:
        args.write_schema.write_text(
            json.dumps(RunEvidencePacket.model_json_schema(), indent=1) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
