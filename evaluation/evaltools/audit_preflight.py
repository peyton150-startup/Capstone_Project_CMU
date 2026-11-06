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
    missing = cited - set(evidence_ids)
    if missing:
        issues.append(f"unknown cited evidence IDs: {sorted(missing)[:3]}")
    return issues


def require_full_traces(packets: Sequence[RunEvidencePacket]) -> None:
    """Refuse a new cohort whose audit evidence cannot support RUN questions."""
    # Variables:
    #   problems: Episode identities and their trace issues, shown before any send.
    problems = [
        f"{packet.meta.episode_key}: {', '.join(issues)}"
        for packet in packets
        if (issues := trace_issues(packet))
    ]
    if problems:
        raise ValueError("incomplete audited cohort: " + "; ".join(problems[:5]))
