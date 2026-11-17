"""Opt-in deterministic Hypothesize/Test uses observable, unscored candidates."""

import json
from dataclasses import replace
from io import StringIO

import pytest

from capstone.agent.artifacts import AgentConclusion
from capstone.agent.investigation import (
    check_conclusion,
    hypothesize,
    investigate,
)
from capstone.agent.investigation import (
    test as run_test,
)
from capstone.agent.model_policy import render
from capstone.agent.triage_hypothesize import (
    TriageHypothesisPacket,
    compile_candidates,
    update_candidate_packet,
)
from capstone.observability import create_event_logger
from capstone.settings import Settings
from tests.helpers import FakeProvider, ScriptedPolicy
from tests.test_triage_deterministic_decide import (
    NoDecideModel,
    answer,
    deps_for,
    state_for,
)


def case(*, policy=None, event_logger=None):
    """One fully isolated triage using the existing typed read-only tools."""
    state = state_for()
    provider = FakeProvider(answer, tick=45)
    # ScriptedPolicy has no one-question combined Decide method; use the
    # supported two-question contract when testing deep-mode isolation.
    questions = (
        2
        if policy is not None
        and not callable(getattr(policy, "interpret_and_decide", None))
        else 1
    )
    deps = replace(
        deps_for(provider, step_questions=questions),
        policy=policy or NoDecideModel(),
        triage_hypothesize="deterministic",
        event_logger=event_logger,
    )
    return state, deps, provider


def test_direct_invalid_hypothesis_and_test_avoid_model_fallback():
    from capstone.agent.artifacts import TerminationReason

    state, deps, provider = case()
    deps.triage_investigate = "off"
    assert hypothesize(state, deps) == "conclude"
    assert not state.triage_candidates
    run_test(state, deps)
    assert state.termination_reason is TerminationReason.NO_USEFUL_ACTION
    assert not deps.policy.asked
    assert not provider.calls


def test_safe_hypothesis_summary_omits_source_text_and_confidence():
    from capstone.api.runs import safe_hypothesis_progress

    state, deps, _ = case()
    investigate(state, deps)
    hypothesize(state, deps)
    public = safe_hypothesis_progress(state)
    assert public["rule_version"] == "1.1"
    assert public["candidate_count"] == len(state.triage_candidates)
    assert all(c["status"] == "unconfirmed" for c in public["candidates"])
    assert "explanation" not in str(public)
    assert "confidence" not in str(public)
    assert "machine_id" not in str(public)


def test_deterministic_hypothesize_is_default_for_guarded_triage():
    cfg = Settings(_env_file=None)
    assert cfg.triage_hypothesize == "deterministic"
    assert cfg.triage_plan == "fixed"
    assert cfg.triage_investigate == "deterministic"
    legacy = Settings(_env_file=None, triage_hypothesize="model")
    assert legacy.triage_hypothesize == "model"


def test_hypothesis_packet_rejects_duplicate_candidates_and_unsafe_reads():
    from pydantic import ValidationError

    state, deps, _ = case()
    investigate(state, deps)
    hypothesize(state, deps)
    candidates = tuple(state.triage_candidates)
    assert candidates
    with pytest.raises(ValidationError):
        TriageHypothesisPacket(candidates=(candidates[0], candidates[0]))
    with pytest.raises(ValidationError):
        TriageHypothesisPacket(
            candidates=candidates,
            test_requirement_ids=("Q99:unobserved",),
        )
    with pytest.raises(ValidationError):
        type(candidates[0]).model_validate(
            {**candidates[0].model_dump(), "family": "untrusted_fault_label"}
        )


def test_candidate_compiler_is_unscored_and_repeatable():
    state, deps, _ = case()
    assert investigate(state, deps) == "continue"
    assert hypothesize(state, deps) == "continue"
    before = compile_candidates(state)
    assert before == compile_candidates(state)
    assert [c.id for c in state.triage_candidates] == ["TC1", "TC2", "TC3"]
    assert all(c.status == "unconfirmed" for c in state.triage_candidates)
    assert all(not hasattr(c, "confidence") for c in state.triage_candidates)
    assert "Q5:temperature" in state.triage_test_requirement_ids
    assert state.triage_hypothesis_trace[-1].action == "compiled"


