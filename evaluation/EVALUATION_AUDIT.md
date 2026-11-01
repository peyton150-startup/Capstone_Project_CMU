# Evaluation audit

Findings of the evaluation architecture review of 2026-11-01, on `main` at
`bc9d155`. The brief was to find evidence that the current success
measurements are misleading, not to confirm that the project works. Where
the evaluation is well designed the audit says so and names the test that
proves it.

Each finding has an id (A agent behaviour, E evaluator and scoring, R
records and reports, L leakage boundary, T tests, X experiments, S the
Snap integration) and an evidence reference: a file, a function, a test, a
record or a note in `docs/PROGRESS.md`.

## 1. Scope and method

Read in full: `agent/investigation.py`, `agent/loop.py`,
`agent/model_policy.py`, `agent/critic.py`, `agent/state.py`,
`agent/tree_of_thought.py`, `agent/evidence_brief.py`, `agent/completion.py`,
`agent/artifacts.py`, `agent/policy.py`, `agent/monitor.py`, `episode.py`,
`experiment.py`, `evals.py`, `evaluation/scoring.py`, `evaluation/labels.py`,
`evaluation/known_answers.py`, `evaluation/auto_label.py`,
`evaluation/memory.py`, `evaluation/manual.py`, `faults.py`, `settings.py`,
`baseline.py`, `providers/factory.py`, `providers/chat.py`,
`providers/hazards.py`, `providers/recall.py`, `providers/manual.py`,
`providers/typesafe.py`, `tools/observation.py`, `tools/actions.py`,
`tools/diagnosis.py`, `simulator/simulator.py`, `simulator/generator.py`,
`simulator/challenge.py`, `simulator/ground_truth.py`, `simulator/state.py`,
`manual/sections.py`, `memory/policy.py`, `memory/service.py`,
`memory/reflection.py`, `learning.py`, the contracts, and the tests named in
`curated/test_notes.json`. Read in part (class and function index, headers):
`simulator/scenarios.py` (`ProductionLine`, ambient and door scenarios not
read line by line), `simulator/sensors.py`, `simulator/line.py`,
`simulator/disturbances.py`, `progress.py`, `benchmark.py`,
`memory_comparison.py`, `memory/recall.py`, `memory/semantic.py`,
`memory/repository.py`, `manual/index.py`, `providers/embeddings.py`. Not
read: `simulator/thermal.py`, `events.py`, `clock.py`, `rng.py`,
`maintenance.py`, `memory/duplicate_threshold.py`, `memory/backfill.py`,
`database/connection.py`, `console.py`, `observability.py`, the migrations.
Those modules are in the inventories with machine-derived statuses only.

Executed: the whole offline suite with per-test coverage (1,700 cases
passed before this change, 8 added), the inventory builder, the packet
builder on the one master run whose records are in the repository, the
request builder in dry run, and the traced runner with the scripted
stand-in. No model was called and no live run was launched.

Documents read: `AGENTS.md`, `docs/MVP_SCOPE.md` (sections 1-9, the
future-work index, the live-runs-owed and SubQ sections),
`docs/PROGRESS.md` (the status table, the 2026-10-27 to 2026-10-31 notes),
`docs/RUN2_FINDINGS_FUTURE_WORK.md`, `docs/INVESTIGATION_REASONING.md`,
`docs/TOT_CRITIC_EVALUATION_FUTURE_WORK.md` (head),
`docs/UNGATED_BUILD_SUMMARY.md`, `docs/benchmarks/2026-10-26-scored-single-agent.md`,
the 2026-10-27 master report, records and labels, `README.md`.

Limits: docs.subq.ai did not resolve from the session, so the Decisions
API shape in `SNAP_QUESTIONS.json` is second-hand (S1). Hand review covered
59 functions and 28 tests; the other 543 functions and 1,329 tests carry
machine-derived statuses only (`VERIFICATION_MATRIX.json`).

## 2. What a successful master run currently means (Phase 2)

