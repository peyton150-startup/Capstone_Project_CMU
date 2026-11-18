"""Pre-commit validation and operational traces for deterministic triage only."""

import json
from io import StringIO

import pytest
from pydantic import ValidationError

from capstone.agent.loop import gather, run_inner_loop
from capstone.agent.policy import CallTool
from capstone.agent.triage_decide import initialize_requirements, matching_evidence
from capstone.agent.triage_evidence_validation import (
    EvidenceQualification,
    validate_triage_result,
)
from capstone.agent.triage_packet import optional_call
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

    from capstone.agent.artifacts import AgentConclusion, TerminationReason
    from capstone.agent.completion import AuditRecord, audit_record

    state.conclusion = AgentConclusion(
        diagnosis="not yet established",
        confidence=0,
        recommendation="escalate",
        assessment="unresolved",
    )
    state.termination_reason = TerminationReason.NO_USEFUL_ACTION
    audit = audit_record(state)
    assert audit.triage_trace_events == tuple(state.triage_trace_events)
    assert AuditRecord.model_validate_json(audit.model_dump_json()).triage_trace_events
    legacy = audit.model_dump(mode="json")
    legacy.pop("triage_trace_events")
    assert AuditRecord.model_validate(legacy).triage_trace_events == ()


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


def test_deterministic_observe_packet_rejects_invalid_sensor_before_commit():
    state = state_for()
    state.started_at = 0.0

    def wrong(request):
        return {**answer(request), "sensor": "load"}

    deps = deps_for(FakeProvider(wrong, tick=45))
    call, evidence = optional_call(
        state,
        deps,
        "get_sensor_summary",
        {
            "machine_id": "CNC-02",
            "sensor": "vibration",
            "from_tick": 20,
            "to_tick": 45,
        },
        "source check",
        6,
    )
    assert evidence is None
    assert call.outcome == "failed"
    assert not state.evidence and not state.provenance
    assert state.triage_evidence_checks[-1].reason_code == "wrong_source"


@pytest.mark.parametrize(
    ("name", "arguments", "rows", "expected"),
    [
        (
            "get_events",
            {"machine_id": "CNC-02", "from_tick": 20, "to_tick": 45},
            [{"tick": 19, "machine_id": "CNC-02"}],
            "outside_window",
        ),
        (
            "get_events",
            {"machine_id": "CNC-02", "from_tick": 20, "to_tick": 45},
            [{"tick": 30, "machine_id": "CNC-04"}],
            "wrong_source",
        ),
        (
            "get_job_history",
            {"job_id": 10},
            [{"tick": 30, "job_id": 11, "machine_id": "CNC-02"}],
            "wrong_source",
        ),
        (
            "get_maintenance_history",
            {"machine_id": "CNC-02"},
            [{"tick": None, "machine_id": "CNC-04"}],
            "wrong_source",
        ),
        (
            "get_inspections",
            {"from_tick": 20, "to_tick": 45},
            [{"tick": 46, "job_id": 10, "result": "failed"}],
            "future_tick",
        ),
        (
            "get_inspections",
            {"from_tick": 20, "to_tick": 45},
            [{"tick": 19, "job_id": 10, "result": "failed"}],
            "outside_window",
        ),
        (
            "get_inspections",
            {"from_tick": 20, "to_tick": 45},
            [{"tick": 30, "job_id": 0, "result": "failed"}],
            "invalid_shape",
        ),
        (
            "get_maintenance_history",
            {"machine_id": "CNC-02"},
            [
                {
                    "tick": None,
                    "machine_id": "CNC-02",
                    "performed_at": "2026-01-01T00:00:00",
                    "kind": "service",
                    "note": "",
                }
            ],
            "accepted",
        ),
        (
            "get_events",
            {"machine_id": "CNC-02", "from_tick": 20, "to_tick": 45},
            [
                {
                    "tick": 30,
                    "machine_id": "CNC-02",
                    "kind": "alarm",
                    "message": "",
                    "job_id": None,
                }
            ],
            "accepted",
        ),
    ],
)
def test_record_admission_checks_requested_source_and_time(
    name, arguments, rows, expected
):
    request = ToolRequest(name=name, arguments=arguments)
    response = ToolResult(
        success=True,
        tool=name,
        source="fake",
        tick=45,
        timestamp=START,
        data=rows,
    )
    checked = validate_triage_result(response, request, 45)
    assert checked.reason_code == expected
    assert checked.accepted == (expected == "accepted")


