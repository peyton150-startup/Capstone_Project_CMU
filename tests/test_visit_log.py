"""SM-4: the technician event log, matched to a capture, and the visit checklist.

The capture and probe are synthetic; no test touches the network or a machine.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from capstone.ingestion.record import CollectorMarker, GapDetail, TelemetryRecord
from capstone.ingestion.visit_log import (
    CONFIRM_BY_HAND,
    TechnicianEvent,
    check_visit,
    load_event_log,
    main,
    match_events,
    report_lines,
)
from tests.test_channel_map import probe

T0 = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)


def obs(minute: float, value: str | None = "1200", item: str = "S1speed"):
    at = T0 + timedelta(minutes=minute)
    return TelemetryRecord(
        source="http://agent:8082",
        instance_id="1",
        device="VF2",
        component="Rotary",
        data_item_id=item,
        category="SAMPLE",
        type="RotaryVelocity",
        value=value,
        available=value is not None,
        sequence=int(minute * 10) + 1,
        source_timestamp=at,
        received_at=at,
    )


def marker(minute: float, event: str, gap: GapDetail | None = None):
    return CollectorMarker(
        source="http://agent:8082",
        event=event,
        at=T0 + timedelta(minutes=minute),
        gap=gap,
    )


def capture():
    """Collected 14:00-14:10, lost 14:10-14:20, collected 14:20-14:30."""
    return [
        marker(0, "started"),
        *[obs(m) for m in range(0, 11)],
        marker(20, "gap", GapDetail(cause="buffer_overrun", lost_from_sequence=102)),
        *[obs(m) for m in range(20, 31)],
        obs(25, None, item="S1load"),
        marker(31, "stopped"),
    ]


def event(minute: float, kind: str = "tool_change", note: str = "T3 to T5"):
    return TechnicianEvent(
        at=T0 + timedelta(minutes=minute),
        event_type=kind,
        note=note,
        logged_by="operator A",
    )


LOG = """at,event_type,note,logged_by,until
2026-11-07T09:05:00-05:00,warm_up,spindle warm-up,operator A,2026-11-07T09:09:00-05:00
2026-11-07T09:25:00-05:00,program_change,started part 1142,operator A,
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- the event log ---------------------------------------------------------


def test_a_log_is_read_in_time_order_with_a_blank_until_left_empty(tmp_path):
    reordered = LOG.splitlines()
    text = "\n".join([reordered[0], reordered[2], reordered[1]]) + "\n"
    events = load_event_log(write(tmp_path, "log.csv", text))
    assert [e.event_type for e in events] == ["warm_up", "program_change"]
    assert events[0].at == T0 + timedelta(minutes=5)
    assert events[0].until == T0 + timedelta(minutes=9)
    assert events[1].until is None


def test_a_time_without_its_utc_offset_is_refused_not_guessed(tmp_path):
    text = "at,event_type,note,logged_by\n2026-11-07T09:05:00,warm_up,x,A\n"
    with pytest.raises(ValueError, match="(?s)line 2.*UTC offset"):
        load_event_log(write(tmp_path, "log.csv", text))


@pytest.mark.parametrize(
    "row, problem",
    [
        ("2026-11-07T09:05:00Z,coffee,x,A,", "event_type"),
        ("2026-11-07T09:05:00Z,warm_up,,A,", "note"),
        ("2026-11-07T09:05:00Z,warm_up,x,A,2026-11-07T09:00:00Z", "until is before at"),
    ],
)
def test_a_bad_entry_is_refused_with_its_line_number(tmp_path, row, problem):
    text = "at,event_type,note,logged_by,until\n" + row + "\n"
    with pytest.raises(ValueError, match=f"(?s)line 2.*{problem}"):
        load_event_log(write(tmp_path, "log.csv", text))


def test_a_header_missing_a_column_is_refused(tmp_path):
    with pytest.raises(ValueError, match="lacks logged_by"):
        load_event_log(write(tmp_path, "log.csv", "at,event_type,note\n"))


# --- matching entries to the capture -----------------------------------------


