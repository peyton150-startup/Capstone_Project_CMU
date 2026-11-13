"""Block 3 of the 2026-11-13 triage schedule: deterministic evidence tests.

What these tests prove, with no model:

- the predicate evaluator answers true, false, insufficient, stale or
  unavailable from observed readings only, and missing data is never "false";
- in a triage, a successful call alone does not close a question that has a
  predicate; only a measured true or false does;
- TRI-03: an open question that separates live rivals keeps a triage
  diagnosis unsupported and holds a triage conclusion open;
- TRI-04: two views of one machine sensor count as one supporter;
- TRIAGE_EVIDENCE_TESTS=off gives the old triage rules, and deep mode is the
  same with the setting on or off;
- each time the rules change an outcome a `TriageTestRecord` is kept, printed
  by the progress view and counted in the experiment report, so a run can show
  whether the setting helped.
"""

import pytest

from capstone.agent.evidence_tests import (
    evaluate,
    open_rival_questions,
    physical_root,
    source_roots,
)
from capstone.agent.loop import InvestigationDeps, diagnosis_supported, gather
from capstone.agent.state import Predicate, Question, TriageTestRecord
from capstone.contracts.provenance import ProvenanceReference
from capstone.experiment import (
    Case,
    format_evidence_tests,
    report,
    run_experiment,
)
from capstone.progress import ProgressView, evidence_test_line
from capstone.settings import Settings
from tests.helpers import FakeProvider, ScriptedPolicy, ask, new_state
from tests.test_episode import SEED
from tests.test_triage import add_evidence, clear, gap_kinds, triage_then_deep
from tests.test_triage_safety_baseline import (
    OTHER_SENSOR,
    RIVAL_QUESTION,
    SAME_SENSOR,
    is_cleared,
    ka09_like_state,
    supported_state,
)


def deps(**changes):
    return InvestigationDeps(
        provider=FakeProvider(), policy=ScriptedPolicy(), **changes
    )


def rows(values, *, start=100, machine="CNC-02", sensor="vibration"):
    """get_readings rows, one per tick from `start`."""
    return [
        {
            "tick": start + i,
            "machine_id": machine,
            "sensor": sensor,
            "value": value,
            "unit": "mm/s",
        }
        for i, value in enumerate(values)
    ]


def summary(mean, *, count=20, from_tick=100, to_tick=119, sensor="vibration"):
    return {
        "machine_id": "CNC-02",
        "sensor": sensor,
        "from_tick": from_tick,
        "to_tick": to_tick,
        "sample_count": count,
        "mean": mean,
        "minimum": mean - 0.1,
        "maximum": mean + 0.1,
        "end_value": mean,
    }


PREDICATE = Predicate(
    machine_id="CNC-02",
    sensor="vibration",
    from_tick=100,
    to_tick=130,
    statistic="mean",
    comparison="above",
    threshold=4.0,
)


def judged(*answers):
    """The verdict on PREDICATE after each answer was observed, in order."""
    # Variables:
    #   answers: (tool, content) pairs, saved as observed evidence E1, E2, ...
    state = new_state()
    for i, (tool, content) in enumerate(answers, start=1):
        add_evidence(state, f"E{i}", f"simulator:{tool}", content)
    return evaluate(PREDICATE, state)


# --- the evaluator ------------------------------------------------------------


def test_readings_above_the_threshold_are_true():
    result = judged(("get_readings", rows([4.5] * 12)))
    assert result.verdict == "true"
    assert result.value == pytest.approx(4.5) and result.sample_count == 12
    assert result.evidence_ids == ("E1",)


def test_readings_below_the_threshold_are_false():
    assert judged(("get_readings", rows([3.0] * 12))).verdict == "false"


def test_too_few_readings_are_insufficient_not_false():
    result = judged(("get_readings", rows([3.0] * 5)))
    assert result.verdict == "insufficient"
    assert result.reason == "5 samples, 10 needed"


def test_readings_outside_the_window_are_stale():
    assert judged(("get_readings", rows([4.5] * 12, start=10))).verdict == "stale"


