"""Block 6: the side-by-side triage comparison (`python -m capstone.experiment compare`).

What these tests prove, offline and with scripted policies only:

- each arm (a records file or a run folder) becomes one column, named by
  --labels or by its path;
- the rows count what the triages did: model questions by stage, p50/p95
  seconds, timeouts, report outcomes, checks holding a report open, plan and
  investigate choices, and the evidence tests;
- safety rows read the truth: a triage that cleared a faulty case is an
  unsafe clearance, a healthy (false alarm) clearance is not, and a scored
  answer naming another machine is a wrong-machine answer;
- a root cause nobody labelled is "not judged"; a hand label judges it;
- a field older records lack is shown "-", never 0, so old runs still load.
"""

import pytest

from capstone.evaluation.labels import Label, LabelBook
from capstone.experiment import (
    Case,
    ExperimentRecord,
    append_records,
    main,
    run_experiment,
)
from capstone.tools.diagnosis import Diagnosis
from capstone.triage_compare import (
    MISSING,
    Arm,
    compare,
    load_arms,
    rows,
    unsafe_clearances,
    wrong_machine,
)
from tests.test_episode import SEED
from tests.test_triage import triage_then_deep

BEARING = Diagnosis(fault="bearing_degradation", machine_id="CNC-02")


@pytest.fixture(scope="module")
def triaged():
    """One real scripted triage-then-deep record, made once for the module."""
    # Variables:
    #   patch: Environment for the run: triage on, no critic, deep run allowed,
    #     and the legacy model Hypothesize stage the comparison rows count.
    patch = pytest.MonkeyPatch()
    patch.setenv("CRITIC", "off")
    patch.setenv("TRIAGE_THEN_DEEP", "on")
    # Legacy model-Hypothesize arm: #299 made deterministic Hypothesize the default.
    patch.setenv("TRIAGE_HYPOTHESIZE", "model")
    case = Case("bearing-6", SEED, "bearing_degradation")
    try:
        (record,) = run_experiment([case], triage_then_deep, name="cmp", triage=True)
    finally:
        patch.undo()
    return record


def variant(record, key, *, triage=None, score=None, report=None):
    """The record under a new run key, with triage, score or report fields changed."""
    # Variables:
    #   triage, score, report: Field updates for the triage record, the score
    #     and the triage's read-only report; None leaves each as it was.
    new_triage = record.triage
    if report is not None:
        new_triage = new_triage.model_copy(
            update={"report": new_triage.report.model_copy(update=report)}
        )
    if triage is not None:
        new_triage = new_triage.model_copy(update=triage)
    return record.model_copy(
        update={
            "run_key": key,
            "triage": new_triage,
            "score": record.score.model_copy(update=score or {}),
        }
    )


def table(*arms):
    """The comparison rows as {row name: cells}."""
    return dict(rows(arms))


def arm(label, *records):
    return Arm(label, list(records), [r.score for r in records])


def test_each_arm_is_a_column_with_its_counts(triaged):
    # A scripted policy asks no model, so the stage numbers are set here.
    metrics = triaged.triage.metrics.model_copy(
        update={
            "calls_by_stage": {"conclude": 1, "plan": 2},
            "model_seconds_by_stage": {"conclude": 4.0, "plan": 6.0},
        }
    )
    staged = variant(triaged, "cmp/1", triage={"metrics": metrics})
    timed_out = variant(staged, "cmp/2", triage={"termination_reason": "timeout"})
    out = table(arm("all", staged, timed_out), arm("control", triaged))
    assert out["runs"] == ["2", "1"]
    assert out["triages"] == ["2", "1"]
    assert out["timeouts"] == ["1", "0"]
    assert out["model calls: plan"] == ["4 (12 s)", "0 (0 s)"]
    assert out["model calls: conclude"] == ["2 (8 s)", "0 (0 s)"]


def test_seconds_are_nearest_rank_percentiles(triaged):
    runs = [
        variant(triaged, f"cmp/{s}", triage={"seconds": float(s)})
        for s in (10, 20, 30, 40, 90)
    ]
    out = table(arm("a", *runs))
    assert out["triage seconds p50"] == ["30 s"]
    assert out["triage seconds p95"] == ["90 s"]


def test_report_outcomes_and_checks_are_counted(triaged):
    refused = variant(
        triaged,
        "cmp/2",
        report={"outcome": "model_answer_refused", "held_open_because": ("gap",)},
    )
    silent = variant(triaged, "cmp/3", report={"outcome": "no_model_answer"})
    none_kept = variant(triaged, "cmp/4", triage={"report": None})
    out = table(arm("a", triaged, refused, silent, none_kept))
    assert out["report: refused"] == ["1"]
    assert out["report: no model answer"] == ["1"]
    assert out["report: none kept"] == ["1"]
    assert out["held open by checks"][0] == str(
        sum(
            bool(r.triage.report and r.triage.report.held_open_because)
            for r in (triaged, refused, silent)
        )
    )


def test_a_python_only_clearance_is_counted_so_it_can_be_caught(triaged):
    bad = variant(
        triaged,
        "cmp/2",
        report={"outcome": "no_model_answer", "recommendation": "no_action"},
    )
    out = table(arm("a", triaged, bad))
    assert out["cleared without model (must be 0)"] == ["1"]


