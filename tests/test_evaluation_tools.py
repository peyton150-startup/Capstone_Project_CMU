"""The evaluation scaffolding under `evaluation/evaltools`.

These tests prove the tools' own contracts: a packet never hands the judge
the hidden truth, the committed schema is the one the code generates, the
question file is well formed and batches at the API's limit, a full trace
reaches the packet when an audit log exists, the traced runner names the
functions each case executed, and the inventory lists every function and
only names curated items that exist. None of them calls a model or SubQ.
"""

import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from capstone.agent.completion import AuditLog
from capstone.experiment import append_records, known_cases, run_experiment
from evaltools import build_inventory, run_packet, snap_request
from tests.test_known_answers import stand_in

REPO = Path(__file__).resolve().parents[1]
BENCHMARKS = REPO / "docs" / "benchmarks"
MASTER_RECORDS = BENCHMARKS / "2026-10-27-master-resumed.records.jsonl"
MASTER_LABELS = BENCHMARKS / "2026-10-27-master-labels.jsonl"
AUDITED_FIVE = BENCHMARKS / "2026-11-02-audited-known-cases"
HIDDEN = run_packet.HIDDEN_WORDS


@pytest.fixture(scope="module")
def master_packets():
    return run_packet.build_all(MASTER_RECORDS, labels_path=MASTER_LABELS)


def test_master_run_packets_keep_the_truth_out_of_the_judge_view(master_packets):
    assert len(master_packets) == 9
    for packet in master_packets:
        text = packet.snap_view.model_dump_json().lower()
        assert not [word for word in HIDDEN if word in text]
        assert packet.evaluator_only.true_faults
        assert packet.snap_view.trace.completeness == "record_only"
        # What the record does not keep is unknown, not zero or empty.
        assert packet.snap_view.facts.machines_examined is None
        assert packet.snap_view.facts.sensors_read is None
        for decision in packet.snap_view.trace.decisions:
            assert decision.confidence is None
            assert decision.arguments is None
            assert decision.information_needed is None


def test_master_run_summary_matches_the_published_result(master_packets):
    """3 of 9 right, 5 timeouts: the numbers docs/PROGRESS.md recorded for EV1."""
    summary = run_packet.batch_summary(master_packets)
    assert summary["runs"] == summary["judged"] == 9
    assert summary["root_cause_correct"] == 3
    assert summary["timeouts"] == 5
    assert summary["traces_complete"] == 0
    # Right recommendations include three abstentions on no-action cases.
    assert summary["recommendation_correct"] == 5
    assert summary["abstained"] == 5
    # Evidence share is pooled (collected over available, as `summarize` and
    # the rubric define it) and, apart, averaged over the runs that had any.
    assert summary["evidence_share"] == pytest.approx(
        summary["evidence_collected"] / summary["evidence_available"]
    )
    assert summary["evidence_share_runs"] == 9
    assert summary["timed_runs"] == 9