def test_no_readings_at_all_are_unavailable():
    assert judged(("get_readings", [])).verdict == "unavailable"
    assert judged().verdict == "unavailable"


def test_a_summary_inside_the_window_is_judged():
    assert judged(("get_sensor_summary", summary(4.6))).verdict == "true"
    assert judged(("get_sensor_summary", summary(3.1))).verdict == "false"


def test_a_summary_reaching_outside_the_window_is_stale():
    late = summary(4.6, from_tick=100, to_tick=200)
    assert judged(("get_sensor_summary", late)).verdict == "stale"


def test_an_empty_summary_is_unavailable():
    empty = summary(4.6, count=0) | {"mean": None}
    assert judged(("get_sensor_summary", empty)).verdict == "unavailable"


def test_another_sensor_is_never_used_as_evidence():
    other = rows([9.0] * 12, sensor="temperature")
    assert judged(("get_readings", other)).verdict == "unavailable"


def test_a_definite_verdict_beats_a_later_insufficient_one():
    result = judged(
        ("get_readings", rows([4.5] * 12)), ("get_readings", rows([3.0] * 3))
    )
    assert result.verdict == "true" and result.evidence_ids == ("E1",)


def test_evidence_not_answered_by_the_factory_is_ignored():
    state = new_state()
    add_evidence(state, "E1", "simulator:get_readings", rows([4.5] * 12))
    state.provenance = [
        ProvenanceReference(
            evidence_id="E1",
            source_id="memory:case-1",
            source_type="document",
            origin="memory",
        )
    ]
    assert evaluate(PREDICATE, state).verdict == "unavailable"


# --- physical roots (TRI-04) ----------------------------------------------------


def test_two_views_of_one_sensor_share_one_root():
    state = supported_state("triage", second=SAME_SENSOR)
    assert source_roots(state, {"E2", "E3"}) == ("CNC-02:vibration",)


def test_two_sensors_are_two_roots():
    state = supported_state("triage", second=OTHER_SENSOR)
    assert source_roots(state, {"E2", "E3"}) == (
        "CNC-02:temperature",
        "CNC-02:vibration",
    )


def test_evidence_without_a_sensor_counts_as_its_own_source():
    state = new_state()
    add_evidence(state, "E1", "simulator:get_events", [{"kind": "alarm"}])
    assert physical_root(state, state.evidence[0]) is None
    assert source_roots(state, {"E1"}) == ("evidence:E1",)


def test_the_request_names_the_root_before_the_answer_does():
    # A gathered answer: the decision's arguments name the sensor asked about.
    state = new_state()
    state.mode = "triage"
    provider = FakeProvider(lambda request: summary(4.6))
    step = ask(
        "get_sensor_summary",
        machine_id="CNC-01",
        sensor="spindle_load",
        from_tick=100,
        to_tick=119,
    )
    deps_ = InvestigationDeps(
        provider=provider, policy=ScriptedPolicy(), clock=lambda: 0.0
    )
    evidence = gather(state, deps_, "investigate", step, interpret=False)
    assert physical_root(state, evidence) == "CNC-01:spindle_load"


# --- TRI-03 and TRI-04 in the Test stage --------------------------------------


def test_an_open_rival_question_is_found():
    state = supported_state("triage", second=OTHER_SENSOR, question=RIVAL_QUESTION)
    assert open_rival_questions(state, {"H1", "H2"}) == [RIVAL_QUESTION]
    # A question naming only a dropped explanation separates nothing live.
    assert open_rival_questions(state, {"H3"}) == []


def test_withheld_support_is_recorded_once_with_its_reason():
    state = supported_state("triage", second=OTHER_SENSOR, question=RIVAL_QUESTION)
    assert diagnosis_supported(state, deps()) is False
    assert diagnosis_supported(state, deps()) is False  # asked again each turn
    (record,) = state.triage_test_records
    assert record.kind == "support_withheld_rival_question"
    assert record.hypothesis_id == "H1" and record.question_ids == ("Q1",)


