"""One command that plans, optionally sends and reports a whole-project evaluation.

    cd evaluation
    uv run python -m evaltools.full_evaluation --commit <sha> \\
        --archive ../docs/benchmarks/2026-11-01-tot13-pairs --out full-eval/<name>
    # later, with approval and keys, the same command plus:
    #   --provider jev --send --max-requests 200 --max-usd 1.00

What it does, in order (CRITERIA_FOR_EVALUATOR.md EVAL-05, -06, -07):

1. **Provenance.** The pinned commit must be the checked-out one (a mismatch
   is refused); the inventories' file hashes, the question, rubric, packet
   and normalization versions are recorded.
2. **Scope manifest.** Every tracked Python file is classed as inventoried,
   a test file, holding no functions, expressly excluded (with the reason
   the inventory gives), or unexplained.
3. **Plan.** Requests for every function, test and tool in the inventories,
   every episode of every archive (`run_packet.build_archive`) and every
   comparison of two runs in one archived pair (BT questions). Each item and
   question gets one ledger row: planned, or why it is not asked (unknown,
   not applicable, not run, not offered, not asked, unfittable, refused).
4. **Budget.** The expected requests, input tokens and cost are printed.
   With `--send`, a plan over `--max-requests` or `--max-usd` is refused
   before anything is sent.
5. **Send** (only with `--send`), through `snap_request.write_requests`:
   resumable, reusing only complete answers to the same request fingerprint.
6. **Ledger and report.** `ledger.jsonl` (one row per item, question and
   provider, with its final status) and `report.json` / `report.md`, which
   keep correctness, evidence, reliability, scope and missingness apart and
   give every number with its denominator. There is no blended score.

Nothing here changes the simulator, the agent or any archived file; it
writes only under `--out`.
"""

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from evaltools import build_inventory, run_packet, snap_request
from evaltools.decision_models import (
    MATCHED_STATE_TOKENS,
    NORMALIZE_VERSION,
    PROVIDERS,
    DecisionProvider,
)

REPO = snap_request.REPO
INVENTORY = snap_request.INVENTORY
REPORT_VERSION = "1.0.0"

# Why a question is not asked, from the reason `applicable_run_questions`
# writes ("unknown: ...", "not_applicable: ..."): the word before the colon.
SKIP_STATUSES = ("unknown", "not_applicable", "not_run", "not_offered", "not_asked")

# Where tracked Python files that are not inventoried belong, matched by path
# prefix, with the reason; the reasons follow VERIFICATION_MATRIX.json
# `exclusions`. Anything else not inventoried is "unexplained".
EXCLUDED = (
    ("migrations/", "Alembic scaffolding outside the capstone package"),
    (".github/", "CI wiring, checked by CI itself"),
    ("test_db_connection.py", "a manual connection probe"),
)

# BT-02's sample rule, applied in code as the question says: an improvement
# claim needs at least this many cases judged in both runs (or repeats).
MATCHED_CASES_NEEDED = 13

# Settings never put in a judge's state: local paths and anything key-like.
PRIVATE_SETTING = ("PATH", "KEY", "TOKEN", "SECRET", "PASSWORD")


# --- provenance ---------------------------------------------------------------------


def git(*args: str) -> str | None:
    """The output of a git command in the repository, or None if git fails."""
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance(commit: str | None, inventory: Path, rubric_version: str) -> dict:
    """What this evaluation was made from, so a result can be traced and repeated.

    ValueError when `commit` is given and is not the checked-out commit: the
    inventories and code read here would not be the ones named.
    """
    # Variables:
    #   head: The checked-out commit, or None outside a git checkout.
    #   dirty: Tracked files changed but not committed, which the commit alone
    #     does not describe.
    head = git("rev-parse", "HEAD")
    if commit is None or head is None:
        raise ValueError("an explicit checked-out --commit is required")
    if not head.startswith(commit):
        raise ValueError(f"--commit {commit} is not the checked-out commit {head}")
    dirty = git("status", "--porcelain", "--untracked-files=no")
    if dirty is None or dirty:
        raise ValueError(
            "the evaluation target must have no uncommitted tracked changes"
        )
    matrix = json.loads((inventory / "VERIFICATION_MATRIX.json").read_text("utf-8"))
    source_hashes = matrix.get("source_sha256") or {}
    if not source_hashes or not matrix.get("coverage_available") or not matrix.get("junit_available"):
        raise ValueError("inventory lacks source hashes or full coverage/JUnit evidence")
    mismatched = [
        file
        for file, expected in source_hashes.items()
        if not (REPO / file).exists() or sha256_of(REPO / file) != expected
    ]
    if mismatched:
        raise ValueError(f"inventory source hash mismatch: {mismatched[:3]}")
    return {
        "report_version": REPORT_VERSION,
        "commit_pinned": commit,
        "commit_checked_out": head,
        "tracked_changes_uncommitted": None if dirty is None else bool(dirty),
        "inventory_source_hashes_verified": True,
        "coverage_sha256": matrix["coverage_sha256"],
        "junit_sha256": matrix["junit_sha256"],
        "inventory_sha256": {
            path.name: sha256_of(path) for path in sorted(inventory.glob("*.json"))
        },
        "rubric_version": rubric_version,
        "packet_schema_version": run_packet.PACKET_SCHEMA_VERSION,
        "normalize_version": NORMALIZE_VERSION,
    }