def test_model_hypothesize_is_never_called_and_test_reads_are_compiled():
    policy = NoDecideModel()
    state, deps, provider = case(policy=policy)
    assert investigate(state, deps) == "continue"
    assert hypothesize(state, deps) == "continue"
    assert "hypothesize" not in policy.asked
    initial_calls = len(provider.calls)
    run_test(state, deps)
    assert len(provider.calls) > initial_calls
    assert "hypothesize" not in policy.asked
    assert "Q5:temperature" in state.triage_test_requirement_ids
    assert state.triage_hypothesis_trace[-1].action == "refreshed"
    assert all(call.name != "get_settings" for call in provider.calls)


def test_model_revalue_is_not_invoked_after_deterministic_test():
    class RevalueSpy(NoDecideModel):
        options = type("Options", (), {"revalue": True})()

        def revalue(self, state):
            raise AssertionError("model revaluation must not run")

    state, deps, _ = case(policy=RevalueSpy())
    assert investigate(state, deps) == "continue"
    assert hypothesize(state, deps) == "continue"
    run_test(state, deps)


def test_test_packet_reflects_new_evidence_without_causal_claims():
    state, deps, _ = case()
    investigate(state, deps)
    hypothesize(state, deps)
    before = state.triage_candidates[1].observation_evidence_ids
    run_test(state, deps)
    after = state.triage_candidates[1].observation_evidence_ids
    assert set(before) <= set(after)
    assert len(after) >= len(before)
    assert state.triage_candidates[1].status == "unconfirmed"
    assert "Q5" in {q.id for q in state.unanswered_questions}
    assert "UNSCORED TRIAGE CANDIDATES" in render(state)


def test_existing_candidate_ids_are_allowed_but_not_fake_hypotheses():
    state, deps, _ = case()
    investigate(state, deps)
    hypothesize(state, deps)
    assert not state.hypotheses
    eid = state.triage_candidates[0].observation_evidence_ids[0]
    raw = AgentConclusion(
        diagnosis="unresolved machinery condition",
        confidence=0.4,
        recommendation="escalate",
        assessment="unresolved",
        hypothesis_id="TC1",
        evidence_ids=(eid,),
    )
    checked, request = check_conclusion(state, deps, raw, None)
    assert request is None
    assert checked.hypothesis_id == "TC1"
    assert checked.assessment == "unresolved"
    with pytest.raises(ValueError, match="never formed"):
        check_conclusion(
            state, deps, raw.model_copy(update={"hypothesis_id": "TC999"}), None
        )


def test_no_action_still_requires_scored_hypotheses_and_clearance():
    state, deps, _ = case()
    investigate(state, deps)
    hypothesize(state, deps)
    eid = state.triage_candidates[0].observation_evidence_ids[0]
    answer = AgentConclusion(
        diagnosis="nothing wrong",
        confidence=0.99,
        recommendation="no_action",
        assessment="supported",
        hypothesis_id="TC1",
        evidence_ids=(eid,),
    )
    checked, _ = check_conclusion(state, deps, answer, None)
    assert checked.recommendation == "escalate"
    assert checked.assessment == "unresolved"
    assert any(g.kind == "triage_no_hypothesis" for g in state.conclusion_trace.gaps)


def test_deep_mode_still_uses_original_model_hypothesize():
    state, deps, _ = case(policy=ScriptedPolicy())
    state.mode = "deep"
    assert hypothesize(state, deps) == "conclude"
    assert deps.policy.asked == ["hypothesize"]
    assert state.triage_candidates == []


