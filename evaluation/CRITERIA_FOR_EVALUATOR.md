# Criteria for evaluator — full-project readiness and required fixes

**Status:** specification / remediation checklist, 2026-11-02. **No fixes in this document are claimed to be implemented.** Since then, items with a **Status (2026-11-02)** line are implemented on a branch and tested offline only; nothing here is verified live. This file records the prerequisites for promoting PR #155's offline evaluation scaffolding into a reliable, repeatable evaluation of the entire in-scope capstone. It does not authorize a paid API call, a live master run, an agent/simulator change, or a merge.

**Related work:** PR #155 (inventories, packets, Snap/Jev request scaffolding, rubric and audit); merged PR #156 (two 13-case anchored/blind pairs, 52 archived episodes); evaluation/EVALUATION_AUDIT.md; evaluation/EVALUATION_RUBRIC.md; evaluation/EVALUATION_README.md; evaluation/DECISION_MODEL_COMPARISON.md; docs/benchmarks/2026-11-01-tot13-pairs/README.md; docs/MVP_SCOPE.md.

## 1. What "ready to evaluate the full project" means

The evaluator must be able to consume the current repository and archived/new runs, and produce a **complete, auditable result without silently dropping items, overwriting identities, reusing stale judgments, interpreting missing evidence as success/failure, or leaking hidden truth to the judge**.

The result must distinguish:

1. **Functional correctness:** deterministic outcomes and adequately supported contract assertions for implemented functions, tools, simulator, agent and end-to-end workflows.
2. **Verification confidence:** direct coverage, assertion quality, failure-path tests, integration/live evidence, independent review and any remaining gaps. A passing test or judge vote alone does not mean VERIFIED.
3. **Agent effectiveness:** root-cause/target accuracy, evidence support, competing hypotheses/ToT, critic usefulness, retrieval contribution, calibrated abstention, recommended/authorized action and post-action verification.
4. **Operational reliability:** provider/model outages, malformed replies, retrieval failures, incomplete traces, latency, timeouts, retries and resource/cost consumption.
5. **Scope:** implemented MVP behavior versus partial, unimplemented and future-work items. A future-work feature cannot fail an MVP gate merely because it is not implemented.

There must be **no single blended "project success" percentage**. Report both the functional result and the strength of its verification, with counts and denominators for each layer.

### Starting snapshot (not a claim of current-main coverage)

PR #155 reports 602 inventoried project functions, 1,378 test functions / 1,729 passing parametrized cases and 17 agent tools on its audited commit; only 63 functions and 28 tests have curated human review. Its committed nine-case master packets have record-only traces. These counts must be **regenerated against the exact evaluation target commit**, not reused as today's authoritative totals. The current inventory deliberately excludes evaluation/evaltools, migrations, CI wiring and some probes: all such exclusions need explicit scope decisions in a complete-project report.

Merged PR #156 archived four live runs with 52 **composite** episode identities (13 per arm), but four diagnosis labels await review. Existing reported accuracy by arm is **A anchored 3/12, A blind 3/12, B anchored 6/13, B blind 6/11**. The 48 judged versus four pending distinction must survive import. None of those runs provides the full audit trace required for evidence-quality judging; all 52 recommendations escalated, and no case demonstrated supported completion. The archive is valid historical evidence, not a substitute for new full-trace tests.

## 2. Required changes and acceptance criteria

The numbered requirements are the definitive implementation checklist. **P0** items can invalidate results; **P1** items are required before a credible full-project assessment; **P2** items improve audit depth or repeatability without blocking the initial small pilot.

### P0 — correctness and integrity blockers

#### EVAL-01 — Preserve composite run identity across archives (P0)

- **Status (2026-11-02):** implemented on branch `fix/evaluator-p0-criteria`, offline tests only; developer review owed, not verified live. Packets, run references, packet/request/answer file names and answer pairing use the episode key `namespace::run_key`; `run_packet --archive` imports all 52 PR #156 episodes in one operation (52 unique keys, references and file names); a repeated run key without a namespace, or twice in one file, is refused; `compare_evaluators` refuses two answers to one question of one item. Not done: the target commit/config is carried in the packet's `meta`, not in the key.

- **Current issue:** PR #156's pair A and pair B reuse raw run keys. PR #155's packet/answer paths and joins use a run key or derived run-ref in places, and its comparison indexes answers by provider, item ID and question ID. Combining pairs can collide or overwrite.
- **Change:** Define a canonical episode key containing at least (pair_id or experiment_namespace, run_key), plus the target commit/config where needed. Propagate it through record import, label/review joins, audit lookup, opaque judge-side run reference, packet names, request IDs, answers, summaries and cross-provider comparisons. Keep the human-readable original run_key as provenance. Never use fault-bearing scenario IDs as judge-side identifiers.
- **Pass:** Import all 52 PR #156 episodes in one operation; exactly 52 unique episodes and no overwritten packet, label, request or answer. A test deliberately inserts the same run key under two pair IDs and proves both survive. Missing namespace is rejected if collisions exist.
- **Likely files:** evaluation/evaltools/run_packet.py, snap_request.py, compare_evaluators.py, new archive importer/runner and tests/test_evaluation_tools.py.

#### EVAL-02 — Respect review-pending labels and denominators (P0)

- **Status (2026-11-02):** implemented on branch `fix/evaluator-p0-criteria`, offline tests only; developer review owed, not verified live. Proposal-format label files are read and `needs_review` honoured; `--review-report` reads an eval report's `label_needs_review` flags and refuses a report label that differs from the file's; a pending label is kept as `label_status: pending_review` and the run is unjudged. The archive reproduces 3/12, 3/12, 6/13, 6/11 with exactly four pending (`evals_judged`/`evals_correct`, outage runs included as `capstone.evals` counts them; the reasoning totals still leave outage runs out).

