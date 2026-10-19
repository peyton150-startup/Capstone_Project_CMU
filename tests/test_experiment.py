"""The experiment harness, hand labels and the report, offline."""

import pytest

import capstone.experiment as experiment
from capstone.agent.model_policy import ModelCall
from capstone.evaluation.labels import Label, LabelBook, apply_label
from capstone.experiment import (
    CallSummary,
    Case,
    ExperimentRecord,
    ask_label,
    grid,
    labelled,
    main,
    read_records,
    report,
    run_experiment,
    seeds_from,
    summarize_calls,
)
from capstone.providers.chat import Attempt
from capstone.tools.diagnosis import Diagnosis
from tests.test_known_answers import stand_in
from tests.test_model_policy import scripted_models

BEARING = Case("bearing-6", 6, "bearing_degradation")  # bearing wear on CNC-02
BATCH = Case("batch-7", 7, "bad_material_batch")  # batch 2


@pytest.fixture(scope="module")
def records():
    return run_experiment([BEARING, BATCH], stand_in, name="unit")


def test_seeds_and_grid():
    assert seeds_from("1-3") == [1, 2, 3] and seeds_from("4,9") == [4, 9]
    cases = grid([1, 2], ["false_alarm", None])
    assert [c.scenario_id for c in cases] == [
        "seed-1/false_alarm",
        "seed-1/any",
        "seed-2/false_alarm",
        "seed-2/any",
    ]


def test_run_keys_are_unique_per_execution(records):
    assert [r.run_key for r in records] == ["unit/1/bearing-6", "unit/2/batch-7"]
    again = run_experiment([BEARING], stand_in, name="unit-2")
    assert again[0].run_key != records[0].run_key


def test_a_label_scores_the_root_cause_from_the_row_alone(records):
    score = records[0].score
    assert score.fault_correct is None
    right = apply_label(
        score, Diagnosis(fault="bearing_degradation", machine_id="CNC-02")
    )
    assert (right.fault_correct, right.target_correct) == (True, True)
    wrong_machine = apply_label(
        score, Diagnosis(fault="bearing_degradation", machine_id="CNC-01")
    )
    assert (wrong_machine.fault_correct, wrong_machine.target_correct) == (True, False)
    nothing = apply_label(score, None)
    assert (nothing.fault_correct, nothing.target_correct) == (False, False)
    # Everything scored from reality stays as it was.
    assert right.resolved == score.resolved and right.tool_calls == score.tool_calls


def test_a_batch_label_is_judged_by_batch(records):
    score = records[1].score
    assert apply_label(
        score, Diagnosis(fault="bad_material_batch", batch_id=2)
    ).target_correct
    assert not apply_label(
        score, Diagnosis(fault="bad_material_batch", batch_id=3)
    ).target_correct


def test_label_book_keeps_the_latest_label(tmp_path):
    book = LabelBook(tmp_path / "labels.jsonl")
    assert book.read() == {}
    book.add(Label(run_key="r1", diagnosis=None, labelled_by="a"))
    later = Label(
        run_key="r1",
        diagnosis=Diagnosis(fault="false_alarm", machine_id="CNC-01"),
        labelled_by="b",
    )
    book.add(later)
    assert book.read() == {"r1": later}


def test_report_applies_labels(records):
    labels = {
        records[0].run_key: Label(
            run_key=records[0].run_key,
            diagnosis=Diagnosis(fault="bearing_degradation", machine_id="CNC-02"),
            labelled_by="me",
        )
    }
    scores = labelled(records, labels)
    assert scores[0].fault_correct is True and scores[1].fault_correct is None
    text = report(records, labels)
    assert text.startswith("1/1 root causes correctly identified (1 not judged)")
    assert "bearing-6" in text and "batch-7" in text


