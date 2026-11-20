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


def read_events():
    """One accepted read reconciled into two requirements, then a rejected one."""
    h1, h2 = "1" * 20, "2" * 20
    return [
        event(
            1,
            event="decide.selected",
            reason_code="selected",
            tool="get_sensor_summary",
            requirement_ids=("Q1:trigger",),
            request_hash=h1,
            attempt=1,
        ),
        event(
            2,
            event="triage.evidence_accepted",
            reason_code="accepted",
            tool="get_sensor_summary",
            request_hash=h1,
            attempt=1,
            evidence_ids=("E2",),
        ),
        event(
            3,
            event="tool.completed",
            reason_code="observed",
            status="accepted",
            tool="get_sensor_summary",
            request_hash=h1,
            attempt=1,
            evidence_ids=("E2",),
            duration_ms=4.0,
        ),
        event(
            4,
            event="triage.requirement_evaluated",
            reason_code="requirement_satisfied",
            status="satisfied",
            requirement_ids=("Q1:trigger",),
            evidence_ids=("E2",),
        ),
        event(
            5,
            event="triage.requirement_evaluated",
            reason_code="requirement_satisfied",
            status="satisfied",
            requirement_ids=("Q5:vibration",),
            evidence_ids=("E2",),
        ),
        event(
            6,
            event="decide.selected",
            reason_code="selected",
            phase="test",
            tool="get_events",
            requirement_ids=("Q3:events",),
            request_hash=h2,
            attempt=2,
        ),
        event(
            7,
            event="triage.evidence_rejected",
            reason_code="invalid_shape",
            phase="test",
            tool="get_events",
            request_hash=h2,
            attempt=2,
        ),
        event(
            8,
            event="tool.completed",
            reason_code="invalid_shape",
            status="failed",
            phase="test",
            tool="get_events",
            request_hash=h2,
            attempt=2,
            duration_ms=1.0,
        ),
    ]


def test_reads_are_joined_by_request_hash_through_to_the_ledger():
    from capstone.progress import read_lines

    every = read_lines(read_events(), every=True)
    assert every == [
        "READS:",
        "  READ " + "1" * 20 + " investigate get_sensor_summary [Q1:trigger] -> "
        "validation accepted -> completed accepted (4 ms) -> "
        "ledger Q1:trigger satisfied, Q5:vibration satisfied",
        "  READ " + "2" * 20 + " test get_events attempt 2 [Q3:events] -> "
        "validation invalid_shape -> completed failed (1 ms)",
    ]
    assert read_lines(read_events(), every=False) == ["FAILED READS:", every[2]]
    assert read_lines(read_events()[:5], every=False) == []


def test_a_completion_conversion_is_printed_even_without_trace():
    state = a_state()
    state.triage_trace_events = [
        event(
            1,
            event="triage.completion_converted",
            phase="test",
            reason_code="data_insufficient",
            status="stopped",
            requirement_ids=("Q4:setting_change",),
            question_ids=("Q4",),
        )
    ]
    lines = []
    view = ProgressView(lines.append)
    view(state)
    view(state)
    assert (
        lines.count(
            "COMPLETION CONVERTED (test): requirements_complete -> data_insufficient; "
            "unresolved Q4:setting_change; open questions Q4"
        )
        == 1
    )


def test_the_failed_reads_follow_the_ledger_with_the_report():
    state = a_state()
    state.triage_trace_events = read_events()
    state.triage_requirement_results = {
        "Q3:events": RequirementResult(status="pending")
    }
    lines = []
    ProgressView(lines.append)(state.model_copy(update={"triage_report": report()}))
    at = lines.index("REQUIREMENTS: pending 1")
    assert lines[at + 2] == "FAILED READS:"


def fake_record(termination="no_useful_action"):
    from types import SimpleNamespace

    from capstone.agent.model_policy import Attempt, ModelCall

    events = [
        event(
            1,
            event="triage.started",
            reason_code="started",
            config_fingerprint="f" * 20,
            source_cutoff_tick=45,
        ),
        *read_events(),
        event(
            9,
            event="triage.stopped",
            phase="test",
            reason_code="data_insufficient",
            status="stopped",
        ),
    ]
    triage = SimpleNamespace(
        diagnostic_trace=events,
        conclude_model_seconds=2.5,
        conclude_check_seconds=0.004,
        termination_reason=termination,
        triage_run_mode="deterministic",
        requirement_results={
            "Q1:trigger": RequirementResult(status="satisfied"),
            "Q4:setting_change": RequirementResult(
                status="insufficient",
                reason="current settings snapshot does not establish a historical change",
            ),
        },
    )
    calls = (
        ModelCall(
            job="conclude",
            outcome="answered",
            mode="triage",
            stage="conclude",
            attempts=(
                Attempt(model="a", outcome="timeout", seconds=2.0),
                Attempt(model="b", outcome="answered", seconds=0.5),
            ),
        ),
    )
    return SimpleNamespace(
        triage=triage,
        model_calls=SimpleNamespace(details=calls),
        run_key="n/1/s",
        scenario_id="s",
        seed=7,
        conclusion=None,
    )


def test_timing_separates_deterministic_reads_from_the_conclusion_model():
    from capstone.triage_diagnostics import timing_lines

    assert timing_lines(fake_record()) == [
        "TIMING: investigate reads 1 (4 ms); test reads 1 (1 ms); "
        "conclude model 2.50 s (1 question(s), 2 attempt(s): a timeout 2.0 s, "
        "b answered 0.5 s); conclude checks 0.004 s"
    ]


def test_the_failure_summary_has_what_a_replay_needs_and_only_codes():
    from capstone.triage_diagnostics import failure_summary

    assert failure_summary(fake_record("evidence_sufficient"), "n") is None
    assert failure_summary(fake_record(), "n") == {
        "name": "n",
        "run_key": "n/1/s",
        "scenario_id": "s",
        "seed": 7,
        "triage_run_mode": "deterministic",
        "config_fingerprint": "f" * 20,
        "source_cutoff_tick": 45,
        "termination_reason": "no_useful_action",
        "stops": [{"phase": "test", "reason": "data_insufficient"}],
        "completion_converted": False,
        "unresolved_requirements": {"Q4:setting_change": "historical_setting_unproven"},
        "failed_reads": [
            {
                "phase": "test",
                "tool": "get_events",
                "request_hash": "2" * 20,
                "attempt": 2,
                "reason": "invalid_shape",
            }
        ],
    }


def test_the_run_command_writes_the_failure_log(tmp_path, monkeypatch, capsys):
    import json

    def fake_run_experiment(cases, policy, **options):
        options["on_record"](fake_record())
        return []

    monkeypatch.setattr("capstone.experiment.run_experiment", fake_run_experiment)
    monkeypatch.setattr("capstone.experiment.append_records", lambda *a: None)
    monkeypatch.setattr("capstone.experiment.format_call_failures", lambda r: [])
    monkeypatch.setattr(
        "capstone.experiment.model_policy_factory", lambda with_recall, **_: None
    )
    log = tmp_path / "failures.jsonl"
    argv = [
        "run",
        "--name",
        "n",
        "--known",
        "--no-manual",
        "--no-audit",
        "--out",
        str(tmp_path / "r.jsonl"),
        "--failure-log",
        str(log),
    ]
    assert main(argv) == 0
    (line,) = log.read_text().splitlines()
    assert json.loads(line)["seed"] == 7
    out = capsys.readouterr().out
    assert "TIMING: investigate reads 1" in out
    assert "REPLAY: {" in out
