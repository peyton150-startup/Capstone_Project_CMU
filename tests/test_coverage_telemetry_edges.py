"""Read-only telemetry CLI failure paths without network access or machine access."""

import argparse
from types import SimpleNamespace

import pytest

from capstone.ingestion import __main__ as ingestion_cli
from capstone.monitoring import __main__ as monitoring_cli


@pytest.mark.parametrize(
    "raw",
    ["invalid", "channel=5", "channel=5:", "channel=abc:5", "channel=2:1"],
)
def test_monitor_threshold_rejects_invalid_ranges(raw):
    with pytest.raises(argparse.ArgumentTypeError):
        monitoring_cli.parse_threshold(raw)


def test_monitor_threshold_accepts_floating_point_bounds():
    key, bounds = monitoring_cli.parse_threshold("LS1load=-0.5:120.5")
    assert key == "LS1load"
    assert bounds.low == -0.5
    assert bounds.high == 120.5


def test_collector_cli_saves_probe_without_polling(monkeypatch, tmp_path, capsys):
    probe = tmp_path / "probe.xml"
    created = []
    monkeypatch.setattr(ingestion_cli, "refusal", lambda *_: None)
    monkeypatch.setattr(
        ingestion_cli,
        "MTConnectCollector",
        lambda url, **kw: (
            created.append((url, kw)),
            SimpleNamespace(probe=lambda: "<Devices/>"),
        )[1],
    )
    monkeypatch.setattr(
        ingestion_cli,
        "run_collector",
        lambda *_args, **_kw: pytest.fail("probe should not start polling"),
    )
    assert (
        ingestion_cli.main(
            ["--url", "http://synthetic:8082", "--save-probe", str(probe)]
        )
        == 0
    )
    assert probe.read_text() == "<Devices/>"
    assert created == [("http://synthetic:8082", {"device": None, "count": 1000})]
    assert "saved the machine" in capsys.readouterr().out


def test_collector_cli_requires_output_in_normal_mode(monkeypatch, capsys):
    monkeypatch.setattr(
        ingestion_cli,
        "MTConnectCollector",
        lambda *a, **k: SimpleNamespace(),
    )
    with pytest.raises(SystemExit) as error:
        ingestion_cli.main(["--url", "http://synthetic"])
    assert error.value.code == 2
    assert "--out is required" in capsys.readouterr().err


@pytest.mark.parametrize("option", ["--out", "--save-probe"])
def test_collector_cli_checks_paths_before_opening_network(
    monkeypatch, tmp_path, option, capsys
):
    monkeypatch.setattr(
        ingestion_cli,
        "refusal",
        lambda path, flag: "unsafe path" if flag == option else None,
    )
    monkeypatch.setattr(
        ingestion_cli,
        "MTConnectCollector",
        lambda *a, **kw: pytest.fail("rejected output must not touch a machine"),
    )
    with pytest.raises(SystemExit) as error:
        ingestion_cli.main(
            ["--url", "http://synthetic", option, str(tmp_path / "private")]
        )
    assert error.value.code == 2
    assert "unsafe path" in capsys.readouterr().err


@pytest.mark.parametrize("interrupt", [False, True])
def test_collector_cli_reports_success_or_graceful_interrupt(
    monkeypatch, tmp_path, capsys, interrupt
):
    collector = object()
    seen = []
    monkeypatch.setattr(ingestion_cli, "refusal", lambda *_: None)
    monkeypatch.setattr(ingestion_cli, "MTConnectCollector", lambda *a, **kw: collector)

    def fake_run(obj, path, *, interval, max_polls):
        assert obj is collector
        seen.append((path, interval, max_polls))
        if interrupt:
            raise KeyboardInterrupt
        return 7

    monkeypatch.setattr(ingestion_cli, "run_collector", fake_run)
    out = tmp_path / "telemetry.jsonl"
    args = [
        "--url",
        "http://synthetic",
        "--device",
        "VMC",
        "--count",
        "4",
        "--out",
        str(out),
        "--interval",
        "2",
        "--polls",
        "3",
        "--allow-inside-repo",
    ]
    assert ingestion_cli.main(args) == 0
    assert seen == [(out, 2.0, 3)]
    captured = capsys.readouterr()
    if interrupt:
        assert "stopped" in captured.err
    else:
        assert "wrote 7 records" in captured.out


