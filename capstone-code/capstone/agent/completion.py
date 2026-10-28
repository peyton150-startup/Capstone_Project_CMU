# Turns a finished investigation into the shared record, and keeps a full log.
# Responsibility: translate working memory honestly. It never upgrades an outcome.
"""What is left when an investigation ends.

Working memory lives for one run. Two things are made from it here:

    complete(state)       the shared `CompletedInvestigation`, which is what
                          reflection, memory and evaluation read
    audit_record(state)   that record plus everything else the run knew:
                          where the evidence came from, the proposal's
                          status, every decision, the loop's counts

`AuditLog` appends audit records to a file, one per line. It keeps every
investigation, right or wrong, including evidence text such as a human's
reason for rejecting a proposal. The agent has no tool that reads it.

The translation is by fixed rule. A check that was inconclusive stays
unverified, and a check that was never made is left out; no tick is ever
filled in to make a record look complete.
"""

from pathlib import Path

from capstone.agent.artifacts import (
    AgentConclusion,
    DetectedAnomaly,
    ProposalRecord,
    VerificationCheck,
)
from capstone.agent.state import DecisionRecord, InvestigationState, ReasoningMetrics
from capstone.contracts import Contract
from capstone.contracts.completed_investigations import (
    ActionProposal,
    Anomaly,
    CompletedInvestigation,
    Conclusion,
    VerificationResult,
)
from capstone.contracts.provenance import ProvenanceReference

# The loop's own calls whose answers say what became of the proposal.
ACTION_TOOLS = ("propose_action", "get_proposals", "execute_action")

# Runtime outcome -> (status, outcome) in the shared record.
VERIFIED = {
    "resolved": ("verified", "resolved"),
    "not_resolved": ("failed", "unresolved"),
    "inconclusive": ("unverified", "unknown"),
}


def action_evidence_ids(state: InvestigationState) -> tuple[str, ...]:
    """Evidence in which the factory reported the proposal, the decision, the start.

    This is how a human's approval or rejection reaches the shared record:
    as what the approval desk said, not as a status the agent filled in.
    """
    return tuple(
        evidence_id
        for decision in state.decisions
        if decision.tool in ACTION_TOOLS
        for evidence_id in decision.evidence_ids
    )


def shared_verification(check: VerificationCheck | None) -> VerificationResult | None:
    """Translate the check by rule. A check that was not made is left out."""
    if check is None or check.outcome not in VERIFIED or check.checked_tick is None:
        return None
    status, outcome = VERIFIED[check.outcome]
    return VerificationResult(
        status=status,
        outcome=outcome,
        summary=f"Predicted: {check.prediction}. Found: {outcome}.",
        evidence_ids=check.evidence_ids,
        observed_tick=check.checked_tick,
    )


def complete(state: InvestigationState) -> CompletedInvestigation:
    """The shared record of one finished investigation. Does not change `state`."""
    # Variables:
    #   proposed: The action proposal for the shared record, or None if none was made.
    #   cited: Evidence for the proposal: what the conclusion cited plus the approval
    #     desk's replies.
    if state.conclusion is None or state.termination_reason is None:
        raise ValueError("the investigation has not finished")
    proposed = None
    if state.proposed_action is not None:
        cited = (*state.conclusion.evidence_ids, *action_evidence_ids(state))
        proposed = ActionProposal(
            action=state.proposed_action.action,
            machine_id=state.proposed_action.machine_id,
            reason=state.proposed_action.reason,
            evidence_ids=tuple(dict.fromkeys(cited)),
        )
    return CompletedInvestigation(
        run_id=state.run_id,
        investigation_id=state.investigation_id,
        anomaly=Anomaly(
            summary=state.anomaly.description, symptoms=(state.anomaly.kind,)
        ),
        evidence=tuple(state.evidence),
        hypotheses=tuple(state.hypotheses),
        conclusion=Conclusion(
            diagnosis=state.conclusion.diagnosis,
            confidence=state.conclusion.confidence,
            evidence_ids=state.conclusion.evidence_ids,
        ),
        proposed_action=proposed,
        verification=shared_verification(state.verification),
        iterations_used=state.iteration_count,
        tool_calls_used=state.tool_call_count,
        termination_reason=state.termination_reason.value,
    )


class AuditRecord(Contract):
    """Everything one investigation knew when it ended. For people, not the agent."""

    completed: CompletedInvestigation
    provenance: tuple[ProvenanceReference, ...]
    anomaly: DetectedAnomaly
    conclusion: AgentConclusion
    proposal: ProposalRecord | None
    action_started_tick: int | None
    action_finish_tick: int | None
    verification: VerificationCheck | None
    decisions: tuple[DecisionRecord, ...]
    metrics: ReasoningMetrics


def audit_record(state: InvestigationState) -> AuditRecord:
    """The shared record together with the runtime detail it leaves out."""
    return AuditRecord(
        completed=complete(state),
        provenance=tuple(state.provenance),
        anomaly=state.anomaly,
        conclusion=state.conclusion,
        proposal=state.proposed_action,
        action_started_tick=state.action_started_tick,
        action_finish_tick=state.action_finish_tick,
        verification=state.verification,
        decisions=tuple(state.decisions),
        metrics=state.metrics(),
    )


class AuditLog:
    """An append-only file of audit records, one JSON object per line."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, record: AuditRecord) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(record.model_dump_json() + "\n")

    def read(self) -> tuple[AuditRecord, ...]:
        if not self.path.exists():
            return ()
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return tuple(AuditRecord.model_validate_json(line) for line in lines if line)
