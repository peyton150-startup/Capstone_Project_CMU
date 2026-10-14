from uuid import UUID

import pytest
from pydantic import ValidationError

from capstone.contracts.completed_investigations import CompletedInvestigation
from capstone.memory.contracts import ReflectionCandidate
from capstone.memory.policy import MemoryPromotionPolicy, failure_lesson


def candidate_data():
    return {
        "investigation": {
            "run_id": "00000000-0000-0000-0000-000000000001",
            "investigation_id": "00000000-0000-0000-0000-000000000002",
            "anomaly": {
                "summary": "Rising vibration and temperature",
                "symptoms": ["rising vibration", "increasing temperature"],
            },
            "evidence": [
                {
                    "id": "trend",
                    "source_id": "get_sensor_summary",
                    "source_type": "tool_result",
                    "content": "Vibration increased over several jobs",
                    "observed_tick": 100,
                },
                {
                    "id": "repair",
                    "source_id": "get_events",
                    "source_type": "event",
                    "content": "Removed bearing was worn",
                    "observed_tick": 150,
                },
                {
                    "id": "after",
                    "source_id": "get_sensor_summary",
                    "source_type": "tool_result",
                    "content": "Vibration returned to baseline",
                    "observed_tick": 200,
                },
            ],
            "hypotheses": [],
            "conclusion": {
                "diagnosis": "bearing degradation",
                "confidence": 0.9,
                "evidence_ids": ["trend", "repair"],
            },
            "proposed_action": {
                "action": "replace_bearing",
                "machine_id": "CNC-02",
                "reason": "Sustained wear pattern",
                "evidence_ids": ["trend"],
            },
            "verification": {
                "status": "verified",
                "outcome": "resolved",
                "summary": "Readings settled after repair",
                "evidence_ids": ["after"],
                "observed_tick": 200,
            },
            "iterations_used": 4,
            "tool_calls_used": 6,
            "termination_reason": "verification_complete",
        },
        "category": "bearing",
        "useful_evidence_ids": ["trend", "repair", "after"],
        "misleading_evidence_ids": [],
        "unnecessary_tool_calls": ["call-4"],
        "diagnosis_assessment": "supported",
        "intervention_worked": True,
        "lesson": {
            "text": "Compare sustained vibration trends and repair findings before attributing recovery to a bearing replacement.",
            "evidence_ids": ["trend", "repair", "after"],
            "reusable": True,
            "contains_transient_details": False,
        },
        "confidence": 0.9,
        "provenance": [
            {
                "evidence_id": "trend",
                "source_id": "get_sensor_summary",
                "source_type": "tool_result",
                "origin": "observable",
                "observed_tick": 100,
            },
            {
                "evidence_id": "repair",
                "source_id": "get_events",
                "source_type": "event",
                "origin": "observable",
                "observed_tick": 150,
            },
            {
                "evidence_id": "after",
                "source_id": "get_sensor_summary",
                "source_type": "tool_result",
                "origin": "observable",
                "observed_tick": 200,
            },
        ],
    }


def test_verified_incident_promoted_without_raw_samples():
    candidate = ReflectionCandidate.model_validate(candidate_data())
    decision = MemoryPromotionPolicy().evaluate(candidate)
    assert decision.accepted
    assert decision.reasons == ("verified_reusable_lesson",)
    assert decision.memory.investigation_id == UUID(int=2)
    assert decision.memory.evidence_ids == ("after", "repair", "trend")
    assert decision.memory.provenance == tuple(
        sorted(candidate.provenance, key=lambda p: p.evidence_id)
    )
    assert "content" not in decision.memory.model_dump_json()
    assert decision.memory.verification.status == "verified"
    assert decision.memory.source_tick == 200


def test_unverified_check_rejected():
    data = candidate_data()
    data["investigation"]["verification"].update(status="unverified", outcome="unknown")
    decision = MemoryPromotionPolicy().evaluate(
        ReflectionCandidate.model_validate(data)
    )
    assert not decision.accepted
    assert "outcome_not_verified" in decision.reasons
    assert decision.memory is None


# --- what did not work ------------------------------------------------------

FAILED_SENTENCE = (
    "replace_bearing on CNC-02 was tried for rising vibration, increasing "
    "temperature and the check afterwards found it unresolved."
)


