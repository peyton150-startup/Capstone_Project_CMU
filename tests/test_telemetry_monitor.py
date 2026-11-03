"""The deterministic monitor: each rule fires once on a change and recovers."""

from datetime import UTC, datetime, timedelta

from capstone.ingestion import TelemetryRecord
from capstone.ingestion.record import CollectorMarker
from capstone.monitoring import JsonlFollower, Monitor, Threshold, replay
from capstone.monitoring.__main__ import main

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
_sequence = iter(range(1, 10_000))


def rec(
    item: str,
    value: str | None,
    *,
    category="EVENT",
    type_="Execution",
    seconds=0.0,
    name=None,
    device="VF2",
    native_code=None,
    message=None,
) -> TelemetryRecord:
    at = T0 + timedelta(seconds=seconds)
    return TelemetryRecord(
        source="http://agent:8082",
        instance_id="1",
        device=device,
        component="c",
        data_item_id=item,
        name=name,
        category=category,
        type=type_,
        value=value,
        available=value is not None,
        native_code=native_code,
        message=message,
        sequence=next(_sequence),
        source_timestamp=at,
        received_at=at,
    )


def cond(level: str | None, **kwargs) -> TelemetryRecord:
    return rec("temp", level, category="CONDITION", type_="TEMPERATURE", **kwargs)


def kinds(alerts) -> list[tuple[str, str]]:
    return [(alert.kind, alert.severity) for alert in alerts]


def run(records, monitor=None):
    return replay(records, monitor or Monitor())


def test_condition_alerts_once_escalates_and_recovers():
    alerts = run(
        [
            cond("NORMAL"),
            cond("WARNING"),
            cond("WARNING"),
            cond("FAULT", native_code="123", message="Spindle overtemperature"),
            cond("FAULT"),
            cond("NORMAL"),
            cond("NORMAL"),
        ]
    )
    assert kinds(alerts) == [
        ("condition", "warning"),
        ("condition", "fault"),
        ("recovered", "info"),
    ]
    assert alerts[1].message == "Spindle overtemperature [123]"


def test_unavailable_from_the_start_is_not_an_alert():
    assert run([rec("load", None, category="SAMPLE", type_="Load")]) == []


def test_channel_going_unavailable_alerts_and_recovers():
    alerts = run(
        [
            rec("exec", "ACTIVE"),
            rec("exec", None),
            rec("exec", None),
            rec("exec", "ACTIVE"),
        ]
    )
    assert kinds(alerts) == [("unavailable", "warning"), ("recovered", "info")]


def test_status_changes_are_reported_but_not_the_first_value():
    alerts = run([rec("exec", "READY"), rec("exec", "READY"), rec("exec", "ACTIVE")])
    assert kinds(alerts) == [("status_change", "info")]
    assert alerts[0].message == "Execution: READY -> ACTIVE"


def test_emergency_stop_triggered_is_a_fault():
    alerts = run(
        [
            rec("estop", "ARMED", type_="EmergencyStop"),
            rec("estop", "TRIGGERED", type_="EmergencyStop"),
        ]
    )
    assert kinds(alerts) == [("status_change", "fault")]


def test_threshold_by_id_or_name_fires_once_and_recovers():
    monitor = Monitor(thresholds={"S1load": Threshold(0, 100)})
    load = dict(category="SAMPLE", type_="Load", name="S1load")
    alerts = run(
        [
            rec("x1", "50", **load),
            rec("x1", "130", **load),
            rec("x1", "140", **load),
            rec("x1", "90", **load),
        ],
        monitor,
    )
    assert kinds(alerts) == [("threshold", "warning"), ("recovered", "info")]
    assert alerts[0].message == "Load 130 outside [0, 100]"


def test_silence_in_a_recording_is_found_without_the_wall_clock():
    alerts = run(
        [rec("exec", "ACTIVE"), rec("exec", "ACTIVE", seconds=120)],
        Monitor(stale_after=60),
    )
    assert kinds(alerts) == [("stale", "warning"), ("recovered", "info")]
    assert alerts[0].data_item_id is None


def test_stale_is_reported_once_per_silence():
    monitor = Monitor(stale_after=60)
    monitor.observe(rec("exec", "ACTIVE"))
    assert monitor.check_stale(T0 + timedelta(seconds=30)) == []
    assert len(monitor.check_stale(T0 + timedelta(seconds=61))) == 1
    assert monitor.check_stale(T0 + timedelta(seconds=90)) == []


def test_replay_is_deterministic():
    records = [
        rec("exec", "READY"),
        rec("exec", "ACTIVE"),
        cond("FAULT"),
        cond("NORMAL"),
    ]
    assert run(records) == run(records)


