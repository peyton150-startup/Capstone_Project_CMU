"""The experiment harness, hand labels and the report, offline."""

import urllib.error

import pytest

import capstone.experiment as experiment
from capstone.agent.completion import AuditLog
from capstone.agent.model_policy import ModelCall
from capstone.benchmark import DEFAULT_SEEDS
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.evaluation.labels import Label, LabelBook, apply_label
from capstone.experiment import (
    HELD_OUT_SEEDS,
    CallSummary,
    Case,
    ExperimentRecord,
    ask_label,
    grid,
    held_out_cases,
    labelled,
    main,
    read_records,
    report,
    run_experiment,
    seeds_from,
    summarize_calls,
)
from capstone.memory.contracts import MemoryQuery
from capstone.providers.chat import Attempt, FallbackClient
from capstone.simulator.generator import FAULTS
from capstone.tools.diagnosis import Diagnosis
from tests.helpers import ask
from tests.test_episode import wear_policy
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


def test_an_answer_that_is_not_a_choice_is_asked_again(records):
    """Seen on 2026-10-21: pressing Enter with no answer stopped the command."""
    answers = iter(["", "x", "9", " 1 ", "CNC-02"])
    label = ask_label(records[0], ask=lambda prompt: next(answers))
    assert label == Diagnosis(fault="bearing_degradation", machine_id="CNC-02")
    answers = iter(["S"])
    assert ask_label(records[0], ask=lambda prompt: next(answers)) == "skip"
    answers = iter(["2", "batch two", "2"])
    assert ask_label(records[1], ask=lambda prompt: next(answers)) == Diagnosis(
        fault="bad_material_batch", batch_id=2
    )


def test_the_command_line_runs_labels_and_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        experiment, "model_policy_factory", lambda with_recall, **_: stand_in
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
    assert summary.model_dump(exclude={"details"}) == CallSummary(
        questions=4,
        answered=2,
        invalid_replies=1,
        invalid_by_job={"decide": 1},
        unanswered=1,
        outage_attempts=4,
        outage_reasons={down: 4},  # why each of them failed
        answered_by={"groq/a": 1, "nvidia/b": 1},
    ).model_dump(exclude={"details"})


@pytest.mark.parametrize("fallback_status", [None, 401, 429, 500])
def test_model_failures_survive_the_cli_file_and_report(
    tmp_path, monkeypatch, capsys, fallback_status
):
    from tests.test_chat_client import UNREACHABLE, client

    def interrupted_policy():
        policy = scripted_models()
        primary, _ = client(TimeoutError(), model="primary")
        failure = (
            UNREACHABLE
            if fallback_status is None
            else urllib.error.HTTPError(
                "https://example.invalid",
                fallback_status,
                "private-response-text",
                None,
                None,
            )
        )
        fallback, _ = client(failure, model="fallback")
        policy.clients["interpret"] = FallbackClient([primary, fallback], retries=0)
        return policy

    monkeypatch.setattr(
        experiment, "model_policy_factory", lambda with_recall, **_: interrupted_policy
    )
    path = tmp_path / "failures.jsonl"
    assert main([
        "run", "--name", "diagnostic", "--seeds", "6", "--faults",
        "bearing_degradation", "--out", str(path),
    ]) == 0  # fmt: skip
    (saved,) = read_records(path)
    assert saved.score.termination_reason == "model_unavailable"
    details = saved.model_calls.details
    assert [call.job for call in details] == ["plan", "decide", "interpret"]
    assert details[-1].outcome == "no_answer"
    fallback_error = (
        "the model service could not be reached"
        if fallback_status is None
        else f"the model service answered HTTP {fallback_status}"
    )
    assert [(a.model, a.outcome) for a in details[-1].attempts] == [
        ("primary", "the model service timed out"),
        ("fallback", fallback_error),
    ]
    assert all(a.seconds >= 0 for a in details[-1].attempts)
    live_output = capsys.readouterr().out
    assert "question 3 interpret: no_answer" in live_output
    assert main(["report", "--results", str(path)]) == 0
    output = capsys.readouterr().out
    assert "a required model question was unanswered" in output
    assert "question 3 interpret: no_answer" in output
    assert "primary: the model service timed out" in output
    assert f"fallback: {fallback_error}" in output
    assert " s)" in output
    assert "private-response-text" not in path.read_text(encoding="utf-8") + output


