"""The eval harness uses the existing episode and scoring boundaries."""

import json
from pathlib import Path

import pytest

from capstone.evals import (
    CONFIDENT,
    EvalReport,
    ScenarioConfig,
    abstention_card,
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


# --- degraded data and the abstention scorecard ------------------------------


def test_the_degraded_matrix_pairs_clean_and_blackout_cases_on_the_same_seeds():
    config = load_scenarios(Path("evals/degraded.json"))
    # "DG-02-bearing-blackout" pairs with "DG-01-bearing-clean": match by name.
    by_name = {s.id.split("-", 2)[2]: s for s in config.cases}
    blackouts = [s for s in config.cases if s.hazards == "blackout"]
    assert len(config.cases) == 11 and len(blackouts) == 5
    for scenario in blackouts:
        name = scenario.id.split("-", 2)[2]
        clean = by_name[name.replace("blackout", "clean")]
        assert (clean.seed, clean.fault, clean.kind, clean.hazards) == (
            scenario.seed,
            scenario.fault,
            scenario.kind,
            None,
        )
    assert by_name["bearing-stale"].hazards == "standard"


def test_each_case_runs_with_its_own_hazards():
    config = ScenarioConfig.model_validate(
        {
            "cases": [
                {"id": "clean", "seed": 6, "fault": "bearing_degradation"},
                {
                    "id": "dark",
                    "seed": 6,
                    "fault": "bearing_degradation",
                    "hazards": "blackout",
                },
            ]
        }
    )
    clean, dark = run_cases(config, name="hazard-cases", make_policy=stand_in)
    assert clean.hazards_fired is None and clean.blackout_recovered is None
    assert dark.hazards_fired is not None and dark.blackout_recovered is not None
    check_resume(config, "hazard-cases", [clean, dark])
    # A saved episode run without the case's hazards is not that case.
    with pytest.raises(ValueError, match="saved episode 2"):
        check_resume(
            config,
            "hazard-cases",
            [
                clean,
                dark.model_copy(
                    update={"hazards_fired": None, "blackout_recovered": None}
                ),
            ],
        )


@pytest.fixture(scope="module")
def dark_bearing():
    config = ScenarioConfig.model_validate(
        {
            "cases": [
                {
                    "id": "dark",
                    "seed": 6,
                    "fault": "bearing_degradation",
                    "hazards": "blackout",
                }
            ]
        }
    )
    (record,) = run_cases(config, name="scorecard", make_policy=stand_in)
    return record


def variant(record, run_key, **changes):
    return record.model_copy(update={"run_key": run_key, **changes})


def label(run_key, diagnosis):
    return Label(run_key=run_key, diagnosis=diagnosis, labelled_by="test")


def test_confident_no_fault_and_honest_abstention_score_apart(dark_bearing):
    """Run A says "nothing wrong" at 0.85; run B names no cause. Plain accuracy
    counts both as wrong; the scorecard tells them apart."""
    a = variant(
        dark_bearing, "A", confidence=0.85, hazards_blocked=2, blackout_recovered=False
    )
    b = variant(
        dark_bearing, "B", confidence=0.3, hazards_blocked=2, blackout_recovered=True
    )
    labels = {
        "A": label("A", Diagnosis(fault="false_alarm")),
        "B": label("B", None),
    }
    report = report_of("scorecard", [a, b], labels)
    case_a, case_b = report.cases

    assert report.overall_accuracy == 0.0  # unchanged: both are wrong here
    assert case_a.committed and case_a.confident_wrong
    assert case_a.missing_read_as_normal is True
    assert case_b.committed is False and case_b.confident_wrong is False
    assert case_b.missing_read_as_normal is False
    assert report.abstention == abstention_card(report.cases)
    card = report.abstention
    assert (card.judged, card.committed, card.abstained) == (2, 1, 1)
    assert card.accuracy_when_committed == 0.0 and card.abstention_rate == 0.5
    assert card.confident_wrong == 1 and card.missing_read_as_normal == 1
    assert (card.blackout_cases, card.refused, card.recovered) == (2, 2, 1)
    assert card.recovery_rate == 0.5


def test_confidence_below_the_line_is_wrong_but_not_confident(dark_bearing):
    low = variant(dark_bearing, "low", confidence=CONFIDENT - 0.01)
    report = report_of(
        "s", [low], {"low": label("low", Diagnosis(fault="wrong_setting"))}
    )
    assert report.cases[0].committed and report.cases[0].correct is False
    assert report.cases[0].confident_wrong is False


def test_a_blackout_that_never_refused_is_not_a_recovery_case(dark_bearing):
    quiet = variant(dark_bearing, "quiet", hazards_blocked=0, blackout_recovered=False)
    card = report_of("s", [quiet], {}).abstention
    assert card.blackout_cases == 1 and card.refused == 0
    assert card.recovery_rate is None


def test_missing_data_read_as_normal_needs_a_blackout(dark_bearing):
    clean = variant(
        dark_bearing,
        "clean",
        hazards_fired=None,
        hazards_blocked=None,
        blackout_recovered=None,
    )
    report = report_of(
        "s", [clean], {"clean": label("clean", Diagnosis(fault="false_alarm"))}
    )
    assert report.cases[0].blackout is False
    assert report.cases[0].missing_read_as_normal is None
    assert report.abstention.missing_read_as_normal == 0


def test_a_wrong_repair_request_is_a_false_intervention(dark_bearing):
    score = dark_bearing.score.model_copy(
        update={
            "recommended_actions": ["replace_bearing CNC-01"],
            "recommendation_correct": False,
        }
    )
    asked = variant(dark_bearing, "asked", score=score)
    right = variant(
        dark_bearing,
        "right",
        score=score.model_copy(update={"recommendation_correct": True}),
    )
    report = report_of("s", [asked, right], {})
    assert [c.false_intervention for c in report.cases] == [True, False]
    assert report.abstention.false_interventions == 1
    assert report.abstention.judged == 0  # needs no label


def test_unjudged_cases_stay_out_of_the_label_counts(dark_bearing):
    card = report_of("s", [dark_bearing], {}).abstention
    assert (card.judged, card.committed, card.abstained) == (0, 0, 0)
    assert card.accuracy_when_committed is None and card.abstention_rate is None
    assert report_of("s", [dark_bearing], {}).cases[0].committed is None


def test_old_reports_without_the_scorecard_still_read(dark_bearing):
    report = report_of("s", [dark_bearing], {})
    old = report.model_dump(exclude={"abstention"})
    for case in old["cases"]:
        for key in (
            "committed",
            "confidence",
            "confident_wrong",
            "false_intervention",
            "blackout",
            "missing_read_as_normal",
            "blackout_recovered",
        ):
            case.pop(key)
    assert EvalReport.model_validate(old).abstention is None


# --- the manual in the eval harness (on by default, --no-manual to opt out) ---


def test_run_cases_offers_the_manual_when_given():
    from capstone.manual.index import KeywordManualSearch
    from capstone.manual.sections import load_manual

    config = ScenarioConfig.model_validate(
        {"cases": [{"id": "bearing-6", "seed": 6, "fault": "bearing_degradation"}]}
    )
    (offered,) = run_cases(
        config,
        name="manual-eval",
        make_policy=stand_in,
        manual=KeywordManualSearch(load_manual()),
    )
    (plain,) = run_cases(config, name="plain-eval", make_policy=stand_in)
    assert offered.manual_searches is not None
    assert plain.manual_searches is None


def test_rescoring_saved_records_never_opens_the_manual(tmp_path, monkeypatch):
    import capstone.evals as evals
    from capstone.experiment import append_records

    config = ScenarioConfig.model_validate(
        {"cases": [{"id": "bearing-6", "seed": 6, "fault": "bearing_degradation"}]}
    )
    (record,) = run_cases(config, name="rescore", make_policy=stand_in)
    saved = tmp_path / "records.jsonl"
    append_records(saved, [record])
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")

    def no_manual(mode):
        raise AssertionError("the manual was opened to rescore records")

    monkeypatch.setattr(evals, "open_manual", no_manual)
    out = tmp_path / "report.json"
    argv = ["--config", str(config_path), "--name", "rescore", "--out", str(out)]
    assert evals.main([*argv, "--records", str(saved)]) == 0
    with pytest.raises(SystemExit):
        evals.main([*argv, "--records", str(saved), "--manual", "--no-manual"])


def test_the_report_carries_a_verdict_that_disagrees_with_the_pick(critiqued):
    note = "object while favouring the leading H1, with no contradiction or alternative raised"
    marked = critiqued.model_copy(
        update={
            "critique": critiqued.critique.model_copy(update={"verdict_mismatch": note})
        }
    )
    [case] = report_of("s", [marked], {}).cases
    assert case.critic_verdict_mismatch == note
    # The fixture's fake critic objects while favouring the leader: the very
    # mismatch seen live, so its record already names it.
    [plain] = report_of("s", [critiqued], {}).cases
    assert plain.critic_verdict_mismatch == critiqued.critique.verdict_mismatch
    clean = critiqued.model_copy(
        update={
            "critique": critiqued.critique.model_copy(update={"verdict_mismatch": None})
        }
    )
    assert report_of("s", [clean], {}).cases[0].critic_verdict_mismatch is None
