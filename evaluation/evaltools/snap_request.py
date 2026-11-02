"""Turn evidence packets and SNAP_QUESTIONS.json into decision-model requests.

    uv run python -m evaltools.snap_request --out requests/<batch> runs --packets packets/<batch>
    uv run python -m evaltools.snap_request --provider both --out requests/<batch> runs --packets ...
    uv run python -m evaltools.snap_request --out requests/fn functions --ids capstone.agent.loop:gather
    uv run python -m evaltools.snap_request --out requests/ts tests --ids tests/test_x.py::test_y
    uv run python -m evaltools.snap_request --out requests/tl tools --names get_readings wait

The questions are provider-neutral: the same named questions, criteria,
scales and missing-evidence rules go to SubQ Snap (`--provider snap`, the
default), TypeSafe Jev (`--provider jev`) or both (`--provider both`). In a
matched comparison every provider receives the same state, fitted to the
smaller context budget by one deterministic rule (`decision_models.fit_state`),
so a disagreement is never explained by one model having seen more.

By default nothing is sent: each request body is written to a JSON file so a
person can read exactly what the judge would see. `--send` posts the files
with the key named by the provider (`SUBQ_API_KEY`, `TYPESAFE_API_KEY`) in
the environment and writes the answers beside them, normalized into the
common schema and tagged with the rubric version, the commit, the question
ids, the provider, the model requested and reported, latency, tokens and
cost, so a result can always be traced to the exact evidence it was given.

The judge is only ever given the `snap_view` half of a run packet. The
`evaluator_only` half (hidden truth comparisons) stays on disk.

Neither service is one of the agent's model providers in the sense of
AGENTS.md section 9 (TypeSafe is already in scope for the evaluator's typed
judgments). This module is evaluation tooling outside the `capstone`
package; it adds no setting, dependency or default to the agent.
"""

import argparse
import ast
import functools
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evaltools.decision_models import (
    MATCHED_STATE_TOKENS,
    NORMALIZE_VERSION,
    PROVIDERS,
    DecisionProvider,
    estimate_tokens,
    fit_state,
    normalize,
)
from evaltools.run_packet import HIDDEN_WORDS, SnapView, leak_in

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "capstone-code"))

# The project's own POST helper, the one its model clients use: it sends a
# User-Agent (Cloudflare-fronted services refuse urllib's default with HTTP
# 403), keeps one deadline for the whole request and raises keyless errors.
from capstone.providers.chat import (  # noqa: E402
    ModelError,
    Transport,
    post_json,
    urllib_transport,
)

EVALUATION = REPO / "evaluation"
QUESTIONS_PATH = EVALUATION / "SNAP_QUESTIONS.json"
INVENTORY = EVALUATION / "inventory"
MAX_QUESTIONS_PER_REQUEST = min(p.max_questions for p in PROVIDERS.values())

# The RUN questions that read the evidence, the hypotheses or the decisions'
# arguments, which only an audit log holds. A `record_only` packet records
# them as unknown without a request. The principles of SNAP_QUESTIONS.json
# list the same ids; a test keeps the two in step.
NEEDS_FULL_TRACE = frozenset(
    {"RUN-01", "RUN-02", "RUN-05", "RUN-06", "RUN-08", "RUN-09", "RUN-10", "RUN-12"}
)


