"""Offline tests for the real-capture-to-investigation boundary.

Every observation is synthetic. No network connection, model key, or factory
controller is used.
"""

from datetime import timedelta

import pytest

from capstone.agent.artifacts import AgentConclusion
from capstone.agent.state import InvestigationState
from capstone.replay_investigation import (
    recorded_tool_specs,
    run_recorded_investigation,
)
from tests.helpers import ScriptedPolicy, ask
from tests.test_replay_provider import T0, capture, channel_map, obs


def test_policy_tool_list_only_contains_capabilities_supported_by_the_capture():
    specs = recorded_tool_specs(capture(), channel_map())
    names = {tool.name for tool in specs}
    assert names == {
        "get_time",
        "list_machines",
        "get_readings",
        "get_sensor_trend",
        "get_sensor_summary",
    }
    assert not {"wait", "get_line_screening", "get_settings", "get_events"} & names
    assert "load (PERCENT)" in next(
        tool.description for tool in specs if tool.name == "get_readings"
    )
    assert "READ-ONLY" in next(iter(specs)).description


def test_tool_list_does_not_offer_machine_status_without_execution():
    lines = [obs(0, "S1load", "10"), obs(60, "S1load", "20")]
    names = {tool.name for tool in recorded_tool_specs(lines, channel_map())}
    assert "list_machines" not in names
    assert "get_readings" in names


def test_cutoff_controls_which_mapped_channels_the_policy_can_see():
    earlier = recorded_tool_specs(
        capture(), channel_map(), cutoff=T0 + timedelta(seconds=100)
    )
    description = next(tool.description for tool in earlier if tool.name == "get_readings")
    assert "load (PERCENT)" in description
    assert "following_error" not in description
    with pytest.raises(ValueError, match="no numeric machine sensors"):
        recorded_tool_specs(capture(), channel_map(), cutoff=T0 - timedelta(seconds=1))


def unresolved(state: InvestigationState):
    """Return an explicitly unresolved, read-only result from a scripted policy."""
    return (
        AgentConclusion(
            diagnosis="The recorded load pattern needs technician review.",
            confidence=0.2,
            recommendation="escalate",
            assessment="unresolved",
            next_check="Ask the technician which program and tool were active.",
        ),
        None,
    )


def test_recorded_capture_uses_the_existing_graph_without_screening_or_actions():
    policy = ScriptedPolicy(
        decisions={
            "investigate": [
                ask(
                    "get_readings",
                    machine_id="VF2",
                    sensor="load",
                    from_tick=0,
                    to_tick=9,
                )
            ]
        },
        conclude=unresolved,
    )
    state = run_recorded_investigation(
        capture(),
        channel_map(),
        policy,
        machine_id="VF2",
        symptom="Operator noticed elevated spindle load",
    )
    assert state.mode == "triage"
    assert state.screening_tool_calls_used == 0
    assert state.conclusion is not None
    assert state.conclusion.recommendation == "escalate"
    assert state.proposed_action is None
    assert state.action_started_tick is None
    assert state.verification is None
    assert state.deep_recommended
    assert any(d.tool == "get_readings" and d.outcome == "observed" for d in state.decisions)
    assert not any(
        d.tool in {"get_line_screening", "propose_action", "execute_action", "wait"}
        for d in state.decisions
    )


def test_no_guessing_a_machine_or_symptom():
    policy = ScriptedPolicy(conclude=unresolved)
    for machine, symptom in [("UNKNOWN", "load high"), ("VF2", "")]:
        with pytest.raises(ValueError):
            run_recorded_investigation(
                capture(),
                channel_map(),
                policy,
                machine_id=machine,
                symptom=symptom,
            )
