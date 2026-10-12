from uuid import UUID

import pytest
from pydantic import ValidationError

from capstone.contracts.completed_investigations import CompletedInvestigation
from capstone.evaluation.memory import (
    MemoryUseRecord,
    build_promotion_record,
    build_use_record,
)
from capstone.memory.contracts import PromotionDecision, ReflectionCandidate
from capstone.memory.policy import MemoryPromotionPolicy
from tests.test_memory_policy import candidate_data


def artifacts():
    candidate = ReflectionCandidate.model_validate(candidate_data())
    return candidate.investigation, MemoryPromotionPolicy().evaluate(candidate)


def later_investigation():
    data = candidate_data()["investigation"]
    data["run_id"] = str(UUID(int=10))
    data["investigation_id"] = str(UUID(int=11))
    return CompletedInvestigation.model_validate(data)


def test_policy_acceptance_is_not_recorded_as_storage():
    incident, decision = artifacts()
    record = build_promotion_record(incident, decision)
    assert record.accepted and not record.stored
    assert record.memory_id == decision.memory.memory_id
    assert record.run_id == incident.run_id
    assert record.reasons == decision.reasons
    assert record.diagnosis_correct is None


def test_storage_and_rejection_records_preserve_decision_reasons():
    incident, decision = artifacts()
    stored = decision.model_copy(update={"stored": True})
    assert build_promotion_record(incident, stored).stored
    rejected = PromotionDecision(
        investigation_id=incident.investigation_id,
        accepted=False,
        reasons=("duplicate_lesson",),
        policy_version=decision.policy_version,
        existing_memory_id=decision.memory.memory_id,
    )
    record = build_promotion_record(incident, rejected)
    assert not record.accepted and not record.stored
    assert record.memory_id is None
    assert record.existing_memory_id == decision.memory.memory_id
    assert record.reasons == ("duplicate_lesson",)


def test_evaluator_correctness_does_not_change_rejected_promotion():
    data = candidate_data()
    data["confidence"] = 0.5
    candidate = ReflectionCandidate.model_validate(data)
    decision = MemoryPromotionPolicy().evaluate(candidate)
    record = build_promotion_record(
        candidate.investigation, decision, diagnosis_correct=True
    )
    assert record.diagnosis_correct is True
    assert not record.accepted and record.memory_id is None
    assert decision == MemoryPromotionPolicy().evaluate(candidate)
    assert "diagnosis_correct" not in candidate.model_dump_json()


def test_promotion_builder_rejects_mismatched_identity_and_policy():
    incident, decision = artifacts()
    with pytest.raises(ValueError, match="investigation"):
        build_promotion_record(later_investigation(), decision)
    other_run = incident.model_copy(update={"run_id": UUID(int=99)})
    with pytest.raises(ValueError, match="run"):
        build_promotion_record(other_run, decision)
    other_policy = decision.model_copy(update={"policy_version": "other"})
    with pytest.raises(ValueError, match="policy"):
        build_promotion_record(incident, other_policy)


def test_retrieval_and_success_do_not_imply_usefulness():
    _, decision = artifacts()
    consumer = later_investigation()
    record = build_use_record(consumer, decision.memory)
    assert record.retrieved and record.used is None
    assert record.effect == "unknown"
    assert record.assessment_source is None
    assert record.consumer_investigation_id == consumer.investigation_id
    assert record.memory_id == decision.memory.memory_id
    assert (
        record.model_dump_json()
        == build_use_record(consumer, decision.memory).model_dump_json()
    )


@pytest.mark.parametrize("effect", ["helped", "hurt", "neutral"])
@pytest.mark.parametrize("source", ["agent_report", "human_review", "evaluator"])
def test_known_effect_retains_assessment_source_and_evidence(effect, source):
    _, decision = artifacts()
    record = build_use_record(
        later_investigation(),
        decision.memory,
        used=True,
        effect=effect,
        assessment_source=source,
        evidence_ids=("trend",),
        explanation="Assessor compared the chosen investigation steps with the lesson",
    )
    assert record.effect == effect
    assert record.assessment_source == source
    assert record.evidence_ids == ("trend",)
    assert record.used is True


@pytest.mark.parametrize(
    "change",
    [
        {"used": None},
        {"retrieved": False},
        {"evidence_ids": ()},
        {"assessment_source": None},
        {"explanation": None},
        {"explanation": "   "},
    ],
)
def test_known_effect_requires_used_retrieved_memory_and_supported_assessment(change):
    data = {
        "consumer_run_id": UUID(int=10),
        "consumer_investigation_id": UUID(int=11),
        "memory_id": UUID(int=12),
        "retrieved": True,
        "used": True,
        "effect": "helped",
        "assessment_source": "agent_report",
        "evidence_ids": ("trend",),
        "explanation": "Reported to have guided the investigation",
    }
    data.update(change)
    with pytest.raises(ValidationError):
        MemoryUseRecord.model_validate(data)


def test_use_builder_rejects_dangling_or_duplicate_evidence_references():
    _, decision = artifacts()
    for ids in (("missing",), ("trend", "trend")):
        with pytest.raises(ValueError, match="evidence"):
            build_use_record(later_investigation(), decision.memory, evidence_ids=ids)


def test_record_of_unused_memory_can_leave_effect_unknown():
    _, decision = artifacts()
    record = build_use_record(later_investigation(), decision.memory, used=False)
    assert record.retrieved and record.used is False and record.effect == "unknown"
