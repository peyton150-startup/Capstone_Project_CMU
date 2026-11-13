"""The read-only triage report (Block 5, 2026-11-13).

`conclude()` builds a `TriageReport` in every triage, after the Python checks:
it carries the model's diagnosis only when the model concluded, links every
finding to the tool and tick it came from, and, when no model answer
survived, names no cause and clears nothing. Deep runs never build one.
"""

import json

from capstone.agent.investigation import UNDETERMINED
from capstone.agent.state import TerminationReason
from capstone.agent.triage_report import (
    EXCERPT_CHARS,
    MAX_UNCONCLUDED_FINDINGS,
    build_triage_report,
)
from capstone.experiment import Case, run_experiment
from tests.test_episode import SEED, wear_policy
from tests.test_triage import (
    ByMode,
    NoConclusion,
    add_evidence,
    clear,
    clearance_state,
    run,
)

# --- built in a triage, from what the checks left --------------------------------


def test_a_triage_the_model_concluded_reports_its_checked_diagnosis(monkeypatch):
    result = run(
        ByMode(wear_policy("intervene"), wear_policy()),
        monkeypatch,
        then_deep=False,
        triage=True,
    )
    first = result.triage
    report = first.triage_report
    assert report.outcome == "model_conclusion"
    assert report.diagnosis == first.conclusion.diagnosis
    assert report.recommendation == first.conclusion.recommendation
    assert report.model_recommendation == first.policy_recommendation
    assert report.deep_recommended is first.deep_recommended
    assert report.machine_id == first.anomaly.machine_id
    assert report.alarm_tick == first.anomaly.tick


def test_every_finding_links_to_the_reading_it_came_from(monkeypatch):
    result = run(
        ByMode(wear_policy("intervene"), wear_policy()),
        monkeypatch,
        then_deep=False,
        triage=True,
    )
    first = result.triage
    report = first.triage_report
    gathered = {e.id: e for e in first.evidence}
    assert [f.evidence_id for f in report.findings] == list(
        first.conclusion.evidence_ids
    )
    for item in report.findings:
        evidence = gathered[item.evidence_id]
        assert item.source_id == evidence.source_id
        assert item.observed_tick == evidence.observed_tick


def test_no_model_answer_gives_no_cause_and_clears_nothing(monkeypatch):
    policy = ByMode(NoConclusion(wear_policy("intervene"), 2), wear_policy())
    first = run(policy, monkeypatch, then_deep=False, triage=True).triage
    report = first.triage_report
    assert report.outcome == "no_model_answer"
    assert report.termination_reason == "model_unavailable"
    assert report.diagnosis is None
    assert report.assessment == "unresolved"
    assert report.recommendation == "escalate"
    assert report.confidence == 0.0
    assert report.deep_recommended is True
    assert "nothing is cleared" in report.summary
    assert "model_unavailable" in report.summary


def test_without_a_model_answer_the_findings_are_the_factory_readings(monkeypatch):
    policy = ByMode(NoConclusion(wear_policy("intervene"), 2), wear_policy())
    first = run(policy, monkeypatch, then_deep=False, triage=True).triage
    observed = [p.evidence_id for p in first.provenance if p.origin == "observable"]
    report = first.triage_report
    assert [f.evidence_id for f in report.findings] == observed[
        :MAX_UNCONCLUDED_FINDINGS
    ]
    assert all(f.origin == "observable" for f in report.findings)


def test_a_triage_out_of_time_before_any_model_is_asked_is_reported_as_such(
    monkeypatch,
):
    policy = ByMode(NoConclusion(wear_policy("intervene"), 0), wear_policy())
    report = run(policy, monkeypatch, then_deep=False, triage=True).triage.triage_report
    assert report.outcome == "no_model_answer"
    assert report.termination_reason == "timeout"
    assert report.diagnosis is None


def test_a_deep_run_builds_no_report(monkeypatch):
    monkeypatch.delenv("TRIAGE", raising=False)
    result = run(wear_policy(), monkeypatch)
    assert result.state.mode == "deep"
    assert result.state.triage_report is None


