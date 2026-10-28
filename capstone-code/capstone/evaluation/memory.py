# Records memory promotion and attributed assessments of later memory use.
# Responsibility: report explicit outcomes without feeding evaluator truth to memory.
import json
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from capstone.contracts import Contract
from capstone.contracts.completed_investigations import CompletedInvestigation
from capstone.contracts.provenance import MEMORY_SOURCE
from capstone.memory.contracts import EpisodicMemory, PromotionDecision, RecalledMemory
from capstone.providers.recall import RECALL_TOOL, REPEATED_SEARCH, SEARCHES_SPENT

Effect = Literal["helped", "hurt", "neutral", "unknown"]
AssessmentSource = Literal["agent_report", "human_review", "evaluator"]


class MemoryPromotionRecord(Contract):
    """Evaluator-side report; correctness never grants promotion eligibility."""

    run_id: UUID
    investigation_id: UUID
    accepted: bool
    stored: bool
    reasons: tuple[str, ...] = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    memory_id: UUID | None = None
    existing_memory_id: UUID | None = None
    diagnosis_correct: bool | None = None

    @model_validator(mode="after")
    def consistent_storage(self):
        if self.accepted != (self.memory_id is not None):
            raise ValueError("only accepted decisions identify a proposed new memory")
        if self.stored and (not self.accepted or self.existing_memory_id is not None):
            raise ValueError("stored records must identify an accepted new memory")
        return self


class MemoryUseRecord(Contract):
    """An attributed assessment, not proof that memory caused the outcome."""

    consumer_run_id: UUID
    consumer_investigation_id: UUID
    memory_id: UUID
    retrieved: bool = True
    used: bool | None = None
    effect: Effect = "unknown"
    assessment_source: AssessmentSource | None = None
    evidence_ids: tuple[str, ...] = ()
    explanation: str | None = None

    @model_validator(mode="after")
    def supported_assessment(self):
        if self.used is True and not self.retrieved:
            raise ValueError("a used memory must have been retrieved")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("assessment evidence references must be unique")
        if self.effect != "unknown" and (
            self.used is not True
            or self.assessment_source is None
            or not self.evidence_ids
            or not self.explanation
            or not self.explanation.strip()
        ):
            raise ValueError(
                "a known effect needs an attributed, supported use assessment"
            )
        return self


def build_promotion_record(
    investigation: CompletedInvestigation,
    decision: PromotionDecision,
    *,
    diagnosis_correct: bool | None = None,
) -> MemoryPromotionRecord:
    """Associate a decision with its completed report without changing either."""
    # Variables:
    #   investigation: The finished investigation the decision belongs to.
    #   decision: What the memory gate decided about its lesson.
    #   diagnosis_correct: Whether the diagnosis was right, from the evaluator; it never
    #     grants promotion.
    #   memory: The memory the decision would store, if it was accepted.
    if decision.investigation_id != investigation.investigation_id:
        raise ValueError("promotion and investigation identities must match")
    memory = decision.memory
    if memory is not None:
        if memory.run_id != investigation.run_id:
            raise ValueError(
                "promotion memory and investigation run identities must match"
            )
        if memory.policy_version != decision.policy_version:
            raise ValueError("promotion memory and decision policy versions must match")
    return MemoryPromotionRecord(
        run_id=investigation.run_id,
        investigation_id=investigation.investigation_id,
        accepted=decision.accepted,
        stored=decision.stored,
        reasons=decision.reasons,
        policy_version=decision.policy_version,
        memory_id=memory.memory_id if memory is not None else None,
        existing_memory_id=decision.existing_memory_id,
        diagnosis_correct=diagnosis_correct,
    )


def build_use_record(
    investigation: CompletedInvestigation,
    memory: EpisodicMemory,
    *,
    retrieved: bool = True,
    used: bool | None = None,
    effect: Effect = "unknown",
    assessment_source: AssessmentSource | None = None,
    evidence_ids: tuple[str, ...] = (),
    explanation: str | None = None,
) -> MemoryUseRecord:
    """Record supplied use observations; never infer benefit from run success."""
    # Variables:
    #   retrieved: Whether the memory was actually returned by a search.
    #   used: Whether the agent's reasoning relied on it; None means not known.
    #   effect: helped, hurt, neutral or unknown; never inferred from the run's success.
    #   assessment_source: Who made the assessment: the agent, a person or the
    #     evaluator.
    if not set(evidence_ids) <= {e.id for e in investigation.evidence}:
        raise ValueError(
            "assessment references evidence absent from the consumer report"
        )
    return MemoryUseRecord(
        consumer_run_id=investigation.run_id,
        consumer_investigation_id=investigation.investigation_id,
        memory_id=memory.memory_id,
        retrieved=retrieved,
        used=used,
        effect=effect,
        assessment_source=assessment_source,
        evidence_ids=evidence_ids,
        explanation=explanation,
    )


