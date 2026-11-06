"""The full-project evaluation command (evaluation/evaltools/full_evaluation.py).

Planned over the archived PR #156 pairs, offline: no model is called; sending
goes through a fake transport.
"""

import json
import os
from collections import Counter
from types import SimpleNamespace

import pytest

from evaltools import full_evaluation, run_packet, snap_request
from evaltools.decision_models import PROVIDERS
from tests.test_evaluation_tools import (
    AUDITED_FIVE,
    PUBLISHED,
    TOT13_PAIRS,
    fake_transport,
)

JEV = [PROVIDERS["jev"]]


@pytest.fixture(scope="module")
def planned(tmp_path_factory):
    """The RUN and BT plan for the archive, for Jev alone."""
    out = tmp_path_factory.mktemp("full")
    result = full_evaluation.plan(
        inventory=snap_request.INVENTORY,
        archives=[TOT13_PAIRS],
        providers=JEV,
        out=out,
        commit=None,
        families=("RUN", "BT"),
    )
    return out, result


def test_every_episode_and_question_has_one_ledger_row(planned):
    """52 episodes x 12 RUN questions, each once, each with a status."""
    _, result = planned
    run_rows = [r for r in result["rows"] if r["family"] == "RUN"]
    keys = [(r["item_id"], r["question_id"]) for r in run_rows]
    assert len(result["packets"]) == 52
    assert len(keys) == len(set(keys)) == 52 * 12
    allowed = {"planned", *full_evaluation.SKIP_STATUSES, "unfittable", "refused"}
    assert {r["status"] for r in run_rows} <= allowed
    assert result["refused_packets"] == []


def test_refused_episode_keeps_every_run_question_row(tmp_path, monkeypatch):
    """An invalid episode is still counted in the RUN ledger."""
    from evaltools import run_packet

    def refuse_archive(_archive, *, refused):
        refused.append({"episode_key": "pair::run/1/KA-01", "reason": "invalid trace"})
        return []

    monkeypatch.setattr(run_packet, "build_archive", refuse_archive)
    result = full_evaluation.plan(
        inventory=snap_request.INVENTORY,
        archives=[tmp_path],
        providers=JEV,
        out=tmp_path,
        commit=None,
        families=("RUN",),
    )
    rows = result["rows"]
    assert len(rows) == 12
    assert {row["status"] for row in rows} == {"refused"}
    assert {row["item_id"] for row in rows} == {"pair::run/1/KA-01"}
    assert result["built"] == []


def test_the_report_keeps_the_published_denominators(planned):
    """Correctness per arm is the published n/judged with the pending labels."""
    _, result = planned
    rows = full_evaluation.settle(result["rows"], planned[0] / "requests")
    report = full_evaluation.report(
        result,
        rows,
        {"counts": {}, "unexplained": [], "stale": []},
        {"commit_pinned": None},
        full_evaluation.budget(result["built"]),
    )
    found = {
        (run["namespace"], run["run"]): (
            run["correct_of_judged"]["n"],
            run["correct_of_judged"]["of"],
            run["pending_review"],
        )
        for run in report["correctness"]["runs"]
    }
    assert found == PUBLISHED
    assert "score" not in json.dumps(report["correctness"]).lower()


def test_per_item_findings_join_truth_judge_and_blinded_reference():
    """A high RUN-12 true preference supports, rather than defeats, grounding."""
    # Variables:
    #   packet: A saved audited run; its truth stays in the local report.
    #   rows: Normalized judge answers for the three grounding questions.
    packet = run_packet.build_archive(AUDITED_FIVE)[0]
    item_id = packet.meta.episode_key
    rows = [
        {
            "family": "RUN",
            "item_id": item_id,
            "provider": "snap",
            "question_id": q,
            "status": "answered",
            "value": value,
        }
        for q, value in (("RUN-01", 3.5), ("RUN-08", 3.5), ("RUN-12", 0.9))
    ]
    findings = full_evaluation.item_findings(
        {"packets": [packet], "functions": {}, "tests": {}},
        rows,
        {item_id: {"RUN-12": True}},
    )
    (finding,) = findings
    assert finding["trace_completeness"] == "full"
    assert finding["fully_right"] == packet.evaluator_only.fully_right
    assert finding["questions"]["RUN-12"]["agrees_with_reference"] is True
    assert finding["evidence_grounded"] == bool(packet.evaluator_only.fully_right)
    assert finding["misleading_success"] is False


