"""Prepare blinded human-review packets and import the reviewer's answers.

Export reads dry-run request bodies only. It refuses a folder containing model
answers so the reference can be frozen before SNAP is consulted.
"""

import argparse
import hashlib
import json
from pathlib import Path


def review_id(item_id: str) -> str:
    """Give the reviewer an opaque stable ID instead of a fault-bearing run key."""
    # Variables:
    #   item_id: The evaluator's private key, hashed before the reviewer sees it.
    return hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:16]


def export_requests(
    requests: Path,
    out: Path,
    limits: dict[str, int],
    *,
    run_strata: dict[str, str] | None = None,
) -> dict:
    """Write blind packets; optionally require both sound and misleading RUNs."""
    # Variables:
    #   items: One state and its questions per internal item, across request chunks.
    #   chosen: The sampled items, preferring full RUN traces and function
    #     states with all three questions before opaque-ID ordering.
    #   mapping: Private link from each blinded ID back to its evaluator item.
    #   visible: The judge's exact question body, with only the private question ID added.
    #   defined: The tagged definition, checked against the judge's actual question.
    #   question_ids: IDs used for import, checked against the request's own ID list.
    if any(requests.glob("*.answers.json")):
        raise ValueError(
            "model answers already exist; prepare references before sending"
        )
    items: dict[tuple[str, str], dict] = {}
    for path in sorted(requests.glob("*.request.json")):
        saved = json.loads(path.read_text(encoding="utf-8"))
        body, tags = saved.get("body"), saved.get("tags", {})
        if body is None or tags.get("family") not in limits:
            continue
        key = (tags["family"], tags["item_id"])
        item = items.setdefault(
            key,
            {"family": key[0], "state": body["state"], "questions": {}},
        )
        if item["state"] != body["state"]:
            raise ValueError(f"two different states for {key[0]} item")
        sent = body.get("questions", {})
        defined = tags.get("questions", {})
        if not isinstance(sent, dict) or set(sent) != set(defined):
            raise ValueError("review questions differ from the judge request")
        question_ids = [question["id"] for question in defined.values()]
        if len(question_ids) != len(set(question_ids)) or (
            "question_ids" in tags and set(question_ids) != set(tags["question_ids"])
        ):
            raise ValueError("review question IDs differ from the judge request")
        for name, question in sent.items():
            tagged = defined[name]
            if (
                not isinstance(question, dict)
                or question.get("type") != tagged.get("type")
                or question.get("criteria") != tagged.get("criteria")
            ):
                raise ValueError(
                    "review question criteria differ from the judge request"
                )
            visible = {"id": tagged["id"], **question}
            prior = item["questions"].get(tagged["id"])
            if prior is not None and prior != visible:
                raise ValueError(
                    "same review question has different judge instructions"
                )
            item["questions"][tagged["id"]] = visible
    if run_strata is not None:
        run_ids = {item_id for family, item_id in items if family == "RUN"}
        if not isinstance(run_strata, dict) or any(
            not isinstance(item_id, str) or label not in ("sound", "misleading")
            for item_id, label in run_strata.items()
        ):
            raise ValueError("run strata must map RUN IDs to sound or misleading")
        if set(run_strata) - run_ids:
            raise ValueError("run strata include unknown RUN IDs")
    chosen = []
    for family, limit in limits.items():
        candidates = sorted(
            (
                (item_id, item)
                for (kind, item_id), item in items.items()
                if kind == family
            ),
            key=lambda pair: (
                pair[1]["state"].get("trace", {}).get("completeness") != "full"
                if family == "RUN"
                else False,
                -len(pair[1]["questions"]) if family == "FN" else 0,
                review_id(pair[0]),
            ),
        )
        selected = candidates[:limit]
        if family == "RUN" and run_strata is not None and limit:
            if limit < 2:
                raise ValueError(
                    "at least two RUN review slots are needed for both strata"
                )
            required = []
            for label in ("sound", "misleading"):
                match = next(
                    (
                        pair
                        for pair in candidates
                        if run_strata.get(pair[0]) == label
                        and pair[1]["state"].get("trace", {}).get("completeness")
                        == "full"
                    ),
                    None,
                )
                if match is None:
                    raise ValueError(f"no full-trace RUN item in {label} stratum")
                required.append(match)
            selected_ids = {item_id for item_id, _ in required}
            selected = (
                required
                + [pair for pair in candidates if pair[0] not in selected_ids][
                    : limit - len(required)
                ]
            )
        chosen.extend((item_id, item) for item_id, item in selected)
    out.mkdir(parents=True, exist_ok=False)
    blinded = out / "blinded"
    blinded.mkdir()
    mapping = {}
    manifest = []
    for item_id, item in chosen:
        opaque = review_id(item_id)
        if opaque in mapping:
            raise ValueError("review ID collision")
        mapping[opaque] = item_id
        packet = {"review_id": opaque, **item}
        path = blinded / f"{opaque}.json"
        path.write_text(json.dumps(packet, indent=1) + "\n", encoding="utf-8")
        manifest.append(
            {
                "review_id": opaque,
                "family": item["family"],
                "questions": sorted(item["questions"]),
            }
        )
    (out / "private_mapping.json").write_text(
        json.dumps(mapping, indent=1) + "\n", encoding="utf-8"
    )
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
    )
    (out / "answers.template.json").write_text(
        json.dumps({item["review_id"]: {} for item in manifest}, indent=1) + "\n",
        encoding="utf-8",
    )
    return {
        "items": len(manifest),
        "by_family": {
            family: sum(item["family"] == family for item in manifest)
            for family in limits
        },
    }


