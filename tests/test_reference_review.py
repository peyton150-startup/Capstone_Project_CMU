"""Human reference packets stay blind to run identity and model answers."""

import json

import pytest

from evaltools.reference_review import export_requests, import_review


def with_judge_questions(request):
    """Populate a synthetic request with exactly the questions sent to SNAP."""
    # Variables:
    #   definitions: Question IDs and criteria kept as request metadata.
    definitions = request["tags"]["questions"]
    request["body"]["questions"] = {
        name: {
            "type": question["type"],
            "instructions": f"Assess {name} from the evidence.",
            "criteria": question["criteria"],
        }
        for name, question in definitions.items()
    }
    return request


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
    (requests / "one.request.json").write_text(
        json.dumps(with_judge_questions(request)), encoding="utf-8"
    )
    review = tmp_path / "review"
    assert export_requests(requests, review, {"RUN": 1})["items"] == 1
    (opaque,) = json.loads((review / "private_mapping.json").read_text())
    blinded = (review / "blinded" / f"{opaque}.json").read_text()
    assert internal not in blinded and "opaque" in blinded
    assert json.loads((review / "answers.template.json").read_text()) == {opaque: {}}
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


def test_function_sample_prefers_items_with_all_judgments(tmp_path):
    """The reference set includes functions whose test questions are answerable."""
    # Variables:
    #   questions: The full function rubric for the evidence-rich candidate.
    #   mapping: The selected opaque ID's private function identity.
    requests = tmp_path / "requests"
    requests.mkdir()
    questions = {
        f"question_{n}": {"id": f"FN-0{n}", "type": "noul", "criteria": {}}
        for n in (1, 2, 3)
    }
    for item_id, selected in (
        ("fn_sparse", {"question_1": questions["question_1"]}),
        ("fn_full", questions),
    ):
        (requests / f"{item_id}.request.json").write_text(
            json.dumps(
                with_judge_questions(
                    {
                        "tags": {"family": "FN", "item_id": item_id, "questions": selected},
                        "body": {"state": {"function_id": item_id}},
                    }
                )
            ),
            encoding="utf-8",
        )
    review = tmp_path / "review"
    export_requests(requests, review, {"FN": 1})
    mapping = json.loads((review / "private_mapping.json").read_text())
    assert list(mapping.values()) == ["fn_full"]


def test_run_strata_guarantees_blind_sound_and_misleading_cases(tmp_path):
    """A private curated map guarantees both kinds without showing their labels."""
    # Variables:
    #   requests: A minimal unsent cohort containing one sound and two misleading runs.
    #   mapping: The private opaque-to-internal identity lookup for the blind sample.
    requests = tmp_path / "requests"
    requests.mkdir()
    for item_id in ("sound-case", "misleading-case", "spare-case"):
        (requests / f"{item_id}.request.json").write_text(
            json.dumps(
                with_judge_questions({
                    "tags": {
                        "family": "RUN",
                        "item_id": item_id,
                        "questions": {
                            "quality": {
                                "id": "RUN-01",
                                "type": "score",
                                "criteria": ["0", "1"],
                            }
                        },
                    },
                    "body": {
                        "state": {
                            "run_ref": "opaque",
                            "trace": {"completeness": "full"},
                        }
                    },
                })
            ),
            encoding="utf-8",
        )
    out = tmp_path / "blind"
    export_requests(
        requests,
        out,
        {"RUN": 2},
        run_strata={"sound-case": "sound", "misleading-case": "misleading"},
    )
    mapping = json.loads((out / "private_mapping.json").read_text())
    assert set(mapping.values()) == {"sound-case", "misleading-case"}
    for opaque in mapping:
        packet = (out / "blinded" / f"{opaque}.json").read_text()
        assert "sound-case" not in packet
        assert "misleading-case" not in packet
        assert '"sound"' not in packet
        assert '"misleading"' not in packet


def test_run_strata_fail_closed_when_balanced_review_is_impossible(tmp_path):
    """A missing negative example must not be presented as a calibrated sample."""
    # Variables:
    #   requests: A candidate with evidence sufficient for RUN review.
    #   selected: A private stratum map missing a deliberately misleading case.
    requests = tmp_path / "requests"
    requests.mkdir()
    (requests / "one.request.json").write_text(
        json.dumps(
            {
                "tags": {"family": "RUN", "item_id": "only", "questions": {}},
                "body": {"state": {"trace": {"completeness": "full"}}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError, match="no full-trace RUN item in misleading stratum"
    ):
        export_requests(
            requests,
            tmp_path / "review",
            {"RUN": 2},
            run_strata={"only": "sound"},
        )
