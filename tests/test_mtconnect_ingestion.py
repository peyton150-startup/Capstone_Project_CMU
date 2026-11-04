"""The read-only MTConnect collector: parsing, sequence tracking and recovery.

Fixtures copy the shape of a live MTConnect 2.8 agent (demo.mtconnect.org);
the machine and values are synthetic. No test touches the network.
"""

import io
import json
import urllib.error
from datetime import UTC, datetime

import pytest

from capstone.ingestion import (
    MTConnectCollector,
    MTConnectError,
    TelemetryRecord,
    parse_streams,
    run_collector,
)
from capstone.ingestion import collector as collector_module
from capstone.ingestion.record import CollectorMarker, parse_line

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
NS2 = "urn:mtconnect.org:MTConnectStreams:2.8"
NS1 = "urn:mtconnect.org:MTConnectStreams:1.3"


def streams(
    body: str,
    *,
    ns: str = NS2,
    instance: str = "100",
    nxt: int = 50,
    first: int = 1,
    last: int = 49,
) -> str:
    """An MTConnectStreams document around the given ComponentStream body."""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><MTConnectStreams xmlns="{ns}">'
        f'<Header instanceId="{instance}" nextSequence="{nxt}" firstSequence="{first}" '
        f'lastSequence="{last}" bufferSize="131072"/><Streams>'
        f'<DeviceStream name="VF2" uuid="haas-vf2">{body}</DeviceStream>'
        f"</Streams></MTConnectStreams>"
    )


SPINDLE = (
    '<ComponentStream component="Rotary" name="S1" componentId="s1"><Samples>'
    '<RotaryVelocity dataItemId="S1speed" name="S1speed" subType="ACTUAL" sequence="12" '
    'timestamp="2026-11-03T11:59:58.1Z">1200</RotaryVelocity>'
    '<Load dataItemId="S1load" sequence="11" timestamp="2026-11-03T11:59:58Z">UNAVAILABLE</Load>'
    "</Samples><Condition>"
    '<Fault dataItemId="S1temp" type="TEMPERATURE" nativeCode="123" sequence="13" '
    'timestamp="2026-11-03T11:59:59Z">Spindle overtemperature</Fault>'
    '<Unavailable dataItemId="S1load_cond" type="LOAD" sequence="3" '
    'timestamp="2026-11-03T10:00:00Z"/>'
    "</Condition></ComponentStream>"
    '<ComponentStream component="Path" name="path" componentId="p1"><Events>'
    '<Execution dataItemId="exec" sequence="10" timestamp="2026-11-03T11:59:57Z">ACTIVE</Execution>'
    '<VariableDataSet dataItemId="vars" sequence="14" timestamp="2026-11-03T11:59:59Z">'
    '<Entry key="b">2</Entry><Entry key="a">1</Entry></VariableDataSet>'
    "</Events></ComponentStream>"
)

OUT_OF_RANGE_2X = (
    '<MTConnectError xmlns="urn:mtconnect.org:MTConnectError:2.8"><Header instanceId="100"/>'
    "<Errors><OutOfRange errorCode=\"OUT_OF_RANGE\"><ErrorMessage>'from' must be greater than 5"
    "</ErrorMessage></OutOfRange></Errors></MTConnectError>"
)
OUT_OF_RANGE_1X = (
    '<MTConnectError xmlns="urn:mtconnect.org:MTConnectError:1.3"><Header instanceId="100"/>'
    '<Errors><Error errorCode="OUT_OF_RANGE">too old</Error></Errors></MTConnectError>'
)


def parse(xml: str):
    return parse_streams(xml, source="http://agent:8082", received_at=NOW)


def by_id(records: list[TelemetryRecord]) -> dict[str, TelemetryRecord]:
    return {record.data_item_id: record for record in records}


class FakeAgent:
    """Answers URLs from a queue and remembers every URL requested."""

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, url: str) -> str:
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


# --- parsing ---------------------------------------------------------------


def test_parse_reads_header_and_sorts_records_by_sequence():
    document = parse(streams(SPINDLE))
    assert (document.instance_id, document.next_sequence, document.first_sequence) == (
        "100",
        50,
        1,
    )
    assert document.last_sequence == 49
    assert [r.sequence for r in document.records] == [3, 10, 11, 12, 13, 14]


def test_parse_maps_samples_events_and_conditions():
    records = by_id(parse(streams(SPINDLE)).records)
    speed = records["S1speed"]
    assert (speed.category, speed.type, speed.sub_type, speed.value) == (
        "SAMPLE",
        "RotaryVelocity",
        "ACTUAL",
        "1200",
    )
    assert speed.number() == 1200.0
    assert (speed.device, speed.component, speed.received_at) == ("VF2", "S1", NOW)
    assert records["exec"].category == "EVENT" and records["exec"].value == "ACTIVE"
    fault = records["S1temp"]
    assert (fault.category, fault.type, fault.value) == (
        "CONDITION",
        "TEMPERATURE",
        "FAULT",
    )
    assert (fault.native_code, fault.message) == ("123", "Spindle overtemperature")