def test_each_pair_is_compared_and_the_sample_rule_is_applied_in_code(planned):
    """Two comparisons (one per pair); 11 matched cases is under the 13 needed."""
    _, result = planned
    compared = result["comparisons"]
    assert len(compared) == 2
    for comparison in compared:
        rule = comparison["sample_rule"]
        assert rule["matched_judged"] == 11
        assert rule["rule"] == "insufficient_sample"
    bt_rows = [r for r in result["rows"] if r["family"] == "BT"]
    assert len(bt_rows) == 2 * 2 and {r["status"] for r in bt_rows} == {"planned"}


def test_a_comparison_request_names_no_scenario_or_run_key(planned):
    """The BT state carries outcomes by case number, never the fault's name."""
    _, result = planned
    bodies = [
        json.dumps(item["body"]).lower()
        for item in result["built"]
        if item["tags"]["family"] == "BT"
    ]
    assert len(bodies) == 2
    for packet in result["packets"]:
        for word in (packet.meta.scenario_id, packet.meta.run_key):
            assert all(word.lower() not in body for body in bodies)


def test_the_sample_rule_is_met_with_enough_matched_cases(planned, monkeypatch):
    _, result = planned
    monkeypatch.setattr(full_evaluation, "MATCHED_CASES_NEEDED", 11)
    a = [
        p
        for p in result["packets"]
        if p.meta.run_key.startswith("master-tot13-anchored")
    ]
    b = [
        p for p in result["packets"] if p.meta.run_key.startswith("master-tot13-blind")
    ]
    namespace = a[0].meta.namespace
    rule = full_evaluation.sample_rule(
        [p for p in a if p.meta.namespace == namespace],
        [p for p in b if p.meta.namespace == namespace],
    )
    assert rule["rule"] == "sample_condition_met"


def test_answers_settle_the_ledger_by_fingerprint(planned, tmp_path, monkeypatch):
    """Sent answers mark rows answered; a failed request marks them failed."""
    _, result = planned
    bt = [item for item in result["built"] if item["tags"]["family"] == "BT"]
    reply = {
        "model": "m",
        "answers": {
            "comparison_valid": {"type": "choice", "choice": "valid"},
            "improvement_supported": {"type": "choice", "choice": "not_an_option"},
        },
    }
    monkeypatch.setenv(PROVIDERS["jev"].key_env, "test-key")
    snap_request.write_requests(
        bt[:1],
        tmp_path,
        send_them=True,
        transport=fake_transport([reply]),
        retries=0,
    )
    snap_request.write_requests(
        bt[1:],
        tmp_path,
        send_them=True,
        transport=fake_transport([OSError("no route")]),
        retries=0,
    )
    rows = [r for r in result["rows"] if r["family"] == "BT"]
    settled = {
        (r["item_id"], r["question_id"]): r["status"]
        for r in full_evaluation.settle(rows, tmp_path)
    }
    first, second = bt[0]["tags"]["item_id"], bt[1]["tags"]["item_id"]
    assert settled[(first, "BT-01")] == "answered"
    assert settled[(first, "BT-02")] == "unreadable"
    assert settled[(second, "BT-01")] == settled[(second, "BT-02")] == "failed"


def test_an_answer_to_another_request_settles_nothing(planned, tmp_path):
    _, result = planned
    rows = [r for r in result["rows"] if r["family"] == "BT"]
    (tmp_path / "x.answers.json").write_text(
        json.dumps(
            {
                "tags": {"request_fingerprint": "0" * 64},
                "answers": [{"question_id": "BT-01", "value": "valid"}],
            }
        ),
        encoding="utf-8",
    )
    assert {r["status"] for r in full_evaluation.settle(rows, tmp_path)} == {"planned"}


def test_small_batches_resume_without_resending_completed_requests(
    planned, tmp_path, monkeypatch
):
    """A large plan can advance through saved answers one request at a time."""
    _, result = planned
    bt = [item for item in result["built"] if item["tags"]["family"] == "BT"]
    assert len(bt) == 2
    first = full_evaluation.pending_batch(bt, tmp_path, 1)
    assert first == bt[:1]
    monkeypatch.setenv(PROVIDERS["jev"].key_env, "test-key")
    reply = {
        "model": "m",
        "answers": {
            "comparison_valid": {"type": "choice", "choice": "valid"},
            "improvement_supported": {
                "type": "choice",
                "choice": "insufficient_sample",
            },
        },
    }
    snap_request.write_requests(
        first, tmp_path, send_them=True, transport=fake_transport([reply]), retries=0
    )
    assert full_evaluation.pending_batch(bt, tmp_path, 1) == bt[1:]
    assert full_evaluation.pending_batch(bt, tmp_path, 2) == bt[1:]
    with pytest.raises(ValueError, match="positive"):
        full_evaluation.pending_batch(bt, tmp_path, 0)