def test_qualification_contract_rejects_conflicting_decision():
    with pytest.raises(ValidationError):
        EvidenceQualification(accepted=True, reason_code="wrong_source")
    with pytest.raises(ValidationError):
        EvidenceQualification(accepted=False, reason_code="accepted")


def test_provider_tool_name_is_verified_during_evidence_admission():
    request = ToolRequest(
        name="get_events",
        arguments={"machine_id": "CNC-02", "from_tick": 20, "to_tick": 45},
    )
    response = ToolResult(
        success=True,
        tool="get_job_history",
        source="fake",
        tick=45,
        timestamp=START,
        data=[],
    )
    assert validate_triage_result(response, request, 45).reason_code == "wrong_source"


def test_unexpected_logger_exception_does_not_affect_trace_or_stop():
    class BrokenLogger:
        def log_event(self, *args, **kwargs):
            raise RuntimeError("broken logging backend")

    state = state_for()
    deps = deps_for(FakeProvider(answer, tick=45))
    deps.event_logger = BrokenLogger()
    run_inner_loop(state, deps, "investigate")
    assert state.triage_logging_failures > 0
    assert state.triage_trace_events[-1].event == "triage.stopped"
    assert state.triage_decide_trace[-1].kind == "stop"


def test_typed_audit_covers_every_selected_attempt():
    state = state_for()
    deps = deps_for(FakeProvider(answer, tick=45))
    run_inner_loop(state, deps, "investigate")

    selected = [e for e in state.triage_trace_events if e.event == "decide.selected"]
    completed = [e for e in state.triage_trace_events if e.event == "tool.completed"]
    validated = [
        e for e in state.triage_trace_events if e.event == "evidence.validated"
    ]
    assert selected and len(selected) == len(completed) == len(validated)
    assert len(selected) == len(state.triage_evidence_checks)
    assert state.triage_trace_events[0].event == "triage.started"
    assert any(e.event == "requirements.compiled" for e in state.triage_trace_events)
    assert all(
        e.request_hash
        and len(e.request_hash) == 20
        and e.attempt >= 1
        and e.candidate_count >= 1
        for e in selected
    )
    assert [e.request_hash for e in selected] == [e.request_hash for e in completed]
    assert all(
        e.accepted == (e.evidence_id is not None) for e in state.triage_evidence_checks
    )


@pytest.mark.parametrize(
    ("tool", "arguments", "row", "expected"),
    [
        (
            "get_events",
            {"machine_id": "CNC-02", "from_tick": 20, "to_tick": 45},
            {"tick": 40, "machine_id": "CNC-03", "kind": "alarm"},
            "wrong_source",
        ),
        (
            "get_events",
            {"machine_id": "CNC-02", "from_tick": 20, "to_tick": 45},
            {"tick": 19, "machine_id": "CNC-02", "kind": "alarm"},
            "outside_window",
        ),
        (
            "get_job_history",
            {"job_id": 10},
            {"tick": 35, "job_id": 11, "machine_id": "CNC-02"},
            "wrong_source",
        ),
        (
            "get_job_history",
            {"job_id": 10},
            {"tick": 46, "job_id": 10, "machine_id": "CNC-02"},
            "future_tick",
        ),
        (
            "get_maintenance_history",
            {"machine_id": "CNC-02"},
            {"tick": 20, "machine_id": "CNC-03", "kind": "service"},
            "wrong_source",
        ),
        (
            "get_inspections",
            {"from_tick": 20, "to_tick": 45},
            {"tick": 43, "job_id": 10, "result": "unknown"},
            "invalid_shape",
        ),
        (
            "get_settings",
            {},
            {"machine_id": "CNC-02"},
            "invalid_shape",
        ),
    ],
)
def test_record_read_cannot_cross_authorized_source_or_time(
    tool, arguments, row, expected
):
    request = ToolRequest(name=tool, arguments=arguments)
    result = ToolResult(
        success=True,
        tool=tool,
        source="fake",
        tick=45,
        timestamp=START,
        data=[row],
    )
    assert validate_triage_result(result, request, 45).reason_code == expected


