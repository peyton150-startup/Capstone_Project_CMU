"""Terminal diagnostics for triage: profile line, --trace events, ledger."""

from capstone.agent.state import InvestigationState
from capstone.agent.triage_report import TriageReport
from capstone.agent.triage_requirements import RequirementResult
from capstone.agent.triage_trace import TriageTraceEvent
from capstone.experiment import main
from capstone.progress import (
    ProgressView,
    requirement_ledger_lines,
    run_header,
    trace_event_line,
)
from capstone.settings import Settings
from tests.test_progress_view import run


def a_state() -> InvestigationState:
    seen = []
    run(watch=seen.append)
    return seen[-1].model_copy(deep=True)


def event(sequence: int, **fields) -> TriageTraceEvent:
    return TriageTraceEvent(
        sequence=sequence,
        event=fields.pop("event", "triage.read_selected"),
        phase=fields.pop("phase", "investigate"),
        reason_code=fields.pop("reason_code", "requirement_pending"),
        **fields,
    )


def report() -> TriageReport:
    return TriageReport(
        machine_id="CNC-02",
        alarm="vibration high",
        alarm_tick=5,
        outcome="no_model_answer",
        assessment="unresolved",
        recommendation="escalate",
        confidence=0.0,
        deep_recommended=True,
        summary="held open",
    )


def test_a_trace_line_names_the_event_and_only_the_fields_that_are_set():
    line = trace_event_line(
        event(
            3,
            tool="get_readings",
            requirement_ids=("Q1:failed_jobs",),
            request_hash="a" * 20,
            remaining_tool_calls=4,
            duration_ms=12.4,
        )
    )
    assert line == (
        "TRACE #3 investigate triage.read_selected; reason requirement_pending; "
        "tool get_readings; requirements Q1:failed_jobs; request "
        + "a" * 20
        + "; calls left 4; 12 ms"
    )
    assert trace_event_line(event(1)) == (
        "TRACE #1 investigate triage.read_selected; reason requirement_pending"
    )


def test_trace_events_print_only_with_trace_and_each_once():
    state = a_state()
    state.triage_trace_events = [event(1), event(2, status="ok")]
    quiet, loud = [], []
    ProgressView(quiet.append)(state)
    view = ProgressView(loud.append, trace=True)
    view(state)
    view(state)
    assert not any(line.startswith("TRACE #") for line in quiet)
    assert [line for line in loud if line.startswith("TRACE #")] == [
        "TRACE #1 investigate triage.read_selected; reason requirement_pending",
        "TRACE #2 investigate triage.read_selected; reason requirement_pending; "
        "status ok",
    ]


def test_the_ledger_counts_statuses_and_gives_stable_reason_codes():
    state = a_state()
    state.triage_requirement_results = {
        "Q4:settings": RequirementResult(
            status="insufficient",
            reason="current settings snapshot does not establish a historical change",
        ),
        "Q1:failed_jobs": RequirementResult(
            status="satisfied", evidence_ids=("E1", "E2"), reason="free text"
        ),
        "Q2:readings": RequirementResult(status="unavailable", reason="tool down"),
    }
    assert requirement_ledger_lines(state) == [
        "REQUIREMENTS: insufficient 1, satisfied 1, unavailable 1",
        "  Q1:failed_jobs: satisfied (requirement_satisfied; 2 evidence)",
        "  Q2:readings: unavailable (requirement_unavailable; 0 evidence)",
        "  Q4:settings: insufficient (historical_setting_unproven; 0 evidence)",
    ]
    state.triage_requirement_results = {}
    assert requirement_ledger_lines(state) == []


def test_the_ledger_prints_once_with_the_triage_report():
    state = a_state()
    state.triage_requirement_results = {
        "Q1:failed_jobs": RequirementResult(status="partial", reason="x")
    }
    lines = []
    view = ProgressView(lines.append)
    view(state)
    assert not any(line.startswith("REQUIREMENTS") for line in lines)
    state.triage_report = report()
    view(state)
    view(state)
    assert [line for line in lines if line.startswith("REQUIREMENTS")] == [
        "REQUIREMENTS: partial 1"
    ]


def test_the_header_names_the_effective_profile_only_for_a_triage_run():
    det = Settings(_env_file=None, triage_run_mode="deterministic")
    assert not any("triage profile" in line for line in run_header(det, manual=None))
    lines = run_header(det, manual=None, triage=True)
    assert (
        "RUN: triage profile deterministic: plan fixed, investigate "
        "deterministic, hypothesize deterministic, evidence tests on, critic off; "
        "model-backed stages: conclude"
    ) in lines
    custom = Settings(
        _env_file=None,
        triage_plan="model",
        triage_investigate="advisory",
        triage_hypothesize="model",
    )
    (line,) = [
        line
        for line in run_header(custom, manual=None, triage=True)
        if "triage profile" in line
    ]
    assert line.startswith("RUN: triage profile custom: plan model")
    assert line.endswith(
        "model-backed stages: conclude, plan, investigate, hypothesize"
    )


def test_the_triage_model_line_says_conclusion_only_when_deterministic():
    det = Settings(_env_file=None, triage_run_mode="deterministic", triage_model="m")
    custom = Settings(_env_file=None, triage_model="m")
    assert "RUN: triage model m (triage conclusion only; thinking off)" in run_header(
        det, manual=None
    )
    assert "RUN: triage model m (every triage question; thinking off)" in run_header(
        custom, manual=None
    )


def test_the_run_command_accepts_trace(tmp_path, monkeypatch):
    seen = {}

    def fake_run_experiment(cases, policy, **options):
        seen.update(options)
        return []

    monkeypatch.setattr("capstone.experiment.run_experiment", fake_run_experiment)
    monkeypatch.setattr(
        "capstone.experiment.model_policy_factory", lambda with_recall, **_: None
    )
    out = tmp_path / "r.jsonl"
    argv = ["run", "--name", "t", "--known", "--no-manual", "--out", str(out)]
    assert main([*argv, "--no-audit", "--trace"]) == 0
    assert seen["trace"] is True
    assert main([*argv, "--no-audit", "--quiet"]) == 0
    assert seen["trace"] is False