def recalled_in(investigation: CompletedInvestigation) -> dict[UUID, tuple[str, ...]]:
    """Each memory an investigation recalled, with the evidence items that held it."""
    # Variables:
    #   found: For each recalled memory, the evidence items that carried it.
    found: dict[UUID, list[str]] = {}
    for evidence in investigation.evidence:
        if not evidence.source_id.startswith(f"{MEMORY_SOURCE}:"):
            continue
        for item in json.loads(evidence.content) or ():
            memory_id = RecalledMemory.model_validate(item).memory_id
            found.setdefault(memory_id, []).append(evidence.id)
    return {memory_id: tuple(ids) for memory_id, ids in found.items()}


def cited_in(investigation: CompletedInvestigation) -> set[str]:
    """The evidence the agent's beliefs, conclusion and proposal rest on."""
    # Variables:
    #   cited: Every evidence id the conclusion, hypotheses and proposal rest on.
    cited = set(investigation.conclusion.evidence_ids)
    for hypothesis in investigation.hypotheses:
        cited.update(hypothesis.supporting_evidence_ids)
        cited.update(hypothesis.contradicting_evidence_ids)
    if investigation.proposed_action is not None:
        cited.update(investigation.proposed_action.evidence_ids)
    return cited


def build_use_records(
    investigation: CompletedInvestigation,
) -> tuple[MemoryUseRecord, ...]:
    """One record per memory the investigation recalled, read from its evidence.

    "Used" only when a hypothesis, the conclusion or the proposal cites the
    recalled item; otherwise unknown, never "not used": an uncited memory may
    still have steered the next look. The effect stays unknown: only a named
    assessment may say a memory helped or hurt, never the run's success.
    """
    # Variables:
    #   cited: The evidence the agent's reasoning rests on.
    #   records: One use record per recalled memory.
    #   used: True if any evidence item holding that memory is cited.
    cited = cited_in(investigation)
    records = []
    for memory_id, evidence_ids in recalled_in(investigation).items():
        used = bool(cited.intersection(evidence_ids))
        records.append(
            MemoryUseRecord(
                consumer_run_id=investigation.run_id,
                consumer_investigation_id=investigation.investigation_id,
                memory_id=memory_id,
                used=True if used else None,
                assessment_source="evaluator" if used else None,
                evidence_ids=evidence_ids,
                explanation="the recalled item is cited by the agent's reasoning"
                if used
                else None,
            )
        )
    return tuple(records)


SearchOutcome = Literal["answered", "repeated", "budget_spent", "failed"]


class RecallSearchRecord(Contract):
    """One memory search an investigation made, for the experimenter.

    Facts from the loop's own decision records: what was asked, whether it
    was answered, refused or failed, and which memories came back. Nothing
    from the hidden truth.
    """

    sequence: int = Field(ge=1)  # the decision record's number
    text: str | None = None  # None when the arguments were not usable
    limit: int | None = None
    outcome: SearchOutcome
    evidence_id: str | None = None
    memory_ids: tuple[UUID, ...] = ()


def build_search_records(state) -> tuple[RecallSearchRecord, ...]:
    """One record per recall_memories call the investigation made, in order.

    `state` is the finished `InvestigationState`. A call the loop skipped as
    a repeat, or the provider refused as one, is "repeated"; one refused
    because no searches were left is "budget_spent"; any other failure is
    "failed".
    """
    # Variables:
    #   state: The finished investigation state, read for its decision records.
    #   contents: The text of each piece of evidence, by id.
    #   records: One record per memory search, in order.
    #   text: What was searched for; None if the arguments were unusable.
    #   limit: How many results were asked for.
    #   message: The tool's error message, if the call failed or was refused.
    #   evidence_id: The evidence that holds the answer, if there was one.
    #   memory_ids: The memories that came back.
    #   outcome: answered, repeated, budget_spent or failed.
    contents = {e.id: e.content for e in state.evidence}
    records = []
    for decision in state.decisions:
        if decision.tool != RECALL_TOOL:
            continue
        text, limit = decision.arguments.get("text"), decision.arguments.get("limit")
        message = decision.error.message if decision.error is not None else None
        evidence_id, memory_ids = None, ()
        if decision.outcome == "repeated_call" or message == REPEATED_SEARCH:
            outcome = "repeated"
        elif message == SEARCHES_SPENT:
            outcome = "budget_spent"
        elif decision.evidence_ids:
            outcome = "answered"
            [evidence_id] = decision.evidence_ids
            memory_ids = tuple(
                RecalledMemory.model_validate(item).memory_id
                for item in json.loads(contents[evidence_id]) or ()
            )
        else:
            outcome = "failed"
        records.append(
            RecallSearchRecord(
                sequence=decision.sequence,
                text=text if isinstance(text, str) else None,
                limit=limit if type(limit) is int else None,
                outcome=outcome,
                evidence_id=evidence_id,
                memory_ids=memory_ids,
            )
        )
    return tuple(records)
