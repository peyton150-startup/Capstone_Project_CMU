"""Evaluator integrity regression tests using real request and inventory shapes.

All tests operate on saved metadata and synthetic evidence; none contacts SNAP.
"""

import json
from types import SimpleNamespace

import pytest

from evaltools import (
    audit_preflight,
    compare_evaluators,
    decision_models,
    reference_review,
    run_packet,
    snap_request,
)


def judge_request():
    """Build a real unsent request with the current rubric and one RUN question."""
    # Variables:
    #   question: A validated current rubric question with its missing-evidence rule.
    question = next(q for q in snap_request.load_questions()[1] if q.id == "RUN-01")
    built = snap_request.build_request(
        {"trace": {"completeness": "full"}},
        [question],
        model="subq-snap-1.1",
        item_id="synthetic-run",
        meta={"family": "RUN", "rubric_version": "1.1.0"},
        state_tokens=None,
    )
    return built[0], question


def test_blind_review_shows_exactly_the_question_sent_to_snap(tmp_path):
    """Reviewer-only notes cannot alter the question the human evaluates."""
    # Variables:
    #   item: The actual judge request, including body and richer private tags.
    item, question = judge_request()
    item["tags"]["questions"][question.name]["scoring_note"] = (
        "do not show this reviewer-only note"
    )
    requests = tmp_path / "requests"
    requests.mkdir()
    (requests / "one.request.json").write_text(json.dumps(item))
    folder = tmp_path / "blind"
    reference_review.export_requests(requests, folder, {"RUN": 1})
    opaque = reference_review.review_id("synthetic-run")
    packet = json.loads((folder / "blinded" / f"{opaque}.json").read_text())
    assert packet["questions"][question.id] == {
        "id": question.id,
        **item["body"]["questions"][question.name],
    }
    assert "scoring_note" not in packet["questions"][question.id]
    assert question.missing_evidence in packet["questions"][question.id]["instructions"]


def test_blind_review_rejects_changed_judge_criteria(tmp_path):
    """Tagged questions cannot silently override the actual judge request."""
    # Variables:
    #   item: A request whose private metadata contradicts the provider body.
    item, question = judge_request()
    item["tags"]["questions"][question.name]["criteria"] = ["different"]
    requests = tmp_path / "requests"
    requests.mkdir()
    (requests / "bad.request.json").write_text(json.dumps(item))
    with pytest.raises(ValueError, match="criteria differ"):
        reference_review.export_requests(requests, tmp_path / "blind", {"RUN": 1})


def test_reference_import_refuses_changed_private_mapping(tmp_path):
    """A valid blind answer cannot be reassigned to a different real run."""
    # Variables:
    #   mapping: The reviewer ID to run ID link, intentionally tampered with.
    item, question = judge_request()
    requests = tmp_path / "requests"
    requests.mkdir()
    (requests / "one.request.json").write_text(json.dumps(item))
    folder = tmp_path / "blind"
    reference_review.export_requests(requests, folder, {"RUN": 1})
    path = folder / "private_mapping.json"
    mapping = json.loads(path.read_text())
    opaque = next(iter(mapping))
    mapping[opaque] = "different-run"
    path.write_text(json.dumps(mapping))
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({opaque: {question.id: 0}}))
    output = tmp_path / "mapped.json"
    with pytest.raises(ValueError, match="mapping does not match"):
        reference_review.import_review(folder, answers, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "versions",
    [("1.0.0", "1.1.0"), ("1.1.0", None), (None, None)],
)
def test_comparison_rejects_mixed_or_unversioned_batches(versions):
    """Scores are not comparable without the same identifiable rubric."""
    # Variables:
    #   files: Saved results from two hypothetical provider requests.
    files = [
        {"tags": {"provider": "snap", "rubric_version": version}, "answers": []}
        for version in versions
    ]
    with pytest.raises(ValueError, match="rubric versions"):
        compare_evaluators.build_report(files, None)


