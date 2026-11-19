"""Replayed triage only receives explicitly authorized MTConnect events."""

import pytest

from capstone.contracts.tools import ToolRequest
from capstone.providers.replay import replay_provider
from capstone.recorded_investigation import replay_tool_specs
from tests.test_replay_provider import capture, channel_map


def test_legacy_replay_still_refuses_unapproved_events():
    provider = replay_provider(capture(), channel_map())
    result = provider.call(
        ToolRequest(name="get_events", arguments={"from_tick": 0, "to_tick": 3})
    )
    assert not result.success
    assert "get_events" not in {
        tool.name
        for tool in replay_tool_specs(
            capture(),
            channel_map(),
            now=provider._observations.now,
        )
    }


def test_approved_execution_events_reach_typed_provider_and_tool_catalog():
    permitted = frozenset({"exec"})
    provider = replay_provider(
        capture(),
        channel_map(),
        approved_event_item_ids=permitted,
    )
    result = provider.call(
        ToolRequest(name="get_events", arguments={"from_tick": 0, "to_tick": 3})
    )
    assert result.success, result.error
    assert [event["kind"] for event in result.data] == ["status", "status"]
    assert all(event["job_id"] is None for event in result.data)

    offered = replay_tool_specs(
        capture(),
        channel_map(),
        now=provider._observations.now,
        approved_event_item_ids=permitted,
    )
    assert "get_events" in {tool.name for tool in offered}


def test_unknown_approved_event_identifier_is_refused_before_any_read():
    import pytest

    with pytest.raises(ValueError, match="approved event IDs"):
        replay_provider(
            capture(),
            channel_map(),
            approved_event_item_ids=frozenset({"fake-alarm"}),
        )


@pytest.mark.parametrize("state", ["STOPPED", "INTERRUPTED", "PROGRAM_STOPPED"])
def test_stopped_program_is_unknown_not_idle_or_down(state):
    """The developer's choice (2026-11-19): keep the tool usable, claim nothing."""
    from datetime import timedelta

    from tests.test_replay_provider import T0, obs

    records = capture()
    records[0] = obs(0, "exec", state, type_="Execution")
    provider = replay_provider(
        records,
        channel_map(),
        now=T0 + timedelta(seconds=30),
    )
    status = provider.call(ToolRequest(name="list_machines"))
    assert status.success, status.error
    assert status.data[0]["status"] == "unknown"


def test_alarm_events_say_whether_they_are_a_warning_or_a_fault():
    from tests.test_replay_provider import obs

    lines = capture() + [
        obs(61, "S1temp", "WARNING", type_="Temperature").model_copy(
            update={"category": "CONDITION", "type": "TEMPERATURE"}
        ),
        obs(62, "S1temp", "FAULT", type_="Temperature").model_copy(
            update={"category": "CONDITION", "type": "TEMPERATURE"}
        ),
        obs(63, "S1temp", "NORMAL", type_="Temperature").model_copy(
            update={"category": "CONDITION", "type": "TEMPERATURE"}
        ),
    ]
    provider = replay_provider(
        lines, channel_map(), approved_event_item_ids=frozenset({"S1temp", "exec"})
    )
    result = provider.call(
        ToolRequest(name="get_events", arguments={"from_tick": 0, "to_tick": 5})
    )
    assert result.success, result.error
    alarms = [
        (e["kind"], e.get("severity"))
        for e in result.data
        if "condition" in e["message"]
    ]
    assert alarms == [
        ("alarm", "warning"),
        ("alarm", "fault"),
        ("condition_clear", None),
    ]
    # Execution events carry no severity key at all.
    assert all("severity" not in e for e in result.data if "execution" in e["message"])


def test_replay_fails_closed_on_out_of_order_source_clocks():
    import pytest

    records = capture()
    records[1], records[2] = records[2], records[1]
    with pytest.raises(ValueError, match="out of order"):
        replay_provider(records, channel_map())


def restart_capture():
    """Execution set at 120 s, load up to 200 s, a buffer overrun, then the
    collector re-reads /current: it repeats Execution ACTIVE with its ORIGINAL
    timestamp and sequence (older than the last load line), then load at 300 s.
    """
    from tests.test_replay_provider import gap, obs

    return [
        obs(0, "exec", "READY", type_="Execution"),
        obs(120, "exec", "ACTIVE", type_="Execution"),
        obs(200, "S1load", "10"),
        gap(250),
        obs(120, "exec", "ACTIVE", type_="Execution"),
        obs(300, "S1load", "40"),
    ]


def test_a_capture_with_a_collector_restart_is_still_replayable():
    """Ordering is checked per channel: a /current repeat is not time travel."""
    provider = replay_provider(
        restart_capture(), channel_map(), approved_event_item_ids=frozenset({"exec"})
    )
    result = provider.call(
        ToolRequest(name="get_events", arguments={"from_tick": 0, "to_tick": 5})
    )
    assert result.success, result.error
    # The repeated ACTIVE (same source, instance and sequence) is listed once.
    assert [event["message"] for event in result.data] == [
        "MTConnect execution READY",
        "MTConnect execution ACTIVE",
    ]


def test_a_channel_going_back_in_time_is_still_refused():
    import pytest

    from tests.test_replay_provider import obs

    lines = [obs(0, "S1load", "10"), obs(90, "S1load", "20"), obs(60, "S1load", "30")]
    with pytest.raises(ValueError, match="out of order"):
        replay_provider(lines, channel_map())
