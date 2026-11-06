"""Human reference packets stay blind to run identity and model answers."""

import json

import pytest

from evaltools.reference_review import export_requests, import_review


def test_review_packets_hide_run_identity_and_import_checked_answers(tmp_path):
    """The reviewer sees only judge-side state, then answers map back privately."""
    # Variables:
    #   internal: A local item key that must not appear in the blinded packet.
    #   request: A prepared, unsent judge request with one score and one noul.
    internal = "pair::run/1/KA-01-bearing"
    requests = tmp_path / "requests"
    requests.mkdir()
    request = {
        "tags": {
            "family": "RUN",
            "item_id": internal,
            "questions": {
                "evidence_quality": {
                    "id": "RUN-01",
                    "type": "score",
                    "criteria": ["0", "1", "2"],
                },
                "citation": {
                    "id": "RUN-12",
                    "type": "noul",
                    "criteria": {"true": "yes", "false": "no"},
                },
            },
        },
        "body": {"state": {"run_ref": "opaque", "trace": {"completeness": "full"}}},
    }
    (requests / "one.request.json").write_text(json.dumps(request), encoding="utf-8")
    review = tmp_path / "review"
    assert export_requests(requests, review, {"RUN": 1})["items"] == 1
    (opaque,) = json.loads((review / "private_mapping.json").read_text())
    blinded = (review / "blinded" / f"{opaque}.json").read_text()
    assert internal not in blinded and "opaque" in blinded
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({opaque: {"RUN-01": 2, "RUN-12": True}}))
    reference = tmp_path / "reference.json"
    assert import_review(review, answers, reference)["questions_reviewed"] == 2
    assert json.loads(reference.read_text()) == {
        internal: {"RUN-01": 2, "RUN-12": True}
    }
    answers.write_text(json.dumps({opaque: {"RUN-01": 8}}))
    with pytest.raises(ValueError, match="invalid score"):
        import_review(review, answers, reference)


def test_review_export_refuses_a_request_folder_with_model_answers(tmp_path):
    """A reviewer sample must be frozen before the model has answered it."""
    # Variables:
    #   requests: A prepared folder already containing a model answer artifact.
    requests = tmp_path / "requests"
    requests.mkdir()
    (requests / "one.answers.json").write_text("{}")
    with pytest.raises(ValueError, match="model answers already exist"):
        export_requests(requests, tmp_path / "review", {"RUN": 1})