**Q1. What success means in the code.** `capstone.evals.report_of` sets
`EvalCase.correct = Score.fully_right` only when a label exists for the run
and is not flagged for review; `overall_accuracy` is right cases over judged
cases. `Score.fully_right` (`evaluation/scoring.py`) is true when every true
cause is named and no wrong cause is, by the label's fault kind and machine
or batch. Nothing else enters "correct": not the evidence, not the
recommendation, not the verification, not the time. The text report of
`capstone.experiment.report` adds right recommendations, unnecessary and
appropriate interventions, resolved, evidence share, miss kinds and tool
calls, each on its own denominator.

**Q2. What that proves.** That a person reading the conclusion recognised
the true fault kind on the true machine or batch. It is a correct test of
the final words against the hidden truth, made after the run and without
side effects (`tests/test_scoring_integrity.py`). It proves nothing about
how the words were reached.

**Q3. Can a run pass with the wrong root cause?** By the accuracy figure,
no: the label must name the truth. By the other summary lines, yes:
`recommendation_correct` and `action_correct` are true for any run that asks
for nothing on a false-alarm or bad-batch case, whatever it concluded
(`scoring.evaluate`: `sorted(asked) == sorted(wanted)` with `wanted` empty).
In master-single-2026-10-27, 2 of the 5 "right recommendations" are
escalations on cases whose cause the agent did not name (KA-03, KA-04 by
hand label None; packets `evaluator_only.recommendation_correct = true`,
`fully_right = false`). `resolved` is true for KA-03, KA-07 and KA-08 where
the fault ended by itself (E4). So the one-line summary can read well while
the diagnosis is wrong. (E2, E4)

**Q4. Correct answer through invalid reasoning, leakage or assumptions?**
Possible by design, and the tests say so:
`tests/test_agent_investigation.py::test_a_conclusion_resting_on_misleading_but_real_evidence_is_accepted`
pins that `check_conclusion` verifies only that cited ids exist and that
numeric claims add up, never that the evidence supports the claim. A label
reads the words. Leakage is guarded well (section 4, L1), so a right answer
is unlikely to come from the truth; it can come from a guess that matches a
two-word label. The saved records cannot tell the two apart, because they
keep no evidence or hypotheses (R1). The packet's RUN-01, RUN-08 and RUN-12
plus the "misleading success" flag are the proposed remedy, and they need
`--audit`.

**Q5. Does the critic influence behaviour?** Only through the opt-in
follow-up. `investigation.critique` records the verdict and nothing reads it
(`critique` docstring; `tests/test_agent_investigation.py::test_critic_answer_is_recorded_and_changes_nothing`).
With `CRITIC_FOLLOWUP=on`, `recheck` makes at most one reading where the
critic pointed; the agent's own policy then interprets it. The verdict,
`favoured_confidence` and `supports_action` never gate the conclusion or the
action. Live: in the 2026-10-30 runs the critic said object on 9 of 10
cases including when the agent was right (PROGRESS note F3), and in the
run-2 challenge it agreed with the wrong transient conclusion at 90%
(RUN2 finding 2, now the blind critic). No run on record shows the critic
changing an outcome. (A1)

**Q6. Does the agent use manual evidence or merely retrieve it?** The
records say only how many searches were made and which sections came back
(`evaluation/manual.py::build_manual_records`); nothing computes whether a
manual section was cited. The one manual-on run before the manual step
(2026-10-27 B) made 0 searches in 3 cases. Since `MANUAL_STEP` defaults on,
every run retrieves sections before planning, so "retrieved" is now
guaranteed and uninformative. The packet adds `cited_by_origin` from the
audit log; RUN-04 judges usefulness. (A3)

**Q7. Does the agent verify a remedy with observable evidence?** The code
makes it hard not to: `verify` accepts resolved / not_resolved only when the
cited evidence is observable, observed after the work and with a data
window after the work (22 tests). But whether the verdict is right is not
compared with the truth anywhere. `ExperimentRecord.verification` and
`Score.resolved` sit side by side in every record and no report joins
them. The packet's `verification_calibration` does: master-single shows 3
true_resolved (KA-02 fixed; KA-07 and KA-08 watched), 1 true_unresolved
(KA-09), 5 no verdict. (E5)

