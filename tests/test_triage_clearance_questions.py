"""Audit #2: a triage may not clear an alarm while its trigger question is unsettled.

The fixed triage plan writes Q1 ("is the alarm sustained or a spike?") with
a measured predicate and no hypothesis, so `conclusion_gaps` never counts it
and `triage_rival_gaps` does not either. Before this fix a triage could answer
"supported, nothing needs doing" with Q1 never settled. Now every question
with a predicate (`state.question_predicates`) must be settled by a measured
true or false before a triage may clear. What these tests prove, with no model:

- an open Q1, or one whose predicate is not a measured true/false, blocks
  the clearance, and the block is recorded;
- Q1 settled as a spike ("false"), with the other clearance rules met, clears;
- escalate and intervene answers are untouched;
- a deep run is unchanged, and TRIAGE_EVIDENCE_TESTS=off gives the old rule.
"""

import pytest

from capstone.agent.investigation import needs_deep_run
from capstone.agent.state import Predicate, Question
from tests.test_triage import add_evidence, clear, clearance_state, gap_kinds

# The fixed plan's Q1 for "vibration above 4.50" on CNC-02 (anomaly tick 10).
PREDICATE = Predicate(
    machine_id="CNC-02",
    sensor="vibration",
    from_tick=0,
    to_tick=20,
    statistic="mean",
    comparison="above",
    threshold=4.5,
    min_samples=10,
)
Q1 = Question(
    id="Q1",
    text="Is CNC-02's vibration still above 4.50, steadily or in a single spike?",
)


def readings(value, count):
    """get_readings rows for CNC-02 vibration, one per tick from 0."""
    return [
        {
            "tick": tick,
            "machine_id": "CNC-02",
            "sensor": "vibration",
            "value": value,
            "unit": "mm/s",
        }
        for tick in range(count)
    ]


def with_q1(*, open_question=True, values=None, count=12):
    """A clearable triage state (PR 246 rules met) with the fixed plan's Q1.

    `open_question` keeps Q1 among the open questions; `values` adds that
    many readings (each of `values`) as evidence E4, or none when None.
    """
    # Variables:
    #   state: Hypothesis, measurement and full screening present, so only
    #     the Q1 rule can block the clearance.
    state = clearance_state()
    state.question_predicates = {"Q1": PREDICATE}
    if open_question:
        state.unanswered_questions = [Q1]
    if values is not None:
        add_evidence(state, "E4", "simulator:get_readings", readings(values, count))
    return state


def withheld(state):
    return [r for r in state.triage_test_records if r.kind == "clearance_question_open"]


def test_an_open_trigger_question_blocks_the_clearance():
    state = with_q1(open_question=True)
    checked = clear(state)
    assert checked.assessment == "unresolved"
    assert checked.recommendation == "escalate"
    assert needs_deep_run(checked)
    assert gap_kinds(state) == ["triage_required_question_open"]
    [gap] = state.conclusion_trace.gaps
    assert gap.question_id == "Q1"
    [record] = withheld(state)
    assert record.question_ids == ("Q1",)
    assert record.verdict == "unavailable"  # no reading of CNC-02 vibration yet


def test_a_closed_question_whose_predicate_is_unsettled_still_blocks():
    # Too few readings: "insufficient", whatever closed the question.
    state = with_q1(open_question=False, values=0.5, count=3)
    clear(state)
    assert gap_kinds(state) == ["triage_required_question_open"]
    assert withheld(state)[0].verdict == "insufficient"


def test_a_trigger_settled_as_a_spike_still_clears():
    state = with_q1(open_question=False, values=0.5)
    checked = clear(state)
    assert checked.assessment == "supported"
    assert checked.recommendation == "no_action"
    assert not needs_deep_run(checked)
    assert gap_kinds(state) == []
    assert withheld(state) == []


def test_a_question_still_open_blocks_even_with_a_settled_verdict():
    # Open means no read answered it: the triage never closed the question,
    # so it may not clear on it (the brief's rule: open, or unsettled).
    state = with_q1(open_question=True, values=0.5)
    clear(state)
    assert gap_kinds(state) == ["triage_required_question_open"]
    assert withheld(state)[0].verdict == "false"


def test_a_question_without_a_predicate_is_not_required():
    state = clearance_state()
    state.unanswered_questions = [Q1]
    checked = clear(state)
    assert checked.recommendation == "no_action"
    assert gap_kinds(state) == []


@pytest.mark.parametrize("recommendation", ["escalate", "intervene"])
def test_answers_that_clear_nothing_are_untouched(recommendation):
    state = with_q1(open_question=True)
    clear(state, recommendation=recommendation)
    assert "triage_required_question_open" not in gap_kinds(state)
    assert withheld(state) == []


def test_a_deep_run_is_unchanged():
    state = with_q1(open_question=True)
    state.mode = "deep"
    checked = clear(state)
    assert checked.recommendation == "no_action"
    assert gap_kinds(state) == []


def test_the_old_triage_rules_do_not_apply_it():
    state = with_q1(open_question=True)
    checked = clear(state, triage_evidence_tests=False)
    assert checked.recommendation == "no_action"
    assert gap_kinds(state) == []


def test_the_report_counts_withheld_clearances(monkeypatch):
    from capstone.agent.state import TriageTestRecord
    from capstone.experiment import format_evidence_tests
    from tests.test_triage_evidence_tests import triaged_record

    record = triaged_record(monkeypatch, "on")
    held = TriageTestRecord(kind="clearance_question_open", stage="decide", tick=10)
    changed = record.model_copy(
        update={"triage": record.triage.model_copy(update={"test_records": [held]})}
    )
    line = format_evidence_tests([changed])
    assert "clearances held open by an unsettled question 1" in line
    assert "changed an outcome in 1" in line