def test_budgeted_send_reserves_before_post_and_resumes_from_measured_usage(
    tmp_path, monkeypatch
):
    """A small slice cannot overspend or repay a completed request on resume."""
    _, questions = snap_request.load_questions()
    items = [
        snap_request.build_request(
            {"case": n},
            questions[:1],
            model=PROVIDERS["snap"].model,
            item_id=f"case-{n}",
            meta={"family": "FN"},
            provider="snap",
        )[0]
        for n in (1, 2)
    ]
    monkeypatch.setenv(PROVIDERS["snap"].key_env, "test-key")
    reply = {
        "model": PROVIDERS["snap"].model,
        "usage": {"input_tokens": 100, "output_tokens": 0},
        "answers": {questions[0].name: {"type": "score", "score": 3.0}},
    }
    sent = []

    def transport(url, headers, data, timeout):
        sent.append(data)
        return json.dumps(reply).encode()

    first = full_evaluation.budgeted_send(
        items,
        tmp_path,
        max_new_requests=1,
        max_usd=0.02,
        max_seconds=30,
        transport=transport,
    )
    assert first["sent"] == 1
    assert len(sent) == 1
    assert first["spent_usd"] < 0.02
    second = full_evaluation.budgeted_send(
        items,
        tmp_path,
        max_new_requests=1,
        max_usd=0.02,
        max_seconds=30,
        transport=transport,
    )
    assert second["sent"] == 1
    assert len(sent) == 2
    assert second["spent_usd"] < 0.02


def test_budgeted_send_keeps_uncertain_charge_reserved_and_stops(tmp_path, monkeypatch):
    """Missing usage leaves a charge reserved and prevents another paid post."""
    _, questions = snap_request.load_questions()
    items = [
        snap_request.build_request(
            {"case": n},
            questions[:1],
            model=PROVIDERS["snap"].model,
            item_id=f"case-{n}",
            meta={"family": "FN"},
            provider="snap",
        )[0]
        for n in (1, 2)
    ]
    monkeypatch.setenv(PROVIDERS["snap"].key_env, "test-key")
    reply = {"answers": {questions[0].name: {"type": "score", "score": 3.0}}}
    sent = []

    def transport(url, headers, data, timeout):
        sent.append(data)
        return json.dumps(reply).encode()

    result = full_evaluation.budgeted_send(
        items,
        tmp_path,
        max_new_requests=2,
        max_usd=0.02,
        max_seconds=30,
        transport=transport,
    )
    assert len(sent) == 1
    assert result["stop_reason"] == "usage_unknown"
    resumed = full_evaluation.budgeted_send(
        items,
        tmp_path,
        max_new_requests=2,
        max_usd=0.02,
        max_seconds=30,
        transport=transport,
    )
    assert len(sent) == 1
    assert resumed["stop_reason"] == "usage_unknown"


def test_budgeted_send_refuses_a_charge_larger_than_the_remaining_cap(
    tmp_path, monkeypatch
):
    """The whole possible input charge is reserved before any paid post."""
    _, questions = snap_request.load_questions()
    item = snap_request.build_request(
        {"case": 1},
        questions[:1],
        model=PROVIDERS["snap"].model,
        item_id="case-1",
        meta={"family": "FN"},
        provider="snap",
    )[0]
    monkeypatch.setenv(PROVIDERS["snap"].key_env, "test-key")
    sent = []

    def transport(url, headers, data, timeout):
        sent.append(data)
        return b"{}"

    result = full_evaluation.budgeted_send(
        [item],
        tmp_path,
        max_new_requests=1,
        max_usd=0.001,
        max_seconds=30,
        transport=transport,
    )
    assert result["stop_reason"] == "usd_limit"
    assert sent == []
    assert not list(tmp_path.glob("*.reservation.json"))


