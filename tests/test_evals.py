"""The eval harness uses the existing episode and scoring boundaries."""

import json
from pathlib import Path

import pytest

from capstone.evals import (
    ScenarioConfig,
    check_resume,
    compare_reports,
    critic_labels,
    load_scenarios,
    report_of,
    reserve_raw_output,
    run_cases,
)
from capstone.evaluation.auto_label import Proposal
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.evaluation.labels import Label
from capstone.experiment import Case
from capstone.tools.diagnosis import Diagnosis
from tests.helpers import FakeCritic, critique_result
from tests.test_episode import wear_policy
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


def test_output_path_is_claimed_before_a_run_and_cannot_be_shared(tmp_path):
    path = tmp_path / "episodes.jsonl"
    reserve_raw_output(path)
    with pytest.raises(FileExistsError):
        reserve_raw_output(path)
    assert path.read_text(encoding="utf-8") == ""


def test_resume_accepts_only_the_saved_prefix_and_keeps_run_numbers():
    config = ScenarioConfig.model_validate(
        {
            "cases": [
                {"id": "bearing-6", "seed": 6, "fault": "bearing_degradation"},
                {"id": "batch-7", "seed": 7, "fault": "bad_material_batch"},
            ]
        }
    )
    (first,) = run_cases(
        ScenarioConfig(cases=config.cases[:1]), name="resume-test", make_policy=stand_in
    )
    check_resume(config, "resume-test", [first])
    (second,) = run_cases(
        ScenarioConfig(cases=config.cases[1:]),
        name="resume-test",
        make_policy=stand_in,
        start=2,
    )
    assert second.run_key == "resume-test/2/batch-7"
    with pytest.raises(ValueError, match="saved episode"):
        check_resume(config, "different-name", [first])
    with pytest.raises(ValueError, match="saved episode"):
        check_resume(config, "resume-test", [first, first])
    with pytest.raises(ValueError, match="saved episode"):
        check_resume(config, "resume-test", [first.model_copy(update={"seed": 99})])


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


def test_master_run_can_show_existing_live_progress_hooks():
    config = ScenarioConfig.model_validate(
        {
            "cases": [
                {"id": BEARING.scenario_id, "seed": 6, "fault": "bearing_degradation"}
            ]
        }
    )
    lines = []
    run_cases(config, name="watched-eval", make_policy=stand_in, watch=lines.append)
    text = "\n".join(lines)
    assert "=== case 1: bearing-6 ===" in text
    assert "the truth" not in text
    assert len(lines) > 3


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


# --- the critic's verdict and pick -------------------------------------------

BEARING_CONFIG = {
    "cases": [{"id": BEARING.scenario_id, "seed": 6, "fault": "bearing_degradation"}]
}
TRUE_CAUSE = Diagnosis(fault="bearing_degradation", machine_id="CNC-02")
OTHER_CAUSE = Diagnosis(fault="wrong_setting", machine_id="CNC-02")


@pytest.fixture(scope="module")
def critiqued(monkeypatch_module):
    config = ScenarioConfig.model_validate(BEARING_CONFIG)
    (record,) = run_cases(
        config, name="critic-test", make_policy=wear_policy, make_critic=FakeCritic
    )
    return record


@pytest.fixture(scope="module")
def monkeypatch_module():
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("CRITIC", "off")
        yield patch


def test_record_keeps_the_claim_the_critic_favoured(critiqued):
    assert critiqued.critique.result.favoured == "H1"
    assert critiqued.critic_favoured_claim == (
        "the bearing on the alarmed machine is wearing"
    )


def test_report_shows_critic_fields(critiqued):
    [case] = report_of("r", [critiqued], {}).cases
    assert case.critic_outcome == "answered"
    assert case.critic_verdict == "object"
    assert case.critic_favoured == "H1"
    assert case.critic_pick_correct is None


def test_critic_pick_scored_from_its_label(critiqued):
    def pick(diagnosis):
        label = Label(
            run_key=critiqued.run_key, diagnosis=diagnosis, labelled_by="test"
        )
        report = report_of(
            "r", [critiqued], {}, critic_labels={critiqued.run_key: label}
        )
        return report.cases[0].critic_pick_correct

    assert pick(TRUE_CAUSE) is True
    assert pick(OTHER_CAUSE) is False


def test_critic_pick_does_not_change_the_agent_s_accuracy(critiqued):
    wrong = Label(run_key=critiqued.run_key, diagnosis=OTHER_CAUSE, labelled_by="t")
    right = Label(run_key=critiqued.run_key, diagnosis=TRUE_CAUSE, labelled_by="t")
    report = report_of(
        "r",
        [critiqued],
        {critiqued.run_key: right},
        critic_labels={critiqued.run_key: wrong},
    )
    assert report.overall_accuracy == 1.0
    assert report.cases[0].critic_pick_correct is False


def test_records_without_critic_report_none(monkeypatch_module):
    config = ScenarioConfig.model_validate(BEARING_CONFIG)
    (record,) = run_cases(config, name="no-critic", make_policy=stand_in)
    label = Label(run_key=record.run_key, diagnosis=TRUE_CAUSE, labelled_by="test")
    report = report_of("r", [record], {record.run_key: label})
    case = report.cases[0]
    assert (
        case.critic_outcome,
        case.critic_verdict,
        case.critic_favoured,
        case.critic_pick_correct,
    ) == (None, None, None, None)
    assert report.overall_accuracy == 1.0
    assert record.critic_favoured_claim is None


def test_critic_labels_are_proposed_from_the_favoured_claim(critiqued):
    asked = []

    def proposer(run_key, claim):
        asked.append((run_key, claim))
        return Proposal(
            label=Label(run_key=run_key, diagnosis=TRUE_CAUSE, labelled_by="fake"),
            needs_review=False,
        )

    labels = critic_labels([critiqued], proposer)
    assert asked == [(critiqued.run_key, critiqued.critic_favoured_claim)]
    assert labels[critiqued.run_key].diagnosis == TRUE_CAUSE


def test_a_critic_label_needing_review_stays_unjudged(critiqued):
    def proposer(run_key, claim):
        return Proposal(
            label=Label(run_key=run_key, diagnosis=TRUE_CAUSE, labelled_by="fake"),
            needs_review=True,
        )

    assert critic_labels([critiqued], proposer) == {}


def test_no_critic_label_when_the_critic_favoured_none(critiqued):
    record = critiqued.model_copy(
        update={
            "critique": critiqued.critique.model_copy(
                update={"result": critique_result(favoured="none")}
            ),
            "critic_favoured_claim": None,
        }
    )
    asked = []
    assert critic_labels([record], lambda *a: asked.append(a)) == {}
    assert asked == []