- **Current issue:** run_packet.evaluator_only_of treats the presence of a label as a judged run, while PR #156 preserves label_needs_review separately in its Jev reports. Presence of a provisional label is not final adjudication.
- **Change:** Import the per-episode review flag (or an independently reviewed adjudication record); set pending labels to **unjudged**, never automatically correct, wrong or abstained. Preserve the original proposal, reviewer status and provenance. Reject ambiguous merges between labels and report flags. Use the same eligible-denominator rule as capstone.evals and document treatment of model-unavailable episodes separately.
- **Pass:** On the unchanged 52-episode archive: A anchored 3/12, A blind 3/12, B anchored 6/13, B blind 6/11; exactly four pending labels; no silent promotion. A newly adjudicated label changes the denominator only by an explicit, versioned decision. Add pending-label, missing-label and duplicate-identity regression tests.
- **Likely files:** run_packet.py, archive importer, comparison/report generator, tests.

#### EVAL-03 — Make judge request caching/retries identity-safe (P0)

- **Status (2026-11-02):** implemented on branch `fix/evaluator-p0-criteria`, offline tests only; developer review owed, not verified live. Each request carries a `request_fingerprint` of provider, endpoint, the whole body, the full question definitions, the budget, the rubric and `NORMALIZE_VERSION`; files are named by provider, item and fingerprint, not position; a saved answer is reused only for an equal fingerprint with an answer to every question; files are written atomically; HTTP 429/5xx, timeouts and unreachable services are retried twice (2 s, 4 s). Not done: a question-schema version separate from the rubric version.

- **Current issue:** snap_request.already_answered checks the evidence state digest and question IDs, but not all semantic request inputs. Changed wording, rubric, provider/model or answer schema can leave an old "answered" file looking reusable. Sequential index-based filenames are also fragile if the item order changes.
- **Change:** Derive a stable fingerprint from the **canonical full outgoing request** (provider and endpoint, requested model/version, fitted state bytes/digest, complete question names/types/instructions/criteria/levels, rubric + question-schema version, context-fit settings and normalization version). Bind responses to that fingerprint and source commit. Match it on resume; use stable collision-resistant request filenames/IDs. Never reuse invalid, partial, mismatched or failed responses as completed judgments. Implement atomic writes and clear failure/retry policy, including 429/5xx/timeouts.
- **Pass:** Reordering items preserves correct matches; changing model, question text, scoring criteria, rubric, source state or fit budget forces a fresh request. A matching successful response is reused exactly once. Failed/partial responses are surfaced and retried safely, not counted as complete.
- **Likely files:** snap_request.py, decision_models.py, compare_evaluators.py, tests.

#### EVAL-04 — Enforce evaluator/truth isolation end to end (P0)

- **Status (2026-11-02):** implemented on branch `fix/evaluator-p0-criteria`, offline tests only; developer review owed, not verified live. The judge view is passed through `SnapView` (no undefined field) and checked before and after fitting for truth field names and the run's scenario id, run key and episode key; three adversarial fixtures are refused before any request; questions are chosen from the judge view alone. Not done: semantic leaks that use none of those strings cannot be proven absent.

- **Current issue:** the judge's snap_view is intentionally separate from evaluator_only, but a field-name blacklist cannot prove absence of all semantic or indirect leaks. The archive's scenario IDs themselves name fault types.
- **Change:** Use an explicit allowlisted judge-state projection at the last request boundary. Keep scenario IDs, original run keys, true faults/targets, score fields, expected actions, reference answers and correctness labels out of every model-visible field, including free-text metadata and question applicability. Generate opaque identifiers from collision-safe composite IDs. Validate both pre-fit and post-fit payloads; add adversarial leak fixtures.
- **Pass:** Hidden-truth sentinel values and scenario names cannot appear in any serialized provider request; violating packets are refused and counted. Judge questions are not selected using outcome truth or labels. Deterministic truth comparison runs only after judge output is captured.
- **Likely files:** run_packet.py, snap_request.py, tests/test_evaluation_tools.py.

#### EVAL-19 — Send judge requests the way the project's live client does, and refuse impossible answers (P0)

- **Status (2026-11-02):** implemented on branch `fix/evaluator-p0-criteria`, offline tests only; developer review owed, not verified live. `send` uses `post_json` with an injectable transport; `normalize` refuses an off-list choice, a noul outside 0–1, a score outside its levels and non-numeric values (`NORMALIZE_VERSION` 1.1.0).

Found by probing PR #155 on 2026-11-02 (`snap_request.send` and `decision_models.normalize` called directly with a captured transport and hand-made replies).

- **Current issue:** `snap_request.send` builds its own `urllib` request with only `Accept`, `Authorization` and `Content-Type`, so Python adds its default `Python-urllib` User-Agent. Cloudflare-fronted services refuse that with HTTP 403 (the reason `capstone.providers.chat` sends `USER_AGENT`). Its timeout is per socket operation, not for the whole request, and its errors are raw `urllib` exceptions. Separately, `normalize` accepted the choice `"zzz"` for a question whose options were `a`/`b`, and a noul of `1.7`; the live TypeSafe client (`capstone/providers/typesafe.py`) refuses both.
- **Change:** Send through `capstone.providers.chat.post_json` (User-Agent, one whole-request deadline, keyless `ModelError`s), with an injectable transport for tests. In `normalize`, refuse a choice that is not one of the question's options and a noul or score outside its range, so the answer is kept as unreadable with a reason rather than counted.
- **Pass:** A captured-transport test sees the project's User-Agent and no key in any error text. An off-list choice, a noul outside 0–1 and a non-numeric score each become `value: None` with an error, and the other answers of the same request survive.
- **Likely files:** snap_request.py, decision_models.py, tests/test_evaluation_tools.py.

