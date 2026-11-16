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
    deps = replace(
        deps_for(provider),
        policy=policy or NoDecideModel(),
        triage_hypothesize="deterministic",
        event_logger=event_logger,
    )
    return state, deps, provider


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
    assert all("counts" in row for row in rows)
    assert next(row for row in rows if row["event"] == "triage.test.completed")[
        "success"
    ] is False
    assert "4.50" not in stream.getvalue()
    assert '"content"' not in stream.getvalue()
    assert state.triage_hypothesis_trace[0].candidate_ids == ("TC1", "TC2", "TC3")
    assert state.triage_hypothesis_trace[-1].stage == "test"


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
