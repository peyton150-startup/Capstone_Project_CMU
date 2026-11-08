"""Cover traced-run bookkeeping without opening models or machinery."""

import json
from types import SimpleNamespace

import coverage
import pytest

from evaltools import traced_run


def test_function_spans_reads_function_boundaries(tmp_path, monkeypatch):
    from evaltools import build_inventory

    package = tmp_path / "package"
    package.mkdir()
    (package / "sample.py").write_text("def f():\n    return 1\n")
    calls = []

    def collect(path):
        calls.append(path)
        return [SimpleNamespace(id="module:f", line=1, end_line=2)]

    monkeypatch.setattr(build_inventory, "collect_functions", collect)
    result = traced_run.function_spans(package)
    assert calls == [package / "sample.py"]
    assert result == {str(package / "sample.py"): [("module:f", 1, 2)]}


def test_functions_hit_joins_coverage_contexts_to_function_ids(tmp_path, monkeypatch):
    events = []

    class FakeData:
        def __init__(self, *, basename):
            events.append(("open", basename))

        def read(self):
            events.append(("read",))

        def measured_files(self):
            return ("ignored.py", "sample.py")

        def contexts_by_lineno(self, filename):
            assert filename == "sample.py"
            return {2: ["episode-1", ""], 3: ["episode-2"]}

    monkeypatch.setattr(coverage, "CoverageData", FakeData)
    monkeypatch.setattr(
        traced_run,
        "function_spans",
        lambda path: {
            "sample.py": [
                ("module:f", 1, 2),
                ("module:g", 2, 4),
            ]
        },
    )
    path = tmp_path / "coverage.data"
    assert traced_run.functions_hit(path) == {
        "episode-1": ["module:f"],
        "episode-2": ["module:g"],
    }
    assert events == [("open", str(path)), ("read",)]


def test_start_tracer_erases_then_starts_and_limits_scope(monkeypatch, tmp_path):
    events = []

    class FakeCoverage:
        def __init__(self, **kwargs):
            events.append(("init", kwargs))

        def erase(self):
            events.append(("erase",))

        def start(self):
            events.append(("start",))

    monkeypatch.setattr(coverage, "Coverage", FakeCoverage)
    path = tmp_path / "trace.coverage"
    tracer = traced_run.start_tracer(path)
    assert isinstance(tracer, FakeCoverage)
    assert events == [
        (
            "init",
            {"data_file": str(path), "source": ["capstone"], "branch": False},
        ),
        ("erase",),
        ("start",),
    ]


def test_run_traced_keeps_case_contexts_and_saves_on_success(monkeypatch):
    from capstone import experiment

    cases = [
        SimpleNamespace(scenario_id="first"),
        SimpleNamespace(scenario_id="second"),
    ]
    calls = []

    class Tracer:
        def switch_context(self, name):
            calls.append(("context", name))

        def stop(self):
            calls.append(("stop",))

        def save(self):
            calls.append(("save",))

    def fake_run(items, policy, *, name, start, on_record, **options):
        assert len(items) == 1 and policy == "policy"
        assert name == "check"
        assert options["manual"] is None
        return [SimpleNamespace(scenario_id=items[0].scenario_id, start=start)]

    monkeypatch.setattr(experiment, "run_experiment", fake_run)
    result = traced_run.run_traced(
        cases, "policy", name="check", cov=Tracer(), manual=None
    )
    assert [(r.scenario_id, r.start) for r in result] == [
        ("first", 1),
        ("second", 2),
    ]
    assert calls == [
        ("context", "check/1/first"),
        ("context", "check/2/second"),
        ("stop",),
        ("save",),
    ]


@pytest.mark.parametrize("scripted", [False, True])
def test_traced_cli_saves_a_deterministic_trace_without_model_calls(
    tmp_path, monkeypatch, capsys, scripted
):
    from capstone import evals, experiment

    case = SimpleNamespace(scenario_id="offline")
    monkeypatch.setattr(
        evals,
        "load_scenarios",
        lambda _: SimpleNamespace(cases=[SimpleNamespace(as_case=lambda: case)]),
    )
    tracer = object()
    monkeypatch.setattr(traced_run, "start_tracer", lambda _: tracer)
    monkeypatch.setattr(
        traced_run,
        "functions_hit",
        lambda _: {"try/1/offline": ["capstone.tools.observation:read"]},
    )
    saved = []
    monkeypatch.setattr(
        experiment,
        "append_records",
        lambda path, rows: saved.extend(rows),
    )
    policies = []

    def make_factory(with_recall, *, tree_of_thought, with_manual):
        policies.append((with_recall, tree_of_thought, with_manual))
        return "offline-policy"

    monkeypatch.setattr(experiment, "model_policy_factory", make_factory)

    def fake_run(cases, policy, **kwargs):
        assert cases == [case]
        assert kwargs["cov"] is tracer
        assert kwargs["budgets"].timeout_seconds == 21
        assert kwargs["hazards"] == "blackout"
        assert kwargs["manual"] is None
        kwargs["on_record"](
            SimpleNamespace(scenario_id="offline", run_key="try/1/offline")
        )

    monkeypatch.setattr(traced_run, "run_traced", fake_run)
    out = tmp_path / "records.jsonl"
    trace = tmp_path / "trace.json"
    args = [
        "--name",
        "try",
        "--out",
        str(out),
        "--trace",
        str(trace),
        "--coverage-file",
        str(tmp_path / ".coverage.trace"),
        "--no-audit",
        "--no-manual",
        "--timeout-seconds",
        "21",
        "--hazards",
        "blackout",
        "--tree-of-thought",
    ]
    if scripted:
        args.append("--scripted")
    assert traced_run.main(args) == 0
    assert len(saved) == 1
    assert json.loads(trace.read_text()) == {
        "try/1/offline": ["capstone.tools.observation:read"]
    }
    assert "completed offline" in capsys.readouterr().out
    assert policies == ([] if scripted else [(False, True, False)])
