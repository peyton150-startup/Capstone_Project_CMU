"""The collector heartbeat and the live watchdog that notices a dead collector."""

from datetime import UTC, datetime, timedelta

from capstone.ingestion import MTConnectCollector, TelemetryRecord, run_collector
from capstone.ingestion.record import CollectorMarker, parse_line
from capstone.monitoring import Monitor, replay
from capstone.watchdog import Watchdog, last_line
from capstone.watchdog.__main__ import main

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
SOURCE = "http://agent:8082"


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def marker(event: str, seconds: float) -> CollectorMarker:
    return CollectorMarker(source=SOURCE, event=event, at=at(seconds))


def record(seconds: float) -> TelemetryRecord:
    return TelemetryRecord(
        source=SOURCE,
        instance_id="1",
        device="VF2",
        component="path",
        data_item_id="exec",
        category="EVENT",
        type="Execution",
        value="READY",
        available=True,
        sequence=int(seconds) + 1,
        source_timestamp=at(seconds),
        received_at=at(seconds),
    )


def write(path, lines, tail: str = "") -> None:
    path.write_text("".join(x.model_dump_json() + "\n" for x in lines) + tail, "utf-8")


# --- the watchdog rule ------------------------------------------------------


def test_fresh_data_raises_nothing(tmp_path):
    assert Watchdog(tmp_path / "t.jsonl").check(record(0), at(100)) == []


def test_silence_without_a_clean_stop_alerts_once_then_recovers(tmp_path):
    dog = Watchdog(tmp_path / "t.jsonl", silent_after=180)
    first = dog.check(record(0), at(181))
    assert [(a.kind, a.severity, a.live_only) for a in first] == [
        ("silent", "warning", True)
    ]
    assert first[0].last_line_at == at(0)
    assert dog.check(record(0), at(600)) == []
    back = dog.check(record(590), at(600))
    assert [(a.kind, a.message) for a in back] == [("recovered", "new lines again")]


def test_a_clean_stop_is_never_called_silent(tmp_path):
    dog = Watchdog(tmp_path / "t.jsonl", silent_after=180)
    assert dog.check(marker("stopped", 0), at(86_400)) == []


def test_a_stop_after_an_alert_closes_it(tmp_path):
    dog = Watchdog(tmp_path / "t.jsonl", silent_after=180)
    dog.check(record(0), at(300))
    closed = dog.check(marker("stopped", 310), at(320))
    assert [(a.kind, a.message) for a in closed] == [
        ("recovered", "collector stopped cleanly")
    ]


def test_heartbeats_keep_a_quiet_machine_from_looking_dead(tmp_path):
    dog = Watchdog(tmp_path / "t.jsonl", silent_after=180)
    assert dog.check(marker("heartbeat", 3_600), at(3_650)) == []


def test_an_empty_or_missing_file_raises_nothing(tmp_path):
    assert Watchdog(tmp_path / "t.jsonl").check(None, at(10_000)) == []


# --- reading the last line --------------------------------------------------


def test_last_line_skips_a_half_written_line_and_bad_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    assert last_line(path) is None
    path.write_text("", "utf-8")
    assert last_line(path) is None
    write(path, [record(0), record(5)], tail='{"record_type": "obs')
    assert last_line(path) == record(5)
    write(path, [record(0)], tail="{not json}\n")
    assert last_line(path) == record(0)


def test_command_line_reports_a_dead_collector(tmp_path):
    source, alerts = tmp_path / "t.jsonl", tmp_path / "w.jsonl"
    write(source, [marker("started", -10_000), record(-9_990)])
    assert main(["--input", str(source), "--alerts", str(alerts), "--checks", "1"]) == 0
    assert '"kind":"silent"' in alerts.read_text("utf-8")


# --- the collector heartbeat ------------------------------------------------


def quiet_agent(url: str) -> str:
    """An agent with nothing new: an empty streams document every time."""
    return (
        '<MTConnectStreams xmlns="urn:mtconnect.org:MTConnectStreams:2.8">'
        '<Header instanceId="1" nextSequence="5" firstSequence="1" lastSequence="4"/>'
        "<Streams/></MTConnectStreams>"
    )


class Clock:
    """A fake clock that moves only when the collector sleeps, like real time."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def now(self) -> datetime:
        return at(self.seconds)

    def sleep(self, seconds: float) -> None:
        self.seconds += seconds


def heartbeats(path) -> list[str]:
    lines = map(parse_line, path.read_text("utf-8").splitlines())
    return [x.event for x in lines if isinstance(x, CollectorMarker)]


def test_a_quiet_machine_gets_a_heartbeat_every_minute(tmp_path):
    out, clock = tmp_path / "t.jsonl", Clock()
    collector = MTConnectCollector(SOURCE, fetch=quiet_agent, now=clock.now)
    # 30 polls, 5 s apart: 150 s of a quiet machine, so heartbeats at 60 and 120 s.
    run_collector(collector, out, interval=5, max_polls=30, sleep=clock.sleep)
    assert heartbeats(out) == ["started", "heartbeat", "heartbeat", "stopped"]


def test_failed_polls_never_write_a_heartbeat(tmp_path, capsys):
    out, clock = tmp_path / "t.jsonl", Clock()

    def down(url: str) -> str:
        raise OSError("agent unreachable")

    collector = MTConnectCollector(SOURCE, fetch=down, now=clock.now)
    run_collector(collector, out, interval=5, max_polls=60, sleep=clock.sleep)
    assert heartbeats(out) == ["started", "stopped"]
    assert "poll failed" in capsys.readouterr().err


def test_the_monitor_counts_a_heartbeat_as_contact():
    lines = [marker("started", 0), record(1)]
    lines += [marker("heartbeat", 60 * n) for n in range(1, 11)]
    lines += [record(660)]
    alerts = replay(lines, Monitor(stale_after=180))
    assert [a.kind for a in alerts] == ["collector"]
