"""The eval harness uses the existing episode and scoring boundaries."""

import json
from pathlib import Path

import pytest

from capstone.evals import (
    ScenarioConfig,
    compare_reports,
    load_scenarios,
    report_of,
    run_cases,
)
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.evaluation.labels import Label
from capstone.experiment import Case
from capstone.tools.diagnosis import Diagnosis
from tests.test_experiment import BEARING
from tests.test_known_answers import stand_in


def test_scenario_file_has_forced_faults_and_unique_ids(tmp_path):
    path = tmp_path / "scenarios.json"
    path.write_text(
        json.dumps(
            {"cases": [{"id": "bearing", "seed": 6, "fault": "bearing_degradation"}]}
        ),
        encoding="utf-8",
    )
    assert load_scenarios(path).cases[0].as_case().fault == "bearing_degradation"
    with pytest.raises(ValueError, match="unique"):
        ScenarioConfig.model_validate(
            {
                "cases": [
                    {"id": "same", "seed": 6, "fault": "bearing_degradation"},
                    {"id": "same", "seed": 7, "fault": "wrong_setting"},
                ]
            }
        )


def test_master_config_covers_all_known_answer_cases():
    config = load_scenarios(Path("evals/scenarios.json"))
    assert [case.as_case() for case in config.cases] == [
        Case(case.scenario_id, case.seed, case.fault, case.kind) for case in KNOWN_CASES
    ]


def test_full_episode_report_keeps_truth_out_of_policy_and_scores_only_labels():
    config = ScenarioConfig.model_validate(
        {
            "cases": [
                {"id": BEARING.scenario_id, "seed": 6, "fault": "bearing_degradation"}
            ]
        }
    )
    (record,) = run_cases(config, name="eval-test", make_policy=stand_in)
    assert record.score.true_fault == "bearing_degradation"
    assert record.score.fault_correct is None
    assert record.agent_steps
    assert {step.agent for step in record.agent_steps} == {"research_agent"}
    unjudged = report_of("eval-test", [record], {})
    assert unjudged.overall_accuracy is None
    assert unjudged.accuracy_by_fault == {"bearing_degradation": None}
    label = Label(
        run_key=record.run_key,
        diagnosis=Diagnosis(fault="bearing_degradation", machine_id="CNC-02"),
        labelled_by="test",
    )
    judged = report_of("eval-test", [record], {record.run_key: label})
    assert judged.overall_accuracy == 1.0
    assert judged.accuracy_by_fault == {"bearing_degradation": 1.0}
    assert judged.cases[0].tool_calls == record.score.tool_calls
    assert judged.cases[0].agent_steps == record.agent_steps


def test_review_flag_excludes_provisional_label_from_accuracy():
    config = ScenarioConfig.model_validate(
        {
            "cases": [
                {"id": BEARING.scenario_id, "seed": 6, "fault": "bearing_degradation"}
            ]
        }
    )
    (record,) = run_cases(config, name="review-test", make_policy=stand_in)
    label = Label(
        run_key=record.run_key,
        diagnosis=Diagnosis(fault="bearing_degradation", machine_id="CNC-02"),
        labelled_by="provisional",
    )
    report = report_of(
        "review-test", [record], {record.run_key: label}, needs_review={record.run_key}
    )
    assert report.judged == 0
    assert report.cases[0].label_needs_review
    assert report.cases[0].correct is None


def test_comparison_requires_same_cases_and_preserves_unknown_accuracy():
    config = ScenarioConfig.model_validate(
        {
            "cases": [
                {"id": BEARING.scenario_id, "seed": 6, "fault": "bearing_degradation"}
            ]
        }
    )
    (record,) = run_cases(config, name="comparison-test", make_policy=stand_in)
    before = report_of("before", [record], {})
    label = Label(
        run_key=record.run_key,
        diagnosis=Diagnosis(fault="bearing_degradation", machine_id="CNC-02"),
        labelled_by="test",
    )
    after = report_of("after", [record], {record.run_key: label})
    comparison = compare_reports(before, after)
    assert comparison.accuracy_change is None
    assert comparison.average_tool_calls_change == 0
    assert comparison.steps_by_agent_before == comparison.steps_by_agent_after
    with pytest.raises(ValueError, match="same scenarios"):
        compare_reports(before, after.model_copy(update={"cases": []}))
