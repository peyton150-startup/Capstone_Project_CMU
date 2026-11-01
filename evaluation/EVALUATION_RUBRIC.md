# Evaluation rubric

- rubric_version: 1.0.0 (2026-11-01). Changing a definition, a denominator
  or a threshold is a new version; results carry the version they were
  scored under and are never rescored silently.
- Pairs with `PROJECT_EVALUATION_CONTEXT.md` 1.0.0, `SNAP_QUESTIONS.json`
  1.0.0 and `RUN_EVIDENCE_SCHEMA.json` 1.0.0.

## 0. Two scores, never one percentage

Every level below reports two separate figures:

- **Functional correctness**: the share of intended behaviours demonstrated
  to work, by a deterministic check or by a passed test whose assertions a
  reviewer judged adequate.
- **Verification confidence**: how strong the evidence behind that share is
  (direct tests with failure paths, integration evidence, a traced live run,
  a judge's agreement with the reference set), reported as the distribution
  of statuses (VERIFIED / PARTIALLY VERIFIED / INSUFFICIENT EVIDENCE / NOT
  TESTED / FAILED / NOT APPLICABLE), not as a number.

A function with five passing tests that never exercise its failure path
scores "works on the happy path" for correctness and PARTIALLY VERIFIED for
confidence. Nothing in this rubric folds the two together.

## 1. Statuses and who may set them

| Status | Meaning | Set by |
|---|---|---|
| VERIFIED | Contract stated; direct tests assert it, including failure and boundary paths; all passed on the commit under review | a reviewer, in `curated/function_notes.json` |
| PARTIALLY VERIFIED | Executed by direct tests that passed; some path or the contract unproven | default for `coverage_class = direct`, or a reviewer |
| INSUFFICIENT EVIDENCE | Executed only by other modules' tests, or only at import | default for `indirect` / `import-only` |
| NOT TESTED | Never executed by any test | default for `none` |
| FAILED | A test failed, or a reviewer found the implementation contradicting its contract | junit outcome or a reviewer |
| NOT APPLICABLE | A protocol method, stub or abstract definition | default for `no-statements` |

Rule: no machine rule grants VERIFIED. A passed test is an execution fact;
VERIFIED is a judgment that the test proves the contract.

## 2. Level 1: function correctness

Per function (597 on the reviewed commit), from `inventory/FUNCTION_INVENTORY.json`:

| Metric | Calculation | Deterministic? | Evidence |
|---|---|---|---|
| executed_in_tests | any test context on a body statement | yes (coverage contexts) | `.coverage` with `--cov-context=test` |
| statement_coverage | executed body statements / body statements | yes | same |
| coverage_class | direct (a test in the module's own test file or named for the function), indirect, import-only, none, no-statements | yes | same |
| contract_specified | docstring or `# Variables:` block present | yes | AST |
| failure_paths_covered | FN-02 judgment, or a reviewer | no (judge) | source + tests |
| verification_status | section 1 | mixed | curated notes |

Aggregates: counts by status (denominator: all 597, with NOT APPLICABLE
listed apart), by module (`VERIFICATION_MATRIX.json` `by_module`).

## 3. Level 2: tool correctness

Per tool (17): schema correctness (argument model equals the provider
table, tested), boundary (no hidden field in any answer over a full run,
tested; TL-01 for undesigned paths), description accuracy (TL-02), silent
failure risk (TL-03), access boundary (procedure tools never offered to a
policy, tested), and observability (every call leaves a `DecisionRecord`,
tested). Aggregate: number of tools with each TL verdict; a tool scored 3 on
TL-03 is listed by name.

## 4. Level 3: test quality

Per test (1349 functions, 1700 parametrized cases), from
`inventory/TEST_INVENTORY.json`:

| Metric | Calculation | Deterministic? |
|---|---|---|
| execution_outcome | passed / failed / skipped / not_run from junit | yes |
| assertions, assert_forms, raises_checks | AST count by form | yes |
| quality flags | no_assertion; weak_assertions_only (truthiness or not-None only); patches_dependencies; may_skip; exercises_no_project_function | yes (heuristics; a reviewer may override) |
| judgment | STRONG / ADEQUATE / WEAK / STRUCTURAL from `curated/test_notes.json`, or TS-01..03 from the judge | no |

Aggregates: tests by outcome; flagged tests by flag; judged tests by
judgment with the number still NOT ASSESSED stated.

## 5. Level 4: agent behaviour (per run)

All from one `RUN_EVIDENCE_PACKET` (`evaltools.run_packet`). "Trace" means
the audit log was present (`trace.completeness = full`).

| Metric | Definition | Deterministic? | Needs trace? | Source |
|---|---|---|---|---|
| machines_examined | machines named in tool arguments | yes | yes | facts |
| sensors_read | sensors per machine | yes | yes | facts |
| repeated_calls, failed_tool_calls | decision outcomes | yes | yes | facts |
| observable_evidence_cited, cited_by_origin | conclusion citations by provenance origin | yes | yes | facts |
| evidence_quality | RUN-01, 0-4 | judge | yes | Snap |
| hypothesis_reasoning | RUN-02, 0-4 | judge | yes | Snap |
| conclusion_support | RUN-08, 0-4, independent of truth | judge | yes | Snap |
| unsupported_confidence | RUN-09 noul; decision rule 0.7 / 0.3 | judge | yes | Snap |
| evidence_cited_matches_content | RUN-12 noul | judge | yes | Snap |
| critic_effectiveness | RUN-03 choice | judge | yes | Snap; beside `critique.verdict_mismatch`, `recheck.outcome` |
| critic_feedback_used | RUN-11 choice | judge | yes | Snap |
| critic_pick_correct | the critic's favoured claim labelled and judged | yes (given a label) | no | evaluator_only |
| retrieval_quality | RUN-04 choice; beside search counts and `cited_by_origin["manual"]` | judge | yes | Snap |
| verification_demonstrated | RUN-05 choice | judge | yes | Snap |
| verification_calibration | agent verdict vs truth: true_resolved, true_unresolved, false_resolved, false_unresolved, inconclusive, not_performed, no_verdict | yes | no | evaluator_only |
| abstention_appropriate | RUN-06 choice | judge | yes | Snap |
| failure_classification | RUN-07 choice | judge | partly | Snap; beside `miss_kind` and `termination_reason` |
| scan_before_no_fault | RUN-10, validation of the deterministic `machines_examined` | judge | yes | Snap |

Derived flags (code, from code facts and judge answers together):

- **misleading success**: `fully_right = true` and RUN-08 mean < 2 (or
  RUN-01 mean < 2). Reported as a count; it is the single most important
  check that the accuracy figure is not flattering.
- **evidence-grounded decision**: `fully_right = true` and RUN-08 mean ≥ 3
  and RUN-12 ≤ 0.3.

## 6. Level 5: end-to-end (per batch)

From `BATCH_SUMMARY.json`. Denominators are stated with every figure.

| Metric | Numerator / denominator | Deterministic? |
|---|---|---|
| root-cause accuracy | runs `fully_right = true` / judged runs (a label exists and is not flagged for review) | yes, given labels |
| accuracy when committed | right / runs whose label names a cause | yes |
| abstention rate | abstained / judged | yes |
| confident wrong | committed, wrong, confidence ≥ 0.8 / judged | yes |
| right recommendation | `recommendation_correct` / reasoned runs. Caveat: true for an escalate on any case that needs no action; report beside abstention | yes |
| false interventions | asked for a fix the truth did not need / reasoned | yes |
| appropriate intervention, resolved | as scoring; `resolved` credits faults that clear by themselves, so report `causes_resolved` for repair-needing faults apart | yes |
| evidence share | relevant evidence collected / available (any window counts; see audit E3) | yes |
| miss kinds | evidence_miss / reasoning_miss counts over wrong judged runs | yes |
| verification calibration | distribution of the seven classes | yes |
| timeouts, model_unavailable | by termination reason | yes |
| mean tool calls, factory calls, wall seconds, model questions, invalid replies, outage attempts | means over reasoned runs | yes |
| cost | not measured: no token accounting exists in the records (see audit X3) | no |
| consistency | the same case run n times: share of runs with the same `fully_right` | yes, needs repeats |

Thresholds (proposed, not met or claimed): a batch is "comparable" only if
BT-01 is valid; an "improvement" claim needs BT-02 = improvement, which
needs at least two repeats per case or all 13 known cases, and no increase
in confident-wrong, false interventions or misleading-success counts.

## 7. Level 6: MVP readiness

`MVP_SCOPE_MATRIX.md` scores each MVP requirement as implemented / verified
/ incomplete / unimplemented with the evidence named, and lists the
blockers. No percentage is computed.

## 8. Reference set and bias controls

- A reference set of judged packets (`packets/reference/`, to be filled)
  with the developer's own answers to RUN-01, RUN-08 and RUN-06, chosen to
  include known-good runs (KA-02 of master-single-2026-10-27, right and
  verified) and known-bad ones (KA-09: confident, wrong, false intervention),
  plus one deliberately broken packet (a conclusion whose cited ids point at
  unrelated readings). Snap is trusted on a question only once its
  agreement with the reference answers is recorded in
  `EVALUATION_AUDIT.md` section 9.
- Labels are decided before any batch comparison and never changed after.
- The judge never sees `evaluator_only`; the hidden-truth words are checked
  absent from every `snap_view` by `run_packet.check_no_truth_in_view`.
- Judge answers are stored with `rubric_version`, `question_ids`,
  `state_digest` and `commit_sha`; a rubric change invalidates nothing but
  starts a new column.
- Snap results never enter the agent's memory store or any prompt.

## 9. Aggregation rules

- Never average a score across questions of different kinds.
- Report per case first, then per fault kind, then the batch.
- A missing answer is a count of its reason (`unknown`, `not_run`,
  `not_offered`, `not_applicable`), never a zero.
- One run per case is reported as a snapshot; the word "improvement" is
  reserved for BT-02 = improvement.
