"""The memory comparison: the same cases with no memory, keyword and semantic
recall, side by side. Scripted policies and a local SQLite store; no network."""

import pytest

from capstone.agent.completion import AuditLog
from capstone.evaluation.labels import Label
from capstone.experiment import run_experiment
from capstone.memory.contracts import MemoryQuery
from capstone.memory_comparison import (
    MODES,
    compare_memory,
    compare_report,
    main,
    memory_for,
    mode_of,
)
from capstone.tools.diagnosis import Diagnosis
from tests.test_episode import wear_policy
from tests.test_experiment import BEARING, recalling


@pytest.fixture
def store(tmp_path):
    """A SQLite store holding one lesson, learned from a bearing run."""
    sqlalchemy = pytest.importorskip("sqlalchemy")
    from capstone.memory.repository import SQLMemoryRepository
    from capstone.memory.schema import metadata
    from capstone.memory.service import MemoryService

    engine = sqlalchemy.create_engine(f"sqlite:///{tmp_path / 'memories.sqlite'}")
    metadata.create_all(engine)
    repository = SQLMemoryRepository(engine)
    run_experiment(
        [BEARING],
        wear_policy,
        name="learn",
        memory=MemoryService(repository),
        log=AuditLog(tmp_path / "audit.jsonl"),
    )
    yield repository
    engine.dispose()


class FixedIndex:
    """A semantic index that always returns the given memory ids."""

    def __init__(self, ids):
        self.ids = tuple(ids)
        self.queries = []

    def search(self, text, k):
        self.queries.append(text)
        return self.ids[:k]


def policy_for(mode):
    """No recall without memory; otherwise the bearing policy that recalls first."""
    return wear_policy() if mode == "none" else recalling()


def stored_ids(repository):
    return [m.memory_id for m in repository.retrieve(MemoryQuery(limit=10))]


def compare(store, index, **options):
    return compare_memory(
        [BEARING], policy_for, name="cmp", repository=store, index=index, **options
    )


def test_every_mode_runs_the_same_cases_and_keeps_its_mode(store):
    results = compare(store, FixedIndex(stored_ids(store)))
    assert list(results) == list(MODES)
    for mode, records in results.items():
        assert [r.scenario_id for r in records] == [BEARING.scenario_id]
        assert all(mode_of(r) == mode for r in records)
        assert records[0].run_key == f"cmp/{mode}/1/{BEARING.scenario_id}"


def test_no_memory_offers_no_recall_and_keeps_no_memory_records(store):
    [record] = compare(store, FixedIndex(()), modes=["none"])["none"]
    assert "recall_memories" not in record.tools_used
    assert record.memory_uses is None


def test_keyword_and_semantic_recall_differ_by_what_their_search_finds(store):
    """Keyword search finds the lesson by its words; an index that finds
    nothing gives semantic mode nothing, with no keyword fallback."""
    results = compare(store, FixedIndex(()), modes=["keyword", "semantic"])
    [keyword], [semantic] = results["keyword"], results["semantic"]
    assert [u.memory_id for u in keyword.memory_uses] == stored_ids(store)
    assert semantic.memory_uses == []


def test_semantic_mode_asks_the_index(store):
    index = FixedIndex(stored_ids(store))
    [record] = compare(store, index, modes=["semantic"])["semantic"]
    assert index.queries == ["vibration bearing"]
    assert [u.memory_id for u in record.memory_uses] == stored_ids(store)
    assert record.memory_uses[0].used is True  # the conclusion cites the recall


def test_the_comparison_writes_nothing_to_memory(store):
    before = stored_ids(store)
    results = compare(store, FixedIndex(before))
    assert stored_ids(store) == before
    assert all(r.memory_promotion is None for rs in results.values() for r in rs)


def test_semantic_mode_never_runs_as_keyword_search_unseen(store):
    with pytest.raises(ValueError, match="needs an index"):
        memory_for("semantic", store, None)
    with pytest.raises(ValueError, match="unknown memory mode"):
        memory_for("vector", store, None)
    with pytest.raises(ValueError, match="may not contain"):
        compare_memory([BEARING], policy_for, name="a/b", repository=store)


def test_the_report_puts_the_modes_side_by_side_with_labels(store):
    results = compare(store, FixedIndex(stored_ids(store)))
    records = [r for rs in results.values() for r in rs]
    right = Diagnosis(fault="bearing_degradation", machine_id="CNC-02")
    labels = {
        r.run_key: Label(run_key=r.run_key, diagnosis=right, labelled_by="test")
        for r in records
        if mode_of(r) != "keyword"  # keyword left unlabelled on purpose
    }
    text = compare_report(records, labels)
    lines = text.splitlines()
    none_line = next(line for line in lines if line.startswith("none "))
    keyword_line = next(line for line in lines if line.startswith("keyword "))
    assert "cause_right=1/1 judged" in none_line and "searches=0" in none_line
    assert "cause_right=0/0 judged" in keyword_line
    assert "searches=1 refused=0 failed=0 recalled=1 cited=1" in keyword_line
    assert "outage=0" in keyword_line
    [case] = [line for line in lines if line.startswith(BEARING.scenario_id)]
    assert "none: cause=True" in case and "keyword: cause=-" in case
    assert "semantic: cause=True" in case
    assert "WARNING" not in text


def test_the_report_warns_when_the_modes_ran_different_cases(store):
    results = compare(store, FixedIndex(()), modes=["none"])
    other = compare_memory(
        [BEARING, BEARING],
        policy_for,
        name="cmp2",
        repository=store,
        modes=["keyword"],
    )
    text = compare_report([*results["none"], *other["keyword"]], {})
    assert "WARNING: the modes did not run the same cases" in text