# --- scope manifest (EVAL-05) -------------------------------------------------------------


def tracked_python_files() -> list[str]:
    """Every Python file git tracks, as repository-relative POSIX paths."""
    listed = git("ls-files", "*.py")
    if listed is None:
        return sorted(
            p.relative_to(REPO).as_posix()
            for p in REPO.rglob("*.py")
            if ".venv" not in p.parts and ".pytest-tmp" not in p.parts
        )
    return sorted(line for line in listed.splitlines() if line)


def has_functions(path: Path) -> bool:
    """True when the file defines at least one function or method."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree)
    )


def scope_manifest(
    functions: dict, tests: dict, files: list[str] | None = None
) -> dict:
    """Each tracked Python file's place in the evaluation, and the gaps.

    Classes: `inventoried` (its functions are in FUNCTION_INVENTORY), `tests`
    (a test file in TEST_INVENTORY), `test_support` (other files under
    tests/), `no_functions` (nothing to evaluate), `excluded` (with the
    reason), `unexplained` (none of these: a gap to resolve). Inventory files
    that no longer exist are listed as `stale`.
    """
    # Variables:
    #   inventoried, test_files: The files the function and test inventories name.
    #   classes: Each file's class and, for an exclusion, why.
    files = tracked_python_files() if files is None else files
    inventoried = {f["file"] for f in functions.values()}
    test_files = {t["file"] for t in tests.values()}
    classes: dict[str, dict] = {}
    for file in files:
        if file in inventoried:
            entry = {"class": "inventoried"}
        elif file in test_files:
            entry = {"class": "tests"}
        elif file.startswith("tests/test_") and file.endswith(".py"):
            entry = {
                "class": "unexplained",
                "reason": "executable test absent from inventory",
            }
        elif file.startswith("tests/"):
            entry = {"class": "test_support"}
        elif reason := next((r for p, r in EXCLUDED if file.startswith(p)), None):
            entry = {"class": "excluded", "reason": reason}
        elif not has_functions(REPO / file):
            entry = {"class": "no_functions"}
        else:
            entry = {"class": "unexplained"}
        classes[file] = entry
    evaluator_gaps = []
    for file in files:
        path = REPO / file
        if not file.startswith("evaluation/evaltools/") or not path.exists():
            continue
        actual = {item.id for item in build_inventory.collect_functions(path)}
        indexed = {key for key, entry in functions.items() if entry["file"] == file}
        evaluator_gaps.extend(sorted(actual - indexed))
    stale = sorted((inventoried | test_files) - set(files))
    counts = Counter(entry["class"] for entry in classes.values())
    return {
        "counts": dict(sorted(counts.items())),
        "unexplained": sorted(
            [f for f, e in classes.items() if e["class"] == "unexplained"]
            + evaluator_gaps
        ),
        "stale": stale,
        "files": classes,
    }


# --- comparisons (BT) -----------------------------------------------------------------


def run_name(packet: run_packet.RunEvidencePacket) -> str:
    """The run a packet belongs to: the first part of its run key."""
    return packet.meta.run_key.split("/")[0]


def case_number(packet: run_packet.RunEvidencePacket) -> str:
    """The case's place in its run (`2` in `run/2/KA-02-bearing`), naming no fault."""
    parts = packet.meta.run_key.split("/")
    return parts[1] if len(parts) > 2 else packet.snap_view.run_ref


def run_settings(packet: run_packet.RunEvidencePacket) -> dict | None:
    """The run's saved settings (`<run>.config.json` beside its records), if any.

    Local paths and key-like settings are left out: they say nothing about the
    treatment and must not reach a judge.
    """
    # Variables:
    #   records: The records file the packet was built from.
    #   config: That run's saved configuration file, when it exists.
    records = Path(packet.meta.records_file)
    if not records.is_absolute():
        records = (Path.cwd() / records).resolve()
    config = records.with_name(
        records.name.removesuffix(".records.jsonl") + ".config.json"
    )
    if not config.exists():
        return None
    saved = json.loads(config.read_text(encoding="utf-8"))
    settings = {
        k: v
        for k, v in (saved.get("settings") or {}).items()
        if not any(word in k.upper() for word in PRIVATE_SETTING)
    }
    return {
        "commit": saved.get("commit"),
        "cases_sha256": saved.get("cases_sha256"),
        "variant": saved.get("variant"),
        "settings": settings,
    }


