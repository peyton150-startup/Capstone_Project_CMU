"""Replayed triage only receives explicitly authorized MTConnect events."""

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


def test_stopped_program_is_not_falsely_reported_as_idle():
    from datetime import timedelta

    from tests.test_replay_provider import T0, obs

    records = capture()
    records[0] = obs(0, "exec", "STOPPED", type_="Execution")
    provider = replay_provider(
        records,
        channel_map(),
        now=T0 + timedelta(seconds=30),
    )
    status = provider.call(ToolRequest(name="list_machines"))
    assert not status.success


def test_replay_fails_closed_on_out_of_order_source_clocks():
    import pytest

    records = capture()
    records[1], records[2] = records[2], records[1]
    with pytest.raises(ValueError, match="out of order"):
        replay_provider(records, channel_map())
