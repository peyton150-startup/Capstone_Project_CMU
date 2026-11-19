"""The calibrated detector, wired to recorded captures (synthetic data only).

No network, controller, model or shop data: the probe and captures are the
synthetic VF2 fixtures used by the other replay tests.
"""

import json
from datetime import timedelta

import pytest

import capstone.recorded_investigation as recorded
from capstone.ingestion.haas_screen import load_baselines, screen_capture
from capstone.ingestion.real_detector import CalibratedSignalBaseline
from tests.test_channel_map import probe
from tests.test_replay_provider import T0, channel_map, obs

APPROVED = frozenset({"S1load"})


def baseline(**changes):
    values = {
        "calibration_id": "vf2-load-fault-free-v1",
        "machine_id": "VF2",
        "data_item_id": "S1load",
        "unit": "PERCENT",
        "mapping_revision": channel_map().probe_sha256,
        "median": 20.0,
        "robust_spread": 4.0,
        "score_threshold": 3.0,
        "min_samples": 5,
        "min_span_seconds": 30,
    }
    return CalibratedSignalBaseline(**{**values, **changes})


def running(load: float = 20.0, *, state: str = "ACTIVE", seconds=range(0, 100, 10)):
    """The machine in one Execution state, with spindle load every 10 s."""
    return [obs(0, "exec", state, type_="Execution")] + [
        obs(second, "S1load", str(load)) for second in seconds
    ]


def screen(lines, *, baselines=None, cutoff=None, **options):
    return screen_capture(
        lines,
        channel_map(),
        baselines or [baseline()],
        authorized_item_ids=options.pop("authorized", APPROVED),
        cutoff=cutoff or T0 + timedelta(seconds=100),
        **options,
    )


# --- scoring -------------------------------------------------------------------


def test_a_running_signal_far_from_its_baseline_triggers_an_investigation():
    report = screen(running(40))
    (only,) = report.screens
    assert only.operating_state == "running"
    assert only.window.status == "scored" and only.window.robust_score == 5
    trigger = report.trigger
    assert trigger.machine_id == "VF2" and trigger.data_item_id == "S1load"
    assert trigger.sample_count == 10
    assert (trigger.first_sequence, trigger.last_sequence) == (1, 91)
    assert trigger.window_start == T0 and trigger.window_end == T0 + timedelta(
        seconds=90
    )
    assert "not a diagnosis" in trigger.description()


def test_normal_running_readings_are_scored_and_trigger_nothing():
    report = screen(running(21))
    assert report.screens[0].window.status == "scored"
    assert report.trigger is None


def test_a_stopped_or_ready_machine_is_not_scored():
    report = screen(running(40, state="READY"))
    assert report.screens[0].operating_state == "not_running"
    assert report.screens[0].window.reason == "not_running"
    assert report.trigger is None


def test_a_machine_that_stops_inside_the_window_is_not_scored():
    lines = running(40) + [obs(50, "exec", "STOPPED", type_="Execution")]
    assert screen(lines).screens[0].operating_state == "not_running"
    assert screen(lines).trigger is None


def test_without_an_execution_value_the_state_is_unknown_and_nothing_triggers():
    lines = [obs(second, "S1load", "40") for second in range(0, 100, 10)]
    report = screen(lines)
    assert report.screens[0].window.reason == "operating_state_unknown"
    assert report.trigger is None


# --- qualification and windowing ------------------------------------------------


def test_refused_samples_are_counted_by_reason_and_never_scored():
    lines = running(40) + [obs(95, "S1load", None), obs(96, "S1load", "nan")]
    only = screen(lines).screens[0]
    assert only.rejected == {"unavailable": 1, "nonfinite": 1}
    assert only.window.sample_count == 10


def test_a_restart_repeat_of_the_same_observation_is_counted_once():
    lines = running(40)
    lines.append(lines[-1].model_copy())  # /current repeats the last sample
    only = screen(lines).screens[0]
    assert only.duplicates_dropped == 1
    assert only.window.sample_count == 10


def test_only_the_newest_source_epoch_is_scored():
    older = [
        obs(second, "S1load", "90").model_copy(update={"instance_id": "0"})
        for second in (1, 2, 3)
    ]
    only = screen(older + running(21)).screens[0]
    assert only.older_epoch_dropped == 3
    assert only.window.sample_count == 10
    assert screen(older + running(21)).trigger is None  # the old 90s are not used


def test_nothing_after_the_cutoff_is_read():
    lines = running(21) + [obs(second, "S1load", "90") for second in (200, 210)]
    assert screen(lines).screens[0].window.sample_count == 10


def test_the_window_keeps_only_samples_shortly_before_the_cutoff():
    report = screen(running(40), window_seconds=55)
    assert report.screens[0].window.sample_count == 5  # 50 s to 90 s
    assert report.trigger.first_sequence == 51


def test_too_few_samples_in_the_window_cannot_trigger():
    report = screen(running(40), window_seconds=15)
    assert report.screens[0].window.reason == "too_few_samples"
    assert report.trigger is None


def test_the_strongest_of_several_flagged_signals_is_the_trigger():
    speed = baseline(
        calibration_id="vf2-speed-v1",
        data_item_id="S1speed",
        unit="REVOLUTION/MINUTE",
        median=1000.0,
        robust_spread=10.0,
    )
    lines = running(40) + [
        obs(second, "S1speed", "1100", type_="RotaryVelocity")
        for second in range(0, 100, 10)
    ]
    report = screen(
        lines,
        baselines=[baseline(), speed],
        authorized=frozenset({"S1load", "S1speed"}),
    )
    assert [s.window.threshold_exceeded for s in report.screens] == [True, True]
    assert report.trigger.data_item_id == "S1speed"  # score 10 beats 5