def test_a_shared_root_is_recorded_with_its_sources():
    state = supported_state("triage", second=SAME_SENSOR)
    assert diagnosis_supported(state, deps()) is False
    (record,) = state.triage_test_records
    assert record.kind == "support_withheld_shared_root"
    assert record.roots == ("CNC-02:vibration",)
    assert record.evidence_ids == ("E2", "E3")
    assert record.reason == "2 supporters from 1 independent source(s)"


def test_a_genuinely_supported_triage_records_nothing():
    state = supported_state("triage", second=OTHER_SENSOR)
    assert diagnosis_supported(state, deps()) is True
    assert state.triage_test_records == []


@pytest.mark.parametrize(
    ("second", "question"),
    [(SAME_SENSOR, None), (OTHER_SENSOR, RIVAL_QUESTION)],
    ids=["shared root", "rival question"],
)
def test_the_setting_off_gives_the_old_triage_rule(second, question):
    state = supported_state("triage", second=second, question=question)
    assert diagnosis_supported(state, deps(triage_evidence_tests=False)) is True
    assert state.triage_test_records == []


@pytest.mark.parametrize("on", [True, False])
@pytest.mark.parametrize(
    ("second", "question"),
    [(SAME_SENSOR, None), (OTHER_SENSOR, RIVAL_QUESTION)],
    ids=["shared root", "rival question"],
)
def test_deep_mode_is_the_same_with_the_setting_on_or_off(on, second, question):
    state = supported_state("deep", second=second, question=question)
    assert diagnosis_supported(state, deps(triage_evidence_tests=on)) is True
    assert state.triage_test_records == []


# --- TRI-03 at the conclusion ---------------------------------------------------


def test_a_rival_question_holds_a_triage_conclusion_open():
    state = ka09_like_state()
    checked = clear(state, evidence_ids=("E2",))
    assert not is_cleared(checked)
    assert gap_kinds(state) == ["unanswered_question"]
    assert state.conclusion_trace.gaps[0].question_id == "Q1"
    (record,) = state.triage_test_records
    assert record.kind == "rival_question_gap" and record.question_ids == ("Q1",)


def test_a_rival_question_no_longer_open_lets_the_triage_clear():
    state = ka09_like_state()
    state.unanswered_questions = []
    checked = clear(state, evidence_ids=("E2",))
    assert is_cleared(checked)
    assert state.triage_test_records == []


def test_deep_conclusion_ignores_the_rival_question_as_before():
    state = ka09_like_state()
    state.mode = "deep"
    assert is_cleared(clear(state, evidence_ids=("E2",)))
    assert state.triage_test_records == []


# --- a question with a predicate closes only on a measured verdict ------------


def answer_question(answer, *, mode="triage", on=True, predicate=PREDICATE):
    """Gather one answer to Q1 and return the state afterwards."""
    # Variables:
    #   answer: What the fake factory returns for the get_readings call.
    #   on: The TRIAGE_EVIDENCE_TESTS setting the loop runs with.
    #   predicate: The measured condition attached to Q1, or None for none.
    state = new_state()
    state.mode = mode
    state.unanswered_questions = [
        Question(id="Q1", text="Is CNC-02 vibration above 4 since tick 100?")
    ]
    if predicate is not None:
        state.question_predicates = {"Q1": predicate}
    deps_ = InvestigationDeps(
        provider=FakeProvider(lambda request: answer),
        policy=ScriptedPolicy(),
        clock=lambda: 0.0,
        triage_evidence_tests=on,
    )
    step = ask(
        "get_readings",
        question_id="Q1",
        machine_id="CNC-02",
        sensor="vibration",
        from_tick=100,
        to_tick=130,
    )
    gather(state, deps_, "investigate", step, interpret=False)
    return state


def open_ids(state):
    return [q.id for q in state.unanswered_questions]


def test_a_measured_verdict_closes_the_question():
    state = answer_question(rows([4.5] * 12))
    assert open_ids(state) == []
    (record,) = state.triage_test_records
    assert record.kind == "question_closed" and record.verdict == "true"
    assert record.roots == ("CNC-02:vibration",)


