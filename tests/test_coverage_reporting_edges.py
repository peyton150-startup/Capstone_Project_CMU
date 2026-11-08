"""Targeted diagnostics, reporting, and comparison edge tests.

Everything uses deterministic synthetic observations and in-memory stand-ins.
No external provider, physical equipment or persistent service is accessed.
"""

import json
from types import SimpleNamespace

import pytest

from capstone import baseline, memory_comparison, tree_reach


def reach_record(*, thoughts=None, calls=None, reason="timeout", steps=None):
    return SimpleNamespace(
        run_key="fake-run",
        scenario_id="synthetic",
        thoughts=thoughts,
        model_calls=None if calls is None else SimpleNamespace(details=calls),
        score=SimpleNamespace(termination_reason=reason),
        agent_steps=steps,
        wall_seconds=4.0,
        hypothesis_reserve_used=True,
    )


def test_reach_groups_cover_generated_skipped_unanswered_and_early_termination():
    candidate = SimpleNamespace(id="H1")
    tree = SimpleNamespace(candidates=[candidate], branching=None)
    skipped = SimpleNamespace(candidates=[], branching="skipped")
    asked = SimpleNamespace(job="hypothesize")
    assert tree_reach.group_of(reach_record(thoughts=[tree])) == "tree"
    assert tree_reach.group_of(reach_record(thoughts=[skipped])) == "skipped"
    assert tree_reach.group_of(reach_record(calls=[asked])) == "no_answer"
    assert tree_reach.group_of(reach_record(reason=None)) == "before_unknown"


def test_reach_counts_attempt_failures_and_only_pre_tree_research_calls():
    decisions = [
        SimpleNamespace(kind="decision", phase="investigate", tool="get_readings"),
        SimpleNamespace(kind="decision", phase="test", tool="get_settings"),
        SimpleNamespace(kind="decision", phase="plan", tool="get_time"),
        SimpleNamespace(kind="reflection", phase="test", tool="get_readings"),
    ]
    calls = [
        SimpleNamespace(
            job="investigate",
            attempts=[
                SimpleNamespace(seconds=1.25, outcome="timeout"),
                SimpleNamespace(seconds=None, outcome="answered"),
            ],
        ),
        SimpleNamespace(job="hypothesize", attempts=[]),
        SimpleNamespace(
            job="verify", attempts=[SimpleNamespace(seconds=10.0, outcome="timeout")]
        ),
    ]
    row = tree_reach.reach_of(reach_record(calls=calls, steps=decisions))
    assert row.seconds_by_job == {"investigate": 1.2}
    assert row.failed_attempts_by_job == {"investigate": 1}
    assert row.last_stage == "plan"
    assert row.research_tool_calls == 2
    assert row.hypothesis_reserve_used is True


def test_reach_summary_groups_time_failures_and_reserve_usage():
    first = tree_reach.Reach(
        run_key="a",
        scenario_id="x",
        group="tree",
        last_stage=None,
        termination_reason=None,
        seconds_by_job={"observe": 1.2},
        failed_attempts_by_job={"observe": 1},
        research_tool_calls=1,
        wall_seconds=3,
        hypothesis_reserve_used=True,
    )
    second = first.model_copy(
        update={
            "run_key": "b",
            "seconds_by_job": {"observe": 2.4},
            "failed_attempts_by_job": {"observe": 2},
            "hypothesis_reserve_used": False,
        }
    )
    summary = tree_reach.summarize([first, second])
    assert summary["groups"]["tree"]["seconds_by_job"] == {"observe": 3.6}
    assert summary["groups"]["tree"]["failed_attempts_by_job"] == {"observe": 3}
    assert summary["groups"]["tree"]["reserve_used"] == 1


