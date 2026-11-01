"""Provider-neutral decision models: SubQ Snap and TypeSafe Jev side by side.

Both services answer named noul / choice / score questions about one state
through a System One style endpoint, so one request shape serves both. What
differs is the model id, the key, the context budget and the price. This
module holds those differences (`PROVIDERS`), the one evidence-fitting rule
both models receive (`fit_state`), the common answer schema (`normalize`)
and the agreement rules (`compare`), so that a comparison is never biased by
one model seeing more evidence or by two different readings of its answer.

Facts about the services are SECOND-HAND: docs.subq.ai and docs.typesafe.ai
were not reachable from the session that wrote this. Each provider record
says so, and `evaluation/DECISION_MODEL_COMPARISON.md` lists what to confirm
before the first live request.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any

# Tokens are not counted exactly here; four characters per token is the
# working estimate, kept conservative on purpose.
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class DecisionProvider:
    name: str
    vendor: str
    endpoint: str
    model: str
    key_env: str
    # The most named questions one request may carry.
    max_questions: int
    # Tokens one request may hold in all, and the share the state may take
    # (the rest is for the questions and the model's own overhead).
    request_tokens: int
    state_tokens: int
    usd_per_million_input: float
    docs: str
    facts_verified: bool
    notes: str

    @property
    def state_chars(self) -> int:
        return self.state_tokens * CHARS_PER_TOKEN


PROVIDERS: dict[str, DecisionProvider] = {
    "snap": DecisionProvider(
        name="snap",
        vendor="SubQ",
        endpoint="https://api.subq.ai/v1/systemone",
        model="subq-snap-1.1",
        key_env="SUBQ_API_KEY",
        max_questions=16,
        request_tokens=384_000,
        state_tokens=300_000,
        usd_per_million_input=0.040,
        docs="https://docs.subq.ai/endpoints/decisions-api/",
        facts_verified=False,
        notes="Public preview per the quickstart as quoted by search results and "
        "two open-source clients; 1-16 questions per request; the key under "
        "which score levels are sent (criteria or levels) is unconfirmed.",
    ),
    "jev": DecisionProvider(
        name="jev",
        vendor="TypeSafe",
        endpoint="https://api.typesafe.ai/v1/systemone",
        model="jev-1.14.0",
        key_env="TYPESAFE_API_KEY",
        max_questions=16,
        request_tokens=64_000,
        state_tokens=28_000,
        usd_per_million_input=0.042,
        docs="https://docs.typesafe.ai/api.md",
        facts_verified=False,
        notes="Jev 1.14.0 (2026-10-14) per secondary sources: default 64K tokens "
        "per request with 32K for the state plus the longest question; an "
        "opt-in header raises it, not used here. Whether jev-latest already "
        "points at 1.14 is disputed, so the exact id is pinned. The repository "
        "already calls this endpoint for noul and choice questions "
        "(capstone/providers/typesafe.py); the score shape is unconfirmed. "
        "Max questions per request is not documented in the sources read; 16 "
        "keeps parity with Snap and the auto-labeller already sends up to 12.",
    ),
}

# The evidence budget both models get in a matched comparison: Jev's state
# share, applied to Snap too, so neither model sees more than the other.
MATCHED_STATE_TOKENS = PROVIDERS["jev"].state_tokens


def estimate_tokens(state: Any) -> int:
    return len(json.dumps(state, separators=(",", ":"), default=str)) // CHARS_PER_TOKEN


def _truncate_evidence(state: dict, chars: int) -> int:
    """Cut every evidence item's content to `chars`; returns how many were cut."""
    cut = 0
    for item in state.get("trace", {}).get("evidence", []):
        content = item.get("content", "")
        if len(content) > chars:
            item["content"] = content[:chars] + " ...[cut for the context budget]"
            item["truncated"] = True
            cut += 1
    return cut


def fit_state(state: dict, max_tokens: int = MATCHED_STATE_TOKENS) -> tuple[dict, list]:
    """A copy of a `snap_view` that fits `max_tokens`, and what was removed.

    The same steps in the same order every time, so two providers given the
    same budget receive byte-identical states. Hypotheses, the conclusion,
    the critique, the verification and the facts are never trimmed: they are
    what the questions are about. Trimming order:

    1. evidence content to 600 characters each
    2. the decisions' `information_needed` text
    3. pruned tree-of-thought candidates
    4. evidence content to 200 characters each
    5. the decisions list (tools_used and facts remain)
    6. the manual and recall search records

    If the state still does not fit, a ValueError says so: splitting the
    trace across requests would make the two providers' views diverge, so
    it is refused rather than done silently.
    """
    fitted = json.loads(json.dumps(state, default=str))
    log: list[str] = []
    if estimate_tokens(fitted) <= max_tokens:
        return fitted, log
    trace = fitted.get("trace", {})
    steps = [
        (
            "evidence content cut to 600 characters",
            lambda: _truncate_evidence(fitted, 600),
        ),
        (
            "decision information_needed removed",
            lambda: [
                d.pop("information_needed", None) for d in trace.get("decisions", [])
            ],
        ),
        ("pruned candidates removed", lambda: trace.pop("pruned_candidates", None)),
        (
            "evidence content cut to 200 characters",
            lambda: _truncate_evidence(fitted, 200),
        ),
        (
            "decisions removed (tools_used and facts kept)",
            lambda: trace.pop("decisions", None),
        ),
        (
            "manual and recall search records removed",
            lambda: (
                trace.pop("manual_searches", None),
                trace.pop("recall_searches", None),
            ),
        ),
    ]
    for description, step in steps:
        step()
        log.append(description)
        if estimate_tokens(fitted) <= max_tokens:
            return fitted, log
    raise ValueError(
        f"the state does not fit {max_tokens} tokens even after: {'; '.join(log)}"
    )