def case_outcome(packet: run_packet.RunEvidencePacket) -> dict:
    """One case's code-computed outcome, for a comparison state."""
    truth = packet.evaluator_only
    return {
        "label_status": truth.label_status,
        "right": truth.fully_right,
        "abstained": truth.abstained,
        "confident_wrong": truth.confident_wrong,
        "false_intervention": truth.false_intervention,
        "model_unavailable": truth.model_unavailable,
        "tool_calls": packet.snap_view.facts.tool_calls,
    }


def sample_rule(a: list, b: list) -> dict:
    """BT-02's sample rule in code: cases judged in both runs, and the counts on them.

    `a` and `b` are the two runs' packets. A case counts as matched when it
    has the same case number in both and is judged in both (a label not
    awaiting review). Below `MATCHED_CASES_NEEDED` matched cases, with one run
    per case, the rule's answer is `insufficient_sample` whatever the counts.
    """
    # Variables:
    #   by_case_a, by_case_b: Each run's packets by case number.
    #   matched: Case numbers judged in both runs.
    by_case_a = {case_number(p): p for p in a}
    by_case_b = {case_number(p): p for p in b}
    matched = sorted(
        c
        for c in set(by_case_a) & set(by_case_b)
        if by_case_a[c].evaluator_only.label_status == "judged"
        and by_case_b[c].evaluator_only.label_status == "judged"
    )

    def right(by_case):
        return sum(by_case[c].evaluator_only.fully_right is True for c in matched)

    return {
        "cases_a": len(a),
        "cases_b": len(b),
        "matched_judged": len(matched),
        "right_on_matched_a": right(by_case_a),
        "right_on_matched_b": right(by_case_b),
        "rule": (
            "insufficient_sample"
            if len(matched) < MATCHED_CASES_NEEDED
            else "sample_condition_met"
        ),
    }


def comparisons(packets: list) -> list[dict]:
    """Every comparison of two runs that share a namespace (one archived pair).

    Each is `{"item_id", "state", "sample_rule", "forbidden"}`. The state holds
    both runs' configurations and batch summaries and the per-case outcomes
    keyed by case number; no scenario id, run key or truth field.
    """
    # Variables:
    #   runs: Packets by (namespace, run name), only for namespaced packets.
    #   by_namespace: The run names of each namespace; every two of them make
    #     one comparison.
    #   state: What the judge is shown: both runs' settings and summaries and
    #     each case's outcome, keyed by case number only.
    #   forbidden: The scenario ids and keys of every packet in the comparison,
    #     plus the truth-side field names, checked against the state.
    runs: dict[tuple, list] = defaultdict(list)
    for packet in packets:
        if packet.meta.namespace is not None:
            runs[(packet.meta.namespace, run_name(packet))].append(packet)
    found = []
    by_namespace: dict[str, list[str]] = defaultdict(list)
    for namespace, name in sorted(runs):
        by_namespace[namespace].append(name)
    for namespace, names in sorted(by_namespace.items()):
        for i, first in enumerate(names):
            for second in names[i + 1 :]:
                a, b = runs[(namespace, first)], runs[(namespace, second)]
                cases = sorted(
                    {case_number(p) for p in a + b}, key=lambda c: (len(c), c)
                )
                by_a = {case_number(p): p for p in a}
                by_b = {case_number(p): p for p in b}
                state = {
                    "comparison": f"{first} vs {second}",
                    "batches": [
                        {
                            "label": label,
                            "run": name,
                            "configuration": json.loads(
                                group[0].snap_view.configuration.model_dump_json()
                            ),
                            "saved_settings": run_settings(group[0]),
                            "label_sources": sorted(
                                {
                                    p.evaluator_only.labelled_by
                                    for p in group
                                    if p.evaluator_only.labelled_by
                                }
                            ),
                            "summary": run_packet.batch_summary(group),
                        }
                        for label, name, group in (("A", first, a), ("B", second, b))
                    ],
                    "per_case": [
                        {
                            "case": c,
                            "A": case_outcome(by_a[c]) if c in by_a else None,
                            "B": case_outcome(by_b[c]) if c in by_b else None,
                        }
                        for c in cases
                    ],
                    "sample_rule_in_code": sample_rule(a, b),
                }
                forbidden = list(run_packet.HIDDEN_WORDS) + [
                    word.lower()
                    for p in a + b
                    for word in (p.meta.scenario_id, p.meta.run_key)
                ]
                found.append(
                    {
                        "item_id": f"BT::{namespace}::{first}__vs__{second}",
                        "state": state,
                        "sample_rule": state["sample_rule_in_code"],
                        "forbidden": forbidden,
                    }
                )
    return found


