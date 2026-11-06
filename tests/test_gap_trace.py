"""The final check's gap trace, and replaying other gap rules on saved results."""

import json

import pytest

from capstone.agent.artifacts import AgentConclusion
from capstone.agent.investigation import check_conclusion, question_role
from capstone.agent.loop import InvestigationDeps
from capstone.agent.policy import ActionRequest
from capstone.agent.state import ConclusionTrace, GapRecord, Question
from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.provenance import ProvenanceReference
from capstone.evaluation.gap_replay import (
    RULES,
    Case,
    Gap,
    case_of,
    final_recommendation,
    legacy_gap,
    main,
    outcome,
)
from capstone.experiment import ExperimentRecord
from tests.helpers import START, FakeProvider, ScriptedPolicy, new_state

RULE = {rule.name: rule for rule in RULES}


def state_with_two_explanations():
    """One observation, a chosen cause H1, a rival H2, and three open questions."""
    # Variables:
    #   questions: Q1 only checks H1, Q2 tells H1 from H2, Q3 names no cause.
    state = new_state()
    state.evidence.append(
        Evidence(
            id="E1",
            source_id="simulator:get_time",
            source_type="tool_result",
            content=json.dumps({"tick": 50}),
            observed_tick=50,
            observed_at=START,
        )
    )
    state.provenance.append(
        ProvenanceReference(
            evidence_id="E1",
            source_id="simulator:get_time",
            source_type="tool_result",
            origin="observable",
            observed_tick=50,
        )
    )
    state.hypotheses = [
        Hypothesis(id="H1", claim="bearing wear", confidence=0.9),
        Hypothesis(id="H2", claim="sensor fault", confidence=0.3),
    ]
    state.unanswered_questions = [
        Question(id="Q1", text="is the temperature rising?", hypothesis_id="H1"),
        Question(
            id="Q2",
            text="does a second sensor agree?",
            hypothesis_id="H1",
            distinguishes_hypothesis_ids=("H1", "H2"),
        ),
        Question(id="Q3", text="did the shift change?"),
    ]
    return state


def answer(**changes):
    values = {
        "diagnosis": "bearing wear",
        "confidence": 0.95,
        "recommendation": "no_action",
        "hypothesis_id": "H1",
        "evidence_ids": ("E1",),
        "assessment": "supported",
    }
    values.update(changes)
    return AgentConclusion(**values)


def check(state, conclusion, request=None):
    deps = InvestigationDeps(provider=FakeProvider(), policy=ScriptedPolicy())
    return check_conclusion(state, deps, conclusion, request)


# --- the trace the check writes ----------------------------------------------


def test_each_gap_is_saved_with_its_kind_and_role():
    state = state_with_two_explanations()
    own = ("Q2", "will it recur?")  # one names a tracked question, one does not
    checked, _ = check(state, answer(unresolved_questions=own))
    trace = state.conclusion_trace
    assert trace.model_assessment == "supported" and trace.forced_unresolved
    assert trace.selected_hypothesis_id == "H1"
    assert [(g.kind, g.question_id, g.role) for g in trace.gaps] == [
        ("model_question", "Q2", "rival_test"),
        ("model_question", None, "unlinked"),
        ("unanswered_question", "Q1", "selected_check"),
        ("unanswered_question", "Q2", "rival_test"),
    ]
    # Q3 names no standing explanation, so the check never counted it.
    assert "did the shift change?" not in checked.unresolved_questions


def test_the_plain_text_the_check_writes_is_unchanged():
    state = state_with_two_explanations()
    checked, _ = check(state, answer(unresolved_questions=("will it recur?",)))
    assert checked.unresolved_questions == (
        "will it recur?",
        "is the temperature rising?",
        "does a second sensor agree?",
    )
    assert checked.assessment == "unresolved" and checked.recommendation == "escalate"


def test_the_model_saying_unresolved_itself_is_told_apart_from_the_check():
    state = new_state()
    state.evidence.extend(state_with_two_explanations().evidence)
    state.provenance.extend(state_with_two_explanations().provenance)
    check(state, answer(assessment="unresolved", hypothesis_id=None))
    trace = state.conclusion_trace
    assert trace.model_assessment == "unresolved"
    assert trace.gaps == () and not trace.forced_unresolved


def test_grounding_gaps_are_saved_by_kind():
    state = state_with_two_explanations()
    state.unanswered_questions = []
    state.hypotheses[0] = state.hypotheses[0].model_copy(
        update={"contradicting_evidence_ids": ["E1"]}
    )
    state.provenance.clear()  # E1 is no longer current-factory evidence
    check(state, answer())
    kinds = [g.kind for g in state.conclusion_trace.gaps]
    assert kinds == ["no_observable_evidence", "selected_has_conflict"]


def test_the_wanted_fix_and_the_action_rules_verdict_are_saved():
    state = state_with_two_explanations()
    state.unanswered_questions = []
    fix = ActionRequest(
        machine_id="CNC-02",
        action="replace_bearing",
        reason="worn",
        prediction="vibration falls",
    )
    check(state, answer(recommendation="intervene", confidence=0.5), fix)
    trace = state.conclusion_trace
    assert trace.model_recommendation == "intervene"
    assert trace.wanted_action == "replace_bearing CNC-02"
    assert trace.action_blocked == "confidence 0.50 below 0.90"


def test_an_answer_with_no_completion_claim_leaves_no_trace():
    state = state_with_two_explanations()
    check(state, answer(assessment=None))
    assert state.conclusion_trace is None