def test_follower_reads_only_complete_lines_and_skips_bad_ones(tmp_path, capsys):
    path = tmp_path / "telemetry.jsonl"
    first, second = rec("exec", "READY"), rec("exec", "ACTIVE")
    line = second.model_dump_json()
    path.write_text(first.model_dump_json() + "\n{bad}\n" + line[:20], encoding="utf-8")
    follower = JsonlFollower(path)
    assert follower.read_new() == [first]
    with path.open("a", encoding="utf-8") as sink:
        sink.write(line[20:] + "\n")
    assert follower.read_new() == [second]
    assert "skipped unreadable line" in capsys.readouterr().err


def test_command_line_replay_writes_alerts(tmp_path):
    source, alerts = tmp_path / "telemetry.jsonl", tmp_path / "alerts.jsonl"
    source.write_text(
        "".join(
            r.model_dump_json() + "\n"
            for r in [rec("exec", "READY"), rec("exec", "ACTIVE")]
        ),
        encoding="utf-8",
    )
    assert main(["--input", str(source), "--alerts", str(alerts)]) == 0
    assert '"kind":"status_change"' in alerts.read_text(encoding="utf-8")


def test_following_a_file_in_pieces_gives_the_same_alerts_as_replaying_it(tmp_path):
    records = [
        rec("exec", "READY"),
        rec("exec", "ACTIVE", seconds=5),
        cond("FAULT", seconds=6),
        rec("exec", "ACTIVE", seconds=200),
        cond("NORMAL", seconds=201),
    ]
    whole = run(records, Monitor(stale_after=60))
    path = tmp_path / "telemetry.jsonl"
    follower, monitor, pieces = JsonlFollower(path), Monitor(stale_after=60), []
    for record in records:
        with path.open("a", encoding="utf-8") as sink:
            sink.write(record.model_dump_json() + "\n")
        pieces += replay(follower.read_new(), monitor)
    assert pieces == whole
    assert [a.kind for a in whole] == [
        "status_change",
        "condition",
        "stale",
        "recovered",
        "recovered",
    ]


def test_monitoring_is_plain_code_with_no_model_clock_or_network():
    """The monitor never calls a model or the agent, and never reads a clock."""
    import ast
    from pathlib import Path

    import capstone.monitoring as package

    forbidden_modules = (
        "capstone.agent",
        "capstone.providers",
        "urllib",
        "socket",
        "http",
        "random",
    )
    forbidden_calls = {"now", "utcnow", "today", "time", "monotonic", "perf_counter"}
    for source in Path(package.__file__).parent.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [alias.name for alias in node.names]
                )
                for name in names:
                    assert not name.startswith(forbidden_modules), (source.name, name)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls, (
                    source.name,
                    node.func.attr,
                )


def marker(event: str, seconds: float, reason=None) -> CollectorMarker:
    return CollectorMarker(
        source="http://agent:8082",
        event=event,
        at=T0 + timedelta(seconds=seconds),
        reason=reason,
    )


def test_a_clean_stop_and_later_start_is_not_stale():
    alerts = run(
        [
            marker("started", 0),
            rec("exec", "ACTIVE", seconds=1),
            marker("stopped", 2, "interrupted"),
            marker("started", 3600),
            rec("exec", "ACTIVE", seconds=3601),
        ],
        Monitor(stale_after=60),
    )
    assert [(a.kind, a.severity, a.message) for a in alerts] == [
        ("collector", "info", "collector started"),
        ("collector", "info", "collector stopped (interrupted)"),
        ("collector", "info", "collector started"),
    ]


def test_a_start_without_a_clean_stop_warns_of_a_crash():
    alerts = run(
        [
            marker("started", 0),
            rec("exec", "ACTIVE", seconds=1),
            marker("started", 600),
            rec("exec", "ACTIVE", seconds=601),
        ],
        Monitor(stale_after=60),
    )
    assert kinds(alerts) == [
        ("collector", "info"),
        ("stale", "warning"),
        ("collector", "warning"),
        ("recovered", "info"),
    ]
    assert "may have crashed" in alerts[2].message


def test_data_without_a_start_marker_counts_as_a_running_collector():
    alerts = run(
        [rec("exec", "ACTIVE"), marker("started", 10)], Monitor(stale_after=60)
    )
    assert kinds(alerts) == [("collector", "warning")]


def test_follower_reads_markers_and_observations(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    lines = [marker("started", 0), rec("exec", "READY"), marker("stopped", 5)]
    text = "".join(x.model_dump_json() + "\n" for x in lines)
    path.write_text(text, encoding="utf-8")
    assert JsonlFollower(path).read_new() == lines