def test_observability_logs_safe_metadata_and_persists_reason_trace():
    stream = StringIO()
    state, deps, _ = case(event_logger=create_event_logger(stream))
    investigate(state, deps)
    hypothesize(state, deps)
    run_test(state, deps)
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    names = {row["event"] for row in rows}
    assert {
        "triage.hypothesize.compiled",
        "triage.read.selected",
        "triage.test.completed",
    } <= names
    assert all(row["run_id"] == str(state.run_id) for row in rows)
    # PR #284 also emits lower-level evidence admission/decision events,
    # whose schema intentionally has no legacy aggregate counts.
    hypothesis_events = [
        row
        for row in rows
        if row["event"]
        in {
            "triage.hypothesize.compiled",
            "triage.read.selected",
            "triage.read.result",
            "triage.test.completed",
        }
    ]
    assert all("counts" in row for row in hypothesis_events)
    assert any("sequence" in row for row in rows)
    assert (
        next(row for row in rows if row["event"] == "triage.test.completed")["success"]
        is False
    )
    assert "4.50" not in stream.getvalue()
    assert '"content"' not in stream.getvalue()
    assert state.triage_hypothesis_trace[0].candidate_ids == ("TC1", "TC2", "TC3")
    assert state.triage_hypothesis_trace[-1].stage == "test"


def test_failed_read_has_diagnostic_result_event_without_exception_text():
    stream = StringIO()
    state = state_for()
    provider = FakeProvider(lambda request: "error", tick=45)
    deps = replace(
        deps_for(provider),
        triage_hypothesize="deterministic",
        event_logger=create_event_logger(stream),
    )
    investigate(state, deps)
    hypothesize(state, deps)
    run_test(state, deps)
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    failed = [row for row in rows if row["event"] == "triage.read.result"]
    assert failed and all(row["success"] is False for row in failed)
    assert all(row["counts"]["failed_response"] == 1 for row in failed)
    assert "Tool execution failed" not in stream.getvalue()
    assert state.triage_decide_trace


def test_old_serialized_records_have_empty_candidate_defaults():
    state = state_for()
    payload = state.model_dump()
    payload.pop("triage_candidates")
    payload.pop("triage_test_requirement_ids")
    payload.pop("triage_hypothesis_trace")
    reconstructed = type(state).model_validate(payload)
    assert reconstructed.triage_candidates == []
    assert reconstructed.triage_test_requirement_ids == ()
    assert reconstructed.triage_hypothesis_trace == []


def test_settings_reject_unsafe_hypothesize_combination():
    with pytest.raises(ValueError, match="requires"):
        Settings(
            triage_hypothesize="deterministic",
            triage_investigate="off",
            triage_plan="fixed",
        )
    good = Settings(
        triage_hypothesize="deterministic",
        triage_investigate="deterministic",
        triage_plan="fixed",
        triage_evidence_tests=True,
    )
    assert good.triage_hypothesize == "deterministic"


def test_compiling_requires_no_model_or_extra_provider_reads():
    state, deps, provider = case()
    investigate(state, deps)
    before = len(provider.calls)
    update_candidate_packet(state, stage="hypothesize")
    assert len(provider.calls) == before
    assert all(
        eid in {e.id for e in state.evidence}
        for candidate in state.triage_candidates
        for eid in candidate.observation_evidence_ids
    )


def test_job_paths_discovered_during_test_are_scheduled():
    """An inspection discovered during Test must schedule every failed job path."""
    from capstone.agent.artifacts import DetectedAnomaly
    from capstone.agent.triage_decide import initialize_requirements
    from capstone.agent.triage_plan import fixed_plan
    from capstone.providers.factory import tool_spec

    state = state_for(max_tool_calls=12)
    state.anomaly = DetectedAnomaly(
        tick=40, kind="inspection_failures", description="two failed jobs"
    )
    state.unanswered_questions = list(fixed_plan(state.anomaly))
    state.question_predicates = {}
    state.triage_packet = None
    state.triage_requirements.clear()
    state.triage_requirement_results.clear()

    def records(request):
        if request.name == "get_inspections":
            return [
                {"tick": 40, "job_id": 10, "batch_id": 1, "result": "failed"},
                {"tick": 41, "job_id": 11, "batch_id": 1, "result": "failed"},
            ]
        if request.name == "get_job_history":
            return [
                {
                    "tick": 30,
                    "job_id": request.arguments["job_id"],
                    "machine_id": "CNC-02",
                    "kind": "job_started",
                    "message": "job began",
                }
            ]
        return []

    provider = FakeProvider(records, tick=45)
    tools = tuple(
        tool_spec(name) for name in ("get_inspections", "get_job_history", "get_events")
    )
    deps = replace(
        deps_for(provider, tools=tools),
        triage_hypothesize="deterministic",
    )
    initialize_requirements(state)
    update_candidate_packet(state, stage="hypothesize", deps=deps)
    assert not any(
        rid.startswith("Q1:job:") for rid in state.triage_test_requirement_ids
    )

    run_test(state, deps)
    assert {"Q1:job:10", "Q1:job:11"} <= set(state.triage_test_requirement_ids)
    assert sorted(
        request.arguments["job_id"]
        for request in provider.calls
        if request.name == "get_job_history"
    ) == [10, 11]
    assert all(
        candidate.status == "unconfirmed" for candidate in state.triage_candidates
    )