@pytest.mark.parametrize(
    ("question", "role"),
    [
        (Question(id="Q", text="t", hypothesis_id="H2"), "rival_test"),
        (
            Question(id="Q", text="t", distinguishes_hypothesis_ids=("H1", "H2")),
            "rival_test",
        ),
        (Question(id="Q", text="t", hypothesis_id="H1"), "selected_check"),
        (Question(id="Q", text="t", hypothesis_id="H9"), "side"),
        (Question(id="Q", text="t"), "side"),
    ],
    ids=["about a rival", "tells two apart", "chosen only", "dropped cause", "none"],
)
def test_a_question_role_says_how_it_bears_on_the_chosen_cause(question, role):
    assert question_role(question, "H1", {"H1", "H2"}) == role


def test_the_results_file_keeps_the_trace_and_reads_older_results():
    trace = ConclusionTrace(
        model_assessment="supported",
        model_recommendation="no_action",
        gaps=(GapRecord(kind="unverified_number", text="E5: unverified"),),
        forced_unresolved=True,
    )
    fields = ExperimentRecord.model_fields
    assert fields["conclusion_trace"].default is None
    assert ConclusionTrace.model_validate(trace.model_dump(mode="json")) == trace


# --- replaying gap rules -----------------------------------------------------


def case(gaps=(), recommendation="no_action", needed=(), **changes):
    values = {
        "scenario_id": "KA-x",
        "model_recommendation": recommendation,
        "model_self_unresolved": False,
        "gaps": gaps,
        "wanted_action": None,
        "action_blocked": None,
        "needed": needed,
        "traced": True,
    }
    values.update(changes)
    return Case(**values)


def test_a_side_question_holds_the_case_open_only_under_todays_rule():
    side = case((Gap("model_question", "side"),))
    assert final_recommendation(side, RULE["today"]) == "escalate"
    assert final_recommendation(side, RULE["grounding+rivals"]) == "no_action"


def test_a_rival_test_holds_it_open_until_rivals_stop_counting():
    rival = case((Gap("unanswered_question", "rival_test"),))
    assert final_recommendation(rival, RULE["grounding+rivals"]) == "escalate"
    assert final_recommendation(rival, RULE["grounding"]) == "no_action"


def test_the_models_own_unresolved_and_the_action_rules_always_hold():
    assert final_recommendation(case(model_self_unresolved=True), RULE["none"]) == (
        "escalate"
    )
    weak = case(recommendation="intervene", action_blocked="no evidence cited")
    assert final_recommendation(weak, RULE["none"]) == "escalate"


@pytest.mark.parametrize(
    ("recommendation", "wanted", "needed", "judged"),
    [
        ("no_action", None, ("replace_bearing CNC-02",), "missed_fault"),
        ("no_action", None, (), "closed_right"),
        ("escalate", None, ("replace_bearing CNC-02",), "held_fault"),
        ("escalate", None, (), "held_no_fault"),
        (
            "intervene",
            "replace_bearing CNC-02",
            ("replace_bearing CNC-02",),
            "right_fix",
        ),
        ("intervene", "reset_setting CNC-02", ("replace_bearing CNC-02",), "wrong_fix"),
        ("intervene", None, ("replace_bearing CNC-02",), "fix_unknown"),
        ("intervene", "replace_bearing CNC-02", (), "unneeded_fix"),
    ],
)
def test_an_ending_is_judged_against_what_the_faults_needed(
    recommendation, wanted, needed, judged
):
    assert outcome(case(needed=needed, wanted_action=wanted), recommendation) == judged


def test_older_gaps_are_sorted_by_their_wording():
    assert legacy_gap("E12: unverified") == Gap("unverified_number")
    assert legacy_gap(
        "The selected hypothesis still has conflicting or unexplained evidence."
    ) == Gap("selected_has_conflict")
    assert legacy_gap("is power rising?") == Gap("question", "unlinked")


def test_a_record_with_no_checked_answer_is_skipped():
    assert case_of({"scenario_id": "KA-x", "policy_recommendation": None}) is None


def test_the_command_reads_traced_and_older_results_with_extra_fields(tmp_path, capsys):
    # Variables:
    #   traced: A newer record whose only gap is a side question.
    #   older: A record with no trace, a field this branch does not know, and
    #     an unverified number as its gap.
    trace = ConclusionTrace(
        model_assessment="supported",
        model_recommendation="no_action",
        gaps=(GapRecord(kind="model_question", text="will it recur?", role="side"),),
        forced_unresolved=True,
    )
    traced = {
        "scenario_id": "KA-07",
        "conclusion_trace": trace.model_dump(mode="json"),
        "score": {"wanted_actions": []},
    }
    older = {
        "scenario_id": "KA-01",
        "policy_recommendation": "no_action",
        "unresolved_questions": ["E5: unverified"],
        "score": {"wanted_actions": ["replace_bearing CNC-02"]},
        "line_context_enabled": True,
    }
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in (traced, older)) + "\n")
    assert main([str(path), "--cases"]) == 0
    printed = capsys.readouterr().out
    assert "2 cases replayed, 0 skipped" in printed
    assert "1 have no gap trace" in printed
    assert "KA-07: model=no_action today=held_no_fault" in printed
    assert "grounding=closed_right" in printed
    assert "KA-01 (untraced): model=no_action today=held_fault" in printed
    assert "none=missed_fault" in printed