def test_unavailable_stays_missing_and_is_never_zero():
    records = by_id(parse(streams(SPINDLE)).records)
    for item in ("S1load", "S1load_cond"):
        assert records[item].available is False
        assert records[item].value is None
        assert records[item].number() is None


def test_dataset_entries_are_stored_as_sorted_json():
    records = by_id(parse(streams(SPINDLE)).records)
    assert json.loads(records["vars"].value) == {"a": "1", "b": "2"}


def test_older_schema_namespace_parses_the_same():
    assert parse(streams(SPINDLE, ns=NS1)).records == parse(streams(SPINDLE)).records


@pytest.mark.parametrize("xml", [OUT_OF_RANGE_2X, OUT_OF_RANGE_1X])
def test_error_documents_raise_with_their_codes(xml):
    with pytest.raises(MTConnectError) as raised:
        parse(xml)
    assert raised.value.codes == ["OUT_OF_RANGE"]


def test_records_round_trip_through_json():
    for record in parse(streams(SPINDLE)).records:
        assert TelemetryRecord.model_validate_json(record.model_dump_json()) == record


# --- the collector's request order and recovery ----------------------------


def collector(agent: FakeAgent, **kwargs) -> MTConnectCollector:
    return MTConnectCollector(
        "http://agent:8082/", fetch=agent, now=lambda: NOW, **kwargs
    )


def test_first_poll_reads_current_then_samples_from_next_sequence():
    agent = FakeAgent(streams(SPINDLE, nxt=15, last=14), streams("", nxt=15, last=14))
    c = collector(agent, count=100)
    assert len(c.poll().records) == 6
    c.poll()
    assert agent.urls == [
        "http://agent:8082/current",
        "http://agent:8082/sample?from=15&count=100",
    ]


def test_device_scopes_every_request():
    agent = FakeAgent(streams("", nxt=1, last=0))
    c = collector(agent, device="VF2")
    c.poll()
    assert agent.urls == ["http://agent:8082/VF2/current"]


def test_sample_drops_records_already_seen():
    agent = FakeAgent(
        streams(SPINDLE, nxt=12, last=11), streams(SPINDLE, nxt=15, last=14)
    )
    c = collector(agent)
    c.poll()
    second = c.poll()
    assert [r.sequence for r in second.records] == [12, 13, 14]
    assert second.gap is False


def test_out_of_range_reports_a_gap_and_restarts_from_current():
    agent = FakeAgent(
        streams("", nxt=5, last=4), OUT_OF_RANGE_2X, streams("", nxt=900, last=899)
    )
    c = collector(agent)
    c.poll()
    result = c.poll()
    assert result.gap is True and result.records == []
    c.poll()
    assert agent.urls[-1] == "http://agent:8082/current"


def test_buffer_overrun_is_reported_as_a_gap():
    agent = FakeAgent(
        streams("", nxt=5, last=4), streams("", nxt=30, first=20, last=29)
    )
    c = collector(agent)
    c.poll()
    assert c.poll().gap is True


def test_agent_restart_discards_old_sequences_and_restarts():
    agent = FakeAgent(
        streams("", instance="100", nxt=500, last=499),
        streams(SPINDLE, instance="200", nxt=15, last=14),
        streams(SPINDLE, instance="200", nxt=15, last=14),
    )
    c = collector(agent)
    c.poll()
    result = c.poll()
    assert result.gap is True and result.records == []
    assert len(c.poll().records) == 6
    assert agent.urls[-1] == "http://agent:8082/current"


def test_more_waiting_when_the_agent_holds_more_than_one_request():
    agent = FakeAgent(streams("", nxt=5, last=4), streams("", nxt=10, last=40))
    c = collector(agent, count=5)
    c.poll()
    assert c.poll().more_waiting is True


# --- running, writing and the read-only HTTP layer -------------------------


def test_run_collector_writes_jsonl_and_survives_failures(tmp_path):
    out = tmp_path / "telemetry.jsonl"
    agent = FakeAgent(
        OSError("connection refused"),
        streams(SPINDLE, nxt=15, last=14),
        "<not xml",
        streams("", nxt=15, last=14),
    )
    log = io.StringIO()
    sleeps: list[float] = []
    written = run_collector(
        collector(agent), out, interval=2, max_polls=4, sleep=sleeps.append, log=log
    )
    assert written == 6
    lines = [parse_line(t) for t in out.read_text(encoding="utf-8").splitlines()]
    assert [line.sequence for line in lines[1:-1]] == [3, 10, 11, 12, 13, 14]
    assert (lines[0].event, lines[-1].event) == ("started", "stopped")
    assert lines[-1].reason == "poll limit reached"
    assert log.getvalue().count("poll failed") == 2
    assert sleeps == [2, 2, 2, 2]