def test_budgeted_send_reserves_the_documented_binary_context_window(
    tmp_path, monkeypatch
):
    """Snap's 384K window is 393,216 tokens, not a decimal 384,000."""
    _, questions = snap_request.load_questions()
    item = snap_request.build_request(
        {"case": 1},
        questions[:1],
        model=PROVIDERS["snap"].model,
        item_id="case-1",
        meta={"family": "FN"},
        provider="snap",
    )[0]
    monkeypatch.setenv(PROVIDERS["snap"].key_env, "test-key")
    sent = []

    def transport(url, headers, data, timeout):
        sent.append(data)
        return b"{}"

    between = 384_000 * 0.04 / 1_000_000 + 0.0001
    result = full_evaluation.budgeted_send(
        [item],
        tmp_path,
        max_new_requests=1,
        max_usd=between,
        max_seconds=30,
        transport=transport,
    )
    assert result["stop_reason"] == "usd_limit"
    assert sent == []


def test_budgeted_send_rejects_nonfinite_limits(tmp_path):
    """NaN or infinity cannot turn the dollar or time guard off."""
    with pytest.raises(ValueError, match="finite"):
        full_evaluation.budgeted_send(
            [],
            tmp_path,
            max_new_requests=1,
            max_usd=float("nan"),
            max_seconds=30,
        )
    with pytest.raises(ValueError, match="finite"):
        full_evaluation.budgeted_send(
            [],
            tmp_path,
            max_new_requests=1,
            max_usd=1,
            max_seconds=float("inf"),
        )


def test_unverified_provider_is_refused_before_a_mixed_batch_posts(
    tmp_path, monkeypatch
):
    """A both-provider plan makes no paid call if either price is unknown."""
    _, questions = snap_request.load_questions()
    items = [
        snap_request.build_request(
            {"case": 1},
            questions[:1],
            model=PROVIDERS[name].model,
            item_id=name,
            meta={"family": "FN"},
            provider=name,
        )[0]
        for name in ("snap", "jev")
    ]
    monkeypatch.setenv(PROVIDERS["snap"].key_env, "test-key")
    sent = []

    def transport(url, headers, data, timeout):
        sent.append(data)
        return b"{}"

    result = full_evaluation.budgeted_send(
        items,
        tmp_path,
        max_new_requests=2,
        max_usd=1,
        max_seconds=30,
        transport=transport,
    )
    assert result["stop_reason"] == "provider_context_unverified"
    assert sent == []


def test_a_saved_reply_finishes_an_interrupted_reservation(tmp_path, monkeypatch):
    """A crash after saving the reply can resume without another paid post."""
    _, questions = snap_request.load_questions()
    items = [
        snap_request.build_request(
            {"case": n},
            questions[:1],
            model=PROVIDERS["snap"].model,
            item_id=f"case-{n}",
            meta={"family": "FN"},
            provider="snap",
        )[0]
        for n in (1, 2)
    ]
    monkeypatch.setenv(PROVIDERS["snap"].key_env, "test-key")
    reply = {
        "usage": {"input_tokens": 100, "output_tokens": 0},
        "answers": {questions[0].name: {"type": "score", "score": 3.0}},
    }
    sent = []

    def transport(url, headers, data, timeout):
        sent.append(data)
        return json.dumps(reply).encode()

    snap_request.write_requests(
        items[:1], tmp_path, send_them=True, transport=transport, retries=0
    )
    stem = snap_request.file_stem(items[0]["tags"])
    snap_request.write_json(
        tmp_path / f"{stem}.reservation.json",
        {
            "request_fingerprint": items[0]["tags"]["request_fingerprint"],
            "provider": "snap",
            "charge_usd": 0.01572864,
            "status": "reserved",
        },
    )
    result = full_evaluation.budgeted_send(
        items,
        tmp_path,
        max_new_requests=1,
        max_usd=0.02,
        max_seconds=30,
        transport=transport,
    )
    assert result["sent"] == 1
    assert len(sent) == 2


def test_malformed_usage_stops_with_a_visible_reason(tmp_path, monkeypatch):
    """A malformed provider usage field is an unknown charge, not a crash."""
    _, questions = snap_request.load_questions()
    item = snap_request.build_request(
        {"case": 1},
        questions[:1],
        model=PROVIDERS["snap"].model,
        item_id="case-1",
        meta={"family": "FN"},
        provider="snap",
    )[0]
    monkeypatch.setenv(PROVIDERS["snap"].key_env, "test-key")
    reply = {
        "usage": "bad usage",
        "answers": {questions[0].name: {"type": "score", "score": 3.0}},
    }

    def transport(url, headers, data, timeout):
        return json.dumps(reply).encode()

    result = full_evaluation.budgeted_send(
        [item],
        tmp_path,
        max_new_requests=1,
        max_usd=0.02,
        max_seconds=30,
        transport=transport,
    )
    assert result["stop_reason"] == "usage_unknown"
    assert result["spent_usd"] > 0