def test_a_measured_false_also_closes_the_question():
    state = answer_question(rows([3.0] * 12))
    assert open_ids(state) == []
    assert state.triage_test_records[0].verdict == "false"


def test_a_successful_call_with_too_little_data_keeps_the_question_open():
    state = answer_question(rows([4.5] * 3))
    assert open_ids(state) == ["Q1"]
    assert state.answers["Q1"] == ["E1"]  # the answer is still kept
    (record,) = state.triage_test_records
    assert record.kind == "question_kept_open" and record.verdict == "insufficient"


def test_a_question_without_a_predicate_closes_as_before():
    state = answer_question(rows([4.5] * 3), predicate=None)
    assert open_ids(state) == [] and state.triage_test_records == []


@pytest.mark.parametrize(("mode", "on"), [("triage", False), ("deep", True)])
def test_old_rules_and_deep_mode_close_on_any_answer(mode, on):
    state = answer_question(rows([4.5] * 3), mode=mode, on=on)
    assert open_ids(state) == [] and state.triage_test_records == []


# --- the setting and the traces ---------------------------------------------------


def test_the_setting_is_on_by_default(monkeypatch):
    monkeypatch.delenv("TRIAGE_EVIDENCE_TESTS", raising=False)
    assert Settings(_env_file=None).triage_evidence_tests is True
    assert InvestigationDeps(provider=None, policy=None).triage_evidence_tests


def test_the_setting_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("TRIAGE_EVIDENCE_TESTS", "off")
    assert Settings(_env_file=None).triage_evidence_tests is False


def test_the_progress_view_prints_each_record_once():
    state = supported_state("triage", second=SAME_SENSOR)
    lines = []
    view = ProgressView(write=lines.append)
    diagnosis_supported(state, deps())
    view(state)
    view(state)
    shown = [line for line in lines if line.startswith("EVIDENCE TEST")]
    assert shown == [
        "EVIDENCE TEST support_withheld_shared_root; hypothesis H1; "
        "sources CNC-02:vibration; 2 supporters from 1 independent source(s)"
    ]


def test_a_record_line_names_the_verdict():
    record = TriageTestRecord(
        kind="question_kept_open",
        stage="investigate",
        tick=10,
        question_ids=("Q1",),
        verdict="stale",
        reason="no readings inside the window",
    )
    assert evidence_test_line(record) == (
        "EVIDENCE TEST question_kept_open; question Q1; verdict stale; "
        "no readings inside the window"
    )


def triaged_record(monkeypatch, setting):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "on")
    monkeypatch.setenv("TRIAGE_EVIDENCE_TESTS", setting)
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], triage_then_deep, name="triaged", triage=True)
    return record


@pytest.mark.parametrize(("setting", "on"), [("on", True), ("off", False)])
def test_an_experiment_records_whether_the_rules_were_on(monkeypatch, setting, on):
    record = triaged_record(monkeypatch, setting)
    assert record.triage.evidence_tests is on
    assert isinstance(record.triage.test_records, list)
    line = format_evidence_tests([record])
    assert line.startswith(f"evidence tests: on in {int(on)} of 1 triage(s)")
    assert line in report([record], {})


def test_the_report_counts_what_the_rules_changed(monkeypatch):
    record = triaged_record(monkeypatch, "on")
    withheld = TriageTestRecord(
        kind="support_withheld_shared_root", stage="test", tick=10
    )
    closed = TriageTestRecord(kind="question_closed", stage="test", tick=10)
    changed = record.model_copy(
        update={
            "triage": record.triage.model_copy(
                update={"test_records": [withheld, closed]}
            )
        }
    )
    line = format_evidence_tests([changed])
    assert "changed an outcome in 1" in line
    assert "1 (one sensor counted twice)" in line
    assert "closed by a measured verdict 1" in line


def test_runs_without_a_kept_setting_have_no_line(monkeypatch):
    record = triaged_record(monkeypatch, "on")
    older = record.model_copy(
        update={"triage": record.triage.model_copy(update={"evidence_tests": None})}
    )
    assert format_evidence_tests([older]) is None
    assert format_evidence_tests([]) is None