**Q8. Can the agent diagnose confidently on insufficient evidence?** Yes
for no_action and escalate. `MIN_ACTION_CONFIDENCE` gates only intervene
(`check_conclusion`). `diagnosis_supported` gates only the loop's own stop;
a policy stop (`evidence_sufficient`) ends research at any confidence and
`conclude` accepts any confidence. The compound case shows it: three runs
concluded a harmless glitch on CNC-03 at up to 0.95 without reading CNC-07
(PROGRESS F4). The F4 fix is a prompt sentence; no code checks that other
machines were examined. The packet's `machines_examined` (needs the audit
log) and RUN-06/RUN-09/RUN-10 are the measurements. (A2, A4)

**Q9. Are failures and timeouts represented accurately?** In the text
report yes: each run line carries `stop=<reason>` and the model-failure
lines. In the JSON `EvalReport` no: `EvalCase` has no termination reason,
so the 5 timeouts of master-single-2026-10-27 (KA-03 to KA-06, KA-09) appear
only as `correct = false` or `None`. `model_unavailable` runs are excluded
from the totals and counted apart (documented, tested). A timed-out run
still produces a conclusion in its reserved follow-up time, so it is
scored like any other; that is defensible, but a reader of the JSON cannot
see it. (R3)

**Q10. Which measurements can improve while reliability worsens?**

| Measurement | How it improves while the system gets worse |
|---|---|
| right recommendations, appropriate interventions | an agent that never acts is right on every no-action case |
| unnecessary interventions = 0 | same |
| accuracy when committed | abstain on every hard case |
| resolved | wait longer: false alarms and batches clear by themselves |
| relevant evidence share | read every relevant sensor for one tick each |
| mean tool calls, wall seconds | stop early and escalate |
| reasoning misses down, evidence misses up | collect less (the miss kind flips, the diagnosis stays wrong) |
| critic objections | object to everything |

Every one of these is reported today without the guard that would catch
it. The rubric therefore reports each beside its guard (abstention rate,
confident-wrong, false interventions, `causes_resolved` for repair-needing
faults, machines examined, RUN-01).

## 3. Findings

### Records and reports

- **R1. The saved record is evidence-free.** `experiment.record_of` keeps
  the conclusion, scores, tool names and counts, but not the evidence
  contents, the hypotheses, the decision arguments or the critic's text.
  Those exist only in the audit log (`agent/completion.AuditRecord`,
  written with `--audit`). The nine master-single packets are
  `record_only`; even `machines_examined` is empty because the record has
  no tool arguments. No run on record can be judged for evidence quality.
  Fix: run `evals` with `--audit` always (a one-line default), or keep the
  audit file beside every results file.
- **R2. Provenance of a run is incomplete.** Neither `ExperimentRecord` nor
  `EvalReport` holds the commit, the `.env` settings beyond
  `step_questions` and `state_action_bar`, the budgets or the manual
  revision; `check_resume` compares run key, scenario, seed and fault only
  (walkthrough note, PROGRESS 2026-10-28). The run-2 files mix
  configurations (RUN2 finding 6). The 2026-10-27 master report does not
  say which commit it ran on.
- **R3. The JSON report hides stop reasons** (Q9).
- **R4. Labels are drafted next to the truth.** The results file holds
  `score.true_fault`; six of the nine master labels were drafted by the
  coding assistant from a file it could read whole, then shown to the
  developer (`2026-10-27-master-labels.jsonl` notes). The process rule
  ("by the conclusion's words") is stated, not enforced. Fix: label from a
  file that holds run keys and conclusions only (`auto_label.conclusions`
  already reads only those two fields; a `label` command that reads the
  same projection would close it).

### Evaluator and scoring