def test_full_command_uses_budgeted_sender(tmp_path, monkeypatch):
    """The full command applies its limits to new sends, not the whole plan."""
    monkeypatch.setattr(
        full_evaluation,
        "provenance",
        lambda *args: {
            "commit_pinned": "test",
            "commit_checked_out": "test",
            "tracked_changes_uncommitted": False,
            "rubric_version": "test",
            "packet_schema_version": "test",
            "normalize_version": "test",
        },
    )
    called = []

    def bounded(items, folder, **limits):
        called.append(limits)
        return {"sent": 0, "spent_usd": 0, "stop_reason": "request_limit"}

    monkeypatch.setattr(full_evaluation, "budgeted_send", bounded)
    status = full_evaluation.main(
        [
            "--archive",
            str(TOT13_PAIRS),
            "--families",
            "BT",
            "--provider",
            "snap",
            "--out",
            str(tmp_path),
            "--send",
            "--max-requests",
            "1",
            "--max-usd",
            "0.02",
            "--max-seconds",
            "15",
        ]
    )
    assert status == 0
    assert called[0]["max_new_requests"] == 1
    assert called[0]["max_seconds"] == 15


def test_a_plan_over_budget_is_refused_before_sending(tmp_path, monkeypatch):
    """Nothing is written as answers, and no key is needed to be refused."""
    monkeypatch.delenv(PROVIDERS["jev"].key_env, raising=False)
    monkeypatch.setattr(
        full_evaluation,
        "provenance",
        lambda *args: {
            "commit_pinned": "test",
            "commit_checked_out": "test",
            "tracked_changes_uncommitted": False,
            "rubric_version": "test",
            "packet_schema_version": "test",
            "normalize_version": "test",
        },
    )
    status = full_evaluation.main(
        [
            "--archive",
            str(TOT13_PAIRS),
            "--families",
            "BT",
            "--provider",
            "jev",
            "--out",
            str(tmp_path),
            "--send",
            "--max-requests",
            "1",
            "--max-usd",
            "1",
        ]
    )
    assert status == 2
    assert not list(tmp_path.rglob("*.answers.json"))


def test_the_budget_counts_the_whole_request_with_a_margin():
    """The questions are paid for too; the 2026-11-02 Jev pilot billed 1.2-1.4x
    the four-characters-per-token estimate of the whole body."""
    from evaltools.decision_models import estimate_tokens

    questions = {f"q{i}": {"type": "noul", "text": "x" * 4000} for i in range(3)}
    body = {"model": "jev-1.14.0", "state": {"a": "y" * 400}, "questions": questions}
    item = {
        "body": body,
        "tags": {
            "provider": "jev",
            "state_tokens_estimate": estimate_tokens(body["state"]),
        },
    }
    spend = full_evaluation.budget([item])["per_provider"]["jev"]
    whole = estimate_tokens(body)
    assert spend["input_tokens_estimate"] >= 1.4 * whole
    # The pilot's real counts against this estimate: every one stays under it.
    for body_estimate, billed in [
        (1098, 1529),
        (1105, 1386),
        (1036, 1314),
        (1495, 1763),
        (1175, 1515),
    ]:
        assert full_evaluation.request_tokens_estimate(body_estimate) >= billed


def test_sending_needs_both_limits(tmp_path):
    with pytest.raises(SystemExit):
        full_evaluation.main(["--out", str(tmp_path), "--send", "--max-usd", "1"])


def test_a_dry_run_writes_the_ledger_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(
        full_evaluation,
        "provenance",
        lambda *args: {
            "commit_pinned": "test",
            "commit_checked_out": "test",
            "tracked_changes_uncommitted": False,
            "rubric_version": "1.0.0",
            "packet_schema_version": "test",
            "normalize_version": "test",
        },
    )
    status = full_evaluation.main(
        [
            "--archive",
            str(TOT13_PAIRS),
            "--families",
            "BT",
            "--provider",
            "jev",
            "--out",
            str(tmp_path),
        ]
    )
    assert status == 0
    for name in ("ledger.jsonl", "report.json", "report.md", "scope_manifest.json"):
        assert (tmp_path / name).exists()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["judging"]["by_status"] == {"planned": 4}
    assert report["missingness"] == {"planned": 4}
    assert "no single blended score" in (tmp_path / "report.md").read_text("utf-8")


