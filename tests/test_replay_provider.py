"""SM-3: the agent's factory tools answered from a recorded capture, read-only.

The probe and the capture are synthetic; no test touches the network or a machine.
"""

from datetime import UTC, datetime, timedelta

import pytest

from capstone.contracts.tools import ToolRequest
from capstone.ingestion.channel_map import Assignment, build_channel_map
from capstone.ingestion.record import CollectorMarker, GapDetail, TelemetryRecord
from capstone.providers.factory import TOOL_ARGUMENTS
from capstone.providers.replay import RecordedObservationTools, replay_provider
from tests.test_channel_map import probe

T0 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


def channel_map(**extra):
    assignments = {
        "S1load": Assignment(measures="spindle load", tool_sensor="load"),
        "Xpos": Assignment(measures="X position", tool_sensor="following_error"),
        **extra,
    }
    return build_channel_map(probe(), assignments)


def obs(second: float, item: str, value: str | None, type_: str = "Load", device="VF2"):
    at = T0 + timedelta(seconds=second)
    return TelemetryRecord(
        source="http://agent:8082",
        instance_id="1",
        device=device,
        component="c",
        data_item_id=item,
        category="EVENT" if type_ == "Execution" else "SAMPLE",
        type=type_,
        value=value,
        available=value is not None,
        sequence=int(second) + 1,
        source_timestamp=at,
        received_at=at,
    )


def gap(second: float):
    return CollectorMarker(
        source="http://agent:8082",
        event="gap",
        at=T0 + timedelta(seconds=second),
        gap=GapDetail(cause="buffer_overrun"),
    )


def capture():
    """Ten minutes: load 10 for 90 s then 90 for 30 s, a gap, then load 40."""
    return [
        obs(0, "exec", "READY", type_="Execution"),
        obs(0, "S1load", "10"),
        obs(90, "S1load", "90"),
        obs(120, "exec", "ACTIVE", type_="Execution"),
        gap(300),
        obs(300, "S1load", "40"),
        obs(330, "S1load", None),  # UNAVAILABLE: no reading
        obs(360, "S1load", "50"),
        obs(599, "Xpos", "1.5"),
    ]


def call(provider, name, **arguments):
    return provider.call(ToolRequest(name=name, arguments=arguments))


# --- the existing contracts hold ---------------------------------------------


def test_every_tool_answers_inside_its_contract_or_refuses_cleanly():
    provider = replay_provider(capture(), channel_map())
    window = {"from_tick": 0, "to_tick": 9}
    requests = {
        "get_time": {},
        "list_machines": {},
        "get_readings": {"machine_id": "VF2", "sensor": "load", **window},
        "get_sensor_trend": {"machine_id": "VF2", "sensor": "load", **window},
        "get_sensor_summary": {"machine_id": "VF2", "sensor": "load", **window},
        "get_proposals": {},
        "wait": {"ticks": 1},
    }
    for name, arguments in requests.items():
        result = call(provider, name, **arguments)
        assert result.success, (name, result.error)
        assert result.source == "replay"
    refused = {
        "get_settings": {},
        "get_line_screening": {},
        "get_events": window,
        "get_job_history": {"job_id": 1},
        "get_maintenance_history": {"machine_id": None},
        "get_inspections": window,
        "get_factory_readings": {"sensor": "air_temperature", **window},
        "propose_action": {"machine_id": "VF2", "action": "x", "reason": "y"},
        "execute_action": {"proposal_id": 1},
    }
    assert set(requests) | set(refused) == set(TOOL_ARGUMENTS)
    for name, arguments in refused.items():
        result = call(provider, name, **arguments)
        assert not result.success, name
        assert result.error.code == "invalid_arguments", name
        assert "capture" in result.error.message, name


def test_time_runs_from_the_first_observation_in_one_minute_ticks():
    result = call(replay_provider(capture(), channel_map()), "get_time")
    assert (result.tick, result.data["tick"]) == (9, 9)
    assert result.timestamp == T0 + timedelta(seconds=599)


# --- readings ----------------------------------------------------------------


def test_readings_come_from_the_mapped_channel_with_the_probes_units():
    rows = call(
        replay_provider(capture(), channel_map()),
        "get_readings",
        machine_id="VF2",
        sensor="load",
        from_tick=0,
        to_tick=9,
    ).data
    assert [(r["tick"], r["value"], r["unit"]) for r in rows] == [
        (0, 10, "PERCENT"),
        (1, 90, "PERCENT"),
        (5, 40, "PERCENT"),
        (6, 50, "PERCENT"),  # the UNAVAILABLE record at 330 s is not a reading
    ]