def test_tree_position_report_skips_unrated_candidates_and_counts_rotation():
    a, b = SimpleNamespace(id="A"), SimpleNamespace(id="B")
    thought = SimpleNamespace(
        candidates=[a, b],
        shown_order=("B", "A", "unrated"),
        ratings=[
            SimpleNamespace(candidate_id="A", confidence=0.8),
            SimpleNamespace(candidate_id="B", confidence=0.4),
            SimpleNamespace(candidate_id="A", confidence=0.1),
        ],
        kept={"A"},
    )
    report = tree_reach.position_effect([reach_record(thoughts=[thought])])
    assert report["trees"] == 1
    assert report["rotated_trees"] == 1
    assert report["by_position"][1]["mean_confidence"] == 0.4
    assert report["by_position"][2]["kept_rate"] == 1
    assert 3 not in report["by_position"]


def test_tree_position_report_ignores_runs_with_no_rating():
    thought = SimpleNamespace(
        candidates=[SimpleNamespace(id="A")],
        shown_order=(),
        ratings=[],
        kept=(),
    )
    report = tree_reach.position_effect([reach_record(thoughts=[thought])])
    assert report == {"trees": 0, "rotated_trees": 0, "by_position": {}}


@pytest.mark.parametrize("json_mode", [False, True])
def test_tree_report_cli_text_and_json_paths(monkeypatch, tmp_path, capsys, json_mode):
    record = reach_record()
    monkeypatch.setattr(tree_reach, "read_all", lambda paths: [record])
    args = [str(tmp_path / "records.jsonl"), "--positions"]
    if json_mode:
        args += ["--json"]
    assert tree_reach.main(args) == 0
    output = capsys.readouterr().out
    if json_mode:
        result = json.loads(output)
        assert result["summary"]["runs"] == 1
        assert result["runs"][0]["group"] == "before_timeout"
        assert result["positions"]["trees"] == 0
    else:
        assert "positions: 0 tree(s)" in output
        assert "before_timeout" in output


