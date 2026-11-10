"""Guardrail drift between batches of saved runs is measured and flagged."""

import json

import pytest

from capstone.evaluation.drift import batch_rates, format_report, main, shifts
from capstone.evaluation.scoring import Score
from capstone.experiment import ExperimentRecord


def run(
    *,
    asked="intervene",
    lowered=None,
    status=(),
    confidence=0.9,
    correct=None,
    stop="diagnosis_supported",
):
    score = Score(
        true_fault="bearing",
        true_machine_id="CNC-02",
        true_batch_id=None,
        diagnosed_fault=None,
        diagnosed_machine_id=None,
        diagnosed_batch_id=None,
        fault_correct=correct,
        target_correct=correct,
        expected_action="replace_bearing",
        actions_taken=[],
        action_correct=False,
        recommendation_status=list(status),
        resolved=False,
        tool_calls=3,
        ticks_elapsed=10,
        termination_reason=stop,
    )
    return ExperimentRecord(
        run_key="r/1/x",
        scenario_id="x",
        seed=1,
        anomaly="a",
        conclusion="wear",
        confidence=confidence,
        recommendation="intervene" if lowered is None else "escalate",
        policy_recommendation=asked,
        recommendation_lowered=lowered,
        verification=None,
        tools_used=[],
        score=score,
    )


def test_rates_count_the_right_runs():
    rates = batch_rates(
        "b",
        [
            run(status=("approved",), correct=True),
            run(lowered="confidence 0.80 below 0.90", confidence=0.8, correct=False),
            run(asked="no_action", status=(), confidence=0.6, stop="timeout"),
            run(status=("rejected",), confidence=0.7, correct=True),
        ],
    )
    assert rates.runs == 4
    assert rates.intervene_rate == 0.75
    assert rates.lowered_rate == pytest.approx(1 / 3)
    assert rates.rejection_rate == 0.5
    assert rates.timeout_rate == 0.25
    assert rates.mean_confidence == pytest.approx(0.75)
    # judged: 0.9 right, 0.8 wrong, 0.7 right -> mean 0.8 minus 2/3 right
    assert rates.calibration_gap == pytest.approx(0.8 - 2 / 3)


def test_runs_with_no_model_are_left_out():
    rates = batch_rates("b", [run(), run(stop="model_unavailable", asked=None)])
    assert rates.runs == 1 and rates.intervene_rate == 1.0


def test_a_rate_with_nothing_to_count_is_none_not_zero():
    rates = batch_rates("b", [run(asked="no_action", confidence=0.5)])
    assert rates.lowered_rate is None
    assert rates.rejection_rate is None
    assert rates.calibration_gap is None


def test_only_moves_past_the_threshold_are_flagged():
    base = batch_rates("base", [run(status=("approved",))] * 4)
    later = batch_rates(
        "later", [run(status=("rejected",))] * 2 + [run(status=("approved",))] * 2
    )
    found = shifts(base, [later], 0.15)
    assert [(s.metric, s.baseline, s.now) for s in found] == [
        ("rejection_rate", 0.0, 0.5)
    ]
    assert shifts(base, [later], 0.6) == []


def test_a_rate_missing_on_one_side_is_never_flagged():
    base = batch_rates("base", [run(asked="no_action")])
    later = batch_rates("later", [run(lowered="no evidence cited")])
    assert all(s.metric != "lowered_rate" for s in shifts(base, [later], 0.0))


def test_the_report_names_each_drift():
    base = batch_rates("base", [run(status=("approved",))])
    later = batch_rates("later", [run(status=("rejected",))])
    text = format_report([base, later], shifts(base, [later], 0.15), 0.15)
    assert "DRIFT later: rejection_rate 0.00 -> 1.00 (+1.00) since base" in text
    quiet = format_report([base, base], [], 0.15)
    assert "No rate moved more than 0.15 from base." in quiet


def write(path, records):
    path.write_text("\n".join(r.model_dump_json() for r in records) + "\n")


def test_the_command_reads_files_and_exits_1_on_drift(tmp_path, capsys):
    write(tmp_path / "base.jsonl", [run(status=("approved",))] * 3)
    write(tmp_path / "later.jsonl", [run(status=("rejected",))] * 3)
    assert main([str(tmp_path / "base.jsonl"), str(tmp_path / "later.jsonl")]) == 1
    assert "DRIFT later: rejection_rate" in capsys.readouterr().out
    assert main([str(tmp_path / "base.jsonl"), str(tmp_path / "base.jsonl")]) == 0


def test_the_command_can_print_json(tmp_path, capsys):
    write(tmp_path / "a.jsonl", [run()])
    write(tmp_path / "b.jsonl", [run(lowered="no evidence cited")])
    main([str(tmp_path / "a.jsonl"), str(tmp_path / "b.jsonl"), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert [b["name"] for b in out["batches"]] == ["a", "b"]
    assert {d["metric"] for d in out["drift"]} == {"lowered_rate"}