def test_trace_preflight_fails_on_unknown_citations():
    """A false evidence ID must never enter the scored RUN cohort."""
    # Variables:
    #   trace: An otherwise complete audit that cites an observation never stored.
    trace = SimpleNamespace(
        completeness="full",
        evidence=[SimpleNamespace(id="real", origin="sensor", content="load 45")],
        hypotheses=[],
        decisions=[],
        conclusion=SimpleNamespace(evidence_ids=["invented"]),
        recheck=None,
        verification=None,
    )
    packet = SimpleNamespace(
        meta=SimpleNamespace(audit_file="audit.jsonl", episode_key="offline/1"),
        snap_view=SimpleNamespace(trace=trace),
    )
    with pytest.raises(ValueError, match="unknown cited evidence IDs"):
        audit_preflight.require_full_traces([packet])


def test_function_test_context_and_tool_test_context_are_visible():
    """FN and TL judgments receive the same local test context as TS judgments."""
    # Variables:
    #   inventories: Real test links and function/tool metadata used by the evaluator.
    root = snap_request.INVENTORY
    functions = json.loads((root / "FUNCTION_INVENTORY.json").read_text())["functions"]
    tests = json.loads((root / "TEST_INVENTORY.json").read_text())["tests"]
    tools = json.loads((root / "TOOL_INVENTORY.json").read_text())["tools"]
    by_test = {t["id"]: t for t in tests}
    by_function = {f["id"]: f for f in functions}
    case = next(
        t
        for t in tests
        if t["name"]
        == "test_bearing_health_outside_unit_interval_is_rejected_on_assignment"
    )
    function = next(f for f in functions if f["direct_tests"])
    function = {
        **function,
        "direct_tests": [case["id"]],
        "indirect_tests": [],
        "test_count": 1,
    }
    state = snap_request.function_state(function, by_test, complete=True)
    assert "@pytest.mark.parametrize" in " ".join(state["tests"][0]["decorators"])
    tool = next(t for t in tools if t["tests"])
    tool_state = snap_request.tool_state(tool, by_function, by_test)
    assert any(
        isinstance(test, dict) and test.get("source") for test in tool_state["tests"]
    )
    missing_state = snap_request.tool_state(tool, by_function, {})
    assert missing_state["test_evidence_incomplete"]
    questions = [q for q in snap_request.load_questions()[1] if q.family == "TL"]
    built = snap_request.item_requests(
        [(tool["name"], missing_state)],
        questions,
        [decision_models.PROVIDERS["snap"]],
        meta={"family": "TL", "rubric_version": "1.1.0"},
        state_tokens=None,
    )
    assert built[0]["tags"]["skipped_questions"]["TL-03"].startswith("unknown:")


def test_blind_review_rejects_mismatched_question_ids(tmp_path):
    """An altered private ID cannot reassign an actual judge question."""
    # Variables:
    #   item: A judge request whose metadata ID no longer matches the request.
    item, question = judge_request()
    item["tags"]["questions"][question.name]["id"] = "RUN-99"
    requests = tmp_path / "requests"
    requests.mkdir()
    (requests / "tampered.request.json").write_text(json.dumps(item))
    with pytest.raises(ValueError, match="question IDs differ"):
        reference_review.export_requests(requests, tmp_path / "blind", {"RUN": 1})


def test_tl01_question_and_boolean_criteria_have_matching_polarity():
    """TL-01 must ask if the boundary is enforced, not if a leak is possible."""
    # Variables:
    #   question: The current model-visible TL-01 definition.
    raw, questions = snap_request.load_questions()
    question = next(item for item in questions if item.id == "TL-01")
    assert raw["rubric_version"] == run_packet.RUBRIC_VERSION == "1.1.1"
    assert question.type == "noul"
    assert "Is the access boundary enforced" in question.to_request()["instructions"]
    assert "Can the tool return" not in question.instructions
    assert "no hidden field or secret can pass" in question.criteria["true"]
    assert "A code path can return hidden state" in question.criteria["false"]
