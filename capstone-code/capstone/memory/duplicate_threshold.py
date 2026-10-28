# Measures the similarity threshold for the planned near-duplicate memory check.
# Responsibility: score labelled lesson pairs and pick a threshold; stores nothing.
"""Measure where "same lesson" ends and "different lesson" begins.

Input is a JSONL file of labelled pairs (docs/benchmarks/near-duplicate-pairs.jsonl).
Each pair shares category, outcome and machine, as the planned check would
require, and is labelled "same", "different" or "unsure" by a person.

    uv run python -m capstone.memory.duplicate_threshold \
        --pairs docs/benchmarks/near-duplicate-pairs.jsonl --out scores.json

Both texts of a pair are embedded as passages, the way stored memories are,
and compared by cosine similarity. The threshold is chosen on the pairs not
held out: the smallest value, to three decimals, strictly above every
"different" pair, because refusing a different lesson loses it silently
while letting a duplicate through only crowds recall. The held-out pairs then
show whether it holds. "unsure" pairs are scored and reported, never used.

This is a measurement only. Nothing here is called by the memory service.
"""

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path

LABELS = ("same", "different", "unsure")


def pair_text(category: str, diagnosis: str, lesson: str) -> str:
    """The text a memory is embedded as (`semantic.memory_document`).

    A memory's symptoms are its anomaly kind, which is also its category.
    """
    return "\n".join((category, category, diagnosis, lesson))


def cosine(u: Sequence[float], v: Sequence[float]) -> float:
    # Variables:
    #   dot: Sum of the products of matching entries.
    #   norm: Product of the two vectors' lengths.
    dot = sum(a * b for a, b in zip(u, v, strict=True))
    norm = math.sqrt(sum(a * a for a in u) * sum(b * b for b in v))
    if norm == 0:
        raise ValueError("cannot compare a zero vector")
    return dot / norm


def choose_threshold(scored: Sequence[tuple[float, str]]) -> float | None:
    """Smallest three-decimal value strictly above every "different" score.

    None when there is no "different" pair to stay above.
    """
    # Variables:
    #   scored: Each pair's similarity score with its human label.
    #   different: Scores of pairs a person labelled as different lessons.
    different = [score for score, label in scored if label == "different"]
    if not different:
        return None
    return math.floor(max(different) * 1000 + 1) / 1000


def evaluate(scored: Sequence[tuple[float, str]], threshold: float) -> dict:
    """What a threshold would do: refusals of different lessons, duplicates caught."""
    # Variables:
    #   same: Scores of pairs labelled as the same lesson.
    #   different: Scores of pairs labelled as different lessons.
    same = [score for score, label in scored if label == "same"]
    different = [score for score, label in scored if label == "different"]
    return {
        "same_pairs": len(same),
        "same_caught": sum(score >= threshold for score in same),
        "different_pairs": len(different),
        "different_refused": sum(score >= threshold for score in different),
    }


def read_pairs(path: Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        if row.get("label") not in LABELS:
            raise ValueError(f"pair {row.get('id')} has no label from {LABELS}")
    return rows


def measure(rows: Sequence[dict], embed) -> dict:
    """Score every pair with `embed` (passage side) and pick the threshold."""
    # Variables:
    #   embed: Turns texts into vectors, the way stored memories are embedded.
    #   texts: Both sides of every pair, in order, so pair i is entries 2i and 2i+1.
    #   vectors: One vector per text.
    #   scores: Similarity of each pair, by pair id.
    #   train: Scores and labels of pairs used to choose the threshold.
    #   held: Scores and labels of pairs kept back to test it.
    texts = [
        pair_text(row["category"], row[side]["diagnosis"], row[side]["lesson"])
        for row in rows
        for side in ("a", "b")
    ]
    vectors = list(embed(texts))
    scores = {
        row["id"]: round(cosine(vectors[2 * i], vectors[2 * i + 1]), 4)
        for i, row in enumerate(rows)
    }
    train = [(scores[r["id"]], r["label"]) for r in rows if not r["held_out"]]
    held = [(scores[r["id"]], r["label"]) for r in rows if r["held_out"]]
    threshold = choose_threshold(train)
    return {
        "threshold": threshold,
        "train": evaluate(train, threshold) if threshold is not None else None,
        "held_out": evaluate(held, threshold) if threshold is not None else None,
        "pairs": [
            {
                "id": row["id"],
                "label": row["label"],
                "held_out": row["held_out"],
                "outcome": row["outcome"],
                "score": scores[row["id"]],
            }
            for row in rows
        ],
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="write the full report as JSON")
    args = parser.parse_args(argv)

    from capstone.memory.semantic import default_embedder
    from capstone.providers.embeddings import embedders_for
    from capstone.settings import get_settings

    settings = get_settings()
    embedders = embedders_for(settings)  # None: the local model
    embed = embedders[0] if embedders is not None else default_embedder()
    report = {"model": settings.embedding_model}
    report |= measure(read_pairs(args.pairs), embed)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps({k: report[k] for k in ("model", "threshold", "train", "held_out")})
    )


if __name__ == "__main__":
    main()