def test_read_outside_allowed_tool_catalog_cannot_be_qualified():
    request = ToolRequest(
        name="get_readings",
        arguments={
            "machine_id": "CNC-02",
            "sensor": "load",
            "from_tick": 20,
            "to_tick": 45,
        },
    )
    result = ToolResult(
        success=True,
        tool="get_readings",
        source="fake",
        tick=45,
        timestamp=START,
        data=[{"tick": 44, "machine_id": "CNC-02", "sensor": "load", "value": 10}],
    )
    assert validate_triage_result(result, request, 45).reason_code == "unsupported_tool"


def test_result_newer_than_provider_envelope_is_quarantined():
    request = ToolRequest(
        name="get_sensor_summary",
        arguments={
            "machine_id": "CNC-02",
            "sensor": "vibration",
            "from_tick": 20,
            "to_tick": 45,
        },
    )
    data = {**answer(request), "last_tick": 45}
    result = ToolResult(
        success=True,
        tool=request.name,
        source="fake",
        tick=44,
        timestamp=START,
        data=data,
    )
    assert validate_triage_result(result, request, 45).reason_code == "invalid_tick"


def test_failed_provider_attempt_still_has_a_rejected_admission_record():
    state = state_for(max_tool_calls=2)

    def fail(request):
        return "error"

    run_inner_loop(
        state,
        deps_for(
            FakeProvider(fail, tick=45),
            tools=(tool_spec("get_sensor_summary"),),
            channels={"CNC-02": ("vibration",)},
        ),
        "investigate",
    )
    assert len(state.triage_evidence_checks) == state.triage_deterministic_reads
    assert all(not check.accepted for check in state.triage_evidence_checks)
    assert state.evidence == []
    assert state.provenance == []
    assert any(
        e.event == "tool.completed" and e.status == "failed"
        for e in state.triage_trace_events
    )


def test_late_envelope_cannot_rewind_trusted_tick():
    state = state_for()

    def late_summary(request):
        return {**answer(request), "last_tick": 44}

    deps = deps_for(
        FakeProvider(late_summary, tick=44),
        tools=(tool_spec("get_sensor_summary"),),
        channels={"CNC-02": ("vibration",)},
    )
    run_inner_loop(state, deps, "investigate")
    assert state.last_tick == 45
    assert state.evidence == []
    assert state.provenance == []
    assert state.triage_evidence_checks
    assert all(
        not check.accepted and check.reason_code == "out_of_order"
        for check in state.triage_evidence_checks
    )


def test_record_read_rejection_never_reaches_provenance():
    state = state_for()

    def wrong_machine_event(request):
        if request.name == "get_events":
            return [{"tick": 40, "machine_id": "CNC-UNKNOWN", "kind": "alarm"}]
        return answer(request)

    run_inner_loop(
        state, deps_for(FakeProvider(wrong_machine_event, tick=45)), "investigate"
    )
    assert any(
        check.reason_code == "wrong_source" for check in state.triage_evidence_checks
    )
    assert not any(
        evidence.source_id.endswith(":get_events") for evidence in state.evidence
    )
    assert all(
        provenance.evidence_id in {e.id for e in state.evidence}
        for provenance in state.provenance
    )


@pytest.mark.parametrize("step_questions", [1, 2])
def test_same_evidence_and_settings_replay_identical_deterministic_trace(
    step_questions,
):
    state_a, state_b = state_for(), state_for()
    run_inner_loop(
        state_a,
        deps_for(FakeProvider(answer, tick=45), step_questions=step_questions),
        "investigate",
    )
    run_inner_loop(
        state_b,
        deps_for(FakeProvider(answer, tick=45), step_questions=step_questions),
        "investigate",
    )
    assert [x.model_dump() for x in state_a.triage_trace_events] == [
        x.model_dump() for x in state_b.triage_trace_events
    ]
    assert [x.model_dump() for x in state_a.triage_evidence_checks] == [
        x.model_dump() for x in state_b.triage_evidence_checks
    ]


def test_explicit_source_allowlist_rejects_lookalike_provider():
    request = ToolRequest(
        name="get_sensor_summary",
        arguments={
            "machine_id": "CNC-02",
            "sensor": "vibration",
            "from_tick": 20,
            "to_tick": 45,
        },
    )
    result = ToolResult(
        success=True,
        tool=request.name,
        source="untrusted-adapter",
        tick=45,
        timestamp=START,
        data=answer(request),
    )
    checked = validate_triage_result(result, request, 45, allowed_sources=("fake",))
    assert not checked.accepted
    assert checked.reason_code == "wrong_provider"