### P1 — required for an entire-project evaluation

#### EVAL-05 — Rebuild the inventory and publish a coverage manifest (P1)

- **Status (2026-11-02):** in part, on branch `feature/full-project-evaluation` (stacked on `fix/evaluator-p0-criteria`), offline tests only; developer review owed, not verified live. `full_evaluation.scope_manifest` classes every tracked Python file as inventoried, tests, test support, no functions, or excluded with a reason, and lists unexplained and stale files; a test fails on any unexplained file (none today). Not done: the inventories are not rebuilt at a pinned commit by the command (they record no commit; their SHA-256 hashes are recorded instead), and tool-to-implementation mapping is unchanged.

- **Change:** Pin one repository commit, run its full offline pytest/coverage/JUnit capture and regenerate function/test/tool inventories. Discover every first-party Python module, including evaluation tooling, migrations and CI/helpers; classify it as in scope, separately verified, or expressly excluded with a reason. Do not present the current 602/1,378/17 as complete for a later commit. Maintain bidirectional function↔test and tool↔implementation mappings; distinguish execution, direct assertions and curated verification.
- **Pass:** The manifest reconciles discovered versus inventoried versus excluded items, with no unexplained omissions or stale curated IDs; every in-scope function/test/tool has a result or explicit NOT TESTED/INSUFFICIENT EVIDENCE/FAILED state.
- **Likely files:** build_inventory.py, a new run manifest, tests and EVALUATION_README.md.

#### EVAL-06 — Build one bounded, resumable full-project evaluation driver (P1)

- **Status (2026-11-02):** in part, on branch `feature/full-project-evaluation` (stacked on `fix/evaluator-p0-criteria`), offline tests only; developer review owed, not verified live. `python -m evaltools.full_evaluation` plans every FN/TS/TL question of the inventories, every RUN question of every archived episode and both BT questions for each archived pair; writes one ledger row per item, question and provider (planned, answered, unreadable, failed, unknown, not applicable, not run, unfittable, refused); is a dry run unless `--send`, which needs `--max-requests` and `--max-usd` and refuses an over-budget plan before sending; resumes through EVAL-03 fingerprints. Not done: a time budget, a reference set input, and a live pilot.

- **Current issue:** snap_request can prepare selected function/test/tool IDs and a packet directory, but has no single audited run covering all inventory entries, all eligible episodes and the two defined batch (BT) questions.
- **Change:** Add an orchestrator/CLI that takes a pinned commit, inventory, archive namespaces, packets, reference set, provider selection and a cost/request/time budget. Generate all relevant FN/TS/TL/RUN/BT questions, deduplicate work using EVAL-03, checkpoint progress and resume idempotently. Support dry-run / offline-only first; make live sends an explicit, separate opt-in. Record every item and question as completed, not applicable, unknown, unfittable, failed or awaiting review.
- **Pass:** An offline dry run visits every in-scope inventory item and all 52 archived episode identities, wires BT-01/BT-02, prints expected request/token/cost counts and a complete missingness report. Stop/resume does not lose or duplicate requests. Missing answers cannot disappear from denominators.
- **Likely files:** new evaluation/evaltools/full_evaluation.py (or equivalent), snap_request.py, build_inventory.py, tests.

#### EVAL-07 — Join deterministic outcomes and model judgments into one report (P1)

- **Status (2026-11-02):** in part, on branch `feature/full-project-evaluation` (stacked on `fix/evaluator-p0-criteria`), offline tests only; developer review owed, not verified live. `report.json`/`report.md` keep provenance, scope, deterministic correctness per run (the `capstone.evals` denominators with pending labels, and the reasoning totals), BT-02's sample rule computed in code, trace completeness, reliability and judging status apart, every figure with its denominator and no blended score. Not done: joining judge answers to reviewer references (still `compare_evaluators`), misleading-success and evidence-grounded flags (need full traces and live answers), and per-function findings beyond status counts.

- **Change:** Produce per-function/per-tool/per-test/per-episode findings and aggregate tables that join deterministic scoring, run outcomes, judge answers, reviewer references and execution provenance by canonical identity. Keep score dimensions separate. Preserve correct denominators, committed-only accuracy, abstention, confident wrong, false interventions, evidence share, intervention necessity, verification calibration, tool/iteration budgets and misses. Compute misleading-success and evidence-grounded flags using explicit rubric rules.
- **Pass:** The report reconciles with the source records/reports; every percentage shows numerator, denominator and eligibility; unanswered or review-pending items remain named unknowns. No manual spreadsheet joins required. Tests catch misleadingly good "recommendation correct" and "resolved" values when the diagnosis/repair is wrong.
- **Likely files:** compare_evaluators.py, run_packet.py, a new consolidated reporter and tests.

#### EVAL-08 — Require complete, provenance-rich traces for new reasoning judgments (P1)

- **Current issue:** stored 2026-10-27 and PR #156 episodes lack full audit evidence. Their record-only traces cannot support many RUN questions.
- **Change:** For new master runs, require the --audit trace and validate its episode linkage, completeness and provenance: actual observations with timestamps/ticks/arguments/results; hypotheses, rejected alternatives and discriminating checks; decisions and tool errors; critic/recheck details; retrieved versus cited manual/memory content; proposed/approved actions; post-action verification. Preserve source hashes/config/model/settings/manual revision. If evidence is missing, skip only evidence-dependent questions with an explicit reason.
- **Pass:** Full-trace fixtures answer the required RUN questions without fabricated confidence, tool arguments or missing evidence. All 52 historical episodes remain labeled record_only where applicable; no retroactive reconstruction of nonexistent traces. Incomplete traces fail a strict new-run gate.
- **Likely files:** traced_run.py, run_packet.py, new preflight validator and tests.