def test_a_pinned_commit_that_is_not_checked_out_is_refused():
    if full_evaluation.git("rev-parse", "HEAD") is None:
        pytest.skip("not a git checkout")
    with pytest.raises(ValueError, match="not the checked-out commit"):
        full_evaluation.provenance("0" * 40, snap_request.INVENTORY, "1.0.0")


def test_provenance_needs_an_explicit_clean_commit(monkeypatch):
    head = "a" * 40
    monkeypatch.setattr(
        full_evaluation,
        "git",
        lambda *args: head if args == ("rev-parse", "HEAD") else " M example.py",
    )
    with pytest.raises(ValueError, match="explicit"):
        full_evaluation.provenance(None, snap_request.INVENTORY, "1.0.0")
    with pytest.raises(ValueError, match="uncommitted"):
        full_evaluation.provenance(head, snap_request.INVENTORY, "1.0.0")


def test_the_scope_manifest_classes_every_file(monkeypatch):
    monkeypatch.setattr(full_evaluation, "has_functions", lambda path: True)
    functions = {
        "a:f": {"file": "capstone-code/capstone/a.py"},
        "gone:f": {"file": "capstone-code/capstone/gone.py"},
    }
    tests = {"tests/test_a.py::t": {"file": "tests/test_a.py"}}
    scope = full_evaluation.scope_manifest(
        functions,
        tests,
        files=[
            "capstone-code/capstone/a.py",
            "tests/test_a.py",
            "tests/helpers.py",
            "evaluation/evaltools/x.py",
            "capstone-code/capstone/new.py",
        ],
    )
    classes = {f: e["class"] for f, e in scope["files"].items()}
    assert classes == {
        "capstone-code/capstone/a.py": "inventoried",
        "tests/test_a.py": "tests",
        "tests/helpers.py": "test_support",
        "evaluation/evaltools/x.py": "unexplained",
        "capstone-code/capstone/new.py": "unexplained",
    }
    assert scope["unexplained"] == [
        "capstone-code/capstone/new.py",
        "evaluation/evaltools/x.py",
    ]
    assert scope["stale"] == ["capstone-code/capstone/gone.py"]


def test_the_repository_has_no_unexplained_python_file():
    """Every tracked Python file is inventoried, a test, excluded with a reason,
    or holds no function; a new module the inventory misses fails here."""
    functions = {
        f["id"]: f
        for f in json.loads(
            (snap_request.INVENTORY / "FUNCTION_INVENTORY.json").read_text("utf-8")
        )["functions"]
    }
    tests = {
        t["id"]: t
        for t in json.loads(
            (snap_request.INVENTORY / "TEST_INVENTORY.json").read_text("utf-8")
        )["tests"]
    }
    scope = full_evaluation.scope_manifest(functions, tests)
    assert scope["unexplained"] == []
    assert scope["stale"] == []


def test_a_new_evaluator_function_requires_inventory_regeneration(monkeypatch):
    path = "evaluation/evaltools/full_evaluation.py"
    indexed = "evaltools.full_evaluation:existing"
    added = "evaltools.full_evaluation:new_function"
    monkeypatch.setattr(
        full_evaluation.build_inventory,
        "collect_functions",
        lambda _path: [SimpleNamespace(id=indexed), SimpleNamespace(id=added)],
    )
    scope = full_evaluation.scope_manifest({indexed: {"file": path}}, {}, files=[path])
    assert scope["unexplained"] == [added]


# --- F06: pairing by scenario and seed ---------------------------------------------


def _one_pair(result):
    """The anchored and blind runs of one archived pair."""
    namespace = result["packets"][0].meta.namespace
    group = [p for p in result["packets"] if p.meta.namespace == namespace]
    a = [p for p in group if p.meta.run_key.startswith("master-tot13-anchored")]
    b = [p for p in group if p.meta.run_key.startswith("master-tot13-blind")]
    return a, b


def _with_meta(packet, **update):
    return packet.model_copy(update={"meta": packet.meta.model_copy(update=update)})


def test_archived_cases_pair_by_scenario_and_seed(planned):
    """Every archived packet carries its seed, and the two arms pair on it."""
    _, result = planned
    assert all(p.meta.seed is not None for p in result["packets"])
    a, b = _one_pair(result)
    rule = full_evaluation.sample_rule(a, b)
    assert rule["paired_by_scenario_and_seed"] == len(a) == len(b)
    assert rule["ambiguous"] == rule["position_mismatches"] == 0
    assert rule["unpaired_a"] == rule["unpaired_b"] == 0