def test_deterministic_investigate_rejects_wrong_provider_before_commit():
    class UnexpectedSource(FakeProvider):
        def call(self, request, *, run_id=None, investigation_id=None):
            result = super().call(
                request, run_id=run_id, investigation_id=investigation_id
            )
            return result.model_copy(update={"source": "untrusted-adapter"})

    state = state_for()
    deps = deps_for(
        UnexpectedSource(answer, tick=45),
        tools=(tool_spec("get_sensor_summary"),),
        channels={"CNC-02": ("vibration",)},
    )
    run_inner_loop(state, deps, "investigate")
    assert not state.evidence and not state.provenance
    assert state.triage_evidence_checks
    assert all(
        not checked.accepted and checked.reason_code == "wrong_provider"
        for checked in state.triage_evidence_checks
    )


def test_observe_clock_rejects_wrong_provider_before_commit():
    class UnexpectedSource(FakeProvider):
        def call(self, request, *, run_id=None, investigation_id=None):
            result = super().call(
                request, run_id=run_id, investigation_id=investigation_id
            )
            return result.model_copy(update={"source": "untrusted-adapter"})

    state = state_for()
    deps = deps_for(UnexpectedSource(lambda _: {"tick": 45}, tick=45))
    evidence = gather(
        state,
        deps,
        "observe",
        CallTool(
            information_needed="current factory clock",
            request=ToolRequest(name="get_time"),
        ),
        interpret=False,
    )
    assert evidence is None
    assert not state.evidence and not state.provenance
    assert state.last_tick == 45
    assert state.triage_evidence_checks[-1].reason_code == "wrong_provider"
    assert state.triage_trace_events[-1].event == "observe.read_validated"
    assert state.triage_trace_events[-1].phase == "observe"


@pytest.mark.parametrize(
    ("tool", "payload"),
    [
        ("get_time", {"tick": 44}),
        ("get_line_screening", {"machines": "invalid"}),
        ("list_machines", [{"machine_id": None, "status": "running"}]),
    ],
)
def test_observe_admission_quarantines_invalid_structures(tool, payload):
    state = state_for()
    deps = deps_for(FakeProvider(lambda _: payload, tick=45))
    evidence = gather(
        state,
        deps,
        "observe",
        CallTool(
            information_needed="validate source observation",
            request=ToolRequest(name=tool),
        ),
        interpret=False,
    )
    assert evidence is None
    assert not state.evidence and not state.provenance
    assert state.last_tick == 45
    assert state.triage_evidence_checks[-1].accepted is False
    assert state.triage_trace_events[-1].status == "rejected"


def test_deterministic_test_phase_uses_same_source_boundary():
    class UnexpectedSource(FakeProvider):
        def call(self, request, *, run_id=None, investigation_id=None):
            result = super().call(
                request, run_id=run_id, investigation_id=investigation_id
            )
            return result.model_copy(update={"source": "untrusted-adapter"})

    state = state_for()
    deps = deps_for(
        UnexpectedSource(answer, tick=45),
        tools=(tool_spec("get_sensor_summary"),),
        channels={"CNC-02": ("vibration",)},
    )
    run_inner_loop(state, deps, "test")
    assert not state.evidence and not state.provenance
    assert state.triage_evidence_checks
    assert all(x.reason_code == "wrong_provider" for x in state.triage_evidence_checks)
    assert any(
        x.event == "triage.evidence_rejected" and x.phase == "test"
        for x in state.triage_trace_events
    )


def test_incomplete_historical_rows_fail_full_contract():
    cases = (
        (
            "get_events",
            {"machine_id": "CNC-02", "from_tick": 20, "to_tick": 45},
            {"tick": 30, "machine_id": "CNC-02"},
        ),
        (
            "get_job_history",
            {"job_id": 10},
            {"tick": 30, "job_id": 10, "machine_id": "CNC-02"},
        ),
        (
            "get_maintenance_history",
            {"machine_id": "CNC-02"},
            {"tick": None, "machine_id": "CNC-02"},
        ),
    )
    for name, arguments, row in cases:
        request = ToolRequest(name=name, arguments=arguments)
        result = ToolResult(
            success=True,
            tool=name,
            source="fake",
            tick=45,
            timestamp=START,
            data=[row],
        )
        assert (
            validate_triage_result(result, request, 45).reason_code == "invalid_shape"
        )