# --- the common answer schema ---------------------------------------------------------


def normalize(
    provider: str,
    question: dict,
    raw: dict,
    *,
    model_reported: str | None,
    latency_seconds: float | None,
    input_tokens: int | None,
    model_requested: str | None = None,
) -> dict:
    """One answer in the provider-neutral shape.

    `value` is the probability of yes (noul), the chosen option (choice) or
    the probability-weighted level (score). `confidence` is the service's
    own figure where it gives one (choice, score); for a noul it is how far
    the probability sits from one half, scaled to 0-1, which is a
    convenience for sorting, not calibration.
    """
    # Variables:
    #   model_requested: The model id the request asked for (a `--model`
    #     override included); None falls back to the provider's default.
    #   provider_record: The provider's table entry, for its default model and
    #     its price.
    kind = question["type"]
    if raw.get("type") not in (None, kind):
        raise ValueError(
            f"{question['id']}: answer type {raw.get('type')!r} is not {kind}"
        )
    if kind == "noul":
        value = float(raw["noul"])
        confidence = abs(value - 0.5) * 2
        probabilities = {"true": value, "false": 1 - value}
    elif kind == "choice":
        value = str(raw["choice"])
        confidence = raw.get("confidence")
        probabilities = raw.get("probabilities")
    else:
        value = float(raw["score"])
        confidence = raw.get("confidence")
        probabilities = raw.get("probabilities")
    provider_record = PROVIDERS[provider]
    cost = (
        None
        if input_tokens is None
        else input_tokens * provider_record.usd_per_million_input / 1_000_000
    )
    return {
        "provider": provider,
        "model_requested": model_requested or provider_record.model,
        "model_reported": model_reported,
        "question_id": question["id"],
        "question_name": question["name"],
        "type": kind,
        "value": value,
        "confidence": None if confidence is None else float(confidence),
        "probabilities": probabilities,
        "latency_seconds": latency_seconds,
        "input_tokens": input_tokens,
        "cost_usd": cost,
    }


# --- agreement ------------------------------------------------------------------------

# Where two models count as agreeing. Stated here once so the report, the
# rubric and the comparison document say the same thing.
NOUL_CLOSE = 0.2  # probabilities this close agree even across the 0.5 line
SCORE_CLOSE = 0.5  # levels


def compare(a: dict, b: dict) -> dict:
    """Whether two normalized answers to the same question agree, and how far apart."""
    if (a["question_id"], a["type"]) != (b["question_id"], b["type"]):
        raise ValueError("compare needs two answers to the same question")
    kind = a["type"]
    if kind == "noul":
        delta = abs(a["value"] - b["value"])
        same_side = (a["value"] >= 0.5) == (b["value"] >= 0.5)
        agree = same_side or delta <= NOUL_CLOSE
        basis = "same side of 0.5" if same_side else f"within {NOUL_CLOSE}"
    elif kind == "choice":
        delta = 0.0 if a["value"] == b["value"] else 1.0
        agree = a["value"] == b["value"]
        basis = "same option"
    else:
        delta = abs(a["value"] - b["value"])
        agree = delta <= SCORE_CLOSE
        basis = f"within {SCORE_CLOSE} level"
    return {
        "question_id": a["question_id"],
        "type": kind,
        "a": a["value"],
        "b": b["value"],
        "delta": round(delta, 3),
        "agree": bool(agree),
        "basis": basis,
        "needs_review": not agree,
    }


def reference_match(answer: dict, expected: Any) -> bool:
    """Does a normalized answer match a reviewer's expected answer?"""
    # Variables:
    #   expected: The reviewer's answer: a boolean for a noul (the strings
    #     "true"/"false" are read as such, since bool("false") is True), an
    #     option for a choice, a level for a score.
    kind = answer["type"]
    if kind == "noul":
        if isinstance(expected, str):
            if expected.lower() not in ("true", "false"):
                raise ValueError(
                    f"a noul reference must be true or false: {expected!r}"
                )
            expected = expected.lower() == "true"
        return (answer["value"] >= 0.5) == bool(expected)
    if kind == "choice":
        return answer["value"] == expected
    return abs(answer["value"] - float(expected)) <= SCORE_CLOSE


def provider_table() -> list[dict]:
    """The provider facts as plain data, for documents and reports."""
    return [asdict(p) for p in PROVIDERS.values()]
