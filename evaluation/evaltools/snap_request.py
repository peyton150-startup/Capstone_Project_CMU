"""Turn evidence packets and SNAP_QUESTIONS.json into Decisions API requests.

    uv run python -m evaltools.snap_request runs --packets packets/<batch> --out requests/<batch>
    uv run python -m evaltools.snap_request functions --ids capstone.agent.loop:gather ...
    uv run python -m evaltools.snap_request tests --ids tests/test_agent_loop.py::test_...
    uv run python -m evaltools.snap_request tools --names get_readings wait

By default nothing is sent: each request body is written to a JSON file so a
person can read exactly what the judge would see. `--send` posts the files
with the key in the SUBQ_API_KEY environment variable and writes the answers
beside them, each tagged with the rubric version, the commit, the question
ids and a digest of the state, so a result can always be traced to the exact
evidence it was given.

The judge is only ever given the `snap_view` half of a run packet. The
`evaluator_only` half (hidden truth comparisons) stays on disk.

SubQ is not one of the agent's model providers (AGENTS.md section 9 lists
those). This module is evaluation tooling outside the `capstone` package; it
adds no setting, dependency or default to the agent.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO = Path(__file__).resolve().parents[2]
EVALUATION = REPO / "evaluation"
QUESTIONS_PATH = EVALUATION / "SNAP_QUESTIONS.json"
INVENTORY = EVALUATION / "inventory"
ENDPOINT = "https://api.subq.ai/v1/systemone"
MAX_QUESTIONS_PER_REQUEST = 16


class SnapQuestion(BaseModel):
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
        """The question in the API's shape. The score key is the one to confirm."""
        body: dict[str, Any] = {"type": self.type, "instructions": self.instructions}
        if self.type == "score":
            # SECOND-HAND: confirm against docs.subq.ai whether ordered levels go
            # under "criteria" (as TypeSafe's shape suggests) or "levels".
            body["criteria"] = list(self.criteria)
        else:
            body["criteria"] = dict(self.criteria)
        return body


def load_questions(path: Path = QUESTIONS_PATH) -> tuple[dict, list[SnapQuestion]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    questions = [SnapQuestion.model_validate(q) for q in raw["questions"]]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("question ids must be unique")
    return raw, questions


def questions_for(family: str, questions: list[SnapQuestion]) -> list[SnapQuestion]:
    return [q for q in questions if q.family == family]


def digest(state: Any) -> str:
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def build_request(
    state: Any, questions: list[SnapQuestion], *, model: str, item_id: str, meta: dict
) -> list[dict]:
    """One or more request bodies (at most 16 questions each) plus their tags."""
    requests = []
    for start in range(0, len(questions), MAX_QUESTIONS_PER_REQUEST):
        chunk = questions[start : start + MAX_QUESTIONS_PER_REQUEST]
        requests.append(
            {
                "tags": {
                    **meta,
                    "item_id": item_id,
                    "question_ids": [q.id for q in chunk],
                    "state_digest": digest(state),
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
    packet: dict, questions: list[SnapQuestion]
) -> tuple[list[SnapQuestion], dict[str, str]]:
    """Which RUN questions a packet can answer, and why the others are skipped."""
    view = packet["snap_view"]
    trace = view["trace"]
    full = trace["completeness"] == "full"
    conclusion = trace.get("conclusion") or {}
    skipped: dict[str, str] = {}
    chosen = []
    for q in questions_for("RUN", questions):
        reason = None
        if (
            q.id
            in (
                "RUN-01",
                "RUN-02",
                "RUN-05",
                "RUN-06",
                "RUN-08",
                "RUN-09",
                "RUN-10",
                "RUN-12",
            )
            and not full
        ):
            reason = "unknown: trace.completeness is record_only (run without --audit)"
        elif q.id in ("RUN-03",) and trace.get("critique") is None:
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


def run_requests(packet_dir: Path, questions: list[SnapQuestion], model: str) -> list:
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
        if chosen:
            built.extend(
                build_request(
                    packet["snap_view"],
                    chosen,
                    model=model,
                    item_id=packet["snap_view"]["run_key"],
                    meta=meta,
                )
            )
        else:
            built.append(
                {
                    "tags": {
                        **meta,
                        "item_id": packet["snap_view"]["run_key"],
                        "question_ids": [],
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


def send(body: dict, api_key: str, timeout: float = 60.0) -> dict:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def write_requests(built: list, out: Path, *, send_them: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get("SUBQ_API_KEY")
    if send_them and not api_key:
        raise SystemExit("--send needs SUBQ_API_KEY in the environment")
    for number, item in enumerate(built, start=1):
        tags = item["tags"]
        stem = f"{number:03d}_{tags['item_id'].replace('/', '__').replace('::', '__')}"
        (out / f"{stem}.request.json").write_text(
            json.dumps(item, indent=1, default=str) + "\n", encoding="utf-8"
        )
        if send_them and item["body"] is not None:
            answers = send(item["body"], api_key)
            (out / f"{stem}.answers.json").write_text(
                json.dumps(
                    {
                        "tags": tags,
                        "answers": answers,
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
    parser.add_argument("--model", default=None, help="override the model id")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--send", action="store_true", help="post with SUBQ_API_KEY")
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

    raw, questions = load_questions(args.questions)
    model = args.model or raw["api"]["model"]
    meta = {"rubric_version": raw["rubric_version"]}
    if args.kind == "runs":
        built = run_requests(args.packets, questions, model)
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
        built = []
        if args.kind == "functions":
            for item in args.ids:
                state = function_state(functions_by_id[item], tests_by_id)
                built += build_request(
                    state,
                    questions_for("FN", questions),
                    model=model,
                    item_id=item,
                    meta={**meta, "family": "FN"},
                )
        elif args.kind == "tests":
            for item in args.ids:
                state = test_state(tests_by_id[item], functions_by_id)
                built += build_request(
                    state,
                    questions_for("TS", questions),
                    model=model,
                    item_id=item,
                    meta={**meta, "family": "TS"},
                )
        else:
            tools_by_name = {
                t["name"]: t
                for t in json.loads(
                    (args.inventory / "TOOL_INVENTORY.json").read_text("utf-8")
                )["tools"]
            }
            for name in args.names:
                state = tool_state(tools_by_name[name], functions_by_id)
                built += build_request(
                    state,
                    questions_for("TL", questions),
                    model=model,
                    item_id=name,
                    meta={**meta, "family": "TL"},
                )
    write_requests(built, args.out, send_them=args.send)
    print(
        f"{len(built)} request file(s) in {args.out}" + (" (sent)" if args.send else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
