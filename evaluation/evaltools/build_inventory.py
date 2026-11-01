"""Build the function, test, tool and verification inventories.

    uv run python -m evaltools.build_inventory --coverage .coverage --junit junit.xml

Static analysis (the `ast` module) lists every project-owned function, method
and test. Coverage data recorded with `pytest --cov=capstone
--cov-context=test` says which tests executed which statements, which gives
the bidirectional function/test mapping. A junit report says which tests
actually passed; a test that did not run is never reported as passing.

Machine-derived defaults are conservative: no automatic rule ever classifies
a function as VERIFIED. Only a curated note (`evaluation/curated/*.json`,
written by a reviewer) can raise a status to VERIFIED or lower it to FAILED.
"""

import argparse
import ast
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO / "capstone-code"
PACKAGE = SOURCE_ROOT / "capstone"
TESTS = REPO / "tests"
CURATED = REPO / "evaluation" / "curated"
DEFAULT_OUT = REPO / "evaluation" / "inventory"

INVENTORY_VERSION = "1.0.0"

# How many ids a list keeps before it is cut, so the files stay readable.
LIST_CAP = 30

# Excluded from the inventory, documented for the audit (Phase 2 requires it).
EXCLUSIONS = [
    "`.venv/`, `uv.lock`: third-party dependencies, not project code.",
    "`migrations/`: Alembic scaffolding; `env.py` is exercised by "
    "tests/test_migrations.py but is not part of the `capstone` package.",
    "`test_db_connection.py` (repository top): a manual connection probe.",
    "`.github/test_groups.py`: CI wiring, checked by CI itself.",
    "`evaluation/evaltools/`: this scaffolding.",
    "Generated files: `.coverage`, `.pytest-tmp/`, `.chroma/`.",
]

STATUS_DEFAULTS = {
    "none": "NOT TESTED",
    "import-only": "INSUFFICIENT EVIDENCE",
    "indirect": "INSUFFICIENT EVIDENCE",
    "direct": "PARTIALLY VERIFIED",
    "no-statements": "NOT APPLICABLE",
}
ALLOWED_STATUS = {
    "VERIFIED",
    "FAILED",
    "PARTIALLY VERIFIED",
    "NOT TESTED",
    "INSUFFICIENT EVIDENCE",
    "NOT APPLICABLE",
}

SIDE_EFFECT_HINTS = {
    "writes_file": re.compile(r"\.open\(|open\(|\.write_text\(|\.write\("),
    "prints": re.compile(r"\bprint\("),
    "network": re.compile(r"urllib|urlopen|requests\."),
    "sleeps": re.compile(r"\bsleep\("),
    "threads": re.compile(r"threading\."),
    "environment": re.compile(r"os\.environ|monkeypatch"),
}

WEAK_ASSERT_FORMS = {"truthiness", "is_not_none"}


@dataclass
class FunctionInfo:
    id: str
    module: str
    file: str
    line: int
    end_line: int
    name: str
    qualname: str
    kind: str
    signature: str
    purpose: str
    docstring: str
    has_variable_block: bool
    decorators: list[str]
    raises: list[str]
    catches: list[str]
    calls: list[str]
    side_effect_hints: list[str]
    statements: int
    is_stub: bool
    mutates_parameters: list[str] = field(default_factory=list)


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def module_name(path: Path) -> str:
    if path.is_relative_to(SOURCE_ROOT):
        parts = path.relative_to(SOURCE_ROOT).with_suffix("").parts
    else:
        parts = path.relative_to(REPO).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def leading_comment(lines: list[str], lineno: int) -> str:
    """Comment lines directly above a definition (and its decorators)."""
    found = []
    index = lineno - 2
    while index >= 0:
        text = lines[index].strip()
        if text.startswith("#"):
            found.append(text.lstrip("# ").rstrip())
        elif text.startswith("@"):
            pass
        else:
            break
        index -= 1
    return " ".join(reversed(found))


