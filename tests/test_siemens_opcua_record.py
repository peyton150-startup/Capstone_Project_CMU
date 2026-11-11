"""The version 2 (OPC UA) record: what it stores and what it refuses."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from capstone.ingestion.siemens_opcua_record import (
    NodeRef,
    OpcUaDataChange,
    OpcUaGap,
    OpcUaSessionMarker,
    StatusInfo,
    continuous_runs,
    data_change,
    parse_opcua_line,
    severity_of,
    status_from_code,
    to_json_line,
)

SERVER = "urn:example:sinumerik:server"
NODE = NodeRef(namespace_uri="urn:example:nc", identifier="/Channel/Spindle/actSpeed")
T0 = datetime(2026, 11, 11, 15, 0, 0, tzinfo=UTC)

GOOD = 0x00000000
UNCERTAIN = 0x40000000
BAD_NO_COMMUNICATION = 0x80310000
GOOD_OVERFLOW = 0x00000480


def change(value=11980.5, value_type="Double", status_code=GOOD, **over):
    fields = {
        "server_uri": SERVER,
        "node": NODE,
        "value": value,
        "value_type": value_type,
        "status_code": status_code,
        "source_timestamp": T0,
        "server_timestamp": T0 + timedelta(milliseconds=40),
        "received_at": T0 + timedelta(milliseconds=80),
        "session_epoch": 1,
        "subscription_id": 7,
        "notification_seq": 1,
    }
    fields.update(over)
    return data_change(**fields)


def marker(event, epoch=1, gap=None, at=T0):
    return OpcUaSessionMarker(
        server_uri=SERVER, event=event, at=at, session_epoch=epoch, gap=gap
    )


def test_severity_comes_from_the_two_highest_bits():
    assert severity_of(GOOD) == "good"
    assert severity_of(GOOD_OVERFLOW) == "good"
    assert severity_of(UNCERTAIN) == "uncertain"
    assert severity_of(BAD_NO_COMMUNICATION) == "bad"
    assert severity_of(0xC0000000) == "bad"


def test_a_severity_that_disagrees_with_the_code_is_refused():
    with pytest.raises(ValidationError, match="does not match"):
        StatusInfo(code=BAD_NO_COMMUNICATION, severity="good")


def test_overflow_is_read_from_the_info_bits():
    assert status_from_code(GOOD_OVERFLOW).overflow is True
    assert status_from_code(GOOD).overflow is False
    # Bit 7 without the data-value info type is not an overflow.
    assert status_from_code(0x00000080).overflow is False


def test_a_good_value_keeps_its_type_and_three_clocks():
    record = change()
    assert record.value == 11980.5 and record.value_type == "Double"
    assert record.status.severity == "good"
    assert record.number() == 11980.5
    assert record.source_timestamp < record.server_timestamp < record.received_at


def test_a_bad_value_is_kept_but_is_never_a_number():
    record = change(
        value=0.0,
        status_code=BAD_NO_COMMUNICATION,
        status_name="BadNoCommunication",
        source_timestamp=None,
    )
    assert record.value == 0.0
    assert record.status.severity == "bad"
    assert record.source_timestamp is None
    assert record.number() is None
    assert record.number(allow_uncertain=True) is None


def test_an_uncertain_value_is_a_number_only_when_asked_for():
    record = change(status_code=UNCERTAIN)
    assert record.number() is None
    assert record.number(allow_uncertain=True) == 11980.5


@pytest.mark.parametrize(
    ("value", "kind"),
    [(float("nan"), "nan"), (float("inf"), "inf"), (float("-inf"), "-inf")],
)
def test_nan_and_infinity_are_set_aside_not_stored_as_numbers(value, kind):
    record = change(value=value)
    assert record.value is None and record.non_finite == kind
    assert record.number() is None
    assert parse_opcua_line(to_json_line(record)) == record


def test_words_and_flags_are_not_numbers():
    assert change(value="AUTO", value_type="String").number() is None
    assert change(value=True, value_type="Boolean").number() is None
    assert change(value=3, value_type="Int32").number() == 3.0


def test_a_whole_number_sent_as_a_double_is_stored_as_a_float():
    record = change(value=5, value_type="Double")
    assert record.value == 5.0 and isinstance(record.value, float)


@pytest.mark.parametrize(
    ("value", "value_type"),
    [
        (1, "Boolean"),
        (True, "Int32"),
        (1.5, "Int32"),
        ("1", "Double"),
        (256, "Byte"),
        (-1, "UInt16"),
        (2**31, "Int32"),
        (7, None),
    ],
)
def test_a_value_that_does_not_fit_its_type_is_refused(value, value_type):
    with pytest.raises(ValidationError):
        change(value=value, value_type=value_type)


def test_a_timestamp_without_a_timezone_is_refused():
    naive = datetime(2026, 11, 11, 15, 0, 0)
    for field in ("source_timestamp", "server_timestamp", "received_at"):
        with pytest.raises(ValidationError):
            change(**{field: naive})


def test_a_timestamp_keeps_its_own_offset():
    local = datetime(2026, 11, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
    record = parse_opcua_line(to_json_line(change(source_timestamp=local)))
    assert record.source_timestamp == local
    assert record.source_timestamp.utcoffset() == timedelta(hours=-5)


def test_a_missing_timestamp_stays_missing():
    record = change(source_timestamp=None, server_timestamp=None)
    line = json.loads(to_json_line(record))
    assert line["source_timestamp"] is None and line["server_timestamp"] is None


def test_the_record_has_no_mtconnect_sequence_or_instance_id():
    line = json.loads(to_json_line(change()))
    assert "sequence" not in line and "instance_id" not in line
    assert line["schema_version"] == 2 and line["source"] == "opcua"
    with pytest.raises(ValidationError):
        OpcUaDataChange.model_validate({**line, "sequence": 5})


def test_a_node_is_keyed_by_namespace_uri_not_index():
    same_path_elsewhere = NodeRef(
        namespace_uri="urn:example:plc", identifier=NODE.identifier
    )
    assert NODE.key != same_path_elsewhere.key
    assert "namespace_index" not in NodeRef.model_fields


def test_lines_round_trip_and_version_1_lines_are_refused():
    gap = marker(
        "gap",
        gap=OpcUaGap(cause="notification_missed", lost_from_seq=2, lost_to_seq=4),
    )
    for line in (change(), marker("connected"), gap):
        assert parse_opcua_line(to_json_line(line)) == line
    with pytest.raises(ValueError, match="not a version 2"):
        parse_opcua_line('{"record_type": "observation", "schema_version": 1}')
    with pytest.raises(ValueError):
        parse_opcua_line("not json")


def test_gap_detail_goes_with_a_gap_marker_and_no_other():
    with pytest.raises(ValidationError):
        marker("gap")
    with pytest.raises(ValidationError):
        marker("heartbeat", gap=OpcUaGap(cause="session_lost"))


def test_runs_split_at_gaps_and_reconnects_but_not_at_heartbeats():
    a, b, c, d = (change(notification_seq=n) for n in (1, 2, 5, 6))
    e = change(session_epoch=2, notification_seq=1)
    lines = [
        marker("connected"),
        a,
        marker("heartbeat"),
        b,
        marker("gap", gap=OpcUaGap(cause="notification_missed")),
        c,
        d,
        marker("disconnected"),
        marker("connected", epoch=2),
        e,
        marker("stopped", epoch=2),
    ]
    assert continuous_runs(lines) == [[a, b], [c, d], [e]]


def test_runs_split_on_a_new_epoch_even_without_a_marker():
    first = change()
    second = change(session_epoch=2)
    assert continuous_runs([first, second]) == [[first], [second]]