def test_unsafe_clearance_is_a_cleared_faulty_case_not_a_cleared_false_alarm(
    triaged,
):
    cleared = {"recommendation": "no_action"}
    faulty = variant(triaged, "cmp/2", triage=cleared)
    healthy = variant(
        triaged, "cmp/3", triage=cleared, score={"true_fault": "false_alarm"}
    )
    assert triaged.score.true_fault != "false_alarm"
    assert unsafe_clearances(arm("a", faulty, healthy)) == "1"
    assert unsafe_clearances(arm("a", healthy)) == "0"


def test_wrong_machine_counts_answers_naming_another_machine(triaged):
    truth = triaged.score.true_machine_id
    right = variant(triaged, "cmp/2", score={"diagnosed_machine_id": truth})
    wrong = variant(triaged, "cmp/3", score={"diagnosed_machine_id": "CNC-99"})
    silent = variant(triaged, "cmp/4", score={"diagnosed_machine_id": None})
    assert wrong_machine(arm("a", right, wrong, silent)) == "1 of 2"


def test_unlabelled_root_causes_are_not_judged_and_a_label_judges_them(
    triaged, tmp_path
):
    unjudged = variant(triaged, "cmp/2", score={"fault_correct": None})
    path = tmp_path / "a.records.jsonl"
    append_records(path, [unjudged])
    (plain,) = load_arms([path])
    assert dict(rows([plain]))["root cause (labels)"] == [
        "0 right, 0 wrong, 1 not judged"
    ]
    book = {"cmp/2": Label(run_key="cmp/2", diagnosis=BEARING, labelled_by="t")}
    (judged,) = load_arms([path], labels=book)
    assert "0 not judged" in dict(rows([judged]))["root cause (labels)"][0]


def test_plan_investigate_and_evidence_test_rows(triaged):
    # The baseline is now fixed-plan by default. Flip the comparison record
    # to the explicit legacy model-plan variant to retain a mixed-mode test.
    model = variant(triaged, "cmp/2", triage={"fixed_plan": False})
    out = table(arm("a", triaged, model))
    assert out["plan: fixed / model"] == ["1 fixed / 1 model"]
    assert out["investigate: compiled / model"][0].endswith(" model")
    assert out["evidence tests"][0].startswith("on ")


def test_older_records_show_missing_fields_as_unknown(triaged, tmp_path):
    old = triaged.model_dump(mode="json")
    for key in (
        "metrics",
        "report",
        "investigate_advice",
        "evidence_tests",
        "test_records",
        "research_tool_calls",
        "packet",
    ):
        old["triage"].pop(key, None)
    record = ExperimentRecord.model_validate(old)
    out = table(arm("old", record))
    assert out["triages"] == ["1"]
    assert out["report: model conclusion"] == [MISSING]
    assert out["cleared without model (must be 0)"] == [MISSING]
    assert out["investigate: compiled / model"] == [MISSING]
    assert out["evidence tests"] == [MISSING]
    assert not any(name.startswith("model calls: ") for name in out)
    # A run with no triage at all has nothing to show either.
    untriaged = table(arm("deep only", triaged.model_copy(update={"triage": None})))
    assert untriaged["triages"] == ["0"] and untriaged["timeouts"] == [MISSING]


def test_the_compare_command_prints_one_column_per_arm(triaged, tmp_path, capsys):
    folder = tmp_path / "triage-main-all"
    folder.mkdir()
    append_records(folder / "all-r1.records.jsonl", [triaged])
    control = tmp_path / "control.records.jsonl"
    append_records(control, [variant(triaged, "cmp/2")])
    book = tmp_path / "labels.jsonl"
    LabelBook(book).add(
        Label(run_key=triaged.run_key, diagnosis=BEARING, labelled_by="t")
    )
    code = main(
        [
            "compare",
            "--results",
            str(folder),
            str(control),
            "--labels",
            "all",
            "control",
            "--label-book",
            str(book),
        ]
    )
    text = capsys.readouterr().out
    assert code == 0
    header = text.splitlines()[1]
    assert "all" in header and "control" in header
    assert "separate from the A1-A4 series" in text
    assert "unsafe clearances (truth)" in text


def test_the_compare_command_refuses_mismatched_labels_and_empty_folders(
    triaged, tmp_path
):
    path = tmp_path / "a.records.jsonl"
    append_records(path, [triaged])
    with pytest.raises(SystemExit):
        main(["compare", "--results", str(path), "--labels", "a", "b"])
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit):
        load_arms([empty])


def test_the_table_is_aligned(triaged):
    text = compare([arm("a-long-name", triaged), arm("b", triaged)])
    lines = text.splitlines()[1:]
    bars = {line.index("|") for line in lines if "|" in line}
    assert len(bars) == 1


def test_rankings_are_counted_and_an_arm_without_them_shows_missing(triaged):
    ranked = [
        variant(
            triaged,
            f"r{n}",
            triage={"ranking": True, "ranking_status": status, "ranking_requests": req},
        )
        for n, (status, req) in enumerate(
            [("accepted", 1), ("accepted", 2), ("rejected", 2), ("unavailable", 1)]
        )
    ]
    rows_ = table(arm("off", triaged), arm("on", *ranked))
    assert rows_["ranking: accepted / abstained / rejected / unavailable"] == [
        "-",
        "2 / 0 / 1 / 1",
    ]
    assert rows_["ranking corrected (saved)"] == ["-", "2 (1 saved)"]