- **E1. Accuracy rests on hand labels with no measured agreement.** Two
  labellers, no inter-rater figure; `auto_label.agreement` exists but the
  Jev comparison was never run (MVP_SCOPE "finish the check on Jev's
  labels"). `--auto-label` would put unvalidated labels into accuracy for
  every proposal not marked for review.
- **E2. Recommendation and action credit for doing nothing** (Q3).
- **E3. Evidence share counts any window.** `faults.Relevant.met_by`
  checks tool name, sensor and machine, never the tick range or the sample
  count. A one-tick `get_readings` on the right machine counts as "vibration
  of CNC-05 collected". `miss_kind` inherits it: a run that glanced at
  everything is a reasoning miss. Fix: require a window covering the fault's
  start or a minimum sample count, computed from the audit log; keep the old
  figure under its old name.
- **E4. Resolution credits faults that clear by themselves.** `_resolved`
  returns true for a false alarm once the offset is zero and for a batch
  once the line moved on. `resolved` in master-single: 4 of 9, of which 1
  (KA-02) was the agent's doing. `causes_resolved` on repair-needing faults
  is the honest figure; the compound and forced-only cases already use it.
- **E5. Verification verdict never compared with the truth** (Q7).
- **E6. The abstention card's `confident_wrong` uses the final
  confidence** (`record.confidence`), which for a lowered intervention is
  the model's confidence in a conclusion the check already demoted. Minor;
  the packet reports `policy_recommendation` and `recommendation_lowered`
  beside it.
- **E7. Summary denominators differ on one line.** `format_summary` divides
  root causes by judged runs and recommendations by scored runs. Readable
  only with the "(n not judged)" suffix; the rubric states every
  denominator.
- **E8 (well designed).** Scoring is pure, deterministic and stable in time
  (`tests/test_scoring_integrity.py`), runs without a model are excluded
  from reasoning totals, an unlabelled run is unjudged rather than wrong,
  partial credit on compound runs is explicit, and the "no fix asked for"
  of 2026-10-26 was found because `recommendation_correct` and
  `policy_recommendation` were recorded. The evaluator's defects are of
  interpretation, not of mechanics.

### Agent behaviour

- **A1. The critic is unmeasured and ungated** (Q5). `verdict_mismatch`
  does not flag `no_objection` beside a contradiction or alternative
  objection (RUN2 finding 5). `recheck` may end `already_answered` on the
  policy's own say-so (record text: "semantic adequacy is unverified").
- **A2. Confidence is checked only for interventions** (Q8).
- **A3. Manual use is not measured** (Q6).
- **A4. The scan rule is prose only** (Q8).
- **A5. Memory has never run live.** The comparison command exists
  (`memory_comparison.py`), fairness fixes were built (C3c), nothing was
  measured. The MVP claim of persistent learning is undemonstrated.
- **A6 (well designed).** Budgets, repeats, provenance, the supported-
  diagnosis gate, the fixed procedure after the conclusion and the
  verification rules are enforced by the loop, not the policy, and the
  tests prove each one (`curated/function_notes.json`: 43 VERIFIED).

### Leakage boundary

- **L1 (well designed).** Five independent guards: the key-set test over a
  full run (`test_observation_tools`), the import-graph rule
  (`test_agent_artifacts`), provenance written by the loop
  (`test_agent_provenance`), the manual leak check (`manual/sections.py`)
  and the memory gate's hidden-truth scan (`memory/policy.py`). The
  critic's view reads only anomaly, evidence and hypotheses
  (`critique_view`). The watch view prints no truth
  (`tests/test_experiment.py::test_watching_shows_each_case_live_but_never_the_truth`).
- **L2. Residual risks are procedural**, not in code: the results and label
  files hold truth and conclusion together (R4); `evals/scenarios.json`
  names each case's fault and sits beside the config a run reads (by
  design, evaluator-side); `progress.watch_episode` prints `truth_lines`
  for a person, which must never be piped into a label session.
- **L3. Prose leaks are tested where they were thought of**: no event
  message names the cause (`test_ground_truth`), no manual section gives a
  standard speed or job time (`test_manual`), no prompt lists the causes
  (`test_model_policy`). A judge question (TL-01) covers paths not yet
  thought of.

### Tests

- **T1. Numbers.** 602 project functions (24 protocol stubs or abstract
  definitions). 557 executed by at least one test, 369 by a direct test. 18
  never executed: the command-line `main`s of `baseline`, `manual.index`,
  `memory.backfill`, `duplicate_threshold`, the console approver, and the
  live-only paths `evals.automatic_labels`, `experiment.open_memory`,
  `manual.index.ready_manual_index` / `open_manual_index`,
  `memory.semantic.default_embedder`, `memory_comparison.open_store_and_index`,
  two nested helpers of `evals.main`, and three trivial properties. 3
  executed only at import. 20 executed with under 80 percent of their
  statements (`VERIFICATION_MATRIX.json` `counts`), among them `evals.main`
  (28 of 60) and `memory_comparison.main` (25 of 37). 1,357 test functions
  (1,708 cases), all passed on the reviewed commit. The live model path
  (`clients_for_jobs` through a real transport) is, correctly, never
  executed offline.
