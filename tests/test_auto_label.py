"""The auto-labeller turns typed judgments into proposed labels, and compares them."""

import json

import pytest

from capstone.evaluation import auto_label
from capstone.evaluation.auto_label import (
    Proposal,
    agreement,
    batches_in,
    conclusions,
    machines_in,
    propose,
)
from capstone.evaluation.labels import Label
from capstone.providers.typesafe import Choice, Judgments, Noul
from capstone.tools.diagnosis import FAULT_KINDS, Diagnosis


class FakeClient:
    """Answers each cause question from `causes` and picks `targets` (else the first option)."""

    model = "jev-latest"

    def __init__(self, causes=None, targets=None, target_confidence=0.9):
        self.causes = causes or {}
        self.targets = targets or {}
        self.target_confidence = target_confidence
        self.asked = []

    def ask(self, state, questions):
        self.asked.append((state, questions))
        answers = {}
        for name, question in questions.items():
            kind, fault = name.split("/")
            if isinstance(question, Noul):
                answers[name] = {"type": "noul", "noul": self.causes.get(fault, 0.02)}
            else:
                assert isinstance(question, Choice)
                choice = self.targets.get(fault, next(iter(question.options)))
                answers[name] = {
                    "type": "choice",
                    "choice": choice,
                    "confidence": self.target_confidence,
                    "probabilities": {o: float(o == choice) for o in question.options},
                }
        return Judgments(model="jev-2026-09-10", answers=answers)


def test_candidates_are_found_in_the_text_in_order():
    text = "CNC-05 then CNC-02, CNC-05 again; batch 2 and batches 3, not job 11"
    assert machines_in(text) == ["CNC-05", "CNC-02"]
    assert batches_in(text) == [2, 3]
    assert machines_in("no machines here") == [] and batches_in("B-12 only") == []


def test_one_request_asks_every_cause_and_a_target_for_each():
    client = FakeClient()
    propose("run", "vibration rose on CNC-02 and CNC-05 in batch 2", client)
    ((state, questions),) = client.asked
    assert state == {"conclusion": "vibration rose on CNC-02 and CNC-05 in batch 2"}
    assert {f"cause/{f}" for f in FAULT_KINDS} <= set(questions)
    assert {f"target/{f}" for f in FAULT_KINDS} <= set(questions)
    machine = questions["target/bearing_degradation"]
    assert list(machine.options) == ["CNC-02", "CNC-05", "none"]
    assert list(questions["target/bad_material_batch"].options) == ["batch 2", "none"]


def test_no_mentioned_id_means_no_target_question():
    client = FakeClient()
    propose("run", "jobs 11 and 13 failed inspection", client)
    assert not any(name.startswith("target/") for name in client.asked[0][1])


def test_a_clear_bearing_conclusion_becomes_a_label():
    client = FakeClient(
        causes={"bearing_degradation": 0.95}, targets={"bearing_degradation": "CNC-05"}
    )
    proposal = propose("run-1", "CNC-02 is fine; CNC-05 bearing wear", client)
    assert proposal.label == Label(
        run_key="run-1",
        diagnosis=Diagnosis(fault="bearing_degradation", machine_id="CNC-05"),
        labelled_by="typesafe/jev-2026-09-10",
    )
    assert not proposal.needs_review
    assert proposal.cause_probabilities["bearing_degradation"] == 0.95


def test_a_batch_is_read_back_as_its_number():
    client = FakeClient(
        causes={"bad_material_batch": 0.9}, targets={"bad_material_batch": "batch 2"}
    )
    proposal = propose("run", "batch 2 is bad", client)
    assert proposal.label.diagnosis == Diagnosis(fault="bad_material_batch", batch_id=2)


def test_several_named_causes_give_a_list():
    client = FakeClient(
        causes={"bearing_degradation": 0.9, "wrong_setting": 0.8},
        targets={"bearing_degradation": "CNC-02", "wrong_setting": "CNC-04"},
    )
    proposal = propose("run", "CNC-02 bearing; CNC-04 speed setting wrong", client)
    assert proposal.label.diagnosis == [
        Diagnosis(fault="bearing_degradation", machine_id="CNC-02"),
        Diagnosis(fault="wrong_setting", machine_id="CNC-04"),
    ]