def exception_names(node: ast.AST) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Call):
        return exception_names(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Tuple):
        return ", ".join(filter(None, (exception_names(e) for e in node.elts)))
    return None


def call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def count_statements(node: ast.AST) -> int:
    return (
        sum(
            isinstance(child, ast.stmt) and not isinstance(child, ast.Pass)
            for child in ast.walk(node)
        )
        - 1
    )  # the def itself


def is_stub(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
    ):
        body = body[1:]  # docstring
    if not body:
        return True
    return all(
        isinstance(stmt, ast.Pass)
        or (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis
        )
        for stmt in body
    )


def function_kind(node, parents: list[ast.AST]) -> str:
    names = {
        d.id if isinstance(d, ast.Name) else getattr(d, "attr", "")
        for d in node.decorator_list
    }
    inside_class = bool(parents) and isinstance(parents[-1], ast.ClassDef)
    if "property" in names or "setter" in names:
        return "property"
    if "classmethod" in names:
        return "classmethod"
    if "staticmethod" in names:
        return "staticmethod"
    if inside_class:
        return "method"
    if parents and isinstance(parents[-1], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "nested_function"
    return "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"


def mutated_parameters(node) -> list[str]:
    """Parameters whose attributes or items are assigned inside the body."""
    params = {a.arg for a in node.args.args + node.args.kwonlyargs}
    params.discard("self")
    params.discard("cls")
    found = set()
    for child in ast.walk(node):
        targets = []
        if isinstance(child, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
        for target in targets:
            root = target
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            if isinstance(root, ast.Name) and root.id in params and root is not target:
                found.add(root.id)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr in {"append", "extend", "clear", "update", "setdefault"}:
                root = child.func.value
                while isinstance(root, (ast.Attribute, ast.Subscript)):
                    root = root.value
                if isinstance(root, ast.Name) and root.id in params:
                    found.add(root.id)
    return sorted(found)


def collect_functions(path: Path) -> list[FunctionInfo]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    module = module_name(path)
    found: list[FunctionInfo] = []

    def visit(node: ast.AST, parents: list[ast.AST], prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, [*parents, child], f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                body_text = "\n".join(lines[child.lineno - 1 : child.end_lineno])
                docstring = ast.get_docstring(child) or ""
                comment = leading_comment(lines, child.lineno)
                purpose = docstring.strip().splitlines()[0] if docstring else comment
                found.append(
                    FunctionInfo(
                        id=f"{module}:{qualname}",
                        module=module,
                        file=rel(path),
                        line=child.lineno,
                        end_line=child.end_lineno,
                        name=child.name,
                        qualname=qualname,
                        kind=function_kind(child, parents),
                        signature=ast.unparse(child.args)
                        + (
                            f" -> {ast.unparse(child.returns)}"
                            if child.returns is not None
                            else ""
                        ),
                        purpose=purpose[:300],
                        docstring=docstring[:400],
                        has_variable_block="# Variables:" in body_text,
                        decorators=[ast.unparse(d) for d in child.decorator_list],
                        raises=sorted(
                            {
                                name
                                for n in ast.walk(child)
                                if isinstance(n, ast.Raise)
                                and (name := exception_names(n.exc))
                            }
                        ),
                        catches=sorted(
                            {
                                name
                                for n in ast.walk(child)
                                if isinstance(n, ast.ExceptHandler)
                                and (name := exception_names(n.type) or "BaseException")
                            }
                        ),
                        calls=sorted(
                            {
                                name
                                for n in ast.walk(child)
                                if isinstance(n, ast.Call) and (name := call_name(n))
                            }
                        ),
                        side_effect_hints=[
                            hint
                            for hint, pattern in SIDE_EFFECT_HINTS.items()
                            if pattern.search(body_text)
                        ],
                        statements=count_statements(child),
                        is_stub=is_stub(child),
                        mutates_parameters=mutated_parameters(child),
                    )
                )
                visit(child, [*parents, child], f"{qualname}.<locals>.")
            elif isinstance(child, ast.stmt):
                # A def inside if/try/with at any level is still a definition.
                visit(child, parents, prefix)

    visit(tree, [], "")
    return found


# --- tests ----------------------------------------------------------------------


ASSERT_FORMS = {
    ast.Eq: "equality",
    ast.NotEq: "inequality",
    ast.Is: "identity",
    ast.IsNot: "identity",
    ast.In: "membership",
    ast.NotIn: "membership",
    ast.Lt: "ordering",
    ast.LtE: "ordering",
    ast.Gt: "ordering",
    ast.GtE: "ordering",
}


def assert_form(node: ast.Assert) -> str:
    test = node.test
    if isinstance(test, ast.Compare) and test.ops:
        op = test.ops[0]
        if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(
            test.comparators[0], ast.Constant
        ):
            value = test.comparators[0].value
            if value is None:
                return "is_not_none" if isinstance(op, ast.IsNot) else "is_none"
            return "identity_constant"
        return ASSERT_FORMS.get(type(op), "other")
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return "negation"
    if isinstance(test, ast.Call):
        return "call_truthiness"
    return "truthiness"


@dataclass
class TestInfo:
    id: str
    file: str
    name: str
    line: int
    docstring: str
    parametrized: bool
    fixtures: list[str]
    assertions: int
    assert_forms: dict[str, int]
    raises_checks: int
    uses: list[str]
    quality_flags: list[str]
    claims: str


HELPER_HINTS = (
    "ScriptedPolicy",
    "FakeProvider",
    "FakeClient",
    "monkeypatch",
    "mock",
    "fake_transport",
    "importorskip",
)


def collect_tests(path: Path) -> list[TestInfo]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        body_text = ast.unparse(node)
        asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
        forms: dict[str, int] = defaultdict(int)
        for a in asserts:
            forms[assert_form(a)] += 1
        raises = sum(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "raises"
            for n in ast.walk(node)
        )
        decorators = [ast.unparse(d) for d in node.decorator_list]
        parametrized = any("parametrize" in d for d in decorators)
        uses = sorted({h for h in HELPER_HINTS if h in body_text})
        flags = []
        if not asserts and not raises:
            flags.append("no_assertion")
        elif asserts and set(forms) <= WEAK_ASSERT_FORMS and not raises:
            flags.append("weak_assertions_only")
        if "mock" in uses or "monkeypatch" in uses:
            flags.append("patches_dependencies")
        if "skip" in body_text or "importorskip" in uses:
            flags.append("may_skip")
        docstring = ast.get_docstring(node) or ""
        found.append(
            TestInfo(
                id=f"{rel(path)}::{node.name}",
                file=rel(path),
                name=node.name,
                line=node.lineno,
                docstring=docstring[:400],
                parametrized=parametrized,
                fixtures=[a.arg for a in node.args.args],
                assertions=len(asserts),
                assert_forms=dict(sorted(forms.items())),
                raises_checks=raises,
                uses=uses,
                quality_flags=flags,
                claims=(docstring.splitlines()[0] if docstring else "")
                or node.name.removeprefix("test_").replace("_", " "),
            )
        )
    return found


# --- coverage and junit --------------------------------------------------------------


def normalize_context(context: str) -> str | None:
    """'tests/test_x.py::test_name[case]|run' -> 'tests/test_x.py::test_name'."""
    if not context or "::" not in context:
        return None
    context = context.split("|", 1)[0]
    context = re.sub(r"\[.*\]$", "", context)
    return context


def read_coverage(path: Path | None) -> tuple[dict, dict, dict]:
    """Per file: {line: {test ids}}, executed lines, and statement lines."""
    if path is None or not path.exists():
        return {}, {}, {}
    from coverage import CoverageData
    from coverage.parser import PythonParser

    data = CoverageData(basename=str(path))
    data.read()
    contexts: dict[str, dict[int, set[str]]] = {}
    executed: dict[str, set[int]] = {}
    statements: dict[str, set[int]] = {}
    for measured in data.measured_files():
        measured_path = Path(measured)
        name = rel(measured_path) if measured_path.is_relative_to(REPO) else measured
        by_line = data.contexts_by_lineno(measured)
        contexts[name] = {
            line: {c for c in (normalize_context(x) for x in ctxs) if c}
            for line, ctxs in by_line.items()
        }
        executed[name] = set(data.lines(measured) or ())
        if measured_path.exists():
            parser = PythonParser(filename=str(measured_path))
            parser.parse_source()
            statements[name] = set(parser.statements)
    return contexts, executed, statements


def read_junit(path: Path | None) -> dict[str, str]:
    """Test id -> outcome (passed, failed, skipped) from a junit XML."""
    if path is None or not path.exists():
        return {}
    outcomes: dict[str, str] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        classname = case.get("classname", "")
        file = classname.replace(".", "/") + ".py"
        name = re.sub(r"\[.*\]$", "", case.get("name", ""))
        test_id = f"{file}::{name}"
        outcome = "passed"
        for child in case:
            if child.tag in ("failure", "error"):
                outcome = "failed"
            elif child.tag == "skipped":
                outcome = "skipped"
        previous = outcomes.get(test_id)
        if previous == "failed" or (previous == "passed" and outcome == "skipped"):
            continue
        outcomes[test_id] = outcome
    return outcomes


# --- curated notes -------------------------------------------------------------------


def read_curated(name: str) -> dict:
    path = CURATED / name
    if not path.exists():
        return {}
    found = json.loads(path.read_text(encoding="utf-8"))
    return found.get("items", found)


# --- tools ----------------------------------------------------------------------------


def collect_tools() -> list[dict]:
    """Every agent-facing tool from the provider tables, plus recall and manual."""
    sys.path.insert(0, str(SOURCE_ROOT))
    from capstone.providers.factory import (
        PROCEDURE_TOOLS,
        TOOL_ARGUMENTS,
        TOOL_DESCRIPTIONS,
    )
    from capstone.providers.manual import MANUAL_SPEC
    from capstone.providers.recall import RECALL_SPEC

    observation = "capstone.tools.observation:ObservationTools."
    actions = "capstone.tools.actions:ActionTools."
    implementation = {
        "get_time": observation + "get_time",
        "list_machines": observation + "list_machines",
        "get_settings": observation + "get_settings",
        "get_readings": observation + "get_readings",
        "get_sensor_trend": observation + "get_sensor_trend",
        "get_factory_readings": observation + "get_factory_readings",
        "get_sensor_summary": observation + "get_sensor_summary",
        "get_events": observation + "get_events",
        "get_job_history": observation + "get_job_history",
        "get_maintenance_history": observation + "get_maintenance_history",
        "get_inspections": observation + "get_inspections",
        "wait": actions + "wait",
        "propose_action": actions + "propose_action",
        "get_proposals": actions + "get_proposals",
        "execute_action": actions + "execute_action",
        RECALL_SPEC.name: "capstone.providers.recall:RecallingProvider.call",
        MANUAL_SPEC.name: "capstone.providers.manual:ManualProvider.call",
    }
    output_models = {
        "get_time": "ClockObservation",
        "list_machines": "MachineObservation[]",
        "get_settings": "SettingObservation[]",
        "get_readings": "SensorObservation[]",
        "get_sensor_trend": "SensorTrendObservation[]",
        "get_factory_readings": "SensorObservation[]",
        "get_sensor_summary": "SensorSummaryObservation",
        "get_events": "EventObservation[]",
        "get_job_history": "EventObservation[]",
        "get_maintenance_history": "MaintenanceObservation[]",
        "get_inspections": "InspectionObservation[]",
        "wait": "ClockObservation",
        "propose_action": "ProposalObservation",
        "get_proposals": "ProposalObservation[]",
        "execute_action": "ExecutionObservation",
        RECALL_SPEC.name: "RecalledMemory[] (safe view)",
        MANUAL_SPEC.name: "manual section rows (section, title, text, document)",
    }
    tools = []
    for name, description in TOOL_DESCRIPTIONS.items():
        procedure = name in PROCEDURE_TOOLS
        tools.append(
            {
                "name": name,
                "offered_to_policy": not procedure,
                "invoked_by": "loop procedure (propose/execute stages)"
                if procedure
                else "research_agent policy (decide), critic follow-up (read-only "
                "research tools except wait), loop itself (get_time, wait in "
                "execute)",
                "changes_factory": name in ("wait", "execute_action"),
                "needs_human_approval": name == "execute_action",
                "description": description,
                "argument_schema": TOOL_ARGUMENTS[name].model_json_schema(),
                "output_contract": output_models[name],
                "implementation": implementation[name],
                "boundary": "capstone.providers.factory:SimulatorFactoryProvider.call "
                "-> run_tool (argument model, output model rebuild, MAX_ROWS=300, "
                "errors without detail)",
                "simulator_access": "reads sim.readings / event_log / state "
                "through ObservationTools, or ActionTools for wait and the "
                "approval desk; never sim.ground_truth() or MachineCondition",
            }
        )
    for spec, source, limit_note in (
        (
            RECALL_SPEC,
            "memory",
            "at most 3 searches, repeats refused (providers/recall.py)",
        ),
        (
            MANUAL_SPEC,
            "manual",
            "at most 3 searches, repeats refused (providers/manual.py); "
            "sections checked for leaks (manual/sections.py)",
        ),
    ):
        tools.append(
            {
                "name": spec.name,
                "offered_to_policy": True,
                "invoked_by": "research_agent policy when the run offers it; "
                "the manual step also calls search_manual once before planning",
                "changes_factory": False,
                "needs_human_approval": False,
                "description": spec.description,
                "argument_schema": spec.arguments,
                "output_contract": output_models[spec.name],
                "implementation": implementation[spec.name],
                "boundary": f"source {source!r}; the loop labels provenance "
                f"origin={source!r} so verification and the memory gate "
                "discount it",
                "simulator_access": "none; answers come from the memory store "
                "or the manual, stamped with the factory tick only",
                "limits": limit_note,
            }
        )
    return tools


# --- assembly ---------------------------------------------------------------------------


def direct_test_files(module: str) -> set[str]:
    """Conventional test files for a module, e.g. capstone.agent.loop -> agent_loop."""
    parts = module.split(".")[1:]
    candidates = set()
    if parts:
        candidates.add(f"tests/test_{'_'.join(parts)}.py")
        candidates.add(f"tests/test_{parts[-1]}.py")
    return candidates


def capped(items: list, cap: int = LIST_CAP) -> list:
    return items[:cap]


def build(coverage_path: Path | None, junit_path: Path | None, out: Path) -> dict:
    functions: list[FunctionInfo] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        functions.extend(collect_functions(path))
    tests: list[TestInfo] = []
    for path in sorted(TESTS.glob("test_*.py")):
        tests.extend(collect_tests(path))

    contexts, executed, statements = read_coverage(coverage_path)
    outcomes = read_junit(junit_path)
    function_notes = read_curated("function_notes.json")
    test_notes = read_curated("test_notes.json")
    # A curated note for something that no longer exists is a stale judgment.
    unknown = set(function_notes) - {f.id for f in functions}
    unknown |= set(test_notes) - {t.id for t in tests}
    if unknown:
        raise ValueError(
            "curated notes name unknown items: " + ", ".join(sorted(unknown))
        )

    test_to_functions: dict[str, set[str]] = defaultdict(set)
    function_records = []
    for f in functions:
        by_line = contexts.get(f.file, {})
        hit = executed.get(f.file, set())
        body = {
            line
            for line in statements.get(f.file, set())
            if f.line < line <= f.end_line
        }
        executing_tests: set[str] = set()
        for line in body:
            executing_tests.update(by_line.get(line, ()))
        covered = len(body & hit)
        direct_files = direct_test_files(f.module)
        # A test file or test named for the function (get_job_history ->
        # test_job_history.py) counts as direct too.
        core = f.name.lower().removeprefix("get_").strip("_")
        direct = sorted(
            t
            for t in executing_tests
            if t.split("::")[0] in direct_files
            or f.name.lower() in t.split("::")[-1].lower()
            or (len(core) > 4 and core in t.split("::")[0].lower())
        )
        indirect = sorted(executing_tests - set(direct))
        for t in executing_tests:
            test_to_functions[t].add(f.id)
        if f.is_stub or f.statements == 0:
            coverage_class = "no-statements"
        elif not executing_tests:
            coverage_class = "import-only" if covered else "none"
        elif direct:
            coverage_class = "direct"
        else:
            coverage_class = "indirect"
        note = function_notes.get(f.id, {})
        status = note.get("verification_status", STATUS_DEFAULTS[coverage_class])
        if status not in ALLOWED_STATUS:
            raise ValueError(f"{f.id}: unknown status {status!r}")
        callers = sorted(g.id for g in functions if f.name in g.calls and g.id != f.id)
        function_records.append(
            {
                **f.__dict__,
                "static_callers": capped(callers),
                "static_call_graph_note": "approximate: by simple name, dynamic "
                "dispatch and graph steps are not resolved",
                "contract_specified": bool(f.docstring) or f.has_variable_block,
                "executed_in_tests": bool(executing_tests),
                "test_count": len(executing_tests),
                "direct_tests": capped(direct),
                "indirect_tests": capped(indirect),
                "indirect_test_count": len(indirect),
                "statements_executed": covered,
                "statements_in_body": len(body),
                "statement_coverage": round(covered / len(body), 3) if body else None,
                "coverage_class": coverage_class,
                "verification_status": status,
                "status_source": "curated"
                if "verification_status" in note
                else "derived",
                "curated": {
                    k: v for k, v in note.items() if k != "verification_status"
                },
                "snap_questions": ["FN-01", "FN-02", "FN-03"]
                if coverage_class != "no-statements"
                else [],
            }
        )

    test_records = []
    for t in tests:
        exercised = sorted(test_to_functions.get(t.id, ()))
        note = test_notes.get(t.id, {})
        outcome = outcomes.get(t.id, "not_run")
        flags = list(t.quality_flags)
        if not exercised and contexts:
            flags.append("exercises_no_project_function")
        test_records.append(
            {
                **t.__dict__,
                "quality_flags": flags,
                "execution_outcome": outcome,
                "exercises": capped(exercised, 40),
                "exercise_count": len(exercised),
                "modules_exercised": sorted({x.split(":")[0] for x in exercised}),
                "judgment": note.get("judgment", "NOT ASSESSED"),
                "curated": {k: v for k, v in note.items() if k != "judgment"},
                "snap_questions": ["TS-01", "TS-02", "TS-03"],
            }
        )

    tools = collect_tools()
    for tool in tools:
        impl = tool["implementation"]
        record = next((r for r in function_records if r["id"] == impl), None)
        tool["tests"] = (
            [] if record is None else record["direct_tests"] + record["indirect_tests"]
        )
        tool["test_count"] = 0 if record is None else record["test_count"]
        tool["verification_status"] = (
            "NOT TESTED" if record is None else record["verification_status"]
        )
        tool["snap_questions"] = ["TL-01", "TL-02", "TL-03"]

    by_status = defaultdict(int)
    for r in function_records:
        by_status[r["verification_status"]] += 1
    by_module = defaultdict(lambda: {"functions": 0, "executed": 0, "direct": 0})
    for r in function_records:
        m = by_module[r["module"]]
        m["functions"] += 1
        m["executed"] += r["executed_in_tests"]
        m["direct"] += r["coverage_class"] == "direct"
    test_outcomes = defaultdict(int)
    for r in test_records:
        test_outcomes[r["execution_outcome"]] += 1

    matrix = {
        "inventory_version": INVENTORY_VERSION,
        "coverage_file": None if coverage_path is None else str(coverage_path),
        "coverage_available": bool(contexts),
        "junit_available": bool(outcomes),
        "counts": {
            "functions": len(function_records),
            "classes_note": "classes are listed through their methods",
            "tests": len(test_records),
            "tools": len(tools),
            "functions_by_status": dict(sorted(by_status.items())),
            "functions_by_coverage_class": dict(
                sorted(
                    defaultdict(
                        int,
                        {
                            c: sum(r["coverage_class"] == c for r in function_records)
                            for c in STATUS_DEFAULTS
                        },
                    ).items()
                )
            ),
            "functions_executed_in_tests": sum(
                r["executed_in_tests"] for r in function_records
            ),
            "functions_with_direct_tests": sum(
                r["coverage_class"] == "direct" for r in function_records
            ),
            "functions_never_executed": [
                r["id"] for r in function_records if r["coverage_class"] == "none"
            ],
            "functions_executed_only_at_import": [
                r["id"]
                for r in function_records
                if r["coverage_class"] == "import-only"
            ],
            "functions_with_partial_statement_coverage": [
                f"{r['id']} ({r['statements_executed']}/{r['statements_in_body']})"
                for r in function_records
                if r["statement_coverage"] is not None
                and r["statement_coverage"] < 0.8
                and r["executed_in_tests"]
            ],
            "stubs_or_protocols": sum(
                r["coverage_class"] == "no-statements" for r in function_records
            ),
            "tests_by_outcome": dict(sorted(test_outcomes.items())),
            "tests_with_no_assertion": [
                r["id"] for r in test_records if "no_assertion" in r["quality_flags"]
            ],
            "tests_with_weak_assertions_only": [
                r["id"]
                for r in test_records
                if "weak_assertions_only" in r["quality_flags"]
            ],
            "tests_exercising_no_project_function": [
                r["id"]
                for r in test_records
                if "exercises_no_project_function" in r["quality_flags"]
            ],
        },
        "by_module": dict(sorted(by_module.items())),
        "function_to_tests": {
            r["id"]: {
                "count": r["test_count"],
                "status": r["verification_status"],
                "direct": r["direct_tests"][:12],
                "indirect": r["indirect_tests"][:12],
            }
            for r in function_records
        },
        "test_to_functions": {
            r["id"]: {
                "count": r["exercise_count"],
                "judgment": r["judgment"],
                "functions": r["exercises"][:20],
            }
            for r in test_records
        },
        "tool_to_tests": {t["name"]: t["tests"] for t in tools},
        "exclusions": EXCLUSIONS,
        "question_families": {
            "FN": "function-level Snap questions (SNAP_QUESTIONS.json, family FN)",
            "TS": "test-level Snap questions (family TS)",
            "TL": "tool-level Snap questions (family TL)",
        },
    }

    out.mkdir(parents=True, exist_ok=True)
    write = lambda name, payload: (out / name).write_text(  # noqa: E731
        json.dumps(payload, indent=1) + "\n", encoding="utf-8"
    )
    write(
        "FUNCTION_INVENTORY.json",
        {"inventory_version": INVENTORY_VERSION, "functions": function_records},
    )
    write(
        "TEST_INVENTORY.json",
        {"inventory_version": INVENTORY_VERSION, "tests": test_records},
    )
    write(
        "TOOL_INVENTORY.json", {"inventory_version": INVENTORY_VERSION, "tools": tools}
    )
    write("VERIFICATION_MATRIX.json", matrix)
    return matrix


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evaltools.build_inventory")
    parser.add_argument("--coverage", type=Path, help=".coverage with test contexts")
    parser.add_argument("--junit", type=Path, help="junit XML from the same run")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    matrix = build(args.coverage, args.junit, args.out)
    counts = {
        k: (v if not isinstance(v, list) else f"{len(v)} items")
        for k, v in matrix["counts"].items()
    }
    print(json.dumps(counts, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