def test_the_command_reports_a_results_file(store, tmp_path, capsys):
    from capstone.experiment import append_records

    results = compare(store, FixedIndex(()), modes=["none", "keyword"])
    path = tmp_path / "cmp.jsonl"
    append_records(path, [r for rs in results.values() for r in rs])
    assert main(["report", "--results", str(path)]) == 0
    out = capsys.readouterr().out
    assert "none " in out and "keyword " in out


def test_the_command_refuses_an_unknown_mode(tmp_path):
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "--name",
                "x",
                "--known",
                "--modes",
                "none,vector",
                "--out",
                str(tmp_path / "x.jsonl"),
            ]
        )


class FailingIndex:
    """A semantic index whose every search fails, like an embedding 429."""

    def search(self, text, k):
        raise ConnectionError("rate limited")


def test_a_failed_semantic_search_is_reported_failed_not_answered_by_keyword(store):
    """Gap 1: semantic mode never falls back to keyword search during a run."""
    [record] = compare(store, FailingIndex(), modes=["semantic"])["semantic"]
    [search] = record.recall_searches
    assert search.outcome == "failed" and search.memory_ids == ()
    assert record.memory_uses == []  # keyword search would have found the lesson
    line = next(
        line
        for line in compare_report([record], {}).splitlines()
        if line.startswith("semantic ")
    )
    assert "searches=1 refused=0 failed=1 recalled=0" in line


def test_outage_runs_are_counted_then_left_out_of_every_total(store):
    """Gap 2: a run no model answered says nothing about memory."""
    from capstone.evaluation.scoring import MODEL_UNAVAILABLE

    [good, other] = compare_memory(
        [BEARING, BEARING], policy_for, name="cmp", repository=store, modes=["none"]
    )["none"]
    outage_score = other.score.model_copy(
        update={"termination_reason": MODEL_UNAVAILABLE, "tool_calls": 99}
    )
    outage = other.model_copy(update={"score": outage_score, "factory_calls": 99})
    right = Diagnosis(fault="bearing_degradation", machine_id="CNC-02")
    labels = {
        r.run_key: Label(run_key=r.run_key, diagnosis=right, labelled_by="test")
        for r in (good, outage)
    }
    text = compare_report([good, outage], labels)
    [line] = [line for line in text.splitlines() if line.startswith("none ")]
    assert "runs=2 outage=1 cause_right=1/1 judged resolved=1/1" in line
    assert f"tool_calls={good.score.tool_calls:.1f}" in line  # the 99 is left out
    assert f"factory_calls={good.factory_calls:.1f}" in line
    [case_two] = [
        line for line in text.splitlines()[2:] if line.endswith("none: outage")
    ]
    assert case_two.startswith(BEARING.scenario_id)


def test_factory_calls_leave_memory_searches_out(store):
    """Gap 3: memory modes are not charged for their searches."""
    results = compare(store, FixedIndex(stored_ids(store)))
    [none], [keyword] = results["none"], results["keyword"]
    assert none.factory_calls == none.score.tool_calls
    assert keyword.factory_calls == keyword.score.tool_calls - 1
    assert keyword.factory_calls == none.factory_calls  # same looking, plus a search
    line = next(
        line
        for line in compare_report(results["keyword"], {}).splitlines()
        if line.startswith("keyword ")
    )
    assert f"factory_calls={keyword.factory_calls:.1f}" in line


def test_a_refused_repeat_counts_as_a_call_but_a_skipped_one_does_not(store):
    """factory_calls follows the same counting rule as tool_calls."""
    from capstone.agent.state import DecisionRecord
    from capstone.experiment import count_factory_calls

    def decision(sequence, tool, outcome):
        return DecisionRecord.model_construct(
            sequence=sequence, tool=tool, outcome=outcome
        )

    class State:
        decisions = [
            decision(1, "get_sensor_history", "observed"),
            decision(2, "get_sensor_history", "repeated_call"),  # never sent
            decision(3, "get_machine_status", "tool_error"),  # sent, refused
            decision(4, "recall_memories", "observed"),
            decision(5, "search_manual", "observed"),
            decision(6, None, "observed"),  # a step with no tool
        ]

    assert count_factory_calls(State()) == 2


def test_the_runs_are_interleaved_case_by_case(store):
    """Gap 5: case 1 in every mode, then case 2, with run keys numbered by case."""
    order = []
    results = compare_memory(
        [BEARING, BEARING],
        policy_for,
        name="cmp",
        repository=store,
        index=FixedIndex(stored_ids(store)),
        on_record=lambda r: order.append(r.run_key),
    )
    expected = [
        f"cmp/{mode}/{number}/{BEARING.scenario_id}"
        for number in (1, 2)
        for mode in MODES
    ]
    assert order == expected
    assert [r.run_key for r in results["keyword"]] == [
        f"cmp/keyword/{n}/{BEARING.scenario_id}" for n in (1, 2)
    ]


def test_a_mode_may_be_named_only_once(store, tmp_path):
    with pytest.raises(ValueError, match="only once"):
        compare_memory(
            [BEARING], policy_for, name="cmp", repository=store, modes=["none", "none"]
        )
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "--name",
                "x",
                "--known",
                "--modes",
                "none,none",
                "--out",
                str(tmp_path / "x.jsonl"),
            ]
        )
