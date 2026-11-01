# Final report

Answers to the audit's final questions, with the evidence behind each. On
`main` at `bc9d155`, 2026-11-01. Counts come from
`inventory/VERIFICATION_MATRIX.json`; findings are referenced by id from
`EVALUATION_AUDIT.md`.

## Part A: the thirteen questions

**1. How many project-owned functions, methods, tools and tests exist?**
602 functions and methods in `capstone-code/capstone` (24 of them protocol
stubs or abstract definitions, 213 classes listed through their methods),
17 agent-facing tools (15 factory tools of which 3 are the loop's fixed
procedure, plus `recall_memories` and `search_manual`), 1,357 test
functions giving 1,708 cases. Exclusions are listed in the matrix.

**2. How many functions have meaningful verification coverage?** 557 are
executed by at least one test and 369 by a direct test. After reviewer
judgment: 43 VERIFIED, 340 PARTIALLY VERIFIED, 177 INSUFFICIENT EVIDENCE
(executed only by other modules' tests or at import), 18 NOT TESTED, 24 NOT
APPLICABLE, 0 FAILED. "Meaningful" in the rubric's sense (contract stated,
failure paths asserted) is the 43 VERIFIED, all in the loop, the stages,
the provider boundary, the approval desk, scoring, the memory gate, the
client and the hazards. The other 340 have direct tests that passed; their
failure paths are not individually established.

**3. How many tests adequately verify their intended behaviour?** All
1,349 pre-existing test functions passed. Reviewed by hand: 28, of which
15 STRONG, 7 ADEQUATE, 3 STRUCTURAL, 3 WEAK. Heuristically flagged: 49
assert only truthiness or not-None (most adequate for their claim on
inspection, 3 confirmed weak), 95 exercise no project function (rules about
imports, prompts and record formats), 1 has no assert statement (it uses
`pytest.raises`). The honest answer is "most, with 1,329 not individually
assessed"; TS-01 to TS-03 are written for that assessment.

**4. Which tests could pass while the implementation is wrong?**
`tests/test_evaluation.py::test_a_reset_resolves_a_wrong_setting` and
`test_rejected_proposals_do_not_count_as_actions` (truthiness only),
`tests/test_baseline.py::test_the_right_repair_is_carried_out_and_nothing_for_a_false_alarm`;
every scripted-episode test as evidence of reasoning (T2); the known-answer
suite before PR #149 for `_resolved` on forced faults (T4, now fixed).
`test_the_agent_never_holds_the_answer_key` would miss a leak under another
name (the key-set test would not).

**5. Which tools are most vulnerable to silent failure?** `get_sensor_trend`
(bucket boundaries untested; idle readings pull means down by design),
`get_readings` under a `Gap` hazard (rows dropped from the middle third with
`success = true`, by design and reported in the record, invisible to the
agent), `get_maintenance_history` under a `StaleRecord` (same), and
`get_sensor_summary` with its endpoint rate (documented, not a slope). The
undesigned risk is low: every answer is rebuilt from an output contract
(`run_tool`). TL-03 is written for the judge to look for more.

**6. Which architectural components are inadequately verified?** Live
entry points (`evals.main` 28 of 60 statements, `experiment.open_memory`,
`manual.index.open_manual_index`, `automatic_labels`): untested offline by
necessity, so a broken live path shows up only in a run. Memory end to end
(never run live). The critic's effect (ungated, unmeasured). Monitoring's
routine-check branch. The manual's semantic index (keyword path tested;
Chroma path only with the extra).

**7. What do the master runs actually prove?** That the whole path runs
live against real models with fallbacks, that budgets and timeouts hold,
that the agent diagnoses bearing wear and false alarms often and batch and
setting faults never, that it rarely asks for a fix, and that one run
(KA-02, 2026-10-27) reached a right diagnosis, an approved repair, a
verified result and a truth-resolved fault. They do not prove reasoning
quality (no evidence kept, R1), improvement over time (X1), or that the
critic, the manual or memory help (A1, A3, A5).

**8. Which important failure modes are not covered?** Confident no-action
on insufficient evidence (A2), a right answer by guess (Q4), critic
feedback ignored, manual retrieved and unused, verification verdict wrong
(E5), configuration drift inside a resumed run (R2), labeller bias (R4),
self-clearing faults counted as resolved (E4), variance between runs of
one case (X2).

**9. MVP requirements: implemented, verified, incomplete, unimplemented?**
See `MVP_SCOPE_MATRIX.md`. Implemented and verified offline: 1a, 1c, 1d, 2,
3a (structure), 3b, 4, 5 (structure), 6, 7, 9a, 9c, 9d. Implemented but not
demonstrated: 8 (memory, never live), 9b (reporting, misleading lines).
Partial: 1b (throughput and defect rate are not sensors). Unimplemented
and out of scope: MCP, observability, frontend, specialists beyond the
critic.

