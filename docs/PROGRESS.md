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
| 16 | The research agent | n/a | n/a | yes | RETIRED 2026-10-19 (only `monitor.py` and `get_sensor_trend` remain; see R2) | `capstone/agent/` (`models.py`, `toolbox.py`, `agent.py`, `monitor.py`, `episode.py`, `__main__.py`); `tools/observation.py` (`get_sensor_trend`) |
| 17 | Memory | n/a | n/a | yes | RETIRED 2026-10-19 (replaced by `capstone/memory/`, rows A6a-A7b) | `capstone/agent/memory.py` (`InvestigationMemory`, `search_incident_history`), `episode.py` |
| A1 | Agent checkpoint 1: one shared finished-investigation record | yes | yes | yes | yes | `contracts/completed_investigations.py`; notes for A1-A5b are in `docs/PROGRESS_ARCHIVE.md` |
| A2 | Agent checkpoint 2: the inner loop (decide, act, observe, stop) | yes | yes | yes | yes | `agent/loop.py`, `agent/state.py`, `agent/policy.py` |
| A3a | Carrying out a fix is its own tool call | yes | yes | yes | yes | `tools/actions.py` (`execute_action`) |
| A3b | The outer sequence up to a conclusion | yes | yes | yes | yes | `agent/investigation.py` |
| A3c | Asking for the fix and carrying it out | yes | yes | yes | yes | `agent/investigation.py` (`propose`, `execute`) |
| A4 | Did the fix work? (look again after the work) | yes | yes | yes | yes | `agent/investigation.py` (`verify`); see row R1 for a later fix |
| A5a | Where each piece of evidence came from (provenance) | yes | yes | yes | yes | `contracts/provenance.py`, `agent/loop.py` |
| A5b | The finished record and the audit log | yes | yes | yes | yes | `agent/completion.py` |
| A6a | The reflection candidate | yes | yes | yes | yes | `memory/reflection.py` |
| A6b | Remembering what did not work | yes | yes | yes | yes | `memory/policy.py` |
| A6c | The loop joined to the memory gate | yes | yes | yes | in part | `learning.py` (`learn_from`); closing question passed in part, the rest taught |
| A7a | Word search and the safe view of a memory | yes | yes | yes | yes | `capstone/memory/` |
| A7b | The recall tool and its two guards | yes | yes | yes | yes | `providers/recall.py` |
| A8a | The model client and the job table | yes | yes | yes | yes | `providers/chat.py` |
| A8b-1 | An outage is retried, then handed on | yes | yes | yes | yes | `providers/chat.py` (`FallbackClient`) |
| A8b-2 | The prompts for the seven questions | yes | yes | yes | no — closing question not yet asked | `agent/model_policy.py` (`ModelPolicy`, `render`); session note 2026-10-19 (8b-2) |
| R1 | Review fixes of 2026-10-16/17 (loop budgets, tool errors, repair check, trend tool) | n/a | n/a | yes | no — built ungated, developer to review | session notes 2026-10-17 |
| R2 | MVP gap fixes of 2026-10-19 (semantic recall for the agent, section 9 score fields, harness, hand labels, known-answer suite, model limits, maintenance history, tool list) | n/a | n/a | yes | no — built ungated, developer to review | session note 2026-10-19 (MVP gap fixes) |
| R2 | Row cap, unjudged diagnosis, old agent retired, episode runner | n/a | n/a | yes | no — built ungated, developer to review | session notes 2026-10-19; `capstone/episode.py`, `agent/monitor.py`, `evaluation/scoring.py`, `providers/factory.py` |

Every row above with four "yes" marks (or "n/a") is complete: no question is
outstanding on it. Still to build after 12c, from `docs/MVP_SCOPE.md`: the
other three fault scenarios (material batch, machine configuration, false
alarm), then evaluation, then the agent itself.

## Session notes

- **2026-10-19 — MVP gap fixes; built ungated at the developer's direction,
  developer to review (understood: no).** From an audit of `main` against
  `MVP_SCOPE.md`; the developer asked for these to be built directly. One
  commit each:
  1. Semantic recall reaches the agent. PR #1 wrote memories into Chroma
     but nothing read them back: `MemoryService.search` stayed word-only
     and `MemoryRecall` had no caller. `MemoryService(..., recall=)` now
     asks `MemoryRecall` in the configured mode and returns the safe
     `RecalledMemory` view; `build_memory_service(repository, settings)`
     opens one index for promotion and recall.
  2. Section 9 score fields (`evaluation/scoring.py`): what the agent
     recommended even if rejected, and whether that was the right request
     (`recommendation_correct`, apart from `action_correct`); the relevant
     evidence for the true fault (`RELEVANT_EVIDENCE`, evaluator-side) and
     which of it was collected; iterations; the termination reason. Runs
     that ended `model_unavailable` are left out of every reasoning total
     (open since 2026-10-15).
  3. Experiments (`capstone/experiment.py`, `evaluation/labels.py`,
     `evaluation/known_answers.py`): `run_experiment` and
     `python -m capstone.experiment run | label | report`; an append-only
     `LabelBook` of hand labels and `apply_label`, which judges a row's root
     cause from the truth already in it, so a run is scored after it ended;
     eight known-answer cases (two per fault), pinned and run offline with a
     scripted stand-in by `tests/test_known_answers.py`.
  4. Model limits (MVP section 3): `MODEL_MAX_OUTPUT_TOKENS` (2048) sent as
     `max_tokens`, a reply cut off at the limit refused as such;
     `MODEL_REQUEST_SECONDS`, `MODEL_QUESTION_SECONDS`, `MODEL_RETRIES`.
  5. Maintenance history (MVP section 1): `simulator/maintenance.py`, one
     to four past service visits per machine from their own stream, the same
     whatever the fault; tool `get_maintenance_history`.
  6. `MVP_SCOPE.md` section 4 now lists the tools the code has, with a
     mapping from the original eight.
  Not done: no live model run yet (needs keys); `.env.example` does not yet
  list the new settings.

