"""Exercise evaluator audit provenance and CLI dry-run decision paths.

No test here submits a judge request or starts an agent.
"""

import hashlib
import json

import pytest

from evaltools import full_evaluation, snap_request


def test_provenance_verifies_clean_commit_and_source_hashes(tmp_path, monkeypatch):
    content = tmp_path / "source.py"
    content.write_text("print('synthetic')\n", encoding="utf-8")
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    matrix = {
        "source_sha256": {
            "source.py": hashlib.sha256(content.read_bytes()).hexdigest()
        },
        "coverage_available": True,
        "junit_available": True,
        "coverage_sha256": "coverage-checksum",
        "junit_sha256": "junit-checksum",
    }
    (inventory / "VERIFICATION_MATRIX.json").write_text(
        json.dumps(matrix), encoding="utf-8"
    )
    monkeypatch.setattr(full_evaluation, "REPO", tmp_path)
    monkeypatch.setattr(
        full_evaluation,
        "git",
        lambda *args: "abc123456" if args[0] == "rev-parse" else "",
    )
    proven = full_evaluation.provenance("abc123", inventory, "rubric-v1")
    assert proven["commit_checked_out"] == "abc123456"
    assert proven["inventory_source_hashes_verified"] is True
    assert proven["coverage_sha256"] == "coverage-checksum"
    assert "VERIFICATION_MATRIX.json" in proven["inventory_sha256"]
    content.write_text("print('changed')\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source hash mismatch"):
        full_evaluation.provenance("abc123", inventory, "rubric-v1")


@pytest.mark.parametrize(
    "head, dirty, issue",
    [
        (None, "", "explicit checked-out"),
        ("different123", "", "not the checked-out"),
        ("abc123456", " M tests/new.py", "uncommitted tracked"),
        ("abc123456", None, "uncommitted tracked"),
    ],
)
def test_provenance_refuses_missing_or_dirty_commits(
    tmp_path, monkeypatch, head, dirty, issue
):
    monkeypatch.setattr(
        full_evaluation,
        "git",
        lambda *args: head if args[0] == "rev-parse" else dirty,
    )
    with pytest.raises(ValueError, match=issue):
        full_evaluation.provenance("abc123", tmp_path, "v1")


def test_tracked_files_falls_back_to_filesystem_when_git_unavailable(
    tmp_path, monkeypatch
):
    (tmp_path / "good.py").write_text("x=1")
    for ignored in (".venv", ".pytest-tmp"):
        folder = tmp_path / ignored
        folder.mkdir()
        (folder / "ignored.py").write_text("x=0")
    monkeypatch.setattr(full_evaluation, "REPO", tmp_path)
    monkeypatch.setattr(full_evaluation, "git", lambda *args: None)
    assert full_evaluation.tracked_python_files() == ["good.py"]


def test_plan_records_functions_that_do_not_have_snap_questions(tmp_path, monkeypatch):
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    for name, payload in (
        (
            "FUNCTION_INVENTORY.json",
            {
                "functions": [
                    {
                        "id": "module:synthetic",
                        "snap_questions": [],
                        "verification_status": "NOT APPLICABLE",
                    }
                ]
            },
        ),
        ("TEST_INVENTORY.json", {"tests": []}),
        ("TOOL_INVENTORY.json", {"tools": []}),
    ):
        (inventory / name).write_text(json.dumps(payload), encoding="utf-8")
    result = full_evaluation.plan(
        inventory=inventory,
        archives=[],
        providers=[full_evaluation.PROVIDERS["snap"]],
        out=tmp_path / "requests",
        commit="abc123",
        families=("FN",),
    )
    assert result["built"] == []
    assert result["packets"] == []
    assert result["functions"]["module:synthetic"]["snap_questions"] == []
    assert result["rows"]
    assert all(
        row["status"] == "not_applicable" and row["family"] == "FN"
        for row in result["rows"]
    )


@pytest.mark.parametrize(
    "answer, expected_status",
    [
        ({"error": "provider failed", "answers": []}, "failed"),
        ({"error": None, "answers": []}, "unreadable"),
        (
            {
                "error": None,
                "answers": [{"question_id": "FN-01", "value": None, "error": "bad"}],
            },
            "unreadable",
        ),
        (
            {
                "error": None,
                "answers": [{"question_id": "FN-01", "value": 3}],
            },
            "answered",
        ),
    ],
)
def test_settle_preserves_failed_unreadable_and_answered_outcomes(
    tmp_path, answer, expected_status
):
    stored = {"tags": {"request_fingerprint": "fingerprint"}, **answer}
    (tmp_path / "item.answers.json").write_text(json.dumps(stored), encoding="utf-8")
    row = {
        "family": "FN",
        "status": "planned",
        "question_id": "FN-01",
        "request_fingerprint": "fingerprint",
    }
    unchanged = {"family": "TS", "status": "refused", "question_id": "TS-01"}
    result = full_evaluation.settle([row, unchanged], tmp_path)
    assert result[0]["status"] == expected_status
    assert result[1] == unchanged
    if expected_status == "answered":
        assert result[0]["value"] == 3


