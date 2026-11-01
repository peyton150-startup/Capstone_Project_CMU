"""Compare two decision models' answers to the same questions on the same evidence.

    uv run python -m evaltools.compare_evaluators --answers requests/<batch> \\
        [--reference reference/<batch>.json] --out comparison/<batch>

Reads every `*.answers.json` that `snap_request --send` wrote, pairs the
answers by item and question across providers, and writes:

- `agreement.json`: per question and per family, how often the two models
  agreed (`decision_models.compare` rules), every disagreement with both
  values for human review, each provider's latency, tokens and cost, and,
  when a reference file exists, each provider's agreement with the
  reviewer's answers.
- `agreement.md`: the same as a table a person can read.

Agreement between two models is reported as agreement, never as
correctness; only the reference set says who was right. A pair is compared
only when both providers saw the same state (`state_digest` equal), so the
report cannot be biased by one model having been given more evidence.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from evaltools.decision_models import PROVIDERS, compare, reference_match


def load_answers(folder: Path) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(folder.glob("*.answers.json"))
    ]


def index_answers(files: list[dict]) -> dict:
    """(provider, item_id, question_id) -> (normalized answer, tags)."""
    found = {}
    for file in files:
        tags = file["tags"]
        for answer in file["answers"]:
            if answer.get("value") is None:
                continue
            found[(tags["provider"], tags["item_id"], answer["question_id"])] = (
                answer,
                tags,
            )
    return found


def request_usage(files: list[dict]) -> dict[str, dict]:
    """Per provider: requests, input tokens and cost, counted once per request.

    Every answer in a request carries that request's `input_tokens` and
    `cost_usd` (the service reports usage per request, not per question), so
    summing over answers would count one request once per question asked.
    Here each answers file is one request and is counted once.
    """
    # Variables:
    #   usage: For each provider, how many requests were sent and the token and
    #     cost totals over them; None when no request reported a figure.
    #   first: The first answer in a file that carries usage; all answers of one
    #     request carry the same figures.
    #   failed_requests: Files `snap_request` wrote for a request that failed
    #     (an `error` and no answers), counted apart from the answered ones.
    usage: dict[str, dict] = {}
    for file in files:
        provider = file["tags"]["provider"]
        entry = usage.setdefault(
            provider,
            {
                "requests": 0,
                "failed_requests": 0,
                "input_tokens": None,
                "cost_usd": None,
            },
        )
        if file.get("error"):
            entry["failed_requests"] += 1
            continue
        entry["requests"] += 1
        first = next(
            (a for a in file["answers"] if a.get("input_tokens") is not None), None
        )
        if first is None:
            continue
        entry["input_tokens"] = (entry["input_tokens"] or 0) + first["input_tokens"]
        if first.get("cost_usd") is not None:
            entry["cost_usd"] = (entry["cost_usd"] or 0.0) + first["cost_usd"]
    return usage


def build_report(files: list[dict], reference: dict | None) -> dict:
    """The agreement report over every answers file, with an optional reference set."""
    # Variables:
    #   answers: Every usable answer, by provider, item and question.
    #   providers: The provider names found; pairs are formed only with exactly two.
    #   pairs: One comparison per question both providers answered on the same state.
    #   unmatched: Answers with no partner, or whose partner saw a different state.
    #   usage: Request counts, tokens and cost per provider, counted once per request.
    #   reference: The reviewer's expected answers, {item: {question: expected}}, or
    #     None when none were given.
    answers = index_answers(files)
    usage = request_usage(files)
    providers = sorted({key[0] for key in answers})
    pairs = []
    unmatched = []
    if len(providers) == 2:
        a_name, b_name = providers
        for (provider, item, question), (answer, tags) in answers.items():
            if provider != a_name:
                continue
            other = answers.get((b_name, item, question))
            if other is None:
                unmatched.append(
                    {"item_id": item, "question_id": question, "missing": b_name}
                )
                continue
            if tags["state_digest"] != other[1]["state_digest"]:
                unmatched.append(
                    {
                        "item_id": item,
                        "question_id": question,
                        "reason": "the two providers saw different states",
                    }
                )
                continue
            pairs.append({"item_id": item, **compare(answer, other[0])})
    by_question = defaultdict(list)
    by_family = defaultdict(list)
    for pair in pairs:
        by_question[pair["question_id"]].append(pair["agree"])
        by_family[pair["question_id"].split("-")[0]].append(pair["agree"])

    def rate(values):
        return round(sum(values) / len(values), 3) if values else None

    per_provider = {}
    for name in providers:
        mine = [a for (p, _, _), (a, _) in answers.items() if p == name]
        # Latency is per request too, but every answer of a request shares it,
        # so the median over answers is the median over requests weighted by
        # how many questions each carried; close enough for a report line.
        latencies = [a["latency_seconds"] for a in mine if a.get("latency_seconds")]
        spent = usage.get(
            name,
            {
                "requests": 0,
                "failed_requests": 0,
                "input_tokens": None,
                "cost_usd": None,
            },
        )
        by_type: dict[str, list[float]] = defaultdict(list)
        for a in mine:
            if a.get("confidence") is not None:
                by_type[a["type"]].append(a["confidence"])
        entry = {
            "model_requested": PROVIDERS[name].model if name in PROVIDERS else None,
            "models_reported": sorted({str(a.get("model_reported")) for a in mine}),
            "answers": len(mine),
            "requests": spent["requests"],
            "failed_requests": spent["failed_requests"],
            "median_latency_seconds": round(median(latencies), 3)
            if latencies
            else None,
            "input_tokens_total": spent["input_tokens"],
            "cost_usd_total": (
                None if spent["cost_usd"] is None else round(spent["cost_usd"], 6)
            ),
            # A noul's confidence is a distance from one half, a choice's or a
            # score's is the service's own figure: kept apart, never averaged
            # across kinds (rubric section 9).
            "mean_confidence_by_type": {
                kind: round(mean(values), 3) for kind, values in sorted(by_type.items())
            },
        }
        if reference:
            hits, tried = 0, 0
            misses = []
            for (p, item, question), (answer, _) in answers.items():
                if p != name:
                    continue
                expected = reference.get(item, {}).get(question)
                if expected is None:
                    continue
                tried += 1
                if reference_match(answer, expected):
                    hits += 1
                else:
                    misses.append(
                        {
                            "item_id": item,
                            "question_id": question,
                            "answer": answer["value"],
                            "expected": expected,
                        }
                    )
            entry["reference_agreement"] = {
                "compared": tried,
                "matched": hits,
                "rate": round(hits / tried, 3) if tried else None,
                "misses": misses,
            }
        per_provider[name] = entry

    return {
        "providers": providers,
        "pairs_compared": len(pairs),
        "agreement_rate": rate([p["agree"] for p in pairs]),
        "agreement_by_family": {k: rate(v) for k, v in sorted(by_family.items())},
        "agreement_by_question": {k: rate(v) for k, v in sorted(by_question.items())},
        "disagreements_for_review": [p for p in pairs if p["needs_review"]],
        "unmatched": unmatched,
        "per_provider": per_provider,
        "caveats": [
            "Agreement between two models is not evidence of correctness; only "
            "the reference set is.",
            "Noul probabilities are preferences, not calibrated probabilities.",
            "Pairs are compared only when both providers saw the same state.",
        ],
    }


def markdown(report: dict) -> str:
    """The report as tables a person can read, one line per provider and per disagreement."""
    # Variables:
    #   report: The dictionary `build_report` made.
    #   confidence: One provider's mean confidence per question kind, as text.
    lines = ["# Evaluator agreement", ""]
    lines.append(
        f"Providers: {', '.join(report['providers']) or 'none'}; pairs compared: {report['pairs_compared']}; agreement rate: {report['agreement_rate']}"
    )
    lines += ["", "| Family | Agreement |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in report["agreement_by_family"].items()]
    lines += ["", "| Question | Agreement |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in report["agreement_by_question"].items()]
    lines += [
        "",
        "## Per provider",
        "",
        "| Provider | Model requested | Models reported | Requests | Answers | Median latency s | Input tokens | Cost USD | Mean confidence by type | Reference agreement |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, entry in report["per_provider"].items():
        ref = entry.get("reference_agreement", {})
        confidence = (
            ", ".join(f"{k} {v}" for k, v in entry["mean_confidence_by_type"].items())
            or "-"
        )
        lines.append(
            f"| {name} | {entry['model_requested']} | {', '.join(entry['models_reported'])} | {entry['requests']} | {entry['answers']} | {entry['median_latency_seconds']} | {entry['input_tokens_total']} | {entry['cost_usd_total']} | {confidence} | {ref.get('matched')}/{ref.get('compared')} |"
        )
    lines += ["", "## Disagreements for human review", ""]
    if not report["disagreements_for_review"]:
        lines.append("none")
    else:
        lines += [
            "| Item | Question | A | B | Delta | Basis |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {d['item_id']} | {d['question_id']} | {d['a']} | {d['b']} | {d['delta']} | {d['basis']} |"
            for d in report["disagreements_for_review"]
        ]
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in report["caveats"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evaltools.compare_evaluators")
    parser.add_argument(
        "--answers", type=Path, required=True, help="folder of *.answers.json"
    )
    parser.add_argument(
        "--reference", type=Path, help="reviewer answers: {item: {question: expected}}"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    reference = (
        json.loads(args.reference.read_text(encoding="utf-8"))
        if args.reference
        else None
    )
    report = build_report(load_answers(args.answers), reference)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "agreement.json").write_text(
        json.dumps(report, indent=1) + "\n", encoding="utf-8"
    )
    (args.out / "agreement.md").write_text(markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {k: report[k] for k in ("providers", "pairs_compared", "agreement_rate")}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