def test_recovered_service_failures_keep_the_answering_fallback(records):
    calls = [ModelCall(
        job="decide", outcome="answered", answered_by="fallback",
        attempts=(
            Attempt(model="primary", outcome="the model service answered HTTP 429",
                    seconds=1.25),
            Attempt(model="fallback", outcome="answered", seconds=0.5),
        ),
    )]  # fmt: skip
    summary = summarize_calls(calls)
    assert summary.unanswered == 0 and summary.outage_attempts == 1
    saved = records[0].model_copy(update={"model_calls": summary})
    text = report([saved], {})
    assert "question 1 decide: answered" in text
    assert "primary: the model service answered HTTP 429 (1.250 s)" in text
    assert "fallback: answered (0.500 s)" in text


def test_old_results_cannot_supply_missing_failure_details(records):
    old = records[0].model_dump()
    old["model_calls"] = {
        "questions": 1,
        "answered": 0,
        "invalid_replies": 0,
        "invalid_by_job": {},
        "unanswered": 1,
        "outage_attempts": 1,
        "answered_by": {},
    }
    saved = ExperimentRecord.model_validate(old)
    assert saved.model_calls.details is None
    assert "model failure details: not recorded" in report([saved], {})


def test_an_unanswered_question_with_no_attempt_does_not_invent_a_cause(records):
    summary = summarize_calls([made("judge", "no_answer")])
    saved = records[0].model_copy(update={"model_calls": summary})
    text = report([saved], {})
    assert "question 1 judge: no_answer" in text
    assert "no request attempt was recorded" in text
    assert "timed out" not in text


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


# --- what memory kept and what was recalled (evaluator-side) ---------------------


@pytest.fixture
def memory(tmp_path):
    sqlalchemy = pytest.importorskip("sqlalchemy")
    from capstone.memory.repository import SQLMemoryRepository
    from capstone.memory.schema import metadata
    from capstone.memory.service import MemoryService

    engine = sqlalchemy.create_engine(f"sqlite:///{tmp_path / 'memories.sqlite'}")
    metadata.create_all(engine)
    yield MemoryService(SQLMemoryRepository(engine))
    engine.dispose()


def recalling(cite=True):
    """The bearing policy, first asking memory; its conclusion cites E2 and E3,
    so E3 (the recall) is cited unless `cite` is off."""
    policy = wear_policy()
    policy.decisions["test"].insert(
        0, ask("recall_memories", text="vibration bearing", limit=5)
    )
    if not cite:
        concluded = policy._conclude

        def conclude(state):
            conclusion, action = concluded(state)
            update = {"evidence_ids": ("E2", "E4")}
            return conclusion.model_copy(update=update), action

        policy._conclude = conclude
    return policy


def learn_then_recall(memory, tmp_path, second, **options):
    policies = iter([wear_policy(), second])
    return run_experiment(
        [BEARING, BEARING],
        lambda: next(policies),
        name="memory",
        memory=memory,
        log=AuditLog(tmp_path / "audit.jsonl"),
        **options,
    )


def test_the_gate_decision_is_recorded_beside_the_run(memory, tmp_path):
    first, _ = learn_then_recall(memory, tmp_path, recalling())
    kept = first.memory_promotion
    assert kept.accepted and kept.stored
    [stored] = memory.search("vibration bearing", limit=5)
    assert kept.memory_id == stored.memory_id
    assert kept.diagnosis_correct is None  # free text, not yet labelled
    assert first.memory_uses == []  # the first run recalled nothing


def test_a_recalled_memory_the_agent_cites_is_marked_used(memory, tmp_path):
    first, second = learn_then_recall(memory, tmp_path, recalling(cite=True))
    [use] = second.memory_uses
    assert use.memory_id == first.memory_promotion.memory_id
    assert (use.retrieved, use.used, use.effect) == (True, True, "unknown")
    assert use.assessment_source == "evaluator" and use.evidence_ids == ("E3",)