def test_budgeted_send_blocks_unknown_provider_without_network(tmp_path):
    result = full_evaluation.budgeted_send(
        [
            {
                "body": {"state": "synthetic"},
                "tags": {"provider": "jev"},
            }
        ],
        tmp_path,
        max_new_requests=1,
        max_usd=2.0,
        max_seconds=1.0,
        transport=lambda *args, **kwargs: pytest.fail("no request permitted"),
        clock=lambda: 0.0,
    )
    assert result["sent"] == 0
    assert result["stop_reason"] == "provider_context_unverified"


@pytest.mark.parametrize("maximum", [0, -1])
def test_budgeted_send_rejects_invalid_request_limits(tmp_path, maximum):
    with pytest.raises(ValueError, match="positive and finite"):
        full_evaluation.budgeted_send(
            [],
            tmp_path,
            max_new_requests=maximum,
            max_usd=1.0,
            max_seconds=5.0,
        )


def prepare_cli_stubs(monkeypatch, events):
    """Isolate the reporting CLI from provenance and external services."""
    monkeypatch.setattr(full_evaluation, "readiness", lambda providers: {})
    monkeypatch.setattr(
        snap_request,
        "load_questions",
        lambda *args: ({"rubric_version": "v1"}, []),
    )
    monkeypatch.setattr(
        full_evaluation,
        "provenance",
        lambda commit, inventory, rubric: {"commit": commit},
    )
    planned = {
        "built": [],
        "rows": [],
        "packets": [],
        "refused_packets": [],
        "functions": {},
        "tests": {},
    }
    monkeypatch.setattr(
        full_evaluation,
        "plan",
        lambda **kwargs: (events.append(("plan", kwargs)), planned)[1],
    )
    monkeypatch.setattr(
        full_evaluation,
        "budget",
        lambda built: {"requests": 0, "cost_usd_estimate": 0},
    )
    monkeypatch.setattr(full_evaluation, "settle", lambda rows, folder: [])
    monkeypatch.setattr(
        full_evaluation,
        "scope_manifest",
        lambda functions, tests: {"unexplained": []},
    )
    monkeypatch.setattr(
        full_evaluation,
        "report",
        lambda *args: {"missingness": {"unknown": 0}},
    )
    monkeypatch.setattr(full_evaluation, "markdown", lambda report: "# Verified\n")
    monkeypatch.setattr(
        snap_request,
        "write_requests",
        lambda requests, directory, *, send_them: {"failed": 0},
    )


def test_full_evaluation_cli_offline_report_and_reference_checksum(
    tmp_path, monkeypatch
):
    events = []
    prepare_cli_stubs(monkeypatch, events)
    reference = tmp_path / "human.json"
    reference.write_text("{}\n", encoding="utf-8")
    out = tmp_path / "report"
    assert (
        full_evaluation.main(
            [
                "--commit",
                "abc123",
                "--provider",
                "snap",
                "--snap-full-context",
                "--out",
                str(out),
                "--reference",
                str(reference),
                "--families",
                "FN",
            ]
        )
        == 0
    )
    assert json.loads((out / "report.json").read_text())["reference_sha256"] == (
        hashlib.sha256(reference.read_bytes()).hexdigest()
    )
    assert (out / "report.md").read_text() == "# Verified\n"
    assert (out / "scope_manifest.json").exists()
    assert events[0][0] == "plan"
    assert events[0][1]["families"] == ("FN",)


def test_full_evaluation_cli_reports_incomplete_live_answers_as_failure(
    tmp_path, monkeypatch
):
    events = []
    prepare_cli_stubs(monkeypatch, events)
    monkeypatch.setattr(
        full_evaluation,
        "budgeted_send",
        lambda *args, **kwargs: {
            "sent": 1,
            "stop_reason": "incomplete_answer",
            "spent_usd": 0.1,
        },
    )
    out = tmp_path / "attempt"
    assert (
        full_evaluation.main(
            [
                "--provider",
                "snap",
                "--out",
                str(out),
                "--send",
                "--max-requests",
                "1",
                "--max-usd",
                "1.0",
            ]
        )
        == 2
    )
    assert (
        json.loads((out / "report.json").read_text())["live_budget"]["stop_reason"]
        == "incomplete_answer"
    )


def test_full_evaluation_cli_requires_full_audit_before_dispatch(
    tmp_path, monkeypatch, capsys
):
    events = []
    prepare_cli_stubs(monkeypatch, events)

    def broken(*args, **kwargs):
        raise ValueError("no full traces")

    monkeypatch.setattr(full_evaluation.audit_preflight, "require_full_traces", broken)
    with pytest.raises(SystemExit) as stopped:
        full_evaluation.main(
            [
                "--out",
                str(tmp_path / "report"),
                "--provider",
                "snap",
                "--require-full-traces",
            ]
        )
    assert stopped.value.code == 2
    assert "no full traces" in capsys.readouterr().err
