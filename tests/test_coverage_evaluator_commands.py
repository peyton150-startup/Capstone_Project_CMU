"""Offline evaluator CLI and trace error paths.

These tests exercise file and argument contracts without model requests.
"""

import json
from types import SimpleNamespace

import pytest

from evaltools import (
    build_inventory,
    compare_evaluators,
    full_evaluation,
    run_packet,
    snap_request,
    traced_run,
)


@pytest.mark.parametrize(
    "options, message",
    [
        (["--provider", "both", "--model", "custom"], "--model needs one provider"),
        (
            ["--provider", "both", "--full-context"],
            "--full-context needs one provider",
        ),
    ],
)
def test_snap_request_cli_rejects_unmatched_model_options(
    tmp_path, capsys, options, message
):
    argv = ["--out", str(tmp_path / "requests"), *options, "functions", "--ids", "FN"]
    with pytest.raises(SystemExit) as stopped:
        snap_request.main(argv)
    assert stopped.value.code == 2
    assert message in capsys.readouterr().err


def test_snap_request_cli_refuses_unknown_function_ids(tmp_path, capsys):
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    for name, values in (
        ("FUNCTION_INVENTORY.json", {"functions": []}),
        ("TEST_INVENTORY.json", {"tests": []}),
        ("TOOL_INVENTORY.json", {"tools": []}),
    ):
        (inventory / name).write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        snap_request.main(
            [
                "--out", str(tmp_path / "requests"),
                "--inventory", str(inventory), "functions", "--ids", "missing",
            ]
        )
    assert stopped.value.code == 2
    assert "not in the inventory" in capsys.readouterr().err


def test_traced_run_refuses_records_audit_collision_before_tracing(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        traced_run,
        "start_tracer",
        lambda _: pytest.fail("must check output paths before tracing"),
    )
    path = tmp_path / "records.jsonl"
    with pytest.raises(SystemExit) as stopped:
        traced_run.main(
            ["--name", "run", "--out", str(path), "--trace",
             str(tmp_path / "trace.json"), "--audit", str(path)]
        )
    assert stopped.value.code == 2
    assert "audit and records paths must differ" in capsys.readouterr().err


