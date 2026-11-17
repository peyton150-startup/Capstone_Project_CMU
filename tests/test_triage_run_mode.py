"""Profile precedence and graph isolation for one-switch deterministic triage."""

from dataclasses import replace

import pytest

from capstone.agent.artifacts import AgentConclusion
from capstone.agent.investigation import hypothesize, run_investigation
from capstone.settings import Settings, TriageExecutionProfile
from tests.helpers import FakeProvider, ScriptedPolicy
from tests.test_triage_deterministic_decide import (
    NoDecideModel,
    answer,
    deps_for,
    state_for,
)


def test_deterministic_profile_overrides_conflicting_raw_knobs():
    cfg = Settings(
        _env_file=None,
        triage_run_mode="deterministic",
        triage_plan="model",
        triage_investigate="off",
        triage_hypothesize="model",
        triage_evidence_tests=False,
        triage_packet=False,
        triage_packet_prompt=False,
        triage_observe_calls="shared",
        triage_hypothesis_seconds=25,
        critic=True,
        critic_followup=True,
        tot_reinstate=True,
    )
    effective = cfg.effective_triage
    assert isinstance(effective, TriageExecutionProfile)
    assert effective.run_mode == "deterministic"
    assert effective.plan == "fixed"
    assert effective.investigate == "deterministic"
    assert effective.hypothesize == "deterministic"
    assert effective.evidence_tests and effective.packet and effective.packet_prompt
    assert effective.observe_calls == "separate"
    assert effective.hypothesis_seconds == 0
    assert not effective.critic
    assert not effective.critic_followup
    assert not effective.critic_reinstate
    # Raw deep/global configuration is not silently mutated.
    assert cfg.triage_plan == "model"
    assert cfg.triage_investigate == "off"
    assert cfg.triage_hypothesize == "model"
    assert cfg.critic
    assert cfg.critic_followup
    assert cfg.tot_reinstate


def test_custom_mode_retains_legacy_arm_and_validation():
    cfg = Settings(
        _env_file=None,
        triage_run_mode="custom",
        triage_plan="model",
        triage_investigate="off",
        triage_hypothesize="model",
        triage_evidence_tests=False,
        triage_packet=False,
        triage_observe_calls="shared",
    )
    profile = cfg.effective_triage
    assert profile.plan == "model"
    assert profile.investigate == "off"
    assert profile.hypothesize == "model"
    assert not profile.evidence_tests and not profile.packet
    assert profile.observe_calls == "shared"
    with pytest.raises(ValueError, match="requires"):
        Settings(
            _env_file=None,
            triage_run_mode="custom",
            triage_investigate="off",
            triage_hypothesize="deterministic",
        )


def test_profile_contract_rejects_inconsistent_direct_instances():
    with pytest.raises(ValueError, match="incompatible"):
        TriageExecutionProfile(
            run_mode="deterministic",
            plan="model",
            investigate="deterministic",
            hypothesize="deterministic",
            evidence_tests=True,
            packet=True,
            packet_prompt=True,
            observe_calls="separate",
            hypothesis_seconds=0,
            critic=False,
            critic_followup=False,
            critic_reinstate=False,
        )


def test_direct_graph_entry_forces_stages_and_calls_only_conclude_model():
    from tests.helpers import START, new_state

    def source(request):
        if request.name == "get_time":
            return {"tick": 45, "time": START.isoformat()}
        return answer(request)

    policy = NoDecideModel(
        conclude=lambda state: (
            AgentConclusion(
                diagnosis="unresolved sensor anomaly",
                confidence=0.3,
                recommendation="escalate",
                assessment="unresolved",
            ),
            None,
        )
    )
    provider = FakeProvider(source, tick=45)
    state = new_state(max_tool_calls=12, max_iterations=24)
    state.mode = "triage"
    state.anomaly = state_for().anomaly
    state.triage_packet_enabled = False
    state.triage_observe_separate = False
    deps = replace(
        deps_for(provider),
        policy=policy,
        triage_run_mode="deterministic",
        triage_investigate="off",
        triage_hypothesize="model",
        triage_evidence_tests=False,
        critic_followup=True,
    )
    completed = run_investigation(state, deps)
    assert completed.triage_run_mode == "deterministic"
    assert completed.triage_fixed_plan
    assert completed.fixed_plan_used
    assert completed.triage_packet_enabled
    assert completed.triage_observe_separate
    assert completed.triage_hypothesis_seconds == 0
    assert policy.asked == ["conclude"]
    assert completed.conclusion is not None
    assert completed.proposed_action is None
    assert all(candidate.status == "unconfirmed" for candidate in completed.triage_candidates)


def test_saved_profile_marker_and_deep_isolation():
    state = state_for()
    state.triage_run_mode = "deterministic"
    provider = FakeProvider(answer, tick=45)
    deps = deps_for(provider)
    # Direct calls honoring a persisted profile normalize even if the
    # caller did not set the matching dependency override.
    assert state.triage_run_mode == "deterministic"
    deep = state_for(mode="deep")
    policy = ScriptedPolicy()
    deps = replace(deps, triage_run_mode="deterministic", policy=policy)
    hypothesize(deep, deps)
    assert policy.asked == ["hypothesize"]
    assert deep.triage_run_mode == "custom"


def test_existing_state_without_profile_roundtrips_to_custom():
    state = state_for()
    payload = state.model_dump()
    payload.pop("triage_run_mode")
    restored = type(state).model_validate(payload)
    assert restored.triage_run_mode == "custom"