# --- plan and ledger (EVAL-06) -------------------------------------------------------------


def ledger_rows(built: list, family_questions: dict) -> list[dict]:
    """One row per item, provider and question for every built request item.

    A request with a body gives its questions the status `planned`. Questions
    a run packet cannot answer get the status in their skip reason. A request
    with no body (too large, or refused) gives every question it would have
    carried that status, with the reason.
    """
    # Variables:
    #   tags: One request item's tags.
    #   reason: Why an item has no body (`unfittable` text, or `refused: ...`).
    #   asked: The question ids a bodiless item would have been asked.
    #   skips_written: Items whose skipped questions are already in the
    #     ledger; a request split in two chunks carries them twice.
    rows = []
    skips_written: set[tuple] = set()
    for item in built:
        tags = item["tags"]
        base = {
            "family": tags["family"],
            "item_id": tags["item_id"],
            "provider": tags["provider"],
        }
        key = (tags["family"], tags["item_id"], tags["provider"])
        skipped_here = {} if key in skips_written else tags.get("skipped_questions")
        skips_written.add(key)
        for question_id, why in (skipped_here or {}).items():
            status = why.split(":", 1)[0]
            rows.append(
                {
                    **base,
                    "question_id": question_id,
                    "status": status if status in SKIP_STATUSES else "unknown",
                    "reason": why,
                }
            )
        if item["body"] is not None:
            rows += [
                {
                    **base,
                    "question_id": q,
                    "status": "planned",
                    "request_fingerprint": tags["request_fingerprint"],
                }
                for q in tags["question_ids"]
            ]
            continue
        reason = tags.get("unfittable")
        if reason is None:
            continue  # every question was skipped, and is listed above
        skipped = set(tags.get("skipped_questions") or {})
        asked = [q for q in family_questions[tags["family"]] if q not in skipped]
        status = "refused" if reason.startswith("refused") else "unfittable"
        rows += [
            {**base, "question_id": q, "status": status, "reason": reason}
            for q in asked
        ]
    return rows