#### EVAL-09 — Verify Snap and Jev contracts with a small live pilot (P1)

- **Current issue:** both services' request/response contracts were marked second-hand in PR #155; no Snap/Jev request was sent by that PR.
- **Change:** Confirm reachable model IDs, endpoint/auth, noul/choice/score payload keys and levels, answer field shapes, max questions, context limits, usage/cost reporting, rate limits and error modes. Use provider-specific adapters if their contracts differ; normalize answers without silently treating null/unparseable answers as success.
- **Pass:** With developer approval and configured keys, a tiny known-answer probe for each question type succeeds for both available services, or unavailable services are explicitly marked unavailable and the main run is blocked/degraded as specified. Store sanitized request/response contract fixtures and run offline tests against them. No full-batch paid calls before this pilot.
- **Likely files:** decision_models.py, snap_request.py, compare_evaluators.py, tests.

#### EVAL-10 — Create independent reference judgments and a calibration gate (P1)

- **Change:** Before reading Snap/Jev answers, freeze an independently reviewed reference set across correct diagnosis, incorrect diagnosis, insufficient evidence, misleading correct answers, false alarms, critic misdirection, retrieval failure, unsupported conclusions and deliberately corrupted evidence. Include FN/TS/TL judgments, not only RUN. Version reviewer decisions and preserve disagreements. Do not use Jev-generated diagnosis labels as independent ground truth for validating Jev.
- **Pass:** Per-question-family reference accuracy/agreement and a confusion/error breakdown are published; the acceptance threshold from EVALUATION_RUBRIC.md is applied only when sample support is sufficient. Two models agreeing does not qualify as correctness. Failed calibration prevents automatic VERIFIED claims.
- **Likely files:** evaluation/reference/, EVALUATION_RUBRIC.md, compare_evaluators.py, curated notes and tests.

#### EVAL-11 — Classify operational failures separately from reasoning failures (P1)

- **Change:** Classify model_unavailable, provider HTTP 429/5xx, bad/missing JSON, retrieval unavailable/stale, missing sensor data, timeout, critic schema rejection, and genuine evidence/reasoning/action mistakes distinctly. A configured manual or critic does not prove it ran successfully. Report attempted, completed and failed calls per stage; never infer precise outage cause from a generic error.
- **Pass:** Synthetic tests for each failure class and the PR #156 archived failure records produce explicit classifications and eligibility rules. Provider outages cannot inflate abstentions or be silently called bad reasoning. Tests also distinguish "not offered", "offered but failed", "retrieved but not used" and "used as evidence".
- **Likely files:** run_packet.py, full_evaluation.py, consolidated reporter and tests.

#### EVAL-12 — Make experiment comparisons provenance-valid (P1)

- **Change:** Capture commit, scenario/seed set, model and fallback routing, sampling, prompts/critic mode, manual/index revision, embeddings, memory state, budgets, hazards, provider availability, and concurrency/maintenance incidents. Reject or flag incompatible pair comparisons. Compare paired cases on matched judged eligibility; do not equate unequal-denominator percentages with improvement. Preserve PR #156's recorded overlap and re-embedding events as limitations.
- **Pass:** PR #156 pair A and B reproduce their published eligible denominators; both arms tie on common-judged case counts (A 3/11, B 6/11). The report refuses a causal "blind improved" claim. Mixed configuration, mismatched seed and untracked changes are conspicuously flagged.
- **Likely files:** import/manifest, BT-01 and BT-02 runner, consolidated reporter and tests.

#### EVAL-13 — Test meaningful functionality, not just test execution (P1)

- **Change:** Review assertions, failure paths, invariants, state transitions, effects/side effects, mocks, mocked boundary leaks and false-positive test behavior. Use deterministic fault-injection/mutation checks on a risk-ranked representative set. Assess simulator hidden-truth separation, retrieval, episodic-memory write gates, provider routing/retries, critic follow-up, ToT branch choice, approval/authorization and post-action verification. Expose anything that passed a superficial test but contradicted its contract.
- **Pass:** In-scope components have explicit pass/partial/failed/not-tested assessments; nominated regression tests reliably fail when their target behaviors are deliberately broken. Curated VERIFIED claims cite exact source, test IDs and failure evidence, not a passing count.
- **Likely files:** build_inventory.py, curated inventories, verification matrix, tests.

#### EVAL-14 — Include controlled repair and verification scenarios (P1)

- **Current issue:** PR #156's 52 runs all escalated; none provides supported completion. Diagnosis accuracy alone is insufficient to claim the full agent workflow is verified.
- **Change:** Design seed-pinned synthetic scenarios covering a real fault, authorized bounded intervention, post-action observation and ground-truth resolution; negative cases where the fix fails, verification is inconclusive, or no action is appropriate; partial data and wrong-machine symptoms. Keep approval and hidden truth outside the investigator; no production-machine control.
- **Pass:** At least one fully traced positive repair and negative repair case are evaluated end-to-end, with action authorization and verification calibration; false alarms, silent faults, multiple causes and incorrect target hypotheses are represented. The evaluator must fail an unsupported "resolved" claim even if a scenario happens to self-clear.
- **Likely files:** synthetic evaluation fixtures, traced master-run plan, EVALUATION_RUBRIC.md and tests. Implementing new agent capability is out of scope here; record any needed product fixes separately.

#### EVAL-15 — Make aggregation, uncertainty and resource use auditable (P1)

- **Status (2026-11-02):** in part, on branch `fix/evaluator-p0-criteria`: median latency is now over requests, not answers; tokens and cost were already counted once per request. The rest is open.