def test_unsupported_channels_remain_missing_but_are_not_scheduled():
    """Missing recorded channels must not become executable Test requests."""
    from capstone.agent.triage_decide import initialize_requirements
    from capstone.providers.factory import tool_spec

    state, deps, provider = case()
    deps = replace(
        deps,
        triage_tool_specs=(tool_spec("get_sensor_summary"),),
        triage_channels={"CNC-02": ("vibration",)},
    )
    initialize_requirements(state)
    update_candidate_packet(state, stage="hypothesize", deps=deps)
    load = next(c for c in state.triage_candidates if c.family == "operating_load")
    assert {"Q5:temperature", "Q5:load"} <= set(load.missing_requirement_ids)
    assert {"Q5:temperature", "Q5:load"} <= set(load.unavailable_requirement_ids)
    assert "Q5:temperature" not in state.triage_test_requirement_ids
    assert "Q5:load" not in state.triage_test_requirement_ids
    run_test(state, deps)
    assert state.triage_decide_trace[-1].reason == "capability_unavailable"
    assert "Q5" in state.triage_question_gaps
    assert "Q5" in {question.id for question in state.unanswered_questions}
    assert all(
        call.arguments.get("sensor") not in {"temperature", "load"}
        for call in provider.calls
    )


def test_qualified_summaries_do_not_close_composite_q5():
    """Source sufficiency is not time-aligned covariation or a confirmed cause."""
    state, deps, _ = case()
    investigate(state, deps)
    hypothesize(state, deps)
    run_test(state, deps)
    assert "Q5" in state.triage_question_gaps
    load = next(c for c in state.triage_candidates if c.family == "operating_load")
    assert "Q5" in load.open_question_ids
    assert load.status == "unconfirmed"
    assert state.triage_hypothesis_trace[-1].unresolved_questions > 0


def test_logging_transport_failure_does_not_change_decision_or_test_plan():
    """Optional JSON logging can fail without changing deterministic behavior."""

    class BrokenLogger:
        def log_event(self, *args, **kwargs):
            raise OSError("private driver error")

    normal_state, normal_deps, _ = case()
    broken_state, broken_deps, _ = case(event_logger=BrokenLogger())
    for state, deps in ((normal_state, normal_deps), (broken_state, broken_deps)):
        investigate(state, deps)
        hypothesize(state, deps)
        run_test(state, deps)

    assert normal_state.triage_candidates == broken_state.triage_candidates
    assert normal_state.triage_test_requirement_ids == (
        broken_state.triage_test_requirement_ids
    )
    assert normal_state.triage_hypothesis_trace == (
        broken_state.triage_hypothesis_trace
    )
    assert normal_state.triage_hypothesis_logging_failures == 0
    assert broken_state.triage_hypothesis_logging_failures > 0


def test_candidate_archive_contract_is_backward_compatible():
    """The experiment stores candidate traces without breaking old runs."""
    from capstone.experiment import TriageRecord

    state, deps, _ = case()
    investigate(state, deps)
    hypothesize(state, deps)
    record = TriageRecord(
        seconds=1.0,
        conclusion=None,
        confidence=None,
        recommendation=None,
        deep_recommended=True,
        deep_ran=False,
        deterministic_candidates=list(state.triage_candidates),
        deterministic_test_requirement_ids=state.triage_test_requirement_ids,
        deterministic_hypothesis_trace=list(state.triage_hypothesis_trace),
    )
    assert record.deterministic_candidates[0].id == "TC1"
    previous = TriageRecord.model_validate(
        {
            "seconds": 1.0,
            "conclusion": None,
            "confidence": None,
            "recommendation": None,
            "deep_recommended": True,
            "deep_ran": False,
        }
    )
    assert previous.deterministic_candidates is None
    assert previous.deterministic_hypothesis_trace is None