class DecisionQuestion(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    id: str = Field(pattern=r"^[A-Z]{2,3}-\d{2}$")
    family: Literal["RUN", "FN", "TS", "TL", "BT"]
    name: str = Field(min_length=1)
    type: Literal["noul", "choice", "score"]
    instructions: str = Field(min_length=1)
    criteria: dict[str, str] | list[str]
    required_evidence: list[str]
    missing_evidence: str

    @model_validator(mode="after")
    def criteria_fit_type(self):
        if self.type == "noul":
            if not isinstance(self.criteria, dict) or set(self.criteria) != {
                "true",
                "false",
            }:
                raise ValueError(f"{self.id}: a noul needs true and false criteria")
        elif self.type == "choice":
            if (
                not isinstance(self.criteria, dict)
                or not 2 <= len(self.criteria) <= 255
            ):
                raise ValueError(f"{self.id}: a choice needs 2 to 255 options")
        elif not isinstance(self.criteria, list) or not 2 <= len(self.criteria) <= 10:
            raise ValueError(f"{self.id}: a score needs 2 to 10 ordered levels")
        return self

    def to_request(self) -> dict:
        """The question in the System One shape both services share."""
        body: dict[str, Any] = {"type": self.type, "instructions": self.instructions}
        if self.type == "score":
            # SECOND-HAND: confirm against each service's documentation whether
            # ordered levels go under "criteria" or "levels".
            body["criteria"] = list(self.criteria)
        else:
            body["criteria"] = dict(self.criteria)
        return body


# The name the tests and older notes use.
SnapQuestion = DecisionQuestion


def load_questions(path: Path = QUESTIONS_PATH) -> tuple[dict, list[DecisionQuestion]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    questions = [DecisionQuestion.model_validate(q) for q in raw["questions"]]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("question ids must be unique")
    # A request keys its questions by name, so a repeated name would silently
    # replace another question in the same request.
    names = [q.name for q in questions]
    if len(names) != len(set(names)):
        raise ValueError("question names must be unique")
    return raw, questions


def questions_for(family: str, questions: list[DecisionQuestion]) -> list:
    return [q for q in questions if q.family == family]


def digest(state: Any) -> str:
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def request_fingerprint(tags: dict, body: dict) -> str:
    """SHA-256 of everything that decides a request's answer.

    The provider and its endpoint, the whole body that is sent (model, fitted
    state, every question's type, instructions and criteria), each question's
    full definition, the evidence budget, the rubric version and the version
    of `normalize`. Two requests with one fingerprint would be answered the
    same way, so a saved answer is reused only for an equal fingerprint;
    changing any of these sends the request again.
    """
    # Variables:
    #   canonical: The inputs above, as sorted-key JSON so the same inputs
    #     always give the same bytes.
    provider = tags["provider"]
    canonical = json.dumps(
        {
            "provider": provider,
            "endpoint": PROVIDERS[provider].endpoint if provider in PROVIDERS else None,
            "body": body,
            "questions": tags.get("questions"),
            "state_budget_tokens": tags.get("state_budget_tokens"),
            "rubric_version": tags.get("rubric_version"),
            "normalize_version": NORMALIZE_VERSION,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_request(
    state: Any,
    questions: list[DecisionQuestion],
    *,
    model: str,
    item_id: str,
    meta: dict,
    provider: str = "snap",
    state_tokens: int | None = MATCHED_STATE_TOKENS,
) -> list[dict]:
    """Request bodies (at most 16 questions each) plus their tags, for one provider.

    `state_tokens` is the evidence budget the state is fitted to; None sends
    the state whole (a provider's own limit still applies). The same budget
    given to two providers yields the same fitted state and the same digest.
    Each request's tags carry its `request_fingerprint`.
    """
    # Variables:
    #   trimmed: What `fit_state` cut to fit the budget, recorded in the tags.
    #   chunk: The questions of one request, at most the providers' limit.
    #   item: One request's tags and body; its fingerprint is taken from both.
    trimmed: list[str] = []
    if state_tokens is not None and isinstance(state, dict):
        state, trimmed = fit_state(state, state_tokens)
    requests = []
    for start in range(0, len(questions), MAX_QUESTIONS_PER_REQUEST):
        chunk = questions[start : start + MAX_QUESTIONS_PER_REQUEST]
        item = {
            "tags": {
                **meta,
                "provider": provider,
                "model_requested": model,
                "item_id": item_id,
                "question_ids": [q.id for q in chunk],
                "questions": {q.name: q.model_dump() for q in chunk},
                "state_digest": digest(state),
                "state_tokens_estimate": estimate_tokens(state),
                "state_budget_tokens": state_tokens,
                "state_trimmed": trimmed,
                "built_at": datetime.now(timezone.utc).isoformat(),
            },
            "body": {
                "model": model,
                "state": state,
                "questions": {q.name: q.to_request() for q in chunk},
            },
        }
        item["tags"]["request_fingerprint"] = request_fingerprint(
            item["tags"], item["body"]
        )
        requests.append(item)
    return requests


# --- run packets ----------------------------------------------------------------------


def applicable_run_questions(
    packet: dict, questions: list[DecisionQuestion]
) -> tuple[list[DecisionQuestion], dict[str, str]]:
    """Which RUN questions a packet can answer, and why the others are skipped."""
    # Variables:
    #   full: True when the packet was built from an audit log, so the trace holds
    #     the evidence, hypotheses and decision arguments.
    #   conclusion: The conclusion view, or {} when the run reached none.
    #   outage: True when no model answered; such a run is asked nothing.
    #   skipped: Question id to the reason it is not asked of this packet.
    #   chosen: The questions this packet can answer, in file order.
    view = packet["snap_view"]
    trace = view["trace"]
    full = trace["completeness"] == "full"
    conclusion = trace.get("conclusion") or {}
    skipped: dict[str, str] = {}
    chosen = []
    outage = view["facts"].get("termination_reason") == "model_unavailable"
    for q in questions_for("RUN", questions):
        reason = None
        if outage:
            # As in every reasoning total: an outage run measures the model
            # services' uptime, not the agent's reasoning.
            reason = "not_applicable: no model answered (model_unavailable)"
        elif q.id in NEEDS_FULL_TRACE and not full:
            reason = "unknown: trace.completeness is record_only (run without --audit)"
        elif q.id == "RUN-03" and trace.get("critique") is None:
            reason = "not_run: no critic in this run"
        elif q.id == "RUN-11" and trace.get("recheck") is None:
            reason = "not_asked: the critic follow-up was off"
        elif q.id == "RUN-04" and not (
            view["configuration"].get("manual_offered")
            or view["configuration"].get("memory_offered")
        ):
            reason = "not_offered: neither the manual nor memory was offered"
        elif q.id == "RUN-09" and conclusion.get("recommendation") in (
            None,
            "escalate",
        ):
            reason = "not_applicable: the agent did not commit"
        elif q.id == "RUN-10" and conclusion.get("recommendation") != "no_action":
            reason = "not_applicable: the recommendation was not no_action"
        if reason is None:
            chosen.append(q)
        else:
            skipped[q.id] = reason
    return chosen, skipped


def run_requests(
    packet_dir: Path,
    questions: list[DecisionQuestion],
    providers: list[DecisionProvider],
    *,
    state_tokens: int | None,
) -> list:
    """One request item per packet and provider; an item with no body is skipped.

    A packet that can answer no question, or whose judge view does not fit
    the evidence budget even after `fit_state` has trimmed it, is written
    with `body: None` and the reason in its tags, so one such packet never
    stops the rest of the batch and the gap is recorded, not silent.
    """
    # Variables:
    #   view: The judge's half, passed through `SnapView` (which refuses any
    #     field it does not define), so only allowed fields can be sent.
    #   forbidden: The truth-side names and this run's own ids, which must
    #     appear in no state that is sent (see `judge_view`).
    #   chosen, skipped: The questions this packet can answer, and why the rest
    #     are not asked.
    #   meta: Tags shared by every request built from this packet.
    #   unfittable: Why the state could not be fitted to the budget, or None.
    #   refusal: Why the packet's judge view was refused, or None.
    built = []
    for path in sorted(packet_dir.glob("*.json")):
        if path.name == "BATCH_SUMMARY.json":
            continue
        packet = json.loads(path.read_text(encoding="utf-8"))
        forbidden = forbidden_for(packet["meta"])
        view, refusal = judge_view(packet, forbidden)
        chosen, skipped = (
            applicable_run_questions({"snap_view": view}, questions)
            if view is not None
            else ([], {})
        )
        meta = {
            "family": "RUN",
            "rubric_version": packet["meta"]["rubric_version"],
            "commit_sha": packet["meta"]["commit_sha"],
            "record_digest": packet["meta"]["record_digest"],
            "skipped_questions": skipped,
            "packet_file": path.name,
        }
        # The episode key names the request files and pairs answers (a run
        # key alone can repeat across archived pairs); it is in the packet's
        # meta, which is never sent. Packets older than schema 1.2.0 have none.
        item_id = packet["meta"].get("episode_key") or packet["meta"]["run_key"]
        for provider in providers:
            unfittable = refusal
            if chosen:
                try:
                    requests = build_request(
                        view,
                        chosen,
                        model=provider.model,
                        item_id=item_id,
                        meta=meta,
                        provider=provider.name,
                        state_tokens=state_tokens,
                    )
                    # Checked again after fitting: what is sent is what counts.
                    leaked = next(
                        (
                            word
                            for r in requests
                            if (word := leak_in(json.dumps(r["body"]), forbidden))
                        ),
                        None,
                    )
                    if leaked is None:
                        built.extend(requests)
                        continue
                    unfittable = f"refused: the request carries {leaked!r}"
                except ValueError as error:
                    unfittable = str(error)
            built.append(
                {
                    "tags": {
                        **meta,
                        "provider": provider.name,
                        "item_id": item_id,
                        "question_ids": [],
                        **({} if unfittable is None else {"unfittable": unfittable}),
                    },
                    "body": None,
                }
            )
    return built


def forbidden_for(meta: dict) -> list[str]:
    """What no state sent for this packet may contain, from its `meta`.

    The truth-side field names, and the run's scenario id, run key and episode
    key: scenario ids name the fault (`KA-01-bearing`).
    """
    names = [meta.get("scenario_id"), meta.get("run_key"), meta.get("episode_key")]
    return [*HIDDEN_WORDS, *(str(n).lower() for n in names if n)]


def judge_view(packet: dict, forbidden: list[str]) -> tuple[dict | None, str | None]:
    """The packet's judge view as it may be sent, or None and why it was refused.

    Only the fields `SnapView` defines pass (anything added to the file on
    disk is refused), and no forbidden text may appear in them.
    """
    # Variables:
    #   view: The judge's half after the allowlist, as plain JSON data.
    try:
        view = SnapView.model_validate(packet["snap_view"]).model_dump(mode="json")
    except (KeyError, ValueError) as problem:
        return None, f"refused: snap_view is not a valid judge view ({problem})"
    leaked = leak_in(json.dumps(view), forbidden)
    if leaked is not None:
        return None, f"refused: snap_view carries {leaked!r}"
    return view, None


# --- functions, tests and tools -----------------------------------------------------------


# How much of a list or a text a state keeps. Whatever is cut is said so in
# the state (`shown`), never dropped silently.
TESTS_PER_FUNCTION = 12
FUNCTIONS_PER_TEST = 15
TESTS_PER_TOOL = 20
TEST_SOURCE_CHARS = 4000
COVERING_TEST_SOURCE_CHARS = 3000
FACTORY = "capstone-code/capstone/providers/factory.py"


def source_lines(file: str, line: int, end_line: int) -> str:
    text = (REPO / file).read_text(encoding="utf-8").splitlines()
    return "\n".join(text[line - 1 : end_line])


@functools.cache
def definition_ends(file: str) -> dict[int, int]:
    """Each function's first line to its last, from the file's syntax tree."""
    tree = ast.parse((REPO / file).read_text(encoding="utf-8"))
    return {
        node.lineno: node.end_lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_source(record: dict, chars: int) -> tuple[str, str | None]:
    """A test's own source, from its first line to its last, and a note if cut.

    The end comes from the syntax tree, so the text never runs on into the
    next test; a source longer than `chars` is cut and the note says so.
    """
    # Variables:
    #   end: The test's last line; its first line alone if the tree has no
    #     function starting there (the note says so).
    end = definition_ends(record["file"]).get(record["line"])
    if end is None:
        return source_lines(record["file"], record["line"], record["line"]), (
            "only the first line: no function starts there in the source"
        )
    text = source_lines(record["file"], record["line"], end)
    if len(text) <= chars:
        return text, None
    return text[:chars], f"cut to {chars} of {len(text)} characters"


def shown(kept: int, total: int) -> str | None:
    """`"12 of 15 shown"` when a list was cut, else None."""
    return None if kept >= total else f"{kept} of {total} shown"


def function_state(record: dict, tests_by_id: dict) -> dict:
    # Variables:
    #   tests: Every covering test found in the inventory, before the cap.
    #   cut: Why a covering test's source was shortened, or None.
    tests = []
    for test_id in record["direct_tests"] + record["indirect_tests"]:
        t = tests_by_id.get(test_id)
        if t is None:
            continue
        source, cut = test_source(t, COVERING_TEST_SOURCE_CHARS)
        tests.append(
            {
                "id": t["id"],
                "claims": t["claims"],
                "assertions": t["assertions"],
                "assert_forms": t["assert_forms"],
                "raises_checks": t["raises_checks"],
                "execution_outcome": t["execution_outcome"],
                "source": source,
                **({"source_cut": cut} if cut else {}),
            }
        )
    return {
        "function_id": record["id"],
        "file": record["file"],
        "signature": record["signature"],
        "contract": {
            "docstring": record["docstring"],
            "has_variable_block": record["has_variable_block"],
            "purpose": record["purpose"],
        },
        "source": source_lines(record["file"], record["line"], record["end_line"]),
        "raises": record["raises"],
        "catches": record["catches"],
        "side_effect_hints": record["side_effect_hints"],
        "static_callers": record["static_callers"],
        "coverage": {
            "class": record["coverage_class"],
            "statement_coverage": record["statement_coverage"],
            "test_count": record["test_count"],
        },
        "tests": tests[:TESTS_PER_FUNCTION],
        "tests_shown": shown(TESTS_PER_FUNCTION, len(tests)),
    }


def test_state(record: dict, functions_by_id: dict) -> dict:
    # Variables:
    #   exercised: The functions the test runs that the inventory knows.
    #   cut: Why the test's source was shortened, or None.
    exercised = [f for f in record["exercises"] if f in functions_by_id]
    source, cut = test_source(record, TEST_SOURCE_CHARS)
    return {
        "test_id": record["id"],
        "claims": record["claims"],
        "docstring": record["docstring"],
        "source": source,
        "source_cut": cut,
        "assertions": record["assertions"],
        "assert_forms": record["assert_forms"],
        "raises_checks": record["raises_checks"],
        "helpers_used": record["uses"],
        "quality_flags": record["quality_flags"],
        "execution_outcome": record["execution_outcome"],
        "exercises": [
            {
                "id": f,
                "purpose": functions_by_id[f]["purpose"],
                "file": functions_by_id[f]["file"],
            }
            for f in exercised[:FUNCTIONS_PER_TEST]
        ],
        "exercises_shown": shown(FUNCTIONS_PER_TEST, len(exercised)),
    }


def wiring_lines(tool: str, files: list[str], after: int = 4) -> str | None:
    """The lines of `files` that name `tool`, each with the next few, by file.

    In `providers/factory.py` these are the tool's description, its argument
    contract and its entry in the provider's call table; a tool served by its
    own provider (the manual, memory recall) is named in that provider's file.
    So the judge reads how this tool, not every tool, is wired. Separate
    passages are joined by `...`. None when no file names the tool.
    """
    # Variables:
    #   text: One file's lines.
    #   keep: The line numbers to show, each naming line and the `after` after it.
    parts: list[str] = []
    for file in files:
        text = (REPO / file).read_text(encoding="utf-8").splitlines()
        keep: set[int] = set()
        for number, line in enumerate(text):
            if f'"{tool}"' in line:
                keep.update(range(number, min(number + after + 1, len(text))))
        if not keep:
            continue
        parts.append(f"# {file}")
        previous = None
        for number in sorted(keep):
            if previous is not None and number != previous + 1:
                parts.append("...")
            parts.append(f"{number + 1}: {text[number]}")
            previous = number
    return "\n".join(parts) if parts else None


def tool_state(tool: dict, functions_by_id: dict) -> dict:
    """What a judge reads about one agent tool: contract, code, wiring, tests."""
    # Variables:
    #   impl: The inventory entry of the function that implements the tool, or
    #     None; its file is also searched for the tool's wiring.
    impl = functions_by_id.get(tool["implementation"])
    return {
        "tool": tool["name"],
        "description_shown_to_model": tool["description"],
        "argument_schema": tool["argument_schema"],
        "output_contract": tool["output_contract"],
        "offered_to_policy": tool["offered_to_policy"],
        "changes_factory": tool["changes_factory"],
        "needs_human_approval": tool["needs_human_approval"],
        "boundary": tool["boundary"],
        "simulator_access": tool["simulator_access"],
        "implementation_source": (
            None
            if impl is None
            else source_lines(impl["file"], impl["line"], impl["end_line"])
        ),
        "provider_wiring_source": wiring_lines(
            tool["name"],
            [FACTORY] + ([impl["file"]] if impl and impl["file"] != FACTORY else []),
        ),
        "tests": tool["tests"][:TESTS_PER_TOOL],
        "tests_shown": shown(TESTS_PER_TOOL, len(tool["tests"])),
        "hazards_note": "Scheduled faults in capstone/providers/hazards.py can time "
        "out, drop the middle third of ticked rows, add a stale maintenance "
        "record or black out one machine's sensor tools; these are designed "
        "degradations, reported in the run record.",
    }


def item_requests(
    items: list[tuple[str, dict]],
    questions: list[DecisionQuestion],
    providers: list[DecisionProvider],
    *,
    meta: dict,
    state_tokens: int | None,
) -> list:
    """Request items for function, test or tool states, one set per provider.

    A state too large for the budget is written with `body: None` and the
    reason, as `run_requests` does for packets, so it never stops the batch.
    """
    # Variables:
    #   items: (item id, state) pairs, one per function, test or tool asked for.
    #   unfittable: Why `fit_state` could not fit this state to the budget.
    built = []
    for item_id, state in items:
        for provider in providers:
            try:
                built += build_request(
                    state,
                    questions,
                    model=provider.model,
                    item_id=item_id,
                    meta=meta,
                    provider=provider.name,
                    state_tokens=state_tokens,
                )
            except ValueError as unfittable:
                built.append(
                    {
                        "tags": {
                            **meta,
                            "provider": provider.name,
                            "item_id": item_id,
                            "question_ids": [],
                            "unfittable": str(unfittable),
                        },
                        "body": None,
                    }
                )
    return built


# --- sending ---------------------------------------------------------------------------


def send(
    provider: DecisionProvider,
    body: dict,
    api_key: str,
    timeout: float = 90.0,
    transport: Transport = urllib_transport,
):
    """POST one request; returns (reply, latency seconds).

    Sent with `capstone.providers.chat.post_json`: the project's User-Agent,
    one deadline for the whole request, and a `ModelError` that names no key
    or reply when the service does not answer. ValueError when the reply is
    not JSON.
    """
    # Variables:
    #   transport: What really sends the bytes; tests pass one that records them.
    #   started: When the request left, for the latency the answers record.
    started = time.monotonic()
    raw = post_json(transport, provider.endpoint, api_key, body, timeout)
    return json.loads(raw), time.monotonic() - started


def normalized_answers(item: dict, reply: dict, latency: float) -> list[dict]:
    """Every answer in the reply, in the common schema, in question order.

    An answer that is missing or not in the shape its question expects is
    kept as an entry with `value: None` and the reason, so one bad answer
    never loses the others of the same (paid) request.
    """
    # Variables:
    #   tags: The request's tags; `model_requested` there is the model actually
    #     asked for, a `--model` override included.
    #   tokens: The request's input tokens, the same on every answer of it.
    #   answers: The reply's answers by question name, {} when it has none.
    tags = item["tags"]
    reply = reply if isinstance(reply, dict) else {}
    usage = reply.get("usage") or {}
    tokens = usage.get("input_tokens")
    answers = reply.get("answers") or {}
    found = []
    for name, question in tags["questions"].items():
        raw = answers.get(name)
        error = "no answer in the reply" if raw is None else None
        if raw is not None:
            try:
                found.append(
                    normalize(
                        tags["provider"],
                        question,
                        raw,
                        model_reported=reply.get("model"),
                        latency_seconds=round(latency, 3),
                        input_tokens=tokens,
                        model_requested=tags.get("model_requested"),
                    )
                )
                continue
            except (KeyError, TypeError, ValueError) as problem:
                error = f"unreadable answer: {problem}"
        found.append(
            {
                "provider": tags["provider"],
                "question_id": question["id"],
                "question_name": name,
                "type": question["type"],
                "value": None,
                "error": error,
            }
        )
    return found


# Characters Windows refuses in a file name. A function id such as
# `capstone.agent.loop:gather` has one; left in, Windows writes an empty file
# and hides the content in an alternate data stream.
UNSAFE_NAME = re.compile(r'[<>:"/\\|?*]')


def file_stem(tags: dict) -> str:
    """A request's file name without extension, valid on every operating system.

    Named by provider, item and the first 12 hex digits of the request's
    fingerprint, never by its place in the batch, so reordering or adding
    items leaves every name (and every saved answer) where it was.
    """
    # Variables:
    #   safe: The item id with `/` and `::` written as `__` (the names run keys
    #     and test ids already had) and any other refused character as `_`.
    safe = tags["item_id"].replace("/", "__").replace("::", "__")
    safe = UNSAFE_NAME.sub("_", safe)
    return f"{tags['provider']}_{safe}_{tags['request_fingerprint'][:12]}"


def describe_failure(error: Exception) -> str:
    """A short reason a request failed, without the request (and so the key)."""
    if isinstance(error, ModelError):
        return str(error)  # post_json's reasons name no key and no reply
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code} {error.reason}"
    return f"{type(error).__name__}: {error}"


def already_answered(path: Path, tags: dict) -> bool:
    """True when `path` holds complete answers to exactly this request.

    The same request fingerprint (model, state, question wording, criteria,
    budget, rubric and normalization), no error, and a usable answer to every
    question asked: a failed or partial reply is asked again, never reused.
    """
    # Variables:
    #   saved: The answers file written earlier, if it can be read.
    #   answers: Its answers, one per question asked when complete.
    if not path.exists():
        return False
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    answers = saved.get("answers") or []
    return (
        "error" not in saved
        and saved.get("tags", {}).get("request_fingerprint")
        == tags.get("request_fingerprint")
        and len(answers) == len(tags.get("question_ids", []))
        and all(a.get("value") is not None for a in answers)
    )


def write_json(path: Path, payload: dict) -> None:
    """Write `payload` whole or not at all: to a temporary file, then renamed.

    A batch stopped mid-write leaves the old file (or none), never half of one
    that a rerun would read as an answer.
    """
    partial = path.with_name(path.name + ".partial")
    partial.write_text(
        json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8"
    )
    os.replace(partial, path)


def write_requests(
    built: list,
    out: Path,
    *,
    send_them: bool,
    transport: Transport = urllib_transport,
    retries: int = 2,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """Write every request file and, when sending, post each and write its answers.

    A request whose answers file already holds complete answers to the same
    request (`already_answered`) is not sent again, so a batch stopped by an
    outage can be rerun without paying twice. A request the service could not
    answer for a passing reason (HTTP 429 or 5xx, a timeout, no connection) is
    tried again up to `retries` more times, waiting 2, 4, ... seconds. One
    that still fails, or fails for good (another HTTP error, a reply that is
    not JSON), is written as an answers file with the error and no answers,
    and the batch goes on.
    """
    # Variables:
    #   send_them: True to post the requests; False writes the files only.
    #   transport, sleep: What sends the bytes and what waits between tries;
    #     tests pass ones that touch no network and no clock.
    #   counts: How many requests were sent, failed, or skipped because they
    #     were already answered, for the closing line of `main`.
    #   stem: The file name both of a request's files share.
    #   answers_path: Where that request's answers (or its failure) go.
    #   attempts: How many times this request was posted.
    #   failed: True once the request has failed for good; its error is written.
    out.mkdir(parents=True, exist_ok=True)
    if send_them:
        for name in {item["tags"]["provider"] for item in built}:
            if not os.environ.get(PROVIDERS[name].key_env):
                raise SystemExit(
                    f"--send needs {PROVIDERS[name].key_env} in the environment"
                )
    counts = {"sent": 0, "failed": 0, "already_answered": 0}
    for item in built:
        tags = item["tags"]
        if item["body"] is None:
            # Never sent, so it has no fingerprint; named by item alone.
            safe = UNSAFE_NAME.sub(
                "_", tags["item_id"].replace("/", "__").replace("::", "__")
            )
            write_json(out / f"{tags['provider']}_{safe}_unsent.request.json", item)
            continue
        stem = file_stem(tags)
        write_json(out / f"{stem}.request.json", item)
        if not send_them or item["body"] is None:
            continue
        answers_path = out / f"{stem}.answers.json"
        if already_answered(answers_path, tags):
            counts["already_answered"] += 1
            continue
        provider = PROVIDERS[tags["provider"]]
        attempts = 0
        failed = False
        while True:
            attempts += 1
            # ModelError: the service did not answer (post_json); OSError, a
            # transport that raises directly; ValueError, a reply not JSON.
            try:
                reply, latency = send(
                    provider,
                    item["body"],
                    os.environ[provider.key_env],
                    transport=transport,
                )
                break
            except (ModelError, OSError, ValueError) as error:
                passing = isinstance(error, ModelError) and error.transient
                if passing and attempts <= retries:
                    sleep(2.0**attempts)
                    continue
                write_json(
                    answers_path,
                    {
                        "tags": tags,
                        "answers": [],
                        "error": describe_failure(error),
                        "attempts": attempts,
                        "answered_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                counts["failed"] += 1
                failed = True
                break
        if failed:
            continue
        write_json(
            answers_path,
            {
                "tags": tags,
                "answers": normalized_answers(item, reply, latency),
                "raw_reply": reply,
                "attempts": attempts,
                "answered_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        counts["sent"] += 1
    return counts


def main(argv=None) -> int:
    """Build (and with `--send`, post) the requests for one family of items."""
    # Variables:
    #   providers: The decision models to prepare requests for, with a `--model`
    #     override applied when one provider is chosen.
    #   state_tokens: The evidence budget every state is fitted to; None with
    #     `--full-context`.
    #   known, wanted: The inventory entries of this family, and the ids asked
    #     for; an id not in the inventory is a usage error, not a crash.
    #   counts: Sent, failed and already-answered requests; any failure makes
    #     the exit status 1 so a script notices.
    parser = argparse.ArgumentParser(prog="python -m evaltools.snap_request")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument(
        "--provider",
        choices=(*PROVIDERS, "both"),
        default="snap",
        help="which decision model(s) to prepare requests for",
    )
    parser.add_argument(
        "--full-context",
        action="store_true",
        help="send the state whole (one provider only; breaks a matched comparison)",
    )
    parser.add_argument("--model", default=None, help="override the model id")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--send", action="store_true", help="post with the provider's key"
    )
    kinds = parser.add_subparsers(dest="kind", required=True)
    runs = kinds.add_parser("runs")
    runs.add_argument("--packets", type=Path, required=True)
    functions = kinds.add_parser("functions")
    functions.add_argument("--ids", nargs="+", required=True)
    tests = kinds.add_parser("tests")
    tests.add_argument("--ids", nargs="+", required=True)
    tools = kinds.add_parser("tools")
    tools.add_argument("--names", nargs="+", required=True)
    args = parser.parse_args(argv)

    providers = (
        list(PROVIDERS.values())
        if args.provider == "both"
        else [PROVIDERS[args.provider]]
    )
    if args.model is not None:
        if len(providers) != 1:
            parser.error("--model needs one provider")
        providers = [DecisionProvider(**{**providers[0].__dict__, "model": args.model})]
    if args.full_context and len(providers) != 1:
        parser.error("--full-context needs one provider; a comparison is matched")
    state_tokens = None if args.full_context else MATCHED_STATE_TOKENS

    raw, questions = load_questions(args.questions)
    meta = {"rubric_version": raw["rubric_version"]}
    if args.kind == "runs":
        built = run_requests(
            args.packets, questions, providers, state_tokens=state_tokens
        )
    else:
        functions_by_id = {
            f["id"]: f
            for f in json.loads(
                (args.inventory / "FUNCTION_INVENTORY.json").read_text("utf-8")
            )["functions"]
        }
        tests_by_id = {
            t["id"]: t
            for t in json.loads(
                (args.inventory / "TEST_INVENTORY.json").read_text("utf-8")
            )["tests"]
        }
        tools_by_name = {
            t["name"]: t
            for t in json.loads(
                (args.inventory / "TOOL_INVENTORY.json").read_text("utf-8")
            )["tools"]
        }
        family, known, wanted = {
            "functions": ("FN", functions_by_id, getattr(args, "ids", None)),
            "tests": ("TS", tests_by_id, getattr(args, "ids", None)),
            "tools": ("TL", tools_by_name, getattr(args, "names", None)),
        }[args.kind]
        unknown = [i for i in wanted if i not in known]
        if unknown:
            parser.error(f"not in the inventory: {', '.join(unknown)}")
        if family == "FN":
            items = [(i, function_state(known[i], tests_by_id)) for i in wanted]
        elif family == "TS":
            items = [(i, test_state(known[i], functions_by_id)) for i in wanted]
        else:
            items = [(n, tool_state(known[n], functions_by_id)) for n in wanted]
        built = item_requests(
            items,
            questions_for(family, questions),
            providers,
            meta={**meta, "family": family},
            state_tokens=state_tokens,
        )
    counts = write_requests(built, args.out, send_them=args.send)
    sent = (
        f" (sent {counts['sent']}, failed {counts['failed']}, "
        f"already answered {counts['already_answered']})"
        if args.send
        else ""
    )
    print(f"{len(built)} request file(s) in {args.out}{sent}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