def test_naming_no_cause_is_a_none_label():
    proposal = propose("run", "Investigation in progress on CNC-03", FakeClient())
    assert proposal.label.diagnosis is None
    assert not proposal.needs_review


def test_the_none_option_leaves_the_target_empty():
    client = FakeClient(causes={"false_alarm": 0.9}, targets={"false_alarm": "none"})
    proposal = propose("run", "transient spike; CNC-01 was checked", client)
    assert proposal.label.diagnosis == Diagnosis(fault="false_alarm")


def test_undetermined_is_labelled_none_without_asking():
    client = FakeClient()
    proposal = propose("run", "undetermined", client)
    assert proposal.label.diagnosis is None and client.asked == []


@pytest.mark.parametrize("probability", [0.5, 0.31, 0.69])
def test_an_unclear_cause_is_marked_for_review(probability):
    client = FakeClient(causes={"wrong_setting": probability})
    proposal = propose("run", "maybe a setting", client)
    assert proposal.needs_review
    assert "wrong_setting" in proposal.review_reasons[0]


def test_a_weakly_chosen_machine_is_marked_for_review():
    client = FakeClient(causes={"bearing_degradation": 0.9}, target_confidence=0.3)
    proposal = propose("run", "bearing on CNC-01 or CNC-02", client)
    assert proposal.needs_review
    assert proposal.label.diagnosis is not None


def _proposal(key, diagnosis, review=False):
    return Proposal(
        label=Label(run_key=key, diagnosis=diagnosis, labelled_by="typesafe/jev"),
        needs_review=review,
    )


def test_agreement_compares_causes_and_targets_with_hand_labels():
    bearing = Diagnosis(fault="bearing_degradation", machine_id="CNC-02", summary="x")
    hand = {
        "a": Label(
            run_key="a",
            diagnosis=Diagnosis(fault="bearing_degradation", machine_id="CNC-02"),
            labelled_by="dev",
        ),
        "b": Label(run_key="b", diagnosis=None, labelled_by="dev"),
        "c": Label(
            run_key="c",
            diagnosis=Diagnosis(fault="false_alarm", machine_id="CNC-01"),
            labelled_by="dev",
        ),
    }
    proposals = [
        _proposal("a", bearing),  # same cause and machine; the summary is ignored
        _proposal("b", None, review=True),
        _proposal(
            "c", Diagnosis(fault="false_alarm", machine_id="CNC-03")
        ),  # wrong machine
        _proposal("unlabelled", None),
    ]
    result = agreement(proposals, hand)
    assert (result.compared, result.agreed) == (3, 2)
    assert (result.unreviewed_compared, result.unreviewed_agreed) == (2, 1)
    assert result.disagreements == {"c": ("false_alarm CNC-03", "false_alarm CNC-01")}


def test_conclusions_read_only_the_key_and_the_words(tmp_path):
    path = tmp_path / "results.jsonl"
    rows = [
        {"run_key": "a", "conclusion": "first", "score": {"true_fault": "secret"}},
        {"run_key": "b", "conclusion": None},
        {"run_key": "a", "conclusion": "rerun"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert conclusions([path]) == {"a": "rerun"}


def test_the_command_writes_proposals_and_reports_agreement(
    tmp_path, monkeypatch, capsys
):
    results = tmp_path / "results.jsonl"
    results.write_text(
        json.dumps({"run_key": "a", "conclusion": "undetermined"}) + "\n",
        encoding="utf-8",
    )
    hand = tmp_path / "hand.jsonl"
    hand.write_text(
        Label(run_key="a", diagnosis=None, labelled_by="dev").model_dump_json() + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "proposals.jsonl"
    monkeypatch.setattr(auto_label, "judgment_client", lambda settings: FakeClient())

    assert auto_label.main([str(results), "--out", str(out), "--hand", str(hand)]) == 0
    (line,) = out.read_text(encoding="utf-8").splitlines()
    assert Proposal.model_validate_json(line).label.diagnosis is None
    assert "agree with hand labels: 1 of 1" in capsys.readouterr().out