@pytest.mark.parametrize("broken_summary", [False, True])
def test_full_graph_deterministic_triage_reaches_checked_conclude(broken_summary):
    """The actual Graph uses one model stage and preserves unresolved telemetry."""
    from capstone.agent.investigation import run_investigation
    from tests.helpers import START, new_state
    from tests.test_triage_deterministic_decide import ALARM

    class ConclusionOnly(NoDecideModel):
        def plan(self, state):
            raise AssertionError("the fixed plan must not ask a model")

        def hypothesize(self, state):
            raise AssertionError("deterministic Hypothesize must not ask a model")

        def conclude(self, state):
            self.asked.append("conclude")
            assert state.triage_candidates
            assert state.triage_hypothesis_trace
            assert "Q5" in state.triage_question_gaps
            return (
                AgentConclusion(
                    diagnosis="unresolved sensor anomaly",
                    confidence=0.4,
                    recommendation="escalate",
                    assessment="unresolved",
                    hypothesis_id="TC1",
                    evidence_ids=tuple(e.id for e in state.evidence[:1]),
                ),
                None,
            )

    def respond(request):
        if request.name == "get_time":
            return {"tick": 45, "time": START.isoformat()}
        if request.name == "get_sensor_summary" and broken_summary:
            return {"machine_id": request.arguments["machine_id"]}
        return answer(request)

    policy = ConclusionOnly()
    provider = FakeProvider(respond, tick=45)
    state = new_state(max_tool_calls=12, max_iterations=24)
    state.mode = "triage"
    state.anomaly = ALARM
    state.triage_fixed_plan = True
    state.triage_packet_enabled = False
    deps = replace(
        deps_for(provider),
        policy=policy,
        triage_hypothesize="deterministic",
        screening_available=False,
    )
    run_investigation(state, deps)

    assert state.fixed_plan_used
    assert policy.asked == ["conclude"]
    assert state.triage_hypothesis_trace[0].stage == "hypothesize"
    assert state.triage_hypothesis_trace[-1].stage == "test"
    assert state.triage_decide_trace
    assert "Q5" in state.triage_question_gaps
    assert state.conclusion is not None
    assert state.conclusion.recommendation == "escalate"
    assert state.conclusion.assessment == "unresolved"
    assert state.deep_recommended
    assert state.triage_report is not None
    assert state.proposed_action is None
    if broken_summary:
        assert state.triage_requirement_results["Q1:trigger"].status != "satisfied"


def test_three_test_reads_survive_unchanged_model_confidence():
    """No model confidence-stall heuristic can stop deterministic evidence tests."""
    state, deps, provider = case()
    deps.stalled_test_results = 1  # Would stop a model confidence-driven Test.
    investigate(state, deps)
    assert hypothesize(state, deps) == "continue"
    initial_calls = len(provider.calls)
    run_test(state, deps)
    test_reads = [
        decision
        for decision in state.triage_decide_trace
        if decision.phase == "test" and decision.kind == "read"
    ]
    assert len(test_reads) >= 3
    assert len(provider.calls) >= initial_calls + 3
    assert not state.hypotheses
    assert not deps.policy.asked
    assert "Q5" in state.triage_question_gaps


def test_zero_candidate_plan_falls_through_to_conclude_without_model():
    """An empty authorized requirement packet never invokes fallback reasoning."""
    state, deps, provider = case()
    state.triage_requirements.clear()
    state.triage_requirement_results.clear()
    assert hypothesize(state, deps) == "conclude"
    assert state.triage_candidates == []
    assert state.triage_test_requirement_ids == ()
    assert state.triage_hypothesis_trace[-1].action == "no_candidates"
    assert provider.calls == []
    assert deps.policy.asked == []