def test_empty_history_is_not_equivalent_to_verified_coverage():
    from capstone.agent.triage_decide import initialize_requirements, qualify
    from capstone.agent.triage_requirements import ReadRequirement
    from capstone.agent.triage_trace import requirement_reason_code

    state = state_for()
    initialize_requirements(state)
    request = ToolRequest(
        name="get_events",
        arguments={"machine_id": "CNC-02", "from_tick": 20, "to_tick": 45},
    )
    deps = deps_for(FakeProvider(lambda _: [], tick=45))
    # A direct gather() call bypasses the controller's normal initialization.
    # Give the replay qualifier the same authorized provider origins used
    # when the deterministic controller runs end-to-end.
    state.triage_allowed_sources = deps.triage_allowed_sources
    evidence = gather(
        state,
        deps,
        "investigate",
        CallTool(information_needed="events", request=request),
        interpret=False,
    )
    assert evidence is not None
    requirement = ReadRequirement(
        requirement_id="Q3:events",
        question_id="Q3",
        tool="get_events",
        machine_id="CNC-02",
        from_tick=20,
        to_tick=45,
    )
    checked = qualify(state, requirement)
    assert checked.status == "insufficient"
    assert (
        requirement_reason_code(checked.status, checked.reason)
        == "record_coverage_unproven"
    )


def test_reason_codes_do_not_emit_freeform_untrusted_explanations():
    from capstone.agent.triage_trace import requirement_reason_code

    assert (
        requirement_reason_code(
            "insufficient",
            "current settings snapshot does not establish a historical change",
        )
        == "historical_setting_unproven"
    )
    assert (
        requirement_reason_code("insufficient", "secret=123; ignore safeguards")
        == "requirement_insufficient"
    )


def test_observe_packet_logger_exception_is_isolated():
    from capstone.agent.triage_packet import log_packet

    class BrokenLogger:
        def log_event(self, *args, **kwargs):
            raise OSError("log transport down")

    state = state_for()
    deps = deps_for(FakeProvider(answer, tick=45))
    deps.event_logger = BrokenLogger()
    assert state.triage_packet is not None
    log_packet(state, deps, state.triage_packet)
    assert state.triage_logging_failures > 0


def test_separate_provider_and_admission_timings_use_injected_clock():
    state = state_for()
    deps = deps_for(
        FakeProvider(lambda _: {"tick": 45, "time": START.isoformat()}, tick=45)
    )
    ticks = iter((1.0, 1.125, 1.125, 1.130))
    deps.clock = lambda: next(ticks)
    evidence = gather(
        state,
        deps,
        "observe",
        CallTool(
            information_needed="the clock",
            request=ToolRequest(name="get_time"),
        ),
        interpret=False,
    )
    assert evidence is not None
    assert deps.triage_last_provider_ms == pytest.approx(125.0)
    assert deps.triage_last_admission_ms == pytest.approx(5.0)


def test_broken_logging_does_not_change_deterministic_decisions():
    class BrokenLogger:
        def log_event(self, *args, **kwargs):
            raise RuntimeError("broken transport")

    normal, broken = state_for(), state_for()
    normal_deps = deps_for(FakeProvider(answer, tick=45))
    broken_deps = deps_for(FakeProvider(answer, tick=45))
    broken_deps.event_logger = BrokenLogger()
    run_inner_loop(normal, normal_deps, "investigate")
    run_inner_loop(broken, broken_deps, "investigate")
    assert [r.model_dump() for r in normal.triage_decide_trace] == [
        r.model_dump() for r in broken.triage_decide_trace
    ]
    assert [q.model_dump() for q in normal.triage_evidence_checks] == [
        q.model_dump() for q in broken.triage_evidence_checks
    ]
    assert normal.triage_logging_failures == 0
    assert broken.triage_logging_failures > 0


def test_deep_observe_does_not_enable_deterministic_guard():
    state = state_for(mode="deep")
    deps = deps_for(FakeProvider(lambda _: {"tick": 44}, tick=45))
    evidence = gather(
        state,
        deps,
        "observe",
        CallTool(
            information_needed="the legacy clock read",
            request=ToolRequest(name="get_time"),
        ),
        interpret=False,
    )
    # Deep mode deliberately retains the old gather admission behavior.
    assert evidence is not None
    assert not state.triage_evidence_checks
    assert not state.triage_trace_events