def test_each_entry_is_placed_in_collected_time_a_gap_or_outside():
    matches = match_events(
        [event(5), event(15), event(29.5), event(-10), event(45)], capture()
    )
    assert [m.placement for m in matches] == [
        "covered",
        "in_gap",
        "covered",
        "outside",
        "outside",
    ]
    assert matches[0].nearest_observation_at == T0 + timedelta(minutes=5)
    assert matches[0].offset_seconds == 0
    assert matches[2].offset_seconds == 30


def test_the_tolerance_allows_for_a_person_noting_the_time_late():
    late = event(10.5)  # 30 s after the last reading before the gap
    assert match_events([late], capture())[0].placement == "covered"
    tight = match_events([late], capture(), tolerance=timedelta(seconds=10))
    assert tight[0].placement == "in_gap"


def test_an_entry_against_an_empty_capture_is_outside():
    (match,) = match_events([event(5)], [marker(0, "started")])
    assert match.placement == "outside"
    assert match.nearest_observation_at is None


# --- the visit check ---------------------------------------------------------


def test_a_visit_with_probe_data_and_a_matched_log_is_ready():
    check = check_visit(probe(), capture(), [event(5), event(25)])
    assert check.probe_items == 7
    assert check.observations == 23
    assert check.channels_with_values == 1  # S1load only ever UNAVAILABLE
    assert (check.runs, check.gaps) == (2, 1)
    assert (check.first_at, check.last_at) == (T0, T0 + timedelta(minutes=30))
    assert check.ready


@pytest.mark.parametrize(
    "probe_xml, events, reason",
    [
        (None, [event(5)], "no probe"),
        ("<not-xml", [event(5)], "unreadable probe"),
        (probe(), [], "no log entries"),
        (probe(), [event(5), event(15)], "an entry in a gap"),
    ],
)
def test_a_visit_is_not_ready_when_a_file_is_missing_or_an_entry_unmatched(
    probe_xml, events, reason
):
    assert not check_visit(probe_xml, capture(), events).ready, reason


def test_the_report_lists_unmatched_entries_and_the_items_to_confirm_by_hand():
    lines = report_lines(check_visit(None, capture(), [event(5), event(15)]))
    text = "\n".join(lines)
    assert "[ ] probe saved: no probe was given" in text
    assert "1 of 2 entries fall in collected time" in text
    assert "in_gap: 2026-11-07T14:15:00+00:00 tool_change (T3 to T5)" in text
    for item in CONFIRM_BY_HAND:
        assert f"[ ] {item}" in text


# --- command line --------------------------------------------------------------


def test_command_line_checks_a_visit(tmp_path, capsys):
    probe_path = write(tmp_path, "probe.xml", probe())
    capture_path = write(
        tmp_path,
        "capture.jsonl",
        "".join(line.model_dump_json() + "\n" for line in capture()),
    )
    good = write(tmp_path, "log.csv", LOG)
    args = ["check", "--probe", str(probe_path), "--capture", str(capture_path)]
    assert main([*args, "--events", str(good)]) == 0
    assert "2 of 2 entries fall in collected time" in capsys.readouterr().out

    gap_log = LOG.replace("09:25:00", "09:15:00")
    assert main([*args, "--events", str(write(tmp_path, "gap.csv", gap_log))]) == 1

    naive = write(tmp_path, "naive.csv", LOG.replace("-05:00,warm", ",warm"))
    assert main([*args, "--events", str(naive)]) == 2
    assert "UTC offset" in capsys.readouterr().err


def test_command_line_writes_an_empty_log_outside_the_repository(tmp_path, capsys):
    out = tmp_path / "events.csv"
    assert main(["template", "--out", str(out), "--allow-inside-repo"]) == 0
    assert out.read_text(encoding="utf-8") == "at,event_type,note,logged_by,until\n"
    assert load_event_log(out) == []
    with pytest.raises(SystemExit):
        main(["template", "--out", str(out), "--allow-inside-repo"])  # never overwrite
    inside = Path(__file__).parent / "events.csv"
    with pytest.raises(SystemExit):
        main(["template", "--out", str(inside)])
    assert not inside.exists()
    assert "inside the git checkout" in capsys.readouterr().err