def test_monitor_cli_rejects_unsafe_alerts_before_reading(monkeypatch, tmp_path):
    monkeypatch.setattr(monitoring_cli, "refusal", lambda *_: "protected source tree")
    monkeypatch.setattr(
        monitoring_cli,
        "JsonlFollower",
        lambda *_: pytest.fail("must refuse before opening the input"),
    )
    with pytest.raises(SystemExit) as stopped:
        monitoring_cli.main(
            [
                "--input",
                str(tmp_path / "data.jsonl"),
                "--alerts",
                str(tmp_path / "unsafe.jsonl"),
            ]
        )
    assert stopped.value.code == 2


@pytest.mark.parametrize("has_alert_path", [False, True])
def test_monitor_cli_replay_is_read_only_and_passes_thresholds(
    monkeypatch, tmp_path, has_alert_path
):
    observations = [object()]
    calls = []
    monitor = object()
    monkeypatch.setattr(monitoring_cli, "refusal", lambda *_: None)
    monkeypatch.setattr(
        monitoring_cli,
        "Monitor",
        lambda **kw: (calls.append(("monitor", kw)), monitor)[1],
    )
    monkeypatch.setattr(
        monitoring_cli,
        "JsonlFollower",
        lambda path: SimpleNamespace(
            read_new=lambda: (calls.append(("read", path)), observations)[1]
        ),
    )
    monkeypatch.setattr(
        monitoring_cli,
        "replay",
        lambda records, active: (
            calls.append(("replay", records, active)),
            ["alert"],
        )[1],
    )
    monkeypatch.setattr(
        monitoring_cli,
        "append_alerts",
        lambda path, events: calls.append(("write", path, events)),
    )
    inp = tmp_path / "sensor.jsonl"
    alerts = tmp_path / "alerts.jsonl"
    args = ["--input", str(inp), "--threshold", "temperature=1:3"]
    if has_alert_path:
        args += ["--alerts", str(alerts)]
    assert monitoring_cli.main(args) == 0
    assert calls[0][1]["thresholds"]["temperature"].high == 3.0
    assert calls[1] == ("read", inp)
    assert calls[2] == ("replay", observations, monitor)
    assert calls[3] == ("write", alerts if has_alert_path else None, ["alert"])


def test_monitor_cli_follow_loop_exits_cleanly_on_interrupt(
    monkeypatch, tmp_path, capsys
):
    collected = []
    monkeypatch.setattr(monitoring_cli, "refusal", lambda *_: None)
    monkeypatch.setattr(monitoring_cli, "Monitor", lambda **kw: object())
    monkeypatch.setattr(
        monitoring_cli,
        "JsonlFollower",
        lambda _path: SimpleNamespace(read_new=lambda: ["record"]),
    )
    monkeypatch.setattr(monitoring_cli, "replay", lambda rows, m: ["alert"])
    monkeypatch.setattr(
        monitoring_cli,
        "append_alerts",
        lambda path, rows: collected.append((path, rows)),
    )
    monkeypatch.setattr(
        monitoring_cli.time,
        "sleep",
        lambda _: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    assert (
        monitoring_cli.main(
            [
                "--input",
                str(tmp_path / "telemetry.jsonl"),
                "--follow",
                "--interval",
                "0.01",
            ]
        )
        == 0
    )
    assert len(collected) == 1
    assert "stopped" in capsys.readouterr().err

def test_monitor_follow_processes_another_batch_before_interrupt(
    monkeypatch, tmp_path, capsys
):
    batches = []
    monkeypatch.setattr(monitoring_cli, "refusal", lambda *_: None)
    monkeypatch.setattr(monitoring_cli, "Monitor", lambda **kwargs: object())
    monkeypatch.setattr(
        monitoring_cli,
        "JsonlFollower",
        lambda path: SimpleNamespace(read_new=lambda: ["reading"]),
    )
    monkeypatch.setattr(
        monitoring_cli, "replay", lambda readings, monitor: ["alert"]
    )
    monkeypatch.setattr(
        monitoring_cli,
        "append_alerts",
        lambda path, alerts: batches.append((path, alerts)),
    )
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(monitoring_cli.time, "sleep", fake_sleep)
    assert monitoring_cli.main(
        [
            "--input", str(tmp_path / "readings.jsonl"),
            "--follow", "--interval", "0.01",
        ]
    ) == 0
    assert len(batches) == 2
    assert sleeps == [0.01, 0.01]
    assert "stopped" in capsys.readouterr().err