def test_an_uncited_memory_is_unknown_not_unused(memory, tmp_path):
    _, second = learn_then_recall(memory, tmp_path, recalling(cite=False))
    [use] = second.memory_uses
    assert (use.used, use.effect, use.assessment_source) == (None, "unknown", None)


def test_without_memory_there_are_no_memory_records(records):
    assert (records[0].memory_promotion, records[0].memory_uses) == (None, None)


def test_nothing_the_evaluator_knows_reaches_the_memory_store(memory, tmp_path):
    learn_then_recall(memory, tmp_path, recalling())
    kept = memory.repository.retrieve(MemoryQuery(limit=100))
    text = " ".join(m.model_dump_json() for m in kept).lower()
    for word in ("diagnosis_correct", "true_fault", "fault_correct", "ground_truth"):
        assert word not in text


def test_the_report_traces_a_recalled_lesson_to_a_wrong_diagnosis(memory, tmp_path):
    records = learn_then_recall(memory, tmp_path, recalling())
    wrong = Diagnosis(fault="wrong_setting", machine_id="CNC-02")
    key = records[0].run_key
    labels = {key: Label(run_key=key, diagnosis=wrong, labelled_by="me")}
    lines = report(records, labels).splitlines()
    assert lines[3] == (
        "memory: 1 lesson(s) stored (0 from right diagnoses, 1 from wrong, 0 not "
        "judged); 1 recalled in 1 run(s), 1 cited by the agent; 1 recalled "
        "lesson(s) came from a wrong diagnosis"
    )
    assert lines[-2].endswith("lesson=stored recalled=0 cited=0 searches=0 refused=0")
    assert " recalled=1 cited=1 searches=1 refused=0" in lines[-1]


def test_the_report_has_no_memory_line_without_memory(records):
    assert not any(
        line.startswith("memory:") for line in report(records, {}).splitlines()
    )


# --- the held-out seeds, for reported numbers only -------------------------------


def test_the_held_out_set_is_every_fault_on_ten_fixed_seeds():
    cases = held_out_cases()
    assert HELD_OUT_SEEDS == tuple(range(1000, 1010))
    assert len(cases) == 40
    assert {(c.seed, c.fault) for c in cases} == {
        (seed, fault) for seed in HELD_OUT_SEEDS for fault in FAULTS
    }


def test_no_seed_anyone_tuned_on_is_held_out():
    tuned = {case.seed for case in KNOWN_CASES} | set(DEFAULT_SEEDS)
    tuned |= set(range(61))  # the tests and the rule baseline (R4c) use 0-60
    assert not tuned & set(HELD_OUT_SEEDS)


def test_the_command_runs_the_held_out_set(tmp_path, monkeypatch):
    ran = {}

    def fake_run(cases, make_policy, **options):
        ran["cases"] = cases
        return []

    monkeypatch.setattr(experiment, "run_experiment", fake_run)
    monkeypatch.setattr(
        experiment, "model_policy_factory", lambda with_recall, **_: None
    )
    out = str(tmp_path / "r.jsonl")
    assert main(["run", "--name", "h", "--held-out", "--out", out]) == 0
    assert ran["cases"] == held_out_cases()


def test_the_report_says_how_many_runs_were_held_out(records):
    assert "held-out seeds: 0/2 runs" in report(records, {}).splitlines()[2]
    held = [r.model_copy(update={"seed": 1003}) for r in records]
    assert "held-out seeds: 2/2 runs" in report(held, {}).splitlines()[2]


def test_a_run_with_several_faults_shows_its_causes_found_and_fixed(records):
    from capstone.evaluation.scoring import evaluate
    from capstone.simulator.challenge import build_challenge

    sim = build_challenge(42, machines=4)
    for _ in range(200):  # past the faults' start
        sim.step()
    compound = evaluate(sim, None, [], tool_calls=0, start_tick=0)
    record = records[0].model_copy(update={"score": compound})
    assert "causes=0/2 fixed=0/2" in report([record], {}).splitlines()[-1]
    assert "causes=" not in report(records, {}).splitlines()[-1]


# --- the compound challenge in experiments ---------------------------------------


def test_a_case_can_name_the_challenge():
    cases = experiment.challenge_cases([3, 5])
    assert [(c.scenario_id, c.seed, c.fault, c.kind) for c in cases] == [
        ("seed-3/challenge", 3, None, "challenge"),
        ("seed-5/challenge", 5, None, "challenge"),
    ]