def import_review(review_dir: Path, answers_path: Path, out: Path) -> dict:
    """Validate blinded answers and map them to evaluator item IDs."""
    # Variables:
    #   mapping: Private opaque-to-internal IDs kept away from the reviewer.
    #   answers: The reviewer's judgments keyed only by opaque ID.
    #   reference: Checked judgments restored to evaluator item IDs for comparison.
    #   mapping: A hashed relation checked against the blind packet before restoring IDs.
    mapping = json.loads((review_dir / "private_mapping.json").read_text("utf-8"))
    answers = json.loads(answers_path.read_text("utf-8"))
    if not isinstance(answers, dict) or set(answers) - set(mapping):
        raise ValueError("review answers contain an unknown review ID")
    reference = {}
    for opaque, judgments in answers.items():
        packet = json.loads(
            (review_dir / "blinded" / f"{opaque}.json").read_text("utf-8")
        )
        if review_id(mapping[opaque]) != opaque or packet.get("review_id") != opaque:
            raise ValueError(f"{opaque}: private review mapping does not match packet")
        if not isinstance(judgments, dict) or set(judgments) - set(packet["questions"]):
            raise ValueError(f"{opaque}: unknown question ID")
        for question_id, value in judgments.items():
            question = packet["questions"][question_id]
            kind = question["type"]
            if kind == "choice" and value not in question["criteria"]:
                raise ValueError(f"{opaque}/{question_id}: invalid choice")
            if kind == "score" and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 0 <= value < len(question["criteria"])
            ):
                raise ValueError(f"{opaque}/{question_id}: invalid score level")
            if kind == "noul":
                if not isinstance(value, bool):
                    raise ValueError(f"{opaque}/{question_id}: answer true or false")
        reference[mapping[opaque]] = judgments
    out.write_text(json.dumps(reference, indent=1) + "\n", encoding="utf-8")
    return {
        "items_reviewed": len(reference),
        "questions_reviewed": sum(map(len, reference.values())),
    }


def main(argv=None) -> int:
    """Export blinded packets or import the independent answers."""
    # Variables:
    #   limits: Sample size per question family for the blind export.
    #   result: Counts from the chosen action, printed for the operator.
    parser = argparse.ArgumentParser(prog="python -m evaltools.reference_review")
    actions = parser.add_subparsers(dest="action", required=True)
    export = actions.add_parser("export")
    export.add_argument("--requests", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    export.add_argument("--run", type=int, default=8)
    export.add_argument(
        "--run-strata",
        type=Path,
        help="Private JSON map of RUN item IDs to sound/misleading; require both in the blind sample",
    )
    export.add_argument("--function", type=int, default=8)
    export.add_argument("--test", type=int, default=8)
    export.add_argument("--tool", type=int, default=5)
    export.add_argument("--batch", type=int, default=2)
    imported = actions.add_parser("import")
    imported.add_argument("--review-dir", type=Path, required=True)
    imported.add_argument("--answers", type=Path, required=True)
    imported.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "export":
        limits = {
            "RUN": args.run,
            "FN": args.function,
            "TS": args.test,
            "TL": args.tool,
            "BT": args.batch,
        }
        if any(limit < 0 for limit in limits.values()):
            parser.error("sample limits must be non-negative")
        run_strata = (
            json.loads(args.run_strata.read_text(encoding="utf-8"))
            if args.run_strata is not None
            else None
        )
        result = export_requests(args.requests, args.out, limits, run_strata=run_strata)
    else:
        result = import_review(args.review_dir, args.answers, args.out)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
