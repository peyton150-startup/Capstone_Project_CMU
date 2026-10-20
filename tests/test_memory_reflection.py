import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

import capstone
from capstone.agent.completion import complete
from capstone.agent.policy import Lesson
from capstone.memory.contracts import ReflectionCandidate
from capstone.memory.policy import MemoryPromotionPolicy, failure_lesson
from capstone.memory.reflection import build_candidate
from tests.helpers import ScriptedPolicy
from tests.test_agent_completion import ENDINGS

ADVICE = "When vibration climbs steadily on one machine, replace its bearing."
CLAIMS_FIXED = "Replacing the bearing fixed the vibration."
MEMORY = Path(capstone.__file__).parent / "memory"


def candidate_for(ending, lesson=ADVICE):
    state = ENDINGS[ending]()
    return build_candidate(complete(state), tuple(state.provenance), lesson), state


# --- code fills every fact ---------------------------------------------------


def test_a_verified_fix_gives_a_candidate_filled_from_the_record():
    candidate, state = candidate_for("verified fix")
    record = complete(state)
    assert isinstance(candidate, ReflectionCandidate)
    assert candidate.investigation == record
    assert candidate.category == "alarm"  # the symptom, not the diagnosis
    assert candidate.intervention_worked is True
    assert candidate.diagnosis_assessment == "supported"
    assert candidate.confidence == record.conclusion.confidence
    cited = tuple(
        dict.fromkeys(
            (*record.conclusion.evidence_ids, *record.verification.evidence_ids)
        )
    )
    assert candidate.useful_evidence_ids == cited
    assert candidate.lesson.evidence_ids == cited
    assert candidate.provenance == tuple(state.provenance)


def test_only_the_sentence_comes_from_the_model():
    candidate, _ = candidate_for("verified fix", lesson=f"  {ADVICE}  ")
    assert candidate.lesson.text == ADVICE
    assert candidate.lesson.reusable is True
    assert candidate.lesson.contains_transient_details is False
    other, _ = candidate_for("verified fix", lesson=CLAIMS_FIXED)
    assert other.model_dump(exclude={"lesson": {"text"}}) == candidate.model_dump(
        exclude={"lesson": {"text"}}
    )


def test_the_gate_accepts_the_candidate_of_a_verified_fix():
    candidate, _ = candidate_for("verified fix")
    decision = MemoryPromotionPolicy().evaluate(candidate)
    assert decision.accepted, decision.reasons
    assert decision.memory.category == "alarm"
    assert decision.memory.lesson == ADVICE


# --- the sentence cannot overrule the check ----------------------------------


@pytest.mark.parametrize("lesson", [CLAIMS_FIXED, "The diagnosis was wrong.", None])
def test_a_failed_fix_is_recorded_as_failed_whatever_the_sentence_claims(lesson):
    candidate, _ = candidate_for("failed fix", lesson=lesson)
    record = candidate.investigation
    assert record.verification.status == "failed"
    assert candidate.intervention_worked is False
    # A fix that did not work does not prove the diagnosis wrong.
    assert candidate.diagnosis_assessment == "unknown"
    # For a failure the model's sentence is not used; code states the fact.
    assert candidate.lesson.text == failure_lesson(record)
    assert "CNC-01" in candidate.lesson.text  # the machine actually repaired


def test_the_gate_keeps_a_failed_fix_as_what_did_not_work():
    candidate, _ = candidate_for("failed fix", lesson=CLAIMS_FIXED)
    decision = MemoryPromotionPolicy().evaluate(candidate)
    assert decision.accepted, decision.reasons
    assert decision.memory.outcome == "unresolved"
    assert decision.memory.lesson == failure_lesson(candidate.investigation)


def test_no_action_that_was_checked_says_nothing_about_an_intervention():
    candidate, _ = candidate_for("no action, checked")
    assert candidate.investigation.proposed_action is None
    assert candidate.intervention_worked is None
    assert candidate.diagnosis_assessment == "unknown"
    decision = MemoryPromotionPolicy().evaluate(candidate)
    assert "nothing_was_tried" in decision.reasons


# --- no observed outcome, or nothing to say: no candidate --------------------


@pytest.mark.parametrize("ending", sorted(ENDINGS))
def test_a_candidate_exists_only_where_an_outcome_was_observed(ending):
    candidate, state = candidate_for(ending)
    check = complete(state).verification
    observed = check is not None and check.status in {"verified", "failed"}
    assert (candidate is not None) == observed
    if candidate is not None:
        ids = {e.id for e in candidate.investigation.evidence}
        assert set(candidate.useful_evidence_ids) <= ids
        MemoryPromotionPolicy().evaluate(candidate)  # the gate can read it


@pytest.mark.parametrize("lesson", [None, "", "   "])
def test_no_sentence_means_no_candidate(lesson):
    candidate, _ = candidate_for("verified fix", lesson=lesson)
    assert candidate is None


# --- the model's side --------------------------------------------------------


def test_the_model_can_write_a_sentence_and_nothing_else():
    assert set(Lesson.model_fields) == {"text"}
    with pytest.raises(ValidationError):
        Lesson(text="")
    with pytest.raises(ValidationError):
        Lesson(text=ADVICE, category="bearing")


def test_a_policy_is_asked_for_the_lesson_and_may_decline():
    state = ENDINGS["verified fix"]()
    assert ScriptedPolicy().write_lesson(state) is None
    written = ScriptedPolicy(lesson=lambda s: Lesson(text=ADVICE)).write_lesson(state)
    assert written == Lesson(text=ADVICE)


def test_the_memory_package_does_not_import_the_agent():
    for path in MEMORY.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            assert not any(n.startswith("capstone.agent") for n in names), path
