"""Evaluator and experiment CLI boundary tests; no real model calls."""

import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from capstone import evals, experiment


def one_scenario():
    return evals.ScenarioConfig(
        cases=(evals.Scenario(id="one", seed=3, fault="bearing_degradation"),)
    )


def fake_report():
    return SimpleNamespace(
        cases=[object()],
        judged=0,
        overall_accuracy=None,
        accuracy_by_fault={},
        steps_by_agent={},
        abstention=None,
        model_dump_json=lambda indent: "{}",
    )


@pytest.mark.parametrize(
    "options",
    [
        ["--labels", "labels.jsonl", "--auto-label"],
        ["--resume", "--records", "old.records.jsonl"],
    ],
)
def test_evals_cli_refuses_incompatible_modes_before_loading_config(tmp_path, options):
    with pytest.raises(SystemExit) as stopped:
        evals.main(["--name", "trial", "--out", str(tmp_path / "out.json")] + options)
    assert stopped.value.code == 2


def test_evals_cli_raises_when_resumed_raw_file_is_absent(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(evals, "load_scenarios", lambda _: one_scenario())
    with pytest.raises(SystemExit) as stopped:
        evals.main(
            [
                "--name",
                "trial",
                "--out",
                str(tmp_path / "out.json"),
                "--resume",
                "--raw-out",
                str(tmp_path / "missing.jsonl"),
            ]
        )
    assert stopped.value.code == 2
    assert "no raw result to resume" in capsys.readouterr().err


def test_evals_cli_refuses_a_corrupt_resumed_prefix(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(evals, "load_scenarios", lambda _: one_scenario())
    existing = tmp_path / "raw.jsonl"
    existing.write_text("already reserved")
    monkeypatch.setattr(evals, "read_records", lambda _: [])
    monkeypatch.setattr(
        evals,
        "check_resume",
        lambda *args: (_ for _ in ()).throw(ValueError("wrong scenario prefix")),
    )
    with pytest.raises(SystemExit) as stopped:
        evals.main(
            [
                "--name",
                "trial",
                "--out",
                str(tmp_path / "out.json"),
                "--resume",
                "--raw-out",
                str(existing),
            ]
        )
    assert stopped.value.code == 2
    assert "wrong scenario prefix" in capsys.readouterr().err


def test_evals_cli_refuses_to_clobber_an_existing_raw_run(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(evals, "load_scenarios", lambda _: one_scenario())
    raw = tmp_path / "already.jsonl"
    raw.write_text("existing data")
    with pytest.raises(SystemExit) as stopped:
        evals.main(
            [
                "--name",
                "trial",
                "--out",
                str(tmp_path / "out.json"),
                "--raw-out",
                str(raw),
            ]
        )
    assert stopped.value.code == 2
    assert raw.read_text() == "existing data"
    assert "raw result path already exists" in capsys.readouterr().err


def test_evals_cli_saved_records_must_match_config_in_order(monkeypatch, tmp_path):
    monkeypatch.setattr(evals, "load_scenarios", lambda _: one_scenario())
    monkeypatch.setattr(
        evals,
        "read_records",
        lambda _: [SimpleNamespace(scenario_id="different")],
    )
    with pytest.raises(SystemExit) as stopped:
        evals.main(
            [
                "--name",
                "trial",
                "--out",
                str(tmp_path / "out.json"),
                "--records",
                str(tmp_path / "records.jsonl"),
            ]
        )
    assert stopped.value.code == 2


def test_evals_cli_rescores_saved_records_and_writes_diff_without_model(
    monkeypatch, tmp_path, capsys
):
    record = SimpleNamespace(scenario_id="one", run_key="trial/1")
    monkeypatch.setattr(evals, "load_scenarios", lambda _: one_scenario())
    monkeypatch.setattr(evals, "read_records", lambda _: [record])
    monkeypatch.setattr(
        evals,
        "run_cases",
        lambda *a, **kw: pytest.fail("re-scoring should not run episodes"),
    )
    monkeypatch.setattr(evals, "report_of", lambda *a, **kw: fake_report())
    monkeypatch.setattr(
        evals.EvalReport,
        "model_validate_json",
        lambda _: fake_report(),
    )
    monkeypatch.setattr(
        evals,
        "compare_reports",
        lambda before, after: SimpleNamespace(
            model_dump_json=lambda indent: json.dumps({"before": True})
        ),
    )
    old = tmp_path / "previous.json"
    old.write_text("{}")
    out = tmp_path / "report.json"
    assert (
        evals.main(
            [
                "--name",
                "trial",
                "--out",
                str(out),
                "--records",
                str(tmp_path / "records.jsonl"),
                "--compare-before",
                str(old),
            ]
        )
        == 0
    )
    assert json.loads(out.read_text()) == {}
    assert json.loads(out.with_suffix(".comparison.json").read_text()) == {
        "before": True
    }
    assert '"cases": 1' in capsys.readouterr().out


def test_evals_cli_saves_fresh_rows_and_uses_live_watch_hook(monkeypatch, tmp_path):
    monkeypatch.setattr(evals, "load_scenarios", lambda _: one_scenario())
    monkeypatch.setattr(evals, "open_manual", lambda _: None)
    monkeypatch.setattr(evals, "report_of", lambda *a, **kw: fake_report())
    saved = []
    monkeypatch.setattr(
        evals,
        "append_records",
        lambda path, rows: saved.append((path, list(rows))),
    )
    record = SimpleNamespace(scenario_id="one", run_key="trial/1")

    def fake_run(cases, *, name, on_record, watch, start, manual):
        assert name == "trial" and start == 1 and len(cases.cases) == 1
        assert callable(watch) and manual is None
        on_record(record)
        return [record]

    monkeypatch.setattr(evals, "run_cases", fake_run)
    out = tmp_path / "report.json"
    raw = tmp_path / "records.jsonl"
    assert (
        evals.main(
            [
                "--name",
                "trial",
                "--out",
                str(out),
                "--raw-out",
                str(raw),
                "--watch",
            ]
        )
        == 0
    )
    assert saved == [(raw, [record])]
    assert raw.exists() and out.exists()


def test_evals_automatic_labels_marks_undetermined_and_deferred_review(monkeypatch):
    records = [
        SimpleNamespace(run_key="none", conclusion=None, critic_favoured_claim=None),
        SimpleNamespace(
            run_key="review", conclusion="bearing", critic_favoured_claim=None
        ),
    ]
    monkeypatch.setattr(evals, "get_settings", lambda: object())
    monkeypatch.setattr(evals, "judgment_client", lambda _: object())
    proposed = SimpleNamespace(
        label=evals.Label(run_key="review", diagnosis=None, labelled_by="offline"),
        needs_review=True,
    )
    calls = []
    monkeypatch.setattr(
        evals,
        "propose",
        lambda run_key, diagnosis, client: (
            calls.append((run_key, diagnosis)),
            proposed,
        )[1],
    )
    monkeypatch.setattr(evals, "critic_labels", lambda records, fn: {"picked": "ok"})
    labels, review, picks = evals.automatic_labels(records)
    assert labels["none"].labelled_by == "no_conclusion"
    assert labels["review"] == proposed.label
    assert review == {"review"}
    assert picks == {"picked": "ok"}
    assert calls == [("review", "bearing")]


def test_experiment_open_memory_refuses_missing_database(monkeypatch):
    from capstone import settings

    monkeypatch.setattr(
        settings,
        "get_settings",
        lambda: SimpleNamespace(database_url=None),
    )
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        experiment.open_memory()


def test_experiment_open_memory_converts_postgres_driver_without_connecting(
    monkeypatch,
):
    import sqlalchemy

    from capstone import settings
    from capstone.memory import repository, service

    chosen = []
    engine = object()
    monkeypatch.setattr(
        settings,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=SecretStr("postgresql://u:p@localhost/demo")
        ),
    )
    monkeypatch.setattr(
        sqlalchemy,
        "create_engine",
        lambda url: (chosen.append(url.drivername), engine)[1],
    )
    monkeypatch.setattr(
        repository,
        "SQLMemoryRepository",
        lambda db: SimpleNamespace(db=db),
    )
    monkeypatch.setattr(
        service,
        "build_memory_service",
        lambda repo, opts: (repo.db, opts),
    )
    result = experiment.open_memory()
    assert chosen == ["postgresql+psycopg"]
    assert result[0] is engine


def test_experiment_cli_prevents_audit_records_collision(tmp_path, capsys, monkeypatch):
    out = tmp_path / "same.jsonl"
    monkeypatch.setattr(experiment, "open_manual", lambda _: None)
    with pytest.raises(SystemExit) as stopped:
        experiment.main(
            [
                "run",
                "--name",
                "x",
                "--seeds",
                "1",
                "--faults",
                "any",
                "--out",
                str(out),
                "--audit",
                str(out),
                "--quiet",
            ]
        )
    assert stopped.value.code == 2
    assert "audit and records paths must differ" in capsys.readouterr().err


@pytest.mark.parametrize(
    "failure", [RuntimeError("provider setup failed"), KeyboardInterrupt()]
)
def test_experiment_cli_does_not_hide_provider_failures_and_interrupts(
    monkeypatch, tmp_path, failure
):
    monkeypatch.setattr(experiment, "known_cases", lambda: [])
    monkeypatch.setattr(experiment, "open_manual", lambda _: None)
    monkeypatch.setattr(
        experiment,
        "model_policy_factory",
        lambda **kw: (
            (_ for _ in ()).throw(failure)
            if isinstance(failure, RuntimeError)
            else lambda: object()
        ),
    )
    monkeypatch.setattr(
        experiment,
        "run_experiment",
        lambda *a, **kw: (_ for _ in ()).throw(failure),
    )
    with pytest.raises(type(failure)):
        experiment.main(
            [
                "run",
                "--name",
                "synthetic",
                "--known",
                "--out",
                str(tmp_path / "record.jsonl"),
                "--no-audit",
                "--quiet",
            ]
        )


def test_experiment_cli_label_skips_missing_conclusions_and_existing_answers(
    monkeypatch, tmp_path
):
    from capstone.evaluation import labels

    records = [
        SimpleNamespace(run_key="already", conclusion="bearing"),
        SimpleNamespace(run_key="empty", conclusion=None),
        SimpleNamespace(run_key="fresh", conclusion="new"),
    ]
    monkeypatch.setattr(experiment, "read_records", lambda _: records)
    monkeypatch.setattr(
        labels.LabelBook,
        "read",
        lambda _: {"already": object()},
    )
    saved = []
    monkeypatch.setattr(
        labels.LabelBook,
        "add",
        lambda _self, row: saved.append(row),
    )
    monkeypatch.setattr(experiment, "ask_label", lambda record: "skip")
    assert (
        experiment.main(
            [
                "label",
                "--results",
                str(tmp_path / "record.jsonl"),
                "--labels",
                str(tmp_path / "labels.jsonl"),
                "--by",
                "reviewer",
            ]
        )
        == 0
    )
    assert saved == []


@pytest.mark.parametrize(
    "options, expected",
    [
        ({"kind": "challenge", "fault": "bearing_degradation"}, "own faults"),
        ({"kind": "standard", "fault": None}, "supported fault"),
        ({"kind": "invalid", "fault": "bearing_degradation"}, "supported fault"),
    ],
)
def test_scenario_config_rejects_incompatible_faults(options, expected):
    with pytest.raises(ValueError, match=expected):
        evals.Scenario(id="invalid", seed=1, **options)


@pytest.mark.parametrize(
    "difference, expected",
    [
        ("duplicate", "duplicate scenarios"),
        ("scenario", "same scenarios"),
        ("truth", "expected faults changed"),
    ],
)
def test_report_comparison_rejects_incompatible_experiments(difference, expected):
    old = SimpleNamespace(
        scenario_id="one",
        expected_faults=("bearing_degradation",),
        correct=True,
    )
    if difference == "scenario":
        new = SimpleNamespace(
            scenario_id="another", expected_faults=old.expected_faults
        )
    elif difference == "truth":
        new = SimpleNamespace(scenario_id="one", expected_faults=("false_alarm",))
    else:
        new = old
    before = SimpleNamespace(cases=[old, old] if difference == "duplicate" else [old])
    after = SimpleNamespace(cases=[new])
    with pytest.raises(ValueError, match=expected):
        evals.compare_reports(before, after)


def test_evaluator_names_compound_diagnoses_and_none():
    assert evals.names(None) == set()
    assert evals.names(
        [
            SimpleNamespace(fault="false_alarm"),
            SimpleNamespace(fault="bearing_degradation"),
        ]
    ) == {"false_alarm", "bearing_degradation"}


def test_evaluator_refuses_resume_beyond_scenario_count():
    config = one_scenario()
    with pytest.raises(ValueError, match="more saved episodes"):
        evals.check_resume(config, "trial", [object(), object()])


@pytest.mark.parametrize("automatic", [False, True])
def test_eval_cli_rescores_with_hand_or_automatic_labels_offline(
    monkeypatch, tmp_path, automatic
):
    """Both label sources must reach the report without rerunning an episode."""
    from capstone.evaluation import labels as label_module

    record = SimpleNamespace(scenario_id="one", run_key="trial/1/one")
    monkeypatch.setattr(
        evals,
        "load_scenarios",
        lambda _: SimpleNamespace(cases=[SimpleNamespace(id="one")]),
    )
    monkeypatch.setattr(evals, "read_records", lambda _: [record])
    monkeypatch.setattr(
        evals, "run_cases", lambda *args, **kwargs: pytest.fail("rescore must not run")
    )
    hand = {"trial/1/one": "human"}
    auto = {"trial/1/one": "machine"}
    monkeypatch.setattr(label_module.LabelBook, "read", lambda _: hand)
    monkeypatch.setattr(
        evals, "automatic_labels", lambda _: (auto, {"trial/1/one"}, {"critic": "pick"})
    )
    seen = []
    report = SimpleNamespace(
        model_dump_json=lambda **_: '{"cases":[]}',
        cases=[],
        judged=0,
        overall_accuracy=None,
        accuracy_by_fault={},
        steps_by_agent={},
        abstention=None,
    )

    def fake_report(name, rows, chosen, *, needs_review, critic_labels):
        seen.append((name, rows, chosen, needs_review, critic_labels))
        return report

    monkeypatch.setattr(evals, "report_of", fake_report)
    out = tmp_path / "report.json"
    args = [
        "--name", "trial", "--out", str(out),
        "--records", str(tmp_path / "saved.jsonl"),
    ]
    args += (
        ["--auto-label"]
        if automatic
        else ["--labels", str(tmp_path / "labels.jsonl")]
    )
    assert evals.main(args) == 0
    assert out.exists()
    assert seen == [
        (
            "trial", [record], auto if automatic else hand,
            {"trial/1/one"} if automatic else set(),
            {"critic": "pick"} if automatic else {},
        )
    ]


def test_experiment_cli_all_faults_and_explicit_timeout_are_forwarded(
    monkeypatch, tmp_path
):
    """An explicit time budget and all-fault grid reach the harness unchanged."""
    from capstone import experiment as experiment_module

    seen = {}
    monkeypatch.setattr(
        experiment_module, "grid",
        lambda seeds, faults: (seen.update(seeds=seeds, faults=faults), [object()])[1],
    )
    monkeypatch.setattr(
        experiment_module, "model_policy_factory",
        lambda **kwargs: (lambda: None),
    )
    monkeypatch.setattr(
        experiment_module, "run_experiment",
        lambda cases, factory, **kwargs: (
            seen.update(cases=cases, budget=kwargs["budgets"]), []
        )[1],
    )
    monkeypatch.setattr(experiment_module, "report", lambda *_: "offline report")
    assert experiment_module.main(
        [
            "run", "--name", "offline", "--seeds", "1", "--faults", "all",
            "--timeout-seconds", "12", "--no-audit", "--quiet",
            "--out", str(tmp_path / "out.jsonl"),
        ]
    ) == 0
    assert seen["seeds"] == [1]
    assert seen["faults"] == list(experiment_module.FAULTS)
    assert len(seen["cases"]) == 1
    assert seen["budget"].timeout_seconds == 12
    assert seen["budget"].followup_seconds == 4


def test_experiment_unjudged_and_absent_memory_fields_do_not_invent_evidence():
    from capstone import experiment as experiment_module

    assert experiment_module._right(SimpleNamespace(fault_correct=None)) is None
    row = SimpleNamespace(memory_promotion=None, recall_searches=None)
    assert experiment_module._lesson(row) == "-"
    assert experiment_module._searches(row) == ""
    result = SimpleNamespace(
        state=SimpleNamespace(conclusion=None, termination_reason=None),
        learning=None,
    )
    assert experiment_module.memory_records(result) == (None, [])