**10. Can Snap independently evaluate the evidence with this framework?**
For runs: only runs made with `--audit` (none on record); the packet gives
it the trace without the truth, and 12 questions with missing-evidence
rules. For functions, tests and tools: yes, from the inventories and the
source, with the deterministic facts in the state. The API shape must be
confirmed first (S1) and the judge validated on the reference set.

**11. What deterministic evidence is required before Snap judgments are
meaningful?** An audit log per run; the commit and configuration per
batch; labels decided before comparison; the reference set with the
developer's own answers; and the four added facts (`verification_calibration`,
`machines_examined`, `cited_by_origin`, a windowed evidence share) so that
the judge's answers can be checked against code where possible.

**12. Three improvements that would most increase confidence.**
(1) `--audit` by default and provenance in the report (R1, R2, R3). (2) A
label projection without truth and a recorded agreement figure (R4, E1).
(3) Guards beside every summary figure and the batch table of the rubric
(E2, E3, E4, E5).

**13. Is the current methodology sufficient for the capstone's claims?**
For "the agent loop works end to end with hidden truth kept out of the
agent": yes, and well. For "the agent diagnoses root causes well", "the
critic helps", "memory helps", "the system is improving": no. Those claims
need matched batches with frozen configuration, labels decided first,
audit logs, repeats, and the judged evidence-quality score beside the
accuracy figure.

## Part B: the first prompt's deliverables

**1. What the master runs prove.** See question 7. In one sentence: the
plumbing is proven live, the reasoning is not, and the numbers between
runs are not comparable.

**2. The five metrics to track.**

| Metric | Why this one |
|---|---|
| root-cause accuracy with the "misleading success" count beside it (fully_right; RUN-08 < 2 on right runs) | the headline, guarded |
| confident-wrong and false-intervention counts | the two ways an agent harms a factory |
| evidence-grounded decisions (right, RUN-08 ≥ 3, RUN-12 ≤ 0.3) | accuracy that is earned |
| verification calibration distribution | whether "it worked" means it worked |
| timeouts and mean wall seconds per case, with tool calls | the cost of the above |

**3. Strongest evidence the system performs correctly.** The scoring
integrity tests; the key-set leak test; the 22 verification tests; the
approval desk tests; KA-02 of 2026-10-27 live (right, fixed, verified,
truth-resolved); the determinism tests (same seed, same episode, same
hazards).

**4. Biggest evaluation blind spots.** R1 (no evidence kept), E2/E4
(credit for inaction and self-clearing faults), R4/E1 (labels next to the
truth, no agreement figure), A1 (critic unmeasured), X1/X2 (no comparable
batches, one run per case).

**5. Reusable context package.** `PROJECT_EVALUATION_CONTEXT.md` (stable,
versioned), `EVALUATION_RUBRIC.md`, `SNAP_QUESTIONS.json`,
`RUN_EVIDENCE_SCHEMA.json`, the inventories, and per-run packets. Each
carries its version; results carry rubric version, commit and a state
digest.

**6. Ready-to-use decision questions.** `SNAP_QUESTIONS.json`: RUN-01 to
RUN-12 (per run), FN-01 to FN-03 (per function), TS-01 to TS-03 (per test),
TL-01 to TL-03 (per tool), BT-01 and BT-02 (per batch comparison). Request
bodies are produced by `evaltools.snap_request` in dry run.

**7. The three highest-value experiments.**

1. **Critic off versus critic on with follow-up, matched.** All 13 known
   cases, one commit, one `.env`, `--audit`, labels decided before
   comparison, two repeats per case if the budget allows. Score with the
   rubric's batch table and RUN-03/RUN-11. Pass if accuracy and
   evidence-grounded decisions rise without more confident-wrong or false
   interventions and within 1.3 times the wall time.
2. **Batch and setting faults in isolation.** KA-03 to KA-06 three times
   each with the current defaults and `--audit`, then RUN-07 on every miss.
   The point is to classify the persistent failure (reasoning versus
   tooling versus retrieval) before changing anything.
3. **Memory on versus off** (`memory_comparison run --known` after filling
   the store on tuning seeds), the only way to support the MVP's "basic
   memory" claim.

## Part C: the one question

*Across the same scenarios, has the current architecture improved
root-cause accuracy and evidence-grounded decision-making without
increasing unsupported conclusions, unnecessary tool calls or investigation
failures?*

Not answerable from the runs on record. The scenarios were the same, the
configurations, commits and label rules were not, no run kept the evidence
that "evidence-grounded" needs, and no case was run twice under one
configuration. The framework in this folder is what makes the question
answerable: packets with the judge view apart from the truth, the guarded
batch table, the comparison questions BT-01 and BT-02, and the three
experiments above.
