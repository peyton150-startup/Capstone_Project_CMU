import json
from pathlib import Path

import pytest

from capstone.memory import duplicate_threshold as d
from capstone.memory.contracts import EpisodicMemory
from capstone.memory.policy import _HIDDEN, _SAMPLE
from capstone.memory.semantic import memory_document

PAIRS = Path(__file__).parents[1] / "docs" / "benchmarks" / "near-duplicate-pairs.jsonl"


def test_pair_text_is_the_text_a_stored_memory_is_embedded_as():
    memory = EpisodicMemory.model_construct(
        category="alarm",
        symptoms=("alarm",),  # a real memory's symptoms are its anomaly kind
        diagnosis="Spindle bearing wear on CNC-03",
        lesson="Compare the alarmed machine's vibration with the others.",
    )
    assert d.pair_text("alarm", memory.diagnosis, memory.lesson) == memory_document(
        memory
    )


def test_cosine():
    assert d.cosine([1, 0], [2, 0]) == pytest.approx(1)
    assert d.cosine([1, 0], [0, 3]) == pytest.approx(0)
    with pytest.raises(ValueError):
        d.cosine([0, 0], [1, 0])


def test_threshold_sits_just_above_every_different_pair():
    scored = [(0.9089, "different"), (0.5, "different"), (0.95, "same")]
    assert d.choose_threshold(scored) == 0.909
    # Strictly above: a different pair exactly on a round value is still kept.
    assert d.choose_threshold([(0.9, "different")]) == 0.901


def test_unsure_and_same_pairs_never_set_the_threshold():
    assert d.choose_threshold([(0.99, "unsure"), (0.98, "same")]) is None
    assert d.choose_threshold([(0.99, "unsure"), (0.7, "different")]) == 0.701


def test_evaluate_counts_what_a_threshold_would_do():
    scored = [(0.95, "same"), (0.85, "same"), (0.88, "different"), (0.99, "unsure")]
    assert d.evaluate(scored, 0.9) == {
        "same_pairs": 2,
        "same_caught": 1,
        "different_pairs": 1,
        "different_refused": 0,
    }


def row(pid, label, a, b, held_out=False):
    return {
        "id": pid,
        "category": "alarm",
        "outcome": "resolved",
        "machine": "CNC-03",
        "a": {"diagnosis": "d", "lesson": a},
        "b": {"diagnosis": "d", "lesson": b},
        "label": label,
        "held_out": held_out,
    }


def fake_embed(texts):
    """One axis per lesson word; texts sharing more words score higher."""
    vocab = ["vibration", "bearing", "speed", "batch"]
    return [[float(t.split("\n")[-1].count(w)) + 0.01 for w in vocab] for t in texts]


def test_measure_chooses_on_training_pairs_and_checks_held_out():
    rows = [
        row("P1", "same", "vibration bearing", "vibration bearing bearing"),
        row("P2", "different", "vibration bearing", "speed batch"),
        row("P3", "unsure", "vibration", "vibration"),
        row("P4", "different", "vibration", "vibration speed", held_out=True),
    ]
    report = d.measure(rows, fake_embed)
    scores = {p["id"]: p["score"] for p in report["pairs"]}
    assert report["threshold"] == d.choose_threshold([(scores["P2"], "different")])
    assert report["train"]["different_pairs"] == 1  # P4 held out, P3 unsure
    assert report["held_out"]["different_pairs"] == 1
    assert scores["P1"] > scores["P2"]


def test_read_pairs_refuses_an_unlabelled_pair(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(row("P1", None, "a", "b")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="P1"):
        d.read_pairs(path)


def test_committed_pairs_are_labelled_and_could_pass_the_gate():
    rows = d.read_pairs(PAIRS)
    assert len(rows) == 60
    assert [r["held_out"] for r in rows] == [n % 5 == 0 for n in range(1, 61)]
    for r in rows:
        for side in ("a", "b"):
            lesson = r[side]["lesson"]
            # The gate refuses numbers with units, ticks and hidden-truth words.
            assert not _SAMPLE.search(lesson) and not _HIDDEN.search(lesson)