def plan(
    *,
    inventory: Path,
    archives: list[Path],
    providers: list[DecisionProvider],
    out: Path,
    commit: str | None,
    state_tokens: int | None = MATCHED_STATE_TOKENS,
    families: tuple[str, ...] = ("FN", "TS", "TL", "RUN", "BT"),
) -> dict:
    """Every request of the evaluation, its ledger rows, and what it needs.

    `families` limits which question families are planned; `state_tokens` is
    the matched evidence budget each state is fitted to.

    Packets of the archives are written under `out/packets` (one folder per
    archive) so the RUN requests are built from files a person can read.
    """
    # Variables:
    #   raw, questions: The question file and its questions.
    #   meta: Tags every request carries.
    #   packets: Every archived episode's packet, for RUN and BT.
    #   refused: Packets the truth check left out while building.
    #   built: Every request item, with or without a body.
    #   family_questions: Each family's question ids, for the rows of items
    #     that are not sent.
    #   compared: Every comparison of two runs in one archived pair (BT).
    raw, questions = snap_request.load_questions()
    family_questions = {
        f: [q.id for q in snap_request.questions_for(f, questions)]
        for f in ("FN", "TS", "TL", "RUN", "BT")
    }
    meta = {"rubric_version": raw["rubric_version"], "commit_sha": commit}
    functions = {
        f["id"]: f
        for f in json.loads((inventory / "FUNCTION_INVENTORY.json").read_text("utf-8"))[
            "functions"
        ]
    }
    tests = {
        t["id"]: t
        for t in json.loads((inventory / "TEST_INVENTORY.json").read_text("utf-8"))[
            "tests"
        ]
    }
    tools = {
        t["name"]: t
        for t in json.loads((inventory / "TOOL_INVENTORY.json").read_text("utf-8"))[
            "tools"
        ]
    }
    built: list = []
    if "FN" in families:
        items = [
            (i, snap_request.function_state(f, tests))
            for i, f in functions.items()
            if f["snap_questions"]
        ]
        built += snap_request.item_requests(
            items,
            snap_request.questions_for("FN", questions),
            providers,
            meta={**meta, "family": "FN"},
            state_tokens=state_tokens,
        )
    if "TS" in families:
        items = [(i, snap_request.test_state(t, functions)) for i, t in tests.items()]
        built += snap_request.item_requests(
            items,
            snap_request.questions_for("TS", questions),
            providers,
            meta={**meta, "family": "TS"},
            state_tokens=state_tokens,
        )
    if "TL" in families:
        items = [(n, snap_request.tool_state(t, functions)) for n, t in tools.items()]
        built += snap_request.item_requests(
            items,
            snap_request.questions_for("TL", questions),
            providers,
            meta={**meta, "family": "TL"},
            state_tokens=state_tokens,
        )
    packets: list = []
    refused: list[dict] = []
    for archive in archives:
        found = run_packet.build_archive(archive, refused=refused)
        folder = out / "packets" / archive.name
        folder.mkdir(parents=True, exist_ok=True)
        for packet in found:
            (folder / run_packet.packet_file_name(packet.meta.episode_key)).write_text(
                packet.model_dump_json(indent=1) + "\n", encoding="utf-8"
            )
        packets += found
        if "RUN" in families:
            built += snap_request.run_requests(
                folder, questions, providers, state_tokens=state_tokens
            )
    run_packet.check_unique(packets)
    compared = comparisons(packets) if "BT" in families else []
    bt_questions = snap_request.questions_for("BT", questions)
    for comparison in compared:
        for provider in providers:
            try:
                requests = snap_request.build_request(
                    comparison["state"],
                    bt_questions,
                    model=provider.model,
                    item_id=comparison["item_id"],
                    meta={**meta, "family": "BT"},
                    provider=provider.name,
                    state_tokens=state_tokens,
                )
            except ValueError as error:
                requests = [_bodiless(comparison, provider, meta, str(error))]
            for request in requests:
                leaked = request["body"] and run_packet.leak_in(
                    json.dumps(request["body"]), comparison["forbidden"]
                )
                if leaked:
                    request = _bodiless(
                        comparison,
                        provider,
                        meta,
                        f"refused: the request carries {leaked!r}",
                    )
                built.append(request)
    rows = ledger_rows(built, family_questions)
    if "RUN" in families:
        rows.extend(
            {
                "family": "RUN",
                "item_id": entry["episode_key"],
                "provider": provider.name,
                "question_id": question_id,
                "status": "refused",
                "reason": entry["reason"],
            }
            for entry in refused
            for provider in providers
            for question_id in family_questions["RUN"]
        )
    if "FN" in families:
        # Functions the inventory asks nothing about (verification status NOT
        # APPLICABLE) still get rows, so no function drops out unrecorded.
        rows += [
            {
                "family": "FN",
                "item_id": i,
                "provider": provider.name,
                "question_id": q,
                "status": "not_applicable",
                "reason": f"not_applicable: inventory status {f['verification_status']}",
            }
            for i, f in functions.items()
            if not f["snap_questions"]
            for provider in providers
            for q in family_questions["FN"]
        ]
    keys = [(r["family"], r["item_id"], r["provider"], r["question_id"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate question ledger row")
    return {
        "built": built,
        "rows": rows,
        "packets": packets,
        "refused_packets": refused,
        "comparisons": compared,
        "functions": functions,
        "tests": tests,
        "tools": tools,
        "rubric_version": raw["rubric_version"],
    }


def _bodiless(comparison: dict, provider: DecisionProvider, meta: dict, reason: str):
    """A comparison request item that will not be sent, with the reason."""
    return {
        "tags": {
            **meta,
            "family": "BT",
            "provider": provider.name,
            "item_id": comparison["item_id"],
            "question_ids": [],
            "unfittable": reason,
        },
        "body": None,
    }


def budget(built: list) -> dict:
    """Requests, input tokens (estimated) and cost (estimated) per provider."""
    # Variables:
    #   per: Each provider's requests with a body (only those are sent), their
    #     estimated input tokens and, from the provider's price, the cost.
    per: dict[str, dict] = {}
    for item in built:
        if item["body"] is None:
            continue
        tags = item["tags"]
        entry = per.setdefault(
            tags["provider"], {"requests": 0, "input_tokens_estimate": 0}
        )
        entry["requests"] += 1
        entry["input_tokens_estimate"] += tags["state_tokens_estimate"]
    for name, entry in per.items():
        entry["cost_usd_estimate"] = round(
            entry["input_tokens_estimate"]
            * PROVIDERS[name].usd_per_million_input
            / 1_000_000,
            4,
        )
    return {
        "per_provider": per,
        "requests": sum(e["requests"] for e in per.values()),
        "cost_usd_estimate": round(
            sum(e["cost_usd_estimate"] for e in per.values()), 4
        ),
    }


def pending_batch(built: list, requests_dir: Path, size: int) -> list:
    """Select the next bounded set of unanswered requests in plan order."""
    # Variables:
    #   item: A planned request, skipped when it has no body or saved complete
    #     answers for the same fingerprint.
    #   size: The most new requests this invocation may send.
    if size < 1:
        raise ValueError("--batch-size must be positive")
    pending = []
    for item in built:
        if item["body"] is None:
            continue
        tags = item["tags"]
        answer = requests_dir / f"{snap_request.file_stem(tags)}.answers.json"
        if not snap_request.already_answered(answer, tags):
            pending.append(item)
        if len(pending) == size:
            break
    return pending


def settle(rows: list[dict], requests_dir: Path) -> list[dict]:
    """The ledger with each planned row's final status from the answers on disk.

    `answered` (a usable value), `unreadable` (the reply's answer was refused
    by `normalize`), `failed` (the request failed), or `planned` still (never
    sent, as in a dry run). Answers are matched by request fingerprint, so an
    answer to an older version of a request never settles a row.
    """
    # Variables:
    #   by_fingerprint: Each answers file's answers by question id, or its
    #     error, keyed by the request fingerprint it answered.
    by_fingerprint: dict[str, dict] = {}
    for path in requests_dir.glob("*.answers.json"):
        saved = json.loads(path.read_text(encoding="utf-8"))
        fingerprint = saved.get("tags", {}).get("request_fingerprint")
        if fingerprint is None:
            continue
        by_fingerprint[fingerprint] = {
            "error": saved.get("error"),
            "answers": {a["question_id"]: a for a in saved.get("answers", [])},
        }
    settled = []
    for row in rows:
        found = by_fingerprint.get(row.get("request_fingerprint"))
        if row["status"] != "planned" or found is None:
            settled.append(row)
            continue
        if found["error"]:
            settled.append({**row, "status": "failed", "reason": found["error"]})
            continue
        answer = found["answers"].get(row["question_id"])
        if answer is None or answer.get("value") is None:
            reason = "no answer" if answer is None else answer.get("error")
            settled.append({**row, "status": "unreadable", "reason": reason})
        else:
            settled.append({**row, "status": "answered", "value": answer["value"]})
    return settled


# --- report (EVAL-07) ---------------------------------------------------------------------


def ratio(numerator: int, denominator: int) -> dict:
    """A count with its denominator, and the rate only when the denominator is not 0."""
    return {
        "n": numerator,
        "of": denominator,
        "rate": round(numerator / denominator, 3) if denominator else None,
    }


def report(
    planned: dict, rows: list[dict], scope: dict, prov: dict, spend: dict
) -> dict:
    """The consolidated result: kinds of result kept apart, each with its denominator.

    - `correctness`: per archived run, the deterministic outcomes (the
      `capstone.evals` denominators and the reasoning totals) and the
      inventory's verification statuses.
    - `comparisons`: each pair's sample rule in code (BT-02).
    - `evidence`: how many episodes have a full trace.
    - `reliability`: outages and how runs ended.
    - `judging`: ledger statuses by family and question.
    - `missingness`: every row not answered, by status.
    """
    # Variables:
    #   runs: Packets by (namespace, run name).
    #   statuses: Ledger rows counted by status.
    runs: dict[tuple, list] = defaultdict(list)
    for packet in planned["packets"]:
        runs[(packet.meta.namespace, run_name(packet))].append(packet)
    correctness = []
    for (namespace, name), packets in sorted(
        runs.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
    ):
        summary = run_packet.batch_summary(packets)
        correctness.append(
            {
                "namespace": namespace,
                "run": name,
                "commit": packets[0].meta.commit_sha,
                "episodes": len(packets),
                # As `capstone.evals` publishes it: outage runs included.
                "correct_of_judged": ratio(
                    summary["evals_correct"], summary["evals_judged"]
                ),
                "pending_review": summary["evals_pending_review"],
                # Reasoning totals: outage runs left out.
                "reasoned_correct_of_judged": ratio(
                    summary["root_cause_correct"], summary["judged"]
                ),
                "abstained_of_judged": ratio(summary["abstained"], summary["judged"]),
                "confident_wrong_of_judged": ratio(
                    summary["confident_wrong"], summary["judged"]
                ),
                "false_interventions_of_reasoned": ratio(
                    summary["false_interventions"],
                    summary["runs"] - summary["model_unavailable"],
                ),
            }
        )
    statuses = Counter(row["status"] for row in rows)
    by_family: dict[str, Counter] = defaultdict(Counter)
    by_question: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        by_family[row["family"]][row["status"]] += 1
        by_question[row["question_id"]][row["status"]] += 1
    verification = Counter(
        f["verification_status"] for f in planned["functions"].values()
    )
    tests_by_outcome = Counter(
        t["execution_outcome"] for t in planned["tests"].values()
    )
    return {
        "provenance": prov,
        "scope": {k: v for k, v in scope.items() if k != "files"},
        "budget": spend,
        "correctness": {
            "runs": correctness,
            "functions_by_verification_status": dict(sorted(verification.items())),
            "functions": len(planned["functions"]),
            "tests_by_execution_outcome": dict(sorted(tests_by_outcome.items())),
            "tests": len(planned["tests"]),
            "tools": len(planned["tools"]),
        },
        "comparisons": [
            {"item_id": c["item_id"], "sample_rule_in_code": c["sample_rule"]}
            for c in planned["comparisons"]
        ],
        "evidence": {
            "episodes": len(planned["packets"]),
            "full_traces": sum(
                p.snap_view.trace.completeness == "full" for p in planned["packets"]
            ),
            "record_only_traces": sum(
                p.snap_view.trace.completeness == "record_only"
                for p in planned["packets"]
            ),
        },
        "reliability": {
            "episodes_model_unavailable": sum(
                p.evaluator_only.model_unavailable for p in planned["packets"]
            ),
            "termination_reasons": dict(
                sorted(
                    Counter(
                        p.snap_view.facts.termination_reason or "none"
                        for p in planned["packets"]
                    ).items()
                )
            ),
            "packets_refused_by_truth_check": planned["refused_packets"],
        },
        "judging": {
            "rows": len(rows),
            "by_status": dict(sorted(statuses.items())),
            "by_family": {
                f: dict(sorted(c.items())) for f, c in sorted(by_family.items())
            },
            "by_question": {
                q: dict(sorted(c.items())) for q, c in sorted(by_question.items())
            },
        },
        "missingness": {
            status: n for status, n in sorted(statuses.items()) if status != "answered"
        },
    }


def markdown(result: dict) -> str:
    """The report as a short Markdown page, every figure with its denominator."""

    # Variables:
    #   lines: The page, built line by line.
    def fraction(r: dict) -> str:
        return f"{r['n']}/{r['of']}"

    prov = result["provenance"]
    lines = [
        "# Full-project evaluation",
        "",
        f"Commit pinned `{prov['commit_pinned']}`, checked out "
        f"`{prov['commit_checked_out']}`; uncommitted tracked changes: "
        f"{prov['tracked_changes_uncommitted']}. Rubric {prov['rubric_version']}, "
        f"packet schema {prov['packet_schema_version']}, normalize "
        f"{prov['normalize_version']}. There is no single blended score.",
        "",
        "## Scope",
        "",
        f"Files by class: {result['scope']['counts']}. Unexplained: "
        f"{result['scope']['unexplained'] or 'none'}. Stale: "
        f"{result['scope']['stale'] or 'none'}.",
        "",
        "## Correctness (deterministic)",
        "",
        "| Namespace | Run | Correct / judged (evals) | Pending review | "
        "Reasoned correct / judged | Abstained | Confident wrong | False interventions |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for run in result["correctness"]["runs"]:
        lines.append(
            f"| {run['namespace']} | {run['run']} | {fraction(run['correct_of_judged'])} "
            f"| {run['pending_review']} | {fraction(run['reasoned_correct_of_judged'])} "
            f"| {fraction(run['abstained_of_judged'])} "
            f"| {fraction(run['confident_wrong_of_judged'])} "
            f"| {fraction(run['false_interventions_of_reasoned'])} |"
        )
    lines += [
        "",
        f"Functions by verification status ({result['correctness']['functions']}): "
        f"{result['correctness']['functions_by_verification_status']}.",
        "",
        "## Comparisons (BT-02 sample rule, in code)",
        "",
    ]
    for comparison in result["comparisons"]:
        rule = comparison["sample_rule_in_code"]
        lines.append(
            f"- `{comparison['item_id']}`: {rule['matched_judged']} cases judged in "
            f"both; right on those A {rule['right_on_matched_a']}, B "
            f"{rule['right_on_matched_b']}; rule: **{rule['rule']}**."
        )
    evidence = result["evidence"]
    lines += [
        "",
        "## Evidence",
        "",
        f"{evidence['full_traces']}/{evidence['episodes']} episodes have a full trace; "
        f"{evidence['record_only_traces']} are record-only (their trace questions "
        "are unknown, not failed).",
        "",
        "## Reliability",
        "",
        f"Episodes where no model answered: "
        f"{result['reliability']['episodes_model_unavailable']}/{evidence['episodes']}. "
        f"Ends: {result['reliability']['termination_reasons']}.",
        "",
        "## Judging and missingness",
        "",
        f"{result['judging']['rows']} ledger rows by status: "
        f"{result['judging']['by_status']}.",
        "",
        "| Family | Statuses |",
        "|---|---|",
    ]
    for family, counts in result["judging"]["by_family"].items():
        lines.append(f"| {family} | {counts} |")
    spend = result["budget"]
    lines += [
        "",
        f"Requests planned: {spend['requests']}; estimated input cost "
        f"${spend['cost_usd_estimate']}.",
        "",
    ]
    return "\n".join(lines)


# --- command ------------------------------------------------------------------------------


def main(argv=None) -> int:
    """Plan, optionally send, then write the ledger and the report."""
    # Variables:
    #   providers: The decision models to prepare requests for.
    #   planned: The plan: request items, ledger rows, packets, comparisons.
    #   spend: Expected requests and cost; checked against the limits before
    #     anything is sent.
    #   counts: Sent, failed and already-answered requests, when sending.
    parser = argparse.ArgumentParser(prog="python -m evaltools.full_evaluation")
    parser.add_argument(
        "--commit", help="the commit being evaluated (must be checked out)"
    )
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument(
        "--archive",
        type=Path,
        action="append",
        default=[],
        help="an archived results folder (repeatable; see run_packet.build_archive)",
    )
    parser.add_argument("--provider", choices=(*PROVIDERS, "both"), default="both")
    parser.add_argument(
        "--families",
        default="FN,TS,TL,RUN,BT",
        help="comma-separated question families to plan",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--send", action="store_true", help="post the requests")
    parser.add_argument("--max-requests", type=int, help="refuse to send more")
    parser.add_argument("--max-usd", type=float, help="refuse to send above this")
    parser.add_argument(
        "--batch-size",
        type=int,
        help="send at most this many pending requests; rerun to resume",
    )
    args = parser.parse_args(argv)
    families = tuple(f.strip() for f in args.families.split(",") if f.strip())
    unknown = set(families) - {"FN", "TS", "TL", "RUN", "BT"}
    if unknown:
        parser.error(f"unknown families: {sorted(unknown)}")
    if args.send and (args.max_requests is None or args.max_usd is None):
        parser.error("--send needs --max-requests and --max-usd")
    providers = (
        list(PROVIDERS.values())
        if args.provider == "both"
        else [PROVIDERS[args.provider]]
    )
    raw, _ = snap_request.load_questions()
    try:
        prov = provenance(args.commit, args.inventory, raw["rubric_version"])
    except ValueError as error:
        parser.error(str(error))
    args.out.mkdir(parents=True, exist_ok=True)
    planned = plan(
        inventory=args.inventory,
        archives=args.archive,
        providers=providers,
        out=args.out,
        commit=args.commit,
        families=families,
    )
    spend = budget(planned["built"])
    print(
        f"{spend['requests']} request(s) planned, about "
        f"${spend['cost_usd_estimate']} of input",
        file=sys.stderr,
    )
    requests_dir = args.out / "requests"
    sending = planned["built"]
    if args.send:
        if args.batch_size is not None:
            sending = pending_batch(planned["built"], requests_dir, args.batch_size)
        batch_spend = budget(sending)
        if (
            batch_spend["requests"] > args.max_requests
            or batch_spend["cost_usd_estimate"] > args.max_usd
        ):
            print(
                f"refused: the batch ({batch_spend['requests']} requests, "
                f"${batch_spend['cost_usd_estimate']}) is over --max-requests "
                f"{args.max_requests} or --max-usd {args.max_usd}; nothing was sent",
                file=sys.stderr,
            )
            return 2
    counts = snap_request.write_requests(sending, requests_dir, send_them=args.send)
    rows = settle(planned["rows"], requests_dir)
    scope = scope_manifest(planned["functions"], planned["tests"])
    result = report(planned, rows, scope, prov, spend)
    with (args.out / "ledger.jsonl").open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, default=str) + "\n")
    (args.out / "scope_manifest.json").write_text(
        json.dumps(scope, indent=1) + "\n", encoding="utf-8"
    )
    (args.out / "report.json").write_text(
        json.dumps(result, indent=1, default=str) + "\n", encoding="utf-8"
    )
    (args.out / "report.md").write_text(markdown(result), encoding="utf-8")
    print(json.dumps(result["missingness"]))
    return 1 if args.send and counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
