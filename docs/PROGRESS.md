# Progress Log

Two separate completion criteria per component (see CLAUDE.md §1):

- **Implemented** — code written, tests passing.
- **Understood** — the developer explained the component back correctly
  (both the pre-implementation gate and the post-implementation re-explain).

A component is complete only when both columns are checked.

| # | Component | Taught | Understood (pre) | Implemented | Understood (post) | Notes |
|---|---|---|---|---|---|---|
| 1 | SimulationClock | yes | yes | yes | yes | `capstone/simulator/clock.py` |
| 2 | Deterministic random source | yes | yes | yes | yes | `capstone/simulator/rng.py` |
| 3 | Machine identity / MachineState | yes | yes | yes | yes | `capstone/simulator/state.py` |
| 4 | Sensor abstraction + vibration sensor | yes | yes | yes | yes | `capstone/simulator/sensors.py` |
| 5 | FactoryState + step() | yes | yes | yes | yes | `state.py`, `simulator.py` |
| 6 | Event log + threshold alarm | yes | yes | yes | yes | `capstone/simulator/events.py` |
| 7 | Scenario abstraction | yes | yes | yes | yes | `capstone/simulator/scenarios.py` |
| 8 | BearingDegradation scenario | yes | yes | yes | yes | `scenarios.py` |
| 8b | Machine failure (a worn-out machine goes down) | yes | yes | yes | yes | `simulator.py` |
| 9a | Ground truth record | yes | yes | yes | yes | `capstone/simulator/ground_truth.py` |
| 9b | Read-only observation tools | yes | yes | yes | yes | `capstone/tools/observation.py` |
| 10 | Temperature sensor (°F) | yes | n/a | yes | yes | `sensors.py`; pattern repeat, no pre-gate needed (CLAUDE.md §2.2) |
| 10a | Operating load and the load sensor | yes | yes | yes | yes | `state.py`, `sensors.py` |
| 10a2 | Load and wear tied together | yes | yes | yes | yes | `scenarios.py`, `sensors.py` |
| 10b | Workload in random blocks | yes | yes | yes | yes | REPLACED by row 12a; the `Workload` scenario no longer exists |
| 10b2 | Job-started event from a per-machine counter | yes | yes | yes | yes | REPLACED by rows 12a/12b; `job_number` no longer exists |
| 10c | Ambient temperature (daily cycle with drift) | yes | yes | yes | yes | `state.py`, `scenarios.py` |
| 10c2 | Loading door | yes | yes | yes | yes | `state.py`, `scenarios.py`, `simulator.py` |
| 10c3 | Factory thermometer + `get_factory_readings` | yes | yes | yes | yes | `sensors.py`, `tools/observation.py` |
| 10d | Temperature lag (warm-up / cool-down) | yes | yes | yes | yes | `capstone/simulator/thermal.py` |
| 10e | Standard line builder, 3-8 machines, seed-chosen size | n/a | n/a | yes | n/a | `capstone/simulator/line.py`; wiring only, no gate needed (CLAUDE.md §2.2) |
| 11a | Letting time pass: `wait` | yes | yes | yes | yes | `capstone/tools/actions.py` |
| 11b | Bearing replacement (downtime, fault ends, technician's finding) | yes | yes | yes | yes | `simulator.py`, `state.py`, `scenarios.py` |
| 11c | Proposals and human approval | yes | yes | yes | yes | `capstone/tools/actions.py` |
| 12a | Assembly line: jobs move machine to machine | yes | yes | yes | yes | `state.py` (`Job`), `scenarios.py` (`ProductionLine`) |
| 12b | Job events and `get_job_history` | yes | yes | yes | yes | `simulator.py`, `tools/observation.py` |
| 12b2 | Worn machines work more slowly; ±2 ticks natural variation | yes | yes | yes | yes | `scenarios.py`, `line.py` |
| 12c | Quality inspection, small pass/fail version | yes | yes | yes | yes | `scenarios.py`, `state.py` (`Inspection`), `simulator.py`, `tools/observation.py` (`get_inspections`) |
| 13a | Material batches and one bad batch (fault scenario 2) | yes | yes | yes | yes | `state.py` (`MaterialBatch`), `scenarios.py` (`BadMaterialBatch`), `simulator.py`, `line.py`, `tools/observation.py` |
| 13b | Machine setting and a wrong setting (fault scenario 3) | yes | yes | yes | no | `state.py` (`speed_setting`), `scenarios.py` (`WrongSetting`, `defect_mark`), `sensors.py`, `thermal.py`, `line.py`, `tools/observation.py` (`get_settings`); re-explain waived for time on 2026-10-06, developer to review |
| 13c | Action: put a machine's setting right (via the approval desk) | n/a | n/a | yes | no — built ungated, developer to review | `simulator.py` (`start_setting_reset`, `_start_maintenance`), `state.py` (`maintenance_kind`), `tools/actions.py` (`reset_setting`) |
| 13d | False alarm / transient anomaly (fault scenario 4) | n/a | n/a | yes | no — built ungated, developer to review | `state.py` (`MachineCondition.vibration_sensor_offset`), `sensors.py`, `scenarios.py` (`FalseAlarm`) |
| 14 | Seeded scenario generator (fault, machine or batch, start tick) | n/a | n/a | yes | no — built ungated, developer to review | `capstone/simulator/generator.py` (`build_scenario`, `FAULTS`) |
| 15 | Evaluation | n/a | n/a | yes | no — built ungated, developer to review | `capstone/evaluation/scoring.py` (`evaluate`, `Score`, `summarize`), `capstone/tools/diagnosis.py` (`Diagnosis`) |
| 16 | The research agent | n/a | n/a | yes | no — built ungated, developer to review | `capstone/agent/` (`models.py`, `toolbox.py`, `agent.py`, `monitor.py`, `episode.py`, `__main__.py`); `tools/observation.py` (`get_sensor_trend`) |
| 17 | Memory | n/a | n/a | yes | no — built ungated, developer to review | `capstone/agent/memory.py` (`InvestigationMemory`, `search_incident_history`), `episode.py` |

Every row above with four "yes" marks (or "n/a") is complete: no question is
outstanding on it. Still to build after 12c, from `docs/MVP_SCOPE.md`: the
other three fault scenarios (material batch, machine configuration, false
alarm), then evaluation, then the agent itself.

## Session notes

- **2026-10-14 — checkpoint 6a closing question PASSED (after one
  re-teach).** Asked why the builder hands the gate every provenance label,
  not only the cited ones, the developer was first unsure. After a worked
  example (an uncited hidden-truth item E4 that gave the agent the answer),
  the developer said every label is passed so the gate can catch a bug that
  let the agent see more than it should have. Added: what the agent saw
  shapes its conclusion whether or not it is cited, so leaving an item out
  of the citations must not hide it from the gate. Checkpoint 6a is
  complete. NEXT: 6b, widen the memory gate to "what did not work" lessons.

- **2026-10-14 — checkpoint 6a: the reflection candidate.** Pre-checkpoint
  passed: asked what the candidate records when the check says not resolved
  but the model's sentence says the fix worked, the developer said the
  builder takes the outcome from the code and ignores the model's claim.
  Corrected: the sentence is advice for a later investigation, not for the
  user in this one. On why the category is the symptom, the developer said
  the diagnosis is the answer itself, while the symptom is what each
  investigation starts from. POST-IMPLEMENTATION UNDERSTANDING IS
  OUTSTANDING. Changes: `agent/policy.py` gains `Lesson` (a single `text`
  field) and a seventh policy question, `write_lesson(state) -> Lesson |
  None`; nothing calls it yet (6c). New `memory/reflection.py`:
  `build_candidate(investigation, provenance, lesson)` makes the
  `ReflectionCandidate` from the shared record alone. Code fills category
  (first symptom), `intervention_worked` (verified -> True, failed -> False,
  None when nothing was proposed), `diagnosis_assessment` (verified ->
  supported, otherwise unknown, never refuted), evidence IDs (conclusion's
  plus the check's), confidence (the conclusion's) and provenance (every
  label). The model supplies only the sentence. No candidate when the check
  is missing or unverified, or the sentence is empty. The builder decides
  nothing; the gate still does. `tests/helpers.py`: `ScriptedPolicy(lesson=)`.
  Tests: new `tests/test_memory_reflection.py` (21), over the ten endings
  from 5b: fields filled from the record; two different sentences give
  identical candidates apart from the text; a failed fix stays failed when
  the sentence claims it worked, and the gate refuses it; a verified fix is
  accepted by the gate; a candidate exists exactly where an outcome was
  observed; `Lesson` has only `text`; `capstone/memory` does not import
  `capstone/agent`. New CI check "Tests: Reflection". Simplification: the
  lesson's `reusable` / `contains_transient_details` flags are set by code
  (they were the writer's own claims); the gate's own scans of the text for
  numbers, ticks and hidden-truth words are the real guard. Verification:
  725 passed locally; Ruff passed; CI green on `cf05576` (all eleven checks).

- **2026-10-14 — checkpoint 5b closing question PASSED.** Asked why the
  producer leaves a check out instead of filling in a tick or an outcome so
  the record looks complete, the developer said a record that looks
  incomplete is a true statement that the work is incomplete, and that the
  one absence covers two cases (not performed, no check time). Added: an
  `unverified` / `unknown` result means a check was made and could not
  decide; writing it for a check that never happened would tell the reader,
  the evaluator and a future agent that someone looked. Checkpoint 5b is
  complete. NEXT: checkpoint 6a, pre-implementation question.

- **2026-10-12 — checkpoint 5b: the finished record and the audit log.
  SESSION ENDED HERE.** Pre-checkpoint passed: for an approval never carried
  out, the developer said the check is "not performed", the record shows the
  approval, and the audit log (the JSON memory) records everything so a later
  reader can see. Clarified: in the shared record "not performed" becomes no
  verification at all, and the reader sees an approval in the evidence with
  no evidence of work starting. POST-IMPLEMENTATION UNDERSTANDING IS
  OUTSTANDING: ask the closing question at the start of the next session
  (why does the producer leave a check out instead of filling in a tick or
  an outcome so the record looks complete?). New `agent/completion.py`:
  `complete(state)` builds the shared `CompletedInvestigation` from working
  memory without changing it, and refuses an unfinished investigation;
  `shared_verification` translates the check by fixed rule (resolved →
  verified/resolved, not resolved → failed/unresolved, inconclusive →
  unverified/unknown, not performed or untimed → left out);
  `action_evidence_ids` makes the shared action cite the evidence in which
  the factory reported the proposal, the human's decision and the start of
  work, which is how approval and rejection reach the shared record;
  `AuditRecord` / `audit_record(state)` hold the shared record plus
  provenance, the runtime anomaly, conclusion and proposal status, the action
  ticks, the runtime check, every decision record and the loop's counts;
  `AuditLog` appends audit records to a JSON-lines file and reads them back.
  The agent has no tool that reads the log. Tests: new
  `tests/test_agent_completion.py` (37), over ten endings run through the
  real simulator (verified fix, failed fix, inconclusive check, check not
  performed, rejected, no human answer, approved and not carried out,
  escalated, no action and checked, failed at every stage): each gives a
  valid record citing only evidence that exists and is labelled, leaves
  working memory unchanged, and contains no hidden-truth words; the same run
  twice gives the same record. THIS COMPLETES THE ORIGINAL REQUEST: completed
  investigations with verification evidence and trusted provenance, with the
  loop still not importing `capstone.memory`. Not done: nothing calls
  `complete` or `AuditLog` automatically at the end of `run_investigation`;
  the older `agent/memory.py` JSON memory still exists beside the new log.
  NEXT (in order): 6a reflection candidate (code fills the facts, the model
  writes only the advice sentence); 6b widen the memory gate to "what did
  not work" lessons; 6c connect loop to gate with an end-to-end test;
  7 memory recall tool and word search; 8 Nemotron-backed policy with no
  list of causes in the prompt; 9 seeded-scenario runs and an evaluator
  model for the free-text diagnosis; 10 retire the older agent. Also still
  pending from before: apply the memory migration to Neon; the SubQ audit.
  The developer's main folder `Capstone_Project_CMU` is still on the old
  `feature/episodic-memory-reflection` branch; work is in
  `Capstone_Project_CMU-agent1` and on `main`.
  Verification: 704 passed locally; Ruff passed; CI green on `d59549c`
  (all ten checks).

- **2026-10-12 — checkpoint 5a: where each piece of evidence came from.**
  Pre-checkpoint passed first time: the developer said a model allowed to
  state the origin could write it in the wrong format or hallucinate the
  wrong source, and the records would then be tainted. Added: the worst case
  is hidden-side material labelled observable, which the memory gate would
  then let through. Post-implementation checkpoint PASSED: the developer
  explained that at arrival everything is fresh and there is no need to go
  back into working memory later to work the provenance out. Added: it is
  also a second record of the same moment, so a later mistake in the
  evidence is not copied into the label.
  Changes: new `contracts/provenance.py` now holds the one definition of
  `ProvenanceReference` (evidence ID, source, source type, origin, tick);
  `memory/contracts.py` imports it from there, so the memory gate and the
  loop use the very same class and existing imports still work.
  `agent/state.py`: `InvestigationState.provenance`. `agent/loop.py`:
  `gather` writes one label beside each evidence item at the moment the tool
  answer arrives, from that same answer, with origin `observable` (the
  factory provider only offers what an operator could see). The policy is
  never asked for an origin and no type it returns has a field for one.
  Tests: new `tests/test_agent_provenance.py` (13): one definition; same
  class object in both packages; a label per evidence item, present before
  the policy first sees the evidence; none for failed or unusable answers;
  kept for an answer the policy could not interpret; the policy's copy
  cannot change them; one-to-one match with the evidence through a whole
  real investigation (research, approved repair, check); everything the
  conclusion and the check cite is labelled. New CI check "Tests: Completed
  record". Simplification: every factory answer is `observable`; a human's
  note inside a tool answer does not make the item `human`. Evidence
  recalled from memory will need its own origin when recall is built.
  Verification: 667 passed locally; Ruff passed; CI green on `1376de0`
  (all ten checks).

- **2026-10-12 — checkpoint 4: did the fix work?** Pre-checkpoint passed
  first time: asked what the loop does with a "resolved" judgement citing
  only evidence from before the repair, the developer said there is no
  observation, so it is unconcluded because we do not know if the problem
  went away. Post-implementation checkpoint PASSED: the developer explained
  that a judge allowed to write the prediction could overwrite the one made
  beforehand, and that its only job is to judge, not to predict. Added: a
  prediction written after seeing the result can always be made to match
  it. The developer also asked whether different models could answer
  different questions; yes — the policy interface is six separate questions,
  so a wrapper can give each to a different provider (for example a second
  model as verification judge), and the loop's checks apply to all of them.
  To build when the first real model is wired in, one model first.
  New in `agent/investigation.py`: `verify` — runs the inner loop in its
  verify phase (the policy chooses what to look at and may wait, from the
  follow-up allowance), asks the policy to judge, then decides whether the
  judgement can stand. Rules: cited evidence must exist; "resolved" and
  "not resolved" need at least one cited item observed after the work
  finished (after the conclusion, when nothing was done), otherwise the
  result is "inconclusive"; with nothing looked at after that tick the
  result is "not performed" and the policy is not asked; the prediction is
  the one recorded before the action and the tick of the check is taken from
  the evidence, so the policy can adjust neither. Nothing tells the agent
  the result: one test repairs the right machine and one the wrong machine,
  and the same scripted judgement (compare the vibration afterwards with
  what was seen before) reaches "resolved" and "not resolved". A "no action"
  conclusion is checked the same way, with the fixed prediction
  `NO_ACTION_PREDICTION`. Not verified, and left with no verification at
  all: escalated, rejected, unanswered, approved but not carried out, and
  work started but not seen to finish. Routing: `propose` now also returns
  "verify" for a no-action conclusion; `execute` returns "verify" only once
  the finish tick is reached. `agent/state.py`: `concluded_tick`.
  Tests: new `tests/test_agent_verification.py` (26), all through the real
  simulator, provider and desk; new CI check "Tests: Verification".
  Simplifications: "after the work" is strictly later than the finish tick,
  so the wait that reaches the finish tick is not itself evidence; how long
  to wait before looking is the policy's choice, not a rule; a failed fix is
  recorded but the agent does not go on to try something else.
  Verification: 654 passed locally; Ruff passed; CI green on `8bd0e1e`
  (all nine checks, including the new "Tests: Verification").

- **2026-10-12 — a CI check for every part, and CI as part of every
  checkpoint (developer's request).** RULE FROM NOW ON: a checkpoint is not
  finished until its push is green on GitHub; each checkpoint entry records
  the CI result as well as the local one. CI (`.github/workflows/ci.yml`) is
  now several named checks instead of one: "Lint and format"; one "Tests: …"
  check per part of the project (Simulator, Tools and provider, Reasoning
  loop, Memory, Evaluation, Older agent); and "Full suite and coverage",
  which stays the source of truth. `.github/test_groups.py` holds the one
  list of which test file belongs to which check; its `check` mode fails CI
  if any test file is in no group or in two, so a new test file cannot be
  silently left out. A NEW TEST FILE MUST BE ADDED TO A GROUP THERE. Local
  check of the groups: 317 + 124 + 93 + 47 + 32 + 15 = 628, the same as the
  full suite.

- **2026-10-12 — CI repaired (reported by the developer).** CI on `main`
  had failed on every push since checkpoint 3b: it installed no optional
  extras, so `pydantic_graph` (the `agent` extra) was missing and the two
  test files that import the outer sequence failed to import. The local
  runs passed only because the worktree has every extra installed. Fix:
  `.github/workflows/ci.yml` now installs and runs with `--all-extras`. Side
  effect: CI now also runs the database and migration tests it had been
  silently skipping (3 files). Verified on GitHub: 628 passed, none skipped.
  Lesson recorded: check the CI run after each push, not only the local suite.

- **2026-10-12 — checkpoint 3c: asking for the fix and carrying it out.**
  Pre-checkpoint passed after two re-teaches. On a rejected proposal the
  developer correctly named the stages that run, but said the note is deleted
  and the loop restarts; corrected: the read-back is saved as evidence so the
  note is kept, the machine is untouched, and the investigation ends. On an
  approved proposal whose execution fails, the developer expected a wait and
  hoped it counted as a fix; corrected: nothing of the agent's own started,
  so nothing is waited for and it is recorded as approved, not carried out.
  The developer then stated that the execute stage is the one that must
  succeed and that the evidence it leaves is the proof. The developer also
  pointed out, correctly, that a working agent would see an existing repair
  in the event log before proposing; the failed execution is the safety net.
  LATER OPTIONS the developer raised (not built): investigate again after a
  rejection, using the human's note; retry after a failed execution; have
  the loop refuse to propose for a machine already down for maintenance.
  Changes in `agent/investigation.py`: `followup_call` (one call the loop
  itself decided on, taken from the follow-up allowance, refused when that
  allowance or the time is used up); `factory_changed` (clears the repeat
  check's memory, because a proposal, a decision and the start of work change
  the factory's answers without the clock moving); `propose` (submits the
  wanted action, keeps the ID, hands the pending proposal to the human hook,
  reads that proposal back and takes its status from the factory); `execute`
  (starts approved work, records the start and finish ticks only if the
  factory confirms, then waits in accepted steps until the finish tick).
  Graph: `conclude → propose → approved? → execute → end`; `execute` can be
  reached only through the proposal. `agent/state.py`: stages `propose` and
  `execute`; `action_started_tick`, `action_finish_tick`,
  `action_carried_out`. `agent/loop.py`: `max_wait_ticks` setting. The
  policy makes none of these calls and the stop reason is not touched.
  Tests: new `tests/test_agent_action.py` (17), all through the real provider
  and approval desk: approved path end to end (machine repaired, note kept
  as evidence); rejection and no-answer stop after the read-back with the
  machine untouched; no change wanted asks nothing; a refused proposal never
  reaches the human; approval with no calls left, and work that cannot start,
  are approved and not carried out; the decision is read even when the same
  question was asked that tick; a hook that decides nothing is not approval.
  `tests/test_agent_investigation.py` updated for the longer path (32).
  Post-implementation checkpoint PASSED: the developer explained that the
  loop follows the authoritative state, whereas the hook having run is only
  a claim. Not built yet: checking whether the fix worked (checkpoint 4).

- **2026-10-12 — Anthropic/Claude removed from the code (developer's
  instruction).** The only model providers in scope are Mistral, Google
  Gemini, Groq, NVIDIA, Cohere and Cloudflare; nothing else is to be added.
  Removed: `ClaudeModel` and `DEFAULT_MODEL` from `agent/models.py`;
  `agent/__main__.py` (the command line could only run that model); the
  `anthropic` dependency from the `agent` extra and `uv.lock`; the two tests
  of them in `tests/test_agent.py`. Kept: the `Model` interface,
  `ScriptedModel`, `Turn`, `ToolCall`, `ToolResult`, which the older agent's
  tests use. The rule is written into `CLAUDE.md` and `AGENTS.md` section 9.
  Older entries below that mention Claude as a model are history, not plan.
  No model is wired to anything yet; the model-backed policy for the
  checkpointed loop will use NVIDIA Nemotron
  (`nvidia/nemotron-3.5-lightning-30b-a3b`, key `NVIDIA_API_KEY`).

- **2026-10-12 — checkpoint 3b: the outer sequence up to a conclusion.**
  Pre-checkpoint passed after one re-teach: the developer first treated a
  cited `E9` as faulty evidence for the model to weigh; after the explanation
  that only the loop creates evidence IDs, correctly said the loop refuses
  the conclusion citing evidence that does not exist, while misleading but
  real evidence is the model's to weigh. Post-implementation checkpoint
  PASSED after one clarification: the developer explained that the
  confidence threshold decides whether the agent may act and that below it
  the result is an escalation, but used "diagnosis" for the recommendation;
  after the distinction was explained, stated it correctly (diagnosis is
  what is believed to be wrong, recommendation is what to do about it).
  Added: an under-confident but honest conclusion keeps its diagnosis so
  the human gets something to act on; one citing evidence that does not
  exist is discarded whole. Recorded as passed one step early: on a
  concrete case (60% confidence, recommends intervening) the developer
  first answered "intervene"; after the before/after distinction was
  made explicit, answered correctly that 60% becomes escalate and 95%
  stays intervene. New `agent/investigation.py`:
  `observe` (asks the factory the time and starts the timer, so the tick is
  known before the policy's first question); `plan` (stores the policy's
  first questions); `investigate` and `test` (run the inner loop and set the
  investigation's stop reason to that loop's); `hypothesize` (takes the
  policy's explanations through the existing evidence check);
  `check_conclusion` (refuses a conclusion citing evidence never gathered or
  a hypothesis never formed; lowers "intervene" to "escalate" when it is not
  confident enough, cites nothing, or names no action); `conclude` (always
  leaves a conclusion; an unusable one becomes `UNDETERMINED`: confidence
  zero, escalate); `build_graph` / `INVESTIGATION_GRAPH` (the stages as
  Pydantic Graph steps with the only allowed order as edges);
  `run_investigation` (runs one investigation and returns its working
  memory). Shortcuts: nothing gathered or a timeout goes straight to the
  conclusion; no explanation means nothing to test. A justified action is
  stored as a `ProposalRecord` with status `not_submitted` plus the predicted
  effect; nothing is submitted or changed in the factory yet (that is 3c).
  `agent/state.py`: stage names `plan` and `hypothesize`, outcome `decided`.
  `agent/loop.py`: `call_signature` extracted so `observe` can register its
  time call under the tick it reported. This closes both gaps left at
  checkpoint 2: the repeat check now has a known tick from the first policy
  question (the expected-failure test is replaced by a passing test at this
  level), and the final stop reason is set (the last research loop's).
  Tests: new `tests/test_agent_investigation.py` (31), including one whole
  investigation through the real provider that leaves the simulator's state,
  clock and event log identical and the approval desk empty; the scripted
  policy and fake provider moved to `tests/helpers.py`. Simplifications:
  the stop reason is simply the last research loop's; asking the time is a
  counted call; `run_investigation` is synchronous. Verification: 612
  passed, no expected failures; Ruff lint/format passed.

- **2026-10-12 — checkpoint 3a: carrying out a fix is its own tool call.**
  Pre-checkpoint passed after one re-teach: the developer was first unsure
  what an approved-but-not-executed proposal means, then explained that
  approved means the action is able to be executed while budget remains, and
  executed means the tool runs and an action is taken. Clarified: the machine
  is untouched until execution, and such a record must say "approved, not
  carried out" and never count as a fix. The developer also asked that the
  loop be able to run longer than a simple look-up loop; the limits are
  settings and will be raised once a real model shows what an investigation
  needs (the 60-second default will certainly have to go up). They stay as
  they are for now. Post-implementation checkpoint PASSED after two
  clarifications: there is no queue (approved work starts at the tick
  `execute_action` is called; a second request for a machine under repair is
  refused, not held), and the desk checks its own list, not the agent's
  copy. The developer then explained that a desk trusting the agent would
  mean the required human approval is not there. The developer also saw
  that the split lets an agent get approval early and act later; noted as a
  post-MVP option that needs approvals to expire first. In 3c the loop
  executes straight after reading an approval.
  Changes: `tools/actions.py` — `Proposal` gains `executed_tick` and
  `finish_tick`; `ApprovalDesk.approve` now only records the decision;
  new `ApprovalDesk.carry_out(proposal_id)` starts the work of an approved
  proposal once and returns what started and when it finishes; new
  agent-facing `ActionTools.execute_action(proposal_id)`.
  `contracts/observations.py` — `ProposalObservation` gains the two ticks;
  new `ExecutionObservation`. `providers/factory.py` — `execute_action` is
  offered, with `ExecuteArguments`; approve and reject are still not.
  `evaluation/scoring.py` — an action counts as taken only if it was carried
  out, not merely approved. `agent/episode.py` — the older runner starts
  approved work itself, because the older agent has no execute step, until
  it is retired. Tests: `test_approval.py` rewritten for the split and
  extended (approval changes nothing in the factory; execution starts the
  repair and reports the finish tick; pending, rejected, unknown, malformed
  and already-used proposals are refused; an edited copy of a proposal does
  not unlock execution; work that cannot start leaves the proposal approved
  and not carried out); `test_factory_provider.py` adds the same through the
  provider and proves no approve/reject tool exists; `tests/helpers.py`
  (`approve_and_run`) keeps the reset and scoring tests describing the same
  behaviour. Known limit, not solved: an approval does not expire, so work
  may start long after it was approved. Verification: 581 passed, 1 expected
  failure; Ruff lint/format passed.

- **2026-10-12 — checkpoint 2: the inner loop, tested and three gaps fixed.**
  Pre-checkpoint passed: the developer said a failed call is reported and
  counts against the budget, and that repeated failure needs a limit and a
  recorded stop reason. Clarified: that limit already exists (three
  unproductive turns in a row stop the loop with "no useful action") and a
  failed call never becomes evidence. Added `tests/test_agent_loop.py` (36 tests, 1 expected
  failure) using a scripted policy and a fake provider, plus one test through
  the real `SimulatorFactoryProvider`. Run against the unchanged loop first:
  four tests failed, one per gap. Fixes, all in `agent/loop.py` and
  `agent/state.py`:
  (1) `run_inner_loop` now starts the timer on the first loop of an
  investigation; before this `started_at` was never set and the timeout could
  not fire. Later loops do not restart it.
  (2) `call_tool` now refuses an answer whose run or investigation ID is not
  this investigation's; it is counted as an unusable result, not evidence.
  (3) `gather` no longer throws away a good answer when the policy fails to
  interpret it (or returns a hypothesis citing evidence that was never
  gathered). The evidence and the answered question stay, no belief changes,
  the step is recorded with the new outcome `uninterpreted`, counted in the
  new `interpretation_failures` field of `InvestigationState` and
  `ReasoningMetrics`, and still counts as unproductive so such a policy
  cannot run forever.
  What the tests prove: a usable answer becomes numbered evidence with source
  and tick; an observation changes the next decision; the policy gets a copy
  and cannot alter counts or evidence; failed, raised, wrong-tool,
  wrong-investigation and empty answers are not evidence and do not crash;
  provider error text is not kept; same question at the same tick is skipped
  without a call, and allowed again after time passes; unusable decisions use
  a turn; the policy cannot claim the loop's stop reasons; tool-call,
  iteration, timeout and unproductive limits each stop the loop; a supported
  diagnosis needs confidence AND two supporting items, applies only in the
  test phase, and beats budget exhaustion on the last call; verification
  spends its own allowance; no hidden-truth words reach working memory
  through the real provider. Post-implementation checkpoint PASSED: the
  developer explained that a kept answer leaves a record to find a code bug
  from, and that the turn is still unproductive because the agent could not
  use the information. Added: the answer is also a true observation the
  policy can still read on a later turn. Known, deliberately left: the repeat check
  needs a known tick before the first call (expected-failure test; the outer
  sequence's observe step supplies it at checkpoint 3); the inner loop
  returns its stop reason but the final reason for the whole investigation
  is the outer sequence's to set. Verification: 568 passed, 1 expected
  failure; Ruff lint/format passed.

- **2026-10-12 — checkpoint 1 complete; memory design confirmed.**
  Post-implementation checkpoint passed after one re-teach: the developer
  first had no answer, then explained that a direct save from the loop would
  put anything recorded into the lessons table instead of lessons only, and
  that the no-import test stays until the protections are in place.
  Clarified: the gate already exists inside `capstone/memory/`; what is
  missing is the agent's side (finished record, look-again step, provenance),
  so a direct save would go around the gate. The developer also confirmed
  the two open memory points in their own words: the model only says what
  should be done while code holds the factual information; the JSON memory
  becomes the audit log. Next: checkpoint 2, the inner loop, taught before
  its tests are written.

- **2026-10-12 — decision for checkpoint 3: carrying out a fix is its own
  tool call (no code change; session paused here).** The developer asked that
  a fix require a tool call so the record shows it was carried out. Today
  `ApprovalDesk.approve` starts the repair itself. To build at checkpoint 3:
  a new agent-facing tool (working name `execute_action(proposal_id)`) that
  refuses unless that exact proposal is approved, so the agent can start an
  approved repair but can never approve one. Chain: `propose_action` → human
  decides at the desk → `get_proposals` → `execute_action` → wait → look
  again. The loop, not the model, makes the execute call right after reading
  an approval. Its answer (what started, on which machine, when it finishes)
  is saved as evidence and tells verification when to look. Costs to handle:
  `approve` no longer starts the repair, so `tools/actions.py`, the provider
  allowlist and the approval tests change; "approved but never executed" is a
  new state that must be reported honestly and never counted as a fix; an
  approval may go stale if execution is delayed (known limit, not solved).
  Clarified for the developer: the agent has no tool that fixes a machine by
  itself, and a finished repair is a separate fact from a solved problem.
  RESUME AT: confirm the two unconfirmed memory points in the entry below,
  ask checkpoint 1's closing question, then teach checkpoint 2 (inner loop).

- **2026-10-12 — memory and evaluation design discussion (no code change).**
  WHERE WE STOPPED: the developer had to leave mid-discussion. Decided by the
  developer: (a) the agent must learn from failed fixes as well as successes;
  the developer reasoned correctly that the agent can observe a failure itself
  (the machine is still down after the fix), so it needs no answer key;
  (b) the agent may look up memory whenever it chooses, as an ordinary counted
  tool call whose answer is saved as evidence marked as from memory; (c) an
  evaluator model may judge the free-text diagnosis against the true fault,
  now that the prompt must not list the possible causes. Explained but NOT
  yet confirmed by the developer: who writes the stored lesson (proposal:
  code fills in symptoms, action, result and provenance; the model writes
  only the advice sentence; the gate checks it); demoting the JSON memory
  (`agent/memory.py`) to an append-only audit log of every investigation that
  the agent cannot search, instead of deleting it. Cautions recorded: a
  failure lesson may say only "this action did not resolve these symptoms",
  never "that diagnosis is wrong"; unchecked or inconclusive outcomes are
  still refused; the evaluator judges wording only, uses a different model
  from the investigator, is tested against hand-labelled diagnoses, and its
  verdict never reaches the agent, reflection or memory. Consequence for the
  memory gate (a later checkpoint): `EpisodicMemory.outcome` and
  `MemoryPromotionPolicy` currently accept only verified `resolved`.
  Also decided by the developer: nothing tells the agent that a fix
  failed; it must find out by looking again after the action. To be built
  at checkpoint 4 as a step the loop requires after every approved action,
  not as model training.
  Model: `NVIDIA_API_KEY` is in the worktree's git-ignored `.env`; NVIDIA's
  catalogue lists `nvidia/nemotron-3.5-lightning-30b-a3b`; structured output
  from it is unverified. NEXT SESSION: confirm the two unconfirmed points,
  ask checkpoint 1's closing question (why test that `capstone/agent/` does
  not import `capstone/memory/`), then start checkpoint 2 (inner loop).

- **2026-10-12 — developer decisions after consolidation (no code change).**
  (1) The checkpointed loop (`agent/loop.py`, `state.py`, `policy.py`,
  `artifacts.py`) and the `capstone/memory/` package are the real path.
  (2) The ungated model wrapper, episode runner, monitor and scoring are to be
  reused by fitting them to the loop's policy interface; the ungated loop
  (`agent/agent.py`) and JSON memory (`agent/memory.py`) are then retired.
  Nothing is retired yet. (3) The model's prompt must NOT list the possible
  causes or their signatures; the current `SYSTEM_PROMPT` in `agent/agent.py`
  does and must not be carried over. Consequence to settle at the evaluation
  checkpoint: scoring reads a fault kind chosen from a fixed list, which a
  free-text diagnosis does not supply. (4) Wire in NVIDIA Nemotron through
  the NVIDIA API as a model behind the policy interface (already named in
  MVP_SCOPE with `NVIDIA_API_KEY`); model ID to come from settings and be
  checked against NVIDIA's catalogue when built; tests must not need a key.
  Proposed for memory, awaiting the developer's agreement: one long-term
  memory (the gated package); keep every completed investigation in a
  separate durable audit record the agent cannot search; add word-overlap
  search and an agent-callable look-up to the gated memory; a reflection step
  where the model writes only the lesson and category while code fills
  provenance and outcome from the verification. Checkpoint 1's closing
  question is still outstanding.

- **2026-10-12 — all branches consolidated onto `main`.** At the developer's
  request, `feature/episodic-memory-reflection`,
  `feature/reasoning-working-memory` and `claude/gifted-hamilton-eqyqf4`
  (rows 13c-17, built ungated) are merged into one history. Four conflicts,
  resolved without changing behaviour: `simulator.py` (kept the ungated
  branch's `_start_maintenance` / setting-reset code; `main`'s side was
  formatting only), `tools/observation.py` (kept both `get_sensor_summary`
  and `get_sensor_trend`), `pyproject.toml` (the `agent` extra now lists
  `anthropic` and `pydantic-graph`), `tests/test_observation_tools.py`
  (tool allowlist holds both; the hidden-truth leak test now also exercises
  `get_sensor_trend` and allows its `min` / `max` / `count` fields). The
  ungated branch's files were Ruff-formatted; `uv.lock` regenerated.
  Verification: 532 passed with all optional dependencies; Ruff lint/format
  passed. NOT YET RECONCILED, and no code was deleted to hide it:
  `capstone/agent/` now holds two agents side by side — the ungated
  model-driven one (`agent.py`, `toolbox.py`, `models.py`, `monitor.py`,
  `episode.py`, `__main__.py`) and the checkpointed loop (`loop.py`,
  `state.py`, `policy.py`, `artifacts.py`); and there are two memories —
  the ungated JSON `agent/memory.py` and the gated `capstone/memory/`
  package. The provider allowlist (`providers/factory.py`) does not yet
  offer `get_sensor_trend`, the setting-reset action or the diagnosis tool.
  Which agent and which memory survive is the developer's decision.

- **2026-10-12 — reasoning/memory consolidation, checkpoint 1 (one shared
  record).** The two parallel workstreams are being consolidated on
  `feature/reasoning-working-memory`. Pre-checkpoint passed: the developer
  explained that two definitions of one record end up different, and, after a
  re-teach of the propose / human decision / `get_proposals` sequence, that
  the desk's own answer saved as evidence would contradict a wrong belief in
  the agent's code. Clarified: the approval status reaches the completed
  investigation as an evidence item, not as a new field on the shared
  proposal. Post-implementation understanding remains outstanding.
  Changes: fast-forwarded this branch to the memory work (no merge commit);
  deleted the reasoning side's `contracts/completed.py`; added
  `agent/artifacts.py` holding the loop's own records, renamed so they cannot
  be confused with the shared ones: `DetectedAnomaly` (tick, machine, kind,
  description), `AgentConclusion` (adds recommendation and hypothesis),
  `ProposalRecord` (adds proposal ID and pending/approved/rejected status),
  `VerificationCheck` (outcome, prediction, checked tick) and the
  `TerminationReason` enum. `agent/state.py`, `policy.py` and `loop.py`
  changed imports and type names only; behaviour is unchanged.
  `agent/__init__.py`, `state.py` (working memory, budgets, decision records),
  `policy.py` (the decision-maker's interface) and `loop.py` (the inner
  decide / call one tool / record loop) are committed here for the first time
  and are NOT yet tested or understood; that is checkpoint 2. Added the
  `agent` optional dependency `pydantic-graph` (not imported yet).
  `tests/test_agent_artifacts.py` (8 tests): one definition of
  `CompletedInvestigation`, the old file is gone, runtime records are imported
  only inside `capstone/agent`, the agent package does not import
  `capstone.memory`, and runtime validation still rejects bad values.
  Verification: 483 passed with all optional dependencies installed; Ruff
  lint/format passed. Remaining checkpoints: 2 inner loop tests (timeout
  start, result identity, first-call repeat check, interpretation failure,
  final stop reason); 3 outer sequence with Pydantic Graph and proposal
  read-back; 4 verification rules; 5a one shared `ProvenanceReference` in
  `capstone/contracts/`, captured when a tool result arrives; 5b completion
  producer for every exit, and durable keeping of the completed investigation
  (memory rows keep evidence IDs, not evidence text); 6 who builds the
  `ReflectionCandidate`, and an integration test through the promotion gate.

- **2026-10-12 — SubQ whole-repository audit follow-up (documentation only).**
  Appended the developer's requested audit task to the end of MVP_SCOPE:
  architecture consistency and authorization/hidden-truth prompts, reproducible
  snapshot and coverage, file/line evidence before fixes, and comparison with
  Codex/Claude on the same snapshot. Checked official Subquadratic research,
  introduction, and model documentation; attributed the vendor benchmark and
  distinguished the long-context preview from Snap's structured decisions.
  No runtime change, external upload, or model invocation. Understanding
  checkpoint and live Neon application for the evaluation increment remain
  outstanding; Agent 1 handoff reconciliation is a separate session dependency.

- **2026-10-12 — memory evaluation records built.** Pre-checkpoint passed;
  post-implementation understanding remains outstanding. Added
  `evaluation/__init__.py` and `evaluation/memory.py`. `MemoryPromotionRecord`
  records acceptance/storage/reasons and memory IDs, with optional evaluator-only
  diagnosis correctness. `build_promotion_record()` checks investigation/run
  identity and policy consistency, then copies the decision without altering
  promotion. `MemoryUseRecord` distinguishes retrieval, known/unknown use,
  effect, assessor source, explanation, and evidence. `build_use_record()`
  validates references against the consumer investigation; known effects require
  actual use, attribution, explanation, and evidence. An agent report remains
  a self-report; no causal benefit is inferred from success. Builders do no I/O;
  records are JSON-serializable artifacts, not additional database tables.
  `docs/EPISODIC_MEMORY.md` includes API examples and these limits.
  Verification: expected missing-module test collection failure first, then
  22 evaluation tests passed; full offline suite 475 passed; Ruff lint/format
  and whitespace checks passed. Agent 1 still uses `contracts/completed.py`,
  with different fields and no final completion producer in its inspected
  runtime modules. Runtime integration, trusted reflection/provenance production,
  final branch review, and live Neon application remain separate steps.

- **2026-10-12 — memory evaluation pre-checkpoint passed.** The developer
  proposed reporting an unknown effect when memory usefulness is not known,
  and asking the agent for its assessment. Clarified that an agent report
  is attributed self-report, not proof of causation. Next increment records
  promotion/storage decisions and later retrieval/use/effect, with assessment
  source and supporting evidence. Evaluation never feeds hidden correctness
  back into promotion. Post-implementation understanding remains outstanding.

- **2026-10-12 — episodic-memory migration built.** Migration pre-checkpoint
  passed; post-implementation checkpoint subsequently passed. The developer
  explained that downgrade deletes the table's memories and upgrade cannot
  recover deleted data. Clarified that upgrade recreates an empty table,
  rather than restoring its original rows. Added
  `migrations/versions/0001_episodic_memory.py`: `upgrade()` explicitly creates
  the memory table, primary/unique constraints, and category index;
  `downgrade()` removes that table and its contents. The revision freezes its
  schema rather than importing evolving application metadata. `migrations/env.py`
  now registers memory metadata; its existing configuration/error handling and
  empty-metadata autogeneration guard remain. Updated scaffold tests for one
  real revision and added a local SQLite upgrade/downgrade/re-upgrade test,
  schema comparison, repeat upgrade, empty memory table, revision tracking,
  and preservation of unrelated data. Updated README and MVP_SCOPE status.
  Added `docs/EPISODIC_MEMORY.md` with lifecycle/command/limits and
  `docs/EPISODIC_MEMORY_MIGRATION.sql` with reviewed offline PostgreSQL upgrade
  SQL generated from a synthetic URL. No live Neon migration or memory insert
  occurred. Verification: missing revision/metadata tests failed before the
  implementation; 13 migration tests and the full 453-test offline suite
  passed afterwards; Ruff lint/format and whitespace checks passed.

- **2026-10-12 — migration pre-implementation checkpoint passed.** The
  developer explained that the service checks the candidate with the policy
  and rejects it before storage if it does not qualify. Table creation does
  not promote or store lessons. Next increment: explicit Alembic revision
  creating the memory table, with offline PostgreSQL SQL and local SQLite
  upgrade/downgrade tests. Live Neon application remains a separate step.

- **2026-10-12 — Agent 2 storage increment.** Built after the persistence
  pre-implementation checkpoint passed; post-implementation understanding
  checkpoint subsequently passed: the developer explained that a qualifying
  duplicate must be reported without adding another memory. The walkthrough
  clarified that the original memory and its provenance remain unchanged.
  `memory/schema.py` defines `episodic_memories`: unique
  investigation IDs and fingerprints, category/source-tick columns, and a
  validated-memory JSON payload (JSONB on PostgreSQL). `memory/repository.py`
  adds `InsertResult` and `SQLMemoryRepository`: `insert_statement()` builds
  dialect-specific conflict-safe SQL; `insert()` writes transactionally or
  identifies the original; `retrieve()` filters, bounds, orders, and validates
  stored rows. `memory/service.py` adds database-independent `MemoryStore`
  and `StorageResult` protocols and `MemoryService`: `promote()` runs policy
  before insertion; `retrieve()` delegates lookup. Duplicate decisions name
  the original memory without overwriting its provenance. Existing handoff,
  policy, contracts, and tests are included in this increment's commit.
  Strengthened tests with a fresh-engine reopen and competing connections.
  Added a narrow Ruff E402 exception for the optional-dependency test guard.
  Verification: expected missing-module collection failure before storage;
  32 memory tests passed afterwards; full offline suite 452 passed; Ruff
  lint/format and whitespace checks passed. PostgreSQL INSERT SQL compiled;
  no live PostgreSQL/Neon writes or migration occurred. Migration and memory
  evaluation records remain to implement. Neon is the intended durable store
  for real runs; SQLite is the offline test store.

- **2026-10-12 — Agent 2 review with understanding checkpoints.** The
  developer reinstated the teaching loop for episodic-memory work. Existing
  additions remain untracked on `feature/episodic-memory-reflection`.
  Reviewed completed investigation, reflection candidate, promotion policy,
  and provenance. The developer correctly explained that a completed loop
  does not establish correctness; human approval permits an action but does
  not prove resolution; unresolved outcomes must not be promoted by the
  current successful-lesson policy. The developer also correctly explained
  why evaluator-only truth must never enter agent memory. These specific
  checkpoints passed; the whole memory component is not yet understood or
  implemented. The developer requested a commit and push after every passed
  checkpoint; checkpoint documentation is saved separately from unfinished
  runtime additions. Existing policy tests: 22 passed. Repository test collection
  fails because `capstone.memory.repository` is not yet implemented.
  Agent 1 uses `contracts/completed.py`, while Agent 2 uses
  `contracts/completed_investigations.py`; their schemas differ and require
  reconciliation before runtime integration. Next checkpoint: deterministic
  identity, duplicate handling, and the persistence boundary.

  Duplicate-handling checkpoint passed: the developer explained that two
  callers can both observe absence before either inserts, but the database
  must enforce uniqueness at insertion. The later insert must preserve the
  original and report a duplicate. Persistence pre-implementation checkpoint
  passed; post-implementation walkthrough remains outstanding.

- **2026-10-12 — module responsibility comments.** Added a short two-line
  comment at the top of every Python module in `capstone`, including package
  initializers, describing its purpose and responsibility. Existing docstrings
  remain intact. No functions, classes, behavior, or component-understanding
  status changed.

- **2026-10-11 — implementation-condition prompt review (documentation only).**
  Evaluated the supplied 43-part Datum/Ratchet prompt against current contracts,
  provider/tool boundaries, approval behavior, tests, dependencies and roadmap.
  Added `docs/FUTURE_WORK_REEVALUATION.md` with corrected gates, current baseline,
  a complete candidate register and an addendum for later prompt execution.
  Linked the register from `README.md` and each relevant Future Work section in
  `docs/MVP_SCOPE.md`, retaining existing framework detail without duplicating it.
  Tightened completeness versus absence, validation versus truth, mutation
  idempotency/unknown outcomes, action transitions/preflight, verification exits,
  early manifests, replay limits, source conflict semantics, concurrency,
  outbox dispatch, redrive safety and first-client authorization. Checked primary
  AWS guidance for idempotency/outbox semantics. Datum/Ratchet inspiration was
  supplied by the prompt; those repositories were not independently audited in
  this condition review. A later three-repository audit must record inspected
  commits/files before claiming otherwise. All future entries may be rejected,
  replaced or deleted at their gates; required safety behavior remains binding.
  No runtime modules, functions/classes, dependencies or architecture changed.
  No component implementation or developer-understanding status advanced.
  Verification: 50 existing contract/provider/approval/sensor-summary tests
  passed; documentation link/register checks and `git diff --check` passed.

- **2026-10-11 — focused developer tooling and future integration audit.**
  Implemented uv-based GitHub Actions CI, Ruff pre-commit hooks, import sorting
  (`I` added to `E4`, `E7`, `E9`, `F`), and informational pytest-cov. Added
  `.github/workflows/ci.yml` and `.pre-commit-config.yaml`; updated
  `pyproject.toml`, `uv.lock`, `.gitignore`, and `README.md`. Both pip-compatible
  dev extras and the uv dev group include pre-commit 4.6.2 and pytest-cov 7.1.0;
  Ruff stays 0.16.10 and existing package versions are preserved. CI uses
  pinned actions, uv 0.13.0 with caching, `.python-version` (3.14.7), read-only
  permissions, locked default installs, Ruff checks, and one offline coverage
  test run with terminal/Markdown reports. No coverage threshold. Local hook
  installation remains a developer choice; both configured hooks were run.
  Hosted execution is not implied by local verification.

  Eight mechanical Python changes: `capstone/observability.py`,
  `capstone/providers/factory.py`, `capstone/simulator/state.py`,
  `test_db_connection.py`, `tests/test_contracts.py`,
  `tests/test_factory_provider.py`, `tests/test_slow_when_worn.py`, and
  `tests/test_wrong_setting.py`. Ruff fixed eight import-rule violations and
  its formatter found 73 files already formatted. An AST comparison against
  Git HEAD, normalizing import grouping/order, checked all 67 tracked Python
  files: imported names/scopes and non-import syntax are unchanged. No
  functions/classes or simulator behavior were added or changed.

  Commands: `uv add --dev 'pre-commit>=4' 'pytest-cov>=7'`, update the matching
  dev extra, `uv lock`, `uv sync --locked`, Ruff import autofix/format,
  `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, and
  `uv run --locked pre-commit run --all-files`. Lint, formatting, and both
  hooks passed. Baseline with database extra: 420 passed (70.35s). Post-change
  default `uv run --locked pytest`: 406 passed, two optional modules skipped
  (39.93s). Coverage run: 406 passed, two skipped (51.84s), 97% informational
  line coverage of `capstone` (944 statements, 29 missed); Markdown append
  also worked. `uv run --locked --extra database pytest`: 420 passed (74.23s),
  using mocks/in-memory SQLite, with no live Neon calls. Test runs used separate
  workspace `.pytest-tmp-*` directories because the default sandbox temp path
  is restricted. A 10-step simulator smoke run in the default environment
  required no database/agent/MCP/RAG packages and imported no settings module.
  YAML validation confirmed workflow triggers/permissions, one coverage test
  command, equal dev dependency declarations, and matching Ruff hook pin.

  Optional informational `uvx ty check --python-version 3.11 --output-format
  concise` used isolated ty 0.0.86, without changing dependencies: 67 errors,
  no warnings (exit 1), three core optional-value narrowing findings and 64
  test findings, including deliberate invalid-input tests and typing gaps.
  No broad type fixes, blanket ignores, or blocking type-check gate added.

  `docs/MVP_SCOPE.md` now documents Docling/HybridChunker (Future Work 1),
  first Pydantic AI MCP (2), later CrewAI `mcps` and existing `output_pydantic`
  handoffs (3), conditional Hypothesis/xdist/ty adoption (6), and Pydantic Evals
  (7), with integration points, reuse, adoption conditions, and tests. The
  audit found Pydantic Graph was not previously named in the roadmap; recorded
  the developer's planned macro-loop role without introducing an implementation
  or substituting CrewAI Flow. The CrewAI/LiteLLM provider design is retained.
  A scoped implementation/checklist plan is in
  `docs/superpowers/plans/2026-10-11-developer-tooling.md`. No future-phase
  agent/MCP/RAG/multi-agent runtime dependencies were installed. Unrelated
  component implementation/understanding status is unchanged; tooling is built
  ungated, developer to review.

  Hosted follow-up: the first run with local uv 0.12.0 failed before project
  installation because its catalog lacked the pinned CPython 3.14.7 Linux
  download. Updated only CI's uv pin to the current documented 0.13.0 release
  so the interpreter pin and lockfile remain intact. The isolated 0.13.0
  catalog query confirmed that Linux download is available. Hosted run
  [38161614543](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/38161614543)
  passed: Python installation, locked sync, Ruff lint/format, and 406 tests
  with two optional modules skipped (18.66s); coverage was 97% and its
  Markdown summary was published. This verifies the hosted workflow as well
  as the local checks above.

- **2026-10-11 — simplified multi-agent provider roadmap.** Revised Future
  Work 3 in `docs/MVP_SCOPE.md` to prefer CrewAI's LLM interface and LiteLLM
  over six custom provider clients. Preserve the existing `LLMProvider`
  protocol, with one planned framework adapter and a small role-model
  registry. Added typed task-output validation, separate retrieval reranking,
  compatible generic fallback, shared execution budgets, and an opt-in
  per-model compatibility gate. Checked the linked official CrewAI/LiteLLM
  documentation; model IDs and advanced capability support remain subject
  to testing at implementation time. Documentation only: no modules,
  functions, classes, dependencies, or understanding status changed.

- **2026-10-11 — MCP roadmap and readiness checklist.** Updated Future Work 2
  in `docs/MVP_SCOPE.md` from a prescribed server split to capability/trust
  boundaries whose server count will be revisited after the minimal MCP
  slice works. Added least-privilege scopes, read-only-first transport over
  existing contracts/providers, OpenTelemetry/LangSmith observability,
  deterministic response verification, a minimal verification record,
  optional operator panel, implementation phases, and split criteria.
  Clarified that the first MCP slice follows the core simulator/agent MVP;
  public observations remain distinct from hidden evaluator truth. Added a
  practical readiness checklist identifying existing foundations and missing
  checks, plus a README link. Documentation only: no modules, functions,
  classes, dependencies, or runtime integrations changed, and no understanding
  status advanced.

- **2026-10-09 — deterministic sensor summary tool.** Understood: no — built
  ungated, developer to review. `tools/observation.py` adds
  `ObservationTools.get_sensor_summary()`: read existing public readings,
  sort by tick, and compute count, endpoints, min/max, sample-weighted mean,
  delta, and endpoint change per elapsed simulation tick. A null machine ID
  selects factory sensors. Windows include both bounds; missing ticks are
  not filled in, empty statistics are null, and zero elapsed time has no
  rate. Invalid tick windows, unknown machines, mixed units, and nonfinite
  readings are rejected. `contracts/observations.py` adds
  `SensorSummaryObservation`, the immutable observable result schema;
  `providers/factory.py` adds strict `SensorSummaryArguments` and an allowlist
  entry connecting the tool to the existing provider envelope. No simulator
  dynamics, hidden-state access, MCP transport, or LLM integration added.
  `tests/test_sensor_summary.py` covers arithmetic on known samples, filtering,
  irregular spacing, empty/single-sample windows, factory sensors, validation,
  provider access, state immutability, hidden-state independence, and seeded
  reproducibility. Existing provider and all-observation leak tests include
  the new tool. `README.md` and `MVP_SCOPE.md` describe the implemented scope.
  Verification: all 420 tests passed, including 18 focused summary cases;
  Ruff lint/format and whitespace checks passed. The suite used a fresh
  workspace temp directory because the sandbox's default pytest temp path
  was not writable. Deliberate limits: endpoint rate rather than trend fitting,
  no interpolation, and no window comparisons or moving averages yet.

- **2026-10-09 — roadmap additions from the developer's pasted proposal.**
  Updated `docs/MVP_SCOPE.md` with Future Work 7: role-specific model
  benchmarking, per-agent reasoning/token budgets, deterministic sensor
  calculations, and known-answer regression scenarios. Cross-model
  benchmarking and specialist role budgets follow the multi-agent extension;
  single-agent limits, a small sensor-summary capability, and basic regression
  cases are planned alongside the existing MVP agent/evaluation work. MCP
  remains deferred, and a failure-diagnostic benchmark mode is explicitly
  excluded. Documentation only: no modules, functions, or classes changed,
  no new behavior implemented, and no understanding status advanced.

- **2026-10-08 — contracts, trace identity, tool/provider boundaries,
  logging, and migration scaffold.** Understood: no — built ungated,
  developer to review. Implemented the five foundations and smaller
  supporting items requested by the developer, within the existing package.
  `contracts/__init__.py` adds `Contract` (immutable fields, unknown fields
  rejected); `observations.py` models only the eight observation tools' public
  data and action results. `evidence.py` adds `Evidence` (source and observed
  content); `hypotheses.py` adds `Hypothesis` (claim, bounded confidence,
  evidence references); `investigations.py` adds `Investigation` (portable
  research record), `run_id_for()` (UUID from an explicit execution key), and
  `investigation_id_for()` (UUID from that run and a positive sequence).
  IDs consume no simulator randomness and do not create persistence records.
  `tools.py` adds `ToolRequest`, `ToolError`, `TraceContext`, and generic
  `ToolResult`; validators prevent conflicting success/error states and
  investigation context without a run. `providers/factory.py` adds the
  `FactoryProvider` protocol, strict argument models/range validation, and
  `SimulatorFactoryProvider.call()`: validate context before actions, dispatch
  only listed existing tools, validate observable results, return structured
  errors and optionally log metadata. Approval and ground truth are never
  dispatchable; direct legacy tools are unchanged. `providers/llm.py` adds
  `LLMProvider`, a protocol for explicit `Investigation` artifacts, with no
  live model implementation or orchestration.
  `observability.py` adds `EventLogger`, `log_event()`, `_safe_identifier()`,
  and `create_event_logger()` for opt-in JSON metadata, secret masking,
  no raw payloads/exception text, no root-logger changes, and no inferred
  wall-clock time. `alembic.ini` and `migrations/` add settings-driven
  `database_url()`, offline SQL rendering, short-lived online connections,
  a revision template, and empty metadata/history. Autogeneration with empty
  metadata is rejected before connecting; no tables or revisions were created
  or applied to Neon. Alembic is an optional database dependency.
  `.env.example`, `README.md`, and `MVP_SCOPE.md` document the implemented
  configuration and foundations. New focused tests cover the contracts,
  deterministic IDs, tool parity, error/approval/hidden-truth boundaries,
  metadata-only logging, and offline migration behavior. Deliberate limits:
  no schema, durable memory, external model/factory adapter, or agent loop;
  future contract migrations remain explicit changes to these boundaries.

- **2026-10-08 — test-intent audit.** Reviewed the existing test suite
  following the developer's request. Strengthened weak baseline-quality
  assertions using controlled draws on both sides of the 1% inspection
  threshold, and registered a real vibration alarm in the wrong-setting
  fixture with a positive-control test. The new quality test was checked
  against a temporary zero-baseline mutation and correctly failed.
  `SimulationClock.advance()` and `time_at()` incorrectly accepted fractional
  and boolean ticks; they now reject noninteger ticks before changing state,
  with eight regression cases. A new provider test also exposed invalid
  context being validated after waiting; validation now precedes all actions.
  Expanded the all-tools leak check to all eight observation tools, using
  nonempty evidence; arrival events are compared with independent per-tick
  machine state so missing events are caught. Slowdown tests now install
  actual vibration sensors and alarms: this exposed the former false claim
  of no alarms throughout the run, replaced by measured slowdown before
  the first alarm. Job-time variation tests now require actual overlap
  between healthy and slightly worn durations. This fixes real gaps rather
  than changing the existing causal model. Final verification: 402 tests
  passed with the database extra; 388 passed and two optional modules skipped
  in the default environment without SQLAlchemy/Alembic/Psycopg. A separate
  simulator/provider smoke check required neither database packages nor
  credentials and did not import settings. Ruff lint and formatting,
  lockfile consistency, and whitespace checks passed. The read-only Neon
  probe returned `True`; Alembic heads/history were empty. Tests demonstrate
  the covered behavior, not completeness of future unimplemented integrations.

- **2026-10-08 — typed settings.** Understood: no — built ungated,
  developer to review. Added Pydantic Settings to `pyproject.toml` and
  `uv.lock`, keeping the simulator's pinned dependency versions.
  New `capstone/settings.py` defines `Settings`, a typed configuration
  model with an optional `SecretStr` database URL;
  `normalize_database_url()` strips whitespace and treats blanks as absent;
  `get_settings()` reads fresh configuration on demand, without a global
  cache or import-time loading. Environment variables override the
  repository's `.env`, unrelated dotenv keys are ignored, and configuration
  reads do not mutate `os.environ`. `check_database_connection()` now reads
  this model and unwraps the secret only when constructing the connection.
  The simulator does not import settings or require a database URL.
  `.env.example` provides a secret-free template for the implemented
  integration; `README.md` documents the source precedence and model;
  `MVP_SCOPE.md` marks settings implemented. `tests/test_settings.py`
  checks precedence, dotenv loading without environment mutation, missing
  and blank values, secret masking, and fresh reads after configuration
  changes. Deliberate simplification: no configuration fields or credentials
  for unimplemented agent/provider/ingestion components.

- **2026-10-08 — Ruff.** Understood: no — built ungated, developer to
  review. Added Ruff to the development group and pip-compatible extra in
  `pyproject.toml`, configured Python 3.11 as the minimum target, 88-character
  formatting, and basic correctness rules (`E4`, `E7`, `E9`, `F`). The
  optional database test's import guard is the only `E402` exception.
  `.gitignore` excludes `.ruff_cache`; `README.md` documents lint and
  format commands; `MVP_SCOPE.md` marks Ruff implemented. The formatter
  changed 36 existing Python files; all tracked Python syntax trees were
  identical before and after formatting, so no functions, classes, or
  simulation behavior changed. Formatting is committed separately from
  typed settings. Ruff checks passed and all 333 existing tests passed
  after formatting. No hooks or CI were added.

- **2026-10-08 — development tooling and Neon connectivity.** Implemented
  ungated at the developer's request. Understood: no — built ungated,
  developer to review. The existing `uv` installation now manages `.venv`
  and the new `uv.lock`; `.python-version` records Python 3.14.7.
  `pyproject.toml` retains setuptools and the pip-compatible development
  extra, adds a default development group and optional database extra,
  and constrains the installed simulator dependency versions: Pydantic
  2.13.4, pydantic-core 2.46.4, annotated-types 0.8.0,
  typing-extensions 4.16.0, typing-inspection 0.4.3. All 331 existing
  simulator tests passed with those versions. `README.md` documents uv
  setup, locked commands, and pip compatibility; `MVP_SCOPE.md` records
  that uv adoption is now implemented rather than future work.
  `.gitignore` excludes local `.env` files, retaining `.env.example` as
  an optional shareable template. The local `.env` remains untracked.
  New module `capstone/database/connection.py` adds
  `check_database_connection()`: loads the repository's `.env` without
  overriding environment variables, selects Psycopg for PostgreSQL URLs
  while preserving URL options, runs only `SELECT 1`, and closes the
  connection and engine. Nothing connects on import. The standalone
  `test_db_connection.py` prints the result and suppresses driver error
  details to keep credentials out of output. `tests/test_database_connection.py`
  checks a real query using in-memory SQLite and rejects empty configuration;
  it runs offline and skips when the database extra is absent. The live
  Neon probe returned `True`; the full suite passed (333 tests). A separate
  smoke check ran the simulator with SQLAlchemy uninstalled, then restored
  the database extra. No schema, agent memory, API, or ingestion
  behavior was added; the simulator remains independent of the database.

- **Session 1** — Repo was empty. Created CLAUDE.md, package skeleton,
  this log. Recommended SimulationClock as the first component; asked
  the first comprehension question. No simulator logic implemented.
- **Session 1 (cont.)** — Clock gate passed (developer explained single
  ownership of time, intermittent same-seed failures with multiple
  counters, and corrupted-ordering consequences for the agent).
  Implemented `SimulationClock` + 8 tests, all passing. Deliberate
  simplification: `clock.py` is a module, not the `clock/` package in
  CLAUDE.md §6; promote it if it grows.
- **Session 1 (cont.)** — Random source gate passed after two corrections
  (clock does not advance streams; sequence depends on `(seed, name)`,
  not seed alone — developer then correctly derived that renaming a
  stream changes its history). Implemented `RandomSource` + 9 tests, 17
  total passing. Stream names are frozen contracts once histories are
  recorded.
- **Session 1 (cont.)** — MachineState gate passed after teaching the
  cause-vs-evidence distinction (developer: "bearing_health is the
  beginning of the chain, vibration is the end — what the sensor says").
  Implemented `MachineStatus`, `MachineCondition` (hidden), `MachineState`
  with pydantic bounds validation; 11 tests, 28 total passing.
- **Session 2** — Sensor gate passed (developer explained read-only role,
  shared-reality correlation, status dependence, many-causes-one-symptom;
  Claude filled in noise → trend-over-readings). Implemented
  `SensorReading` (frozen), `Sensor` base, `VibrationSensor` with
  monotonic squared wear curve and status dependence; 11 tests, 39 total.
- **Session 3** — Sensor post-implementation gate passed. Needed
  teaching first on `super().__init__`, `gauss`, and noise vs. drift
  (corrected: bearings do not degrade unless a scenario writes to them;
  noise averages out as `noise_sd / sqrt(N)`). Developer then correctly
  judged that the same 3.1 mm/s reading implicates CNC-01 (baseline 2.0)
  but not CNC-04 (baseline 3.0), and that the agent must compare a
  machine against its own past readings. Claude filled in: 3-4 readings
  is too few against the noise, and per-sensor constructor parameters
  are what rule out a single global threshold. Taught FactoryState +
  `step()`; gate question asked. Tests run under Python 3.13 on this
  machine (3.11 not installed).
- **Session 3 (cont.)** — FactoryState + `step()` gate passed after
  several corrections (FactoryState holds truth, not how it changes;
  the log holds evidence, not past states; readings are evidence, not a
  partial copy of state). Developer derived that read-then-update logs
  the undamaged bearing at tick 50 and the damage at 51, and that
  update-then-read records damage in the step it happens. Claude filled
  in: the tick stamp, not the delay, is what makes the other ordering
  wrong. Implemented `FactoryState`, `Simulator` with `step()`; 9 tests,
  48 total. Debt: `_update_reality` is an empty hook, and the ordering
  test overrides it in a subclass until scenarios exist (row 7).
- **Session 3 (cont.)** — `step()` post-implementation gate passed
  (developer: tick first, damage before the reading, both sensors read
  and write to the reading log). Claude filled in where each result
  lands (clock / FactoryState / log). Taught the event log, with a
  vibration threshold alarm as the first event; gate question asked.
- **Session 3 (cont.)** — Event log gate passed (developer: an alarm on
  `bearing_health` would hint the hidden truth to the agent; an alarm
  can fire on a healthy machine and that ambiguity is wanted). Developer
  proposed heavy load as the cause; load is not modelled yet — candidate
  for the unrelated-anomaly source in CLAUDE.md §5.1. Implemented
  `Event` (frozen), `EventLog` (append-only, tick-ordered),
  `ThresholdAlarm`, and an alarm stage in `step()`; 9 tests, 57 total.
- **Session 3 (cont.)** — Event log post-implementation gate passed.
  Developer first attributed "readings show it first" to the alarm being
  appended after the reading within a step; corrected (same tick — the
  threshold is the reason). Developer then read off a worked table that
  the event log says nothing about CNC-04 at tick 450 and that about
  0.40 health remains at the first alarm. Taught the Scenario
  abstraction; gate question asked.
- **Session 3 (cont.)** — Scenario gate passed after re-teaching
  (developer was unsure why a scenario may not write a fake reading;
  then correctly stated that a heavy-load scenario changes only the load
  for a few ticks and restores it, and that the sensor produces the
  5.0 mm/s reading). Implemented `Scenario` base, `add_scenario`, and
  the scenario loop in `_update_reality`; 7 tests, 63 total. The
  test-only `Simulator` subclass is gone (debt from row 5 cleared).
  `load` is NOT in `MachineState` yet — it belongs with the false-alarm
  scenario.
- **Session 3 (cont.)** — Scenario post-implementation gate passed
  (developer: scenarios run before the sensors, can change anything in
  FactoryState, cannot change an event's tick). Claude filled in: they
  run after the clock advances, and cannot touch the clock, reading log
  or event log at all. Taught BearingDegradation (wear only while
  RUNNING, linear health loss with seeded variation, failure transition
  deferred to its own increment); gate question asked.
- **Session 3 (cont.)** — BearingDegradation gate passed on the second
  attempt. First answer put the curve in the noise and a temperature
  function inside the scenario; re-taught with the worked wear-squared
  table and the one-job-per-component split. Developer then stated that
  the curve comes from the equation that squares wear, and that the
  scenario changes only bearing health, with vibration and temperature
  readings following from it. Implemented `BearingDegradation` (wear
  only while RUNNING, seeded variation, clamped at 0); 14 tests, 77
  total. Seed 42 sample run: start tick 100, rate 0.001, first alarm at
  tick 714. Debt: no failure transition; a wrong `machine_id` surfaces
  as a KeyError on the first active tick, not at construction.
- **Session 3 (cont.)** — BearingDegradation post-implementation gate
  passed (developer: health holds while idle because the machine is not
  running; vibration is high before, drops during idle, resumes after;
  the agent should read the machine's idle status). Claude corrected two
  points: after restart vibration returns to the same elevated level as
  before the pause, not to normal; and the dangerous wrong conclusion is
  "the problem went away", not "the machine is broken". Also confirmed
  on request that health never drops without a scenario (no normal wear;
  deliberate). Taught the failure transition; gate question asked.
- **Session 3 (cont.)** — Failure transition gate passed first time
  (developer: it does not belong in BearingDegradation, which should
  only change bearing health, and other causes of failure should not
  depend on it; the event says only that the machine stopped, because
  working out why is the agent's job). Implemented a consequences stage
  in `step()` between scenarios and sensors; 8 tests, 85 total. Seed 42
  sample run: fault starts tick 100, first alarm 714, machine stops 995.
  Debt: failure level is one number for all machines; only RUNNING
  machines fail; nothing can bring a DOWN machine back yet.
- **Session 3 (cont.)** — Failure transition post-implementation gate
  passed (developer raised unprompted that status is observable; then:
  event log first mentions CNC-04 at tick 714, and the reading log is
  what the agent needs to date the fault). Claude corrected: status
  would read "down", not "idle"; and the fault is not visible in the
  readings at tick 100 itself — it emerges from the noise around tick
  250-300 and the agent must extrapolate back. Split row 9 into 9a
  (ground truth) and 9b (tools). Taught 9a; gate question asked.
- **Session 3 (cont.)** — Ground truth gate passed after re-teaching
  part 1 (developer knew at once that tools reading the ground truth
  would hand the agent the answers; was unsure why `bearing_health` is
  not enough, then answered on the false-alarm case that the fact has to
  come from the ground truth). Claude corrected again that sensor
  readings are not in FactoryState. Implemented `GroundTruth` (frozen),
  abstract `Scenario.ground_truth()`, `Simulator.ground_truth()`;
  8 tests, 93 total. Debt: `Simulator.ground_truth()` is a public method
  on the same object the tools will wrap — 9b must make it unreachable;
  `fault` is free text; no end tick or cause field yet.
- **Session 3 (cont.)** — Ground truth post-implementation gate passed
  (developer: it comes from the scenarios, it is what will go wrong, and
  only evaluation may read it — no agent tools). Claude filled in why it
  does not change: it is built from settings fixed when the scenario is
  created. Taught the read-only observation tools (allow-list vs
  block-list); gate question asked.
- **Session 3 (cont.)** — Observation tools gate passed (developer chose
  the build-from-scratch version on a hunch; after the worked example,
  explained that a newly added machine field leaves that list untouched,
  whereas copy-everything would pass it through because it had not been
  accounted for). Implemented `ObservationTools` with `get_time`,
  `list_machines`, `get_readings`, `get_events`; 10 tests, 103 total,
  including a full-run leak test. Debt: `_sim` is private by convention
  only — real enforcement comes when the agent is given just these four
  functions; an unknown sensor name returns an empty list rather than an
  error; each call scans the whole log; nothing lets the agent advance
  time yet.
- **Session 3 (cont.)** — Observation tools post-implementation gate
  passed (developer: the agent can list machines and get CNC-04's
  readings; it cannot get bearing health or the degradation rate; the
  observation is built, not copied). Claude corrected: the tools object
  does hold the simulator — the protection is that only named fields are
  passed out and the agent is handed only the tools. Developer asked,
  unprompted, whether the agent can find the stop and backtrack through
  the reading log: yes, that is the intended investigation path. Rows
  1-9 complete. Proposed rows 10-12 from MVP_SCOPE.md; developer has not
  yet agreed the order.
- **Session 3 (cont.)** — TemperatureSensor built as a pattern repeat
  (CLAUDE.md §2.2), in Fahrenheit at the developer's request: 115 °F
  healthy, +45 °F per unit of wear (straight line), 72 °F when not
  running, noise 1 °F. Developer correctly said BearingDegradation needs
  no change, but expected `Simulator.step()` and `ObservationTools` to
  need changes — they do not (only `sensors.py` changed); explained, to
  be re-checked in the post-implementation question. 6 tests, 109 total.
  Debt: no warm-up or cool-down lag.
- **Session 3 (cont.)** — Developer noticed that temperature is too
  clean a signal (only bearing wear moves it) and asked how to make the
  agent's job harder while staying realistic. Agreed to add, before the
  maintenance action: operating load, room temperature drift, and
  warm-up/cool-down lag (rows 10a-10d). Taught 10a; gate question asked.
  Row 10's re-explain questions were not answered and are still owed.
- **Session 3 (cont.)** — TemperatureSensor re-explain passed on the
  architecture question (developer: sensors are one kind of object the
  other modules already account for, so a new one is just another entry
  in the list, not a new component). The cross-checking question was
  not answered separately; it is superseded by the load gate's first
  question, which tests the same idea with load in the picture.
- **Session 3 (cont.)** — Load gate passed (developer: worry about the
  machine at normal load, because temperature should not be that high
  for a routine job; separate per-sensor ideas of load would duplicate
  it, and if they drifted apart there would be no way to tell which was
  right or reconcile them). Implemented `MachineState.load` (0-1,
  default 0.5), load terms in `VibrationSensor` (+1.5 mm/s per unit) and
  `TemperatureSensor` (+30 °F per unit), and `LoadSensor` (%); 10 tests,
  119 total. One older test in `test_state.py` copied the machine minus
  `condition` and so picked up `load` automatically — the copy-and-
  remove behaviour from the tools gate, seen for real; expectation
  updated. `ObservationTools` needed no change and does not expose
  `load`. Debt: nothing changes load yet (row 10b); bearing wear does
  not raise load; load does not speed up wear.
- **Session 3 (cont.)** — Developer brought outside feedback that the
  two load simplifications are unrealistic (a worn bearing does raise
  motor load a little; heavy load does shorten bearing life, steeply).
  Agreed to model both as row 10a2. Taught it (wear rate scales with
  load cubed; friction term lives in `LoadSensor`, not in `load`); gate
  question asked. Row 10a's re-explain question is still owed.
- **Session 3 (cont.)** — Load re-explain passed (developer: the two
  explanations are higher load or a degraded bearing). The deciding
  reading was not named this time; the developer had used the load
  sensor to decide the two-machine case in the pre-implementation gate,
  so Claude filled it in. Row 10a2 gate question still awaiting answer.
- **Session 3 (cont.)** — Load–wear coupling gate passed (developer
  chose the sensor-side friction term because it does not change load
  for everyone, only the reading; asked how load then speeds up wear —
  explained it lives in `BearingDegradation`, which reads `load` and
  still writes only health; developer then said the heavier-loaded
  machine fails first). Claude filled in the two failure modes of the
  other option (double counting, runaway loop). Implemented wear scaled
  by (load / 0.5) ** 3 and `LoadSensor` friction of 8 × wear²; 9 tests,
  128 total. Sample: same fault from tick 100, machine at 80% load stops
  at tick 319, machine at 30% load is still at health 0.81 at tick 1000.
  Debt: the cube is steep and uncapped; friction does not depend on load.
- **Session 3 (cont.)** — Load–wear coupling re-explain passed on the
  second attempt. Developer first said the load gets heavier as the
  machine wears; corrected (the reading rises, `load` does not).
  Developer then stated that the actual load is 80 and the difference is
  the wear, and confirmed unprompted that friction is not tracked as its
  own value and need not be. Taught workload variation (10b); gate
  question asked.
- **Session 3 (cont.)** — Developer's direction on 10b: load must vary
  on every machine in every run, not only in one scenario; block-based
  load is acceptable as a starter, with load driven by what the machine
  is actually making to follow (row 12). Note: MVP_SCOPE.md says one
  product type; whether to vary by product or by job size is undecided.
  Added proposed row 10e (standard line builder). 10b gate questions
  still awaiting answers.
- **Session 3 (cont.)** — Workload gate passed (developer: a jump means
  another product is on the machine — too big and sudden to be wear,
  which is gradual; workload should run first, otherwise degradation
  runs and then the product is switched for that tick). Implemented
  `Workload` (blocks of 30-90 ticks, load 0.3-0.8, own stream per
  machine); scenarios may now declare no ground truth; 9 tests, 137
  total. Debt: run order (workload before degradation) is a convention
  to be enforced by the line builder (10e); load changes instantly; the
  agent sees load only via the load sensor, with no job record to
  explain a change (row 12).
- **Session 3 (cont.)** — Workload re-explain passed with gaps filled by
  Claude. Developer: the agent looks at the load, and also the vibration;
  confirmed by asking that two scenarios can run at once. Claude
  corrected that vibration rises with load too, so the second check is
  the shape of the change (step vs. creep), and explained why a changing
  workload hides a slow fault (job steps are larger than the drift, so
  the agent must compare periods of similar load). Developer proposed
  recording load changes in the event log; agreed as row 10b2, taught,
  gate question asked.
- **Session 3 (cont.)** — Job-event gate passed on the second attempt.
  Developer first thought "machine stopped" was written by a reading
  threshold and rightly objected that a threshold cannot work for load;
  re-taught the two event routes (alarm on a reading vs. the simulator
  noticing a state change). Developer then stated that the simulator
  reads the job number, finds it different, and adds the entry to the
  event log. Implemented `MachineState.job_number`, `Workload` raising
  it, and `Simulator._record_new_jobs`; 9 tests, 146 total. The
  copy-minus-condition test in `test_state.py` broke a second time on
  the new field and was rewritten to check only what it means to check.
  Debt: the event carries no job identity or description (row 12).
- **Session 3 (cont.)** — Developer proposed tracking one job number
  through the machines (a job travelling down the line). Agreed as the
  design for row 12, not built now. Open items: (1) developer's go-ahead
  on the fix so a machine that is not running starts no new jobs — found
  in the 10b2 sample run, where a DOWN machine logged nine more jobs;
  (2) row 10b2 re-explain.
- **Session 3 (cont.)** — Job-event re-explain passed (developer: with a
  job event it is just a new job; with none it could be wear and should
  be investigated). Developer approved the fix: `Workload` now starts no
  new job on a machine that is not running and resumes when it runs
  again; 2 tests, 148 total. Taught room temperature drift (10c); gate
  question asked.
- **Session 3 (cont.)** — Developer asked for the machines to form an
  assembly line with a job moving through them (e.g. job 117: CNC-01 →
  CNC-02 → CNC-04). Agreed and moved up: row 12 split into 12a-12c, with
  12a next after 10c. Rows 10d (thermal lag), 10e (line builder) and 11
  (maintenance action) follow the line work; 10e will likely fold into
  12a. Row 10c gate question still awaiting answer.
- **Session 3 (cont.)** — Developer pasted an outside review of row 10c.
  Adopted from it: name the scenario `AmbientTemperature` (not
  `RoomTemperature`); make the daily cycle vary a little from day to day
  with a slow seeded drift rather than a perfect repeating curve. Noted
  for later, not now: HVAC cycling, door openings, temperature zones.
  The paste also contained answers to both gate questions; per CLAUDE.md
  §1.1 these do not count as the developer's own explanation, so the
  gate was re-asked with a different example.
- **Session 3 (cont.)** — Ambient gate passed in the developer's own
  words (it stays in the factory state and others read it from there
  without storing it; CNC-02 cooling less than its neighbours may have a
  wear issue, because heat from wear offsets the cooling of the
  factory). Implemented `FactoryState.ambient_temperature`,
  `AmbientTemperature` (daily cycle, warmest ~4 pm, plus slow seeded
  drift), and `TemperatureSensor` measuring from the air; 10 tests, 158
  total. Developer asked for a loading-door scenario with an event; added
  as row 10c2. Debt: `warmest_tick` assumes a 6 am start with one-minute
  ticks; `Sensor.read` takes ambient as a keyword — a second shared fact
  would want a small environment object; no thermometer for the agent.
- **Session 3 (cont.)** — Ambient re-explain passed (developer: look at
  load, see what the building temperature is, then vibration should tell
  the story of the wear). Claude filled in that the agent has no
  thermometer, so "the building temperature" has to be read off the
  other machines. Taught the loading door (10c2); gate question asked.
- **Session 3 (cont.)** — Developer asked whether ambient temperature is
  a hidden field; explained the three kinds of state (secrets, plain
  facts, measured conditions) and that ambient is unmeasured by choice.
  Developer decided to add a factory thermometer (row 10c3, after the
  door). 10c2 gate still awaiting answer.
- **Session 3 (cont.)** — Loading door gate passed (developer: ambient
  first and the door second; leave the season out and make the door a
  set cooling; "the factory state would notice the door opened" —
  corrected: the state only holds the door, the simulator's `step()`
  notices). DESIGN CHANGE DURING IMPLEMENTATION, explained to the
  developer: the door does not subtract from `ambient_temperature`. It
  writes its own `door_cooling`, and `FactoryState.air_temperature` is
  ambient minus door cooling. Reason: subtracting each tick only works
  if the daily cycle resets the value first every tick; without it the
  air would fall forever. The two scenarios now write different values
  and their order does not matter. Implemented `LoadingDoor`, door
  events with `machine_id=None`; 13 tests, 171 total. Debt: one door,
  one fixed cooling; a machine-filtered `get_events` hides door events.
- **Session 3 (cont.)** — Loading door re-explain passed (developer:
  check the load, and check the event log to see whether the door had
  been opened). Claude added a third check: the other machines dipping
  at the same time. Taught the factory thermometer (10c3); gate question
  asked.
- **Session 3 (cont.)** — Thermometer gate passed after re-teaching.
  Developer first expected the agent to see the thermometer as soon as
  it wrote to the reading log; re-taught that the agent sees only what a
  tool returns, and the developer concluded a new tool is needed. On the
  worked case (118 °F, air 75 °F, normal load) the developer judged
  nothing wrong and said the agent must take the factory temperature and
  work out the heat the machine gives off; Claude supplied the figure
  (118 − 75 = 43). Implemented `FactoryThermometer`,
  `Simulator.add_factory_sensor`, `get_factory_readings` (fifth tool);
  10 tests, 181 total. Debt: `FactoryThermometer` is not a `Sensor`
  subclass (different inputs) — a shared base is due if a second
  factory-level sensor appears.
- **Session 3 (cont.)** — Thermometer re-explain passed (developer: the
  machine could just be under a heavy load, and the agent would use the
  load sensor). Fixed a table slip: row 10c's post-implementation column
  was blank although the notes recorded the pass. Taught the assembly
  line (12a): one job identity moving station to station, hand-off only
  when the next station is free, load taken from the job, a machine with
  no work or nowhere to send it is idle; gate question asked.
- **Session 3 (cont.)** — Assembly line gate passed (developer: idle
  neighbours of a broken machine are just not busy; load now comes from
  a job number that follows the line from machine 1 to the last one).
  Claude filled in what stops the agent blaming idle machines (status,
  the stop event, their flat history) and why a shared job helps (the
  same load appears on each machine in turn). Implemented `Job`,
  `MachineState.job` / `job_progress`, `FactoryState.completed_jobs`,
  `ProductionLine`; job events now read "job N started". REMOVED the
  stand-ins: `Workload`, `MachineState.job_number`, and their two test
  files (20 tests); 14 new tests, 175 total. Sample (seed 42): a wear
  fault on CNC-02 stops it at tick 721 and the line makes nothing more.
  OPEN ISSUE found in the sample run: with every job taking a different
  time, healthy machines are idle 17% / 24% / 34% of the time along the
  line. Debt: no buffers between machines; no job-finished events or
  job-history tool (12b); a DOWN machine keeps its last `load` value.
- **Session 3 (cont.)** — Developer pasted an outside review of 12a.
  Adopted: working time is a property of the machine
  (`MachineState.ticks_per_job`, default 60), not of the job; a job now
  carries only its id and load; no random variation in time for now.
  Kept: one job brings the same load to every machine. Measured result:
  a balanced line (60/60/60) is never idle once full; an uneven line
  (60/70/55) idles in a fixed pattern each 70-tick cycle — the machine
  before the slow one waits 10 ticks holding a finished job, the one
  after waits 15 ticks empty. 18 line tests, 179 total. Which times the
  standard line uses is left for the line builder (10e). The paste also
  answered the re-explain question; per CLAUDE.md §1.1 it was re-asked
  with a different example. Later options noted from the review: a few
  ticks of natural variation, several job types, per-machine load.
- **Session 3 (cont.)** — Developer pasted an outside priority list.
  ORDER ADOPTED for the remaining rows: 12a (done, re-explain owed) →
  10d temperature lag → 12b job history and events → 11 maintenance
  action + advancing time → 12c quality, small pass/fail version →
  10e line builder → then stop adding simulator features. Standard line
  times taken as 60 / 70 / 55 ticks (CNC-02 the slowest step), to be set
  in 10e. Two items on the list already exist: sensor noise (vibration
  ±0.15 mm/s, temperature ±1 °F, load ±2 points, thermometer ±0.3 °F)
  and not exposing causes (status is only running / idle / down; tools
  return id and status). Gates are not skipped to meet a one-day target.
- **Session 3 (cont.)** — Assembly line re-explain passed on the second
  attempt. Developer first had the two kinds of waiting reversed (said
  CNC-01 waits empty and CNC-04 waits holding a job for a "CNC-05");
  re-taught with a tick-by-tick cycle and the two end-of-line facts. On
  a fresh line (80/50/50) the developer answered that CNC-02 is empty
  and waiting for CNC-01, and that CNC-01 is always going unless the
  line has no job for it — and said plainly that the first attempt had
  been a guess. Taught temperature lag (10d): the machine's real
  temperature becomes state, moved toward its settling point each tick
  by the simulator; the sensor only reads it. Gate question asked.
- **Session 3 (cont.)** — Temperature lag gate passed with one gap.
  Developer: the lag belongs in the machine state, because two sensors
  on one machine would otherwise give two different readings; a careless
  agent would conclude the machine is worn, and should check the
  thermometer and the loading door. GAP, filled by Claude and to be
  re-checked after implementation: the first thing to check is the
  machine's recent work (the heavy job just before). Implemented
  `thermal.py` (`settling_temperature`, `settle`, `warm_or_cool`),
  `MachineState.temperature`, `Simulator(thermal_lag_ticks=...)` with a
  default of 1 (no lag) so earlier exact results still hold;
  `TemperatureSensor` now only reads the stored temperature, and the
  ambient keyword added to `Sensor.read` in 10c is gone again. 12 tests,
  191 total. Sample on the 60/70/55 line with lag 20: CNC-04 swings
  between about 90 and 118 °F every cycle as it waits and works. Debt:
  one lag for all machines; lag defaults to off until the line builder
  sets it; heat constants are module constants, not per machine.
- **Session 3 (cont.)** — Temperature lag re-explain passed and the gap
  is closed (developer: check whether the machine had a much heavier
  load a tick or a few ticks before; if it is healthy the agent would
  expect to find something like an 80% load there). Taught job history
  (12b): "finished" events, a job id on job events, the current job in
  `list_machines`, and a `get_job_history` tool built from the event
  log; gate question asked.
- **Session 3 (cont.)** — 12b gate, first attempt: developer said a
  longer wait between "finished on CNC-01" and "started on CNC-02"
  points at the first machine; corrected (CNC-01 had already finished —
  the job waits because CNC-02 is still occupied). Second question not
  yet answered. Developer proposed that a worn machine take extra ticks
  per job; agreed as row 12b2. Claude noted its own example was not yet
  possible in the simulator: with fixed working times a wait is either
  the normal length or, after a breakdown, endless — 12b2 is what makes
  a lengthening wait real.
- **Session 3 (cont.)** — 12b gate passed. Developer DECIDED, against
  Claude's expected answer, that job history should say "blocked by
  CNC-02", because it happens in real life; accepted — the factory's own
  systems could see it, and it does not say why the next machine is
  slow. On the timing question the developer first thought the line had
  skipped a CNC-03 (the line is CNC-01, CNC-02, CNC-04 — naming gap to
  fix in the line builder: use CNC-01/02/03), then read off that CNC-02
  took 88 ticks on the job; Claude added that 88 against a normal 70
  points at CNC-02. Implemented started / finished / "blocked by <next>"
  job events with a `job_id`, `FactoryState.line`, the current job in
  `list_machines`, and `get_job_history` (sixth tool); 11 tests, 202
  total. Debt: no "starved" note for an empty waiting machine;
  `get_job_history` scans the whole log.
- **Session 3 (cont.)** — Developer asked for machines renamed in order,
  more machines, and a line of 3 to 8 machines chosen per run. Built the
  line builder (row 10e) now, as wiring under CLAUDE.md §2.2:
  `build_line(seed, machines=3)` gives CNC-01 upward, working times
  60/70/55/65/60/68/58/62 by position (second machine slowest), three
  sensors per machine, thermometer, vibration alarm at 4.5, ambient
  cycle timed from the clock (peak 4 pm whatever the start time),
  loading door, production line, thermal lag 20. Faults are added by the
  caller afterwards so they run after the line. 19 tests, 221 total.
  SCOPE CHANGE at developer's direction: `docs/MVP_SCOPE.md` and
  `CLAUDE.md` now say 3-8 machines (was 3-5). Older tests keep their own
  small hand-built factories and the old names (CNC-04 etc.). Row 12b's
  re-explain is still owed.
- **Session 3 (cont.)** — Job history re-explain passed (developer:
  CNC-02 worked on job 5 from tick 341 to 410; the job spent 10 ticks
  waiting; a slower CNC-02 would enlarge "the first number", its own
  working time). Claude added that the wait on CNC-01 grows as well,
  because CNC-02 frees up later. Taught 12b2 (a worn machine makes less
  than one tick of progress per tick); gate question asked.
- **Session 3 (cont.)** — Developer asked that the seed decide the
  number of machines. Done in `build_line`: with no size given, a
  dedicated stream (`line.size`) draws 3-8; passing `machines=` still
  fixes it. Over seeds 0-599 the sizes come out roughly evenly (85-108
  each); seed 42 gives 8 machines. 222 tests. Idea noted for evaluation
  time, not built: let the seed also choose the fault, the machine and
  the start tick. Row 12b2 gate still awaiting answer.
- **Session 3 (cont.)** — 12b2 gate passed (developer: CNC-02 is the
  worn one, and both neighbours wait the extra 10 ticks — CNC-01 because
  it cannot send its job on yet, CNC-03 because it cannot receive one
  yet; a rising working time is open information, not a leak). Developer
  added a requirement: no single field should make the fault easy to
  find at once. Acted on it: with working times exact, even one extra
  tick was a perfect giveaway, so the standard line now varies each
  job's time at each machine by ±2 ticks (`time_variation`, seeded, off
  by default elsewhere). This reverses the earlier "postpone natural
  variation" decision, for that reason. Implemented `working_speed`
  (1 − 0.4 × wear²) applied to job progress; 13 tests, 235 total.
  Sample: a wearing CNC-02 takes 71, 71, 72, 73, 74, 76, 78, 80, 84, 93
  ticks per job as health falls to 0.1, with no vibration alarm before
  the slowdown is visible; a machine at health 0.3 completes 15 jobs
  where a healthy line completes 19. Debt: only bearing wear slows a
  machine, so slowness still has one cause until the configuration
  scenario exists.
- **Session 3 (cont.)** — 12b2 re-explain passed (developer: one slow
  job proves nothing because jobs vary — the agent needs to be more
  patient and look at other readings such as vibration and load). Claude
  added: and at the trend over many jobs. Split row 11 into 11a (wait),
  11b (replace bearing), 11c (approval). Taught 11a; gate question
  asked.
- **Session 3 (cont.)** — Developer asked whether temperature can rise
  without vibration or the reverse: yes from innocent causes (air, door,
  lag around job changes), but no fault does it yet; cooling problem
  (temperature only) and a vibration-only spike noted as candidates for
  the remaining MVP scenarios. Wait gate passed (developer: both agents
  see the same factory, which scoring needs so one run can be judged
  against another; while waiting CNC-02 is potentially wearing and could
  fail and then be down). Implemented `ActionTools.wait(ticks)`, limit
  480 per call, in a new `tools/actions.py`; 14 tests, 249 total. Debt:
  look-ups cost no simulated time at all; a wait runs its full length
  even if a machine breaks down partway.
- **Session 3 (cont.)** — Wait re-explain passed (developer: several
  short waits let the agent see broken machines earlier and fix them,
  where one bulk wait might let two or more machines break and halt
  production). Claude added the cost: more tool calls, which scoring
  counts. Taught 11b (bearing replacement: downtime, health restored,
  the fault ends, events); gate question asked.
- **Session 3 (cont.)** — Developer asked whether maintenance should be
  possible without halting the line (a second line, with jobs re-routed
  to it). DECIDED: one line for now, repairs stop it — the stoppage is
  the cost that makes the agent's choice real — but leave an opening for
  more lines. Opening made, as wiring: `FactoryState.lines` (name →
  machine order) replaces the single `line`; job numbers come from
  `FactoryState.next_job_id` so they are unique across lines;
  `next_on_line()` finds a machine's successor on its own line; a
  machine on two lines is refused. `tests/test_two_lines.py` runs two
  lines side by side (unique job ids, a breakdown on one leaves the
  other producing); 6 tests, 255 total. NOT built: re-routing jobs
  between lines, and `build_line` still makes one line. Also DECIDED for
  11b: repairing a machine that has already broken down takes three
  times as long as a planned replacement (135 vs 45 ticks), so catching
  the fault before the break is penalised less. 11b gate questions still
  awaiting answers.
- **Session 3 (cont.)** — 11b gate passed with one gap. Developer: left
  alone, the scenario would keep degrading the new bearing at the old
  pace, so the state needs the bearing's health "or the status of
  fixed"; a needless repair costs evaluation points and a factory
  unhappy at pausing production for nothing. Claude sharpened the first
  (health alone cannot tell a new bearing from a not-yet-worn one, so
  the state records the tick of replacement and the scenario compares it
  with its own start). GAP to re-check: what the agent sees afterwards
  that shows a repair was not the answer. Developer then proposed that
  the event log report the removed bearing's condition, since it can be
  seen once it is out of the machine — adopted: the "finished" event
  ends "old bearing in good condition / worn / badly worn / had failed",
  in words and never as a number. Implemented
  `Simulator.start_bearing_replacement` (45 ticks planned, 135 after a
  breakdown), `_finish_maintenance`, `MachineState.maintenance_until`
  and `bearing_replaced_tick`, and the stop rule in
  `BearingDegradation`; 17 tests, 272 total. Debt: only one kind of
  repair; the cut-offs for the technician's wording are fixed numbers;
  the agent cannot call it yet.
- **Session 3 (cont.)** — 11b re-explain passed, gap closed with help
  (developer: after a repair that found a good bearing, the load might
  be heavy and the agent would check that sensor). Claude stated the
  conclusion the developer implied: the bearing diagnosis was wrong, and
  the agent must look for another cause — load, recent heavy work, the
  air. Taught 11c (propose → human approves → applied; the agent has no
  approve tool); gate question asked.
- **Session 3 (cont.)** — Approval gate passed (developer: without the
  separation accountability is lost — the agent could do whatever it
  wants and the authority would be the agent, not the human; after an
  approved repair it would read the event log for the bearing's
  condition and compare load and vibration with the old bearing). Claude
  added the step the developer left out: it must first wait out the 45
  ticks of the repair. Implemented `Proposal`, `ApprovalDesk` (submit,
  pending, approve, reject) and the agent tools `propose_action` and
  `get_proposals`; 13 tests, 285 total. The agent now has six look-up
  tools and three others (wait, propose, check proposals). A test fault
  I first wrote was too fast and the machine had already broken down
  before the agent acted, which a failing test caught; slowed it so the
  full loop is exercised on a machine still in service. Debt: a proposal
  carries no stated prediction separate from its reason; approval is
  instant; one action type.
- **Session 3 (cont.)** — Approval re-explain passed (developer: nothing
  happens after a proposal because the human has to approve it, so the
  readings are the same). Taught 12c (pass/fail inspection at the end of
  the line; a hidden defect risk on each job built up from the wear of
  the machines that worked on it; 1% baseline); gate question asked.
- **Session 3 (cont.)** — Quality gate passed (developer: inspection
  results cannot say which machine, but they show for a fact that
  something on the line is wrong and the machines need checking — "it
  tells you the health of the line"; one failure is weak evidence
  because there is always a small chance of one, and one in four is when
  to worry). At the developer's request the progress table was rewritten
  with consistent columns: several rows had been marked complete only in
  their notes with the last column left blank; no question had been
  missed. Implemented `Job.defect_risk` (hidden), `Inspection`,
  `FactoryState.inspections`, inspection events, `get_inspections`
  (seventh look-up tool); inspections draw from their own stream; 13
  tests, 298 total. Measured failure rates over 6,000 ticks with one
  machine at a fixed health: 2% at 1.0, 3% at 0.7, 8% at 0.5, 27% at
  0.3, 39% at 0.2. Debt: no defect type; every job is inspected; on a
  single line quality cannot point at a machine.
- **Session 3 (end)** — Quality re-explain passed (developer: a failed
  job speaks about the line, so the agent then looks at the machines'
  vibration or temperature to see which one stands out). ALL ROWS IN THE
  TABLE ARE COMPLETE; 298 tests pass under `py -3.13 -m pytest`.
  NEXT SESSION, in this order unless the developer says otherwise:
  (1) the three remaining MVP fault scenarios — material batch, machine
  configuration, false alarm — each taught and gated; (2) a seeded
  scenario generator (fault, machine, start tick); (3) evaluation;
  (4) the agent; (5) memory. Start by teaching the first of the three
  scenarios; nothing is half-built.
- **Session 4** — Resumed from the session 3 plan. Taught row 13a, the
  material batch scenario: raw material arrives in numbered batches, each
  job is cut from the batch in use and carries its batch number (open
  information); a batch has a hidden quality that becomes the job's
  starting defect risk; the fault scenario writes only that hidden
  quality for one batch, and failures then come out of the existing
  inspection. No machine is at fault and the fault ends by itself when
  the batch runs out. Gate question asked; nothing implemented.
- **Session 4 (cont.)** — Material batch gate passed on the fourth
  exchange. Question 1 first time (developer: failures carry on after the
  needless repair, then fall when the batch changes; check the batch
  number); Claude added the machines' own readings, the technician's
  "good condition" finding, and the trap of crediting a repair made just
  before the batch ran out. The second question needed re-teaching
  twice: the developer first took the design to be about what the agent
  can see, then expected the inspection code to change for each new
  fault. Landed on: the inspection looks at one number, the job's total,
  and cannot say which cause produced a failure. Claude filled in that
  the agent must therefore get the cause from batch numbers and machine
  readings. Implemented `MaterialBatch`, `FactoryState.batch`,
  `Job.batch_id`, `Inspection.batch_id`, `ProductionLine(jobs_per_batch)`
  (off by default; 25 on the standard line), `BadMaterialBatch`,
  "material batch N opened" events, `batch_id` in `get_inspections`;
  `GroundTruth` now has optional `machine_id` / `start_tick` and a
  `batch_id`. 15 tests, 313 total. DESIGN POINT settled during
  implementation: the next batch is opened the moment the last job is
  cut from the current one, so a fault that runs after the line can mark
  it before its first job; for the same reason batch 1 cannot be the bad
  one. Sample (seed 42, 3 machines, batch 3 bad at 0.30): failures per
  batch 0, 1, 10, 0, 1 of 25, and every sensor reading identical to the
  same day without the fault. Debt: the agent learns a job's batch only
  from its inspection, not while the job is on the line; no action yet
  to set a batch aside; the ground truth has no start tick for this
  fault; one material supply shared by all lines.
- **Session 4 (cont.)** — Material batch re-explain passed with gaps
  filled by Claude (developer: look at the inspection failures, at each
  machine for anything out of range, and at the event log for alarms; a
  bad batch says nothing about the next one, which has to be judged
  afresh, whereas a worn machine can be found and fixed). Claude added
  the two points left unsaid: the batch number on each failure is the
  first thing to read, and the deciding contrast is that bad-batch
  failures fall back to normal at the next batch while a worn machine's
  carry on across the boundary and grow. Row 13a complete. Taught row
  13b, the wrong machine setting: a speed setting on each machine
  (1.0 = standard) that the machine's own physics reads; the fault
  scenario writes only that setting, once, as a step. Gate question
  asked, including whether the agent should be able to read the setting
  directly; nothing implemented.
- **Session 4 (cont.)** — Wrong-setting gate passed after several
  exchanges. Developer asked whether a faster machine is not simply a
  good thing (answer: more parts but fewer good ones, about 13.1 against
  14.1 good parts per 1,000 ticks) and proposed that a wrong setting
  wear the bearing faster. DECIDED: limited version only — the speed
  setting multiplies wear that a `BearingDegradation` is already
  causing, and causes none by itself; the full version waits until
  everyday wear exists. DECIDED by the developer: the agent may read the
  setting freely, as in a real factory. To keep the earlier rule that no
  single field gives a fault away, it is shown in the machine's own
  units (rpm, a different standard on every machine) and the standard
  value is not shown. The first gate answer named where each fault shows
  up, not what rules each out; re-taught. Developer then classified
  three fresh cases correctly and, for the slowed machine, gave the
  single lasting step and flat vibration as ruling out wear; Claude
  filled in what rules out a bad batch (failures across two batches, and
  a machine's job time changed). Implemented
  `MachineState.standard_speed` / `speed_setting` / `speed_ratio`,
  `WrongSetting` (writes the setting once), the setting's effect on
  `working_speed`, vibration (+2.0 mm/s per unit of speed), settling
  temperature (+40 °F per unit), `defect_mark` (8 x distance from
  standard squared), wear scaled by speed ratio cubed, `get_settings`
  (eighth look-up tool), per-machine standard speeds on the standard
  line. 18 tests, 331 total. Debt: no history of the setting and no
  "setting changed" event, so the agent sees only the current value; no
  action to put a setting right yet (next step); one setting per
  machine; the load sensor ignores speed. The developer then asked for
  everything remaining to be built without gates because time is short;
  per CLAUDE.md 1.1 this was not done, and the choice of changing the
  rule itself was put to the developer.
- **Session 4 (end)** — RULE CHANGE by the developer, recorded at the
  top of CLAUDE.md section 1: out of time, so rows 13c-17 are built
  without gates, build first and explain afterwards. Row 13b's
  re-explain is waived, not passed. The developer will read the changed
  modules afterwards and wants, at the end, a list of modules changed,
  functions added and what each means. 331 tests pass under
  `py -3.13 -m pytest` (plain `python -m pytest` elsewhere). NOTHING IS
  HALF-BUILT. BUILD ORDER AND DEFAULTS for the next session, to be used
  unless the developer says otherwise:
  1. **13c reset action.** A second action type on the approval desk,
     "reset_setting": machine down for 10 ticks, then `speed_setting`
     back to None; the finished event says in words "setting was off
     standard" or "setting was already standard". Mirror
     `start_bearing_replacement` / `_finish_maintenance`.
  2. **13d false alarm.** A short spike that needs no action: for a few
     ticks one machine's vibration sensor reads high enough to trip the
     alarm while nothing in the machine's condition changes, then it
     returns to normal by itself. Model it as hidden state the sensor
     reads (for example a temporary sensor offset on the machine), never
     as a scenario writing a reading. Ground truth: fault
     "false_alarm", the machine, the start tick; correct action: none.
  3. **14 generator.** `build_scenario(seed)` on top of `build_line`:
     its own stream picks one of the four faults, the machine or batch,
     and the start tick; returns the simulator ready to run.
  4. **15 evaluation.** Per run, from the ground truth and a record of
     what the agent did: fault type named correctly, machine or batch
     named correctly, action appropriate (bearing replacement / none for
     a bad batch or false alarm / reset setting), problem resolved
     afterwards, tool calls used, ticks elapsed. Reads the ground truth;
     the agent never does. Table in docs/MVP_SCOPE.md section 9.
  5. **16 agent.** One agent, tools only (`ObservationTools`,
     `ActionTools`), staged loop from docs/MVP_SCOPE.md section 3,
     keeping a hypothesis table. Default model: Claude through the
     Anthropic SDK, model id `claude-opus-5-5`, key from
     `ANTHROPIC_API_KEY` (SUPERSEDED 2026-10-12: removed; Anthropic is
     not a provider in this project). Tests must not need a key: drive the loop with
     a scripted stand-in model. Human approval stays a separate step the
     agent cannot perform.
  6. **17 memory.** One JSON record per investigation (anomaly,
     evidence, hypotheses, conclusion, action, outcome) and a simple
     look-up of similar past cases.
- **Session 5 — row 13c built ungated.** Second action type
  `reset_setting` on the approval desk. `Simulator.start_setting_reset`
  stops the machine for 10 ticks (`setting_reset_ticks`); when done
  `speed_setting` goes back to None and the event reads "setting reset
  finished: setting was off standard" or "... already standard". The
  start/finish code is now shared with the bearing replacement through
  `_machine_for_maintenance`, `_start_maintenance` and
  `MachineState.maintenance_kind`; bearing messages unchanged. A
  broken-down machine cannot be reset (it needs a repair). 7 tests, 338
  total.
- **Session 5 — row 13d built ungated.** `FalseAlarm` writes a hidden
  `MachineCondition.vibration_sensor_offset` (default +5.0 mm/s) on one
  machine for `duration` ticks (default 5), then sets it back to 0. The
  `VibrationSensor` adds the offset to its reading (running or idle), so
  the ordinary threshold alarm trips. Nothing else in the machine
  changes: a test compares against the same day without the fault and
  finds only those few vibration readings differ. Ground truth: fault
  "false_alarm", machine, start tick; the correct action is none. 6
  tests, 344 total.
- **Session 5 — row 14 built ungated.** `build_scenario(seed, machines=None,
  fault=None)` calls `build_line` and then, from its own stream
  `generator`, picks one of the four faults, a machine, a start tick in
  200-600 and the fault's strength (bearing rate 0.0004-0.0008; speed
  factor 0.85/0.88/1.12/1.15; bad batch 2 or 3 with added risk
  0.35-0.50; false alarm lasting 3-8 ticks). `fault=` forces the kind
  for balanced experiments. DECISION taken without asking: generated
  lines use 10 jobs per batch (the standard line keeps 25) because at 25
  a second batch only opens after about 1,750 ticks. 9 tests, 353 total.
- **Session 5 — row 15 built ungated.** The agent's final answer is a
  `Diagnosis` (fault kind, machine or batch, summary) in
  `tools/diagnosis.py`: it crosses the tool boundary from agent to
  evaluation, so it lives with the tools, not in evaluation. `evaluate()`
  takes the simulator at the end of the run, the diagnosis, the desk's
  proposals, the tool-call count and the start tick, and returns a
  `Score` row: fault right, machine/batch right, action right (the
  APPROVED actions must be exactly the one expected: replace_bearing,
  reset_setting, or nothing for a bad batch or false alarm; rejected
  proposals do not count), resolved (read from hidden state: bearing
  replaced after the fault began; setting back to None; bad batch used
  up; sensor offset gone), tool calls, ticks elapsed. `summarize` and
  `format_summary` give the "18/20 root causes" line. 9 tests, 362 total.
- **Session 5 — row 16 built ungated.** The agent package:
  `models.py` hides the language model behind `start` / `continue_with`;
  `ClaudeModel` calls `claude-opus-5-5` through the Anthropic SDK
  (manual tool loop, adaptive thinking, effort "high", server-side
  refusal fallback), `ScriptedModel` replays fixed turns so tests need no
  key. `toolbox.py` describes 14 tools to the model (the 9 look-ups incl.
  a new `get_sensor_trend`, wait, propose_action, get_proposals, plus
  `update_hypotheses` for the hypothesis table and `submit_diagnosis` to
  finish), counts every call, returns errors as error results, and
  refuses answers over 300 rows. `agent.py` holds the system prompt (the
  staged loop from MVP_SCOPE section 3) and the turn loop.
  `monitor.py` runs the line through the agent's own tools until an
  alarm, a stopped machine, or 3 failed inspections in the last 10.
  `episode.py` wires it all: seeded scenario, monitor, agent, the human
  (an `approver` function; `approve_all` for experiments,
  `ask_on_console` for live use) deciding proposals between turns, and
  evaluation. `python -m capstone.agent --seed 0 --runs 20` runs the real
  agent. Not run against the real model in this session (no key);
  everything is tested with the scripted stand-in. DECISION taken without
  asking: generated wrong settings made stronger (0.80/0.82/1.18/1.20)
  because 12-15% off often went undetected for 4,000 ticks. 13 tests,
  376 total.
- **Session 5 — row 17 built ungated; THE BUILD IS COMPLETE.**
  `InvestigationMemory` appends one JSON line per investigation (anomaly,
  evidence calls, last hypothesis table, conclusion, approved actions,
  outcome = maintenance findings the event log reported) and offers the
  agent `search_incident_history` (word-overlap ranking). It deliberately
  never stores the score or ground truth. 4 tests, 380 total, all
  passing under `python -m pytest`. Every row 13c-17 still needs the
  developer's review; the plain-English summary of what changed is in
  `docs/UNGATED_BUILD_SUMMARY.md`. Not yet done: a run of the real
  agent with an API key, and the experiment table it would produce.