def test_tree_report_cli_loads_all_files_in_order(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(
        tree_reach,
        "read_records",
        lambda path: (seen.append(path), [str(path)])[1],
    )
    paths = [tmp_path / "first.jsonl", tmp_path / "second.jsonl"]
    assert tree_reach.read_all(paths) == [str(p) for p in paths]
    assert seen == paths


def test_memory_comparison_opens_sql_only_for_nonsemantic_modes(monkeypatch):
    from capstone import experiment

    store = object()
    monkeypatch.setattr(
        experiment,
        "open_memory",
        lambda: SimpleNamespace(repository=store),
    )
    assert memory_comparison.open_store_and_index(["none", "keyword"]) == (store, None)


def test_memory_comparison_semantic_errors_never_fall_back_to_keyword(monkeypatch):
    from capstone import experiment, settings
    from capstone.memory import semantic

    monkeypatch.setattr(
        experiment,
        "open_memory",
        lambda: SimpleNamespace(repository=object()),
    )
    monkeypatch.setattr(settings, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(
        semantic,
        "open_configured_index",
        lambda _: (_ for _ in ()).throw(RuntimeError("index unavailable")),
    )
    with pytest.raises(SystemExit, match="RuntimeError"):
        memory_comparison.open_store_and_index(["semantic"])


def test_memory_comparison_semantic_mode_preserves_index(monkeypatch):
    from capstone import experiment, settings
    from capstone.memory import semantic

    store, index = object(), object()
    monkeypatch.setattr(
        experiment,
        "open_memory",
        lambda: SimpleNamespace(repository=store),
    )
    monkeypatch.setattr(settings, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(semantic, "open_configured_index", lambda _: index)
    assert memory_comparison.open_store_and_index(["semantic"]) == (store, index)


@pytest.mark.parametrize("mode", ["nonsense", "none,none"])
def test_memory_comparison_cli_rejects_unrecognized_or_duplicate_modes(
    monkeypatch, tmp_path, mode
):
    monkeypatch.setattr(memory_comparison, "safe_console", lambda: None)
    with pytest.raises(SystemExit) as stopped:
        memory_comparison.main(
            [
                "run",
                "--name",
                "synthetic",
                "--known",
                "--out",
                str(tmp_path / "out.jsonl"),
                "--modes",
                mode,
            ]
        )
    assert stopped.value.code == 2


@pytest.mark.parametrize("labelled", [False, True])
def test_memory_comparison_report_cli_reads_saved_records(
    monkeypatch, tmp_path, capsys, labelled
):
    monkeypatch.setattr(memory_comparison, "safe_console", lambda: None)
    monkeypatch.setattr(memory_comparison, "read_records", lambda _: ["saved"])
    monkeypatch.setattr(
        memory_comparison,
        "compare_report",
        lambda records, labels: f"comparison {len(records)} {len(labels)}",
    )
    if labelled:
        from capstone.evaluation import labels

        monkeypatch.setattr(labels.LabelBook, "read", lambda _self: {"case": object()})
    args = ["report", "--results", str(tmp_path / "results.jsonl")]
    if labelled:
        args += ["--labels", str(tmp_path / "labels.jsonl")]
    assert memory_comparison.main(args) == 0
    assert (
        "comparison 1 1" if labelled else "comparison 1 0"
    ) in capsys.readouterr().out


@pytest.mark.parametrize("selection", ["--known", "--held-out", "--seeds"])
def test_memory_comparison_run_cli_dispatches_without_models(
    monkeypatch, tmp_path, capsys, selection
):
    from capstone import experiment

    monkeypatch.setattr(memory_comparison, "safe_console", lambda: None)
    monkeypatch.setattr(memory_comparison, "known_cases", lambda: ["known"])
    monkeypatch.setattr(memory_comparison, "held_out_cases", lambda: ["held"])
    monkeypatch.setattr(memory_comparison, "grid", lambda seeds, faults: ["seed"])
    monkeypatch.setattr(memory_comparison, "seeds_from", lambda _: [10])
    monkeypatch.setattr(
        experiment,
        "model_policy_factory",
        lambda *, with_recall: lambda: f"policy-{with_recall}",
    )
    monkeypatch.setattr(
        memory_comparison,
        "open_store_and_index",
        lambda modes: (object(), None),
    )
    monkeypatch.setattr(
        memory_comparison,
        "compare_report",
        lambda rows, labels: f"compared {len(rows)}",
    )
    emitted = []
    monkeypatch.setattr(
        memory_comparison,
        "append_records",
        lambda path, records: emitted.extend(records),
    )
    chosen = []

    def compare(cases, factory, *, name, repository, index, modes, on_record):
        chosen.extend(cases)
        assert factory("none") == "policy-False"
        assert factory("keyword") == "policy-True"
        record = SimpleNamespace(run_key="sample", conclusion=None)
        on_record(record)
        return {"none": [record], "keyword": []}

    monkeypatch.setattr(memory_comparison, "compare_memory", compare)
    args = [
        "run",
        "--name",
        "sample",
        "--out",
        str(tmp_path / "out.jsonl"),
        "--modes",
        "none,keyword",
    ]
    args += [selection, "10"] if selection == "--seeds" else [selection]
    assert memory_comparison.main(args) == 0
    assert chosen == [
        {"--known": "known", "--held-out": "held", "--seeds": "seed"}[selection]
    ]
    assert len(emitted) == 1
    assert "compared 1" in capsys.readouterr().out


@pytest.mark.parametrize("raw, expected", [("2-4", [2, 3, 4]), ("1,5,9", [1, 5, 9])])
def test_baseline_seed_ranges_and_lists(raw, expected):
    assert baseline._seeds(raw) == expected


@pytest.mark.parametrize("known", [False, True])
def test_baseline_cli_formats_known_and_explicit_cases(monkeypatch, capsys, known):
    monkeypatch.setattr(
        baseline,
        "KNOWN_CASES",
        [SimpleNamespace(scenario_id="known", seed=1, fault="bearing_degradation")],
    )
    monkeypatch.setattr(baseline, "FAULTS", ["false_alarm"])
    calls = []

    def run(seed, fault):
        calls.append((seed, fault))
        return SimpleNamespace(
            diagnosed_fault="false_alarm",
            fault_correct=True,
            target_correct=True,
            resolved=True,
            miss_kind=None,
        )

    monkeypatch.setattr(baseline, "run_baseline", run)
    monkeypatch.setattr(baseline, "summarize", lambda items: len(items))
    monkeypatch.setattr(baseline, "format_summary", lambda items: f"total={items}")
    assert baseline.main(["--known"] if known else ["--seeds", "1-2"]) == 0
    assert calls == (
        [(1, "bearing_degradation")]
        if known
        else [(1, "false_alarm"), (2, "false_alarm")]
    )
    assert "total=" in capsys.readouterr().out


@pytest.mark.parametrize(
    "before, alarm, after, expected",
    [
        (2.0, 10.0, 1.0, "false_alarm"),
        (2.0, 10.0, 9.0, "bearing_degradation"),
        (None, 10.0, 1.0, "bearing_degradation"),
    ],
)
def test_baseline_alarm_classifies_sustained_and_transient_signals(
    before, alarm, after, expected
):
    tick = [100]

    class Look:
        def get_time(self):
            return {"tick": tick[0]}

        def get_readings(self, *, from_tick, to_tick, **kwargs):
            if to_tick == 99:
                value = before
            elif from_tick == 100 and to_tick == 100:
                value = alarm
            else:
                value = after
            return [] if value is None else [{"value": value}]

    class Act:
        def wait(self, *, ticks):
            tick[0] += ticks

    found = baseline.diagnose(
        Look(),
        Act(),
        SimpleNamespace(kind="alarm", machine_id="CNC-1", tick=100),
    )
    assert found.diagnosis.fault == expected
    assert found.calls[0] == ("wait", {"ticks": baseline.SETTLE_TICKS})


@pytest.mark.parametrize(
    "inspections, expected",
    [
        ([], "false_alarm"),
        ([{"batch_id": 1, "result": "failed"}], "wrong_setting"),
        (
            [{"batch_id": 1, "result": "failed"}] * 3
            + [{"batch_id": 2, "result": "passed"}] * 10,
            "bad_material_batch",
        ),
    ],
)
def test_baseline_uses_inspections_when_job_times_do_not_identify_machine(
    inspections, expected
):
    tick = [1]

    class Look:
        def get_time(self):
            return {"tick": tick[0]}

        def get_events(self, **kwargs):
            return []

        def get_inspections(self, **kwargs):
            return inspections

    class Act:
        def wait(self, *, ticks):
            tick[0] += ticks

    verdict = baseline.diagnose(
        Look(),
        Act(),
        SimpleNamespace(kind="inspection", machine_id=None, tick=1),
    )
    assert verdict.diagnosis.fault == expected
    assert "get_inspections" in [name for name, _ in verdict.calls]


def test_baseline_status_alarm_uses_only_the_observable_stop():
    result = baseline.diagnose(
        object(),
        object(),
        SimpleNamespace(kind="status", machine_id="CNC-2", tick=12),
    )
    assert result.diagnosis.fault == "bearing_degradation"
    assert result.diagnosis.machine_id == "CNC-2"

def test_tree_reach_text_report_prints_each_rating_position(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(tree_reach, "read_all", lambda paths: [])
    monkeypatch.setattr(
        tree_reach,
        "position_effect",
        lambda records: {
            "trees": 1,
            "rotated_trees": 1,
            "by_position": {
                1: {"ratings": 2, "mean_confidence": 0.5, "kept_rate": 1.0}
            },
        },
    )
    assert tree_reach.main(
        [str(tmp_path / "records.jsonl"), "--positions"]
    ) == 0
    output = capsys.readouterr().out
    assert "shown 1: 2 rating(s)" in output
    assert "kept 100%" in output
