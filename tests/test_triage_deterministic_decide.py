"""The opt-in triage controller collects evidence without Decide model calls."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from capstone.agent.artifacts import DetectedAnomaly, TerminationReason
from capstone.agent.evidence_packet import EvidencePacket
from capstone.agent.loop import InvestigationDeps, run_inner_loop
from capstone.agent.state import Question
from capstone.agent.triage_plan import fixed_plan, fixed_predicates
from capstone.contracts.tools import ToolError, ToolResult
from capstone.providers.factory import tool_spec
from capstone.settings import Settings
from tests.helpers import START, FakeProvider, ScriptedPolicy, new_state

ALARM = DetectedAnomaly(
    tick=40,
    machine_id="CNC-02",
    kind="alarm",
    description="alarm on CNC-02: vibration 9.99 u above 4.50",
)
TOOLS = tuple(
    tool_spec(name)
    for name in (
        "get_sensor_summary",
        "get_events",
        "get_maintenance_history",
        "get_settings",
    )
)
CHANNELS = {"CNC-02": ("vibration", "temperature", "load")}


class NoDecideModel(ScriptedPolicy):
    """A policy that fails the test if triage Decide or Interpret asks it."""

    def decide(self, state, phase):
        raise AssertionError("model Decide was called")

    def interpret(self, state, step, evidence):
        raise AssertionError("model Interpret was called")

    def interpret_and_decide(self, state, phase, step, evidence):
        raise AssertionError("model combined Decide was called")

    def interpret_and_decide_many(self, state, phase, pairs):
        raise AssertionError("model batched Decide was called")


def state_for(*, max_tool_calls=12, max_iterations=24, mode="triage"):
    """One fixed-plan alarm after Observe, with a stable cutoff at tick 45."""
    state = new_state(max_tool_calls=max_tool_calls, max_iterations=max_iterations)
    state.anomaly = ALARM
    state.mode = mode
    state.last_tick = 45
    state.triage_packet = EvidencePacket(
        machine_id="CNC-02",
        trigger_tick=40,
        observation_tick=45,
        roster=("CNC-02",),
        roster_verified=True,
    )
    state.unanswered_questions = list(fixed_plan(ALARM))
    state.question_predicates.update(fixed_predicates(ALARM))
    state.fixed_plan_used = True
    return state


def answer(request):
    """Return enough finite sensor data, but only a current settings snapshot."""
    if request.name == "get_sensor_summary":
        return {
            **request.arguments,
            "sample_count": 12,
            "first_tick": max(20, request.arguments["from_tick"]),
            "last_tick": request.arguments["to_tick"],
            "mean": 4.6,
            "delta": 0.2,
        }
    if request.name == "get_settings":
        return [{"machine_id": "CNC-02", "speed_rpm": 1000}]
    return []


def deps_for(provider, *, step_questions=1, tools=TOOLS, channels=CHANNELS):
    """Give the controller an explicit read-only catalog and a tripwire policy."""
    return InvestigationDeps(
        provider=provider,
        policy=NoDecideModel(),
        clock=lambda: 0.0,
        triage_investigate="deterministic",
        triage_tool_specs=tools,
        triage_channels=channels,
        step_questions=step_questions,
    )


@pytest.mark.parametrize("step_questions", [1, 2])
def test_no_decide_or_interpret_model_call_even_on_final_read(step_questions):
    state = state_for()
    provider = FakeProvider(answer, tick=45)
    reason = run_inner_loop(
        state, deps_for(provider, step_questions=step_questions), "investigate"
    )
    assert reason is TerminationReason.NO_USEFUL_ACTION
    assert state.triage_decide_trace[-1].reason == "data_insufficient"
    assert state.triage_deterministic_reads == len(provider.calls)
    assert "Q5" not in {q.id for q in state.unanswered_questions}
    assert "Q4" in {q.id for q in state.unanswered_questions}


def test_shared_sensor_read_supports_two_requirements_once():
    state = state_for()
    provider = FakeProvider(answer, tick=45)
    run_inner_loop(state, deps_for(provider), "investigate")
    vibration = [
        r
        for r in provider.calls
        if r.name == "get_sensor_summary" and r.arguments["sensor"] == "vibration"
    ]
    assert len(vibration) == 1
    assert state.triage_requirement_results["Q1:trigger"].status == "satisfied"
    assert state.triage_requirement_results["Q5:vibration"].status == "satisfied"
    assert set(state.triage_requirement_results["Q1:trigger"].evidence_ids) & set(
        state.triage_requirement_results["Q5:vibration"].evidence_ids
    )


def test_temperature_without_load_keeps_q5_open():
    state = state_for()
    provider = FakeProvider(answer, tick=45)
    run_inner_loop(
        state,
        deps_for(provider, channels={"CNC-02": ("vibration", "temperature")}),
        "investigate",
    )
    assert state.triage_requirement_results["Q5:temperature"].status == "satisfied"
    assert state.triage_requirement_results["Q5:load"].status != "satisfied"
    assert "Q5" in {q.id for q in state.unanswered_questions}
    assert not any(r.arguments.get("sensor") == "load" for r in provider.calls)


def test_failed_jobs_require_job_paths_and_reuse_inspections():
    anomaly = DetectedAnomaly(
        tick=40, kind="inspection_failures", description="3 parts failed"
    )
    state = new_state(max_tool_calls=8)
    state.anomaly = anomaly
    state.mode = "triage"
    state.last_tick = 45
    state.unanswered_questions = list(fixed_plan(anomaly))
    state.fixed_plan_used = True

    def records(request):
        if request.name == "get_inspections":
            return [
                {"tick": 41, "job_id": 10, "batch_id": "B1", "result": "failed"},
                {"tick": 42, "job_id": 11, "batch_id": "B1", "result": "failed"},
            ]
        if request.name == "get_job_history":
            return [{"tick": 30, "job_id": request.arguments["job_id"],
                     "machine_id": "CNC-02", "kind": "job_started"}]
        if request.name == "get_settings":
            return [{"machine_id": "CNC-02", "speed_rpm": 1000}]
        return []

    provider = FakeProvider(records, tick=45)
    tools = tuple(tool_spec(name) for name in (
        "get_inspections", "get_job_history", "get_settings", "get_events"
    ))
    run_inner_loop(state, deps_for(provider, tools=tools), "investigate")
    assert sum(call.name == "get_inspections" for call in provider.calls) == 1
    assert sorted(call.arguments["job_id"] for call in provider.calls
                  if call.name == "get_job_history") == [10, 11]
    assert {"Q1", "Q2"} <= set(state.answers)
    assert state.answers["Q1"] == state.triage_question_evidence["Q1"]


def test_current_settings_snapshot_does_not_prove_a_change():
    state = state_for()
    run_inner_loop(state, deps_for(FakeProvider(answer, tick=45)), "investigate")
    assert (
        state.triage_requirement_results["Q4:setting_change"].status == "insufficient"
    )
    assert "Q4" in {q.id for q in state.unanswered_questions}


def test_transient_error_gets_one_real_retry():
    state = state_for()
    attempts = 0

    def transient(request):
        nonlocal attempts
        if (
            request.name == "get_sensor_summary"
            and request.arguments["sensor"] == "vibration"
        ):
            attempts += 1
            if attempts == 1:
                return "error"
        return answer(request)

    provider = FakeProvider(transient, tick=45)
    run_inner_loop(state, deps_for(provider), "investigate")
    assert attempts == 2
    assert state.triage_requirement_results["Q1:trigger"].status == "satisfied"


def test_permanent_tool_refusal_is_not_retried():
    state = state_for()

    class RefusingProvider(FakeProvider):
        def call(self, request, *, run_id=None, investigation_id=None):
            if request.name != "get_sensor_summary":
                return super().call(
                    request, run_id=run_id, investigation_id=investigation_id
                )
            self.calls.append(request)
            return ToolResult(
                success=False,
                tool=request.name,
                source="fake",
                tick=45,
                timestamp=START + timedelta(minutes=45),
                run_id=run_id,
                investigation_id=investigation_id,
                error=ToolError(
                    code="invalid_arguments", message="unsupported channel"
                ),
            )

    provider = RefusingProvider(answer, tick=45)
    run_inner_loop(state, deps_for(provider), "investigate")
    assert sum(r.arguments.get("sensor") == "vibration" for r in provider.calls) == 2
    # Q1 and Q5 request different windows. Neither exact request was retried.
    assert all(count == 1 for count in state.triage_read_attempts.values())


def test_empty_catalog_fails_before_a_provider_call():
    provider = FakeProvider(answer, tick=45)
    with pytest.raises(ValueError, match="authorized tool catalog"):
        run_inner_loop(state_for(), deps_for(provider, tools=()), "investigate")
    assert provider.calls == []


def test_older_response_does_not_move_authorized_cutoff():
    state = state_for()
    provider = FakeProvider(answer, tick=43)
    run_inner_loop(state, deps_for(provider), "investigate")
    assert state.triage_observation_cutoff_tick == 45
    assert all(r.arguments.get("to_tick", 45) <= 45 for r in provider.calls)


def test_tool_budget_stops_with_the_actual_reason():
    state = state_for(max_tool_calls=1)
    provider = FakeProvider(answer, tick=45)
    reason = run_inner_loop(state, deps_for(provider), "investigate")
    assert reason is TerminationReason.MAX_TOOL_CALLS
    assert len(provider.calls) == 1
    assert state.triage_decide_trace[-1].reason == "max_tool_calls"


def test_no_candidate_stops_without_a_model_fallback():
    state = state_for()
    provider = FakeProvider(answer, tick=45)
    deps = deps_for(provider)
    run_inner_loop(state, deps, "investigate")
    state.triage_requirements.pop("Q4:setting_change")
    state.unanswered_questions = [q for q in state.unanswered_questions if q.id == "Q2"]
    before = len(provider.calls)
    reason = run_inner_loop(state, deps, "investigate")
    assert reason is TerminationReason.NO_USEFUL_ACTION
    assert state.triage_decide_trace[-1].reason == "no_eligible_read"
    assert len(provider.calls) == before


def test_test_phase_does_not_stall_on_unchanged_confidence():
    state = state_for(max_tool_calls=14)
    provider = FakeProvider(answer, tick=45)
    channels = {
        "CNC-02": CHANNELS["CNC-02"]
        + ("power", "following_error", "hydraulic_pressure")
    }
    deps = deps_for(provider, channels=channels)
    run_inner_loop(state, deps, "investigate")
    state.unanswered_questions = [
        Question(id="Q6", text="Check CNC-02 power"),
        Question(id="Q7", text="Check CNC-02 following error"),
        Question(id="Q8", text="Check CNC-02 hydraulic pressure"),
    ]
    before = len(provider.calls)
    run_inner_loop(state, deps, "test")
    assert len(provider.calls) - before == 3
    assert state.triage_decide_trace[-1].reason != "max_iterations"
    assert {"Q6", "Q7", "Q8"} <= set(state.answers)


def test_insufficient_samples_keep_trigger_open_without_same_read_loop():
    state = state_for()

    def sparse(request):
        data = answer(request)
        if request.name == "get_sensor_summary":
            data.update(sample_count=1, first_tick=45, last_tick=45)
        return data

    provider = FakeProvider(sparse, tick=45)
    run_inner_loop(state, deps_for(provider), "investigate")
    assert state.triage_requirement_results["Q1:trigger"].status == "insufficient"
    assert "Q1" in {q.id for q in state.unanswered_questions}
    assert all(count == 1 for count in state.triage_read_attempts.values())


def test_unavailable_sensor_is_never_sent_to_replay_provider():
    state = state_for()
    provider = FakeProvider(answer, tick=45)
    deps = deps_for(provider, tools=(tool_spec("get_sensor_summary"),), channels={})
    run_inner_loop(state, deps, "investigate")
    assert provider.calls == []
    assert state.triage_decide_trace[-1].reason == "capability_unavailable"


def test_future_response_is_quarantined_without_moving_the_cutoff():
    state = state_for()
    provider = FakeProvider(answer, tick=46)
    run_inner_loop(
        state,
        deps_for(
            provider,
            tools=(tool_spec("get_sensor_summary"),),
            channels={"CNC-02": ("vibration",)},
        ),
        "investigate",
    )
    assert state.evidence == []
    assert state.provenance == []
    assert state.triage_observation_cutoff_tick == 45
    assert state.triage_decide_trace[0].outcome == "invalid_result"


def test_identical_inputs_choose_the_same_reads_and_stop():
    def once():
        state = state_for()
        run_inner_loop(state, deps_for(FakeProvider(answer, tick=45)), "investigate")
        return [record.model_dump() for record in state.triage_decide_trace]

    assert once() == once()


def test_invalid_plan_setting_is_rejected():
    with pytest.raises(ValidationError, match="requires TRIAGE_PLAN=fixed"):
        Settings(
            _env_file=None, TRIAGE_INVESTIGATE="deterministic", TRIAGE_PLAN="model"
        )
    settings = Settings(
        _env_file=None, TRIAGE_INVESTIGATE="deterministic", TRIAGE_PLAN="fixed"
    )
    assert settings.triage_investigate == "deterministic"