def test_asking_for_a_label_at_the_console(records):
    answers = iter(["1", "CNC-02"])
    label = ask_label(records[0], ask=lambda prompt: next(answers))
    assert label == Diagnosis(fault="bearing_degradation", machine_id="CNC-02")
    answers = iter(["2", "2"])
    assert ask_label(records[1], ask=lambda p: next(answers)) == Diagnosis(
        fault="bad_material_batch", batch_id=2
    )
    assert ask_label(records[0], ask=lambda p: "0") is None
    assert ask_label(records[0], ask=lambda p: "s") == "skip"


def test_the_command_line_runs_labels_and_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        experiment, "model_policy_factory", lambda with_recall: stand_in
    )
    results = tmp_path / "results.jsonl"
    assert (
        main(
            [
                "run", "--name", "cli", "--seeds", "6", "--faults",
                "bearing_degradation", "--out", str(results),
            ]
        )
        == 0
    )  # fmt: skip
    (record,) = read_records(results)
    assert record.run_key == "cli/1/seed-6/bearing_degradation"

    labels = tmp_path / "labels.jsonl"
    answers = iter(["1", "CNC-02"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert (
        main(
            ["label", "--results", str(results), "--labels", str(labels), "--by", "me"]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["report", "--results", str(results), "--labels", str(labels)]) == 0
    assert capsys.readouterr().out.startswith("1/1 root causes correctly identified")


# --- what the model questions came to, and how long each run took --------------


def made(job, outcome, answered_by=None, *attempts):
    return ModelCall(
        job=job,
        outcome=outcome,
        answered_by=answered_by,
        attempts=tuple(Attempt(model="m", outcome=o) for o in attempts),
    )


def test_invalid_replies_and_outages_are_counted_apart():
    down = "the model service could not be reached"
    summary = summarize_calls(
        [
            made("plan", "answered", "groq/a", "answered"),
            # Two outages on the first model, then the fallback answered.
            made("decide", "answered", "nvidia/b", down, down, "answered"),
            made("decide", "invalid_reply", None, "answered"),
            made("judge", "no_answer", None, down, down),
        ]
    )
    assert summary == CallSummary(
        questions=4,
        answered=2,
        invalid_replies=1,
        invalid_by_job={"decide": 1},
        unanswered=1,
        outage_attempts=4,
        answered_by={"groq/a": 1, "nvidia/b": 1},
    )


def test_a_model_policy_run_keeps_its_call_summary_and_its_time():
    ticks = iter([100.0, 142.5])
    (record,) = run_experiment(
        [BEARING], scripted_models, name="calls", clock=lambda: next(ticks)
    )
    calls = record.model_calls
    assert calls is not None and calls.questions == 14
    assert (calls.answered, calls.invalid_replies, calls.unanswered) == (14, 0, 0)
    assert calls.answered_by == {"fake/model": 14}
    assert record.wall_seconds == 42.5


def test_a_policy_that_keeps_no_calls_records_none(records):
    assert records[0].model_calls is None
    assert records[0].wall_seconds is not None and records[0].wall_seconds >= 0


def test_a_results_line_from_before_still_reads(records):
    old = records[0].model_dump(exclude={"model_calls", "wall_seconds"})
    again = ExperimentRecord.model_validate(old)
    assert (again.model_calls, again.wall_seconds) == (None, None)


def test_the_report_shows_the_model_questions():
    ticks = iter([0.0, 30.0])
    records = run_experiment(
        [BEARING], scripted_models, name="r", clock=lambda: next(ticks)
    )
    lines = report(records, {}).splitlines()
    assert lines[1] == (
        "model questions: 14 (14 answered, 0 invalid replies, 0 unanswered, "
        "0 failed attempts); 30 s per episode on average"
    )
    assert "questions=14 invalid=0 unanswered=0 s=30" in lines[-1]


def test_the_report_says_when_no_model_was_recorded(records):
    lines = report(records, {}).splitlines()
    assert lines[1].startswith("model questions: not recorded")
    assert "questions=-" in lines[-1]
