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
    assert [e.origin for e in trace.evidence] == ["observable", "observable"]
    assert packet.snap_view.facts.machines_examined == ["CNC-02"]
    assert packet.evaluator_only.verification_calibration == "no_verdict"
    # Unjudged until a label exists; never counted as wrong.
    assert packet.evaluator_only.fully_right is None
    assert packet.evaluator_only.abstained is None


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
    for path in (REPO / "capstone-code" / "capstone").rglob("*.py"):
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
    return {
        "tags": {
            "provider": provider,
            "model_requested": model,
            "item_id": item_id,
            "question_ids": ["FN-01"],
            "questions": {"q": question},
            "state_digest": "d",
        },
        "body": {"model": model, "state": {}, "questions": {}},
    }


def test_request_file_names_are_valid_on_every_operating_system(tmp_path):
    """A function id has a colon; Windows would write an empty file for it."""
    built = [
        request_item("capstone.agent.loop:gather"),
        request_item("tests/test_x.py::test_y"),
    ]
    snap_request.write_requests(built, tmp_path, send_them=False)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [
        "001_snap_capstone.agent.loop_gather.request.json",
        "002_snap_tests__test_x.py__test_y.request.json",
    ]
    assert all(p.stat().st_size > 0 for p in tmp_path.iterdir())


def test_a_failed_request_is_recorded_and_a_rerun_sends_only_what_is_missing(
    tmp_path, monkeypatch
):
    import urllib.error

    monkeypatch.setenv("SUBQ_API_KEY", "test-key")
    sent = []

    def flaky(provider, body, api_key, timeout=90.0):
        sent.append(body)
        if len(sent) == 1:
            raise urllib.error.HTTPError(provider.endpoint, 429, "Too Many", {}, None)
        return {"model": "m", "answers": {"q": {"type": "noul", "noul": 0.7}}}, 0.1

    monkeypatch.setattr(snap_request, "send", flaky)
    built = [request_item("a"), request_item("b")]
    counts = snap_request.write_requests(built, tmp_path, send_them=True)
    assert counts == {"sent": 1, "failed": 1, "already_answered": 0}
    failed = json.loads((tmp_path / "001_snap_a.answers.json").read_text())
    assert failed["error"] == "HTTP 429 Too Many" and failed["answers"] == []
    assert "test-key" not in json.dumps(failed)
    # The rerun sends only the request that failed.
    counts = snap_request.write_requests(built, tmp_path, send_them=True)
    assert counts == {"sent": 1, "failed": 0, "already_answered": 1}
    assert len(sent) == 3


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
    assert [r["run_key"] for r in refused] == [first.meta.run_key]
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