def test_reordered_cases_still_pair_and_the_reordering_is_flagged(planned):
    """Rotating B's case numbers changes no pairing, but is reported."""
    _, result = planned
    a, b = _one_pair(result)
    numbers = [full_evaluation.case_number(p) for p in b]
    rotated = [
        _with_meta(
            p,
            run_key=p.meta.run_key.replace(
                f"/{n}/", f"/{numbers[(i + 1) % len(numbers)]}/", 1
            ),
        )
        for i, (p, n) in enumerate(zip(b, numbers, strict=True))
    ]
    before = full_evaluation.sample_rule(a, b)
    after = full_evaluation.sample_rule(a, rotated)
    assert after["matched_judged"] == before["matched_judged"]
    assert after["right_on_matched_b"] == before["right_on_matched_b"]
    assert after["position_mismatches"] == len(b)


def test_a_differently_seeded_case_is_not_paired(planned):
    """Same slot and scenario but another seed is a different case."""
    _, result = planned
    a, b = _one_pair(result)
    changed = [_with_meta(b[0], seed=b[0].meta.seed + 1000), *b[1:]]
    rule = full_evaluation.sample_rule(a, changed)
    assert rule["paired_by_scenario_and_seed"] == len(a) - 1
    assert rule["unpaired_a"] == rule["unpaired_b"] == 1
    assert rule["position_mismatches"] == 1
    compared = full_evaluation.match_cases(a, changed)
    assert compared["only_b"][0].meta.seed == b[0].meta.seed + 1000


def test_a_case_without_a_seed_or_with_a_repeated_one_is_ambiguous(planned):
    _, result = planned
    a, b = _one_pair(result)
    no_seed = [_with_meta(a[0], seed=None), *a[1:]]
    assert full_evaluation.sample_rule(no_seed, b)["ambiguous"] == 1
    repeated = [*a, _with_meta(a[0], run_key=a[0].meta.run_key + "-again")]
    rule = full_evaluation.sample_rule(repeated, b)
    assert rule["ambiguous"] == 2
    assert rule["paired_by_scenario_and_seed"] == len(a) - 1


# --- F04 / T24: a large plan through many small fake slices ------------------------


def _answering_transport(input_tokens):
    """A fake Snap that answers every question of every body, and keeps each post."""
    posts = []

    def transport(url, headers, data, timeout):
        body = json.loads(data)
        posts.append(body)
        answers = {}
        for name, question in body["questions"].items():
            if question["type"] == "noul":
                answers[name] = {"type": "noul", "noul": 0.7}
            elif question["type"] == "choice":
                first = next(iter(question["criteria"]))
                answers[name] = {"type": "choice", "choice": first}
            else:
                answers[name] = {"type": "score", "score": 0}
        reply = {
            "model": PROVIDERS["snap"].model,
            "usage": {"input_tokens": input_tokens, "output_tokens": 0},
            "answers": answers,
        }
        return json.dumps(reply).encode()

    transport.posts = posts
    return transport


@pytest.fixture(scope="module")
def snap_plan(tmp_path_factory):
    """The RUN, BT and TL plan for Snap alone: a large plan to drive in slices."""
    out = tmp_path_factory.mktemp("snap-plan")
    return full_evaluation.plan(
        inventory=snap_request.INVENTORY,
        archives=[TOT13_PAIRS],
        providers=[PROVIDERS["snap"]],
        out=out,
        commit=None,
        families=("RUN", "BT", "TL"),
    )


def test_a_large_plan_finishes_through_small_resumed_slices(
    snap_plan, tmp_path, monkeypatch
):
    """T24: many small slices finish the plan; no request is posted twice."""
    monkeypatch.setenv(PROVIDERS["snap"].key_env, "test-key")
    bodies = [item for item in snap_plan["built"] if item["body"] is not None]
    assert len(bodies) > 50
    transport = _answering_transport(input_tokens=2_000)
    slices = []
    while True:
        result = full_evaluation.budgeted_send(
            snap_plan["built"],
            tmp_path,
            max_new_requests=7,
            max_usd=1.0,
            max_seconds=60,
            transport=transport,
        )
        slices.append(result)
        if result["stop_reason"] is None:
            break
        assert result["stop_reason"] == "request_limit"
        assert len(slices) < 100
    assert len(slices) >= len(bodies) // 7
    assert len(transport.posts) == len(bodies)
    unique = {json.dumps(body, sort_keys=True) for body in transport.posts}
    assert len(unique) == len(bodies)
    expected = len(bodies) * 2_000 * PROVIDERS["snap"].usd_per_million_input / 1e6
    assert slices[-1]["spent_usd"] == pytest.approx(expected)
    settled = full_evaluation.settle(snap_plan["rows"], tmp_path)
    sent_rows = {r["status"] for r in settled if r.get("request_fingerprint")}
    assert sent_rows == {"answered"}
    # A finished plan sends nothing more.
    again = full_evaluation.budgeted_send(
        snap_plan["built"],
        tmp_path,
        max_new_requests=7,
        max_usd=1.0,
        max_seconds=60,
        transport=transport,
    )
    assert again["sent"] == 0
    assert len(transport.posts) == len(bodies)