def test_traced_run_refuses_nonempty_record_file_before_tracing(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        traced_run,
        "start_tracer",
        lambda _: pytest.fail("must not overwrite existing results"),
    )
    path = tmp_path / "records.jsonl"
    path.write_text("previous result\n", encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        traced_run.main(
            ["--name", "run", "--out", str(path), "--trace",
             str(tmp_path / "trace.json"), "--no-audit"]
        )
    assert stopped.value.code == 2
    assert "already has records" in capsys.readouterr().err


def test_traced_run_stops_and_saves_trace_when_episode_raises(monkeypatch):
    from capstone import experiment

    activity = []
    case = SimpleNamespace(scenario_id="failure")
    cov = SimpleNamespace(
        switch_context=lambda context: activity.append(("context", context)),
        stop=lambda: activity.append(("stop",)),
        save=lambda: activity.append(("save",)),
    )

    def failed(*args, **kwargs):
        raise RuntimeError("scripted failure")

    monkeypatch.setattr(experiment, "run_experiment", failed)
    with pytest.raises(RuntimeError, match="scripted failure"):
        traced_run.run_traced([case], lambda: None, name="test", cov=cov)
    assert activity == [
        ("context", "test/1/failure"),
        ("stop",),
        ("save",),
    ]


@pytest.mark.parametrize(
    "extra, message",
    [
        (["--labels", "labels.json"], "--archive finds each run's files itself"),
        (["--namespace", "another"], "--archive finds each run's files itself"),
    ],
)
def test_run_packet_cli_refuses_ambiguous_archive_sources(
    tmp_path, capsys, extra, message
):
    with pytest.raises(SystemExit) as stopped:
        run_packet.main(
            ["--archive", str(tmp_path / "archive"), "--out",
             str(tmp_path / "out"), *extra]
        )
    assert stopped.value.code == 2
    assert message in capsys.readouterr().err


def test_run_packet_cli_outputs_empty_batch_summary_without_model(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(run_packet, "build_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(run_packet, "batch_summary", lambda _: {"runs": 0})
    out = tmp_path / "packets"
    schema = tmp_path / "schema.json"
    assert run_packet.main(
        ["--records", str(tmp_path / "none.jsonl"), "--out", str(out),
         "--write-schema", str(schema)]
    ) == 0
    assert json.loads((out / "BATCH_SUMMARY.json").read_text()) == {
        "runs": 0, "refused": []
    }
    assert "properties" in json.loads(schema.read_text())
    assert '"runs": 0' in capsys.readouterr().out


def test_run_packet_cli_preserves_refused_packet_manifest(
    tmp_path, monkeypatch, capsys
):
    def fake_build(*args, **kwargs):
        kwargs["refused"].append({"episode_key": "bad", "reason": "truth leak"})
        return []

    monkeypatch.setattr(run_packet, "build_all", fake_build)
    monkeypatch.setattr(run_packet, "batch_summary", lambda _: {"runs": 0})
    out = tmp_path / "packets"
    assert run_packet.main(
        ["--records", str(tmp_path / "records.jsonl"), "--out", str(out)]
    ) == 0
    data = json.loads((out / "BATCH_SUMMARY.json").read_text())
    assert data["refused"] == [{"episode_key": "bad", "reason": "truth leak"}]
    assert "refused" in capsys.readouterr().err


@pytest.mark.parametrize(
    "options, message",
    [
        (["--families", "FN,NOPE"], "unknown families"),
        (["--snap-full-context"], "--snap-full-context requires --provider snap"),
        (["--send"], "--send needs --max-requests and --max-usd"),
        (["--env-file", "/fake/missing.env"], "does not exist"),
    ],
)
def test_full_evaluation_cli_refuses_invalid_or_unsafe_options(
    tmp_path, capsys, options, message
):
    with pytest.raises(SystemExit) as stopped:
        full_evaluation.main(["--out", str(tmp_path / "results"), *options])
    assert stopped.value.code == 2
    assert message in capsys.readouterr().err


def test_build_inventory_cli_prints_counts_without_building_the_world(
    monkeypatch, tmp_path, capsys
):
    recorded = []

    def fake_build(coverage, junit, out):
        recorded.append((coverage, junit, out))
        return {"counts": {"functions": [1, 2, 3], "tests": [1]}}

    monkeypatch.setattr(build_inventory, "build", fake_build)
    path = tmp_path / "inventory"
    assert build_inventory.main(["--out", str(path)]) == 0
    assert recorded == [(None, None, path)]
    assert json.loads(capsys.readouterr().out) == {
        "functions": "3 items", "tests": "1 items"
    }


def test_compare_evaluators_cli_saves_offline_agreement(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        compare_evaluators, "load_answers", lambda _: []
    )
    data = {
        "providers": [],
        "pairs_compared": 0,
        "agreement_rate": None,
        "disagreements_for_review": [],
        "caveats": [],
    }
    monkeypatch.setattr(compare_evaluators, "build_report", lambda *_: data)
    monkeypatch.setattr(compare_evaluators, "markdown", lambda _: "# review\n")
    source = tmp_path / "answers"
    source.mkdir()
    reference = tmp_path / "reference.json"
    reference.write_text("{}")
    out = tmp_path / "report"
    assert compare_evaluators.main(
        ["--answers", str(source), "--reference", str(reference),
         "--out", str(out)]
    ) == 0
    assert json.loads((out / "agreement.json").read_text()) == data
    assert (out / "agreement.md").read_text() == "# review\n"
    assert json.loads(capsys.readouterr().out)["pairs_compared"] == 0