- **Change:** Report per-item, per-fault, per-batch and MVP-readiness breakdowns with thresholds and counts for abstention, confident-wrong, misleading success, false intervention, timeouts and missing evidence. Keep numerical score, categorical choice and noul preferences separate. Count latency/tokens/cost **once per request** (including failures) and compare latency at request level, not answer-weighted median. Guard against silent truncation, dropped oversized packets, duplicate answers and unknown statuses.
- **Pass:** Fixture totals match hand-calculated expectations; a 12-question request does not count 12 times for tokens/latency/cost; missing/unfittable/skipped counts reconcile to the planned question manifest. "Improvement" is unavailable unless BT-02's replicate and no-regression criteria pass.
- **Likely files:** compare_evaluators.py, run_packet.py, consolidated reporter and tests.

### P2 — worthwhile follow-ups, not a substitute for P0/P1

- **EVAL-16 — Depth of manual review (P2):** expand the 63 function / 28 test curated sample by risk, especially unreviewed modules, evaluator code, error handling and simulator ground truth; publish the remaining unreviewed count.
- **EVAL-17 — Repeatability and statistical confidence (P2):** use frozen same-seed repeat sets and a declared comparison design; distinguish repeat-run stochastic variation from a true improvement. Report sample size and uncertainty rather than overclaiming from one run.
- **EVAL-18 — Observability and performance budgets (P2):** correlate trace spans, retrieval latency, model calls/fallbacks, token usage and resource spend by episode and question; set explicit retry budgets, parallelism limits and safe interruption controls.

#### EVAL-20 — Show the judge each test and tool as it really is (P1)

- **Status (2026-11-02):** implemented on branch `fix/evaluator-p0-criteria`, offline tests only; developer review owed, not verified live. Test sources run from the test's first to its last line (syntax tree); every shortened list or text says so (`tests_shown`, `exercises_shown`, `source_cut`); each tool shows only the lines that name it in `providers/factory.py` and in its own implementation file (the manual and memory tools are wired in `providers/manual.py` and `providers/recall.py`, which the old fixed excerpt never showed).

Found by the same 2026-11-02 probe, against the 1,378 inventoried tests.

- **Current issue:** `snap_request.test_state` shows a test as the 80 lines from its first line, and `function_state` shows each covering test as 60 lines. 1,377 of 1,378 tests are shorter than that, so the judge also reads the neighbouring tests (and one longer test is cut off). Every one of the 17 tool states carries the same `providers/factory.py` lines 1–120, of a 450-line file: repeated in each request and still incomplete. Lists are cut without a note: covering tests to 12, exercised functions to 15 (5 tests are cut today), tool tests to 20.
- **Change:** Use each test's own end line from the source's syntax tree (the inventory already records `end_line` for functions). Replace the fixed factory excerpt with the function that wires that tool, found by name. Wherever a list or a text is shortened, say so in the state (how many were kept of how many), as `fit_state` already does for trimmed evidence.
- **Pass:** No test state contains a second `def test_`; the longest test is shown whole or marked as cut. Two tool states no longer share an identical wiring excerpt. A state built from a 16-function test says `15 of 16 shown`.
- **Likely files:** snap_request.py, build_inventory.py (test end lines), tests.

#### EVAL-21 — Keep stated counts in step with the question file (P2)

- **Status (2026-11-02):** implemented on branch `fix/evaluator-p0-criteria`, offline tests only; developer review owed, not verified live. A test compares the EVF note's stated counts with `load_questions()`.

- **Current issue:** `docs/PROGRESS.md` (EVF session note) says `SNAP_QUESTIONS.json` holds 22 questions; it holds 23 (RUN 12, FN 3, TS 3, TL 3, BT 2). Corrected in the same change as this item.
- **Change:** Generate counts quoted in the evaluation documents from the files they describe, or test them, so they cannot drift again.
- **Pass:** A test fails when a document's stated question count differs from `load_questions()`.

### Confirmed PR #160 follow-up findings (2026-11-02; documentation only)

**Source and scope.** A second review checked the implementation on open PR #160 (`feature/full-project-evaluation`, stacked on open PR #159) against the archived data on `main`. The defects below are **confirmed by static code inspection**, not fixed by this update. The independent reviewer could not execute the acceptance suite because Python 3.14 was unavailable in that environment. The repository's previously reported offline tests/CI do not establish that these *new* acceptance cases pass. PR #159 and #160 must remain unmerged pending developer review.

**Readiness distinction.** Findings F01–F04 are P0 barriers to a **complete, accurately accounted, bounded and practically resumable** full run; raising limits may allow requests to start, but does not solve missing evidence or ledger omissions. F05–F09 are P1 requirements for a reproducible and credible interpretation. The ability to finish HTTP requests is **not** proof that the evaluation is correct. Nothing below authorizes live sending, paid API use, new master runs, or merging.

#### F01 — Import and validate real audit logs (P0; EVAL-08 / EVAL-06)

- **Observed:** `evaluation/evaltools/run_packet.py::build_archive()` discovers `<run>.records.jsonl`, label, critic-label and report siblings, but fails to pass the existing `<run>.audit.jsonl` sibling to `build_all()`. The five complete audit records saved by merged PR #162 would therefore appear to be `record_only`.
- **Fix:** Resolve `audit_path=_sibling(records_path, stem, ".audit.jsonl")`; verify exact bijection between audit `run_id` and record episode identity, with no missing, duplicate, orphan, mislabeled or truncated audit entries. Fail the strict audited-import gate if an expected audit is absent or invalid. Never manufacture a trace for older records.
- **Pass (T21):** Import PR #156's 52 record-only episodes **and** PR #162's five audited episodes using both `--archive` arguments; exactly **57 unique composite identities**, with **52 record-only and five full traces**; five audited RUN packets contain actual saved audit evidence. Reject an orphan, duplicate and missing expected audit in negative tests. **Not yet executed.**

