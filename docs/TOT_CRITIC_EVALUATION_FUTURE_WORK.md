# Future work: evidence-scored ToT and critic-controller evaluation

**Status:** PLANNED / EVALUATION ONLY — not enabled, implemented, or approved for a runtime change by this document.  
**Priority:** After the ongoing experiment finishes; first prioritize pruning correctness and evaluator quality.  
**Source:** CMU Module 4, Mini-Lesson 4.1, *Tree-of-Thought Accuracy and Structure in Multi-Agents*; [Tree of Thoughts (Yao et al., 2023)](https://arxiv.org/abs/2305.10601).  
**Related:** [Review signal 2026-10-30](REVIEW_SIGNAL_2026-10-30.md) (verified findings from the ToT review and machining videos). **Related roadmap:** [MVP Scope — GoT and multi-cause diagnosis](MVP_SCOPE.md#graph-of-thoughts-got-hypothesis-reasoning--medium-priority-evaluation-2026-10-29) and [Future Work 7](MVP_SCOPE.md#future-work-7--model-evaluation-execution-budgets-and-computed-evidence).

## Scheduling gate: protect the runs in progress

On 2026-10-29, the developer reported that the current evaluation is at **run 1 of 2**, with substantial testing still ahead. The run status is operator-reported, **not independently verified** here.

- Finish both existing runs using their **already selected** model/provider, code revision, prompts, retrieval/manual mode, critic/ToT flags, evaluation rubric, cases, seeds, and budgets. Do **not** switch on ToT, introduce new critic behavior, change scoring, restart jobs, or modify the experiment while collecting this series.
- Preserve results and reproducibility metadata (commit SHA, CLI arguments, scenario/seed, model/provider versions where known, retrieval/manual snapshot, timestamps, wall time, tokens/model calls, tool calls, completion and failure reasons). Keep evaluator-only truth outside agent-visible inputs.
- Treat two runs as a **baseline snapshot**, not statistically sufficient evidence for a superiority claim. Design a later matched-seed, repeatable evaluation with enough cases to expose regressions. Record which comparisons are scripted/offline versus fresh live model calls.
- Begin this future-work series **only after** the current runs are complete, their records are saved, and baseline scoring is confirmed. This PR must not alter active jobs, CI gates, test scenarios, simulator behavior, or production defaults.

## Current implementation (verified in `main` at planning time)

- `capstone-code/capstone/agent/tree_of_thought.py`: opt-in, depth-one candidate generation (up to five), model rating, deterministic pruning (retain up to three); its surviving candidates become hypotheses and discriminating questions. This is **not** deep/full-tree ToT.
- `capstone-code/capstone/agent/critic.py`: independent reviewer of up to five surviving hypotheses and observed evidence; checks that claimed evidence IDs were gathered, but cannot independently prove their semantic relevance.
- `capstone-code/capstone/agent/investigation.py`: explicit Pydantic Graph stages with critic before conclusion and an **optional** single, read-only critic-directed recheck. The critic does not directly overwrite a diagnosis or approve an action; the controller/policy makes the next decision.
- `tests/test_tree_of_thought.py`: scripted/offline baseline-versus-ToT contract test; it confirms an extra model question in that case, **not** an aggregate live accuracy gain.
- Existing `MVP_SCOPE.md` already proposes multi-label diagnosis, position-invariance checks, and optional GoT. This page sequences and gates those proposals rather than adding a new framework.

## Ranked experiments after the baseline

### P0 — Unproven "impossible" ratings must not become confident hypotheses

**Problem (verified against `main`, 2026-10-30):** In `prune()` (`agent/tree_of_thought.py`), a candidate rated `impossible` with no gathered contradiction is added to `unproven` and kept in `alive`, then ranked by `rating.confidence`. `TreeOfThoughtPolicy.hypothesize()` copies that same value into `Hypothesis.confidence`. But for an `impossible` verdict, the model's confidence is confidence *that the candidate is false*. A rating of `impossible, 0.95` with nothing cited therefore becomes H1 at 0.95.

That value is used downstream:

- `InvestigationState.leading_hypothesis` / `confidence` (`agent/state.py`) pick the highest-confidence hypothesis.
- `critic.shown_hypotheses()` sorts by confidence, so the critic sees it as the leading hypothesis.
- `loop.py` gates diagnosis on `min_diagnosis_confidence` (default 0.9) and `investigation.py` gates action on `min_action_confidence` (default 0.9). A 0.95 "impossible" can clear both.

`tests/test_tree_of_thought.py` only covers unproven-impossible ratings at 0.1 to 0.4, so this case is untested.

**Change (small, deterministic, no extra model calls):**

1. In `prune()`, rank an unproven `impossible` by a neutral score instead of `rating.confidence` (e.g. `min(rating.confidence, 1 - rating.confidence)`, or a fixed floor such as 0.1), and always rank it below every `sure`/`likely` candidate.
2. In `hypothesize()`, set `Hypothesis.confidence` for an unproven candidate to that same neutral score, never the raw rating confidence.
3. Record the case in `Thought` (e.g. `unresolved: tuple[str, ...]`) so experiment records show which kept candidates came from an unsupported `impossible` verdict.
4. Add tests: `rating("C1", "impossible", 0.95)` with nothing cited must not rank first and must yield a hypothesis below `min_diagnosis_confidence`; a `likely, 0.6` candidate must outrank it.

**Pass criteria:** The new tests pass; existing `test_tree_of_thought.py` tests are unchanged except where they assert the old ranking. No change to model-call count, so no latency impact.

### P1 — Evidence-grounded pruning and deferred alternatives

**Problem:** `prune()` checks whether cited evidence IDs exist and permits an `impossible` verdict to remove a hypothesis when a gathered contradiction ID is cited. Citation existence alone does **not** establish a real contradiction. The fixed top-three cap can also discard plausible simultaneous causes merely by rank.

**Experiment:** Compare current top-k against a bounded, evidence-aware policy. Distinguish `contradicted` (supported refutation), `deferred/untested` (budget/rank), `supported`, and `unresolved`. Make a deferred cause observable to evaluation; do not silently mark it false. Preserve multiple independently supported explanations, e.g., bearing wear **and** excess cutting load. Prefer deterministic contradiction/constraint checks where the simulator or sensor contract genuinely supports them; uncertain semantic claims remain unverified, not hard rejects.

**Pass criteria:** Improve true-cause retention and multi-cause recall without unacceptable extra false positives, unsafe interventions, or latency. Include cases with misleading but real evidence IDs, correlated measurements, noisy/missing telemetry, and false alarms.

### P2 — Critic review of possible false eliminations

**Problem:** The existing critic sees **survivors**, not discarded candidates. A correct cause that was pruned before critique may be invisible to the reviewer. The optional post-critic one-observation loop does not fix a missing candidate by itself.

**Experiment:** Start with a low-cost **deterministic** audit of reasons for pruning. If measurable false eliminations remain, test an opt-in, bounded pre-prune critic check of questionable exclusions; optionally reinstate one justified candidate for a single discriminating observation. Use the existing tool and approval boundaries. Do not add an extra agent or model call by default.

**Pass criteria:** The critic detects and recovers more mistakenly discarded true causes, records its objections and the controller response, and does not merely increase model agreement or generate endless rechecks.

### P3 — Adaptive branching and explicit controller limits

**Problem:** Current opt-in ToT has static candidate and survivor counts (defaults five and three), although easy single-fault investigations may need no branching and ambiguous cases may need an extra alternative.

**Experiment:** Compare the static depth-one mode with a controller that uses observable ambiguity (contradictory readings, unresolved distinct hypotheses, poor evidence coverage) to decide **whether** to branch and how many candidates to retain. Keep the implementation within current Pydantic Graph/typed policies; a new orchestration framework is not needed. Explicitly cap width, depth, model calls, tool calls, wall time, and retries; preserve a reserve for conclusion, human-approved action, and verification. Support honest `undetermined` / escalation when evidence is insufficient.

**Pass criteria:** Match or improve root-cause/action accuracy on difficult cases while reducing unnecessary model calls on simple cases and respecting deadlines.

### P4 — Evaluate the evaluator, not just the generator

**Problem:** Current rankings rely on a model's self-reported confidence, with candidate order as a tie-breaker. Existence of a supporting citation is not proof of its strength. A critic can confidently prefer an unsupported explanation.

**Experiment:** Compare a transparent evidence-strength rubric (independent support, contradictions, symptom coverage, telemetry provenance/freshness, outstanding checks) against raw model confidence. Avoid double-counting correlated sensor summaries and readings. On a fixed set of cases, rotate candidate order and separately score individual hypotheses to quantify ranking/position sensitivity. Keep log-probability scoring an optional feasibility study, **not** a presumed bias fix or calibrated probability.

**Pass criteria:** Better evidence attribution, stable rankings under reordering, improved calibration only if probability calibration is actually measured, and fewer confidently wrong diagnoses.

### P5 — Bounded second depth through observation, not more model reasoning

**Problem:** Current ToT is depth one: `hypothesize` generates, rates and prunes once, and the kept candidates' questions (T1, T2, ...) go to the existing test stage. There is no point where the tree is re-valued after the test stage gathers new evidence, so an early wrong ranking is only corrected by the ordinary loop.

**Experiment:** Reuse existing infrastructure rather than adding search code or agents. After the test stage answers the T questions, run one more `value` + `prune()` pass over the *same kept candidates* (no new `generate` call), using the newly gathered evidence IDs. Cap at depth two. Do not implement the course lab's breadth-five, depth-three BFS.

**Time budget:** This adds one model question per investigation. Measured per-question latency in `docs/benchmarks/2026-10-27-master-resumed.records.jsonl` ranged from about 4 s to 113 s, and that run hit `timeout` at about 881 s wall time. So:

- Skip the second pass when it would eat into `followup_seconds` (default 400 of `timeout_seconds` 1200, `agent/state.py`).
- Prefer routing the `value` question to the faster model in the chain, since rating is a narrow job.
- Pair with P3: only branch (and only re-value) when the case is ambiguous.

**Pass criteria:** Better recovery after an early wrong hypothesis and better true-cause retention than depth-one (cohort D), with no rise in `timeout` terminations and p95 wall time within budget.

### Not planned: a third agent for speed

Considered on 2026-10-30 and rejected for now. The pipeline's time goes to sequential model calls and provider timeouts, not to agent count; another agent adds calls. A third agent would only cut time if it ran in parallel with currently sequential work, or did a narrow job (e.g. "should we branch?") on a much faster model. Cheaper levers first: route fast jobs to the faster model, tighten per-call timeouts so failover happens sooner, and P3's adaptive branching.

## Controlled comparison matrix

| Cohort | Hypothesis policy | Critic | Critic-directed recheck | Question answered |
| --- | --- | --- | --- | --- |
| A | Ordinary bounded investigator | Off | Off | Baseline |
| B | Ordinary bounded investigator | Review-only | Off | Added value of critic review |
| C | Ordinary bounded investigator | On | One bounded, read-only check | Added value of closing the critic loop |
| D | Opt-in depth-one ToT | On | Same one-check policy as C | Incremental value of ToT branching |

For P0 and P5, add: **D0** = cohort D with the P0 fix, and **D2** = D0 plus the P5 second pass. Compare D vs D0 (fix only) and D0 vs D2 (depth two). Compare C vs D to isolate ToT; B vs C to isolate recheck; A vs B to isolate review. If evaluating P1–P4 changes, add a separate ablation against the most appropriate frozen cohort, **one change at a time**. Hold fixed the scenario/seed set, model/provider, prompts except the intended treatment, retrieval/manual snapshot, evaluation code, tool availability, approvals and configured global budgets. Disclose unavoidable model-call differences and whether results were fresh or replayed.

**Core measures:** root-cause accuracy, correct-cause retention before/after pruning, multi-label precision/recall/F1 on applicable compound-fault cases, false interventions, action correctness, post-action verification, unsupported/contradictory citations, recovery after an early wrong hypothesis, abstention under degraded data, completion/failure rate, model/tool calls, tokens/provider cost if available, and p50/p95 wall time.

**Decision rule:** Only enable a changed policy by default if repeatable matched-case improvements are meaningful and do not regress safety, evidence quality, or intended pilot runtime. Otherwise retain the existing simpler baseline. A passing scripted unit test is not enough to claim increased real-model diagnostic accuracy.

## Boundaries and non-goals

- No modifications in this documentation PR to `agent/`, contracts, simulator, experiments, test files, settings, providers, or active workflows.
- No automatic physical maintenance action: preserve read-only research, human approval, ground-truth isolation, and independently observed post-action verification.
- Do not equate more agents, longer reasoning, model confidence, or wider search with accuracy.
- Do not implement Graph of Thoughts or multi-agent orchestration as a prerequisite; consider them **only after** the simpler ToT/critic ablations show a remaining measurable gap.
