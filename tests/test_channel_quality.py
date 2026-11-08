"""SM-2 remainder: UNAVAILABLE stretches and per-channel staleness in a capture.

Synthetic records only; no test touches the network or a machine.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from capstone.ingestion.quality import (
    channel_ages,
    load_limits,
    main,
    stale_channels,
    unavailable_spans,
)
from capstone.ingestion.record import CollectorMarker, GapDetail, TelemetryRecord

T0 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


def obs(second: float, item: str = "S1load", value: str | None = "40"):
    at = T0 + timedelta(seconds=second)
    return TelemetryRecord(
        source="http://agent:8082",
        instance_id="1",
        device="VF2",
        component="Rotary",
        data_item_id=item,
        category="SAMPLE",
        type="Load",
        value=value,
        available=value is not None,
        sequence=int(second) + 1,
        source_timestamp=at,
        received_at=at,
    )


def marker(second: float, event: str):
    return CollectorMarker(
        source="http://agent:8082",
        event=event,
        at=T0 + timedelta(seconds=second),
        gap=GapDetail(cause="buffer_overrun") if event == "gap" else None,
    )


def at(second: float) -> datetime:
    return T0 + timedelta(seconds=second)


# --- UNAVAILABLE stretches -------------------------------------------------


def test_a_stretch_runs_from_unavailable_to_the_next_real_value():
    lines = [
        marker(0, "started"),
        obs(0),
        obs(10, value=None),
        obs(15, value=None),  # still unavailable: the same stretch
        obs(15, item="S1speed", value="1200"),
        obs(40),
    ]
    (span,) = unavailable_spans(lines)
    assert (span.data_item_id, span.start, span.end) == ("S1load", at(10), at(40))
    assert span.ended_by == "available_again"
    assert span.seconds == 30


def test_a_stretch_open_at_a_gap_closes_at_the_last_collected_reading():
    lines = [
        obs(0),
        obs(10, value=None),
        obs(20, item="S1speed", value="1200"),
        marker(300, "gap"),
        obs(300),  # back, but after a gap: no one knows when it came back
    ]
    (span,) = unavailable_spans(lines)
    assert (span.start, span.end, span.ended_by) == (at(10), at(20), "collection_broke")


def test_a_stretch_open_at_the_end_closes_with_the_capture():
    lines = [obs(0, value=None), obs(5, item="S1speed", value="1")]
    (span,) = unavailable_spans(lines)
    assert (span.start, span.end, span.ended_by) == (at(0), at(5), "capture_end")


def test_a_channel_that_always_had_a_value_has_no_stretch():
    assert unavailable_spans([obs(0), obs(10), obs(20)]) == []


# --- staleness ---------------------------------------------------------------


def capture():
    return [
        marker(0, "started"),
        obs(0, item="Xload"),
        obs(0, item="exec", value="ACTIVE"),
        obs(30, item="Xload"),
        obs(100),
        obs(120),
    ]


def test_only_channels_given_a_limit_can_be_stale():
    ages = {a.data_item_id: a for a in channel_ages(capture())}
    assert ages["exec"].age_seconds == 120  # judged on the capture's own clock
    assert not any(a.stale for a in ages.values())  # no limits, nothing checked
    stale = stale_channels(capture(), {"Xload": 60, "S1load": 60})
    assert [a.data_item_id for a in stale] == ["Xload"]
    assert stale[0].age_seconds == 90
    assert not stale[0].broke_since


def test_the_check_time_can_be_given():
    stale = stale_channels(capture(), {"S1load": 60}, at=at(200))
    assert [(a.data_item_id, a.age_seconds) for a in stale] == [("S1load", 80)]


def test_silence_after_a_break_is_marked_as_possibly_the_collectors():
    lines = [obs(0, item="Xload"), obs(0), marker(50, "gap"), obs(200)]
    (age,) = stale_channels(lines, {"Xload": 60})
    assert age.broke_since


def test_an_empty_capture_has_no_ages():
    assert channel_ages([marker(0, "started")]) == []


@pytest.mark.parametrize(
    "content, problem",
    [
        ('["Xload"]', "expected an object"),
        ('{"Xload": "60"}', "not a number"),
        ('{"Xload": true}', "not a number"),
        ('{"Xload": 0}', "must be positive"),
    ],
)
def test_a_bad_limits_file_is_refused(tmp_path, content, problem):
    path = tmp_path / "limits.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=problem):
        load_limits(path)


# --- command line --------------------------------------------------------------


def test_command_line_reports_stretches_and_stale_channels(tmp_path, capsys):
    lines = [*capture(), obs(130, value=None), obs(140)]
    path = tmp_path / "capture.jsonl"
    path.write_text("".join(line.model_dump_json() + "\n" for line in lines))
    limits = tmp_path / "limits.json"
    limits.write_text(json.dumps({"Xload": 60}), encoding="utf-8")

    assert main(["--capture", str(path)]) == 0
    out = capsys.readouterr().out
    assert "1 UNAVAILABLE stretch(es)" in out
    assert "VF2/S1load: 2026-11-08T09:02:10+00:00 for 10 s (available_again)" in out

    assert main(["--capture", str(path), "--limits", str(limits)]) == 1
    assert "VF2/Xload: last report 110 s ago, limit 60 s" in capsys.readouterr().out

    limits.write_text('{"Xload": -1}', encoding="utf-8")
    assert main(["--capture", str(path), "--limits", str(limits)]) == 2
    with pytest.raises(SystemExit):
        main(["--capture", str(path), "--at", "2026-11-08T09:00:00"])