#### F02 — Close the test inventory and evaluator-code omission (P0; EVAL-05)

- **Observed:** Of **88 tracked `tests/test_*.py` files**, the referenced inventory includes **87**: `tests/test_full_evaluation.py` is missing. `scope_manifest()` classifies any otherwise unknown file in `tests/` as `test_support`, so the omission does not fail the existing unexplained-file gate. `evaluation/evaltools/` is excluded wholesale despite containing the evaluator implementation under assessment.
- **Fix:** Regenerate the inventory and coverage/JUnit data against the exact chosen commit. Enumerate all tracked test definitions and distinguish legitimate support modules from executable test files. Do not let a `test_*.py` file silently fall into support. Include evaluator modules in a self-test / separately verified inventory (or a per-file explicit exclusion with its own test evidence); reconcile functions, tools, tests and coverage bidirectionally.
- **Pass (T22):** All **88 currently tracked test files** are accounted for, including `tests/test_full_evaluation.py`; zero unexplained executable tests; insertion of an unindexed `tests/test_*.py` or an unreviewed evaluator function trips preflight. Counts must be recomputed, not hardcoded to 88.

#### F03 — Give every refused episode explicit question-ledger rows (P0; EVAL-06 / EVAL-07)

- **Observed:** `full_evaluation.plan()` collects refused packets and the summary reports them, but `ledger_rows()` walks only built request items. A packet refused during `build_archive()` has **no RUN question rows**, breaking per-episode and per-provider reconciliation.
- **Fix:** Preserve every rejected episode identity and reason before requesting; emit one explicit `refused` (or documented applicable skip) row for **each expected RUN question and selected provider**. Do not classify refused as answered, and do not omit it from total eligibility or completeness accounting. Detect duplicate and missing ledger keys.
- **Pass (T23):** Inject one truth-leaking or invalid packet into an otherwise valid 57-episode import. Its identity remains visible, its RUN ledger rows are all present and refused, no requests for it are sent, and planned + skipped + refused + settled totals reconcile by provider, family, item and question.

#### F04 — Make requests and money limits usable during an actual large run (P0; EVAL-06 / EVAL-15)

- **Status (2026-11-04):** bounded Snap sending implemented and tested offline
  on the evaluator fix branch. The full plan remains visible; each invocation
  has request, cumulative dollar and wall-clock limits. A full-window charge
  is reserved before posting; measured usage settles it; missing usage or an
  interrupted post stops further sends without retrying. Jev/mixed live
  sending remains blocked until Gate C confirms its request window and usage
  contract. No paid request was made for this change. The complete T24
  large-plan fake-provider acceptance run and live calibration remain open.

- **Observed:** `full_evaluation.budget()` estimates **input tokens only**, not outputs or retries. `--max-requests` / `--max-usd` compare against the **entire plan** and abort before any send if the plan exceeds a limit. The current archive-only dry run reported around **2,016 requests per provider**; a small authorized budget cannot process the first slice.
- **Fix:** Keep the full plan/ledger, but add bounded `--max-new-requests` / batch-size, a real wall-clock deadline, checkpointed state, and idempotent resume. Estimate both input and output tokens plus retry exposure; enforce an explicit hard spending policy from **measured** usage when returned, and a conservative fallback/stop when actual spend is unknown. Count remaining rather than already completed requests. Require explicit opt-in for live work and do not equate input-only estimates with dollar caps.
- **Pass (T24):** A full dry run can be resumed through many **small** fake-provider slices with no duplicate payment/response; cap exhaustion stops safely with pending rows preserved. Retries, failures, response costs and unavailable usage never silently exceed or masquerade as a validated spending cap.

#### F05 — Require stable target and per-run source provenance (P1; EVAL-05 / EVAL-03)