- **2026-10-19 — checkpoint 8b-2 built: the model-backed policy.**
  Pre-check passed on 2026-10-16; built to the design recorded then.
  POST-IMPLEMENTATION UNDERSTANDING IS OUTSTANDING: ask the closing question
  at the start of the next session. Changed:
  1. `contracts/tools.py` `ToolSpec` (name, description, argument schema).
     `providers/factory.py`: `TOOL_ARGUMENTS` (a test keeps it equal to the
     provider's own table), `PROCEDURE_TOOLS` (`propose_action`,
     `get_proposals`, `execute_action`: the loop's fixed procedure, never
     offered to a policy), `tool_spec(name)`, `research_tools()`.
     `providers/recall.py` `RECALL_SPEC`, offered only when memory is given.
  2. `providers/chat.py`: `Attempt(model, outcome)` and
     `FallbackClient.attempts`, every model asked in the latest question
     and what came of it ("answered", "invalid reply", or the outage), kept
     even when a later model answers. This closes the 8b-1 gap: Groq's
     timeouts (uptime) and Mistral's invalid reply (reasoning) are recorded
     apart.
  3. New `agent/model_policy.py`:
     - `render(state)`: the one view every question gets: anomaly, now,
       budget left, open questions, evidence with its ID, the call that
       produced it (from the loop's decision records) and its tick,
       memories marked "FROM MEMORY: a past investigation's belief",
       hypotheses with confidence and cited IDs, conclusion, action, work
       ticks, prediction, and the last 3 failed calls with what to correct.
       No decision records or counters, no list of causes. One evidence item
       shows at most `MAX_EVIDENCE_CHARS` (2,000) characters, with a note.
     - `SYSTEM`: one system prompt per job on a shared `COMMON` preamble (cite
       only IDs shown; one tick is one minute; say what is not known).
       `PHASE`: what `decide` is for in investigate, test and verify (verify
       says only data from after the work counts). The conclude prompt
       lists the approvable actions, never the causes.
     - Answer types: `PlanAnswer`, `NextStep` (`CallTool | Stop`),
       `Interpretation`, `ConcludeAnswer` (conclusion + optional action),
       `Judgement` (outcome and cited IDs only; the prediction is the one
       recorded before the action), `LessonAnswer`.
     - `ModelPolicy(clients, tools)`: one client per job; refuses with
       `ValueError` a call to a tool it did not offer; keeps `calls`, one
       `ModelCall` (job, answered / invalid_reply / no_answer, answered_by,
       attempts) per question; never changes `state`.
  4. `tests/test_model_policy.py` (25): the view; memory labels; failed
     calls shown; no bookkeeping; truncation; no fault kind in any prompt,
     schema or tool description; the client puts the schema in the system
     prompt; each question's answer; tools not offered refused and counted
     against the model; the attempt record through a real `FallbackClient`;
     the policy never changes state; and a whole seed-6 episode run on
     model replies written from the prompt text alone (found, approved,
     fixed, checked "resolved", 14 model questions). CI group "Model policy".
  Measured: the largest prompt in that episode is about 8,400 characters
  (a decide turn with nine evidence items and the tool list).
  Not done: no run against a real model yet; the 60 s budget will likely be
  too short for real models at two questions per tool call.
  Closing question to ask: why does `Judgement` have no prediction field,
  and why does `ModelPolicy` refuse `propose_action` in a decision even
  though the provider would accept it?

- **2026-10-19 — the rest of the review, built ungated; developer to review
  (understood: no).** Changed, in order of the commits:
  1. Row cap (`providers/factory.py` `MAX_ROWS = 300`, in `run_tool`): a
     list answer longer than 300 rows is refused as `invalid_arguments`,
     with "N rows is more than 300; narrow the tick range, or use
     get_sensor_trend or get_sensor_summary". Time does not move. Why: at
     anomaly time one `get_readings` call returned 400-2,000 rows (40-220 KB),
     more than any prompt built from the evidence can carry.
  2. Unjudged diagnosis (`evaluation/scoring.py`): `evaluate(..., judged=False)`
     leaves `fault_correct` and `target_correct` as None instead of counting
     an unlabelled free-text answer as wrong; `summarize` adds `judged`;
     `format_summary` reports root causes out of the judged runs, e.g.
     "7/8 root causes correctly identified (2 not judged)". Actions and
     "resolved" are scored from reality either way.
  3. Old agent retired: `agent/agent.py`, `toolbox.py`, `models.py`,
     `memory.py`, `episode.py`, `tests/test_agent.py`, `tests/test_memory.py`.
     Rows 16 and 17 are marked RETIRED. Kept from them: `monitor.py`,
     `get_sensor_trend` and the tool descriptions.
  4. The runner, new `capstone/episode.py` (outside `capstone/agent`, like
     `learning.py`, because the agent may not import memory):
     `run_episode(seed, policy, fault=, approver=, judge=, memory=, log=,
     budgets=, clock=)` builds the scenario, runs monitoring, runs
     `run_investigation` with a `SimulatorFactoryProvider` (wrapped in
     `RecallingProvider` when memory is given), lets the `approver` decide
     each proposal on the desk, calls `learn_from` when memory and an audit
     log are both given, then `evaluate`. `judge` reads the conclusion text
     and returns a `Diagnosis`; without one the root cause is unjudged, and
     `rescore(result, label)` scores it later from a hand label.
     `EpisodeResult` holds the simulator, so it is the experimenter's and
     never the agent's. `approve_all`, `reject_all`, `ask_on_console`.
     `agent/monitor.py`: `detect_anomaly` (was `wait_for_anomaly`) returns a
     `DetectedAnomaly` (kind `alarm`, `status`, `inspection_failures`, or a
     `routine_check` when nothing shows by tick 4000).
  5. `tests/test_episode.py` (9): whole episodes with a scripted policy and
     no model on seed 6 (bearing wear on CNC-02): found, approved, fixed,
     checked "resolved" and scored 4/4; unjudged without a judge; a later
     hand label; a refusing human leaves the fault; same seed, same episode;
     no hidden words in working memory; a verified fix is audited and
     remembered; monitoring names a symptom, not a cause.
  6. Session notes from 2026-10-12 and earlier moved to
     `docs/PROGRESS_ARCHIVE.md` (this file went from 2,218 to under 650 lines).
  Still open: 8b-2 (the prompts; gated, taught 2026-10-16); an evaluator
  model for the diagnosis, tested against hand labels; a script that runs
  20 seeded episodes and prints the summary once a real policy exists.

- **2026-10-18 — compound challenge builder and feedback assessment.**
  Added `simulator/challenge.py`: `build_challenge()` selects three machines
  and onset using a separate seeded stream, then combines bearing wear/speed
  faults, harmless vibration spike, temperature drift and missing samples.
  Ordinary `build_line()` is unchanged. Tests replay tool calls/observations,
  compare seeds, check sparse histories, hidden fields and supported line sizes.
  README and `docs/SIMULATOR_DIFFICULTY_COMPATIBILITY.md` describe usage, each
  changed module/class/function and limits. Assessed Kanika's feedback there:
  existing configurations are feasible now; cooling failure needs new physics;
  complete agent/evaluator integration is still absent, not just prompt work.
  Delayed information is explicitly excluded by the developer. No investigation
  modules/contracts changed. Understood: no — built ungated, developer to review.
  Verification: 503 tests passed; repository-wide Ruff lint/format and whitespace
  checks passed. First disturbance increment independently passed 498 tests.

- **2026-10-18 — instrument disturbances implemented, delayed records excluded.**
  Developer authorized the harder simulator features except delayed maintenance
  records. `simulator/disturbances.py` adds `SensorDrift` (growing calibration
  bias), `TransientAnomaly` (temporary harmless bias), and `SensorDropout`
  (temporary signal loss), sharing `_SensorDisturbance` window/ground-truth
  handling. Each writes its own `SensorEffect` in hidden machine state;
  overlapping windows do not erase each other. `Sensor.read()` applies offsets;
  `Sensor.available()` controls transmission. `Simulator.step()` draws normal
  noise during dropout but stores/alarms only transmitted samples. State, tools,
  observations and beliefs remain separate. Tests cover timing, causal isolation,
  overlapping effects, actual provider results/alarms, sparse summaries and
  invalid parameters. No investigation tools/contracts changed. Understood: no —
  built ungated, developer to review. Challenge builder is the next increment.

- **2026-10-18 — simulator difficulty interface verification.**
  Added five compatibility cases in `tests/test_difficulty_tool_compatibility.py`
  and findings in `docs/SIMULATOR_DIFFICULTY_COMPATIBILITY.md`. Existing compound
  faults and partial repairs work through unchanged tools; synthetic drift,
  transient and sparse observations fit existing responses. Delayed historical
  event insertion is rejected; publication/occurrence semantics remain unsettled.
  The completed report has one proposed action and no runtime solver is present.
  No production code or new difficulty behavior added, respecting the developer's
  zero-investigation-change condition. No functions/classes added to production
  and no new understanding claimed.

- **2026-10-18 — RAG retry requirement explicitly deferred to Future Work.**
  Moved the agent-directed RAG/repeat-retrieval section into Future Work 1 in
  `docs/MVP_SCOPE.md` and marked it outside the current MVP, not implemented.
  Updated the reference in `docs/EPISODIC_MEMORY.md`. Documentation only;
  no functions/classes added, runtime changes, or understanding claimed.
  The developer explicitly authorized committing and pushing these changes
  to the existing GitHub repository.

- **2026-10-18 — agent-directed RAG repeat-search requirement (documentation only).**
  Updated `docs/MVP_SCOPE.md` and `docs/EPISODIC_MEMORY.md`: the same Nemotron
  investigation agent assesses retrieved evidence and can revise/repeat searches
  when results or a draft answer are insufficient. No separate RAG reasoning
  model. Proposed PostgreSQL/pgvector embeddings remain unimplemented. Recorded
  a three-call default per knowledge gap, overall investigation limits, explicit
  uncertainty on exhaustion, source/attempt tracing, and offline acceptance
  checks. No functions/classes added or runtime behavior changed. This checkout
  has filtered SQL retrieval but no connected agent/RAG loop. Runtime work and
  memory understanding checkpoints remain outstanding; no new understanding
  is claimed.

- **2026-10-17 — second set of review changes; built ungated, developer to
  review (understood: no).** Checked against `main` after the five fixes
  above. Changed:
  1. Repair check (`agent/investigation.py` `verify`, inner `later`): a look
     counts as "after the work" only if the data it asked for also starts
     after the work finished. `starts` maps each evidence ID to the
     `from_tick` of the request that produced it, read from the loop's own
     `DecisionRecord`s; a tool with no range (e.g. `list_machines`) reports
     the factory as it is and still counts. Before: after the wrong machine
     was repaired, a look at tick 945 at ticks 0-99 of the worn machine was
     judged "resolved", and memory would have kept that lesson. Now it is
     "inconclusive". Test:
     `test_a_look_now_at_data_from_before_the_work_does_not_count` (a window
     wholly before, and one that starts before and runs past the work).
     Known edge: `get_job_history` has no range but can describe an old job.
  2. `get_sensor_trend` offered through `providers/factory.py` (new
     `TrendArguments`, new `contracts/observations.py`
     `SensorTrendObservation`): per-block mean/min/max/count. A summary's
     change comes from its two end readings, so it cannot tell slow wear
     from a single jump; a trend can, at under 1/20 of the size of raw
     readings (tested).
  3. `providers/factory.py` `TOOL_DESCRIPTIONS`: a model-readable sentence
     per tool, copied from the old `agent/toolbox.py` so it survives that
     file's retirement. Nothing reads it yet; 8b-2 will. A test keeps it in
     step with the tool table. It lists no causes or fault signatures.
  4. Removed `providers/llm.py` (`LLMProvider`) and the `Investigation`
     record in `contracts/investigations.py`: nothing used them. The ID
     helpers `run_id_for` / `investigation_id_for` stay.
  5. `CLAUDE.md` is now the single line `@AGENTS.md`; `AGENTS.md` names no
     single agent, notes that the gated loop has been in use again since
     2026-10-12, and gives the `uv sync --all-extras` setup.
  6. Table rows A1-A8b-2 and R1 added above from these notes.
  NOT DONE, on purpose: the old agent (`agent/agent.py`, `toolbox.py`,
  `models.py`, `agent/memory.py`, their tests) is not retired yet, because
  `agent/episode.py` imports it and the 2026-10-12 decisions retire it only
  after the runner reuses `episode.py`; `.agents/skills` is kept (Codex
  reads skills only there). Still open from the review: cap or summarise
  evidence before 8b-2 prompts include it; a runner chaining scenario,
  `run_investigation`, `learn_from` and `evaluate`; scoring of the free-text
  diagnosis (hand labels first, per the 2026-10-12 decision); a scripted
  end-to-end test before 8b-2; archiving old session notes.

- **2026-10-17 — five loop and tool-boundary fixes, applied from a review;
  built ungated, developer to review (understood: no).** A review of the loop
  against an agent-workflows book was checked against the code on seeded
  factories with a stand-in model at 3 s per request; these five came out of
  it and were applied as five commits on main. Nothing of 8b-2 is built; the
  one-reply-per-turn cache and the prompt context wait for 8b-2.
  1. `agent/state.py` `Budgets.followup_seconds` (20 s): `check_termination`
     in `agent/loop.py` ends investigate and test with `timeout` once that
     much time is left, so the conclusion, proposal, work and check keep it.
     Before, research could spend all 60 s; the human approved a fix that was
     never carried out, and the run still said `diagnosis_supported`.
  2. `gather(..., interpret=False)` for calls the loop makes itself
     (`get_time` in `observe`, every `followup_call`): still evidence, but
     the policy is not asked to read them. 5 of 19 policy calls in the
     verification fixture were of this kind.
  3. `providers/chat.py`: a request waits 15 s (was 60); `FallbackClient`
     gives one question `max_seconds` = 20 in all, retries and fallback
     included (was up to 244 s); a read timeout says "timed out", not
     "could not be reached".
  4. Tool errors say what to correct. `providers/factory.py` `run_tool`
     splits a bad argument (field and pydantic's message), a tool's own
     refusal (new `tools/errors.py` `ToolInputError`, message passed on) and
     anything else (no detail; new code `invalid_result` for an answer that
     breaks its contract). Sensor names are `Literal`s, so a misspelled one
     is refused instead of returning 0 rows; `DecisionRecord.error` keeps the
     tool's account of a failed call.
  5. `diagnosis_supported` also needs no contradicting evidence;
     `confidence_stalled` ends testing with `no_useful_action` when the last
     3 test results moved confidence by less than 0.05.
  Verification: 848 passed locally (826 + 22 new); Ruff check and format
  passed.

- **2026-10-16 — checkpoint 8b-2 taught, pre-check PASSED; SESSION PAUSED
  HERE (developer moving locations). Nothing of 8b-2 is built.** Asked why
  the prompt shows evidence with IDs, the developer first did not know;
  after a hint (a model citing E9 when only E1-E5 exist) said the IDs let
  the loop verify evidence was not made up, and added that code, not the
  model, assigns the IDs. Correct. PLANNED DESIGN for next session: new
  `capstone/agent/model_policy.py` with `ModelPolicy(clients, tools)`; one
  shared `render(state)` view (anomaly, budget left, open questions,
  evidence with IDs/source/tick, hypotheses with confidence and cited IDs;
  no bookkeeping, no fault list); a system prompt per job; `decide` also
  gets the phase and the research tool list (names, descriptions, argument
  schemas from `providers/factory.py`; not `propose_action`,
  `execute_action` or `get_proposals`; `recall_memories` only when given);
  `interpret` also gets the step and newest evidence. Answer types needing
  wrappers: plan (questions), decide (`CallTool | Stop`), conclude
  (conclusion + optional action), lesson (`Lesson | None`). Then the small
  follow-on: record which models were tried per turn and why each failed.

- **2026-10-16 — checkpoint 8b-1 closing question PASSED (after one
  re-teach).** Asked what happens when Groq times out twice and the Mistral
  fallback sends an invalid reply, the developer first said it would be
  retried and handed on again. Re-taught: a bad reply is never retried or
  handed on; `ValueError` reaches the loop, which records `invalid_decision`
  and asks again on its next turn; episodic memory holds factory lessons,
  not provider failures. The developer then said Mistral's invalid reply
  should count against reasoning quality while Groq's timeouts are only
  uptime. Correct. Checkpoint 8b-1 is complete. Gap found and carried into
  8b-2: `FallbackClient` discards the failures when a later model answers,
  so Groq's timeouts are recorded nowhere; each turn should record which
  models were tried and why each failed. NEXT: 8b-2, the prompts.

- **2026-10-15 — package docstrings; SESSION PAUSED HERE.** At the
  developer's request each `__init__.py` (capstone and its eight packages,
  and tests) now says in a sentence or two what the folder holds and how its
  modules fit together. Documentation only; CI green on `7039e25`. NEXT: the
  8b-1 closing question is asked and NOT YET ANSWERED (Groq times out twice
  on `decide`, the Mistral fallback answers with an invalid reply: what does
  `FallbackClient` do, what does the loop record, which model is counted as
  wrong?). Then 8b-2, the prompts for the seven questions.

- **2026-10-15 — checkpoint 8b-1: an outage is retried, then handed on.**
  8b split in two: 8b-1 (what happens when no model answers) and 8b-2 (the
  prompts for the seven questions, built from working memory). Pre-checkpoint
  passed: asked why an unreachable provider and a reply that breaks the type
  should be handled differently, the developer said the bad reply is the
  model's mistake (it described an action instead of choosing one), and for
  the outage proposed: retry first, then reroute to another provider to be
  named later. DEVELOPER DECISION: retry, then fallback; the fallback is a
  setting, empty by default. Added: an outage that survives both is not the
  agent's fault, so it gets its own stop reason. POST-IMPLEMENTATION
  UNDERSTANDING IS OUTSTANDING. Changes: `providers/chat.py`: `ModelError`
  gains `transient` (unreachable, timeout, HTTP 429 and 5xx: yes; 401, 400:
  no); new `FallbackClient(clients, retries=1, retry_delay=2.0, sleep)` asks
  each model in turn, retries a transient failure once (after a pause),
  moves straight on after a permanent one, never retries or hands on a reply
  that breaks the type (`ValueError` goes to the loop as before), records
  `answered_by`, and when nothing answers raises one `ModelError` naming
  each failure without keys; `clients_for_jobs` now gives each job a
  `FallbackClient` (its own model, then `FALLBACK_MODEL` if set and
  different). `settings.py`: `FALLBACK_MODEL`. `agent/artifacts.py`:
  `TerminationReason.MODEL_UNAVAILABLE`. `agent/state.py`: `stage`, the stage
  now running. `agent/investigation.py`: the stages that ask the policy set
  `stage`; `run_investigation` catches `ModelError` and calls
  `stop_without_a_model`, which sets the stop reason, keeps a conclusion
  already reached or writes "undetermined", and records a "stopped" decision
  at the interrupted stage. Not an invalid decision, not an unproductive
  turn. Tests: 12 new in `tests/test_chat_client.py`, 2 in
  `tests/test_agent_investigation.py`. Still open: the evaluation does not
  yet treat `model_unavailable` runs differently (it should leave them out of
  the agent's reasoning scores); `answered_by` is not yet copied into the
  decision record (8b-2). Verification: 826 passed locally; Ruff passed;
  CI green on `d103eda` (all twelve checks).

- **2026-10-15 — checkpoint 8a closing question PASSED (after one
  re-teach).** Asked why `ask` refuses a reply that does not match the type
  instead of repairing it, the developer first said repairing is a lot of
  work and asking the model again is better (no retry exists yet; that is
  an 8b design point). Re-taught: a repaired answer fills fields the model
  never chose, so code would make the decision and the record would say the
  model made it; refusals are also counted, which measures each model's
  reliability for the job table. The developer then said an unclear reply
  is not a definite answer that can go into the data, only something that
  could lean either way. Completed: a repair would pick the side, so the
  repair code would be the one deciding. Checkpoint 8a is complete. NEXT:
  8b, the model policy: prompts for the seven questions from working memory,
  what happens when a model service is unreachable (`ModelError`), and
  whether to retry a refused reply.

- **2026-10-15 — checkpoint 8a reworked: one generic client, a job table.**
  The developer pointed out that MVP_SCOPE (Provider integration, revised
  2026-10-11) rules out per-provider clients, and asked that any model can
  do any job when settings say which does which. The developer's key file
  holds keys for the six providers in scope (NVIDIA, Groq, Mistral, Gemini,
  Cohere, Cloudflare Workers AI) plus Cloudflare R2 storage keys, and no
  model names. Weighed: LiteLLM (MVP_SCOPE's plan) supports all six but
  installs OpenAI's Python SDK, which CLAUDE.md section 9 forbids; one
  standard-library client reaches all six through their OpenAI-style chat
  endpoints using only the common subset (system and user messages,
  temperature, Bearer key, reply text). DEVELOPER DECISION: the generic
  client; revisit LiteLLM/CrewAI at the multi-agent phase. The design was the
  developer's own, so it served as the pre-check; post-implementation
  understanding is outstanding. Changes: `providers/nvidia.py` renamed to
  `providers/chat.py`: `ChatClient(url, api_key, model)` with the same
  `ask`; `PROVIDERS` (address and key setting for each of the six;
  Cloudflare's address needs `CLOUDFLARE_ACCOUNT_ID`); `JOBS` (the seven
  policy questions); `client_for("provider/model")` (unknown providers,
  including openai and anthropic, refused; a missing key or account ID named
  without its value); `clients_for_jobs(settings)` (one client per job;
  only providers in use need a key). `settings.py`: a key per provider,
  `CLOUDFLARE_ACCOUNT_ID`, `DEFAULT_MODEL` (`nvidia/nvidia/nemotron-3.5-
  lightning-30b-a3b`) and `PLAN_MODEL` ... `LESSON_MODEL` overrides;
  `NVIDIA_MODEL` removed. Tests: `tests/test_chat_client.py` (37, replacing
  the NVIDIA client's 22). Mistake recorded: while tidying, a `git checkout`
  of `settings.py` discarded the new settings; the file was rewritten and the
  full suite re-run before committing. Still open for 8b: `ModelError` is not
  among the loop's `POLICY_ERRORS`; whether each model follows the JSON
  instruction is untested until the live check (8c). Verification: 812
  passed locally; Ruff passed; CI green on `ea66f30` (all twelve checks).

- **2026-10-15 — checkpoint 8a: the NVIDIA model client.** Pre-checkpoint
  passed: the developer said the tools are what the model uses to find the
  cause, while a list of causes would let it use elimination instead of
  investigating; no hints. Added: a list turns an open investigation into
  multiple choice, so the project would measure the list, not the agent.
  POST-IMPLEMENTATION UNDERSTANDING IS OUTSTANDING. Changes: `settings.py`:
  `NVIDIA_API_KEY` (masked, blank = missing) and `NVIDIA_MODEL` (default
  `NVIDIA_DEFAULT_MODEL` = `nvidia/nemotron-3.5-lightning-30b-a3b`); the blank
  check is now `normalize_secret`. New `providers/nvidia.py`: `NvidiaClient`
  (`from_settings`, `ask(system, prompt, answer_type)`) sends one chat request
  to `https://integrate.api.nvidia.com/v1/chat/completions` with the standard
  library (no new dependency; no OpenAI SDK), temperature 0, the answer
  type's JSON schema appended to the system prompt; the reply text has any
  `<think>` block and one code fence removed and is validated against the
  type; anything else raises `ValueError`, never repaired. Service failures
  raise `ModelError` (HTTP status or "could not be reached" only; never the
  key or body); the client's repr hides the key. Sending goes through a
  `Transport` function. Tests: new `tests/test_nvidia_client.py` (22), all
  with a fake transport: request shape; model choice; four reply wrappings
  accepted; non-JSON, rule-breaking, extra-field and non-object replies
  refused; malformed service replies refused; HTTP, unreachable and timeout
  errors give `ModelError` without the key; settings. Open for 8b:
  `ModelError` is not among the loop's `POLICY_ERRORS`, so an unreachable
  service would end an investigation with an exception; and NVIDIA's
  structured-output support for this model is still unverified (8c).
  Verification: 797 passed locally; Ruff passed; CI green on `b474484` (all
  twelve checks).

- **2026-10-15 — memory migration applied to Neon.** The developer named
  the file holding the Neon connection string; a script copied the single
  postgres URL found there into this worktree's git-ignored `.env` as
  `DATABASE_URL` without printing it (host on `aws.neon.tech`, SSL
  required). Before: `alembic current` showed no revision and the public
  schema had no tables (PostgreSQL 18.6). Ran `alembic upgrade head`. After:
  `alembic current` is `0001_episodic_memory (head)`; tables
  `alembic_version` and `episodic_memories` (memory_id UUID,
  investigation_id UUID, category VARCHAR(128), source_tick INTEGER,
  fingerprint VARCHAR(64), payload JSONB), unique keys on fingerprint and
  investigation_id, index on category; 0 rows. The 6b outcome change needed
  no migration (it is inside the JSON payload). Still pending: the SubQ
  audit; checkpoint 8a's question.

- **2026-10-15 — Neon agent skills added; migration still blocked.** At the
  developer's request ran `npx neon@latest skills -s neon -s neon-postgres -y`
  (npm package `neon` 8.7.1, Neon's official CLI, repository
  `neondatabase/neon-pkgs`), then the same with `-a claude-code`. Added
  `.agents/skills/` (OpenCode), `.claude/skills/` (Claude Code), identical
  copies of `neon` and `neon-postgres` from `neondatabase/agent-skills`, and
  `skills-lock.json` recording their source and hashes. Documentation only;
  nothing in `capstone/` uses them. `neon skills update` refreshes them. The
  developer asked that these survive when this worktree's work is merged into
  the main project folder. The Neon migration has NOT been applied: this
  worktree's `.env` has no `DATABASE_URL`; the developer is to add it.
  Checkpoint 8a's pre-implementation question (why the prompt may list tools
  but not possible causes) is asked and not yet answered.

- **2026-10-15 — checkpoint 7b closing question PASSED.** Asked what the
  model could do to get around guard 1 if it chose the label itself, the
  developer said it could write `observable` on a recalled memory and so turn
  the memory into evidence. Added: the same principle as 5a; a guard is only
  as good as the label it trusts, so labels come from the answer's source,
  written by code. Checkpoint 7b is complete, and with it checkpoint 7.
  NEXT: 8, a Nemotron-backed policy with no list of causes in the prompt.

- **2026-10-15 — checkpoint 7b: the recall tool and its two guards.**
  Pre-checkpoint passed: the developer said a recalled memory describes the
  factory in the past, not now (the machine could have a new problem), so it
  can guide where to look but cannot count as evidence for a claim. Added:
  the memory's own tick is old, but the recall answer is stamped with the
  current tick, which is what would have fooled `verify`.
  POST-IMPLEMENTATION UNDERSTANDING IS OUTSTANDING. Changes:
  `contracts/provenance.py`: origin gains `memory`; `MEMORY_SOURCE =
  "memory"` defined once so the loop need not import the provider. New
  `providers/recall.py` `RecallingProvider(factory, memory)`:
  `recall_memories(text, limit 1-10, default 5)` answered from
  `MemoryService.search` with source `memory`, stamped from the factory's
  `get_time`; every other tool passed to the factory unchanged; bad
  arguments give `invalid_arguments`, a failing store `provider_error`
  without its message. `agent/loop.py` `gather`: origin `memory` when the
  answer's source is `memory`, else `observable`. Guard 1,
  `agent/investigation.py` `verify`: only `observable` evidence counts as
  observed after the work. Guard 2, `memory/policy.py`: `rests_on_memory`
  when any cited reference (conclusion, check, action, lesson) has origin
  `memory`; an uncited memory that only guided the search is allowed.
  Tests: new `tests/test_recall_tool.py` (15): answered from memory at the
  factory's tick with no evidence IDs; other tools unchanged; bad arguments
  refused; store errors not leaked; empty result is not an error; recalled
  items labelled `memory` and all others `observable` in a real run; a fix
  cannot be verified by citing a memory dated after the work (shown to fail
  with the guard switched off); a real look still verifies when a memory is
  also cited; the gate refuses a cited memory and allows an uncited one; end
  to end, a verified run whose conclusion cites a memory is not remembered.
  New CI check "Tests: Recall". Not done: no runner hands the agent a
  `RecallingProvider` yet (step 9), and nothing tells a model the tool
  exists (step 8). Verification: 775 passed locally; Ruff passed; CI green
  on `adac0d6` (all twelve checks).

- **2026-10-14 — checkpoint 7b taught; SESSION PAUSED HERE.** Nothing of 7b
  is built. Pre-checkpoint question asked and NOT YET ANSWERED: in the
  example (repair finishes at tick 900, the agent recalls at tick 950 a
  memory that a bearing replacement worked, judges "resolved" citing it),
  why refuse to let the memory confirm this repair? Optional second part:
  the difference between a memory guiding where to look and supporting a
  conclusion. Proposed design, awaiting that answer: new
  `providers/recall.py` `RecallingProvider(factory_provider, memory_service)`
  answers `recall_memories(text, limit 1-10)` from `MemoryService.search`
  with source `memory`, stamped with the factory's current tick, and passes
  every other tool to the factory; `ProvenanceReference.origin` gains
  `memory`; `gather` labels answers whose source is `memory` as origin
  `memory`; guard 1 in `verify`: only `observable` evidence counts as
  looking again (memory-only citations give inconclusive, memory-only
  looking gives not performed); guard 2 at the gate: a candidate whose
  cited evidence includes memory-origin items is refused
  (`rests_on_memory`). NEXT SESSION: ask the 7b question again, then build.

- **2026-10-14 — checkpoint 7a closing question PASSED (after two
  re-teaches).** Asked what searches would return if filler words were
  counted, the developer first thought the search matches whole sentences
  (it matches single words), then that a higher score ranks lower (it ranks
  first). After a worked example (an irrelevant conveyor failure scoring 5
  on "was tried for the" against a relevant vibration success scoring 1),
  the developer said failures would rise to the top, successes would sink
  and might never be picked, and relevance would be almost gone. Known
  weakness kept: "tried" and "check" survive filler removal, so failures
  still get a small boost. Checkpoint 7a is complete. NEXT: 7b, the
  `recall_memories` tool, a `memory` origin label, and the guards that a
  recalled memory never counts as proof a fix worked and never supports a
  new lesson.

- **2026-10-14 — checkpoint 7a: word search and the safe view of a
  memory.** The developer asked whether this is semantic search: no, word
  overlap; paraphrases ("shaking" for "vibration") do not match. Accepted
  for now because memory words are code-written and the factory's tools use
  the same words; semantic search would replace only the scoring step if real
  model queries miss. MCP confirmed as Future Work 2, after the core MVP;
  the provider's one `call` boundary is where it would sit. Pre-checkpoint
  passed after one re-teach: asked what goes wrong if a recalled memory
  carries its evidence IDs, the developer first said the agent would conclude
  before reasoning (anchoring, a 7b concern), then, after the example, that
  evidence numbers mean different things in different investigations, so a
  cited old "E2" would pass the existence check while naming unrelated new
  evidence. POST-IMPLEMENTATION UNDERSTANDING IS OUTSTANDING. Changes:
  `memory/contracts.py` `RecalledMemory` (memory ID, category, symptoms,
  past diagnosis, action, machine, outcome, lesson, source tick; no evidence
  IDs, provenance, confidence, fingerprint or run/investigation IDs). New
  `memory/recall.py`: `words` (normalised, filler words dropped, tool names
  split at underscores), `recalled(memory)` (the view), `search_memories`
  (score = shared words with category, symptoms, action, machine and lesson;
  zero scores dropped; ties by most recent then memory ID).
  `MemoryService.search(text, limit=5)` searches the 100 most recent memories
  the store returns. Nothing the agent can call yet (7b). Tests: new
  `tests/test_memory_recall.py` (10). Simplification: only the 100 most
  recent memories are searched. Verification: 760 passed locally; Ruff
  passed; CI green on `ee59092` (all eleven checks).

- **2026-10-14 — checkpoint 6c closing question PASSED (in part, the rest
  taught).** Asked why `learn_from` asks the model for a lesson only after a
  verified fix, the developer said code provides that information and is
  the source of truth, which is the reason for a failed fix (code writes
  that sentence). Taught the other reason: a rejected proposal or an
  inconclusive check can never become a memory, so a sentence asked for
  there is certain to be discarded and only costs a model call. The rule:
  ask only when the sentence can reach memory. Checkpoint 6c is complete,
  and with it checkpoint 6. NEXT: 7, a memory recall tool with word search.

- **2026-10-14 — checkpoint 6c: the loop joined to the gate.**
  Pre-checkpoint passed after one clarification: the developer said the step
  sits outside the loop so the agent cannot bypass the guards and write to
  the audit log or memory directly, and that the audit line goes first so a
  database failure still leaves the investigation on record (only that
  run's lesson is lost). Clarified: the loop never holds a handle to either;
  the audit log holds unfiltered investigations, not hidden truth.
  POST-IMPLEMENTATION UNDERSTANDING IS OUTSTANDING. Changes: new
  `capstone/learning.py` (above both packages): `learn_from(state, policy,
  memory, log) -> LearningOutcome` refuses an unfinished investigation,
  appends the audit record first, asks `policy.write_lesson` only for a
  verified fix (a model that declines or raises gives no lesson), builds the
  candidate and sends it through `MemoryService.promote`. A store failure is
  raised to the caller after the audit line is written. `LearningOutcome`:
  investigation ID, whether the lesson was requested, the lesson, the gate's
  decision (None when nothing went to the gate). Nothing calls `learn_from`
  automatically yet; the episode runner (step 9) will call it after
  `run_investigation`. Tests: new `tests/test_learning.py` (11), end to end
  through the real simulator and a temporary SQLite store: a verified fix is
  audited and its advice stored as resolved; a wrong-machine repair is
  stored as unresolved in code's words with the model never asked; both
  coexist; a rejected proposal is audited only; a repeated investigation is
  not stored twice (`duplicate_investigation`) though the log keeps both
  lines; a model that declines or fails leaves no memory; a database failure
  still leaves the audit line; an unfinished investigation writes nothing;
  working memory unchanged; `capstone/agent` imports neither
  `capstone.learning` nor `capstone.memory`. Added to the "Reflection" CI
  check; `pyproject.toml` allows the importorskip import order in the new
  test, as for the repository tests. Simplification: the gate's decision is
  returned but not yet written into the audit log. Verification: 750 passed
  locally; Ruff passed; CI green on `9b006a3` (all eleven checks).

- **2026-10-14 — checkpoint 6b closing question PASSED (after one
  re-teach).** Asked why the gate recomputes the failure sentence instead of
  trusting the builder, the developer was unsure but named the main case:
  the model's sentence could get through. Re-taught: the gate is the last
  check before something becomes permanent, so it trusts no producer;
  builders change and multiply, and anything can construct a candidate.
  Same pattern as checkpoint 4 (the loop checks the judge) and 6a (every
  provenance label). On the follow-up (a builder edited to pass the model's
  "wrong diagnosis" sentence), the developer said the gate rejects it as
  not written by code and that without the recheck an incorrect sentence
  would be stored. Corrected: the whole candidate is refused
  (`lesson_not_factual`), nothing is stored, and the gate judges the text,
  not who wrote it. Checkpoint 6b is complete. NEXT: 6c, connect the loop
  to the gate with an end-to-end test.

- **2026-10-14 — checkpoint 6b: remembering what did not work.**
  Pre-checkpoint passed: the developer first asked whether code was now
  deciding if the fix worked; clarified that the agent still finds that out
  by looking again (checkpoint 4) and code only copies its verdict into
  memory, refusing any explanation of why. The developer then said a
  general sentence ("replacing the bearing does not fix high vibration")
  would make a future agent think the repair will not fix its problem, when
  only this repair on this machine failed. Corrected: the sentence holds no
  tick; the time is in `source_tick`. POST-IMPLEMENTATION UNDERSTANDING IS
  OUTSTANDING (closing question asked: why does the gate recompute the
  failure sentence instead of trusting the builder?). Changes:
  `memory/policy.py`: new `failure_lesson(investigation)` ("<action> on
  <machine> was tried for <symptoms> and the check afterwards found it
  unresolved."); `MemoryPromotionPolicy` is now `episodic-v2` and accepts
  two kinds: a verified fix (rules unchanged) and an observed failure, which
  needs an action that was tried (`nothing_was_tried`), the exact
  `failure_lesson` text (`lesson_not_factual`), `diagnosis_assessment`
  unknown (`diagnosis_cannot_be_judged`) and `intervention_worked` False
  (`intervention_outcome_mismatch`); no confidence check for failures, since
  the claim rests on the check. Evidence, provenance, transient-detail and
  hidden-truth checks apply to both. Accepted failures get reason
  `observed_failed_action`. `memory/contracts.py`: `EpisodicMemory.outcome`
  is `resolved` or `unresolved` (inside the JSON payload; no migration).
  `memory/reflection.py`: for a failed check with an action, the sentence is
  `failure_lesson`, and the model's sentence is ignored.
  `docs/EPISODIC_MEMORY.md` updated. Tests: `test_memory_policy.py` +11
  (failure accepted; low confidence still accepted; refuted / supported /
  wrong `intervention_worked` refused; an explanation or generalisation
  refused; nothing tried refused; hidden truth and missing evidence still
  refused; success and failure differ), `test_memory_reflection.py` updated
  (a failed fix is stored whatever the model wrote, naming the machine
  actually repaired, CNC-01). Simplifications: duplicates are by category
  plus sentence, so identical failures are kept once; "no action, but the
  symptom stayed" is still refused. Verification: 739 passed locally; Ruff
  passed; CI green on `31ed1f1` (all eleven checks).

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

Older notes (2026-10-12 and earlier) are in `docs/PROGRESS_ARCHIVE.md`.
