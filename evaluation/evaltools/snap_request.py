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
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evaltools.decision_models import (
    MATCHED_STATE_TOKENS,
    PROVIDERS,
    DecisionProvider,
    estimate_tokens,
    fit_state,
    normalize,
)

REPO = Path(__file__).resolve().parents[2]
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
    return raw, questions


def questions_for(family: str, questions: list[DecisionQuestion]) -> list:
    return [q for q in questions if q.family == family]


def digest(state: Any) -> str:
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


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
    """
    trimmed: list[str] = []
    if state_tokens is not None and isinstance(state, dict):
        state, trimmed = fit_state(state, state_tokens)
    requests = []
    for start in range(0, len(questions), MAX_QUESTIONS_PER_REQUEST):
        chunk = questions[start : start + MAX_QUESTIONS_PER_REQUEST]
        requests.append(
            {
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
        )
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
    #   skipped: Question id to the reason it is not asked of this packet.
    #   chosen: The questions this packet can answer, in file order.
    view = packet["snap_view"]
    trace = view["trace"]
    full = trace["completeness"] == "full"
    conclusion = trace.get("conclusion") or {}
    skipped: dict[str, str] = {}
    chosen = []
    for q in questions_for("RUN", questions):
        reason = None
        if q.id in NEEDS_FULL_TRACE and not full:
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
        elif q.id == "RUN-09" and conclusion.get("recommendation") == "escalate":
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
    #   chosen, skipped: The questions this packet can answer, and why the rest
    #     are not asked.
    #   meta: Tags shared by every request built from this packet.
    #   unfittable: Why the state could not be fitted to the budget, or None.
    built = []
    for path in sorted(packet_dir.glob("*.json")):
        if path.name == "BATCH_SUMMARY.json":
            continue
        packet = json.loads(path.read_text(encoding="utf-8"))
        chosen, skipped = applicable_run_questions(packet, questions)
        meta = {
            "family": "RUN",
            "rubric_version": packet["meta"]["rubric_version"],
            "commit_sha": packet["meta"]["commit_sha"],
            "record_digest": packet["meta"]["record_digest"],
            "skipped_questions": skipped,
            "packet_file": path.name,
        }
        item_id = packet["snap_view"]["run_key"]
        for provider in providers:
            unfittable = None
            if chosen:
                try:
                    built.extend(
                        build_request(
                            packet["snap_view"],
                            chosen,
                            model=provider.model,
                            item_id=item_id,
                            meta=meta,
                            provider=provider.name,
                            state_tokens=state_tokens,
                        )
                    )
                    continue
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


# --- functions, tests and tools -----------------------------------------------------------


def source_lines(file: str, line: int, end_line: int) -> str:
    text = (REPO / file).read_text(encoding="utf-8").splitlines()
    return "\n".join(text[line - 1 : end_line])


def function_state(record: dict, tests_by_id: dict) -> dict:
    tests = []
    for test_id in record["direct_tests"] + record["indirect_tests"]:
        t = tests_by_id.get(test_id)
        if t is None:
            continue
        tests.append(
            {
                "id": t["id"],
                "claims": t["claims"],
                "assertions": t["assertions"],
                "assert_forms": t["assert_forms"],
                "raises_checks": t["raises_checks"],
                "execution_outcome": t["execution_outcome"],
                "source": source_lines(t["file"], t["line"], t["line"] + 60)[:3000],
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
        "tests": tests[:12],
    }


def test_state(record: dict, functions_by_id: dict) -> dict:
    return {
        "test_id": record["id"],
        "claims": record["claims"],
        "docstring": record["docstring"],
        "source": source_lines(record["file"], record["line"], record["line"] + 80)[
            :4000
        ],
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
            for f in record["exercises"][:15]
            if f in functions_by_id
        ],
    }


def tool_state(tool: dict, functions_by_id: dict) -> dict:
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
        "provider_wiring_source": source_lines(
            "capstone-code/capstone/providers/factory.py", 1, 120
        ),
        "tests": tool["tests"][:20],
        "hazards_note": "Scheduled faults in capstone/providers/hazards.py can time "
        "out, drop the middle third of ticked rows, add a stale maintenance "
        "record or black out one machine's sensor tools; these are designed "
        "degradations, reported in the run record.",
    }


# --- sending ---------------------------------------------------------------------------


def send(provider: DecisionProvider, body: dict, api_key: str, timeout: float = 90.0):
    """POST one request; returns (reply, latency seconds)."""
    request = urllib.request.Request(
        provider.endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        reply = json.loads(response.read())
    return reply, time.monotonic() - started


def normalized_answers(item: dict, reply: dict, latency: float) -> list[dict]:
    """Every answer in the reply, in the common schema, in question order."""
    tags = item["tags"]
    usage = reply.get("usage", {}) if isinstance(reply, dict) else {}
    tokens = usage.get("input_tokens")
    answers = reply.get("answers", {})
    found = []
    for name, question in tags["questions"].items():
        raw = answers.get(name)
        if raw is None:
            found.append(
                {
                    "provider": tags["provider"],
                    "question_id": question["id"],
                    "question_name": name,
                    "type": question["type"],
                    "value": None,
                    "error": "no answer in the reply",
                }
            )
            continue
        found.append(
            normalize(
                tags["provider"],
                question,
                raw,
                model_reported=reply.get("model"),
                latency_seconds=round(latency, 3),
                input_tokens=tokens,
            )
        )
    return found


def write_requests(built: list, out: Path, *, send_them: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    if send_them:
        for name in {item["tags"]["provider"] for item in built}:
            if not os.environ.get(PROVIDERS[name].key_env):
                raise SystemExit(
                    f"--send needs {PROVIDERS[name].key_env} in the environment"
                )
    for number, item in enumerate(built, start=1):
        tags = item["tags"]
        safe = tags["item_id"].replace("/", "__").replace("::", "__")
        stem = f"{number:03d}_{tags['provider']}_{safe}"
        (out / f"{stem}.request.json").write_text(
            json.dumps(item, indent=1, default=str) + "\n", encoding="utf-8"
        )
        if send_them and item["body"] is not None:
            provider = PROVIDERS[tags["provider"]]
            reply, latency = send(provider, item["body"], os.environ[provider.key_env])
            (out / f"{stem}.answers.json").write_text(
                json.dumps(
                    {
                        "tags": tags,
                        "answers": normalized_answers(item, reply, latency),
                        "raw_reply": reply,
                        "answered_at": datetime.now(timezone.utc).isoformat(),
                    },
                    indent=1,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )


def main(argv=None) -> int:
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
        if args.kind == "functions":
            family, items = (
                "FN",
                [
                    (i, function_state(functions_by_id[i], tests_by_id))
                    for i in args.ids
                ],
            )
        elif args.kind == "tests":
            family, items = (
                "TS",
                [(i, test_state(tests_by_id[i], functions_by_id)) for i in args.ids],
            )
        else:
            tools_by_name = {
                t["name"]: t
                for t in json.loads(
                    (args.inventory / "TOOL_INVENTORY.json").read_text("utf-8")
                )["tools"]
            }
            family, items = (
                "TL",
                [
                    (n, tool_state(tools_by_name[n], functions_by_id))
                    for n in args.names
                ],
            )
        built = []
        for item_id, state in items:
            for provider in providers:
                built += build_request(
                    state,
                    questions_for(family, questions),
                    model=provider.model,
                    item_id=item_id,
                    meta={**meta, "family": family},
                    provider=provider.name,
                    state_tokens=state_tokens,
                )
    write_requests(built, args.out, send_them=args.send)
    print(
        f"{len(built)} request file(s) in {args.out}" + (" (sent)" if args.send else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