def test_run_collector_refuses_to_poll_faster_than_the_minimum(tmp_path):
    with pytest.raises(ValueError):
        run_collector(
            collector(FakeAgent()), tmp_path / "x.jsonl", interval=0.1, max_polls=1
        )


def test_http_get_sends_only_get_and_reads_error_bodies(monkeypatch):
    seen = []

    def fake_urlopen(request, timeout):
        seen.append(request.get_method())
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            {},
            io.BytesIO(OUT_OF_RANGE_2X.encode()),
        )

    monkeypatch.setattr(collector_module.urllib.request, "urlopen", fake_urlopen)
    assert "OUT_OF_RANGE" in collector_module.http_get(
        "http://agent:8082/sample?from=1"
    )
    assert seen == ["GET"]


# --- start and stop markers ------------------------------------------------


class Interrupting(FakeAgent):
    """An agent whose second request is interrupted by Ctrl+C."""

    def __call__(self, url: str) -> str:
        if self.urls:
            raise KeyboardInterrupt
        return super().__call__(url)


def markers(path) -> list[CollectorMarker]:
    lines = [parse_line(t) for t in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if isinstance(line, CollectorMarker)]


def test_ctrl_c_writes_a_clean_stop_and_keeps_the_count(tmp_path):
    out = tmp_path / "telemetry.jsonl"
    agent = Interrupting(streams(SPINDLE, nxt=15, last=14))
    written = run_collector(collector(agent), out, interval=1, sleep=lambda _: None)
    assert written == 6
    assert [(m.event, m.reason) for m in markers(out)] == [
        ("started", None),
        ("stopped", "interrupted"),
    ]
    assert markers(out)[0].source == "http://agent:8082"


def test_a_crash_writes_no_stop_marker(tmp_path):
    out = tmp_path / "telemetry.jsonl"
    agent = FakeAgent(RuntimeError("bug in the collector"))
    with pytest.raises(RuntimeError):
        run_collector(collector(agent), out, interval=1, sleep=lambda _: None)
    assert [m.event for m in markers(out)] == ["started"]


def test_lines_written_before_markers_existed_still_read_as_observations():
    record = parse(streams(SPINDLE)).records[0]
    old_line = json.loads(record.model_dump_json())
    del old_line["record_type"]
    assert parse_line(json.dumps(old_line)) == record


# --- keeping shop telemetry out of git checkouts ----------------------------


def test_a_checkout_is_found_from_a_git_folder_or_a_worktree_git_file(tmp_path):
    from capstone.ingestion.privacy import git_checkout_containing

    normal, worktree = tmp_path / "normal", tmp_path / "worktree"
    (normal / ".git").mkdir(parents=True)
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    assert git_checkout_containing(normal / "data" / "t.jsonl") == normal.resolve()
    assert git_checkout_containing(worktree / "t.jsonl") == worktree.resolve()


def test_a_path_outside_every_checkout_is_allowed():
    import tempfile
    from pathlib import Path

    from capstone.ingestion.privacy import git_checkout_containing, refusal

    outside = Path(tempfile.mkdtemp()) / "telemetry.jsonl"
    if git_checkout_containing(outside) is not None:
        pytest.skip("the system temp folder is inside a git checkout here")
    assert refusal(outside, "--out") is None


@pytest.mark.parametrize("option", ["--out", "--save-probe"])
def test_the_collector_refuses_to_write_inside_the_repository(tmp_path, capsys, option):
    from capstone.ingestion.__main__ import main

    # pytest's scratch folder sits inside this checkout (--basetemp=.pytest-tmp).
    with pytest.raises(SystemExit) as stop:
        main(["--url", "http://agent:8082", option, str(tmp_path / "t.jsonl")])
    assert stop.value.code == 2
    assert "inside the git checkout" in capsys.readouterr().err
    assert not (tmp_path / "t.jsonl").exists()


@pytest.mark.parametrize("package", ["capstone.monitoring", "capstone.watchdog"])
def test_monitor_and_watchdog_refuse_alerts_inside_the_repository(
    tmp_path, capsys, package
):
    import importlib

    main = importlib.import_module(f"{package}.__main__").main
    source = tmp_path / "t.jsonl"
    source.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        main(["--input", str(source), "--alerts", str(tmp_path / "a.jsonl")])
    assert stop.value.code == 2
    assert "inside the git checkout" in capsys.readouterr().err
