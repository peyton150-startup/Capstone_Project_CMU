"""Replay-to-investigation tests with synthetic data and a scripted policy.

No network requests, real controllers, model API keys or shop data are used.
"""

from datetime import timedelta

import pytest

from capstone.agent.artifacts import AgentConclusion, TerminationReason
from capstone.agent.policy import Stop
from capstone.recorded_investigation import (
    main,
    replay_tool_specs,
    run_recorded_investigation,
)
from tests.helpers import ScriptedPolicy, ask
from tests.test_replay_provider import T0, capture, channel_map


def unresolved_policy():
    """Review a mapped load value and explicitly request technician validation."""
    # Variables:
    #   finding: The uncertain result returned after the agent reads telemetry.
    finding = AgentConclusion(
        diagnosis="cause not established by recorded spindle load",
        confidence=0.2,
        assessment="unresolved",
        recommendation="escalate",
        next_check="ask the operator about program and tool changes",
    )
    return ScriptedPolicy(
        decisions={
            "investigate": [
                ask(
                    "get_sensor_summary",
                    machine_id="VF2",
                    sensor="load",
                    from_tick=0,
                    to_tick=9,
                ),
                Stop(reason=TerminationReason.NO_USEFUL_ACTION),
            ]
        },
        conclude=lambda state: (finding, None),
    )


def test_offered_tools_match_real_observed_channels_and_no_simulator_tools():
    tools = replay_tool_specs(capture(), channel_map(), now=T0 + timedelta(seconds=300))
    names = {tool.name for tool in tools}
    assert {
        "get_time",
        "get_readings",
        "get_sensor_trend",
        "get_sensor_summary",
    } <= names
    assert "get_factory_readings" not in names
    assert "get_line_screening" not in names
    assert "get_settings" not in names
    assert "get_events" not in names
    assert "get_maintenance_history" not in names
    assert "get_inspections" not in names
    assert "propose_action" not in names
    summary = next(tool for tool in tools if tool.name == "get_sensor_summary")
    assert summary.arguments["properties"]["sensor"]["enum"] == ["load"]
    assert "VF2: load" in summary.description
    assert "60 seconds" in summary.description


def test_future_channel_not_offered_until_its_actual_observation():
    earlier = replay_tool_specs(
        capture(), channel_map(), now=T0 + timedelta(seconds=300)
    )
    later = replay_tool_specs(capture(), channel_map(), now=T0 + timedelta(seconds=599))
    old = next(tool for tool in earlier if tool.name == "get_readings")
    new = next(tool for tool in later if tool.name == "get_readings")
    assert old.arguments["properties"]["sensor"]["enum"] == ["load"]
    assert new.arguments["properties"]["sensor"]["enum"] == [
        "following_error",
        "load",
    ]
    assert "wait" in {tool.name for tool in earlier}
    assert "wait" not in {tool.name for tool in later}


def test_recorded_data_runs_through_the_existing_graph_without_actions(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    policy = unresolved_policy()
    state = run_recorded_investigation(
        capture(),
        channel_map(),
        policy,
        machine_id="VF2",
        description="Review unusual spindle load, root cause unknown",
        clock=lambda: 0.0,
    )
    assert state.mode == "triage"
    assert state.anomaly.machine_id == "VF2"
    assert state.anomaly.kind == "operator_review"
    # Recorded captures have no simulator baseline: screening is not invoked.
    assert state.screening_tool_calls_used == 0
    assert not any(d.tool == "get_line_screening" for d in state.decisions)
    assert state.proposed_action is None
    assert state.action_started_tick is None
    assert state.verification is None
    assert state.deep_recommended is True
    assert any(
        d.tool == "get_sensor_summary" and d.outcome == "observed"
        for d in state.decisions
    )
    assert not any(
        d.tool in {"propose_action", "execute_action"} for d in state.decisions
    )
    assert "plan" in policy.asked
    assert "conclude" in policy.asked


def test_replay_rejects_unknown_or_unmapped_machine():
    with pytest.raises(ValueError, match="no manually mapped"):
        run_recorded_investigation(
            capture(),
            channel_map(),
            unresolved_policy(),
            machine_id="FAKE",
            description="Review a reading",
        )


def test_replay_rejects_an_empty_review_request():
    with pytest.raises(ValueError, match="nonempty"):
        run_recorded_investigation(
            capture(),
            channel_map(),
            unresolved_policy(),
            machine_id="VF2",
            description="  ",
        )


def test_cli_requires_explicit_authorization_before_reading_any_capture(capsys):
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--capture",
                "/missing/capture.jsonl",
                "--channel-map",
                "/missing/map.json",
                "--probe",
                "/missing/probe.xml",
                "--machine",
                "VF2",
                "--description",
                "Review spindle load",
                "--out",
                "/missing/review.json",
            ]
        )
    assert error.value.code == 2
    assert "--approved-remote-model" in capsys.readouterr().err


def test_cli_refuses_to_write_confidential_review_inside_a_checkout(tmp_path, capsys):
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--capture",
                "/missing/capture.jsonl",
                "--channel-map",
                "/missing/map.json",
                "--probe",
                "/missing/probe.xml",
                "--machine",
                "VF2",
                "--description",
                "Review spindle load",
                "--out",
                str(checkout / "review.json"),
                "--approved-remote-model",
            ]
        )
    assert error.value.code == 2
    assert "inside the git checkout" in capsys.readouterr().err
