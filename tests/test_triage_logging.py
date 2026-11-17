"""Logging for the 2026-11-13 triage blocks (built 2026-11-14).

The progress view prints the fixed plan (TRIAGE_PLAN=fixed) with its
predicates and the read-only triage report; the experiment report counts
where triage plans came from and how the reports ended.
"""

import json

from capstone.agent.state import Predicate
from capstone.agent.triage_report import build_triage_report
from capstone.experiment import (
    Case,
    ExperimentRecord,
    format_triage_outcomes,
    run_experiment,
)
from capstone.progress import (
    MAX_REPORT_REASONS,
    ProgressView,
    predicate_text,
    report_lines,
)
from tests.test_episode import SEED, wear_policy
from tests.test_triage import ByMode, clearance_state, run, triage_then_deep
from tests.test_triage_report import NoConclusion, checked


def watched(monkeypatch, policy, **env):
    """The progress view's lines for one scripted triage, with `env` set."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    lines = []
    run(
        policy,
        monkeypatch,
        then_deep=False,
        triage=True,
        watch=ProgressView(lines.append),
    )
    return lines


# --- the progress view -------------------------------------------------------------


def test_a_fixed_plan_is_printed_once_with_its_predicate(monkeypatch):
    lines = watched(
        monkeypatch,
        ByMode(wear_policy("intervene"), wear_policy()),
        TRIAGE_PLAN="fixed",
    )
    plans = [line for line in lines if line.startswith("PLAN fixed table")]
    assert plans == [
        "PLAN fixed table (no model call): 5 question(s) Q1, Q2, Q3, Q4, Q5; "
        "1 with a predicate"
    ]
    (predicate,) = [line for line in lines if line.startswith("  predicate Q1:")]
    assert "vibration on CNC-02" in predicate and "above" in predicate
    # TRIAGE_PACKET is on by default, so the screening question is answered.
    (screening,) = [line for line in lines if line.startswith("  screening Q2:")]
    assert "answered by E" in screening and "every roster machine" in screening


def test_a_model_plan_prints_no_fixed_plan_line(monkeypatch):
    # Model planning remains available as an explicit comparison arm.
    monkeypatch.setenv("TRIAGE_PLAN", "model")
    monkeypatch.setenv("TRIAGE_INVESTIGATE", "advisory")
    lines = watched(monkeypatch, ByMode(wear_policy("intervene"), wear_policy()))
    assert not any(line.startswith("PLAN fixed table") for line in lines)


def test_the_triage_report_is_printed_once_after_the_conclusion(monkeypatch):
    lines = watched(monkeypatch, ByMode(wear_policy("intervene"), wear_policy()))
    reports = [i for i, line in enumerate(lines) if line.startswith("TRIAGE REPORT")]
    conclusion = next(
        i for i, line in enumerate(lines) if line.startswith("CONCLUSION")
    )
    assert len(reports) == 1 and reports[0] > conclusion
    assert lines[reports[0]].startswith("TRIAGE REPORT model_conclusion:")
    assert any(line.startswith("  summary: ") for line in lines[reports[0] :])


def test_without_a_model_answer_the_report_line_says_so(monkeypatch):
    policy = ByMode(NoConclusion(wear_policy("intervene"), 2), wear_policy())
    lines = watched(monkeypatch, policy)
    (line,) = [line for line in lines if line.startswith("TRIAGE REPORT")]
    assert line.startswith("TRIAGE REPORT no_model_answer: unresolved, escalate")
    assert "deep run recommended" in line


def test_report_lines_list_why_the_checks_held_it_open():
    report = build_triage_report(checked(clearance_state(screening="machine_unscored")))
    lines = report_lines(report)
    held = [line for line in lines if line.startswith("  held open: ")]
    assert held and len(held) <= MAX_REPORT_REASONS + 1
    assert any("CNC-01" in line for line in held)


def test_a_refused_answer_prints_why():
    from capstone.agent.investigation import UNDETERMINED

    state = clearance_state()
    state.conclusion = UNDETERMINED
    state.conclusion_rejected = "the conclusion cites evidence that was not gathered"
    lines = report_lines(build_triage_report(state))
    assert lines[0].startswith("TRIAGE REPORT model_answer_refused:")
    assert any(line.startswith("  refused: the conclusion cites") for line in lines)


def test_predicate_text_reads_as_one_phrase():
    predicate = Predicate(
        machine_id="CNC-05",
        sensor="hydraulic_pressure",
        from_tick=0,
        to_tick=25,
        statistic="mean",
        comparison="below",
        threshold=65.0,
    )
    assert predicate_text(predicate) == (
        "mean hydraulic_pressure on CNC-05 over t=0-25 below 65 (at least 10 readings)"
    )


# --- the experiment report ----------------------------------------------------------


def test_the_report_counts_plans_and_report_outcomes(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    monkeypatch.setenv("TRIAGE_PLAN", "fixed")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (fixed,) = run_experiment([case], triage_then_deep, name="fixed", triage=True)
    monkeypatch.setenv("TRIAGE_PLAN", "model")
    (unanswered,) = run_experiment(
        [case],
        lambda: ByMode(NoConclusion(wear_policy("intervene"), 1), wear_policy()),
        name="none",
        triage=True,
    )
    line = format_triage_outcomes([fixed, unanswered])
    assert line.startswith("triage plan: 1 fixed table, 1 model; ")
    assert "1 model conclusion, 0 refused, 1 no model answer, 0 none" in line
    assert line.endswith("0 cleared without a model conclusion")


def test_older_records_without_a_report_count_as_none(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], triage_then_deep, name="old", triage=True)
    data = json.loads(record.model_dump_json())
    data["triage"].pop("report")
    data["triage"].pop("fixed_plan")
    old = ExperimentRecord.model_validate(data)
    line = format_triage_outcomes([old])
    assert "0 fixed table, 1 model" in line and "1 none" in line


def test_no_triage_gives_no_line(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.delenv("TRIAGE", raising=False)
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], lambda: wear_policy(), name="deep")
    assert format_triage_outcomes([record]) is None
