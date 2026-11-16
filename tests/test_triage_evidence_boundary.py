"""Pre-commit validation and operational traces for deterministic triage only."""

import json
from io import StringIO

import pytest
from pydantic import ValidationError

from capstone.agent.loop import gather, run_inner_loop
from capstone.agent.policy import CallTool
from capstone.agent.triage_decide import initialize_requirements, matching_evidence
from capstone.agent.triage_evidence_validation import validate_triage_result
from capstone.agent.triage_trace import TriageTraceEvent
from capstone.contracts.tools import ToolRequest, ToolResult
from capstone.observability import create_event_logger
from capstone.providers.factory import tool_spec
from tests.helpers import START, FakeProvider
from tests.test_triage_deterministic_decide import answer, deps_for, state_for


def test_qualified_read_is_committed_with_ordered_source_linked_trace():
    stream = StringIO()
    state = state_for()
    provider = FakeProvider(answer, tick=45)
    deps = deps_for(provider)
    deps.event_logger = create_event_logger(stream)
    run_inner_loop(state, deps, "investigate")

    assert state.triage_evidence_checks
    assert any(x.accepted and x.evidence_id for x in state.triage_evidence_checks)
    assert [e.sequence for e in state.triage_trace_events] == list(
        range(1, len(state.triage_trace_events) + 1)
    )
    assert state.triage_trace_events[-1].event == "triage.stopped"
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(events) == len(state.triage_trace_events)
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert all("data" not in event and "arguments" not in event for event in events)


def test_precommit_rejection_keeps_wrong_source_out_of_evidence():
    state = state_for()

    def wrong_source(request):
        data = answer(request)
        if request.name == "get_sensor_summary":
            data["machine_id"] = "CNC-PRIVATE"
        return data

    provider = FakeProvider(wrong_source, tick=45)
    deps = deps_for(
        provider,
        tools=(tool_spec("get_sensor_summary"),),
        channels={"CNC-02": ("vibration",)},
    )
    run_inner_loop(state, deps, "investigate")
    assert state.evidence == []
    assert state.provenance == []
    assert all(not x.accepted for x in state.triage_evidence_checks)
    assert "wrong_source" in {x.reason_code for x in state.triage_evidence_checks}
    assert any(e.event == "triage.evidence_rejected" for e in state.triage_trace_events)
    assert all(d.evidence_ids == () for d in state.decisions if d.tool)


def test_future_result_is_rejected_before_commit_and_tick_restored():
    state = state_for()
    provider = FakeProvider(answer, tick=46)
    deps = deps_for(
        provider,
        tools=(tool_spec("get_sensor_summary"),),
        channels={"CNC-02": ("vibration",)},
    )
    run_inner_loop(state, deps, "investigate")
    assert not state.evidence and not state.provenance
    assert state.last_tick == 45
    assert state.triage_observation_cutoff_tick == 45
    assert all(x.reason_code == "future_tick" for x in state.triage_evidence_checks)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"sample_count": 12, "first_tick": 35, "last_tick": 46}, "future_tick"),
        ({"sensor": "load"}, "wrong_source"),
        ({"mean": float("nan")}, "invalid_numeric"),
        ({"first_tick": 46}, "future_tick"),
        ({"from_tick": 10}, "outside_window"),
    ],
)
def test_validator_rejects_invalid_provider_payload(change, reason):
    request = ToolRequest(
        name="get_sensor_summary",
        arguments={
            "machine_id": "CNC-02",
            "sensor": "vibration",
            "from_tick": 20,
            "to_tick": 45,
        },
    )
    response_data = {
        "machine_id": "CNC-02",
        "sensor": "vibration",
        "from_tick": 20,
        "to_tick": 45,
        "sample_count": 12,
        "first_tick": 30,
        "last_tick": 45,
        "mean": 4.6,
        "delta": 0.2,
    }
    response_data.update(change)
    result = ToolResult(
        success=True,
        tool="get_sensor_summary",
        source="fake",
        tick=45,
        timestamp=START,
        data=response_data,
    )
    assert validate_triage_result(result, request, 45).reason_code == reason


def test_logging_failure_does_not_affect_controller_decisions():
    class FailingLogger:
        def log_event(self, *args, **kwargs):
            raise OSError("logging unavailable")

    state = state_for()
    provider = FakeProvider(answer, tick=45)
    deps = deps_for(provider)
    deps.event_logger = FailingLogger()
    run_inner_loop(state, deps, "investigate")

    assert state.triage_logging_failures > 0
    assert state.triage_decide_trace[-1].kind == "stop"
    assert state.triage_trace_events[-1].event == "triage.stopped"
    assert state.triage_evidence_checks


def test_pydantic_trace_rejects_free_form_reason_and_nonfinite_duration():
    with pytest.raises(ValidationError):
        TriageTraceEvent(
            sequence=1,
            event="triage.stopped",
            phase="investigate",
            reason_code="password=secret\n",
        )
    with pytest.raises(ValidationError):
        TriageTraceEvent(
            sequence=1,
            event="triage.stopped",
            phase="investigate",
            reason_code="timeout",
            duration_ms=float("inf"),
        )


def test_reused_observe_summary_must_pass_same_source_validation():
    state = state_for()
    request = ToolRequest(
        name="get_sensor_summary",
        arguments={
            "machine_id": "CNC-02",
            "sensor": "vibration",
            "from_tick": 20,
            "to_tick": 45,
        },
    )

    def incorrect(request):
        return {**answer(request), "sensor": "load"}

    deps = deps_for(FakeProvider(incorrect, tick=45))
    # Simulate a preexisting Observe result gathered without the new hook.
    evidence = gather(
        state,
        deps,
        "observe",
        CallTool(information_needed="existing Observe summary", request=request),
        interpret=False,
    )
    assert evidence is not None
    initialize_requirements(state)
    requirement = state.triage_requirements["Q1:trigger"]
    assert matching_evidence(state, requirement) == []