def failure_data():
    """The same incident, except the check found the repair did not work."""
    data = candidate_data()
    data["investigation"]["verification"].update(
        status="failed", outcome="unresolved", summary="Vibration still high"
    )
    data["diagnosis_assessment"] = "unknown"
    data["intervention_worked"] = False
    data["lesson"]["text"] = FAILED_SENTENCE
    return data


def test_the_failure_sentence_states_only_what_was_observed():
    investigation = CompletedInvestigation.model_validate(
        failure_data()["investigation"]
    )
    assert failure_lesson(investigation) == FAILED_SENTENCE


def test_an_observed_failed_action_is_promoted():
    decision = MemoryPromotionPolicy().evaluate(
        ReflectionCandidate.model_validate(failure_data())
    )
    assert decision.accepted, decision.reasons
    assert decision.reasons == ("observed_failed_action",)
    memory = decision.memory
    assert memory.outcome == "unresolved"
    assert memory.lesson == FAILED_SENTENCE
    assert memory.verification.status == "failed"
    assert memory.intervention.machine_id == "CNC-02"
    assert memory.source_tick == 200
    assert memory.policy_version == "episodic-v2"


def test_a_failure_does_not_rest_on_the_agents_confidence():
    data = failure_data()
    data["confidence"] = 0.3
    data["investigation"]["conclusion"]["confidence"] = 0.3
    assert (
        MemoryPromotionPolicy()
        .evaluate(ReflectionCandidate.model_validate(data))
        .accepted
    )


@pytest.mark.parametrize(
    "change,reason",
    [
        # A failed fix proves neither that the diagnosis was right nor wrong.
        ({"diagnosis_assessment": "refuted"}, "diagnosis_cannot_be_judged"),
        ({"diagnosis_assessment": "supported"}, "diagnosis_cannot_be_judged"),
        ({"intervention_worked": True}, "intervention_outcome_mismatch"),
        ({"intervention_worked": None}, "intervention_outcome_mismatch"),
    ],
)
def test_a_failure_cannot_claim_more_than_the_check(change, reason):
    data = failure_data()
    data.update(change)
    decision = MemoryPromotionPolicy().evaluate(
        ReflectionCandidate.model_validate(data)
    )
    assert not decision.accepted
    assert reason in decision.reasons


@pytest.mark.parametrize(
    "text",
    [
        "Bearing wear was the wrong diagnosis for rising vibration.",
        "Replacing the bearing does not fix high vibration.",
    ],
)
def test_a_failure_keeps_no_explanation_or_generalisation(text):
    data = failure_data()
    data["lesson"]["text"] = text
    decision = MemoryPromotionPolicy().evaluate(
        ReflectionCandidate.model_validate(data)
    )
    assert not decision.accepted
    assert "lesson_not_factual" in decision.reasons


def test_a_failure_with_nothing_tried_is_rejected():
    data = failure_data()
    data["investigation"]["proposed_action"] = None
    data["intervention_worked"] = None
    decision = MemoryPromotionPolicy().evaluate(
        ReflectionCandidate.model_validate(data)
    )
    assert not decision.accepted
    assert "nothing_was_tried" in decision.reasons


def test_a_failure_still_passes_the_evidence_and_hidden_truth_checks():
    data = failure_data()
    data["provenance"][0]["origin"] = "simulator_hidden"
    data["investigation"]["verification"]["evidence_ids"] = []
    reasons = (
        MemoryPromotionPolicy()
        .evaluate(ReflectionCandidate.model_validate(data))
        .reasons
    )
    assert "hidden_truth" in reasons
    assert "insufficient_evidence" in reasons


def test_a_success_and_its_failure_are_different_memories():
    policy = MemoryPromotionPolicy()
    success = policy.evaluate(ReflectionCandidate.model_validate(candidate_data()))
    failure = policy.evaluate(ReflectionCandidate.model_validate(failure_data()))
    assert success.memory.outcome == "resolved"
    assert failure.memory.fingerprint != success.memory.fingerprint