- **T2. Scripted episodes prove plumbing, not reasoning.** The known-answer
  suite's stand-in always answers "undetermined"
  (`tests/test_known_answers.py::stand_in`); `test_model_policy.py::test_a_whole_episode_runs_on_model_replies_alone`
  feeds canned JSON. They prove the stages, budgets and records; a reader
  must not take "13 cases pass" as diagnostic ability.
- **T3. Heuristic flags.** 49 tests assert only truthiness or not-None; on
  review 3 of the 6 read were WEAK (a broken `_resolved` for wrong settings
  could pass `test_a_reset_resolves_a_wrong_setting`) and the rest adequate
  for their claim. 95 tests exercise no project function: import rules,
  prompt text rules, backward-compatibility of records, data-model limits.
  They are legitimate but they inflate "tests per module" if counted as
  behaviour. 97 patch dependencies (monkeypatch or mock); 14 may skip
  (database and Chroma extras).
- **T4. A real evaluator defect went unnoticed.** Until PR #149,
  `scoring._resolved` had no branch for servo or hydraulic faults and fell
  through to the false-alarm check, so an unrepaired servo fault scored
  "resolved" (PROGRESS, EV2 note). No test caught it because no case
  exercised those faults. The known cases now pin it, and the lesson is
  general: the evaluator needs deliberately wrong inputs (known-bad
  fixtures) as much as the agent does.
- **T5 (well designed).** Failure paths are tested where it matters most:
  the loop (invalid decisions, bad answers, timeouts versus outages), the
  provider (every error class without detail), the approval desk (every
  way round the human), verification (every way to fake a result), the
  memory gate (every refusal reason). The `# Variables:` blocks give most
  functions a stated contract (`contract_specified` in the inventory).

### Experiments

- **X1. No two batches on record are comparable.** 2026-10-26 (e65bd8f,
  bar 0.9 unstated, two questions per step, no manual), 2026-10-27 master
  (commit unrecorded, bar stated, two questions, no manual, resumed at
  KA-04), the bar-0.80 pair (25f0df0, three seeds), the 2026-10-30 critic
  runs and the run-2 arms (mixed configurations, resumed across changes)
  differ in commit, settings, cases and label sources. `compare_reports`
  checks scenario sets only. No improvement or regression can be asserted
  from them.
- **X2. One run per case.** The same seed gave opposite conclusions on
  consecutive days (seed 6: escalate 0.75 then no_action 0.85, PROGRESS
  2026-10-27). Without repeats, a one-case difference is noise.
- **X3. No cost accounting.** Records hold question counts, attempts and
  seconds, not tokens; `Judgments.input_tokens` exists for Jev only. "API
  cost" cannot be reported from the records.
- **X4. Held-out seeds never run.** `HELD_OUT_SEEDS` (1000-1009) exist with
  the right discipline and have never been used for a reported number.
- **X5. What is consistent across all runs** (observed, not a comparison):
  bearing and false-alarm cases are diagnosed right often; batch and
  setting cases have never been labelled right in any live run on record;
  KA-09 has been called a transient in every run; fixes are rarely asked
  for (0 of 9 on 2026-10-26, 1 of 9 on 2026-10-27). These are findings
  about the agent, repeatable enough to act on, and they say nothing about
  which change helped.

### Snap integration

- **S1. API shapes second-hand.** Neither docs.subq.ai nor
  docs.typesafe.ai resolved; the request shape follows the quickstart as
  quoted by search results and two open-source clients, and matches the
  TypeSafe System One client already in the repository
  (`providers/typesafe.py`). The score-level key and Jev's
  questions-per-request limit are marked to confirm
  (`DECISION_MODEL_COMPARISON.md` section 1). No request was sent.
- **S2. Scope.** SubQ is not an agent provider (AGENTS.md section 9) and
  TypeSafe is in scope for the evaluator only. The request builder lives
  outside `capstone`, adds no setting, dependency or default, and reads
  each key from the environment of the person who sends. The developer
  should confirm this reading before any live request.