def test_the_command_runs_the_challenge_on_the_given_seeds(tmp_path, monkeypatch):
    ran = {}

    def fake_run(cases, make_policy, **options):
        ran["cases"] = cases
        return []

    monkeypatch.setattr(experiment, "run_experiment", fake_run)
    monkeypatch.setattr(
        experiment, "model_policy_factory", lambda with_recall, **_: None
    )
    out = str(tmp_path / "r.jsonl")
    assert main(["run", "--name", "c", "--challenge", "1-2", "--out", out]) == 0
    assert ran["cases"] == experiment.challenge_cases([1, 2])


@pytest.fixture(scope="module")
def mixed(records):
    challenge = run_experiment(
        experiment.challenge_cases([3]), stand_in, name="challenge"
    )
    return [*records, *challenge]


def test_a_challenge_run_is_built_and_scored_with_several_faults(mixed):
    score = mixed[-1].score
    assert score.true_fault == "compound"
    assert {c.fault for c in score.causes} == {"bearing_degradation", "wrong_setting"}
    assert len(score.distractors) == 3
    assert score.resolved is False and score.causes_resolved == 0


def test_the_report_totals_and_lists_one_and_several_fault_runs_apart(mixed):
    lines = report(mixed, {}).splitlines()
    assert lines[1].startswith("one fault: ")
    assert "runs with several faults" not in lines[1]
    assert lines[2].startswith("several faults: ")
    assert "runs with several faults: 0/1 fully right" in lines[2]
    one = lines.index("runs with one fault:")
    several = lines.index("runs with several faults:")
    assert [line.split()[0] for line in lines[one + 1 : several - 1]] == [
        "bearing-6",
        "batch-7",
    ]
    assert lines[several + 1].startswith("seed-3/challenge")
    assert "causes=-/2 fixed=0/2" in lines[several + 1]


def test_a_report_of_one_kind_only_is_not_split(records):
    lines = report(records, {}).splitlines()
    assert not any(line.startswith(("one fault:", "runs with")) for line in lines)


def test_the_report_says_why_attempts_failed():
    late, busy = "the model service timed out", "the model service answered HTTP 429"
    calls = [
        made("interpret", "no_answer", None, late, busy, busy),
        made("decide", "answered", "cohere/c", late, "answered"),
    ]
    summary = summarize_calls(calls)
    assert summary.outage_reasons == {busy: 2, late: 2}
    record = ExperimentRecord(
        run_key="r/1/x",
        scenario_id="x",
        seed=1,
        anomaly="a",
        conclusion=None,
        confidence=None,
        recommendation=None,
        verification=None,
        tools_used=[],
        score=run_experiment([BEARING], stand_in, name="why")[0].score,
        model_calls=summary,
    )
    line = experiment.format_model_calls([record])
    assert line.endswith("failed because: answered HTTP 429 2, timed out 2")


def test_the_report_says_why_replies_were_invalid():
    late = "the model service timed out"
    calls = [
        made(
            "conclude",
            "invalid_reply",
            None,
            "invalid reply: cut off at the output-token limit",
        ),
        made("decide", "invalid_reply", None, late, "invalid reply: not valid JSON"),
        made("interpret", "invalid_reply", None, "invalid reply"),  # an older record
        made("plan", "answered", "nvidia/x", "answered"),
    ]
    summary = summarize_calls(calls)
    assert summary.invalid_reasons == {
        "cut off at the output-token limit": 1,
        "not valid JSON": 1,
        "reason not recorded": 1,
    }
    assert summary.outage_attempts == 1  # the timeout only, not the invalid replies
    assert summary.outage_reasons == {late: 1}
    record = ExperimentRecord(
        run_key="r/1/x",
        scenario_id="x",
        seed=1,
        anomaly="a",
        conclusion=None,
        confidence=None,
        recommendation=None,
        verification=None,
        tools_used=[],
        score=run_experiment([BEARING], stand_in, name="why-invalid")[0].score,
        model_calls=summary,
    )
    line = experiment.format_model_calls([record])
    assert "; invalid because: " in line
    assert "cut off at the output-token limit 1" in line
