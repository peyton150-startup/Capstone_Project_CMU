"""Blinded reviewer calibration contracts, exercised without an API request."""

import json

import pytest

from evaltools import reference_review


def prepared_requests(root, *, family="RUN", identifier="test-case"):
    directory = root / "requests"
    directory.mkdir(exist_ok=True)
    request = {
        "tags": {
            "family": family,
            "item_id": identifier,
            "questions": {
                "one": {
                    "id": "RUN-01",
                    "type": "score",
                    "criteria": ["bad", "good"],
                },
                "two": {
                    "id": "RUN-02",
                    "type": "choice",
                    "criteria": ["yes", "no"],
                },
                "three": {
                    "id": "RUN-03",
                    "type": "noul",
                    "criteria": {"true": "yes", "false": "no"},
                },
            },
        },
        "body": {
            "state": {
                "trace": {"completeness": "full"},
                "run_ref": "opaque",
            }
        },
    }
    request["body"]["questions"] = {
        name: {
            "type": question["type"],
            "instructions": f"Judge {name} against the evidence.",
            "criteria": question["criteria"],
        }
        for name, question in request["tags"]["questions"].items()
    }
    (directory / f"{identifier}.request.json").write_text(
        json.dumps(request), encoding="utf-8"
    )
    return directory, request


def test_review_refuses_conflicting_states_for_one_internal_item(tmp_path):
    requests, packet = prepared_requests(tmp_path)
    packet["body"]["state"]["run_ref"] = "different"
    (requests / "second.request.json").write_text(json.dumps(packet))
    with pytest.raises(ValueError, match="two different states"):
        reference_review.export_requests(requests, tmp_path / "review", {"RUN": 1})


@pytest.mark.parametrize(
    "strata, message",
    [
        ({"test-case": "guess"}, "run strata must map"),
        ({"absent": "sound"}, "unknown RUN IDs"),
        (["sound"], "run strata must map"),
    ],
)
def test_review_refuses_untrusted_strata_metadata(tmp_path, strata, message):
    requests, _ = prepared_requests(tmp_path)
    with pytest.raises(ValueError, match=message):
        reference_review.export_requests(
            requests,
            tmp_path / "review",
            {"RUN": 2},
            run_strata=strata,
        )


def test_review_requires_enough_slots_for_stratification(tmp_path):
    requests, _ = prepared_requests(tmp_path)
    with pytest.raises(ValueError, match="at least two RUN review slots"):
        reference_review.export_requests(
            requests,
            tmp_path / "review",
            {"RUN": 1},
            run_strata={"test-case": "sound"},
        )


def test_review_does_not_silently_reuse_a_blinded_id(tmp_path, monkeypatch):
    requests, _ = prepared_requests(tmp_path)
    extra = json.loads((requests / "test-case.request.json").read_text())
    extra["tags"]["item_id"] = "second"
    (requests / "second.request.json").write_text(json.dumps(extra))
    monkeypatch.setattr(reference_review, "review_id", lambda _: "duplicate")
    with pytest.raises(ValueError, match="review ID collision"):
        reference_review.export_requests(requests, tmp_path / "review", {"RUN": 2})


@pytest.mark.parametrize(
    "answers, reason",
    [
        ({"RUN-01": True}, "invalid score"),
        ({"RUN-01": 3}, "invalid score"),
        ({"RUN-01": -1}, "invalid score"),
        ({"RUN-02": "maybe"}, "invalid choice"),
        ({"RUN-03": "true"}, "answer true or false"),
        ({"unknown": 1}, "unknown question ID"),
    ],
)
def test_reference_import_refuses_invalid_answers(tmp_path, answers, reason):
    requests, _ = prepared_requests(tmp_path)
    review_dir = tmp_path / "review"
    reference_review.export_requests(requests, review_dir, {"RUN": 1})
    mapping = json.loads((review_dir / "private_mapping.json").read_text())
    opaque = next(iter(mapping))
    answer_file = tmp_path / "answers.json"
    answer_file.write_text(json.dumps({opaque: answers}), encoding="utf-8")
    result = tmp_path / "reference.json"
    with pytest.raises(ValueError, match=reason):
        reference_review.import_review(review_dir, answer_file, result)
    assert not result.exists()


def test_reference_import_rejects_unknown_blinded_identity(tmp_path):
    requests, _ = prepared_requests(tmp_path)
    review_dir = tmp_path / "review"
    reference_review.export_requests(requests, review_dir, {"RUN": 1})
    answer_file = tmp_path / "answers.json"
    answer_file.write_text(json.dumps({"unrecognized": {}}))
    with pytest.raises(ValueError, match="unknown review ID"):
        reference_review.import_review(review_dir, answer_file, tmp_path / "ref.json")


def test_reference_cli_fails_before_exporting_negative_limits(tmp_path):
    requests, _ = prepared_requests(tmp_path)
    with pytest.raises(SystemExit) as stopped:
        reference_review.main(
            [
                "export",
                "--requests",
                str(requests),
                "--out",
                str(tmp_path / "review"),
                "--run",
                "-1",
            ]
        )
    assert stopped.value.code == 2
    assert not (tmp_path / "review").exists()


def test_reference_cli_exports_and_imports_without_exposing_case_ids(tmp_path, capsys):
    requests, _ = prepared_requests(tmp_path)
    review_dir = tmp_path / "review"
    assert (
        reference_review.main(
            [
                "export",
                "--requests",
                str(requests),
                "--out",
                str(review_dir),
                "--run",
                "1",
                "--function",
                "0",
                "--test",
                "0",
                "--tool",
                "0",
                "--batch",
                "0",
            ]
        )
        == 0
    )
    mapping = json.loads((review_dir / "private_mapping.json").read_text())
    opaque = next(iter(mapping))
    answer_path = tmp_path / "answers.json"
    answer_path.write_text(
        json.dumps({opaque: {"RUN-01": 1, "RUN-02": "yes", "RUN-03": False}})
    )
    result_path = tmp_path / "mapped.json"
    assert (
        reference_review.main(
            [
                "import",
                "--review-dir",
                str(review_dir),
                "--answers",
                str(answer_path),
                "--out",
                str(result_path),
            ]
        )
        == 0
    )
    assert json.loads(result_path.read_text()) == {
        "test-case": {"RUN-01": 1, "RUN-02": "yes", "RUN-03": False}
    }
    assert "questions_reviewed" in capsys.readouterr().out