def test_the_deep_run_after_a_triage_builds_no_report_of_its_own(monkeypatch):
    result = run(
        ByMode(wear_policy("intervene"), wear_policy()),
        monkeypatch,
        then_deep=True,
        triage=True,
    )
    assert result.triage.triage_report is not None
    assert result.state is not result.triage
    assert result.state.triage_report is None


def test_the_same_seed_gives_the_same_report(monkeypatch):
    def once():
        policy = ByMode(wear_policy("intervene"), wear_policy())
        return run(policy, monkeypatch, then_deep=False, triage=True).triage

    assert once().triage_report == once().triage_report


# --- the builder on its own ----------------------------------------------------------


def checked(state, **changes):
    """A state after the final check, as conclude() leaves it for the builder."""
    state.conclusion = clear(state, **changes)
    state.policy_recommendation = changes.get("recommendation", "no_action")
    state.deep_recommended = True
    return state


def test_every_reason_the_checks_held_the_answer_open_is_reported():
    state = checked(clearance_state(screening="machine_unscored"))
    report = build_triage_report(state)
    assert report.outcome == "model_conclusion"
    assert report.assessment == "unresolved"
    assert report.recommendation == "escalate"
    assert report.model_recommendation == "no_action"
    assert report.held_open_because == tuple(
        g.text for g in state.conclusion_trace.gaps
    )
    assert any("CNC-01" in reason for reason in report.held_open_because)


def test_a_supported_clearance_reports_no_reason_to_hold_it_open():
    state = checked(clearance_state())
    state.deep_recommended = False
    report = build_triage_report(state)
    assert report.assessment == "supported"
    assert report.recommendation == "no_action"
    assert report.held_open_because == ()
    assert report.deep_recommended is False


def test_a_refused_model_answer_is_reported_without_its_cause():
    state = clearance_state()
    state.conclusion = UNDETERMINED
    state.conclusion_rejected = "the conclusion cites evidence that was not gathered"
    report = build_triage_report(state)
    assert report.outcome == "model_answer_refused"
    assert report.refused_because == state.conclusion_rejected
    assert report.diagnosis is None
    assert report.recommendation == "escalate"
    assert "refused" in report.summary


def test_a_manual_passage_is_never_listed_as_a_reading_without_a_conclusion():
    state = clearance_state()
    add_evidence(state, "E9", "manual:search_manual", {"text": "normal is < 5"})
    state.provenance[-1] = state.provenance[-1].model_copy(update={"origin": "manual"})
    state.conclusion = UNDETERMINED
    state.termination_reason = TerminationReason.TIMEOUT
    report = build_triage_report(state)
    assert "E9" not in {f.evidence_id for f in report.findings}


def test_long_readings_are_cut_and_extra_readings_are_counted():
    state = clearance_state()
    add_evidence(state, "E4", "simulator:get_sensor_history", {"values": "x" * 500})
    for n in range(MAX_UNCONCLUDED_FINDINGS):
        add_evidence(state, f"F{n}", "simulator:get_sensor_summary", {"n": n})
    state.conclusion = UNDETERMINED
    state.termination_reason = TerminationReason.TIMEOUT
    report = build_triage_report(state)
    assert len(report.findings) == MAX_UNCONCLUDED_FINDINGS
    long = next(f for f in report.findings if f.evidence_id == "E4")
    assert len(long.excerpt) == EXCERPT_CHARS and long.excerpt.endswith("...")
    total = MAX_UNCONCLUDED_FINDINGS + 4  # E1, E2, E3 and E4 come first
    assert f"{total} reading(s)" in report.summary
    assert f"({total - MAX_UNCONCLUDED_FINDINGS} not listed)" in report.summary


# --- kept in the experiment record --------------------------------------------------


def test_the_experiment_record_keeps_the_report(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment(
        [case],
        lambda: ByMode(NoConclusion(wear_policy("intervene"), 1), wear_policy()),
        name="report",
        triage=True,
    )
    report = record.triage.report
    assert report is not None and report.outcome == "no_model_answer"
    # It survives the records file.
    again = json.loads(record.model_dump_json())["triage"]["report"]
    assert again["diagnosis"] is None and again["recommendation"] == "escalate"
