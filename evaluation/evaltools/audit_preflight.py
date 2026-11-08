"""Check whether an episode has the evidence needed for trace-based judging."""

from collections.abc import Sequence

from evaltools.run_packet import RunEvidencePacket


def trace_issues(packet: RunEvidencePacket) -> list[str]:
    """Name missing or inconsistent audit evidence without inventing it."""
    # Variables:
    #   trace: The judge-visible account of the episode, built from its audit.
    #   evidence_ids: IDs the audit actually records, used to validate citations.
    #   cited: IDs the conclusion and hypotheses claim to have used.
    trace = packet.snap_view.trace
    if trace.completeness != "full" or packet.meta.audit_file is None:
        return ["audit log missing"]
    issues = []
    evidence_ids = [item.id for item in trace.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        issues.append("duplicate evidence IDs")
    if any(not item.content for item in trace.evidence):
        issues.append("empty evidence content")
    if any(not item.origin or item.origin == "unknown" for item in trace.evidence):
        issues.append("evidence lacks provenance origin")
    hypothesis_ids = [item.id for item in trace.hypotheses]
    if len(hypothesis_ids) != len(set(hypothesis_ids)):
        issues.append("duplicate hypothesis IDs")
    decision_sequences = [item.sequence for item in trace.decisions]
    if len(decision_sequences) != len(set(decision_sequences)):
        issues.append("duplicate decision sequences")
    if any(
        decision.tick is None or decision.arguments is None
        for decision in trace.decisions
    ):
        issues.append("decision lacks time or arguments")
    cited = set()
    if trace.conclusion is not None:
        cited.update(trace.conclusion.evidence_ids)
    for hypothesis in trace.hypotheses:
        cited.update(hypothesis.supporting_evidence_ids)
        cited.update(hypothesis.contradicting_evidence_ids)
        cited.update(hypothesis.unexplained_evidence_ids)
    for decision in trace.decisions:
        cited.update(decision.evidence_ids)
    if trace.recheck is not None and trace.recheck.evidence_id:
        cited.add(trace.recheck.evidence_id)
    if trace.verification is not None:
        cited.update(trace.verification.evidence_ids)
        verification = trace.verification
        if (
            verification.action_started_tick is not None
            and verification.action_finish_tick is not None
            and verification.action_finish_tick < verification.action_started_tick
        ):
            issues.append("action finish precedes start")
        if (
            verification.checked_tick is not None
            and verification.action_finish_tick is not None
            and verification.checked_tick < verification.action_finish_tick
        ):
            issues.append("verification precedes action finish")
    missing = cited - set(evidence_ids)
    if missing:
        issues.append(f"unknown cited evidence IDs: {sorted(missing)[:3]}")
    return issues


def require_full_traces(
    packets: Sequence[RunEvidencePacket], *, refused: Sequence[dict] = ()
) -> None:
    """Refuse a new cohort whose audit evidence cannot support RUN questions."""
    # Variables:
    #   problems: Episode identities and their trace issues, shown before any send.
    #   refused: Packets rejected by the hidden-truth check before trace checking.
    problems = [
        f"{packet.meta.episode_key}: {', '.join(issues)}"
        for packet in packets
        if (issues := trace_issues(packet))
    ]
    problems.extend(
        f"{item['episode_key']}: refused packet ({item['reason']})" for item in refused
    )
    if problems:
        raise ValueError("incomplete audited cohort: " + "; ".join(problems[:5]))