- **S3. Two judges.** Snap and Jev are run as independent evaluators on
  the same fitted evidence; the report measures agreement and lists
  disagreements for review, and the reference set decides who was right.
  Whether the second judge earns its keep is decided per question family
  after the first traced batch (`DECISION_MODEL_COMPARISON.md` sections
  5 and 6).

## 4. The challenge scenarios (Phase 4)

| Risk | Detected today? | By what | Added here |
|---|---|---|---|
| Correct cause through unsupported reasoning | no | labels read words only | RUN-01, RUN-08, RUN-12; "misleading success" flag (needs `--audit`) |
| Incorrect diagnosis marked successful | partly | accuracy no; right-recommendation and resolved lines yes (E2, E4) | denominators and guards in the rubric; `fully_right` reported first |
| Critic finds a weakness, feedback ignored | partly | `recheck.outcome` records skipped / policy_stopped | RUN-03, RUN-11 |
| Manual retrieved, never used | no | search counts only | `cited_by_origin`, RUN-04 |
| Episodic recall misleading | partly | `memory_uses.used` by citation; "recalled lesson from a wrong diagnosis" line | RUN-04 covers memory origin too; live memory run needed |
| Ground truth leaks into the agent | yes | five guards (L1) | TL-01 for prose paths |
| Verification reports success without confirming | partly | `verify` refuses pre-work evidence; the verdict is unchecked | `verification_calibration`, RUN-05 |
| Failed or timed-out runs vanish from aggregates | partly | text report shows stops; JSON does not (R3) | `facts.finished_on_time`, `timeouts` in the batch summary |
| A tool silently returns invalid values | partly | `run_tool` rebuilds answers from contracts; hazards are designed and reported | TL-03; `failed_tool_calls`, `repeated_calls` |
| Overconfident diagnosis on insufficient evidence | partly | `confident_wrong` needs a label; the bar gates only intervene | RUN-06, RUN-09, RUN-10, `machines_examined` |

## 5. Comparing the experiments on record (Phase 6)

Not valid as comparisons (X1). What the records support:

| Claim | Status |
|---|---|
| Root-cause accuracy improved between 2026-10-26 (5/8) and 2026-10-27 (3/9) | insufficient sample and different conditions; the drop is within one-run noise and the label rule changed between them (three 10-26 labels were relabelled) |
| The manual helps | not measured: 0 searches in the only manual-on run before the manual step |
| The critic helps | not measured: no matched critic-off/critic-on batch with one frozen configuration; run-2 has one confirmed right case per arm |
| One question per step is faster | plausible from question counts (23-35 per case at two) but no matched batch |
| Batch and setting faults are a persistent weakness | observed in every live run on record (X5) |

## 6. Validating the judge (Phase 7)

Not done; designed in `EVALUATION_RUBRIC.md` section 8. The reference set
should start with KA-02 of master-single-2026-10-27 (right, intervened,
verified) and KA-09 (confident, wrong, false intervention), both of which
need an audit log that the saved run does not have, so the reference set
must come from the next traced run. One deliberately broken packet
(citations pointing at unrelated readings) is specified so that a judge
that praises it is caught.

## 7. Recommendations, in order

1. Run `evals` with `--audit` by default and record commit, settings and
   manual revision in `EvalReport` (R1, R2, R3). Deterministic, small,
   unblocks every judge question.
2. Label from a projection file that holds run keys and conclusions only
   (R4, E1), and record inter-labeller agreement on the next batch.
3. Report the guards beside every flattering figure (E2, E4, E3): the
   rubric's batch table is the format; `evaltools.run_packet` computes it.
4. Add deterministic checks the records can carry: `verification_calibration`,
   `machines_examined`, `cited_by_origin`, a windowed evidence share.
5. Run the three experiments in `FINAL_REPORT.md` section 7 with one frozen
   configuration each, labels decided first, repeats where the budget
   allows.
6. Fill the reference set and record Snap's agreement before trusting any
   judge answer.
7. Add known-bad evaluator fixtures (a scorer that must fail on them) so
   that the next `_resolved`-style defect is caught (T4).