def test_nothing_after_the_cutoff_is_shown_and_wait_moves_it():
    provider = replay_provider(
        capture(), channel_map(), now=T0 + timedelta(seconds=100)
    )
    window = {"machine_id": "VF2", "sensor": "load", "from_tick": 0, "to_tick": 9}
    assert [r["value"] for r in call(provider, "get_readings", **window).data] == [
        10,
        90,
    ]
    assert call(provider, "get_time").tick == 1
    assert call(provider, "wait", ticks=5).data["tick"] == 6
    assert len(call(provider, "get_readings", **window).data) == 4
    assert call(provider, "wait", ticks=60).data["tick"] == 9  # stops at the end


def test_an_unmapped_sensor_or_machine_is_refused_not_answered_empty():
    provider = replay_provider(capture(), channel_map())
    window = {"from_tick": 0, "to_tick": 9}
    power = call(provider, "get_readings", machine_id="VF2", sensor="power", **window)
    assert "VF2 has no channel mapped to power" in power.error.message
    other = call(provider, "get_readings", machine_id="M2", sensor="load", **window)
    assert "unknown machine M2" in other.error.message


def test_records_named_by_device_uuid_are_read_too():
    lines = [obs(0, "S1load", "10", device="haas-vf2"), obs(60, "S1load", "20")]
    lines.append(obs(120, "exec", "ACTIVE", type_="Execution"))
    rows = call(
        replay_provider(lines, channel_map()),
        "get_readings",
        machine_id="VF2",
        sensor="load",
        from_tick=0,
        to_tick=2,
    ).data
    assert [r["value"] for r in rows] == [10, 20]


# --- statistics ----------------------------------------------------------------


def test_the_trend_is_time_weighted_and_never_spans_the_gap():
    rows = call(
        replay_provider(capture(), channel_map()),
        "get_sensor_trend",
        machine_id="VF2",
        sensor="load",
        from_tick=0,
        to_tick=9,
        bucket_ticks=5,
    ).data
    first, second = rows
    # Ticks 0-4: 10 held 90 s, 90 held 30 s (to the last reading before the
    # gap), and nothing across the gap: (10*90 + 90*30) / 120 = 30.
    assert (first["mean"], first["min"], first["max"], first["count"]) == (
        30,
        10,
        90,
        2,
    )
    # Ticks 5-9: 40 for 30 s, UNAVAILABLE for 30 s (not filled), 50 for 239 s.
    assert second["mean"] == pytest.approx(round((40 * 30 + 50 * 239) / 269, 3))
    assert second["count"] == 2


def test_the_summary_mean_is_time_weighted_and_the_rate_is_endpoint():
    summary = call(
        replay_provider(capture(), channel_map()),
        "get_sensor_summary",
        machine_id="VF2",
        sensor="load",
        from_tick=0,
        to_tick=4,
    ).data
    assert summary["sample_count"] == 2
    assert summary["mean"] == 30  # a plain average of 10 and 90 would say 50
    assert summary["rate_of_change"] == 80  # (90 - 10) over one tick, as described


# --- machines ----------------------------------------------------------------------


def test_machine_status_follows_the_last_execution_value():
    early = replay_provider(capture(), channel_map(), now=T0 + timedelta(seconds=60))
    assert call(early, "list_machines").data == [
        {"machine_id": "VF2", "status": "idle", "job_id": None, "hydraulics": False}
    ]
    late = call(replay_provider(capture(), channel_map()), "list_machines").data
    assert late[0]["status"] == "running"


def test_a_machine_without_an_execution_value_is_not_guessed():
    lines = [obs(0, "S1load", "10"), obs(60, "S1load", "20")]
    result = call(replay_provider(lines, channel_map()), "list_machines")
    assert "no Execution value for VF2" in result.error.message


# --- construction --------------------------------------------------------------------


def test_a_bad_setup_is_refused():
    with pytest.raises(ValueError, match="no observations"):
        RecordedObservationTools([gap(0)], channel_map())
    with pytest.raises(ValueError, match="inside the capture"):
        RecordedObservationTools(
            capture(), channel_map(), now=T0 - timedelta(seconds=1)
        )
    doubled = channel_map(S1speed=Assignment(tool_sensor="load"))
    with pytest.raises(ValueError, match="two channels assigned load"):
        RecordedObservationTools(capture(), doubled)
