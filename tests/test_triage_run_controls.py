"""Per-run managed configuration is validated, immutable and Graph-scoped."""

import pytest
from pydantic import ValidationError

from capstone.settings import Settings
from capstone.triage_run_controls import (
    EffectiveTriageRun,
    TriageRunOptions,
    overridden_fields,
    resolve_triage_run,
)


def settings():
    return Settings(
        _env_file=None,
        triage_run_mode="custom",
        triage_plan="fixed",
        triage_investigate="deterministic",
        triage_hypothesize="deterministic",
        triage_evidence_tests=True,
        triage_packet=True,
        triage_packet_prompt=True,
        triage_then_deep=True,
        critic=False,
        triage_seconds=90,
        triage_tool_calls=6,
    )


def test_deterministic_overrides_stage_knobs_but_retains_conclude_and_budget():
    raw = TriageRunOptions(
        run_mode="deterministic",
        plan="model",
        investigate="off",
        hypothesize="model",
        evidence_tests=False,
        packet=False,
        packet_prompt=False,
        observe_calls="shared",
        hypothesis_seconds=30,
        then_deep=False,
        conclude_brief=False,
        conclude_cap=False,
        seconds=64,
        tool_calls=3,
    )
    run = resolve_triage_run(settings(), raw)
    assert run.run_mode == "deterministic"
    assert (run.plan, run.investigate, run.hypothesize) == (
        "fixed", "deterministic", "deterministic"
    )
    assert run.packet and run.packet_prompt and run.evidence_tests
    assert run.observe_calls == "separate"
    assert run.hypothesis_seconds == 0.0
    assert run.seconds == 64 and run.tool_calls == 3
    assert not run.then_deep and not run.conclude_brief and not run.conclude_cap
    assert run.stage_modes()["conclude"] == "model"
    assert run.stage_modes()["critic_recheck"] == "off"
    assert "plan" in overridden_fields(raw, run)
    assert "then_deep" not in overridden_fields(raw, run)
    assert run == EffectiveTriageRun.model_validate(run.model_dump())


def test_custom_mode_validates_dependencies_and_applies_selections():
    base = settings()
    custom = TriageRunOptions(
        run_mode="custom",
        plan="model",
        investigate="off",
        hypothesize="model",
        evidence_tests=False,
        packet=False,
        packet_prompt=False,
        observe_calls="shared",
        hypothesis_seconds=12,
        seconds=60,
    )
    resolved = resolve_triage_run(base, custom)
    assert resolved.plan == "model"
    assert resolved.investigate == "off"
    assert resolved.hypothesize == "model"
    assert not resolved.evidence_tests and not resolved.packet
    assert resolved.hypothesis_seconds == 12
    with pytest.raises(ValidationError, match="requires fixed Plan"):
        resolve_triage_run(
            base, TriageRunOptions(
                run_mode="custom", plan="model",
                investigate="deterministic", hypothesize="model",
            ),
        )
    with pytest.raises(ValidationError, match="requires fixed Plan"):
        resolve_triage_run(
            base, TriageRunOptions(
                run_mode="custom", plan="model", investigate="off",
                hypothesize="deterministic",
            ),
        )
    with pytest.raises(ValidationError, match="packet prompt requires"):
        resolve_triage_run(
            base, TriageRunOptions(
                run_mode="custom", packet=False, packet_prompt=True,
            ),
        )


@pytest.mark.parametrize("invalid", [
    {"run_mode": "unrestricted"},
    {"packet": "yes"},
    {"tool_calls": 0},
    {"tool_calls": 31},
    {"seconds": 901},
    {"hypothesis_seconds": -1},
    {"api_key": "PRIVATE"},
    {"allowed_sources": ["simulator", "siemens"]},
])
def test_unrecognized_or_unsafe_request_fields_are_refused(invalid):
    with pytest.raises(ValidationError):
        TriageRunOptions.model_validate(invalid)


def test_unmodified_server_default_is_preserved_and_immutable():
    cfg = settings()
    original = cfg.model_dump()
    effective = resolve_triage_run(cfg)
    assert effective.plan == "fixed"
    assert effective.seconds == 90
    assert effective.tool_calls == 6
    with pytest.raises(ValidationError):
        effective.seconds = 100
    assert cfg.model_dump() == original


def test_real_graph_episode_uses_only_submitted_triage_settings(monkeypatch):
    """No global env mutation: type-safe inputs flow to actual graph stages."""
    from capstone import episode
    from capstone.agent.artifacts import AgentConclusion
    from tests.test_episode import SEED
    from tests.test_triage_deterministic_decide import NoDecideModel

    cfg = settings()
    monkeypatch.setattr(episode, "get_settings", lambda: cfg)
    run = resolve_triage_run(
        cfg, TriageRunOptions(
            run_mode="deterministic", then_deep=False, seconds=70,
            tool_calls=3, conclude_brief=False, conclude_cap=False,
        )
    )
    policy = NoDecideModel(
        conclude=lambda state: (
            AgentConclusion(
                diagnosis="unresolved measurement",
                confidence=0.25,
                assessment="unresolved",
                recommendation="escalate",
            ),
            None,
        ),
    )
    result = episode.run_episode(
        SEED, policy, triage=True, triage_configuration=run, clock=lambda: 0.0
    )
    first = result.triage
    assert first is not None and result.state is first
    assert first.triage_run_mode == "deterministic"
    assert first.fixed_plan_used
    assert first.budgets.timeout_seconds == 70
    assert first.budgets.max_tool_calls == 3
    assert first.triage_conclude_brief is False
    assert first.triage_conclude_cap is False
    from capstone.api.runs import safe_executed_triage
    actual = safe_executed_triage(first)
    assert actual["run_mode"] == "deterministic"
    assert actual["fixed_plan_executed"]
    assert actual["deadline_seconds"] == 70
    assert actual["research_tool_call_budget"] == 3
    assert actual["conclude_brief_enabled"] is False
    assert "diagnosis" not in actual and "api_key" not in actual
    assert policy.asked == ["conclude"]
    assert cfg.triage_seconds == 90 and cfg.triage_tool_calls == 6


def test_custom_profile_can_override_server_deterministic_default(monkeypatch):
    """Turning the frontend switch OFF must actually restore model stages."""
    from capstone import episode
    from tests.test_episode import SEED, wear_policy
    from tests.test_triage import ByMode

    cfg = Settings(
        _env_file=None,
        triage_run_mode="deterministic",
        triage_plan="fixed",
        triage_investigate="deterministic",
        triage_hypothesize="deterministic",
        triage_evidence_tests=True,
        critic=False,
    )
    monkeypatch.setattr(episode, "get_settings", lambda: cfg)
    override = resolve_triage_run(
        cfg, TriageRunOptions(
            run_mode="custom",
            plan="model", investigate="off",
            hypothesize="model", evidence_tests=False,
            then_deep=False, seconds=60, tool_calls=4,
        )
    )
    policy = ByMode(wear_policy("escalate"), wear_policy())
    result = episode.run_episode(
        SEED, policy, triage=True, triage_configuration=override,
        clock=lambda: 0.0,
    )
    first = result.triage
    assert first is not None and result.state is first
    assert first.triage_run_mode == "custom"
    assert first.fixed_plan_used is False
    assert first.budgets.timeout_seconds == 60
    assert first.budgets.max_tool_calls == 4
    assert "plan" in policy.triage.asked
    assert "hypothesize" in policy.triage.asked
    assert "conclude" in policy.triage.asked
    # The source of defaults was never modified.
    assert cfg.triage_run_mode == "deterministic"