# --- refusals ------------------------------------------------------------------


def test_a_baseline_for_an_unauthorized_item_is_refused():
    with pytest.raises(ValueError, match="not authorized"):
        screen(running(40), authorized=frozenset({"Xpos"}))


def test_a_naive_cutoff_or_bad_window_is_refused():
    with pytest.raises(ValueError, match="UTC offset"):
        screen(running(40), cutoff=T0.replace(tzinfo=None))
    with pytest.raises(ValueError, match="positive"):
        screen(running(40), window_seconds=0)


def test_baselines_for_another_probe_or_twice_for_one_signal_are_refused(tmp_path):
    path = tmp_path / "baselines.json"
    path.write_text(json.dumps([baseline().model_dump()]), encoding="utf-8")
    assert load_baselines(path, channel_map())[0].calibration_id == (
        "vf2-load-fault-free-v1"
    )
    path.write_text(
        json.dumps([baseline(mapping_revision="b" * 64).model_dump()]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different probe"):
        load_baselines(path, channel_map())
    twice = [baseline().model_dump(), baseline(calibration_id="v2").model_dump()]
    path.write_text(json.dumps(twice), encoding="utf-8")
    with pytest.raises(ValueError, match="two baselines"):
        load_baselines(path, channel_map())
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="nonempty"):
        load_baselines(path, channel_map())


# --- the command line ----------------------------------------------------------


def write_sources(tmp_path, lines):
    """The capture, channel map, probe and baseline files the CLI reads."""
    paths = {
        name: tmp_path / name
        for name in ("capture.jsonl", "map.json", "probe.xml", "baselines.json")
    }
    paths["capture.jsonl"].write_text(
        "".join(line.model_dump_json() + "\n" for line in lines), encoding="utf-8"
    )
    paths["map.json"].write_text(channel_map().model_dump_json(), encoding="utf-8")
    paths["probe.xml"].write_text(probe(), encoding="utf-8")
    paths["baselines.json"].write_text(
        json.dumps([baseline().model_dump()]), encoding="utf-8"
    )
    return paths


@pytest.fixture(autouse=True)
def synthetic_outputs_may_sit_in_the_checkout(monkeypatch):
    # pytest's temporary folder is inside the repository, which the CLI's
    # privacy guard refuses; these files are synthetic, so allow them here.
    monkeypatch.setattr(recorded, "refusal", lambda path, flag: None)


def cli(tmp_path, paths, *extra):
    return recorded.main(
        [
            "--capture",
            str(paths["capture.jsonl"]),
            "--channel-map",
            str(paths["map.json"]),
            "--probe",
            str(paths["probe.xml"]),
            "--baseline",
            str(paths["baselines.json"]),
            "--authorized-item-id",
            "S1load",
            "--screen-out",
            str(tmp_path / "screen.json"),
            "--out",
            str(tmp_path / "review.json"),
            "--approved-remote-model",
            *extra,
        ]
    )


def test_cli_with_no_flagged_signal_writes_the_report_and_calls_no_model(
    tmp_path, monkeypatch, capsys
):
    def no_model(*args, **kwargs):
        pytest.fail("no model may be built when the detector flags nothing")

    monkeypatch.setattr(recorded, "clients_for_jobs", no_model)
    monkeypatch.setattr(recorded, "run_recorded_investigation", no_model)
    paths = write_sources(tmp_path, running(21))
    assert cli(tmp_path, paths) == 0
    report = json.loads((tmp_path / "screen.json").read_text(encoding="utf-8"))
    assert report["trigger"] is None
    assert report["screens"][0]["window"]["status"] == "scored"
    assert not (tmp_path / "review.json").exists()
    assert "no investigation started" in capsys.readouterr().out


def test_cli_with_a_flagged_signal_investigates_that_machine(tmp_path, monkeypatch):
    started = {}

    class Stub:
        conclusion = None

        def model_dump_json(self, **kwargs):
            return "{}"

    def investigate(lines, channel_map, policy, **kwargs):
        started.update(kwargs)
        return Stub()

    class NoModel:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(recorded, "clients_for_jobs", lambda: {})
    monkeypatch.setattr(recorded, "late_clients", lambda: {})
    monkeypatch.setattr(recorded, "triage_clients", lambda: {})
    monkeypatch.setattr("capstone.agent.model_policy.ModelPolicy", NoModel)
    monkeypatch.setattr(recorded, "run_recorded_investigation", investigate)
    paths = write_sources(tmp_path, running(40))
    assert cli(tmp_path, paths) == 0
    assert started["machine_id"] == "VF2"
    assert "Calibrated detector flagged S1load on VF2" in started["description"]
    report = json.loads((tmp_path / "screen.json").read_text(encoding="utf-8"))
    assert report["trigger"]["calibration_id"] == "vf2-load-fault-free-v1"
    assert (tmp_path / "review.json").exists()


@pytest.mark.parametrize(
    "extra, message",
    [
        (["--machine", "VF2"], "trigger names the machine"),
        (["--description", "look"], "trigger names the machine"),
    ],
)
def test_cli_refuses_a_machine_or_description_with_a_baseline(
    tmp_path, capsys, extra, message
):
    paths = write_sources(tmp_path, running(40))
    with pytest.raises(SystemExit):
        cli(tmp_path, paths, *extra)
    assert message in capsys.readouterr().err


def test_cli_without_a_baseline_still_needs_machine_and_description(capsys):
    with pytest.raises(SystemExit):
        recorded.main(
            [
                "--capture",
                "c.jsonl",
                "--channel-map",
                "m.json",
                "--probe",
                "p.xml",
                "--out",
                "r.json",
                "--approved-remote-model",
            ]
        )
    assert "--machine and --description are required" in capsys.readouterr().err