def test_cap_exhaustion_stops_safely_and_keeps_pending_rows(
    snap_plan, tmp_path, monkeypatch
):
    """The dollar cap is never passed, across resumes, and unsent rows stay planned."""
    monkeypatch.setenv(PROVIDERS["snap"].key_env, "test-key")
    transport = _answering_transport(input_tokens=300_000)
    price = PROVIDERS["snap"].usd_per_million_input / 1e6
    reserve = full_evaluation.SNAP_BILLABLE_INPUT_CEILING * price
    cap = 0.05
    for _ in range(3):
        result = full_evaluation.budgeted_send(
            snap_plan["built"],
            tmp_path,
            max_new_requests=50,
            max_usd=cap,
            max_seconds=60,
            transport=transport,
        )
        assert result["stop_reason"] == "usd_limit"
        assert result["spent_usd"] <= cap
        assert result["spent_usd"] + reserve > cap
    each = 300_000 * price
    assert len(transport.posts) == int((cap - reserve) // each) + 1
    statuses = Counter(
        r["status"]
        for r in full_evaluation.settle(snap_plan["rows"], tmp_path)
        if r.get("request_fingerprint")
    )
    assert statuses["answered"] > 0
    assert statuses["planned"] > 0


# --- Snap key input ----------------------------------------------------------------


def test_env_file_loads_only_the_provider_keys(tmp_path, monkeypatch):
    """The key file sets the selected provider's key and nothing else."""
    snap = PROVIDERS["snap"]
    monkeypatch.delenv(snap.key_env, raising=False)
    monkeypatch.delenv("UNRELATED_SECRET", raising=False)
    keys = tmp_path / ".env"
    keys.write_text(
        f"# keys\nexport {snap.key_env}='abc'\nUNRELATED_SECRET=x\n", encoding="utf-8"
    )
    assert full_evaluation.load_provider_keys(keys, [snap]) == [snap.key_env]
    assert os.environ[snap.key_env] == "abc"
    assert "UNRELATED_SECRET" not in os.environ
    monkeypatch.setenv(snap.key_env, "already-set")
    assert full_evaluation.load_provider_keys(keys, [snap]) == []
    assert os.environ[snap.key_env] == "already-set"


def test_a_dry_run_reports_whether_snap_could_be_sent(tmp_path, monkeypatch):
    """The report says the key is set and Snap's contract is verified; no value leaks."""
    snap = PROVIDERS["snap"]
    monkeypatch.delenv(snap.key_env, raising=False)
    monkeypatch.setattr(
        full_evaluation,
        "provenance",
        lambda *args: {
            "commit_pinned": "test",
            "commit_checked_out": "test",
            "tracked_changes_uncommitted": False,
            "rubric_version": "1.0.0",
            "packet_schema_version": "test",
            "normalize_version": "test",
        },
    )
    keys = tmp_path / "keys.env"
    keys.write_text(f"{snap.key_env}=secret-value-123\n", encoding="utf-8")
    out = tmp_path / "out"
    status = full_evaluation.main(
        [
            "--archive",
            str(TOT13_PAIRS),
            "--families",
            "BT",
            "--provider",
            "snap",
            "--env-file",
            str(keys),
            "--out",
            str(out),
        ]
    )
    # The key file put the value in the process; take it out again.
    monkeypatch.delenv(snap.key_env, raising=False)
    assert status == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["readiness"]["snap"] == {
        "key_env": snap.key_env,
        "key_present": True,
        "live_contract_verified": True,
    }
    for written in out.rglob("*"):
        if written.is_file():
            assert "secret-value-123" not in written.read_text("utf-8", "replace")