def test_missing_verification_rejected():
    data = candidate_data()
    data["investigation"]["verification"] = None
    assert (
        "outcome_not_verified"
        in MemoryPromotionPolicy()
        .evaluate(ReflectionCandidate.model_validate(data))
        .reasons
    )


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"confidence": 0.79}, "low_confidence"),
        ({"diagnosis_assessment": "refuted"}, "diagnosis_not_supported"),
        ({"intervention_worked": False}, "intervention_not_successful"),
        ({"provenance": []}, "missing_provenance"),
    ],
)
def test_promotion_gates(change, reason):
    data = candidate_data()
    data.update(change)
    result = MemoryPromotionPolicy().evaluate(ReflectionCandidate.model_validate(data))
    assert not result.accepted
    assert reason in result.reasons


@pytest.mark.parametrize("origin", ["evaluator_hidden", "simulator_hidden"])
def test_hidden_truth_provenance_rejected(origin):
    data = candidate_data()
    data["provenance"][0]["origin"] = origin
    result = MemoryPromotionPolicy().evaluate(ReflectionCandidate.model_validate(data))
    assert "hidden_truth" in result.reasons
    assert result.memory is None


def test_obviously_mislabeled_hidden_field_rejected():
    data = candidate_data()
    data["investigation"]["evidence"][0]["content"] = (
        "bearing_health = 0.4 from ground_truth"
    )
    assert (
        "hidden_truth"
        in MemoryPromotionPolicy()
        .evaluate(ReflectionCandidate.model_validate(data))
        .reasons
    )


@pytest.mark.parametrize(
    "update",
    [
        {"reusable": False},
        {"contains_transient_details": True},
        {"text": "Vibration was 6.72 mm/s at tick 123"},
    ],
)
def test_transient_sensor_details_not_promoted(update):
    data = candidate_data()
    data["lesson"].update(update)
    decision = MemoryPromotionPolicy().evaluate(
        ReflectionCandidate.model_validate(data)
    )
    assert not decision.accepted
    assert any(
        reason in decision.reasons for reason in ("not_reusable", "transient_details")
    )


def test_references_require_actual_evidence_and_matching_provenance():
    data = candidate_data()
    data["lesson"]["evidence_ids"] = ["missing"]
    assert (
        "missing_evidence"
        in MemoryPromotionPolicy()
        .evaluate(ReflectionCandidate.model_validate(data))
        .reasons
    )
    data = candidate_data()
    data["provenance"][0]["source_id"] = "other_tool"
    assert (
        "provenance_mismatch"
        in MemoryPromotionPolicy()
        .evaluate(ReflectionCandidate.model_validate(data))
        .reasons
    )


@pytest.mark.parametrize("field", ["lesson", "conclusion", "verification"])
def test_support_flags_without_evidence_rejected(field):
    data = candidate_data()
    target = data[field] if field == "lesson" else data["investigation"][field]
    target["evidence_ids"] = []
    result = MemoryPromotionPolicy().evaluate(ReflectionCandidate.model_validate(data))
    assert "insufficient_evidence" in result.reasons
    assert not result.accepted


def test_verified_no_action_incident_can_be_promoted():
    data = candidate_data()
    data["investigation"]["proposed_action"] = None
    data["intervention_worked"] = None
    result = MemoryPromotionPolicy().evaluate(ReflectionCandidate.model_validate(data))
    assert result.accepted
    assert result.memory.intervention is None


def test_policy_is_deterministic_and_configurable():
    candidate = ReflectionCandidate.model_validate(candidate_data())
    policy = MemoryPromotionPolicy()
    assert policy.evaluate(candidate) == policy.evaluate(candidate)
    assert not MemoryPromotionPolicy(min_confidence=0.95).evaluate(candidate).accepted
    with pytest.raises(ValueError):
        MemoryPromotionPolicy(min_confidence=1.1)


def test_completion_contract_round_trips_existing_artifacts():
    result = CompletedInvestigation.model_validate(candidate_data()["investigation"])
    assert (
        CompletedInvestigation.model_validate_json(result.model_dump_json()) == result
    )
    assert result.iterations_used == 4
    with pytest.raises(ValidationError):
        CompletedInvestigation.model_validate(
            {**result.model_dump(), "ground_truth": {}}
        )


def test_duplicate_evidence_ids_and_negative_counters_rejected():
    data = candidate_data()["investigation"]
    data["evidence"].append(data["evidence"][0])
    with pytest.raises(ValidationError):
        CompletedInvestigation.model_validate(data)
    data = candidate_data()["investigation"]
    data["tool_calls_used"] = -1
    with pytest.raises(ValidationError):
        CompletedInvestigation.model_validate(data)