def test_the_truth_guard_catches_a_hidden_field_in_any_letter_case(master_packets):
    packet = master_packets[0]
    tainted = packet.model_copy(
        update={
            "snap_view": packet.snap_view.model_copy(
                update={
                    "trace": packet.snap_view.trace.model_copy(
                        update={"anomaly": "note: True_Batch_ID 3 looks bad"}
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="true_batch_id"):
        run_packet.check_no_truth_in_view(tainted)


def test_the_committed_schema_is_the_one_the_packet_model_generates():
    committed = json.loads(
        (REPO / "evaluation" / "RUN_EVIDENCE_SCHEMA.json").read_text()
    )
    assert committed == run_packet.RunEvidencePacket.model_json_schema()


def test_snap_questions_are_well_formed_and_batch_at_the_api_limit():
    raw, questions = snap_request.load_questions()
    assert raw["rubric_version"] == run_packet.RUBRIC_VERSION
    families = {q.family for q in questions}
    assert families == {"RUN", "FN", "TS", "TL", "BT"}
    # The questions a record-only packet cannot answer are named once in the
    # code and once in the file's principles; the two must agree.
    stated = {
        q.id
        for q in questions
        if q.family == "RUN" and "record_only packets: unknown" in q.missing_evidence
    }
    stated |= {
        q.id for q in questions if "record_only, do not ask" in q.missing_evidence
    }
    assert stated == snap_request.NEEDS_FULL_TRACE
    principle = next(p for p in raw["principles"] if "record_only" in p)
    assert all(q_id in principle for q_id in snap_request.NEEDS_FULL_TRACE)
    for question in questions:
        body = question.to_request()
        assert body["type"] == question.type
        assert body["criteria"]
    many = questions * 2  # more than sixteen
    requests = snap_request.build_request(
        {"x": 1}, many, model="m", item_id="i", meta={}
    )
    assert all(len(r["body"]["questions"]) <= 16 for r in requests)
    assert sum(len(r["body"]["questions"]) for r in requests) == len(many)


def test_record_only_packets_skip_the_questions_that_need_a_trace(master_packets):
    _, questions = snap_request.load_questions()
    packet = json.loads(master_packets[0].model_dump_json())
    chosen, skipped = snap_request.applicable_run_questions(packet, questions)
    assert {q.id for q in chosen} <= {"RUN-07"}
    assert "RUN-01" in skipped and "record_only" in skipped["RUN-01"]


def test_an_unfittable_packet_is_recorded_as_skipped_not_fatal(
    master_packets, tmp_path
):
    """One packet whose judge view cannot be trimmed to the budget does not
    stop the batch: its item has no body and says why."""
    from evaltools import decision_models

    _, questions = snap_request.load_questions()
    small = json.loads(master_packets[0].model_dump_json())
    big = json.loads(master_packets[1].model_dump_json())
    # The conclusion is never trimmed, so a huge one cannot be fitted.
    big["snap_view"]["trace"]["conclusion"]["diagnosis"] = "x" * (
        decision_models.MATCHED_STATE_TOKENS * decision_models.CHARS_PER_TOKEN + 1000
    )
    for name, packet in (("a.json", small), ("b.json", big)):
        (tmp_path / name).write_text(json.dumps(packet))
    built = snap_request.run_requests(
        tmp_path,
        questions,
        [decision_models.PROVIDERS["snap"]],
        state_tokens=decision_models.MATCHED_STATE_TOKENS,
    )
    by_file = {item["tags"]["packet_file"]: item for item in built}
    assert by_file["a.json"]["body"] is not None
    assert by_file["b.json"]["body"] is None
    assert "does not fit" in by_file["b.json"]["tags"]["unfittable"]


def test_an_audit_log_gives_the_packet_a_full_trace(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    case = known_cases()[0]  # KA-01: the stand-in reads CNC-02's vibration
    records = run_experiment([case], stand_in, name="packet-check", log=log)
    append_records(tmp_path / "records.jsonl", records)
    (packet,) = run_packet.build_all(
        tmp_path / "records.jsonl", audit_path=tmp_path / "audit.jsonl"
    )
    trace = packet.snap_view.trace
    assert trace.completeness == "full"
    # The time, the loop's line screening, then the stand-in's reading.
    assert [e.origin for e in trace.evidence] == ["observable"] * 3
    assert packet.snap_view.facts.machines_examined == ["CNC-02"]
    assert packet.evaluator_only.verification_calibration == "no_verdict"
    # Unjudged until a label exists; never counted as wrong.
    assert packet.evaluator_only.fully_right is None
    assert packet.evaluator_only.abstained is None


def test_audited_import_rejects_missing_duplicate_and_orphan_traces(tmp_path):
    """A declared audit cannot silently lose or add an episode."""
    case = known_cases()[0]
    records = run_experiment([case], stand_in, name="audit-check")
    records_path = tmp_path / "records.jsonl"
    audit_path = tmp_path / "audit.jsonl"
    append_records(records_path, records)
    audit_path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="audit/record mismatch"):
        run_packet.build_all(records_path, audit_path=audit_path)
    log = AuditLog(audit_path)
    run_experiment([case], stand_in, name="audit-check", log=log)
    assert (
        run_packet.build_all(records_path, audit_path=audit_path)[
            0
        ].snap_view.trace.completeness
        == "full"
    )
    audit_line = audit_path.read_text(encoding="utf-8")
    audit_path.write_text(audit_line + audit_line, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate audit run id"):
        run_packet.build_all(records_path, audit_path=audit_path)
    audit_path.write_text("", encoding="utf-8")
    run_experiment([known_cases()[1]], stand_in, name="audit-check", log=log)
    with pytest.raises(ValueError, match="orphan="):
        run_packet.build_all(records_path, audit_path=audit_path)


def test_the_traced_run_names_the_functions_each_case_executed(tmp_path):
    config = tmp_path / "one.json"
    config.write_text(
        json.dumps(
            {"cases": [{"id": "KA-07-false-alarm", "seed": 8, "fault": "false_alarm"}]}
        )
    )
    trace = tmp_path / "trace.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evaltools.traced_run",
            "--config",
            str(config),
            "--name",
            "trace-check",
            "--out",
            str(tmp_path / "records.jsonl"),
            "--trace",
            str(trace),
            "--coverage-file",
            str(tmp_path / ".coverage.trace"),
            "--scripted",
            "--no-manual",
        ],
        cwd=REPO / "evaluation",
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    executed = json.loads(trace.read_text())
    (key,) = executed
    assert key == "trace-check/1/KA-07-false-alarm"
    assert "capstone.agent.loop:run_inner_loop" in executed[key]
    assert "capstone.evaluation.scoring:evaluate" in executed[key]


def test_the_inventory_lists_every_function_and_every_curated_item_exists(tmp_path):
    matrix = build_inventory.build(None, None, tmp_path)
    counted = 0
    source_paths = [
        *(REPO / "capstone-code" / "capstone").rglob("*.py"),
        *(REPO / "evaluation" / "evaltools").rglob("*.py"),
    ]
    for path in source_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        counted += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for node in ast.walk(tree)
        )
    assert matrix["counts"]["functions"] == counted
    functions = json.loads((tmp_path / "FUNCTION_INVENTORY.json").read_text())
    by_id = {f["id"]: f for f in functions["functions"]}
    assert "capstone.agent.loop:gather" in by_id
    assert by_id["capstone.evaluation.scoring:evaluate"]["status_source"] == "curated"
    assert {f["verification_status"] for f in by_id.values()} <= (
        build_inventory.ALLOWED_STATUS
    )
    # Without coverage, no machine rule may grant VERIFIED.
    assert all(
        f["status_source"] == "curated"
        for f in by_id.values()
        if f["verification_status"] == "VERIFIED"
    )
    tools = json.loads((tmp_path / "TOOL_INVENTORY.json").read_text())["tools"]
    assert {t["name"] for t in tools} >= {"get_readings", "wait", "search_manual"}


def test_per_test_coverage_contexts_reach_the_inventory(tmp_path):
    """A configured coverage run keeps both tests that call one function."""
    # Variables:
    #   coverage_path: The isolated data file read back through the inventory
    #     parser after the probe finishes.
    #   probe: A subprocess keeps its coverage tracer separate from pytest-cov.
    #   contexts: Test ids attributed to the source line exercised twice.
    coverage_path = tmp_path / ".coverage.contexts"
    probe = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from coverage import Coverage
        sys.path.insert(0, str(Path(sys.argv[2]) / "evaluation"))
        from evaltools.build_inventory import names_function
        coverage = Coverage(data_file=sys.argv[1], config_file=str(Path(sys.argv[2]) / "pyproject.toml"))
        coverage.start()
        for name in ("first", "second"):
            coverage.switch_context(f"tests/test_evaluation_tools.py::test_{name}")
            names_function("sensor_alarm", "sensor")
        coverage.stop()
        coverage.save()
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe, str(coverage_path), str(REPO)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    contexts, _, _ = build_inventory.read_coverage(coverage_path)
    expected = {
        "tests/test_evaluation_tools.py::test_first",
        "tests/test_evaluation_tools.py::test_second",
    }
    assert expected in contexts["evaluation/evaltools/build_inventory.py"].values()


def test_constructor_callers_are_matched_by_class_name():
    """An unrelated class constructor is not a caller of AuditLog.__init__."""
    # Variables:
    #   functions: Source functions whose call expressions can name AuditLog.
    #   target: The AuditLog constructor being checked for false callers.
    #   callers: Source functions reported as constructing AuditLog.
    functions = build_inventory.collect_functions(
        REPO / "capstone-code" / "capstone" / "agent" / "completion.py"
    )
    functions += build_inventory.collect_functions(
        REPO / "capstone-code" / "capstone" / "experiment.py"
    )
    functions += build_inventory.collect_functions(
        REPO / "evaluation" / "evaltools" / "run_packet.py"
    )
    target = next(
        function
        for function in functions
        if function.id == "capstone.agent.completion:AuditLog.__init__"
    )
    callers = build_inventory.static_callers_of(target, functions)
    assert callers == [
        "capstone.experiment:main",
        "evaluation.evaltools.run_packet:audit_by_run",
    ]


def test_function_questions_need_the_complete_test_evidence():
    """Incomplete function packets keep FN-02/03 unknown, without a model call."""
    # Variables:
    #   complete: A five-pilot function whose rebuilt test list is complete.
    #   truncated: A heavily used constructor whose test list still has a cap.
    #   shortened: A function packet with a cut test source, even though its
    #     test id list is complete.
    from evaltools import decision_models

    inventory = json.loads(
        (snap_request.INVENTORY / "FUNCTION_INVENTORY.json").read_text("utf-8")
    )["functions"]
    tests = {
        test["id"]: test
        for test in json.loads(
            (snap_request.INVENTORY / "TEST_INVENTORY.json").read_text("utf-8")
        )["tests"]
    }
    by_id = {function["id"]: function for function in inventory}
    complete = snap_request.function_state(
        by_id["capstone.agent.completion:action_evidence_ids"], tests
    )
    truncated = snap_request.function_state(
        by_id["capstone.simulator.rng:RandomSource.__init__"], tests
    )
    assert complete["coverage"]["test_count"] == len(complete["tests"])
    assert complete["tests_shown"] is None
    assert any(
        test["id"].endswith("test_the_action_cites_what_the_factory_reported_about_it")
        for test in complete["tests"]
    )
    assert truncated["tests_shown"] is not None
    assert truncated["tests_shown"].endswith(
        f"of {truncated['coverage']['test_count']} shown"
    )
    _, questions = snap_request.load_questions()
    requests = snap_request.item_requests(
        [("complete", complete), ("truncated", truncated)],
        snap_request.questions_for("FN", questions),
        [decision_models.PROVIDERS["jev"]],
        meta={"family": "FN", "rubric_version": "1.0.0"},
        state_tokens=None,
    )
    assert requests[0]["tags"]["question_ids"] == ["FN-01", "FN-02", "FN-03"]
    assert requests[1]["tags"]["question_ids"] == ["FN-01"]
    assert requests[1]["tags"]["skipped_questions"] == {
        "FN-02": "unknown: function test evidence is incomplete",
        "FN-03": "unknown: function test evidence is incomplete",
    }
    shortened = {**complete, "tests": [{**complete["tests"][0], "source_cut": "cut"}]}
    [shortened_request] = snap_request.item_requests(
        [("shortened", shortened)],
        snap_request.questions_for("FN", questions),
        [decision_models.PROVIDERS["jev"]],
        meta={"family": "FN", "rubric_version": "1.0.0"},
        state_tokens=None,
    )
    assert shortened_request["tags"]["question_ids"] == ["FN-01"]


# --- two decision models on the same evidence ---------------------------------------


def test_both_providers_get_the_same_fitted_state_and_questions(master_packets):
    from evaltools import decision_models

    _, questions = snap_request.load_questions()
    state = json.loads(master_packets[1].snap_view.model_dump_json())
    built = {
        name: snap_request.build_request(
            state,
            snap_request.questions_for("RUN", questions)[:3],
            model=provider.model,
            item_id="x",
            meta={},
            provider=name,
        )[0]
        for name, provider in decision_models.PROVIDERS.items()
    }
    snap, jev = built["snap"], built["jev"]
    assert snap["tags"]["state_digest"] == jev["tags"]["state_digest"]
    assert snap["body"]["state"] == jev["body"]["state"]
    assert snap["body"]["questions"] == jev["body"]["questions"]
    assert snap["body"]["model"] != jev["body"]["model"]
    assert snap["tags"]["state_budget_tokens"] == decision_models.MATCHED_STATE_TOKENS


def test_fitting_a_state_is_deterministic_and_keeps_the_conclusion():
    from evaltools import decision_models

    big = {
        "trace": {
            "evidence": [{"id": f"E{i}", "content": "x" * 5000} for i in range(40)],
            "decisions": [{"information_needed": "why", "tool": "get_time"}] * 50,
            "pruned_candidates": [{"id": "C1"}],
            "conclusion": {"diagnosis": "keep me"},
            "hypotheses": [{"id": "H1"}],
        }
    }
    fitted, log = decision_models.fit_state(big, 3000)
    again, _ = decision_models.fit_state(big, 3000)
    assert fitted == again
    assert decision_models.estimate_tokens(fitted) <= 3000
    assert fitted["trace"]["conclusion"] == {"diagnosis": "keep me"}
    assert fitted["trace"]["hypotheses"] == [{"id": "H1"}]
    assert "evidence content cut to 600 characters" in log
    assert big["trace"]["evidence"][0]["content"] == "x" * 5000  # untouched
    with pytest.raises(ValueError):
        decision_models.fit_state(big, 10)


def test_answers_normalize_to_one_schema_and_compare_by_the_stated_rules():
    from evaltools import decision_models

    noul = {"id": "RUN-09", "name": "unsupported_confidence", "type": "noul"}
    choice = {"id": "RUN-05", "name": "verification_demonstrated", "type": "choice"}
    score = {"id": "RUN-08", "name": "conclusion_support", "type": "score"}
    a = decision_models.normalize(
        "snap",
        noul,
        {"type": "noul", "noul": 0.9},
        model_reported="subq-snap-1.1",
        latency_seconds=1.0,
        input_tokens=1000,
    )
    b = decision_models.normalize(
        "jev",
        noul,
        {"type": "noul", "noul": 0.35},
        model_reported="jev-1.14.0",
        latency_seconds=2.0,
        input_tokens=1000,
    )
    assert set(a) == set(b)
    assert a["cost_usd"] == pytest.approx(0.040 / 1000)
    assert b["cost_usd"] == pytest.approx(0.042 / 1000)
    assert decision_models.compare(a, b)["agree"] is False
    close = decision_models.normalize(
        "jev",
        noul,
        {"noul": 0.45},
        model_reported=None,
        latency_seconds=None,
        input_tokens=None,
    )
    assert decision_models.compare(close, b)["agree"] is True  # within 0.2
    yes = decision_models.normalize(
        "snap",
        choice,
        {"type": "choice", "choice": "yes", "confidence": 0.8},
        model_reported=None,
        latency_seconds=None,
        input_tokens=None,
    )
    no = decision_models.normalize(
        "jev",
        choice,
        {"type": "choice", "choice": "no", "confidence": 0.6},
        model_reported=None,
        latency_seconds=None,
        input_tokens=None,
    )
    assert decision_models.compare(yes, no)["agree"] is False
    three = decision_models.normalize(
        "snap",
        score,
        {"type": "score", "score": 3.2, "confidence": 0.5},
        model_reported=None,
        latency_seconds=None,
        input_tokens=None,
    )
    nearly = decision_models.normalize(
        "jev",
        score,
        {"type": "score", "score": 2.8},
        model_reported=None,
        latency_seconds=None,
        input_tokens=None,
    )
    assert decision_models.compare(three, nearly)["agree"] is True
    assert decision_models.reference_match(three, 3) is True
    assert decision_models.reference_match(yes, "no") is False
    with pytest.raises(ValueError):
        decision_models.normalize(
            "snap",
            noul,
            {"type": "choice", "choice": "x"},
            model_reported=None,
            latency_seconds=None,
            input_tokens=None,
        )
    with pytest.raises(ValueError):
        decision_models.compare(a, yes)


def test_the_agreement_report_pairs_only_identical_states_and_flags_disagreements(
    tmp_path,
):
    from evaltools import compare_evaluators

    question = {"id": "FN-01", "name": "q", "type": "noul", "criteria": {}}

    def answers_file(provider, item, value, digest):
        return {
            "tags": {
                "provider": provider,
                "item_id": item,
                "state_digest": digest,
                "questions": {"q": question},
            },
            "answers": [
                {
                    "provider": provider,
                    "question_id": "FN-01",
                    "question_name": "q",
                    "type": "noul",
                    "value": value,
                    "confidence": abs(value - 0.5) * 2,
                    "latency_seconds": 1.0,
                    "input_tokens": 100,
                    "cost_usd": 0.0,
                    "model_reported": provider,
                }
            ],
        }

    files = [
        answers_file("snap", "f1", 0.9, "same"),
        answers_file("jev", "f1", 0.2, "same"),
        answers_file("snap", "f2", 0.9, "one"),
        answers_file("jev", "f2", 0.9, "other"),
    ]
    # A request with two questions reports its tokens once, on both answers.
    files[0]["answers"].append(
        {**files[0]["answers"][0], "question_id": "FN-02", "question_name": "q2"}
    )
    report = compare_evaluators.build_report(files, {"f1": {"FN-01": True}})
    assert report["pairs_compared"] == 1
    assert report["agreement_rate"] == 0.0
    assert report["disagreements_for_review"][0]["item_id"] == "f1"
    assert report["unmatched"][0]["item_id"] == "f2"
    assert report["per_provider"]["snap"]["reference_agreement"]["matched"] == 1
    assert report["per_provider"]["jev"]["reference_agreement"]["matched"] == 0
    snap = report["per_provider"]["snap"]
    # Three answers over two requests: tokens counted per request, not per answer.
    assert snap["answers"] == 3 and snap["requests"] == 2
    assert snap["input_tokens_total"] == 200
    assert snap["mean_confidence_by_type"] == {"noul": 0.8}
    text = compare_evaluators.markdown(report)
    assert "f1" in text and "Caveats" in text


# --- fixes after review -------------------------------------------------------------


def request_item(item_id, provider="snap", model="subq-snap-1.1"):
    """A minimal sendable request item, as `build_request` shapes one."""
    question = {"id": "FN-01", "name": "q", "type": "noul"}
    item = {
        "tags": {
            "provider": provider,
            "model_requested": model,
            "item_id": item_id,
            "question_ids": ["FN-01"],
            "questions": {"q": question},
            "state_digest": "d",
        },
        "body": {"model": model, "state": {"item": item_id}, "questions": {}},
    }
    item["tags"]["request_fingerprint"] = snap_request.request_fingerprint(
        item["tags"], item["body"]
    )
    return item


def fake_transport(replies):
    """A transport that records each request and answers from `replies` in turn.

    A reply that is an exception is raised, as the network would.
    """
    sent = []

    def transport(url, headers, body, timeout):
        sent.append({"url": url, "headers": headers, "body": json.loads(body)})
        reply = replies[min(len(sent), len(replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply).encode()

    transport.sent = sent
    return transport


GOOD_REPLY = {"model": "m", "answers": {"q": {"type": "noul", "noul": 0.7}}}


def test_request_file_names_are_valid_on_every_operating_system(tmp_path):
    """A function id has a colon; Windows would write an empty file for it."""
    built = [
        request_item("capstone.agent.loop:gather"),
        request_item("tests/test_x.py::test_y"),
    ]
    snap_request.write_requests(built, tmp_path, send_them=False)
    names = sorted(p.name for p in tmp_path.iterdir())
    fingerprints = [item["tags"]["request_fingerprint"][:12] for item in built]
    assert names == [
        f"snap_capstone.agent.loop_gather_{fingerprints[0]}.request.json",
        f"snap_tests__test_x.py__test_y_{fingerprints[1]}.request.json",
    ]
    assert all(p.stat().st_size > 0 for p in tmp_path.iterdir())


def test_a_failed_request_is_recorded_and_a_rerun_sends_only_what_is_missing(
    tmp_path, monkeypatch
):
    import urllib.error

    monkeypatch.setenv("SUBQ_API_KEY", "test-key")
    busy = urllib.error.HTTPError("https://x", 429, "Too Many", {}, None)
    transport = fake_transport([busy, GOOD_REPLY])
    built = [request_item("a"), request_item("b")]
    counts = snap_request.write_requests(
        built, tmp_path, send_them=True, transport=transport, retries=0
    )
    assert counts == {"sent": 1, "failed": 1, "already_answered": 0}
    stem = snap_request.file_stem(built[0]["tags"])
    failed = json.loads((tmp_path / f"{stem}.answers.json").read_text())
    assert failed["error"] == "the model service answered HTTP 429"
    assert failed["answers"] == []
    assert "test-key" not in json.dumps(failed)
    # The rerun sends only the request that failed.
    counts = snap_request.write_requests(
        built, tmp_path, send_them=True, transport=transport, retries=0
    )
    assert counts == {"sent": 1, "failed": 0, "already_answered": 1}
    assert len(transport.sent) == 3


def test_answers_name_the_model_requested_and_keep_unreadable_ones(tmp_path):
    item = request_item("a", model="subq-snap-custom")
    item["tags"]["questions"]["r"] = {"id": "FN-02", "name": "r", "type": "noul"}
    reply = {"answers": {"q": {"noul": 0.9}, "r": {"type": "noul"}}}
    good, bad = snap_request.normalized_answers(item, reply, 0.5)
    assert good["model_requested"] == "subq-snap-custom"
    assert bad["value"] is None and "unreadable" in bad["error"]
    # A reply that is not a JSON object loses no answer silently either.
    assert all(
        a["value"] is None for a in snap_request.normalized_answers(item, [], 0.5)
    )


def test_failed_requests_are_counted_apart_from_answered_ones():
    from evaltools import compare_evaluators

    files = [
        {"tags": {"provider": "snap"}, "answers": [], "error": "HTTP 500 x"},
        {
            "tags": {"provider": "snap"},
            "answers": [{"input_tokens": 50, "cost_usd": 0.0}],
        },
    ]
    usage = compare_evaluators.request_usage(files)["snap"]
    assert usage["requests"] == 1 and usage["failed_requests"] == 1
    assert usage["input_tokens"] == 50


def test_a_refused_packet_is_left_out_and_named_not_fatal(monkeypatch):
    first = run_packet.build_all(MASTER_RECORDS, labels_path=MASTER_LABELS)[0]
    marker = first.snap_view.run_ref  # in this packet's judge view only
    monkeypatch.setattr(run_packet, "HIDDEN_WORDS", (marker,))
    refused = []
    packets = run_packet.build_all(
        MASTER_RECORDS, labels_path=MASTER_LABELS, refused=refused
    )
    assert len(packets) == 8
    assert [r["episode_key"] for r in refused] == [first.meta.episode_key]
    with pytest.raises(ValueError):
        run_packet.build_all(MASTER_RECORDS, labels_path=MASTER_LABELS)


def test_the_judge_view_never_names_the_scenario(master_packets):
    """Scenario ids name the fault (KA-01-bearing), so they stay in meta."""
    for packet in master_packets:
        text = packet.snap_view.model_dump_json().lower()
        assert packet.meta.scenario_id.lower() not in text
        assert packet.meta.run_key.lower() not in text
        assert packet.snap_view.run_ref == run_packet.run_ref(packet.meta.run_key)
    packet = master_packets[0]
    tainted = packet.model_copy(
        update={
            "snap_view": packet.snap_view.model_copy(
                update={
                    "trace": packet.snap_view.trace.model_copy(
                        update={"anomaly": f"see {packet.meta.scenario_id}"}
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="scenario id"):
        run_packet.check_no_truth_in_view(tainted)


def test_a_recheck_record_reaches_the_packet_whole():
    """Every follow-up run failed here: the view lacked the record's `question`."""
    from capstone.agent.artifacts import RecheckRecord

    assert set(run_packet.RecheckView.model_fields) == set(RecheckRecord.model_fields)
    record = next(iter(run_packet.read_records(MASTER_RECORDS)))
    followed = record.model_copy(
        update={
            "recheck": RecheckRecord(
                outcome="observed", trigger="objection", question="vibration again?"
            )
        }
    )
    line = followed.model_dump_json()
    packet = run_packet.build_packet(
        followed,
        line,
        label=None,
        critic_label=None,
        audit=None,
        records_file="r",
        audit_file=None,
        labels_file=None,
        commit_sha=None,
    )
    assert packet.snap_view.trace.recheck.question == "vibration again?"
    assert packet.snap_view.configuration.critic_followup_on is True


def test_outage_runs_are_out_of_the_reasoning_totals_and_asked_nothing(
    master_packets,
):
    _, questions = snap_request.load_questions()
    down = master_packets[0].model_copy(
        update={
            "evaluator_only": master_packets[0].evaluator_only.model_copy(
                update={"model_unavailable": True}
            ),
            "snap_view": master_packets[0].snap_view.model_copy(
                update={
                    "facts": master_packets[0].snap_view.facts.model_copy(
                        update={"termination_reason": "model_unavailable"}
                    )
                }
            ),
        }
    )
    batch = [down, *master_packets[1:]]
    summary = run_packet.batch_summary(batch)
    assert summary["model_unavailable"] == 1
    assert summary["judged"] == 8
    chosen, skipped = snap_request.applicable_run_questions(
        json.loads(down.model_dump_json()), questions
    )
    assert chosen == []
    assert all("model_unavailable" in reason for reason in skipped.values())


def test_a_run_without_a_critique_does_not_claim_the_critic_was_off(master_packets):
    for packet in master_packets:
        if packet.snap_view.trace.critique is None:
            assert packet.snap_view.configuration.critic is None


def test_packet_file_names_are_valid_on_every_operating_system():
    assert run_packet.packet_file_name("ev:1/2/KA-01") == "ev_1__2__KA-01.json"


def test_a_function_is_named_by_a_test_only_as_whole_words():
    assert build_inventory.names_function("test_gather_reads_two", "gather")
    assert build_inventory.names_function("test_job_history", "job_history")
    assert build_inventory.names_function("test_x_fit_state", "_fit_state")
    assert not build_inventory.names_function("test_relevant_evidence", "relevant_e")
    assert not build_inventory.names_function("test_gathering", "gather")
    assert not build_inventory.names_function("test_run_it", "run")


def test_run_09_is_not_asked_of_a_run_without_a_conclusion(master_packets):
    _, questions = snap_request.load_questions()
    packet = json.loads(master_packets[0].model_dump_json())
    packet["snap_view"]["trace"]["completeness"] = "full"
    packet["snap_view"]["trace"]["conclusion"] = None
    chosen, skipped = snap_request.applicable_run_questions(packet, questions)
    assert "RUN-09" not in {q.id for q in chosen}
    assert skipped["RUN-09"].startswith("not_applicable")


def test_a_noul_reference_written_as_text_is_read_as_a_boolean():
    from evaltools import decision_models

    answer = {"type": "noul", "value": 0.9}
    assert decision_models.reference_match(answer, "true") is True
    assert decision_models.reference_match(answer, "False") is False
    with pytest.raises(ValueError):
        decision_models.reference_match(answer, "maybe")


def test_an_unfittable_function_state_is_skipped_not_fatal():
    from evaltools import decision_models

    _, questions = snap_request.load_questions()
    built = snap_request.item_requests(
        [("small", {"x": 1}), ("big", {"source": "x" * 10_000})],
        snap_request.questions_for("FN", questions),
        [decision_models.PROVIDERS["snap"]],
        meta={"family": "FN"},
        state_tokens=100,
    )
    by_item = {item["tags"]["item_id"]: item for item in built}
    assert by_item["small"]["body"] is not None
    assert by_item["big"]["body"] is None
    assert "does not fit" in by_item["big"]["tags"]["unfittable"]


def test_a_traced_run_refuses_to_append_to_earlier_records(tmp_path):
    """Appending would give two records the same run key."""
    from evaltools import traced_run

    out = tmp_path / "records.jsonl"
    out.write_text('{"earlier": true}\n')
    with pytest.raises(SystemExit) as stopped:
        traced_run.main(
            ["--name", "x", "--out", str(out), "--trace", str(tmp_path / "t.json")]
        )
    assert stopped.value.code == 2


# --- evaluator readiness fixes (CRITERIA_FOR_EVALUATOR.md) ----------------------------

TOT13_PAIRS = BENCHMARKS / "2026-11-01-tot13-pairs"
# The published PR #156 figures (summary.json): confirmed correct over judged,
# per pair and arm, with the labels still awaiting review.
PUBLISHED = {
    ("tot13-20261031-184429-543214a2", "master-tot13-anchored"): (3, 12, 1),
    ("tot13-20261031-184429-543214a2", "master-tot13-blind"): (3, 12, 1),
    ("tot13-20261031-210256-3910997b", "master-tot13-anchored"): (6, 13, 0),
    ("tot13-20261031-210256-3910997b", "master-tot13-blind"): (6, 11, 2),
}


@pytest.fixture(scope="module")
def archive_packets():
    refused = []
    packets = run_packet.build_archive(TOT13_PAIRS, refused=refused)
    assert refused == []
    return packets


def test_the_archive_imports_52_distinct_episodes(archive_packets):
    """EVAL-01 / T01: both pairs reuse every run key, and none is overwritten."""
    keys = [p.meta.episode_key for p in archive_packets]
    assert len(keys) == len(set(keys)) == 52
    assert len({p.meta.run_key for p in archive_packets}) == 26
    assert len({p.snap_view.run_ref for p in archive_packets}) == 52
    names = {run_packet.packet_file_name(k) for k in keys}
    assert len(names) == 52
    assert {p.meta.commit_sha for p in archive_packets} == {
        "e59208d584938ed96a606bc317354882fcc8e01c"
    }


def test_both_archives_import_57_episodes_with_five_real_traces(archive_packets):
    audited = run_packet.build_archive(AUDITED_FIVE)
    packets = [*archive_packets, *audited]
    assert len(packets) == len({p.meta.episode_key for p in packets}) == 57
    assert len(audited) == 5
    assert {p.snap_view.trace.completeness for p in archive_packets} == {"record_only"}
    assert {p.snap_view.trace.completeness for p in audited} == {"full"}
    assert all(p.snap_view.trace.decisions for p in audited)
    assert {p.meta.commit_sha for p in audited} == {
        "31ddd79eb3ab6a3bc0c01f43fb3b137348346394"
    }


def test_the_archive_keeps_the_published_denominators(archive_packets):
    """EVAL-02 / T02: pending labels stay unjudged; the four arms match summary.json."""
    by_run = {}
    for packet in archive_packets:
        by_run.setdefault(
            (packet.meta.namespace, packet.meta.run_key.split("/")[0]), []
        ).append(packet)
    found = {}
    for key, packets in by_run.items():
        summary = run_packet.batch_summary(packets)
        found[key] = (
            summary["evals_correct"],
            summary["evals_judged"],
            summary["evals_pending_review"],
        )
    assert found == PUBLISHED
    pending = [
        p for p in archive_packets if p.evaluator_only.label_status == "pending_review"
    ]
    assert len(pending) == 4
    for packet in pending:
        # Kept as provenance, never scored.
        assert packet.evaluator_only.label is not None
        assert packet.evaluator_only.fully_right is None
        assert packet.evaluator_only.abstained is None
        assert packet.snap_view.facts.committed is None


def test_a_repeated_run_key_needs_a_namespace(tmp_path):
    """EVAL-01 / T01: the same records under two names survive; unnamed, refused."""
    one = run_packet.build_all(MASTER_RECORDS, namespace="pair-a")
    two = run_packet.build_all(MASTER_RECORDS, namespace="pair-b")
    run_packet.check_unique(one + two)
    assert {p.snap_view.run_ref for p in one}.isdisjoint(
        p.snap_view.run_ref for p in two
    )
    with pytest.raises(ValueError, match="namespace"):
        run_packet.check_unique(
            run_packet.build_all(MASTER_RECORDS) + run_packet.build_all(MASTER_RECORDS)
        )
    # One file repeating a run key is refused outright.
    line = MASTER_RECORDS.read_text(encoding="utf-8").splitlines()[0]
    twice = tmp_path / "twice.records.jsonl"
    twice.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="repeat"):
        run_packet.build_all(twice)


def test_a_proposal_awaiting_review_is_kept_but_not_scored(tmp_path):
    """EVAL-02: auto-label proposal files are read and `needs_review` is honoured."""
    labels = [
        json.loads(line)
        for line in MASTER_LABELS.read_text(encoding="utf-8").splitlines()
        if line
    ]
    proposals = tmp_path / "proposals.jsonl"
    proposals.write_text(
        "".join(
            json.dumps({"label": label, "needs_review": i == 0}) + "\n"
            for i, label in enumerate(labels)
        ),
        encoding="utf-8",
    )
    plain = run_packet.build_all(MASTER_RECORDS, labels_path=MASTER_LABELS)
    proposed = run_packet.build_all(MASTER_RECORDS, labels_path=proposals)
    by_key = {p.meta.run_key: p for p in proposed}
    held = by_key[labels[0]["run_key"]].evaluator_only
    assert held.label_status == "pending_review" and held.fully_right is None
    assert held.label == plain[0].evaluator_only.label
    before = run_packet.batch_summary(plain)
    after = run_packet.batch_summary(proposed)
    assert after["evals_judged"] == before["evals_judged"] - 1
    assert after["evals_pending_review"] == 1


def test_a_review_report_that_disagrees_with_the_labels_is_refused(tmp_path):
    """EVAL-02: a flag is never joined to a different label."""
    labels, _ = run_packet.read_labels(MASTER_LABELS)
    key, label = next(iter(labels.items()))
    other = json.loads(label.model_dump_json()) | {"labelled_by": "someone else"}
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "run_key": key,
                        "diagnosis_label": other,
                        "label_needs_review": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="differs"):
        run_packet.review_flags(report, labels)


def fingerprinted(state, question, *, model="m", tokens=None):
    return snap_request.build_request(
        state,
        [question],
        model=model,
        item_id="i",
        meta={"rubric_version": "1.0.0"},
        state_tokens=tokens,
    )[0]["tags"]["request_fingerprint"]


def test_every_request_input_changes_the_fingerprint():
    """EVAL-03 / T04: a saved answer is never reused for a changed request."""
    _, questions = snap_request.load_questions()
    question = questions[0]
    state = {"a": 1}
    base = fingerprinted(state, question)
    assert fingerprinted(state, question) == base
    reworded = question.model_copy(update={"instructions": question.instructions + "!"})
    variants = [
        fingerprinted(state, question, model="other-model"),
        fingerprinted({"a": 2}, question),
        fingerprinted(state, reworded),
        fingerprinted(state, question, tokens=10_000),
    ]
    assert base not in variants and len(set(variants)) == len(variants)


def test_reordered_items_keep_their_files_and_answers(tmp_path, monkeypatch):
    """EVAL-03 / T03: names do not depend on order; a rerun re-sends nothing."""
    monkeypatch.setenv("SUBQ_API_KEY", "test-key")
    transport = fake_transport([GOOD_REPLY])
    built = [request_item("a"), request_item("b")]
    snap_request.write_requests(built, tmp_path, send_them=True, transport=transport)
    counts = snap_request.write_requests(
        list(reversed(built)), tmp_path, send_them=True, transport=transport
    )
    assert counts == {"sent": 0, "failed": 0, "already_answered": 2}
    assert len(transport.sent) == 2
    assert not list(tmp_path.glob("*.partial"))


def test_a_partial_answer_is_asked_again(tmp_path, monkeypatch):
    """EVAL-03 / T07: a reply missing an answer is not a completed judgment."""
    monkeypatch.setenv("SUBQ_API_KEY", "test-key")
    transport = fake_transport([{"model": "m", "answers": {}}, GOOD_REPLY])
    built = [request_item("a")]
    snap_request.write_requests(built, tmp_path, send_them=True, transport=transport)
    counts = snap_request.write_requests(
        built, tmp_path, send_them=True, transport=transport
    )
    assert counts["sent"] == 1 and counts["already_answered"] == 0


def test_a_passing_outage_is_retried_and_a_lasting_one_recorded(tmp_path, monkeypatch):
    """EVAL-03: HTTP 429 and 5xx are tried again; the wait comes from `sleep`."""
    import urllib.error

    monkeypatch.setenv("SUBQ_API_KEY", "test-key")
    busy = urllib.error.HTTPError("https://x", 503, "Busy", {}, None)
    waits = []
    transport = fake_transport([busy, busy, GOOD_REPLY])
    counts = snap_request.write_requests(
        [request_item("a")],
        tmp_path,
        send_them=True,
        transport=transport,
        retries=2,
        sleep=waits.append,
    )
    assert counts["sent"] == 1 and waits == [2.0, 4.0]
    refused = urllib.error.HTTPError("https://x", 401, "No", {}, None)
    transport = fake_transport([refused])
    counts = snap_request.write_requests(
        [request_item("b")],
        tmp_path,
        send_them=True,
        transport=transport,
        retries=2,
        sleep=waits.append,
    )
    assert counts["failed"] == 1 and len(transport.sent) == 1


def leaky_packet_dir(tmp_path, master_packets, change):
    """A packet folder holding one master packet after `change(packet_json)`."""
    packet = json.loads(master_packets[0].model_dump_json())
    change(packet)
    folder = tmp_path / "packets"
    folder.mkdir()
    (folder / "p.json").write_text(json.dumps(packet), encoding="utf-8")
    return folder


@pytest.mark.parametrize(
    "change",
    [
        # The scenario id written into free text the judge would read.
        lambda p: p["snap_view"]["facts"].update(
            {"termination_reason": p["meta"]["scenario_id"]}
        ),
        # A truth-side field name added to the judge's half on disk.
        lambda p: p["snap_view"]["configuration"].update({"hazards": "true_fault"}),
        # A field the judge view does not define.
        lambda p: p["snap_view"].update({"evaluator_note": "x"}),
    ],
)
def test_a_leaking_packet_on_disk_is_refused_before_any_request(
    tmp_path, master_packets, change
):
    """EVAL-04 / T05: the last boundary re-checks what would be sent."""
    _, questions = snap_request.load_questions()
    folder = leaky_packet_dir(tmp_path, master_packets, change)
    built = snap_request.run_requests(
        folder,
        questions,
        [snap_request.PROVIDERS["snap"]],
        state_tokens=snap_request.MATCHED_STATE_TOKENS,
    )
    assert [b["body"] for b in built] == [None]
    assert built[0]["tags"]["unfittable"].startswith("refused")


def test_every_master_request_is_free_of_the_runs_own_ids(master_packets, tmp_path):
    """EVAL-04 / T05: no sent body names its scenario, run key or episode key."""
    _, questions = snap_request.load_questions()
    folder = tmp_path / "packets"
    folder.mkdir()
    for packet in master_packets:
        name = run_packet.packet_file_name(packet.meta.episode_key)
        (folder / name).write_text(packet.model_dump_json(), encoding="utf-8")
    built = snap_request.run_requests(
        folder,
        questions,
        list(snap_request.PROVIDERS.values()),
        state_tokens=snap_request.MATCHED_STATE_TOKENS,
    )
    sent = [b for b in built if b["body"] is not None]
    assert sent
    for packet in master_packets:
        for item in sent:
            text = json.dumps(item["body"]).lower()
            assert packet.meta.scenario_id.lower() not in text
            assert packet.meta.run_key.lower() not in text


def test_judge_requests_carry_the_project_user_agent_and_no_key(monkeypatch):
    """EVAL-19 / T17: sent with post_json, as the project's model clients are."""
    import urllib.error

    from capstone.providers.chat import USER_AGENT, ModelError

    transport = fake_transport([GOOD_REPLY])
    snap_request.send(
        snap_request.PROVIDERS["jev"], {"x": 1}, "secret-key", transport=transport
    )
    headers = transport.sent[0]["headers"]
    assert headers["User-Agent"] == USER_AGENT
    assert headers["Authorization"] == "Bearer secret-key"
    failing = fake_transport([urllib.error.HTTPError("https://x", 500, "x", {}, None)])
    with pytest.raises(ModelError) as caught:
        snap_request.send(
            snap_request.PROVIDERS["jev"], {}, "secret-key", transport=failing
        )
    assert "secret-key" not in snap_request.describe_failure(caught.value)


@pytest.mark.parametrize(
    "question, raw",
    [
        ({"type": "choice", "criteria": {"a": "", "b": ""}}, {"choice": "zzz"}),
        ({"type": "choice", "criteria": {"a": "", "b": ""}}, {"choice": 1}),
        ({"type": "noul", "criteria": {}}, {"noul": 1.7}),
        ({"type": "noul", "criteria": {}}, {"noul": -0.1}),
        ({"type": "noul", "criteria": {}}, {"noul": "0.5"}),
        ({"type": "noul", "criteria": {}}, {"noul": float("nan")}),
        ({"type": "score", "criteria": ["0", "1", "2"]}, {"score": 3}),
        ({"type": "score", "criteria": ["0", "1", "2"]}, {"score": True}),
    ],
)
def test_an_impossible_answer_is_kept_unreadable(question, raw):
    """EVAL-19 / T18: refused as the live TypeSafe client refuses it."""
    question = {"id": "FN-01", "name": "q", **question}
    item = request_item("a")
    item["tags"]["questions"] = {
        "q": question,
        "r": {"id": "FN-02", "name": "r", "type": "noul", "criteria": {}},
    }
    bad, good = snap_request.normalized_answers(
        item, {"answers": {"q": raw, "r": {"noul": 0.2}}}, 0.1
    )
    assert bad["value"] is None and "unreadable" in bad["error"]
    assert good["value"] == 0.2


def test_states_show_each_test_whole_and_say_what_was_cut():
    """EVAL-20 / T19: no neighbouring test; every shortened list says so."""
    inventory = REPO / "evaluation" / "inventory"
    functions = {
        f["id"]: f
        for f in json.loads((inventory / "FUNCTION_INVENTORY.json").read_text("utf-8"))[
            "functions"
        ]
    }
    tests = json.loads((inventory / "TEST_INVENTORY.json").read_text("utf-8"))["tests"]
    tools = json.loads((inventory / "TOOL_INVENTORY.json").read_text("utf-8"))["tools"]
    for test in tests:
        state = snap_request.test_state(test, functions)
        if state["source_cut"] is None:
            body = ast.parse(textwrap.dedent(state["source"])).body
            assert len(body) == 1, test["id"]
        known = [f for f in test["exercises"] if f in functions]
        if len(known) > snap_request.FUNCTIONS_PER_TEST:
            assert state["exercises_shown"] == (
                f"{snap_request.FUNCTIONS_PER_TEST} of {len(known)} shown"
            )
        else:
            assert state["exercises_shown"] is None
    wiring = [
        snap_request.tool_state(t, functions)["provider_wiring_source"] for t in tools
    ]
    assert all(w for w in wiring)
    assert len(set(wiring)) == len(wiring)
    for tool, text in zip(tools, wiring, strict=True):
        assert f'"{tool["name"]}"' in text


def test_the_stated_question_count_matches_the_question_file():
    """EVAL-21 / T20: the EVF note's count is the file's count."""
    import re

    _, questions = snap_request.load_questions()
    families = [q.family for q in questions]
    progress = (REPO / "docs" / "PROGRESS.md").read_text(encoding="utf-8")
    stated = re.search(
        r"\((\d+) questions: (\d+) per run, (\d+) per function, (\d+) per\s+test, "
        r"(\d+) per tool, (\d+) per batch comparison\)",
        progress,
    )
    assert stated is not None
    total, *per_family = (int(n) for n in stated.groups())
    assert total == len(questions)
    assert per_family == [families.count(f) for f in ("RUN", "FN", "TS", "TL", "BT")]


def test_two_answers_to_one_question_are_refused_and_latency_is_per_request():
    """EVAL-01 / EVAL-15: no silent overwrite; one latency figure per request."""
    from evaltools import compare_evaluators

    def answers_file(item, latency, fingerprint, n=1):
        return {
            "tags": {
                "provider": "snap",
                "item_id": item,
                "request_fingerprint": fingerprint,
                "state_digest": "d",
                "model_requested": "m",
            },
            "answers": [
                {
                    "question_id": f"FN-0{i}",
                    "type": "noul",
                    "value": 0.5,
                    "latency_seconds": latency,
                }
                for i in range(1, n + 1)
            ],
        }

    with pytest.raises(ValueError, match="two answers"):
        compare_evaluators.index_answers(
            [answers_file("a", 1.0, "f1"), answers_file("a", 1.0, "f2")]
        )
    report = compare_evaluators.build_report(
        [answers_file("a", 1.0, "f1", n=9), answers_file("b", 3.0, "f2")], None
    )
    assert report["per_provider"]["snap"]["median_latency_seconds"] == 2.0