- **Observed:** `--commit` is optional, and `provenance()` records a dirty checkout rather than rejecting it. Inventory SHA-256s do not establish that coverage/inventories were built at the declared commit.
- **Fix/pass (T25):** Require an explicit commit and clean tracked workspace for a publishable assessment; prove inventory regeneration at that commit, with question/rubric and archive hashes. Keep the **current code commit** distinct from each **historical experiment source commit** (including PR #156 and #162 runs). Reject missing/mismatched provenance or prominently demote it to exploratory-only, never silently claim reproducibility.

#### F06 — Pair experiments by scenario and seed, not by position (P1; EVAL-12)

- **Observed:** `full_evaluation.case_number()` derives the match from the numeric slot in the run key (`run/2/...`); two episodes at position 2 could be unrelated scenarios/seeds. The current 13-matched sample rule does not independently establish compatible experiment configuration.
- **Fix/pass (T26):** Join on stable case/scenario identity **and seed**, validated from source-private metadata; use opaque judge-visible labels. Detect a reordered, replaced or differently seeded case even when sequence numbers match. Check frozen model/prompt/manual/memory/settings and PR #156's operational interruptions, and prevent unsupported causal improvement claims.

#### F07 — Finish per-item finding and independent-reference joins (P1; EVAL-07 / EVAL-10)

- **Observed:** `report()` primarily reports function verification-status totals, test execution outcomes and judge ledger states. It does not yet give a per-function/per-tool/per-test judgment joined to independent, versioned human references, nor independently calibrated evidence-grounding findings.
- **Fix/pass (T27):** Publish each item's deterministically checked claims, executed tests, assertion strength, judge answer, reviewer reference, disagreements and insufficiency reason. Preserve separate **functional correctness** and **verification confidence** measures; keep agent effectiveness and reliability distinct. Unknown/pending never automatically becomes VERIFIED.

#### F08 — Validate real Snap/Jev contracts before scaling (P1; EVAL-09 / EVAL-10)

- **Observed:** The project's question schema uses **`noul`** as an explicit provider-side question type and **Jev** as the configured TypeSafe evaluator name. Do **not** silently replace `noul` with `null`: `null` is also a missing-value concept, not necessarily the vendor's question type. Provider model naming and request/answer shapes remain **unverified live**.
- **Fix/pass (T28):** With separately authorized tiny calls, check actual API names, authentication, three answer types (`noul`, choice, score), response fields, model IDs, rate limits, deadline, usage and output cost. Freeze independent reference judgments *before* judge responses; Jev-generated diagnosis proposals cannot independently calibrate Jev. Keep unknown contracts explicitly blocked or degraded.

#### F09 — Detect plausible failures, not merely passing tests (P1; EVAL-13 / EVAL-14)

- **Observed:** Offline evaluator tests demonstrate important scaffolding but are not a substitute for falsification of runtime assertions, bad retrieval/critic evidence, and repair verification.
- **Fix/pass (T29):** Use risk-ranked mutations and negative controls (unsupported but fluent diagnosis, retrieval failure, invalid critic output, wrong-machine evidence, unauthorized/misapplied fix, failed verification and self-clearing fault). Verify at least one audited success and failure path with a simulated technician-authorized intervention. No real machine control or unapproved master runs.

**Implementation order:** fix **F01 then F03** first (small, immediate evidence/accounting blockers), followed by **F02 and F04** (full inventory and bounded completion). Next enforce F05/F06 and finish the P1 trust/calibration work. Run **Gate A** offline, **Gate B** with fake providers, **Gate C** with explicit authorization for a tiny live pilot, and only then **Gate D** for the evidence-based full-project assessment.

## 3. Gate sequence: when to run what

### Gate A — safe offline preflight

- [ ] EVAL-01 through EVAL-05 and EVAL-19 pass identity, label, cache, truth-boundary, manifest, transport and answer-validation tests on the chosen commit.
- [ ] Import all 52 archived PR #156 episodes with zero collisions and exactly four pending diagnoses; additionally ingest PR #162's five audited cases with **57 unique composite identities**, correct audit linkage, and five full (not record-only) traces (F01/T21).
- [ ] Regenerate the full first-party inventory, reconcile all deliberate exclusions and validate artifact/checksum provenance; explicitly account for every executable test file (including `tests/test_full_evaluation.py`) and the evaluator's own Python implementation (F02/T22).
- [ ] Build packets and dry-run all applicable questions without external model or vendor API calls.
- [ ] Refused, missing-trace, out-of-scope, unfittable and pending items appear in a machine-readable manifest **and a reconciled per-question ledger** (F03/T23).

**Result permitted:** "offline inventory and dry-run ready". **Not permitted:** "full-project evaluator validated".

### Gate B — full offline integration

- [ ] EVAL-06 through EVAL-08 and EVAL-11 through EVAL-13 and EVAL-15 satisfy their tests.
- [ ] Complete FN/TS/TL/RUN/BT orchestration and checkpoint/resume with fake/recorded provider replies; prove small bounded batches can finish a large plan across resumptions without duplicate requests or unaccounted usage (F04/T24).
- [ ] Consolidated reports preserve the published PR #156 denominators and compare the paired arms correctly.
- [ ] Every result names its explicit clean target commit, separate historical run commits, rubric/question versions, evidence completeness and confidence status; invalid case/seed joins are blocked (F05/F06, T25/T26).
- [ ] All intentional test mutations/negative controls are caught.

**Result permitted:** "whole-project evaluation pipeline works offline". It still cannot claim live-judge reliability or full agent-behavior verification.

### Gate C — approved small live calibration

- [ ] Developer explicitly authorizes the small API pilot and associated spend. Do not make live provider requests as part of these documentation changes.
- [ ] EVAL-09 validates real Snap/Jev contracts, including the provider-defined `noul` question type; EVAL-10 freezes independent reference judgments first (F08/T28).
- [ ] Each question family used for scoring has adequate reference support; uncalibrated families remain human-review-only.
- [ ] Request fingerprints, interruption/retry behavior, input costs and provider identity survive real replies.

**Result permitted:** "decision-model judging calibrated for the validated families".

### Gate D — full evidence-based project assessment

- [ ] EVAL-14 includes controlled, fully traced intervention and verification examples.
- [ ] New master-run batches carry complete audits and frozen provenance; archived record-only cases are never falsely upgraded.
- [ ] The approved evaluation plan covers simulator, agent, retrieval, memory, ToT, critic, tools, tests, end-to-end episodes, failure modes and MVP scope.
- [ ] P0/P1 acceptance tests pass on the **exact same code and rubric revisions** being evaluated; all missingness and exclusions remain visible.
- [ ] A final report provides deterministic outcomes and calibrated judge assessments side by side, per-item findings, every denominator, outstanding gaps, distinct functional-correctness and verification-confidence results, and a separate MVP-readiness verdict (F07/F09, T27/T29).

**Result permitted:** "full-project evaluation completed", with any remaining unverified behavior explicitly reported rather than concealed.

## 4. Minimum regression/acceptance test matrix

| ID | Test fixture / operation | Must prove |
| --- | --- | --- |
| T01 | Two PR #156 pairs with repeated run_key | 52 distinct composite episodes; no packet, label or answer overwrite |
| T02 | Four review-pending diagnosis labels | Published 3/12, 3/12, 6/13, 6/11; exactly four remain unjudged |
| T03 | Same request, reordered inventory | Stable resume with no duplicate charge or lost response |
| T04 | Change one request dimension at a time | Model, provider, question text, criteria, rubric, evidence or fitting change invalidates cached answer |
| T05 | Malicious/accidental truth field in state/metadata | Request rejected before provider send, also after trimming |
| T06 | Record-only versus audited episode | Only evidence-supported RUN questions asked; missing facts remain unknown, not false/zero |
| T07 | Incomplete/failed provider response | Explicit failure/incomplete status, safe retry and no bogus completed judgment |
| T08 | Full inventory scan | All first-party definitions covered or reasoned exclusions; stale inventory fails preflight |
| T09 | End-to-end fake-provider evaluation | FN, TS, TL, RUN and BT all covered with complete request/answer/status ledger |
| T10 | PR #156 matched comparison | Correct paired eligibility; no unsupported blind-mode improvement claim |
| T11 | Deliberately wrong but fluent answer | Human reference/evidence judge detects unsupported reasoning independently of root-cause label |
| T12 | Authorized fix, failed fix, self-clearing fault | Verification verdicts checked against state and intervention; no false repair credit |
| T13 | Retrieval outage, provider outage, critic rejection | Operational errors classified separately from investigative reasoning |
| T14 | Many questions in one request | Usage and latency counted per request; missing response counts reconcile |
| T15 | Change target commit/config or scenario seed | Evaluation provenance mismatch is rejected or prominently flagged |
| T16 | Mutated implementation with superficially passing assertions | Test-quality gate detects insufficient coverage or fails the intended regression |
| T17 | Captured transport on a judge request | The project's User-Agent is sent; no key appears in any error |
| T18 | Off-list choice, noul above 1, non-numeric score | Each answer is kept unreadable with a reason; the rest of the request survives |
| T19 | Test and tool states built from the full inventory | No neighbouring test is included; every shortened list or text says how much was kept |
| T20 | Stated question count in the evaluation docs | Matches `load_questions()` |
| T21 | Import both PR #156 and #162 archives, then corrupt audit linkage | 57 unique identities, 52 record-only and five full traces; orphan/duplicate/missing expected audits rejected |
| T22 | Reconcile 88 tracked test files and evaluator code; inject unindexed test | `tests/test_full_evaluation.py` and evaluator modules explicitly accounted for; new omissions fail preflight |
| T23 | Refuse one packet before request building | Every expected RUN question/provider remains in the refused ledger; zero dropped rows or sent refusals |
| T24 | Large fake-provider plan with tiny request/time/money budget and resumed passes | Full eventual completion without duplicate sends; input/output/retry exposure and actual usage constrained or safely stopped |
| T25 | Missing SHA, dirty worktree, stale inventories, different archive source commit | Publishable evaluation refused/demoted; target code, coverage and historical run provenance distinguishable |
| T26 | Permute case positions and seeds while keeping the same case numbers | Mismatched scenario/seed/config invalidates pair; no unwarranted improvement claim |
| T27 | Reference judgments and incomplete functional evidence | Per-function/tool/test findings join independent reference and judge decisions; two nonblended scores, no invented VERIFIED |
| T28 | Authorized small live API contract and calibration pilot | `noul`, choice, score plus model/auth/usage contracts verified or explicitly unavailable; independent frozen references |
| T29 | Risk-ranked mutation and positive/negative simulated repair controls | Weak tests, unsupported conclusions and false resolution fail; authorized repair vs failure are distinguished |

## 5. Deliverables for the actual implementation PRs

The implementation should produce, at minimum:

1. Versioned canonical run identity and archive-import manifest.
2. Versioned judge-request fingerprint, stable resume ledger and provider-contract fixtures.
3. Full first-party inventory, scope/exclusion manifest and verification matrix built on the selected commit.
4. Unified offline/optional-live evaluation CLI for functions, tests, tools, episodes and batch comparisons.
5. Full-trace schema validation and explicit record-only compatibility for archives.
6. An independently adjudicated reference set and calibration report for available decision models.
7. Per-item/per-episode consolidated findings and per-batch aggregation with correct denominators, operational failure classes, provenance and costs.
8. Positive and negative synthetic intervention/verification evidence.
9. Regression tests T01–T29 (including the confirmed F01–F09 defects) and a reproducible, documented dry-run command.
10. A final readiness report clearly separating **implemented**, **verified**, **incomplete**, **not implemented**, **future work** and **blocked for missing evidence**.

## 6. Constraints and handoff

- **Documentation only in this PR update.** Do not misrepresent this checklist as completed fixes; implementation and its tests are subsequent work on the PR branch or separate implementation PRs as appropriate.
- Preserve the original PR #156 archive bytes and all four review-pending labels. Do not silently rewrite historical outcomes to make a metric match.
- Existing master episodes without audits may support deterministic/record-level scoring but **cannot** prove evidence quality, hypothesis testing, retrieval use or causal repair verification.
- Synthetic/public/anonymized inputs only. Hidden simulator truth must remain unavailable to the investigator and to decision-model judges.
- Don't add model providers to the agent. Snap/Jev are optional evaluator-side services only, subject to explicit authorization for live calls.
- **No repository merge, live master run, external API invocation or production logic change is implied by this specification.**

**Release decision:** PR #155's current scaffold can be used for offline inventory work and limited dry runs. As of the static PR #160 review on 2026-11-02, F01–F04 remain confirmed implementation blockers and F05–F09 remain trust/reproducibility requirements. The independent reviewer could not run the new Python 3.14 acceptance tests, so their outcomes are unknown. Treat the full-project evaluator as **NOT READY** until P0/P1 requirements and Gates A–D are actually satisfied and evidenced. Keep PR #159 and PR #160 **unmerged** pending developer review.