def test_rejected_factory_clock_blocks_entire_deterministic_read_path():
    from capstone.agent.artifacts import TerminationReason

    state = state_for()
    provider = FakeProvider(
        lambda request: (
            {"tick": 44, "time": START.isoformat()}
            if request.name == "get_time"
            else answer(request)
        ),
        tick=45,
    )
    deps = deps_for(provider)
    evidence = gather(
        state,
        deps,
        "observe",
        CallTool(
            information_needed="the trusted factory clock",
            request=ToolRequest(name="get_time"),
        ),
        interpret=False,
    )
    assert evidence is None
    assert state.triage_clock_verified is False
    assert state.triage_evidence_checks[-1].reason_code == "invalid_tick"
    read_count = len(provider.calls)

    reason = run_inner_loop(state, deps, "investigate")
    assert reason is TerminationReason.NO_USEFUL_ACTION
    assert len(provider.calls) == read_count
    assert not state.evidence and not state.provenance
    assert state.triage_decide_trace[-1].reason == "data_insufficient"
    assert state.triage_trace_events[-1].event == "triage.stopped"
    assert state.triage_trace_events[-1].requirement_ids


def test_accepted_factory_clock_allows_authorized_deterministic_reads():
    state = state_for()
    provider = FakeProvider(
        lambda request: (
            {"tick": 45, "time": START.isoformat()}
            if request.name == "get_time"
            else answer(request)
        ),
        tick=45,
    )
    deps = deps_for(provider)
    evidence = gather(
        state,
        deps,
        "observe",
        CallTool(
            information_needed="trusted time",
            request=ToolRequest(name="get_time"),
        ),
        interpret=False,
    )
    assert evidence is not None
    assert state.triage_clock_verified is True

    run_inner_loop(state, deps, "investigate")
    assert len(provider.calls) > 1
    assert state.triage_deterministic_reads > 0


def test_empty_source_allowlist_denies_deterministic_reads():
    state = state_for()
    provider = FakeProvider(answer, tick=45)
    deps = deps_for(provider)
    deps.triage_allowed_sources = ()
    with pytest.raises(ValueError, match="authorized provider sources"):
        run_inner_loop(state, deps, "investigate")
    assert not provider.calls


def test_empty_source_allowlist_rejects_observe_time():
    state = state_for()
    deps = deps_for(
        FakeProvider(lambda _: {"tick": 45, "time": START.isoformat()}, tick=45)
    )
    deps.triage_allowed_sources = ()
    evidence = gather(
        state,
        deps,
        "observe",
        CallTool(
            information_needed="factory time",
            request=ToolRequest(name="get_time"),
        ),
        interpret=False,
    )
    assert evidence is None
    assert state.triage_clock_verified is False
    assert state.triage_evidence_checks[-1].reason_code == "wrong_provider"


def test_failed_optional_sensor_read_always_has_a_typed_rejection():
    state = state_for()
    state.started_at = 0.0
    deps = deps_for(FakeProvider(lambda _: "error", tick=45))
    call, evidence = optional_call(
        state,
        deps,
        "get_sensor_summary",
        {
            "machine_id": "CNC-02",
            "sensor": "vibration",
            "from_tick": 20,
            "to_tick": 45,
        },
        "optional alarm window",
        6,
    )
    assert evidence is None
    assert call.outcome == "failed"
    assert state.triage_evidence_checks[-1].reason_code == "provider_error"
    assert state.triage_evidence_checks[-1].evidence_id is None
    assert state.triage_trace_events[-1].event == "observe.read_validated"
    assert state.triage_trace_events[-1].status == "rejected"
    assert not state.evidence and not state.provenance


def test_repeated_optional_sensor_read_has_typed_rejection_without_recalling():
    state = state_for()
    state.started_at = 0.0
    provider = FakeProvider(answer, tick=45)
    deps = deps_for(provider)
    args = {
        "machine_id": "CNC-02",
        "sensor": "vibration",
        "from_tick": 20,
        "to_tick": 45,
    }
    _, initial = optional_call(
        state, deps, "get_sensor_summary", args, "initial window", 6
    )
    assert initial is not None
    before = len(provider.calls)
    _, second = optional_call(
        state, deps, "get_sensor_summary", args, "repeat window", 6
    )
    assert second is None
    assert len(provider.calls) == before
    assert state.triage_evidence_checks[-1].reason_code == "repeated_call"
    assert state.triage_trace_events[-1].reason_code == "repeated_call"


