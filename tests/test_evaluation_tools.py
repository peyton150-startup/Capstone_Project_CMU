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
HIDDEN = ("true_fault", "true_machine_id", "ground_truth", "evaluator_only")


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
    report = compare_evaluators.build_report(files, {"f1": {"FN-01": True}})
    assert report["pairs_compared"] == 1
    assert report["agreement_rate"] == 0.0
    assert report["disagreements_for_review"][0]["item_id"] == "f1"
    assert report["unmatched"][0]["item_id"] == "f2"
    assert report["per_provider"]["snap"]["reference_agreement"]["matched"] == 1
    assert report["per_provider"]["jev"]["reference_agreement"]["matched"] == 0
    text = compare_evaluators.markdown(report)
    assert "f1" in text and "Caveats" in text