def test_config_fingerprint_changes_when_authorized_sources_change():
    a, b = state_for(), state_for()
    allowed = deps_for(FakeProvider(answer, tick=45))
    expanded = deps_for(FakeProvider(answer, tick=45))
    expanded.triage_allowed_sources = ("fake", "simulator")
    run_inner_loop(a, allowed, "investigate")
    run_inner_loop(b, expanded, "investigate")
    fingerprint_a = next(
        event.config_fingerprint
        for event in a.triage_trace_events
        if event.event == "triage.started"
    )
    fingerprint_b = next(
        event.config_fingerprint
        for event in b.triage_trace_events
        if event.event == "triage.started"
    )
    assert fingerprint_a is not None
    assert fingerprint_b is not None
    assert fingerprint_a != fingerprint_b


@pytest.mark.parametrize("then_deep", [False, True])
def test_deterministic_boundary_survives_a_full_episode(monkeypatch, then_deep):
    """Use the real simulator and Pydantic Graph, not just controller stubs."""
    from capstone.agent.artifacts import AgentConclusion
    from capstone.episode import run_episode
    from tests.helpers import ScriptedPolicy
    from tests.test_episode import SEED, wear_policy
    from tests.test_triage import ByMode

    class GuardedTriage(ScriptedPolicy):
        def plan(self, state):
            raise AssertionError("fixed triage plan must not invoke the model")

        def decide(self, state, phase):
            raise AssertionError("deterministic Decide must not invoke the model")

        def interpret(self, state, step, evidence):
            raise AssertionError("deterministic Interpret must not invoke the model")

    monkeypatch.setenv("TRIAGE", "on")
    # Exercise the production default, not explicit deterministic overrides.
    monkeypatch.delenv("TRIAGE_PLAN", raising=False)
    monkeypatch.delenv("TRIAGE_INVESTIGATE", raising=False)
    monkeypatch.setenv("TRIAGE_PACKET", "on")
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "on" if then_deep else "off")
    triage_policy = GuardedTriage(
        conclude=lambda _state: (
            AgentConclusion(
                diagnosis="further inspection required",
                confidence=0.2,
                recommendation="escalate",
                assessment="unresolved",
            ),
            None,
        )
    )
    policy = ByMode(triage_policy, wear_policy())
    result = run_episode(
        SEED,
        policy,
        fault="bearing_degradation",
        clock=lambda: 0.0,
        triage=True,
    )
    triage = result.triage
    assert triage is not None
    assert triage.mode == "triage"
    assert triage.triage_clock_verified is True
    assert triage.triage_packet is not None
    assert triage.fixed_plan_used
    assert triage.triage_deterministic_reads > 0
    assert any(check.accepted for check in triage.triage_evidence_checks)
    events = [event.event for event in triage.triage_trace_events]
    assert "observe.read_validated" in events
    assert "requirements.compiled" in events
    assert "triage.stopped" in events
    assert "conclusion.checked" in events
    assert [event.sequence for event in triage.triage_trace_events] == list(
        range(1, len(events) + 1)
    )
    assert triage.policy_recommendation == "escalate"
    assert triage.deep_recommended is True
    assert triage.proposed_action is None
    assert triage.verification is None
    assert set(triage_policy.asked) <= {"hypothesize", "conclude"}

    if then_deep:
        assert result.state is not triage
        assert result.state.mode == "deep"
        assert result.state.follows_triage == triage.investigation_id
        assert not result.state.triage_trace_events
        assert result.state.conclusion is not None
    else:
        assert result.state is triage


def test_rejected_clock_skips_optional_packet_reads_even_with_cached_tick():
    state = state_for()
    state.triage_clock_verified = False
    provider = FakeProvider(answer, tick=45)
    deps = deps_for(provider)
    call, evidence = optional_call(
        state,
        deps,
        "get_sensor_summary",
        {
            "machine_id": "CNC-02",
            "sensor": "vibration",
            "from_tick": 20,
            "to_tick": 45,
        },
        "optional sensor window",
        6,
    )
    assert call.outcome == "skipped_unavailable"
    assert call.reason == "observation_cutoff_untrusted"
    assert evidence is None
    assert provider.calls == []
    assert state.triage_evidence_checks == []
