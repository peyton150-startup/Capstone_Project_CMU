# Progress Log

> **2026-10-31 — future-work docs marked with what is built:** Docs only; no
> code, tests or settings changed. An audit of `main` (`af3b7bf`) marks each
> item in `MULTI_AGENT_SURVEY_FUTURE_WORK.md`, `REVIEW_SIGNAL_2026-10-30.md`,
> `TOT_CRITIC_EVALUATION_FUTURE_WORK.md` and
> `SIMULATOR_DIFFICULTY_COMPATIBILITY.md` as ✅ IMPLEMENTED, 🟡 PARTLY
> IMPLEMENTED or ❌ NOT BUILT. Built: P0, the deterministic part of P2,
> cohorts A to D, the difficulty tests, and (stale limits corrected) the
> solver, scoring and four repair actions. Not built: critic anchoring
> ablation, `value` job, safety rules in `why_not_acted()`, P3, P5.
> Understood: no — built ungated, developer to review.

> **2026-10-31 — model sampling and independent critic backup settings:**
> Built ungated at the developer's request (understood: no). `settings.py`
> adds `SamplingOptions`, `PROVIDER_SAMPLING` and `MODEL_SAMPLING` JSON maps,
> plus `CRITIC_FALLBACK_MODEL`. `critic_models` appends only its own backups
> and deduplicates them, preserving legacy critic lists. `providers/chat.py`
> adds exact-model sampling defaults and combines them with provider and model
> overrides in `client_for`; `ChatClient` validates and sends temperature and
> optional top_p. Defaults: NVIDIA Nemotron 3.5 Super VL text 1.0/0.95,
> Cohere Command A 0.3/0.75, Ministral 14B 0/service default; other models
> retain 0/service default. Model overrides win field by field; explicit null
> removes top_p. `.env.example` and [MODEL_CONFIGURATION.md](MODEL_CONFIGURATION.md)
> give copyable settings, precedence and provider references. Tests exercise
> outgoing payloads, investigator and critic fallback routing, quoted `.env`
> JSON, inheritance, invalid values and legacy critic chains. No live model
> tests or master episodes for this change. The developer subsequently
> requested merging PR #146 after verification, superseding the earlier hold.
> No walkthrough understanding is claimed; existing result files are unchanged.

> **2026-10-31 — Cohere JSON-output fallback fix:** The interrupted ToT
> run-2 files saved two cases each. Cohere's HTTP 422 was reproduced live
> on a ToT generation request: `NO_VALID_RESPONSE_GENERATED` ("No valid
> response generated. Try updating messages"). A diagnostic adding
> `response_format={"type": "json_object"}` passed both generation and
> rating and returned three valid hypotheses; ordinary and combined decision
> probes also passed, and a short NVIDIA planning probe answered. These were
> small live diagnostics, not master episodes or an availability guarantee.
> After the change, the actual patched Cohere client also passed generation
> and rating and returned three valid hypotheses, using the same small test state.
> `providers/chat.py` now enables JSON-object mode for Cohere, keeping the
> schema instruction and Pydantic validation. NVIDIA's schema mode is unchanged.
> Tests check the payload, valid answers and refusal of wrong-shaped JSON.
> Built ungated at the developer's request (understood: no). The existing
> interrupted results remain provider-failure records; no episode was rerun.
> Provider reference: [Cohere compatibility API](https://docs.cohere.com/docs/compatibility-api).

> **2026-10-31: docs-only multi-agent survey future work (not implemented):**
> [MULTI_AGENT_SURVEY_FUTURE_WORK.md](MULTI_AGENT_SURVEY_FUTURE_WORK.md) records
> three items from Guo et al. (2024), checked against `main`: (1) a blind-critic
> anchoring ablation, (2) using operator rejection notes, which are stored but
> never read back, and (3) describing the system in the survey's framework for
> the write-up. Linked from P4 and Future Work 3. No code, tests, settings or
> understanding status changed; the paper is not yet in README "Research basis"
> because no change based on it has been made.
> The same PR adds [MANUFACTURING_AGENT_PAPERS_FUTURE_WORK.md](MANUFACTURING_AGENT_PAPERS_FUTURE_WORK.md):
> five items from Hoang et al. (MAKA), Schall (P&ID-grounded validation) and
> Köhle et al. (silent faults), led by a silent-execution hazard and
> action-target checks in `why_not_acted()`. Also docs only.

> **2026-10-30 — terminal progress colors:** Interactive progress output
> highlights beliefs, existing investigation stages, evidence, critic details,
> and conclusions. Redirected output and NO_COLOR remain plain. Display-only;
> no investigation behavior or understanding status changed.

> **2026-10-29 — README technology stack:** Added an overview of the project's
> language, frameworks, model integrations, optional storage, and development
> tools to `README.md`. Documentation only; no behavior or understanding
> status changed.

> **2026-10-29 — docs-only pilot-readiness future work recorded (not implemented):**
> [MVP_SCOPE.md](MVP_SCOPE.md#high-priority-future-work--pilot-readiness-fast-triage-and-the-rest-of-abstention-updated-2026-10-30)
> now prioritizes (1) closing the review-only critic with at most one bounded
> read-only discriminating observation/hypothesis revision, (2) separate
> rapid, read-only preliminary triage from the current 1,200-second deep
> investigation, and (3) deterministic degraded-data/abstention tests using
> existing fault-injection tooling. Each needs its own later implementation
> PR, matched before/after evaluation and safety/latency acceptance tests.
> No agent behavior, simulator, tests or runtime settings changed here.

> **2026-10-29 — audit of the eight most recently merged PRs** (at main
> commit `7ef7b61`): all already have detailed entries below. This index links
> each change to its record without changing its understanding status:
>
> - #126: C1b walkthrough after merge; post-understanding remains no.
> - #118: KA-01/02 critic results and KA-03 skipped-critique finding; the
>   follow-up was implemented in #122.
> - #125: README technology stack (the note above).
> - #123: degraded-case matrix and abstention scorecard, row D2; closing
>   question outstanding; not run live.
> - #122: critic before conclusions and up to five hypotheses, row C1b;
>   post-understanding remains no, as recorded in #126.
> - #120: opt-in timed sensor blackout, row D1; closing question outstanding;
>   not run live.
> - #121: experiment/build responsibility split in the session notes.
> - #119: opt-in critic follow-up, row C2r; closing question outstanding;
>   not run live. #122 later changed which hypothesis K1 tests when the critic
>   objects and favours a non-leading hypothesis.
>
> #124 and #117 were open at this audit; their changes are not yet on main.
>
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
| 13b | Machine setting and a wrong setting (fault scenario 3) | yes | yes | yes | yes (after one re-teach, 2026-10-20) | `state.py` (`speed_setting`), `scenarios.py` (`WrongSetting`, `defect_mark`), `sensors.py`, `thermal.py`, `line.py`, `tools/observation.py` (`get_settings`); re-explain waived for time on 2026-10-06, done on 2026-10-20 (session note) |
| 13c | Action: put a machine's setting right (via the approval desk) | yes (after the build) | n/a | yes | yes (after one re-teach) | `simulator.py` (`start_setting_reset`, `_start_maintenance`), `state.py` (`maintenance_kind`), `tools/actions.py` (`reset_setting`) |
| 13d | False alarm / transient anomaly (fault scenario 4) | yes (after the build) | n/a | yes | yes (after one hint) | `state.py` (`MachineCondition.vibration_sensor_offset`), `sensors.py`, `scenarios.py` (`FalseAlarm`) |
| 14 | Seeded scenario generator (fault, machine or batch, start tick) | yes (after the build) | n/a | yes | yes | `capstone/simulator/generator.py` (`build_scenario`, `FAULTS`) |
| 15 | Evaluation | yes (after the build) | n/a | yes | yes | `capstone/evaluation/scoring.py` (`evaluate`, `Score`, `summarize`), `capstone/tools/diagnosis.py` (`Diagnosis`) |
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
| A6c | The loop joined to the memory gate | yes | yes | yes | yes (gap filled 2026-10-22) | `learning.py` (`learn_from`); closing question passed in part on 2026-10-14; the rest answered back on 2026-10-22 |
| A7a | Word search and the safe view of a memory | yes | yes | yes | yes | `capstone/memory/` |
| A7b | The recall tool and its two guards | yes | yes | yes | yes | `providers/recall.py` |
| A8a | The model client and the job table | yes | yes | yes | yes | `providers/chat.py` |
| A8b-1 | An outage is retried, then handed on | yes | yes | yes | yes | `providers/chat.py` (`FallbackClient`) |
| A8b-2 | The prompts for the seven questions | yes | yes | yes | yes | `agent/model_policy.py` (`ModelPolicy`, `render`); session note 2026-10-19 (8b-2) |
| R1 | Review fixes of 2026-10-16/17 (loop budgets, tool errors, repair check, trend tool) | yes (after the build) | n/a | yes | yes | session notes 2026-10-17 |
| R3 | MVP gap fixes of 2026-10-19 (semantic recall for the agent, section 9 score fields, harness, hand labels, known-answer suite, model limits, maintenance history, tool list) | yes (after the build) | n/a | yes | yes | session note 2026-10-19 (MVP gap fixes) |
| R2 | Row cap, unjudged diagnosis, old agent retired, episode runner | yes (after the build) | n/a | yes | yes (after one re-teach) | session notes 2026-10-19; `capstone/episode.py`, `agent/monitor.py`, `evaluation/scoring.py`, `providers/factory.py` |
| A8c | Provider benchmark: each model measured alone, from real episodes | yes | yes | yes | yes | `capstone/benchmark.py`; `providers/chat.py` (`Attempt.seconds`); no real model run yet |
| A8d | Runtime limits: a model question gets only its stage's time left; a total size for the evidence in a prompt | yes | yes (second try, after one re-teach) | yes | yes (after one re-teach) | `agent/loop.py` (`ask_policy`, `OutOfTime`), `agent/state.py` (`research_seconds`, `seconds_for_question`), `agent/model_policy.py` (`evidence_section`, `MAX_EVIDENCE_SECTION_CHARS`), `providers/chat.py` (`max_seconds`); session note 2026-10-19 (A8d) |
| A9a | NVIDIA embeddings for memory search (nemotron-3-embed-1b) | yes | yes (after one re-teach) | yes | yes (after two re-teaches) | `providers/embeddings.py` (`NvidiaEmbedder`, `embedders_for`), `memory/semantic.py` (`IndexModelMismatch`, `open_configured_index`, two-role `ChromaMemoryIndex`), `settings.py` (`EMBEDDING_MODEL`), `memory/backfill.py` (`--rebuild`); session note 2026-10-20 (A9a) |
| A9b | The decide answer as one flat object (no union to nest) | yes | yes (after one re-teach) | yes | yes (after one re-teach) | `agent/model_policy.py` (`NextStep`, `NextStep.decision`, the decide prompt); session note 2026-10-20 (A9b) |
| E1 | Experiment records keep each run's model questions and wall-clock time | yes | yes | yes | yes | `capstone/experiment.py` (`CallSummary`, `summarize_calls`, `format_model_calls`); session notes 2026-10-19 and 2026-10-20 (E1) |
| E2 | Experiment records keep what memory stored and what each run recalled | yes | yes | yes | yes | `capstone/evaluation/memory.py` (`recalled_in`, `cited_in`, `build_use_records`), `capstone/experiment.py` (`memory_records`, `format_memory`); session note 2026-10-20 (E2) |
| E3 | An unnecessary intervention counted apart from a missed fix | yes | yes | yes | yes | `capstone/evaluation/scoring.py` (`Score.unnecessary_actions`, `summarize`), `capstone/experiment.py` (`extra=`); session note 2026-10-20 (E3) |
| E4 | A fixed set of held-out seeds for reported numbers | yes | yes | yes | yes | `capstone/experiment.py` (`HELD_OUT_SEEDS`, `held_out_cases`, `run --held-out`); session note 2026-10-20 (E4) |
| E5 | Scoring a run with several true faults (causes, distractors, partial credit) | yes | yes | yes | yes | `capstone/evaluation/scoring.py` (`Cause`, `CAUSE_KINDS`, `judge_causes`, `judge`, `Score.causes`/`fully_right`), `capstone/evaluation/labels.py`; session note 2026-10-20 (E5) |
| R4a | Scoring-integrity tests: scoring changes nothing, repeats exactly, stays right later | yes (after the build) | n/a | yes | yes (after one re-teach) | `tests/test_scoring_integrity.py`; session note 2026-10-20 (R4a) |
| R4b | Evidence-vs-reasoning miss label on each wrong diagnosis | yes (after the build) | n/a | yes | yes | `evaluation/scoring.py` (`Score.miss_kind`, `EVIDENCE_MISS`, `REASONING_MISS`), `experiment.py`; session note 2026-10-20 (R4b) |
| R4c | Rule-based diagnostic baseline (the yardstick for the agent) | yes (after the build) | n/a | yes | yes (after one re-teach) | `capstone/baseline.py` (`diagnose`, `run_baseline`, `Verdict`); session note 2026-10-20 (R4c) |
| R4d | Unreliable tools on a fixed schedule (timeouts, gaps, a stale record) | yes (after the build) | n/a | yes | yes (after one re-teach) | `providers/hazards.py` (`UnreliableProvider`, `Timeout`, `Gap`, `StaleRecord`, `standard_hazards`, `HazardReport`), `episode.py`, `experiment.py`; session note 2026-10-20 (R4d) |
| R4e | Evidence-completeness stop: an open question on a current explanation blocks the automatic "supported" stop | yes (after the build) | n/a | yes | yes | `agent/loop.py` (`diagnosis_supported`); session note 2026-10-20 (R4e) |
| L1 | Live runs finish: User-Agent for Groq, the fallback keeps its share of a question's time, a stage deadline is a timeout, measured limits, failure reasons in records | yes (after the build, 2026-10-22) | n/a | yes | yes | `providers/chat.py` (`USER_AGENT`, `FallbackClient.ask`, `ModelError.out_of_time`), `agent/loop.py` (`ask_policy`), `settings.py`, `agent/state.py` (`Budgets`), `experiment.py` (`CallSummary.outage_reasons`); session note 2026-10-20 (L1) |
| E6 | The compound challenge in experiments (a case names the scenario kind; KA-09) | yes (after the build, 2026-10-22) | n/a | yes | yes | `episode.py` (`build_world`, `STANDARD`, `CHALLENGE`, `SCENARIO_KINDS`, `run_episode(kind=)`), `evaluation/known_answers.py` (`KnownCase.kind`, KA-09), `experiment.py` (`Case.kind`, `challenge_cases`, `run --challenge`, `several_faults`, `report`); session note 2026-10-20 (E6) |
| L2 | Benchmark under the real limits; limits set from it; retries back off | yes (after the build, 2026-10-22) | n/a | yes | yes (re-checked 2026-10-22) | `benchmark.py` (`single_model_clients`, `run_model`, `EpisodeRecord.wall_seconds`, `ModelReport.concluded`/`median_episode_seconds`/`outage_reasons`, `Limits`, `suggested_limits`, `format_limits`, `--timeout-seconds`), `providers/chat.py` (`FallbackClient.ask` pauses), `settings.py` (`MODEL_RETRIES` 3), `agent/state.py` (`Budgets` 1200/400), `docs/benchmarks/2026-10-20.md`; session notes 2026-10-20 (L2) |
| L2b | The prompts show the time left and how to spend the budget | yes (after the build, 2026-10-22) | n/a | yes | yes | `agent/model_policy.py` (`render` BUDGET LEFT seconds, `COMMON` pacing rule, `decide` stop case, `LOW_CALLS`, `LOW_BUDGET_NOTE`); session note 2026-10-21 (time left) |
| L3 | Requesty and xKiro as providers (model routers); their free models benchmarked | yes (after the build, 2026-10-22) | n/a | yes | yes | `providers/chat.py` (`PROVIDERS` requesty, xkiro), `settings.py` (`REQUESTY_API_KEY`, `XKIRO_API_KEY`), `.env.example`, AGENTS.md section 9, `docs/benchmarks/2026-10-21-routers.md`; session note 2026-10-21 (L3) |
| L4 | Why a reply was invalid is recorded (cut off, not JSON, wrong shape, tool not offered) | yes (after the build, 2026-10-22) | n/a | yes | yes (re-checked 2026-10-22) | `providers/chat.py` (`INVALID_REPLY`, `invalid_outcome`, `is_model_outcome`), `agent/model_policy.py` (`_refuse`), `experiment.py` (`CallSummary.invalid_reasons`, report line), `benchmark.py` (`ModelReport.invalid_reasons`); session note 2026-10-21 (L4) |
| L5 | NVIDIA is asked to keep replies to the answer type's JSON schema (structured output) | yes (after the build, 2026-10-22) | n/a | yes | yes | `providers/chat.py` (`Provider.structured_output`, `ChatClient(structured_output=)`, `response_format`); session note 2026-10-21 (L5) |
| L6 | LLM7 and Kilo Code as providers; their free models checked (Z.ai checked and dropped) | yes (after the build, 2026-10-22) | n/a | yes | yes | `providers/chat.py` (`PROVIDERS` llm7, kilo), `settings.py` (`LLM7_API_KEY`, `KILO_CODE_API_KEY`), `.env.example`, AGENTS.md section 9, `docs/benchmarks/2026-10-21-llm7-kilo.md`; session note 2026-10-21 (L6) |
| L7 | The request limit covers the whole request (a watchdog thread), not each read | yes | yes (after one correction) | yes | yes (walkthrough 2026-10-23: Q1, Q2 after one re-teach, Q3 corrected) | `providers/chat.py` (`run_with_deadline`, `urllib_transport`); session note 2026-10-22 (L7) |
| G1 | The memory gate refuses a "resolved" lesson when no action was taken (policy episodic-v3) | yes | yes (after one correction) | yes | yes (walkthrough 2026-10-24: Q1 and Q3 corrected, Q2 after one re-teach) | `memory/policy.py` (`no_action_taken`, version), `learning.py` (`learn_from`); session note 2026-10-24 (G1) |
| M1 | The machine manual (SIM-CNC-001) and the `search_manual` tool (RAG over a fixed reference) | yes (design discussed 2026-10-22) | n/a | yes | yes (Q3 gap filled 2026-10-22; walkthrough Q1 right, Q2 corrected) | `manual/sections.py` (`ManualSection`, `parse_manual`, `check_no_leaks`, `load_manual`), `manual/index.py` (`KeywordManualSearch`, `ChromaManualIndex`, `open_manual_index`), `providers/manual.py` (`ManualProvider`, `MANUAL_SPEC`), `evaluation/manual.py`, `episode.py`, `experiment.py` (`--manual`), `contracts/provenance.py`, `agent/loop.py`, `agent/model_policy.py`, `memory/policy.py`; session note 2026-10-22 (M1) |
| C2 | Course Module 2 gap note (working memory, episodic memory, tools, loops) | yes (after the build, 2026-10-22) | n/a | yes (docs) | yes | `docs/COURSE_MODULES.md`; session note 2026-10-20 (Module 2) |
| C4 | Course Module 4: opt-in tree-of-thought hypothesize step | yes (after the build, 2026-10-22) | n/a | yes | yes | `agent/tree_of_thought.py` (`TreeOfThoughtPolicy`, `GENERATE`, `VALUE`, `prune`, `Thought`), `experiment.py` (`run --tree-of-thought`); session note 2026-10-20 (Module 4) |
| FD | Experiment failure diagnostics: every model attempt kept, recovered failures shown | yes (after the build, 2026-10-22) | n/a | yes | yes (re-checked 2026-10-22) | `experiment.py` (`CallSummary.details`, `format_call_failures`, `save_record`), `evaluation/scoring.py`; session note 2026-10-20 (failure diagnostics) |
| C3a | Memory comparison command: the same cases with no memory, keyword and semantic recall | yes (after the build, 2026-10-22) | n/a | yes | yes (re-checked 2026-10-22) | `capstone/memory_comparison.py` (`MODES`, `memory_for`, `compare_memory`, `mode_of`, `compare_report`); session note 2026-10-20 (Module 3, piece 1) |
| C3c | Memory comparison made fair: strict semantic mode, outage runs left out, factory calls apart from searches, failed searches shown, runs interleaved by case | after the build (built ungated at the developer's request; PR #74 walkthrough 2026-10-26) | n/a | yes | yes (walkthrough 2026-10-26: Q1 after one correction, Q2 after two re-teaches, Q3 corrected) | `memory/recall.py` (`SemanticRecallFailed`, `MemoryRecall(fallback=...)`), `experiment.py` (`ExperimentRecord.factory_calls`, `NOT_FACTORY`, `count_factory_calls`, `run_experiment(start=...)`), `memory_comparison.py` (`memory_for`, `compare_memory`, `failed`, `mode_line`, `case_line`); session note 2026-10-26 (C3c) |
| C3b | Bounded memory search: no repeated search, at most three per investigation, each recorded | yes (after the build, 2026-10-22) | n/a | yes | yes | `providers/recall.py` (`RecallingProvider`, `MAX_SEARCHES`, `REPEATED_SEARCH`, `SEARCHES_SPENT`), `evaluation/memory.py` (`build_search_records`); session note 2026-10-20 (Module 3, piece 2) |
| D1 | Near-duplicate threshold measurement tool (provisional 0.909) | yes (walkthrough, 2026-10-22) | n/a | yes | yes (after corrections) | `capstone/memory/duplicate_threshold.py`; session notes 2026-10-22 |
| T1 | TypeSafe Jev client and the auto-labeller (proposed diagnosis labels, compared with hand labels) | yes (pre-merge walkthrough, 2026-10-23) | n/a | yes | yes (after corrections: Q1 cost of speculative questions, Q2 why truth would bias labels) | `providers/typesafe.py` (`Noul`, `Choice`, `JudgmentClient`, `read_judgments`, `judgment_client`), `evaluation/auto_label.py` (`propose`, `Proposal`, `agreement`, `conclusions`, `main`), `settings.py` (`TYPESAFE_API_KEY`, `TYPESAFE_MODEL`), `.env.example`, AGENTS.md section 9, `docs/benchmarks/2026-10-23-jev-auto-labels.md`; session note 2026-10-23 (T1) |
| F1 | Bearing progression: opt-in three-day profile (quiet stretch, onset, steeper ramp) | yes (after the build: pre-merge walkthrough 2026-10-26) | n/a | yes | yes (walkthrough 2026-10-26: Q1 in part, corrected; Q2 mostly, corrected; Q3 after one re-teach) | `simulator/scenarios.py` (`BearingDegradation` `onset_health`, `quiet_factor`), `simulator/generator.py` (`BEARING_PROFILES`, `THREE_DAY_*`, `build_scenario(bearing_profile=)`), `docs/benchmarks/2026-10-26-bearing-three-day.md`; session note 2026-10-26 (F1) |
| LV | Live progress view in the terminal: a watcher hook in the loop and `python -m capstone.progress` | after the build (built ungated at the developer's request; PR #81 walkthrough 2026-10-26) | n/a | yes | yes (walkthrough 2026-10-26: Q1 after a re-teach, Q2 after a re-teach, Q3 corrected) | `agent/loop.py` (`InvestigationDeps.watch`, `notify`), `agent/investigation.py` (`staged`, notify before the human's review and after a model stop), `episode.py` (`run_episode(watch=...)`), `progress.py` (`ProgressView`, `step_line`, `truth_lines`, `watch_episode`, `main`); session note 2026-10-26 (LV) |
| F2 | Machine power in kW (`PowerSensor`, standard on every machine, offered to the agent) | yes (after the build: pre-merge walkthrough 2026-10-26) | n/a | yes | yes (walkthrough 2026-10-26: Q1 in part, corrected; Q2 after one hint; Q3 right) | `simulator/sensors.py` (`PowerSensor`), `simulator/line.py`, `providers/factory.py` (`MachineSensor`, tool descriptions), `simulator/disturbances.py`; session note 2026-10-26 (F2) |
| F3 | Fault-pack registry: the four faults described once (`capstone/faults.py`), no behaviour change | yes (after the build: pre-merge walkthrough 2026-10-26) | n/a | yes | yes (walkthrough 2026-10-26: Q1 in part, corrected; Q2 right after one correction; Q3 after a re-teach) | `faults.py` (`FaultPack`, `AgentSide`, `EvaluatorSide`, `FaultPlace`, `PACKS`, `BY_KIND`, `agent_side`, `Relevant` moved here), `simulator/generator.py`, `tools/diagnosis.py`, `tools/actions.py`, `evaluation/scoring.py`, `baseline.py`; session note 2026-10-26 (F3) |
| F4 | Servo-drive fault pack: worn axis drive, following-error sensor and alarm, drive replacement; only when forced | yes (after the build: pre-merge walkthrough 2026-10-26) | n/a | yes | yes (walkthrough 2026-10-26: Q1 in part, completed; Q2 right; Q3 right, with additions) | `simulator/state.py` (`axis_health`, `axis_replaced_tick`), `simulator/scenarios.py` (`AxisDriveWear`, `DEFECT_FROM_AXIS`), `simulator/sensors.py` (`FollowingErrorSensor`), `simulator/line.py`, `simulator/simulator.py` (`start_servo_drive_replacement`), `tools/actions.py`, `providers/factory.py`, `faults.py` (servo pack, `in_default_draw`, `DEFAULT_DRAW`), `simulator/generator.py`; session note 2026-10-26 (F4) |
| F5 | Hydraulic-leak fault pack: hydraulics on some machines (observable), pressure sensor and low-pressure alarm, seal repair; only when forced | yes (after the build: pre-merge walkthrough 2026-10-26) | n/a | yes | yes (walkthrough 2026-10-26: Q1 in part, corrected; Q2 right, with an addition; Q3 after a re-teach) | `simulator/line.py` (`HYDRAULIC_POSITIONS`), `simulator/state.py` (`has_hydraulics`, `hydraulic_health`, `hydraulics_repaired_tick`), `simulator/scenarios.py` (`HydraulicLeak`, `DEFECT_FROM_HYDRAULICS`), `simulator/sensors.py` (`HydraulicPressureSensor`), `simulator/events.py` (`ThresholdAlarm(below=)`), `simulator/simulator.py` (`start_hydraulic_repair`), `tools/observation.py`, `tools/actions.py`, `contracts/observations.py`, `providers/factory.py`, `faults.py`; session note 2026-10-26 (F5) |
| L8 | A chain of fallback models (FALLBACK_MODEL takes several, in order); Cohere's output cap | yes (after the build, 2026-10-28) | n/a | yes | no — walkthrough done 2026-10-28: Q1 right; Q3 in part (Cohere refused the request; why the cap is per provider); mark left for the developer | `settings.py` (`fallback_models`), `providers/chat.py` (`clients_for_jobs`, `Provider.max_output_tokens`, `_capped`); session note 2026-10-26 (L8) |
| L9 | `experiment run` shows the live progress view by default (`--quiet` to turn it off), without the truth | yes (after the build, 2026-10-28) | n/a | yes | no — walkthrough done 2026-10-28: Q2 half right (the copy), the crash guard added; mark left for the developer | `experiment.py` (`run_experiment(watch=)`, `--quiet`); session note 2026-10-26 (L9) |
| A10 | The policy's own recommendation, and why an intervention was lowered, are recorded (MAX-HIGH change 1) | yes (after the build, 2026-10-28) | n/a | yes | no — walkthrough done 2026-10-28: Q1 in part, corrected; Q2 (b) right, (a) and (c) corrected; Q3 in part, corrected (session note 2026-10-28); mark left for the developer | `agent/investigation.py` (`why_not_acted`, `check_conclusion`, `conclude`), `agent/state.py` (`policy_recommendation`, `recommendation_lowered`), `experiment.py` (`ExperimentRecord` fields, `overruled_text`); session note 2026-10-26 (A10) |
| A11 | The conclude prompt states the bar in force (change 2); the bar is a setting, MIN_ACTION_CONFIDENCE (change 3) | yes (after the build, 2026-10-28) | n/a | yes | no — taught together with A13 on 2026-10-28 (see A13); mark left for the developer | `agent/state.py` (`action_confidence_needed`), `agent/loop.py` (`ask_policy`), `agent/model_policy.py` (`action_bar_note`, `conclude`), `settings.py` (`min_action_confidence`), `episode.py`; session note 2026-10-26 (A11) |
| A12 | Configurable questions per step: STEP_QUESTIONS=1 combines interpretation and next decision; 2 retains separate questions | yes | yes (2026-10-27: updated beliefs and requested tool; code decides what is allowed) | yes | no — walkthrough done 2026-10-28: closing question in part (named tracing, not the stop checks), follow-up unsure then corrected; mark left for the developer | `agent/policy.py`, `agent/model_policy.py`, `agent/loop.py`, `agent/state.py`, `settings.py`, `episode.py`, `experiment.py`; session note 2026-10-27 (A12) |
| A13 | STATE_ACTION_BAR: show or hide the action threshold in prompts, with enforcement unchanged | yes (after the build, 2026-10-28) | no — built ungated, developer to review | yes | no — walkthrough done 2026-10-28: Q1 right except what the record shows; Q2 right; Q3 conclusion not supported by the repo's notes, corrected; mark left for the developer | `settings.py`, `agent/state.py`, `agent/loop.py`, `agent/model_policy.py`, `episode.py`, `experiment.py`; session note 2026-10-27 (A13) |
| A14 | Prompt guidance: one discriminating check before stopping with an uncertain leading explanation | yes (after the build, 2026-10-28) | no — built ungated, developer to review | yes | no — walkthrough done 2026-10-28: Q2 mostly right, missed that waiting is the one tool that changes the factory; mark left for the developer | `agent/model_policy.py` (`SYSTEM["decide"]`); session note 2026-10-27 (A14) |
| A15 | Prompt guidance: consult an available manual before recommending a repair | yes (after the build, 2026-10-28) | no — built ungated, developer to review | yes | no — walkthrough done 2026-10-28: Q1 misread at first, then right; Q3 right first step (the trace), checks added; mark left for the developer | `agent/model_policy.py` (`manual_use_note`, `decide`, `interpret_and_decide`); session note 2026-10-27 (A15) |
| EV1 | Configurable full-episode evaluation harness and single-agent master baseline | yes (after the build, 2026-10-28) | n/a (built first, taught after) | yes (baseline run 2026-10-28: 3 of 9 right) | partly — two walkthroughs on 2026-10-28. One (session note 2026-10-27, EV1): Q1 wrong, corrected; Q2 mostly right, completed; Q3 not answered, re-taught, follow-up check corrected; re-check of Q3 owed. The other (session note 2026-10-28, walkthroughs): Q1 in part, corrected; Q2 right, with an addition; Q3 wrong at first, corrected | `capstone/evals.py`, `evals/scenarios.json`, `experiment.py` (`AgentStep`), `agent/state.py`, `agent/model_policy.py`, `tests/test_evals.py`; session note 2026-10-27 (EV1) |
| C1 | Critic, review only: a second model judges the two leading hypotheses between `test` and `conclude` and changes nothing in the run (first multi-agent role) | yes (design conversation 2026-10-28) | yes per the build plan (pre-check 2026-10-28); no session note records it here, developer to confirm | yes (tests only; no live run) | no - pre-merge walkthrough done 2026-10-28 (PR #106): Q1 outcome right, mechanism and record filled in; Q2 `started_at` right, wrongly said research loses the time (it is the follow-up reserve), corrected; Q3 not sure at first, taught, then the check right (accepted) with the reason mixed up, corrected (session note 2026-10-28, C1); mark left for the developer | `settings.py` (`critic`, `critic_model`, `critic_seconds`, `critic_models`), `providers/chat.py` (`critic_client`), `agent/artifacts.py` (`Objection`, `CritiqueResult`, `CritiqueRecord`), `agent/critic.py` (`Critic`, `CRITIC_SYSTEM`, `critique_view`, `top_two`), `agent/investigation.py` (`critique`, graph edge), `agent/loop.py` (`InvestigationDeps.critic`, `critic_seconds`), `agent/state.py` (`critique`), `episode.py`, `experiment.py`, `progress.py`, `evals.py`; session note 2026-10-28 (C1) |

| C2r | Critic follow-up (`recheck`): one read-only reading where the critic pointed, when it objects or agrees below the action bar; opt-in `CRITIC_FOLLOWUP` | yes (2026-10-29) | yes (2026-10-29, after one correction: a normal reading means "not confirmed", not "no action needed") | yes | no — closing question outstanding | `agent/investigation.py` (`recheck_trigger`, `recheck`, graph edge `critique -> recheck -> conclude`), `agent/artifacts.py` (`RecheckRecord`), `agent/state.py` (`recheck`), `agent/loop.py` (`InvestigationDeps.critic_followup`), `settings.py` (`critic_followup`), `episode.py`, `experiment.py` (`ExperimentRecord.recheck`); session note 2026-10-29 (C2r) |
| C1b | Critic before every conclusion, shown every hypothesis (up to five) | yes (2026-10-29) | yes (2026-10-29: which `favoured` is still refused, and why; right, the reason corrected) | yes | no - walkthrough done 2026-10-29, after the merge at the developer's request (PR #122): Q1 mostly right, the record's consequence added; Q2 partly, the question's wording and the one-call mechanism corrected; Q3 wrong at first (the cap), taught, check right; mark left for the developer | `agent/critic.py` (`shown_hypotheses`, `SHOWN_HYPOTHESES`, `CRITIC_SYSTEM`, `critique_view`), `agent/artifacts.py` (`CritiqueResult` descriptions, `CritiqueRecord.after_stage`), `agent/investigation.py` (`route`, `critique`, `recheck` question `K1`); session note 2026-10-29 (C1b) |
| D1 | Timed sensor-feed blackout: the alarmed machine's sensors refuse for a seeded 10-50 ticks; opt-in `--hazards blackout` | yes (2026-10-29) | yes (2026-10-29, after one correction: the agent cannot fix a feed, it escalates and reports) | yes | no — closing question outstanding | `providers/hazards.py` (`Blackout`, `blackout_hazards`, `BLACKOUT_TICKS`, `BLACKOUT_STREAM`, `BLACKOUT_MESSAGE`, `HazardProfile`, `HazardReport.blocked`, `HazardReport.blackout_recovered`), `episode.py` (`run_episode(hazards=...)`), `experiment.py` (`--hazards [standard|blackout]`, `ExperimentRecord.hazards_blocked`, `ExperimentRecord.blackout_recovered`); session note 2026-10-29 (D1) |
| D2 | Degraded-case matrix (`evals/degraded.json`) and the abstention scorecard: answering vs declining kept apart | yes (2026-10-29) | yes (2026-10-29, buckets right; completed: run A is also confident-and-wrong and missing-data-read-as-normal, and why that matters for a pilot) | yes | no — closing question outstanding | `evals.py` (`Scenario.hazards`, `EvalCase` scorecard fields, `AbstentionCard`, `abstention_card`, `names`, `CONFIDENT`, `NO_FAULT`, `EvalReport.abstention`, `check_resume`), `experiment.py` (`Case.hazards`), `evals/degraded.json`; session note 2026-10-29 (D2) |
| M2 | Option B for the critic: with a manual offered, code searches it on every hypothesis the critic is shown and puts the sections in its prompt as guidance | no — built first at the developer's request, to be taught after | no — built ungated, developer to review | yes | no | `agent/critic.py` (`manual_sections`, `MANUAL_PER_HYPOTHESIS`, `MANUAL_NOTE`, `Critic(manual=...)`, `Critic.last_sections`, `critique_view(sections=...)`, a `CRITIC_SYSTEM` rule), `agent/artifacts.py` (`CritiqueRecord.manual_sections`), `agent/investigation.py` (`critique`), `episode.py`; session note 2026-10-29 (M2) |

| M1b | The manual step: with a manual offered, search it once on the anomaly before the agent plans; the `search_manual` tool stays; opt-in `MANUAL_STEP` | no — built first at the developer's request, to be taught after | no — built ungated, developer to review | yes | no | `agent/investigation.py` (`manual_query`, `consult_manual`, `MANUAL_STEP_LIMIT`, graph edge `observe -> manual -> plan`), `agent/loop.py` (`InvestigationDeps.manual_step`), `settings.py` (`manual_step`), `episode.py`, `evaluation/manual.py` (`ManualSearchRecord.automatic`); session note 2026-10-29 (M1) |
Every row above with four "yes" marks (or "n/a") is complete: no question is
outstanding on it. Still to build after 12c, from `docs/MVP_SCOPE.md`: the
other three fault scenarios (material batch, machine configuration, false
alarm), then evaluation, then the agent itself.

## Session notes

- **2026-10-30 (F5, config): one question per step is the default.** The
  developer's decision. The 2026-10-30 master runs all used
  `STEP_QUESTIONS=2` and asked 23-35 model questions per case; every batch
  and setting case timed out. `settings.step_questions` now defaults to 1
  (A12's combined interpret-and-decide question, about half the questions);
  `STEP_QUESTIONS=2` asks two. `.env.example` now shows 1. `episode.py` uses
  the setting when the policy can answer both at once (`interpret_and_decide`,
  which every model-backed policy has, tree-of-thought included) and 2 for a
  scripted policy that cannot; the record keeps the mode used. Test files
  whose scripted model replies are written for two questions
  (`tests/test_model_policy.py`, `tests/test_experiment.py`) pin
  `STEP_QUESTIONS=2` with an autouse fixture. Tests: the default is 1
  (`tests/test_settings.py`); a model policy reaches the loop in mode 1, a
  scripted one runs and is recorded in mode 2 (`tests/test_episode.py`). A
  local `.env` copied from the old example still says 2 and wins over the
  default. Built ungated at the developer's request (understood: no). Not run
  live.

- **2026-10-30 (F4): every model question is told to scan every machine.**
  From the 2026-10-30 master runs: on KA-09 (compound) the true faults were
  on CNC-07 (bearing wear and a wrong setting) while the alarm named CNC-03,
  a decoy false alarm; all three runs concluded "CNC-03 glitch, nothing to
  fix" (one at 0.95) without examining CNC-07. At the developer's wording,
  `COMMON` in `agent/model_policy.py` (the start of every job's system prompt,
  tree-of-thought included) now says a complete scan of the factory accounts
  for every machine, not only the ones the alarm names, and that before
  concluding nothing is wrong, or that the alarmed machine alone explains it,
  the agent checks the other machines (`list_machines`, then their readings
  and inspection results). Tests (`tests/test_model_policy.py`): every job's
  prompt carries the rule; the tool it names exists. Prompt only, no code
  check. Built ungated; teaching later (understood: no). Not run live.

- **2026-10-30 (F3): the critic's verdict must agree with its own pick.** The
  developer saw the critic's verdict not match what it said. In the
  2026-10-30 runs it said "object" on 9 of 10 cases, including while favouring
  the leader with a "why" that supported it and only minor gaps (KA-07 twice,
  KA-01), and "no_objection" while favouring another hypothesis (KA-03,
  H6 over the leader H3), which the follow-up then skipped. Likely cause: the
  only worked example in `CRITIC_SYSTEM` favoured the leading H1 and still ended
  `verdict: object`. Fixes: step 6 now ties the verdict to the pick
  (no_objection when the pick is the leader and nothing contradicts it or
  fits better; minor gaps are listed but do not change it), and the example
  ends `no_objection`; `recheck_trigger` treats a pick of another current
  hypothesis as an objection whatever the verdict; `verdict_mismatch` (with
  `SERIOUS_OBJECTIONS` = contradiction, alternative) names a disagreement,
  kept as `CritiqueRecord.verdict_mismatch`, `EvalCase.critic_verdict_mismatch`
  and a live-view line. The reply itself is never corrected, so the prompt's
  effect can be measured. Tests (`tests/test_critic.py`,
  `tests/test_agent_investigation.py`, `tests/test_progress_view.py`,
  `tests/test_evals.py`): each mismatch pattern and the agreeing ones; the
  prompt and example; a no_objection that prefers another hypothesis is
  tested; the record, report and view carry it. Built ungated; teaching later
  (understood: no). Not run live.

- **2026-10-30 (F2): manual 1.2, a bad lot does not fail every part.** From
  the 2026-10-30 master runs: on KA-03 the agent saw that only batch-2 jobs
  failed (all ten batch-1 jobs passed) and still ruled the batch out, because
  "a uniform batch issue would not spare jobs 12 and 14". The manual step had
  retrieved §2.9 each time, but §2.9 did not say that passing jobs do not
  clear a lot. `manual/sim-cnc-001.md` §2.9 "How to interpret" now says a bad
  lot raises the share of rejects without failing every part, that passing
  jobs from it do not clear it, that a pattern among a few jobs is usually
  chance, and to judge a batch by its reject rate against other batches. Kept
  general: no numbers from any case. Revision 1.1 -> 1.2, so the index
  rebuilds itself before the next run (it notices the change). Tests
  (`tests/test_manual.py`): the new guidance is in §2.9 at revision 1.2; the
  revision checks moved to 1.2. Built ungated; teaching later at the
  developer's request (understood: no). Not run live.

- **2026-10-30 (F1): the critic follow-up gets its own time window.** From
  the 2026-10-30 master runs: every batch and setting case ran out of research
  time (830-1000 s), so the follow-up skipped with "no research time left",
  including KA-05, where the critic named `get_settings`, the right check.
  `recheck` now opens its own window, `deps.recheck_seconds`
  (`CRITIC_FOLLOWUP_SECONDS`, default 90 s), as the critic has one: research
  time left is set to that window while it runs, and afterwards `started_at`
  moves by the seconds used, so the conclusion, proposal and check keep the
  time they had. `recheck_trigger` no longer needs research time; it skips
  when the window is 0 or no tool call is left. The body moved to
  `follow_up`. Tests (`tests/test_agent_investigation.py`,
  `tests/test_episode.py`): the trigger runs after research timed out; a zero
  window skips; the follow-up runs in its window after a timeout, its question
  is given 90 s, and the reserve is unchanged; a policy slower than the window
  stops on time with the reserve unchanged; the setting reads. Built ungated;
  teaching later at the developer's request (understood: no). Not run live.

- **2026-10-30 (docs-only): the future-work area of `MVP_SCOPE.md` now lists
  only work that is not built.** Asked for by the developer. The area went from
  about 2,500 to about 2,100 lines. Each section was checked against this log
  and the code (grep for MCP, OpenTelemetry, LangSmith, MMR, Voyage, Docling,
  `similar_lesson`, triage, `compare_sensor_windows`, hypothesis/xdist/ty,
  Dependabot) before it was removed or trimmed.
  - **Removed, because built:** the `uv` adoption note; the three MAX-HIGH
    changes (A10, A11); the known-answer scenarios (EV1); running the compound
    challenge (E6); the "Implemented foundations" table; the fault-pack plan
    (F3-F5), keeping only what is left; the "Next build candidates" table; the
    cross-provider fallback section (L1, L2, L7, L8) and the role-configuration
    section; the "why not CrewAI" bullets (kept in the 2026-10-26 note below).
  - **Trimmed to what is left:** agent-directed RAG (built: R3, A7b, A9a, C3b,
    M1; left: the usefulness record, reopening a search, memory over MCP);
    pilot-readiness (critic loop built: C2r, C1b; degraded data built: D1, D2;
    left: rapid triage, a live degraded run, a conflicting-observations case,
    demo traces); simulator fidelity (F1-F5 built; left: the experiments
    hookup, Brandon's review, kWh, amps, more components); FW3 (the critic is
    built: C1, C1b, C2r, M2; the other roles stay); FW6 (only `uv audit`, `ty`,
    Dependabot, xdist, Hypothesis stay); FW7 (sensor summaries and the provider
    benchmark built).
  - **Kept as written:** FW2 (nothing built), FW4, FW5, MMR, Voyage, Jev,
    near-duplicate memory check, Docling, the evaluation cache, Graph of
    Thoughts, the Pydantic AI review, Pydantic Evals, the Subquadratic audit,
    the Haas retrofit, difficulty modes and the frontend notes, FW9, FW10.
  - **New:** an index table by priority, group headings, and "Live runs and
    follow-ups still owed" (the live comparisons for A12-A15 and the critic, the
    degraded matrix, the memory comparison and its follow-ups, Jev agreement).
  - "Future Work N" numbers and the A-D letters stay as fixed IDs (code
    comments and tests cite them). Three headings were retitled and their links
    in `FUTURE_WORK_REEVALUATION.md` and this file updated; every link into
    `MVP_SCOPE.md` was rechecked. Not touched: other documents' prose that still
    calls built items "planned".

- **2026-10-30 (T1): tree-of-thought, factory-only eliminations, and the
  pruned branches kept and shown.** Asked for by the developer after a review
  of the three ToT fixes (#108, #109, #110, all intact on `main`). With the
  manual on by default and the manual step before `hypothesize`, #109 let a
  rating rule a cause out by citing a manual section. Built ungated at the
  developer's request (understood: no).
  - `agent/tree_of_thought.py`: `prune(..., observed_ids=...)` counts only
    factory evidence as a contradiction (the policy passes the provenance ids
    with `origin == "observable"`); the uncited reason now reads "rated
    impossible with no factory evidence against it; ranked below the best N";
    the `VALUE` prompt says manual sections and memories cannot rule a
    candidate out. `pruned_trace` turns the dropped candidates into
    `PrunedCandidate`s, and `hypothesize` returns them in
    `PrunedInterpretation.pruned`.
  - `agent/policy.py`: `PrunedInterpretation`, a code-only subclass of
    `Interpretation`, so no model's reply can carry a pruned list (the model's
    reply type is unchanged). `agent/state.py`: `PrunedCandidate` and
    `InvestigationState.pruned_candidates`. `agent/loop.py`:
    `apply_interpretation` keeps them.
  - **Where the pruned branches are kept:** `state.pruned_candidates` (the
    run's trace); the critic's prompt (`PRUNED_NOTE`, "RULED OUT BEFORE
    TESTING"; `favoured` still only a current hypothesis; an `alternative`
    objection and the check may aim at a dropped one, which the follow-up
    then tests); the audit log (`AuditRecord.pruned_candidates`; `--audit`
    now writes the record with or without memory, in `episode.py`), not the
    shared `CompletedInvestigation`, since memory learns only from beliefs;
    the live view ("ruled out by tree-of-thought:"); and, as before, the full
    trees in `ExperimentRecord.thoughts`. Written into
    `docs/COURSE_MODULES.md` (Module 4).
  Tests (`tests/test_tree_of_thought.py`, `tests/test_critic.py`,
  `tests/test_agent_completion.py`, `tests/test_progress_view.py`): a manual
  citation cannot rule a cause out, a factory one can; hypothesize hands back
  what it dropped (not what cited ungathered evidence); the model's reply type
  has no pruned field; the loop keeps them and an ordinary reading adds none; a
  tree run writes them to the audit log and not to the shared record; the
  critic is shown them, cannot favour one, and is told so; older audit lines
  read `()`; `--audit` without memory writes the record; the live view prints
  them once. Not run live.
  **Added the same day (T1, still in #136, not merged until the developer's
  two master runs finish):** P0 from `docs/TOT_CRITIC_EVALUATION_FUTURE_WORK.md`.
  An "impossible" rating with no factory evidence was kept and ranked by its
  confidence, which is confidence that the candidate is false, so
  "impossible, 0.95" became H1 at 0.95, above both 0.9 bars; the factory-only
  rule above makes the case more common. Now `unproven_confidence`
  (`min(c, 1 - c)`) scores it, `prune` ranks it below every sure or likely
  candidate and returns its rating with that score (so the hypothesis carries
  it), and `Thought.unresolved` lists it (the raw rating stays in
  `Thought.ratings`). And P1's "deferred is not false": `PrunedCandidate.status`
  is `contradicted` (factory evidence cited) or `deferred` (ranked out,
  unrated), shown to the critic and in the live view. Tests: `impossible, 0.95`
  ranks below `likely, 0.6` at 0.05; a low sure or likely still outranks an
  unproven impossible; its hypothesis stays under the bars and the tree lists
  it; none listed otherwise; older trees read; the trace says contradicted or
  deferred. The MAX-HIGH "agent never recommends a fix" note the developer
  asked about was already in `docs/MVP_SCOPE.md`, word for word; nothing added.

- **2026-10-29 (config): the manual index is rebuilt before a run when the
  manual changed.** Rule from the developer, who had just re-embedded the
  manual by hand: **when the manual changes, the index must be rebuilt before
  the next run.** Now automatic. `manual/index.py`: `section_digest` (a
  fingerprint of each section's title, text and revision) is stored with each
  section by `ChromaManualIndex.build`; `ChromaManualIndex.is_current` is true
  only when the index holds exactly today's sections with today's
  fingerprints; `ready_index` / `ready_manual_index` reuse a current index and
  otherwise rebuild it first, saying why (empty, the manual changed, or built
  by another embedding model). `experiment.open_manual` (used by
  `capstone.experiment run` and `capstone.evals`) calls it before every
  semantic run and prints "rebuilt the manual index before the run: ..." when
  it rebuilt. The index is still built once and reused: the manual's vectors
  do not change between runs, so only each search's own words are embedded.
  An index built before fingerprints were kept (including the developer's
  re-embed of today) is rebuilt once, on its next run. Tests
  (`tests/test_manual.py`): an empty index is built; a current one is
  reused; an edited title, text or revision changes the fingerprint and is
  not current; a removed or added section is not current; a changed manual
  is rebuilt with that reason; another embedding model is rebuilt; an index
  without fingerprints is rebuilt once and then reused; a semantic run says
  when it rebuilt and says nothing when it reused. Built ungated at the
  developer's request (understood: no); to be taught 2026-10-30.

- **2026-10-29 (config): the manual is on by default; `--no-manual` opts
  out.** The developer's choices: the manual is offered by default, searched by
  meaning (semantic, as `--manual` did; `--manual keyword` still picks shared
  words); the manual step (M1b) is on by default too (`MANUAL_STEP` now
  defaults to true, `MANUAL_STEP=off` turns only the step off); and both
  `capstone.experiment run` and `capstone.evals` get the same options.
  `experiment.add_manual_options` adds `--manual [semantic|keyword]` (default
  semantic) and `--no-manual`, one or the other. `evals.run_cases(manual=...)`
  offers the tool and passes the manual to the episodes; the evals CLI opens
  the manual only when it runs episodes, never to rescore `--records`. A
  semantic run still needs the Chroma manual index built
  (`python -m capstone.manual.index`) and stops with that hint if it is not.
  Tests: `tests/test_experiment.py` (an autouse fixture swaps in the offline
  keyword search; on by default by meaning; `--no-manual` gives none; both
  flags together are refused; `MANUAL_STEP` defaults to on; the agent-search
  record test turns the step off to keep its intent), `tests/test_evals.py`
  (`run_cases` offers the manual when given; rescoring never opens it).
  Config-level change, built ungated at the developer's request (understood:
  no). Runs from now on differ from earlier runs, which had no manual unless
  asked for: compare like with like.

- **2026-10-29 (M2): Option B, the manual for the critic.** The developer
  decided Option B on 2026-10-28 (code searches the manual for the critic; the
  critic never calls a tool) and asked, on 2026-10-29, for a search on **every
  hypothesis the critic will see** (up to five since C1b), built first and
  taught afterwards, not merged yet. Built ungated, developer to review
  (understood: no). Separate from M1 (the agent's manual step), on its own
  branch.
  Built: `Critic(client, tools, manual=...)` gets the run's `ManualSearch`.
  `episode.py` passes it when the run offers a manual. In `review`, before the
  one question, `manual_sections` searches each shown hypothesis's claim
  (`MANUAL_PER_HYPOTHESIS` = 2 sections each), keeps each section once, in the
  order the hypotheses are shown, and `critique_view` adds them under
  `MANUAL_NOTE` (guidance for the machine model, not a look at the factory, no
  evidence id). `CRITIC_SYSTEM` gains one rule saying the same. The search runs
  inside `review`, so its time is the critic's and the investigation keeps
  its own. It calls the search directly, not the `search_manual` tool, so it
  uses none of the agent's three searches and adds nothing to the agent's
  evidence. A failed search shows nothing. `Critic.last_sections` and
  `CritiqueRecord.manual_sections` keep the ids shown ("§2.9"): `()` when a
  manual was offered and nothing was found, `None` without one (and in older
  records). The critic still cannot cite a section: `_problem` refuses any id
  that is not gathered evidence. Tests (`tests/test_critic.py`,
  `tests/test_agent_investigation.py`, `tests/test_episode.py`): no manual,
  no change; every shown hypothesis searched, sections shown once and in
  order after the hypotheses; found nothing gives `()`; a failed search still
  answers; a section id cited as evidence is refused; the prompt says
  guidance, not evidence, and names no fault; the real manual shown to the
  critic names no hidden truth; the record keeps the ids, older records read
  `None`; a settings-built critic gets the manual only when the run offers
  one. Spec section 1 marked built. Not run live.

- **2026-10-29 (M1b): the manual step, step 1 of the developer's manual
  plan.** The developer's plan: first give the manual its own step, then keep
  it as a tool the agent can call (`search_manual`, which already exists). The
  developer asked for it to be built first and taught afterwards, and not to
  be merged yet. Built ungated, developer to review (understood: no).
  Why: in the six saved runs that offered the manual, the agent searched it
  once, never on the batch or setting cases, although section 2.9 says to
  group inspections by batch (the check KA-03 missed).
  Built: a stage `manual` between `observe` and `plan`
  (`consult_manual`), on only with `MANUAL_STEP` and a manual offered
  (`episode.py` sets `manual_step` only when `manual` is given). The loop
  makes one `search_manual` call itself, as it does for the time, on
  `manual_query`: the anomaly's kind and description, the only words known
  before any hypothesis. The search asks for `MANUAL_STEP_LIMIT` = 3
  sections. It goes through the normal `gather` path, so the answer is
  evidence labelled `manual` (general guidance, never a look at the
  factory; `diagnosis_supported`, `verify` and the memory gate already
  refuse to count it as observation). It counts as a tool call and as one of
  the manual's three searches, and the policy is not asked to read it there:
  it sees the sections in the plan's prompt and every later one.
  `ManualSearchRecord.automatic` (False for older records) marks the step's
  search apart from the agent's own. Tests (`tests/test_manual.py`): off by
  default; the step searches on the anomaly before the plan, and the plan
  sees the sections; it is labelled manual and recorded as automatic; the
  tool stays open afterwards; the step uses one of the three searches; the
  query is the anomaly's kind and words only; old records read as chosen by
  the agent; an episode runs the step only when it offers a manual and
  `MANUAL_STEP` is on. The graph-shape test now expects `observe --> manual
  --> plan`. Not run live. Option B for the critic is its own PR.

- **2026-10-29: PR #117 pre-merge walkthrough.** The developer explained
  that a stop with a question ID is invalid and that `information_needed`
  carries the explanation while call-only fields stay empty. The developer
  correctly identified that mixed stop replies are recorded as invalid;
  initially assumed the rejected reply still stops the stage. Corrected: the
  loop may ask again, and a valid tool call can continue the investigation;
  repeated unproductive steps can instead reach the limit. The developer
  explained this distinction correctly after the correction. No live model
  measurement of the prompt change was performed.

- **2026-10-29: a stop leaves the call fields empty (prompt and schema).**
  The investigator kept answering a decide question with `choice: stop` while
  also setting `tool`, `arguments`, `question_id` or `hypothesis_id`, which
  `NextStep.one_kind_of_step` refuses. Counted across every saved results file:
  26 of 1,448 questions (1.8 %), all decide, in 10 of 87 runs, and none in the
  earliest files. Each costs a question and counts as an unproductive step;
  three in a row end the stage (KA-02 in the first critic run: three refused
  stops, then `no_useful_action`, a wrong recorded stop reason). Likely cause:
  `NextStep` is flat on purpose, so every field looks allowed on a stop, and the
  decide prompt never said to leave them empty; a KA-01 stop said "Q2 is settled
  by E2", which suggests `question_id: "Q2"`. Changes in `agent/model_policy.py`:
  one sentence in `SYSTEM["decide"]` (used by the step-by-step and the combined
  question): leave those four fields empty when stopping and say what was
  settled, and which question, in `information_needed`; descriptions on the
  four fields ("Only with choice call_tool; leave empty when stopping") and on
  `stop_reason`, which reach the model with the schema; the refusal now ends
  with `(found: <fields>)`, keeping the old wording first so older counts still
  match. Still refused, never repaired. To check: the same count on the next
  runs. Built ungated at the developer's choice (option 1 of three), developer
  to review.

- **2026-10-29 (docs-only): a separate pass for variable comments.** Rule set
  by the developer, now `AGENTS.md` section 7.1: after a change's code is
  written and its tests pass, a separate pass checks the `# Variables:` block
  at the top of every function the change created or changed, naming the
  variables that carry meaning in one plain sentence each (not trivial ones),
  then reruns lint and the touched tests, and the pull request lists the
  commented functions. Applies to both coding agents.

- **2026-10-29 (docs-only): walkthrough of PR #122 (C1b), given after the
  merge at the developer's request** (so they could start testing in another
  session). The 'Understood (post)' mark stays **no**; the developer decides.
  - Q1 (why `after_stage` is read in `critique()`): mostly right, the state is
    read before `recheck` changes `state.stage`. Refined: it is `recheck`, not
    the critic, that sets the stage (even when it skips). Added: read in
    `conclude()` with the follow-up on, every run would say `test`, so the
    "skipped testing" split (KA-03 style) would vanish.
  - Q2 (critic objects and favours H3 below a leading H1): `K1` tests H3,
    right. Corrected: its text names both ids and carries the critic's check,
    not its objection; the agent's own policy makes at most one read-only call
    and may pick another tool or stop. Refined why: the check was built to
    separate the pick from the leader, it avoids framing the reading as
    confirming the leader, and the record attributes the reading to H3. Without
    an objection the follow-up skips.
  - Q3 (six hypotheses, `favoured` H6): wrong at first (said it is recorded
    under H6). Taught: only five are shown, so H6 is refused as `invalid_reply`,
    the whole reply is discarded, `recheck` skips ("no usable answer"), the run
    concludes as normal. Risks: the cap can hide a sixth, correct hypothesis;
    one bad field discards the whole reply. Check (four hypotheses, `favoured`
    H6): right, refused because the critic hallucinated it; the skipped
    follow-up added.
  - Developer's idea, for the critic tuning: a confidence on each objection,
    recorded first and checked against labels before anything reads it (it can
    still be confidently wrong).

- **2026-10-29 (docs-only): KA-03 with the critic, and a note to run the
  critic before every conclusion.** Live runs with the critic on (Ministral 14B
  then Cohere): `critic-known-1.jsonl` (KA-01, KA-02) and `critic-ka03-1.jsonl`
  (KA-03, seed 7), files kept untracked in the developer's folder. Jev labels
  (`critic-known-1.labels.jsonl`, none marked for review): KA-01 and KA-02 the
  agent was right (bearing wear on CNC-02 and CNC-05, fixes resolved); the
  critic answered in 6.1 s and 7.6 s, favoured the right cause both times
  (provisional, labelled from the claim wording saved before PR #114), objected
  both times, and said the evidence did not justify acting both times. KA-03:
  research timed out in `investigate`, so `test` and the critique were skipped;
  the agent escalated without naming batch 2 although its first look showed it.
  The run had no invalid stop replies and three model timeouts. Recorded as
  future-work item 4 in
  `docs/superpowers/specs/2026-10-28-critic-review-only-design.md`: run the
  critic before every conclusion. Nothing built in this note; item 4 was
  then built in PR #122 (C1b).

- **2026-10-29 (D2): the degraded-case matrix and the abstention
  scorecard.** Item 2 of the 2026-10-29 pilot-readiness list, second piece
  (the blackout was D1). Taught first. Gate question (a blackout on a worn
  bearing: run A says "false alarm" at 0.85, run B names no cause): the
  developer put A in committed and B in abstained, which is right. Completed:
  A is also confident-and-wrong and missing-data-read-as-normal. That matters
  for a pilot because B costs a technician a look, while A tells the shop a
  wearing machine is fine. Built:
  - `evals/degraded.json`, 11 cases on the known-answer seeds: clean and
    `blackout` pairs for bearing (6), wrong setting (9), false alarm (8), bad
    batch (7) and the compound challenge (3), plus one standard-hazards
    bearing case (stale record). Run with
    `python -m capstone.evals --config evals/degraded.json`. Live runs are
    Codex's (`AGENTS.md` §12).
  - Per-case hazards: `Scenario.hazards` and `Case.hazards`, used by
    `run_experiment` before the run-wide setting. `check_resume` refuses a
    saved episode whose hazards do not match its case.
  - The scorecard (`AbstentionCard`, from `abstention_card`, kept on
    `EvalReport.abstention`, printed by the CLI). A judged case is
    *committed* when its label names a cause and *abstained* when it names
    none. It reports: accuracy when committed, abstention rate, confident and
    wrong (committed, wrong, confidence >= `CONFIDENT` = 0.8), false
    interventions (a repair asked for that was wrong; needs no label),
    missing data read as normal (a blackout case with a real fault labelled
    `false_alarm`), and recovery (refused blackout cases that read the
    sensors again once the feed was back).
  - Plain accuracy is unchanged: abstaining still counts as wrong there. The
    scorecard sits beside it.
  Tests (`tests/test_evals.py`): the matrix pairs clean and blackout cases on
  the same seeds; each case runs with its own hazards and resume checks
  them; runs A and B score apart while plain accuracy is unchanged; just
  below 0.8 is wrong but not confident; a blackout that never refused is not
  a recovery case; missing-data-read-as-normal needs a blackout; a wrong
  repair request is a false intervention without a label; unjudged cases
  stay out of the label counts; old reports still read. Not run live.

- **2026-10-29: C1b, the critic before every conclusion, shown every
  hypothesis.** Step 1 of four agreed with the developer (critic placement,
  automatic manual retrieval, observable evidence to recommend a fix, gap
  classification with a trace). Built on PR #119's follow-up. Taught first; the
  gate question (which `favoured` is still refused once every hypothesis is
  shown) was answered right, with the reason corrected (review only, the agent
  never sees the reply yet; the reasons today are that the critic cannot have
  weighed an invented id and the record would be meaningless).
  - `agent/investigation.py`: `route` sends both "conclude" branches to
    `critique`, so every path passes `critique -> recheck -> conclude`.
    `critique` records `after_stage` (read before `recheck` sets the stage to
    test). `recheck`: when the critic objects and favours another hypothesis,
    `K1` tests that pick and names both ids.
  - `agent/critic.py`: `shown_hypotheses` replaces `top_two` (every hypothesis,
    most believed first, ties in list order, at most `SHOWN_HYPOTHESES = 5`);
    the view marks the leading one; `CRITIC_SYSTEM` asks for the best-supported
    hypothesis and a check that separates the pick from the leader.
  - `agent/artifacts.py`: `CritiqueResult` field descriptions match;
    `CritiqueRecord.after_stage` (older records read as `None`).
  - Tests: every hypothesis shown and capped at five; the leader marked once; a
    third hypothesis may be favoured; one past the cap is refused; the critic
    reviews a run that timed out in `investigate` (`after_stage` investigate);
    `after_stage` test on the usual path and read before the follow-up; `K1`
    tests the critic's pick when it is not the leader; the graph test expects
    both forks to go to `critique`.
  - Developer's note: tune the critic afterwards (it objected in every live run
    so far, including the right ones).


- **2026-10-29 (D1): a timed sensor-feed blackout.** Item 2 of the
  2026-10-29 pilot-readiness list (degraded data and abstention), first
  piece. Taught first. Gate question (a dead feed and three failed reads: why
  not conclude "false alarm"?): right that a dead feed is not a false alarm
  and the agent should escalate or report; corrected that it cannot
  "intervene to fix the feed" (its actions are maintenance requests, and they
  need human approval), and that `hazards_fired` is the evaluator's trace,
  never shown to the agent. The developer's design choices: **timed only**
  (no permanent blackout), with the length **random from a seeded stream**,
  **10-50 ticks**, and hazards stay **opt-in** (off unless asked for).
  Built: `Blackout(machine_id, until_tick)` in `providers/hazards.py`
  refuses `get_readings`, `get_sensor_trend` and `get_sensor_summary` for that
  one machine until `until_tick`, however often it is asked. The message
  ("The sensor feed for CNC-02 is not responding.") never says when it
  ends. `blackout_hazards` draws the length from the simulator's own
  `RandomSource` stream `hazard.blackout`, from the run's start tick. A new
  stream name leaves every other stream unchanged, so the factory is the
  same world with or without it. The simulator is never touched. Asking again
  works only after factory time has passed (`wait`). `HazardReport.blocked`
  counts refused calls, and `blackout_recovered` (None without a blackout) is
  True once the agent reads the machine's sensors after being refused.
  `run_episode(hazards="blackout")` and `python -m capstone.experiment run
  --hazards blackout` turn it on; `--hazards` alone is still the standard
  schedule. Both are off by default. Records keep `hazards_blocked` and
  `blackout_recovered`. Tests (`tests/test_hazards.py`, `tests/test_experiment.py`):
  refuses until the end tick and never says when; other machines and tools
  untouched; waiting past the end gives the real answer and records the
  recovery (one tick short still refuses); a feed never refused is no
  recovery; the factory is untouched; the length is seeded and within 10-50;
  no named machine, no blackout; an episode reports it, repeats exactly and
  keeps the same world; the CLI is off by default, `--hazards` is standard,
  `--hazards blackout` is the blackout; older records still read. Not run
  live. Later implemented in #123: the degraded-case matrix and the
  abstention scorecard (accuracy among answered cases, abstention rate,
  wrong confident conclusions, false interventions, recovery rate).
- **2026-10-29 (docs-only): Codex runs the master experiments, Claude Code
  builds the code.** At the developer's request, `AGENTS.md` §12 records the
  split. Codex does the live master runs, their labelling and the result
  notes. Claude Code builds features, fixes and tests through pull requests,
  runs only tests and scripted offline runs itself, and hands merged changes
  to Codex to run live.

- **2026-10-29 (C2r): the critic follow-up, one reading where the critic
  pointed.** Item 1 of the 2026-10-29 pilot-readiness list. Taught first. The
  developer's goal: at about 0.80 the agent escalates, and the critic should
  confirm so it can intervene. Two designs were offered: (A) the critic's
  agreement lowers the bar, or (B) the agreement earns one confirming factory
  reading. The developer chose B, with A kept for later, once labelled critic
  runs show how often `supports_action` is right. Points from the teaching: in
  EV1 the bar lowered no intervention (KA-01 escalated at 0.85 by its own
  choice), and the critic sees the agent's evidence, so its agreement is not an
  independent look. Gate question (leader at 0.82, critic agrees, the reading
  is normal): right that it stays below the bar and escalates; corrected that
  a normal reading means "not confirmed", not "no action needed", and that the
  critic's agreement never counts at the bar.
  Built: a stage `recheck` between `critique` and `conclude`, on only with
  `CRITIC_FOLLOWUP` (default off, so the review-only critic stays the
  baseline). `recheck_trigger` runs it when the critic answered and either
  objected, or favoured the leading hypothesis while that was below
  `min_action_confidence`. It skips, with the reason recorded, when the
  critic gave no usable answer, named no check, favoured another hypothesis
  without objecting, the leader already reaches the bar, or no research time
  or tool call is left. When it runs, the critic's `discriminating_check`
  becomes open question K1, tied to the leader in this original build. #122
  changes K1 to test the critic's pick when it objects and favours a
  different hypothesis. The agent's own policy is
  asked for one test-stage decision, and at most one call goes through the
  normal `gather` (allowlist, provenance labelled by its real source, one
  interpretation). Then the run goes to `conclude`, where the bar applies to
  the agent's own confidence as before. The critic is never asked again, so
  the stage cannot loop. `RecheckRecord` (outcome, trigger, reason, question,
  tool, evidence id, leader and confidence before and after) is kept on the
  state and in `ExperimentRecord.recheck`. Tests: `tests/test_agent_investigation.py`
  (off by default; no critic; an objection earns exactly one observable
  reading that answers K1; never loops; agreement plus a confirming reading
  intervenes; agreement without one still escalates; the same agreement
  without the follow-up escalates; a stopping or bad policy decision makes no
  call; trigger reasons, including the run's own bar; time and call budgets;
  a skip calls nothing; the graph shape), `tests/test_episode.py` (the
  setting reaches the run; off by default), `tests/test_experiment.py` (kept
  in the record; older records still read). Not run live. Limits: the
  policy may answer K1 with any read-only tool, not the one the critic named
  (by design: the critic's text is never run as a call); one follow-up only;
  the critic's own confidence and `supports_action` are recorded, never used.

- **2026-10-29 (docs-only): Haas VF-based simulator retrofit and older-machine support.** Recorded a HIGH-priority post-baseline future-work plan in `docs/MVP_SCOPE.md` for a real, revision-specific Haas VF NGC profile to replace the generic CNC as the simulator's eventual default, with optional Classic Control/RS-232 compatibility for early-2000s machines, `FactoryProvider` read-only adapters, manual/SOP RAG, field discovery, optional external sensors, explicit missing-data semantics and deterministic offline comparisons. No runtime changes or machine integrations were made; the existing `SIM-CNC-001` manual remains synthetic.


- **2026-10-28 (docs-only): future-work notes for the critic.** After the first
  live critic run the developer asked whether the critic may use the manual
  (it may not: no tools, by the spec) and chose Option B: code searches the
  manual for the hypotheses' claims and puts the sections in the critic's
  prompt, labelled as general guidance, with no tool loop. Recorded with the
  rejected Option A, the open question of a critic that calls evidence bad,
  and the missing "asking the critic" line in the live view, and a note on
  Option B that a way is needed to get the agent to call the manual at all
  (it was not offered in the first run, and only prompt guidance pushes it),
  in a new
  "Future work notes" section of
  `docs/superpowers/specs/2026-10-28-critic-review-only-design.md`. Nothing
  built.

- **2026-10-28 (C1 fix): the critic's pick is labelled from the claim it judged.**
  Found in the first live critic run (`critic-known-1.jsonl`, KA-01 and KA-02):
  `favoured_claim` in `experiment.py` read the favoured hypothesis from the
  final state, after the conclusion and the check. The agent rewords its
  hypotheses after the critique, so the saved claim was not the one the critic
  judged; in KA-02 it even said the replacement worked and vibration was below
  the threshold. That text is what the Jev labeller reads for measure 3, so the
  critic could be credited with words written after the fix. Now
  `CritiqueRecord.favoured_claim` (default `None`, older records still read)
  keeps the claim as worded at the critique, set in `critique()` from the shown
  hypotheses, and `favoured_claim` reads only that. The two saved records from
  that run still carry the late wording in `critic_favoured_claim`: label their
  picks by hand, or rerun. Built ungated, developer to review.

- **2026-10-28 (C1 follow-up): the live view shows more of the critic's answer.**
  Asked for by the developer while watching the first live critic run. The
  `CRITIC (...)` line now has two lines under it: `why: ...` and `confidence
  0.65, supports action: no, objections: missing_evidence, alternative;
  <model> in 8.2 s`. A critic that gave no answer prints `tried for N s`.
  `CritiqueRecord.answered_by` is new (default `None`, so older records still
  read): `critique()` in `agent/investigation.py` reads it from the critic's
  own latest call record, which also names the model whose reply was refused.
  The spec already asked for it ("each critique records which model answered").
  Not done: a line before the critic is asked (the view only runs after a
  stage ends, so a long wait still looks silent; showing it needs a pending
  marker on the state). Built ungated, developer to review.

- **2026-10-28 (docs-only): walkthrough of PR #108 (tree-of-thought trees in
  the experiment record), given after the merge at the developer's request.**
  Three questions. (1) Why a record's `thoughts` is `null`: the developer
  gave two reasons that both give a different value (a confident single
  answer and a timeout leave a list, possibly empty); re-taught that `null`
  means no tree policy ran or an old file, `[]` a tree policy that recorded
  nothing. (2) Why the file round trip is tested: "not sure", then "it needs to
  decode it" after a hint; taught that decoding rebuilds `Thought` and
  `Candidate` objects and tuples from the type annotations and rejects
  mismatches. (3) What the trees let you check: the developer said how
  candidates were dropped or kept can be inspected; the missing link
  (matching a candidate's free-text claim to the hidden fault kind) was
  taught, not found. Understanding of #108 is only partly shown: the
  "Understood" mark stays **no** for the tree-record change.

- **2026-10-28: tree-of-thought trees saved with each experiment record.**
  From an outside audit of the tree-of-thought step: `TreeOfThoughtPolicy`
  kept each hypothesize step's tree (`Thought`: candidates, ratings, kept ids,
  and why each other candidate was dropped) on `policy.thoughts`, but
  `ExperimentRecord` had no place for it, so a saved results file could not
  show whether the right cause was pruned. `experiment.py` now has
  `ExperimentRecord.thoughts` (a list of `Thought`, None for the ordinary
  step and older files), `record_of(..., thoughts=...)`, and
  `run_experiment` passes `getattr(policy, "thoughts", None)`. Evaluator-side
  only: nothing goes back to the agent or a prompt. Tests in
  `tests/test_tree_of_thought.py`: the scripted ToT run's record carries the
  tree and the plain run's does not; the tree survives a write and read of
  the results file. Built ungated, developer to review (understood: no).
- **2026-10-28: C1, the critic (review only), built from the plan.**
  Built task by task from `docs/superpowers/plans/2026-10-28-critic-review-only.md`
  (spec `docs/superpowers/specs/2026-10-28-critic-review-only-design.md`), each task's
  tests first, one commit per task. Off by default (`CRITIC=off`), so existing runs and
  the EV1 baseline are unchanged.
  - **Task 1, settings and the critic's own client.** `Settings.critic` (`CRITIC`, on/off),
    `Settings.critic_model` (`CRITIC_MODEL`, a comma-separated chain, blank means unset),
    `Settings.critic_seconds` (`CRITIC_SECONDS`, default 40, must be above 0).
    `critic_models(settings)` reads the chain in order without repeats.
    `critic_client(settings)` builds a `FallbackClient` from that chain only: the shared
    `FALLBACK_MODEL` chain is not added, because it leads back to the investigator's
    models. With no `CRITIC_MODEL` it raises `ModelError` naming the setting.
  - **Task 2, the critic's question.** `Objection` and `CritiqueResult` (every field has
    a description, which the client sends with the schema) and `CritiqueRecord`
    (outcome, result, the ids shown, seconds used) in `agent/artifacts.py`.
    `agent/critic.py`: `top_two(state)` (by confidence, ties in list order),
    `critique_view(state, tools)` (the anomaly, the same evidence section as every
    other question, the two hypotheses, and the tool list as text the critic cannot
    call), `CRITIC_SYSTEM` (the six-step procedure and a neutral house-plant example
    that names no fault), and `Critic.review`, which records a `ModelCall`
    (`job="critique"`, `agent="critic"`) whatever happens and refuses a reply that
    favours a hypothesis it was not shown or cites evidence never gathered.
  - **Task 3, the stage.** `critique(state, deps)` in `agent/investigation.py`, wired
    `test -> critique -> conclude`. It does nothing without a critic or hypotheses.
    It shows the critic a copy of the state, records the outcome (`answered`,
    `no_answer` on `ModelError`, `invalid_reply` on a refused reply), and never stops
    the run. It moves `started_at` forward by the seconds the critic used, so the
    investigation's time left is the same after the stage as before it.
  - **Task 4, episode and records.** `run_episode(critic=...)`; with `CRITIC=on` it
    builds the critic before the factory, so a missing `CRITIC_MODEL` fails before the
    case runs. `EpisodeResult.critic_calls`, `ExperimentRecord.critique`,
    `run_experiment(make_critic=...)`: the critic's questions are counted after the
    policy's and appear in `agent_steps` as `agent="critic"`, phase `critique`.
    The live view prints one `CRITIC (...)` line.
  - **Task 5, the EV1 report.** `EvalCase.critic_outcome`, `critic_verdict`,
    `critic_favoured`, `critic_pick_correct`; `ExperimentRecord.critic_favoured_claim`;
    `report_of(critic_labels=...)` scores the pick from its own label, never the
    agent's accuracy; `critic_labels(records, proposer)` labels each favoured claim
    with Jev and leaves out a proposal that needs review. `automatic_labels` now
    returns the critic labels as a third value.
  - **Not done.** The live prompt check on three or four made-up states (plan Task 6
    step 1) was not run: the developer asked for no live runs this session. No master
    run. `.env.example`: the developer added `CRITIC`, `CRITIC_MODEL` and
    `CRITIC_SECONDS` (commented out, so a copy still loads with the defaults);
    the coding assistant cannot read or edit that file.
  - Gate: pre-merge walkthrough done (AGENTS.md section 11 step 6), result below. The 'Understood (post)' mark stays **no**; the developer decides.
  - Walkthrough, PR #106. Q1 (the critic's models time out): said the critic is skipped, the loop goes on and no critique is recorded. Right on the outcome; corrected on: it already happened in the live spike; 'skipped' (`critique` is `None`) is not 'timed out' (`outcome="no_answer"` with a record); who catches it (`Critic.review` records and re-raises, `critique()` catches); the deadline moves by the seconds used; the investigator's own timeout instead ends the run with `MODEL_UNAVAILABLE`. Q2 (1,200 s timeout, `started_at` 100, critic takes 25 s): `started_at` 125, right; time left (300 s before and after) not given; said research would lose time, which is wrong, research is finished when the critic runs, the follow-up reserve (conclusion, proposal, work, check) would lose it. Q3 (valid JSON with `favoured` = H3 when only H1 and H2 were shown): 'not sure'; taught (`_problem` refuses it, the call and attempt are marked `invalid_reply`, `state.critique` has no result, the critic cannot have judged a hypothesis it was not shown, and the pick would corrupt measure 3). Check: `favoured` = none plus an objection citing real evidence is accepted. The developer said accepted, right, but thought it might be refused for not being H1 or H2; corrected, none is allowed.
  - Open design question raised by the developer: what to do if the critic says the evidence itself is bad. Today `_problem` checks only that cited ids exist, and there is no objection kind for unreliable evidence (closest: `missing_evidence`, `unsupported_claim`). Review-only records it as text. Whether the agent should re-check, discount or ignore it is option 2, to be decided after labelled runs show the critic is right when it says so.

- **2026-10-28 (test only): a guard that the agent package never imports
  truth-side code.** Asked for by the developer while reviewing the critic
  (PR #106): the protection that the agent cannot reach hidden truth was
  structural (only `episode.py` holds both sides) and prompt-content tests,
  with no import check. `tests/test_agent_artifacts.py` now has `TRUTH_SIDE`
  (`capstone.simulator`, `capstone.evaluation`, `capstone.episode`,
  `capstone.experiment`, `capstone.evals`), `is_truth_side` (a module or any
  submodule, so `capstone.simulatorish` does not match), and two tests:
  `test_the_agent_package_does_not_import_truth_side_code` (every file under
  `agent/`, direct imports) and `test_the_truth_side_check_catches_a_forbidden_import`
  (a planted file is caught). Checked by hand too: adding
  `from capstone.evaluation import scoring` to `agent/state.py` made the
  guard fail, naming the file. Limits: direct imports only (as the memory
  test); `agent/monitor.py` imports `ObservationTools` and `ActionTools`, the
  tool boundary itself, which stays allowed; `capstone.faults` is not on the
  list because its agent side (`FAULT_KINDS`, `ACTIONS`) is meant for prompts.
  Built ungated (test only), developer to review.

- **2026-10-28 (fix): the automatic stop counts only factory evidence.**
  From an outside audit: `diagnosis_supported` (`agent/loop.py`) counted
  every supporting evidence id towards `min_supporting_evidence` (2), so two
  machine-manual answers, or a recalled memory, could make the diagnosis look
  settled and stop research. Now only supporters whose provenance origin is
  `observable` (answered by the factory) count, each id once; manual,
  memory and unrecorded ids do not. The same rule `verify` already applied
  after a fix. Tests in `tests/test_agent_loop.py`: a new
  `test_only_factory_answers_count_as_support_for_the_automatic_stop`
  (manual and memory alone, one observed, two observed, one id cited twice,
  unknown ids); the two hand-built stop tests now record their evidence as
  factory answers (`answered`). Built ungated, developer to review
  (understood: no).

- **2026-10-28 (docs-only): walkthroughs for A10-A15, L8, L9 and EV1.**
  Each was taught after the build, then quizzed three ways (EV1: three
  questions on the harness). The "Understood (post)" marks stay **no**: the
  answers were in part right and needed corrections, and the developer
  decides when a row turns to yes. Results:
  - A10: Q1 (why `recommendation_lowered` uses the raw reply) in part,
    corrected (the checked `request` is always `None`). Q2 (reading the
    records): (b) right; (a) the model chose escalate, but confidence is not
    known from the record; (c) wrong at first, then corrected: `None` means
    the recording lines never ran (time out or unusable reply). Q3 (what
    zero fixes means): KA-01 right (the bar blocked it); KA-02 the bar plays
    no part when the model itself says escalate, so a prompt or reasoning
    change is needed, not a lower bar.
  - A11 and A13, taught together: Q1 (bar hidden, 0.88 intervene) right
    apart from the record, which shows `policy_recommendation`,
    `recommendation_lowered` and `state_action_bar=False`. Q2 (why the code
    still checks) right: the code is the authority, and the confidence is
    the model's own claim. Q3 (2 fixes with the bar shown, 0 hidden): the
    developer's reading was "the agent does not use the bar", which the
    repo's notes do not support: `docs/MVP_SCOPE.md` item 9 records only two
    cases from different runs where stating the bar seemed to lower
    confidence, with the live comparison still outstanding. Corrected: repeat
    each setting on the same seeds, one live run at a time, and compare right
    recommendations and unnecessary fixes, not only the fix count.
  - A12: closing question (why the combined mode holds its next call as
    `pending_decision`) in part: the developer named tracing; the reason is
    that every stop check in `check_termination` runs before every call.
    Follow-up: the stored call is discarded when the next turn stops, and
    never runs in a later phase.
  - A14: Q2 (why one wait, not repeated) in part: the budget was named; the
    main risk is that `wait` is the one tool that changes the factory, so a
    real fault keeps worsening.
  - A15: Q1 (why the manual note is empty when the tool is not offered)
    misread at first, then right: the prompt must match the tool list, or the
    model asks for a tool that is refused. Q3 (still 0 manual searches): the
    trace first, in order: tool offered, note in the prompt, asked and
    refused versus never asked, only then a model that ignores it.
  - L8: Q1 (why a bad reply does not move on to the next model) right: it is
    the model's own doing and a measurement. Q3: Cohere refused the request
    over its 8,192 limit (not a cut-off answer); NVIDIA's carries 16,384;
    the cap is per provider so models that think at length keep their room.
  - L9: Q2 in part: the watcher gets a copy; a watcher that raises is caught
    and logged without its text, so a display fault cannot stop a run.
  - EV1 (a second walkthrough, with other questions, is recorded in the
    EV1 note of 2026-10-27): Q1 in part: the truth is
    used to build the world and again to score, never passed to the agent;
    the boundary is the tool provider. Q2 right, with the second reason
    that the judged cases are probably the easy ones; unjudged is unknown,
    not wrong. Q3: thought a repeat without `--resume` restarts the run;
    corrected: `reserve_raw_output` refuses an existing file, and `--resume`
    runs `check_resume` first.

- **2026-10-28 (fix): tree-of-thought "impossible" needs a cited contradiction.**
  From an outside audit: `prune` (`agent/tree_of_thought.py`) dropped any
  candidate the rating model called impossible, with no evidence against it,
  so a real cause could be ruled out by say-so. `Rating` now has
  `contradicting_evidence_ids`, the `VALUE` prompt asks for them on an
  impossible verdict, and `prune` drops for "rated impossible" only when
  gathered evidence against the candidate is cited (by the rating or the
  candidate itself). Otherwise the candidate is ranked by its confidence
  like the rest; if ranked out, the reason reads "rated impossible with no
  contradiction cited; ranked below the best N". Tests in
  `tests/test_tree_of_thought.py`: cited, uncited, ungathered-only and
  candidate-cited cases; the ranked-out reason; the prompt names the field;
  existing scripted ratings now cite their contradiction. Limit: any
  gathered evidence counts, including manual or memory answers (`prune` sees
  ids, not origins). Not run live. Built ungated, developer to review
  (understood: no).

- **2026-10-28 (EV1): the single-agent master baseline, finished and labelled.**
  The run `master-single-2026-10-27` resumed at KA-04 (`--resume --watch`, in
  a terminal tab the developer watched) and finished all nine cases. Settings:
  defaults (`STEP_QUESTIONS=2`, `STATE_ACTION_BAR=true`, bar 0.9), NVIDIA
  Nemotron Super 120B, no manual, memory or hazards: the harness has no manual
  option yet, so this is master run A, not a test of A15 (to discuss with the
  developer after all master runs). Labels
  (`docs/benchmarks/2026-10-27-master-labels.jsonl`) follow the 2026-10-26 rule,
  the conclusion's words and not the true fault: the developer decided KA-01,
  KA-03 and KA-04 (all "none"); the coding assistant drafted the other six and
  showed them to the developer. Result (`2026-10-27-master-resumed.json`):
  **3 of 9 right (33%)**: false alarm 2/2, bearing 1/3 (KA-02; KA-09's compound
  case named only the bearing on CNC-03), bad batch 0/2, wrong setting 0/2.
  111 tool calls, 236 model questions, 6,251 s in all. Five cases ended on the
  time limit (KA-03 to KA-06, KA-09), each after 3-5 outage retries; no
  intervention was lowered by the bar (KA-01 escalated at 0.85 by its own
  choice). The mixed raw file from 2026-10-27 is left out. Merged before the
  walkthrough at the developer's request (2026-10-28); understanding stays
  "no" until the walkthrough is done.
  **Walkthrough (2026-10-28, after the merge).** Q1 (if `STEP_QUESTIONS`
  changes between a run and its resume, what does `check_resume` do?): answered
  that it stops on the mismatch; wrong, corrected: it checks only run key,
  scenario, seed and forced fault, so the resume goes on and the report mixes
  two configurations (each record still stores `step_questions`). Q2 (why an
  unlabelled case is `correct = None`, not `False`): right that it is unjudged,
  not wrong; completed: as `False` it would make `compare_reports` show an
  accuracy change that never happened, while `None` keeps `accuracy_change`
  unknown. Q3 (why `--resume` skips `reserve_raw_output`, and what it loses):
  not answered; re-taught: `"x"` mode needs the file absent and a resume needs
  it present; a resume has no exclusive claim, so two copies would both run
  and append. Follow-up check (what kept today's resume safe?): answered that
  no `--resume` was used; corrected: it was used; one copy at a time, checked
  before the start, kept it safe. Possible follow-ups, not built: compare
  settings in `check_resume`; a lock file for a resumed run.

- **2026-10-28 (docs-only): variable comments across `capstone/`, and the
  A10 walkthrough begun.** No behaviour changed. At the developer's request,
  each function with variables that carry meaning now has a `# Variables:`
  comment block at the top of its body, one sentence per variable, in 58 of
  the 81 modules, which is every module that has a function with variables
  worth describing. Only variables where the name alone does not say enough
  were described. The other 23 modules have no function to comment (package
  `__init__` files, plain data definitions such as `contracts/*` and
  `agent/artifacts.py`, `ground_truth.py`, `known_answers.py`, `schema.py`)
  or only stubs and validators without variables (`agent/policy.py`,
  `contracts/tools.py`, `memory/contracts.py`). Tests and command line
  parsers were left alone. Checked by comparing the syntax tree of every
  changed file with the one on `main` (identical in all 58 files), so only
  comments changed. The block in
  `agent/investigation.py` `conclude` also explains "lowered" and how to read
  `policy_recommendation` and `recommendation_lowered` together.
  A10 walkthrough (not finished; row A10 stays "Understood: no"): Q1 (why
  `recommendation_lowered` uses the model's raw reply, not the checked one) —
  partly right, corrected: the checked `request` is always `None`, so every
  reason would read "no action named". Q2 (reading the records): (b) right;
  (a) right that the model chose escalate, corrected that its confidence is
  not known from the record; (c) wrong at first, corrected — `None` means the
  recording lines never ran (time out or unusable reply). Q3 still to ask.

- **2026-10-27 (EV1): evaluation harness before specialists.** The developer
  approved the order: Phase 3 first, a current single-agent baseline, Phase 1
  PydanticAI specialists inside the existing Pydantic Graph, then Phase 2
  ground-truth-gated memory with observational memories retained. The developer
  additionally asked for a full nine-case master run now and another after the
  final phase, using the same case config and comparing accuracy, tool calls,
  runtime, and per-agent work. Teaching walkthroughs follow each phase's code
  and tests and do not block PR creation. No agent architecture, simulator,
  memory or tool behavior changed in EV1.

  `capstone/evals.py` reads evaluator-only scenario config, runs the existing
  `run_experiment`, and writes one JSON report with per-case expected faults,
  conclusion, diagnosis label, correctness, calls, runtime, and attributed
  steps. The raw `ExperimentRecord` JSONL is retained for later relabelling
  without rerunning the model. Hand labels use the existing `LabelBook`;
  optional TypeSafe proposals remain unjudged when marked for review.
  `compare_reports` checks matching scenario IDs and expected faults before
  computing before/after changes. `DecisionRecord.agent` and `ModelCall.agent`
  default to `research_agent`; `record_of` transfers these to `AgentStep`, so
  future specialists can identify themselves. Older records remain readable.
  `--watch` passes through the existing live progress hook and flushes output
  so the terminal shows each step immediately. A four-case preliminary run
  was stopped before any case completed when the developer requested the full
  nine-case master with visible progress. The master uses `python -u` and
  `--watch`. A second copy of that command started in the interactive terminal
  while the tool-launched copy was running. Both wrote to the same raw path;
  the tool-launched copy was stopped and only the interactive run continues.
  `reserve_raw_output` now claims a raw file exclusively before model calls,
  preventing later concurrent runs from mixing rows at the same path. The
  interactive run ended after two completed cases without a final report.
  Its two records were copied to a clean raw file, checked against the scenario
  prefix, and the remaining seven cases resumed under the same run name.
  `check_resume` refuses a different run name, order or duplicate; `--resume`
  continues the saved prefix with the existing episode runner. The mixed raw
  file is excluded from the PR.
  `evals/scenarios.json` lists the nine fixed known-answer cases (two each for
  the four MVP faults and one compound challenge). `tests/test_evals.py` checks
  config validation, full episode scoring boundaries, uncertain labels,
  comparisons and the live progress hook. The complete local suite passed
  1,410 tests; eight focused tests passed after the progress, output
  reservation and resume options. Live
  baseline result and CI status to record after they finish. Understanding
  remains no until the walkthrough.

- **2026-10-27 (A15): manual-search guidance when a manual is available.**
  Built ungated at the developer's request to build, merge with green CI,
  then quiz. Understood: no — developer to review.
  `agent/model_policy.py` adds `manual_use_note(tools, phase)`, which returns
  guidance only when `search_manual` is offered and the phase is
  investigate/test. `ModelPolicy.decide` and `interpret_and_decide` append
  it to their prompts: before recommending a repair, search the observed
  symptom and relevant procedure unless those sections were already
  retrieved. Use the manual to choose checks against current factory
  evidence; a manual describes the machine model, not the cause here.
  Respect search limits, reuse retrieved sections, and state limitations
  rather than retrying endlessly after failure/exhaustion. Approval and
  post-action verification remain mandatory. Verification prompts do not
  receive this research guidance. No manual is enabled automatically:
  existing `--manual` configuration still controls tool availability.
  `tests/test_model_policy.py` adds 12 prompt-contract cases: both question
  modes, with/without the manual tool, across investigate/test/verify. The
  four enabled research cases failed before implementation. Dependency sync,
  all 110 policy/manual/provenance tests, Ruff lint/format, CI-group validation
  and `git diff --check` passed. Independent read-only review found no
  defects. CI must pass before merge. This is prompt guidance, not a
  hard repair gate; no live model called and manual use/diagnostic benefit
  remain unmeasured.
  Final integration with A12-A14: all 322 affected settings, policy, loop,
  investigation, episode, experiment, manual, provenance and verification
  tests passed (1m34s). The scripted repair now covers all four combinations
  of `STEP_QUESTIONS` (1/2) and `STATE_ACTION_BAR` (true/false), asserting the
  recorded settings and actual threshold visibility as well as successful
  repair/verification. Static checks and CI-group validation passed again.

  **Whole-build summary for later review:** `.env.example` and `settings.py`
  expose the two independent controls (defaults 2 and true; real `.env`
  untouched). `agent/policy.py` defines the combined reply, and
  `agent/loop.py` validates/applies beliefs, budgets and cached next steps.
  `agent/state.py`, `episode.py` and `experiment.py` retain both settings
  for comparison, including early failures and compatibility with older
  records. `agent/model_policy.py` asks the combined question, conditionally
  displays the threshold, advises one bounded discriminating check, and
  advises available manual searches before repair. Existing simulator
  reality, evidence provenance, human approval and post-intervention
  verification stay under their existing owners. Tests changed in
  `test_settings.py`, `test_model_policy.py`, `test_agent_loop.py` and
  `test_agent_investigation.py`; `docs/MVP_SCOPE.md` and this log record
  what was built. The frontend-settings note was recorded separately.
  Understanding remains no until the developer's post-merge quiz; live
  speed, accuracy and manual-use comparisons remain outstanding.


- **2026-10-27 (A14): check before stopping, prompt guidance.** Built ungated
  at the developer's request to build, merge with green CI, then quiz.
  Understood: no — developer to review. `agent/model_policy.py`'s
  `SYSTEM["decide"]` now tells investigation/testing to make one
  discriminating check before stopping with a leading but uncertain
  explanation, if it could change the conclusion and budget permits:
  compare the same sensor on another machine, or at most one wait of about
  10 ticks followed by a re-read. Say what the check showed, reuse checks
  already answered, and do not keep waiting to raise confidence. Waiting
  advances the simulated fault. Stop honestly if the check is already done
  or the budget cannot cover it. Verification after intervention remains
  mandatory. `ModelPolicy.decide` and `interpret_and_decide` already use
  this shared system prompt, so both step modes receive the guidance.
  It names no numerical confidence bar, so hiding the bar remains possible.
  This is guidance a model can ignore, not the alternative hard loop-level
  stop refusal. No budgets, tool permissions or simulator behavior changed;
  no additional setting. `tests/test_model_policy.py` adds two cases proving
  the actual emitted system includes the bounded-check guidance in both
  question modes; they failed before the change. Dependency sync, all 142
  policy/loop/verification tests, Ruff lint/format, CI-group validation and
  `git diff --check` passed. Independent read-only review found no defects.
  After integrating the merged A13 setting, the same affected checks passed
  again (144 tests, including the visibility regressions).
  CI must pass before merge. No real model called: whether diagnoses improve,
  false alarms remain untouched or investigations take longer is unmeasured.


- **2026-10-27 (A13): optional action-bar visibility.** Built ungated at the
  developer's explicit request to build all four additions, merge after
  green CI, then quiz afterward. Understood: no — developer to review.
  - `settings.py`: `Settings.state_action_bar` reads `STATE_ACTION_BAR`,
    default true; `.env.example` documents true/false. Real `.env` untouched.
  - `agent/state.py`: `InvestigationState.state_action_bar` records the
    configured visibility. `episode.py` initializes it before planning and
    passes it into `InvestigationDeps`, so early outages still record it.
  - `agent/loop.py`: `InvestigationDeps.state_action_bar` controls
    `ask_policy`'s copy: hidden means `action_confidence_needed` is None.
    The enforcement value `min_action_confidence` stays on the dependencies;
    `check_conclusion` and human approval are unchanged.
  - `agent/model_policy.py`: `action_bar_note` also checks visibility, so a
    direct model-policy caller cannot accidentally display a hidden bar.
  - `experiment.py`: `ExperimentRecord.state_action_bar` and `record_of`
    save visibility; old records load with None (unknown).
  Nine new tests in existing CI-grouped files `test_settings.py`,
  `test_agent_investigation.py` and `test_model_policy.py` cover the two
  environment values and default; prompt omission; identical enforcement
  with the bar shown/hidden above/below the threshold; recording an
  overruled intervention; early outage metadata; old-record compatibility.
  All nine passed. Dependency sync, Ruff lint/format and CI-group validation
  passed; full `uv run pytest`: 1,370 passed (8m52s) on the visibility branch
  before integrating the separately merged A12 change. After integration,
  all 237 settings, model-policy, loop, investigation, episode and experiment
  tests passed; static checks and CI-group validation passed again.
  Independent read-only review
  found no defects. No real model called; confidence effects and live
  comparison against the master run remain unmeasured.

- **2026-10-27 (A12): one-question steps, selectable with STEP_QUESTIONS.**
  Pre-implementation understanding passed: the developer identified updated
  beliefs and the requested tool as the two outputs, then identified code
  as the authority that decides whether the request is allowed. Implemented
  on `feature/step-questions`. The developer then explicitly requested
  "make the changes first then merge then quiz me after": build and merge
  all four requested additions after green CI, with the closing questions
  and technical walkthrough deferred until after merging. Understanding
  remains no until demonstrated. Other requested changes (the
  `STATE_ACTION_BAR` switch, check-before-stopping guidance and manual-search
  guidance) remain separate components, not implemented in this change.
  - `settings.py`: `Settings.step_questions` accepts 1 or 2, defaults to 2;
    `.env.example` documents the switch. The real `.env` is untouched.
  - `agent/policy.py`: `InterpretedStep` holds an interpretation and a next
    decision. `ReasoningPolicy.interpret_and_decide` defines the combined
    policy question; custom policies need it only when using mode 1.
  - `agent/model_policy.py`: `StepAnswer` adds an interpretation to the
    existing flat `NextStep` answer, keeping its call/stop validation.
    `ModelPolicy.interpret_and_decide` asks `DECIDE_MODEL` (or the default)
    one question for both parts and refuses tools not offered. Separate
    `INTERPRET_MODEL` calls are unused inside the loop in mode 1.
  - `agent/loop.py`: `InvestigationDeps.step_questions` selects the mode.
    `run_inner_loop` still asks the first decision of each phase separately;
    after a usable tool result, mode 1 asks the combined question, validates
    the beliefs with `apply_interpretation`, and caches the next decision.
    Every cached step still passes the next turn's budget/repeat checks.
    Even the last permitted result is interpreted; a combined timeout keeps
    its evidence and stops on timeout. Invalid combined answers keep the
    evidence, apply neither part and count as unproductive. Mode 2 retains
    the existing path. Applies to investigate, test and verify phases.
  - `agent/state.py`: `InvestigationState.step_questions` records the mode;
    `episode.py` initializes that mode before planning (so an early model
    outage still records it) and passes it into the loop dependencies.
    `experiment.py`: `ExperimentRecord.step_questions` and `record_of` save
    the mode, while older records load with None (unknown).
  Tests added to existing CI-grouped files `test_settings.py`,
  `test_model_policy.py` and `test_agent_loop.py`: configuration and invalid
  modes; one combined model question with the stage deadline; unoffered
  tools and mixed call/stop replies refused; invented evidence refused;
  last-result interpretation; research and verification call limits;
  cached choices blocked after time runs out; invalid-reply stopping;
  timeout evidence retention; both modes complete the same scripted repair
  and save their mode even after an early planning outage, and older records
  still load. That offline example
  takes 11 questions in mode 1 versus 14 in mode 2, with the same successful
  repair. This is scripted, not measured live speed or model accuracy.
  Verification: `uv sync --all-extras`; full `uv run pytest`: 1,381 passed
  (8m04s). After collection, the early-planning-outage regression was added
  and the metadata initialization fixed; the final model-policy/episode
  rerun passed 72 tests with a separate `--basetemp`. An earlier concurrent
  focused rerun had 70 passes and two SQLite cleanup errors because both
  runs used the fixed `.pytest-tmp`; the isolated rerun resolved those.
  Ruff lint/format, CI-group validation and `git diff --check` passed.
  Independent read-only review found no defects, including the metadata fix.
  No live model
  called. Compare identical known-answer cases in
  modes 2 and 1, one run at a time, holding the other settings fixed; label
  and compare causes right, repairs requested, tool calls, elapsed seconds
  and invalid replies. Live accuracy/speed comparison remains outstanding.

- **2026-10-27: future frontend settings controls (documentation only).**
  At the developer's request, added a note to `docs/MVP_SCOPE.md` Future
  Work 8: if a frontend is built, expose user-adjustable `.env` settings as
  controls, including `STEP_QUESTIONS` and `STATE_ACTION_BAR`. Backend
  validation and action-threshold enforcement remain in force; API keys
  and other secrets remain backend-only. No frontend or runtime behavior
  changed; implementation and understanding statuses are unchanged. Local
  tests skipped under AGENTS.md section 11's docs-only rule.

- **2026-10-26: Brandon Reff acknowledgment (documentation only).**
  Added a README acknowledgment thanking Brandon Reff for helping improve
  simulator realism through manufacturing feedback, at the developer's
  request. No runtime behavior or tests changed; understanding statuses
  unchanged. No teaching gate applies to this credit.
  Verification: dependency sync, 1,332 offline tests, Ruff lint and
  formatting (218 files), and the CI test-group check passed.

- **2026-10-26 (LV): live progress view in the terminal (next build
  candidate 9). Built ungated at the developer's request; understood after
  the PR #81 walkthrough (below).** Terminal only; a later frontend (Future
  Work 8) would sit on the same hook. Changes:
  - `agent/loop.py`: `InvestigationDeps.watch` (a callable, default None)
    and `notify(state, deps)`, which hands the watcher a deep copy of the
    state (so it can read, never change, the investigation) and logs and
    ignores a watcher that raises (no exception text logged: it could quote
    evidence). Called at the top of each inner-loop turn, just before the
    policy is asked (the slow part), so the last result is on screen.
  - `agent/investigation.py`: every graph stage runs through `staged`, which
    calls `notify` after the stage; `notify` also runs just before
    `human_review` (the proposal is on screen before the approval question)
    and after a model-unavailable stop. The hook is not in `record()`: its
    20 callers do not have the deps, and the watcher prints whatever is new
    since it last looked, so a few call sites miss nothing.
  - `episode.py`: `run_episode(watch=...)` passes it on.
  - `progress.py` (new): `ProgressView` keeps its own place (decisions
    shown; last beliefs, conclusion, proposal, check) and prints only what
    changed: each step with its tool call and evidence (one line each,
    memory and manual answers labelled), beliefs when they change, the
    conclusion, each proposal status, the check. `truth_lines` (evaluator
    side) is printed by `watch_episode` only after the run, under its own
    heading. Command: `python -m capstone.progress --seed N [--fault F]
    [--kind K] [--approve console|all|none] [--memory] [--manual MODE]
    [--hazards]`; console approval is the default; `--memory` learns nothing.
  Tests: `tests/test_progress_view.py` (10, Episode CI group). Scripted only;
  nothing ran against a real model.
  First live run by the developer (seed 7, bearing on CNC-03): every step
  printed as it happened; the agent read only ~30-tick windows, blamed job
  23's start, escalated at 0.85 and asked for nothing (an evidence miss by
  the plan's categories; one run, not a conclusion). It showed one display
  bug, **not fixed**: a stop line prints the agent's whole stop reason
  (`step_line` does not `shorten` `information_needed` there).
  Developer's notes added to `docs/MVP_SCOPE.md`: Future Work 8 (a frontend
  must hand the watcher's work to another thread, since the watcher runs in
  the run's thread) and Future Work 3 (roles that ask several model
  questions outside `run_inner_loop` need more `notify` checkpoints; no role
  field on `DecisionRecord` yet).
  **PR #81 pre-merge walkthrough, 2026-10-26.** Q1 (what a watcher could do
  with the live state; why a shallow copy is not enough): said it could give
  the agent information (right, one way); taught erasing `seen_calls` or
  `decisions` and changing the conclusion, and that a shallow copy shares
  the inner lists. Asked why a reporter would change anything: answered that
  the copy guards against accidents (an in-place `content[:90]` or `sort()`
  in a display), as the tool boundary guards the truth by construction.
  Follow-up right (`hypotheses.clear()` reaches the live run, replacing
  `conclusion` does not). Q2 (only stage-level `notify`): described the
  current per-turn behaviour; re-taught that steps #3-#10 would appear all
  at once when `investigate` ended; follow-up right (#12 appears when `test`
  ends). Q3 (truth shown live): said a labeller would be biased (true: hand
  labels are blind); corrected that the console approver is the main
  problem, since approvals would then rest on the truth; follow-up right.


- **2026-10-26: docs: "Next build candidates" brought up to date
  (developer's request).** `docs/MVP_SCOPE.md`: the table now lists open
  items in ranked order with a Rank column, and done items (1, 2, 3, 6, 8,
  10) on one line. Numbers stay as fixed IDs. The scored single-agent run
  comes first, before any item. Open: 4 (kW), 5 (servo/hydraulic as
  fault-pack entries), 7 (evaluator labels: only the agreement check is
  left), and new items 11 (three-day profile usable in experiments, longer
  monitor wait), 12 (a live memory comparison run), 13 (comparison
  follow-ups: `--cases`, repeats, store header), 14 (keyword and semantic
  recall made comparable), then 9 (live progress view, never built). The
  placement of 7, 9 and 11-14 is the coding agent's proposal for the
  developer to confirm. Documentation only; no understanding status changed.

- **2026-10-26: docs: which tests to run before pushing (developer's
  rule).** AGENTS.md section 11 step 3 no longer asks for the full
  `uv run pytest` before every push: docs/CI/config changes skip local
  tests; code changes run the touched modules' tests, ruff and the CI group
  check, then CI runs everything; the full suite still runs locally for
  shared modules (loop, scoring, contracts, simulator core), when CI is down
  or slow, or before a live model run. Merging still needs green CI. Reason:
  CI already runs every group and a full coverage run on each PR; the local
  full suite took 19 minutes on 2026-10-26. Documentation only; no
  understanding status changed.

- **2026-10-26: stale-branch cleanup and Gemma 4 E4B Cloud Run feasibility
  (documentation only; deployment blocked on project access).** Deleted
  12 remote branches only after verifying their tips were ancestors of
  `origin/main`: `claude/gifted-hamilton-eqyqf4`,
  `docs/brandon-feedback-servo-hydraulic-current`,
  `docs/fault-pack-registry-plan`,
  `docs/high-priority-bearing-power-simulator`,
  `docs/mmr-episodic-retrieval-20261023`,
  `docs/technician-voice-last-priority-20261021`,
  `feature/bounded-recall`, `feature/compound-challenge-experiments`,
  `feature/episodic-memory-reflection`, `feature/prompt-budget-pacing`,
  `feature/reasoning-working-memory`, and `feature/tree-of-thought`.
  Deleted four fully merged local branches: `claude/build-track-a97149`,
  `claude/modules-track-460217`, `feature/episodic-memory-reflection`, and
  `feature/reasoning-working-memory`. PR #72 merged elsewhere during the
  operation; refreshed state after its remote branch disappeared. Kept
  detached worktrees, new active branches, uncommitted edits and result
  files. `docs/GEMMA_CLOUD_RUN.md` records official model IDs, GPU costs,
  CPU free-allowance arithmetic, the project-access status, and the
  staged probe/integration plan. The user supplied project ID
  `capstone-project-512814`; portable gcloud 590.0.1 was downloaded and
  checksum verified under ignored `.chroma/cloud-run-tools/`; version and
  account-list commands succeeded, and browser login was started.
  No service deployed or real model run;
  zero-cost inference remains unverified. No functions, classes, runtime
  settings or dependencies changed. Docs only: understanding statuses
  unchanged; provider integration has not passed a teaching gate.
  Verification: `uv sync --all-extras`; `uv run pytest` (1,258 passed);
  Ruff lint and formatting (211 files), CI test-group check, and
  `git diff --check` passed. No real model called.

- **2026-10-26: L9: the live progress view in experiments, on by default.
  Built first at the developer's request; understood: no, to be taught
  before merging.** The developer asked to see what tonight's 9-case run was
  doing; the progress view (PR #81) only started its own single episode, so
  the running experiment (started without it) was left untouched and this
  applies from the next run. `run_experiment` gains `watch` (a line
  writer): each case prints a header ("=== case N: <scenario> ===") and then
  the progress view's lines as the agent works (`ProgressView` passed as
  `run_episode`'s `watch`). The truth is never printed by the experiment's
  view, unlike `python -m capstone.progress`: conclusions are labelled by
  hand afterwards and seeing the answer first would bias the labels; it stays
  in the results record. `experiment run` watches by default; `--quiet` gives
  the old one line per finished case. Other callers of `run_experiment`
  (memory comparison, tests) are unchanged (watch defaults to None). Tests:
  `test_experiment.py` (a watched case prints its header and live lines and
  no truth; the command watches by default and `--quiet` turns it off).
  Merged without the pre-merge walkthrough at the developer's request,
  during the scored run; the walkthrough is owed (with L8's).

- **2026-10-26: L8: a chain of fallback models, and Cohere's output cap.
  Built first at the developer's request, before tonight's scored run;
  understood: no, to be taught in the pre-merge walkthrough.** The developer
  asked for several fallbacks, so a spent quota (Cloudflare's daily one) does
  not end a run: Cloudflare, then Cohere, then Requesty (one request at a
  time there, which suits a last resort when runs go one at a time).
  `FallbackClient` already took any number of models with equal time shares;
  only the setting was single. `settings.fallback_models` splits
  FALLBACK_MODEL on commas, in order, without repeats; `clients_for_jobs`
  appends each one a job does not already have. A single model works as
  before. Probes the same evening (one call at a time): NVIDIA Nemotron 120B
  one HTTP 500 then 5 of 5 answered in 1-5 s; Cloudflare Llama 3.3 70B
  answered; Cohere `command-a-03-2025` refused with HTTP 400 because the
  project asks for 16,384 output tokens and Command A allows 8,192, so
  `Provider.max_output_tokens` (Cohere 8,192) caps the request (`_capped`),
  after which it answered; Requesty `google/gemma-4-31b-it` answered in 3.9 s.
  The developer's suggestion `requesty/nvidia/nemotron-3-super-120b-a12b` is
  listed by Requesty at price 0 but answered 404, origin "provider" (NVIDIA
  says not found), as Nemotron Nano did through Requesty on 2026-10-21; it is
  also the main model on the same servers, so it would fail when NVIDIA does.
  Tonight's chain, set for the run only through the run's environment (the
  `.env` is not edited): cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast,
  cohere/command-a-03-2025, requesty/nvidia/nemotron-3-ultra-550b-a55b (the
  developer's choice, answered in 1.3 s through Requesty). The developer's
  rule: on NVIDIA's own API only Super 120B is used, because every model on
  that endpoint shares one rate limit on the key, so a second one would cause
  429s for the main model; through Requesty (its own account) Ultra 550B is
  fine. Requesty forwards it to NVIDIA, so a wide NVIDIA outage could
  take it down with the main model; Cloudflare and Cohere sit between them.
  Gemma 4 31B (Requesty, 3.9 s) stays a tested spare. Tests:
  `test_chat_client.py` (several fallbacks in order, without repeats; Cohere
  never asked for more than 8,192 while others get the setting; a first
  fallback out of quota (HTTP 429 twice) passes to the second). Merged
  without the pre-merge walkthrough at the developer's request (dinner before
  the scored run); the walkthrough is owed. Not done:
  `.env.example` could not be edited from the coding session.

- **2026-10-26 (late): A11: MAX-HIGH changes 2 and 3. Built first at the
  developer's request ("not much usage left: build fix 2 and 3, teach them
  tomorrow"); one PR for both, to save usage; merged before teaching at
  the developer's request; the test (KA-01 to KA-03, MIN_ACTION_CONFIDENCE
  0.80 for that run only) and the walkthrough moved to 2026-10-27;
  understood: no.** Change 2:
  the loop writes the bar in force on the policy's copy of the state
  (`action_confidence_needed`, set in `ask_policy` from
  `deps.min_action_confidence`, like `seconds_for_question`), and the model
  policy's conclude prompt appends `action_bar_note`: intervene is accepted
  only at that confidence or above, with a cited evidence ID and a named
  action, otherwise it becomes escalate; below the bar, say which evidence
  would raise it. Because the number comes from the loop, the prompt can
  never state a different bar from the one enforced. Change 3: the bar is a
  setting, `MIN_ACTION_CONFIDENCE` (`settings.min_action_confidence`,
  default 0.9, 0 to 1), passed into `InvestigationDeps` by `run_episode`; the
  value is the developer's decision, to be set from runs with changes 1 and
  2, never from one run. Tests: `test_agent_investigation.py` (the policy is
  shown the bar the loop enforces), `test_model_policy.py` (the note states
  the bar only when the loop set it). Owed for 2026-10-27: the walkthroughs
  for #85, #86, #89 (A10, Q1 asked) and this PR (A11); then a run of the
  known-answer cases to measure changes 1 and 2.

- **2026-10-26 (evening): A10: the policy's own recommendation is recorded
  (MAX-HIGH change 1). Built first at the developer's request; understood:
  no, to be taught before merging.** Measurement only; the agent's behaviour
  is unchanged. `agent/investigation.py`: `why_not_acted(deps, conclusion,
  request)` names the first unmet condition for an intervention ("no action
  named", "no evidence cited", "confidence 0.80 below 0.90"), and
  `check_conclusion` now uses it for its decision (same three conditions as
  before). `conclude` keeps the policy's answer apart from the checked one:
  `state.policy_recommendation` is what the policy recommended,
  `state.recommendation_lowered` why an intervention was lowered (computed
  from the policy's own answer, before the check). `experiment.py`:
  `ExperimentRecord` gains both fields (None in older results, which still
  read), and the report line adds `overruled=intervene->escalate (<why>)`
  when it happened (`overruled_text`). Tests:
  `test_agent_investigation.py` (an overruled intervention keeps the
  policy's own recommendation and a reason; the exact reason for each of the
  three conditions; an accepted intervention and a chosen escalate record no
  lowering), `test_experiment.py` (the report shows the overrule and why;
  results from before still read). Tonight's records cannot be filled in
  after the fact; the next run will tell "chose escalate" from "overruled".

- **2026-10-26 (evening): the scored single-agent run, done (results only;
  nothing built).** The "NEXT SESSION" run below, on `main` at `e65bd8f`: the
  nine known-answer cases, one at a time, 16:32-18:21, NVIDIA Super 120B with
  the fallback chain Cloudflare, Cohere, Requesty Ultra 550B (for this run
  only). Hand-labelled by the developer; three labels first followed the true
  fault and were relabelled by the conclusions' words at the developer's
  decision (KA-03 servo on CNC-06, KA-05 and KA-06 no cause). Scored (one-fault
  cases): **5/8 root causes** (rule baseline 8/8), 5/8 targets, 4/8 right
  recommendations, **0 fixes asked for** (baseline 3), 0 unnecessary, 77% of
  relevant evidence (baseline 44%). Misses: KA-03 and KA-05 reasoning (all
  evidence gathered), KA-06 evidence; KA-09 (not labelled) named only the
  decoy. No case ended "model unavailable": 213 of 220 questions answered
  despite 76 timeouts and 51 HTTP 500 from NVIDIA; Cohere answered when
  Cloudflare's quota ran out. Details, tables and limits:
  `docs/benchmarks/2026-10-26-scored-single-agent.md`; labels
  `docs/benchmarks/2026-10-26-labels-single-1.jsonl`; baseline
  `docs/benchmarks/2026-10-26-baseline-known.txt`. Conclusion for 2026-10-27:
  the MAX-HIGH fix first, then a reasoning role (critic or analyst) as the
  first multi-agent role.

- **2026-10-27: the two master runs, done (results only; nothing built).**
  Seeds 6 and 9 (bearing) and 7 (bad batch) at the 0.80 bar stated in the
  prompt, `main` at `25f0df0`, one at a time. A: manual off
  (`results-bar80.jsonl`, 09:41-10:19). B: manual on, by meaning
  (`results-bar80-manual.jsonl`, 10:20-10:59). Not hand-labelled; read from
  the conclusions and the records.

  | Seed | A: own recommendation, confidence | A: fix asked for | B: own recommendation, confidence | B: fix asked for |
  |---|---|---|---|---|
  | 6 bearing | escalate, 0.75 (timeout) | no | **no_action, 0.85** (wrong: "transient spike") | no |
  | 9 bearing | escalate, 0.70 | no | **intervene, 0.90** | **`replace_bearing` CNC-05, right, fault resolved** |
  | 7 bad batch | escalate, 0.90 | no | escalate, 0.65 (timeout; blamed CNC-03/04/06) | no |

  - **The manual was never searched: 0 searches in 0 of 3 runs in B.** The
    tool was on and offered. So A and B differ only by run-to-run variance (the
    same seed gave opposite conclusions on seed 6), and B says nothing yet
    about what the manual adds. Next step if the manual is to be tested: the
    prompt does not say when to consult it (candidate item 20 in
    `docs/MVP_SCOPE.md`).
  - **Nothing was overruled in either run** (fix 1): every escalate was the
    model's own choice. Confidence moves a lot between runs of the same case
    (seed 9: 0.70 in A, 0.90 in B), so the bar is not what holds back fixes;
    what the agent checked before concluding is (see the planned
    check-before-stopping rule, item 19). Seed 9 in B, the first fix any run
    has asked for: belief 0.41 to 0.90 after load and temperature, `wait(10)`
    and re-reading, and a comparison with CNC-04, then `replace_bearing`,
    approved, carried out; the simulator confirms the fault gone; the agent's
    own check afterwards said `inconclusive` (the lesson-run finding 1 again).
  - **Time:** A 11-15 min per case (6 timeouts in seed 6, Cloudflare answering
    HTTP 429 on every ask), B 10-15 min; B: 79 questions, 13 failed attempts
    (all timeouts), 2 refused replies, about 773 s per episode (A about 760 s).
  - **Seed 7 again:** both runs read the batch-2 failures as an odd/even job
    pattern or as machines (CNC-03/04/06), not as a batch, as on 2026-10-26.

- **2026-10-27: planned setting, questions per step; Cloudflare left out of
  the chain for now (docs only; nothing built).** Measured on the first case
  of the 0.80-bar test (seed 6, bearing, `results-bar80.jsonl`): 881 s, of
  which 837 s inside model calls (tools and simulation 43 s); 75% of the
  model time went on 30 successful answers (about 21 s each, NVIDIA's median
  19 s), 16% on 6 timeouts, 7% on 2 refused replies, 2% on Cloudflare's HTTP
  429. 33 questions; the case ended on `stop=timeout`. Each tool call costs two
  questions (`decide`, then `interpret` of its result), about 40 s together.
  - **Planned setting `STEP_QUESTIONS` (not built; item 17 in
    `docs/MVP_SCOPE.md`).** `2` (default, today's behaviour): `interpret`
    and `decide` are separate questions. `1`: one question per step, "what
    does the newest evidence mean, and what next?", answered as one object
    holding the interpretation and the next decision (a new contract
    combining `Interpretation` and `NextStep`), checked by the same rules
    (the stop-step rule, tools offered, evidence IDs); the loop still
    enforces every budget. It would roughly halve the model questions per
    step. Risks: one refused reply loses both parts, and a combined answer
    may reason less well, so measure: the same known-answer cases both ways
    on the same code, one run at a time (causes right, fixes asked for, tool
    calls, seconds per episode, refused replies). Touches
    `agent/model_policy.py` (`interpret`, `decide`, their prompts),
    `agent/loop.py` (`run_inner_loop`), `settings.py`, and the experiment
    record (note the setting). A second, separate lever already exists:
    `INTERPRET_MODEL` and `DECIDE_MODEL` can name faster models (Cloudflare's
    median answer 5 s, Cohere's 2 s, against NVIDIA's 19 s); to be measured
    for quality.
  - **Cloudflare out of the chain until its quota resets.** In the 09:41 run
    it answered HTTP 429 on all 15 asks (the quota was spent in the previous
    evening's run), and each question paid four failed tries before the next
    model. For the next runs the chain is `cohere/command-a-03-2025`, then
    `requesty/nvidia/nemotron-3-ultra-550b-a55b` (set in the run's
    environment, `.env` untouched, no code change). Re-add
    `cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast` when a one-question
    probe answers. The run in progress was left running with it. A code
    answer to the same problem (skip a provider after repeated 429s) is the
    circuit-breaker candidate, row 5 of `docs/FUTURE_WORK_REEVALUATION.md`.
  - **Planned setting `STATE_ACTION_BAR` (not built; item 18 in
    `docs/MVP_SCOPE.md`).** On (default, today): the conclude prompt states
    the confidence bar (`action_bar_note`, fix 2). Off: the prompt does not
    mention it; the code still enforces `MIN_ACTION_CONFIDENCE`, and fix 1
    still records the model's own recommendation and why it was lowered.
    Why: confidence should be an honest estimate, not a number aimed at a
    threshold the model can see. In the 0.80-bar test the model chose
    escalate itself (not overruled) at confidence 0.75 (seed 6, was 0.80 the
    evening before) and 0.70 (seed 9, was 0.85): lower with the bar stated,
    but only two cases from different runs, and this model's answers vary from
    run to run, so it is not shown that stating the bar caused it. A cleaner
    variant: the model gives its diagnosis, an honest confidence and the
    action it would take, and only the code decides act or escalate. Touches
    `agent/model_policy.py` (`action_bar_note`, `conclude`), `settings.py`
    and the experiment record (note the setting). Measure: the same three
    cases with the bar hidden at 0.80 against master run A below; repeat a
    case if the difference is small.
  - **The two master runs, for now (developer, 2026-10-27): the same run
    with the manual off and on, nothing else different.** Seeds 6 and 9
    (bearing) and 7 (bad batch), one at a time, `main` at `25f0df0`, bar 0.80
    stated in the prompt, two questions per step, live view on, the bar's
    value and chain set in the run's environment only. **A, manual off**:
    `results-bar80.jsonl`, chain NVIDIA, Cloudflare, Cohere, Requesty Ultra
    550B. **B, manual on** (`--manual`, by meaning): `results-bar80-manual.jsonl`,
    chain NVIDIA, Cohere, Requesty Ultra 550B (Cloudflare answered none of A's
    asks, so A's answers came from the same models). Compare A with B only,
    for what the manual adds. The main folder stays on `25f0df0` until B is
    done, so the code is identical. The hidden bar, one question per step and
    the 0.9 bar are planned, not scheduled: no usage left for more runs.
  - **Planned prompt rule: check before stopping (not built; item 19 in
    `docs/MVP_SCOPE.md`).** Candidate wording for the `decide` prompt
    (`agent/model_policy.py`): once one explanation clearly leads but is
    below the confidence needed to act, do not stop yet; make one check that
    could separate it from the others, for example read the same sensor on
    another machine, or `wait` a few ticks (about 10) and read it again, and
    say what the check showed. Evidence so far, from run B (manual on, never
    used), and a single case, so a hint only: on seed 9 the agent's belief in
    a mechanical fault went 0.41 to 0.68 after reading load and temperature,
    to 0.82 after `wait(10)` and re-reading vibration, and to 0.90 after
    comparing CNC-04; it then asked for `replace_bearing` (approved,
    carried out). In run A, same seed, it stopped at 0.70 on `no_useful_action`
    after fewer checks and escalated. On seed 6 run B concluded a transient
    spike (no_action, 0.85, wrong for a bearing case) and never waited and
    re-read before concluding; that is the check that tells a spike from a
    rising fault. Cautions: a `wait` moves the factory's clock, so a real fault
    keeps developing during it (bound it: one wait, about 10 ticks, only when
    the leading belief is between roughly 0.5 and the bar); each check spends
    tool calls from a time budget that was already running out; a prompt rule
    can be ignored. A loop-level alternative that cannot be ignored: refuse a
    policy stop (`evidence_sufficient`, `no_useful_action`) while the leading
    belief is below the action bar and budget remains, and ask for one more
    test. Measure either way on the same known-answer cases against the master
    runs, one run at a time (causes right, fixes asked for, confidence,
    seconds per episode, false alarms still left alone). It changes what the
    agent does, so teach it first.

- **FIRST THING ON 2026-10-27 (MAX-HIGH PRIORITY, developer's decision): the
  agent never recommends a fix.** In tonight's scored run (started 16:32 on
  `e65bd8f`, 9 known-answer cases, `results-single-1.jsonl`) the first three
  cases all ended `escalate` with no repair: KA-01 and KA-02 (bearing) found
  the right machine and cause at confidence 0.80 and 0.85; KA-03 (batch) was
  unsure (0.60). `check_conclusion` lowers "intervene" to "escalate" below
  `min_action_confidence` 0.9, the conclude prompt never states that bar, and
  the record keeps only the final recommendation. Before any multi-agent role:
  (1) record the model's own recommendation beside the final one; (2) state
  the 0.9 bar in the conclude prompt; (3) revisit the 0.9 value with the
  numbers from (1) and (2). Details: `docs/MVP_SCOPE.md`, "MAX-HIGH PRIORITY"
  (above Future Work 7) and ranked item 16. Also seen on KA-03: the new
  following-error sensor and servo repair pulled the agent from a bad batch
  toward a servo-drive replacement on CNC-06 (no repair was asked for before
  the time ran out).

- **NEXT SESSION: a scored single-agent run, before any multi-agent role.**
  The developer's point (2026-10-26): to know where a second agent could
  help, the current agent's misses must be scored first. The 2026-10-21 live
  numbers (about 3 of 8 one-fault cases right) were the coding agent's
  reading, not hand labels. Steps, one live run at a time:
  1. Probe the chat model and the fallback; stop if they fail.
  2. Score what already exists: label the nine conclusions in
     `results-5.jsonl` (`uv run python -m capstone.experiment label
     --results results-5.jsonl --labels labels-live-5.jsonl --by <name>`),
     then `experiment report --results results-5.jsonl --labels
     labels-live-5.jsonl`.
  3. A fresh run of the known-answer cases on today's `main` (`experiment
     run --name single-known-1 --known --out results-single-1.jsonl`),
     labelled and reported the same way; a second run if time allows, since
     answers vary between runs of the same case.
  4. Put the rule baseline beside it (`python -m capstone.baseline --known`).
  5. Read the report's miss labels per case (R4b): a reasoning miss (the
     evidence was gathered, the conclusion was wrong or escalated) is what a
     critic or independent analyst could fix; an evidence miss points at a
     research role instead. That choice picks the first multi-agent role.

- **2026-10-26: PR #83 pre-merge walkthrough (F5).** CI first failed on one
  job ("Install uv" timed out downloading the tool, before any test ran);
  re-run, all 15 green. The developer asked whether observable equipment
  changes how machines were observed before: no existing value changed;
  `list_machines` gained one field (a shape change: 7 pinning tests and
  `MachineObservation` updated); the other sensor tools, events (no new alarm
  on existing runs), settings, inspections and job histories are unchanged;
  old saved results lack the field. Q1 (why fix the false alarms in the
  sensor, not the alarm): said fix at the source, the sensor being the
  agent's source of truth; corrected: the sensor is the source of evidence,
  not truth; an alarm that read `machine.status` would read hidden reality
  (the alarm "fires on a reading, never on machine state"), would change
  every alarm (one shared class), while a powered-off transducer sending
  nothing matches the physics. Q2 (why fixed hydraulic positions): right
  that a random draw could give no or all machines hydraulics; added that
  fixed positions cost no draw (so no seed moved); corrected the downside:
  the agent learns which machines have hydraulics (not issues), and could
  memorise the layout instead of checking. Q3 (why the builder's extra draw
  is harmless): unsure (said nothing else changes); re-taught: the draw
  comes after the shared draws (fault, machine, start), only inside the
  hydraulic builder, which no existing run uses, and nothing is drawn from
  the generator stream after it. Understood (Q1 in part, corrected; Q3 after
  a re-teach).

- **2026-10-26: F5: the hydraulic-leak fault pack (Future Work 8 D, second
  part). Built first at the developer's request; understood: no, to be taught
  in the pre-merge walkthrough.** Which machines have hydraulics is fixed by
  position (`line.HYDRAULIC_POSITIONS`: CNC-02, CNC-05, CNC-07; no random
  draw) and observable (`has_hydraulics`; `hydraulics` in `list_machines` and
  `MachineObservation`). `HydraulicLeak` lowers hidden `hydraulic_health`
  while the pump runs (running or idle) and refuses a machine without
  hydraulics; `HydraulicPressureSensor` (bar) only on equipped machines;
  `ThresholdAlarm` gains `below=` for the low-pressure alarm at 55 bar;
  `defect_mark` adds `DEFECT_FROM_HYDRAULICS` 0.30 x leak squared;
  `start_hydraulic_repair` (40 ticks, refused without hydraulics, as is
  proposing it); pressure on a machine without hydraulics is refused by
  `get_readings`. Pack `hydraulic_leak` / `repair_hydraulics`, difficulty
  hard (proposed), not in the default draw; a forced leak keeps the seed's
  machine if equipped, else draws an equipped one, with the seed's start.
  Found and fixed while checking: the first version raised 518 low-pressure
  alarms in 40 runs without a leak, every time a machine went down (pump off,
  pressure 0); the monitor would have opened investigations on them. Now the
  transducer sends nothing while the machine is down (`available`). The
  700-tick fingerprints had missed it (no downtime in that window), so a
  second proof was added: full event logs over 2,500 ticks for every old
  fault on seeds 1-10 (including breakdowns), identical before and after, as
  are the 602 fingerprints (new sensors aside). The provider's typed check
  refused `list_machines` until `MachineObservation` gained `hydraulics`.
  Forced seeds 1-20: alarm 717-1,358 ticks after the start, no other alarm
  on the leaking machine. Tests: new `tests/test_hydraulics.py` (16, CI group
  Simulator); updated `test_build_line.py`, `test_factory_provider.py`,
  `test_fault_packs.py`, and the seven tests that pin exactly what
  `list_machines` shows (`test_job_history.py`, `test_load.py`,
  `test_observation_tools.py` twice, `test_production_line.py`,
  `test_quality.py`, `test_slow_when_worn.py`) for the new observable
  `hydraulics` field; the hidden-word check (no "health", "fault",
  "condition" text in any tool answer) passes unchanged. Not done: pump wear, oil temperature, fluid level, a
  sticking valve, pump power, a baseline rule, a known-answer case.

- **2026-10-26: PR #82 pre-merge walkthrough (F4).** Before Q1 the
  developer asked whether a worn drive would also raise power: yes in a real
  machine (more current), not in the build as it stood; the developer asked
  to add it in this PR, so `PowerSensor` gained `drive_kw` 1.0 x axis wear
  squared (healthy drives add 0; fingerprints still identical), and power no
  longer separates a worn drive from a worn bearing. Q1 (telling a worn drive
  from a worn bearing on the same machine): said following error and rejects
  rise (true, but rejects rise for both); taught what following error is (the
  gap between where the axis is told to be and where it is) and the
  differential checks; the developer then added that the drive leaves
  vibration and temperature flat (the deciding evidence). Q2 (a new mistake
  on ordinary runs, now that the sensor and repair are on every machine):
  right: mistaking a bad batch for the drive; added how scoring records it
  (wrong cause, and an unnecessary intervention if a replacement is asked
  for) and the evidence that should prevent it. Q3 (why hydraulics must be
  per machine, unlike servo): right: not every machine has hydraulics; added
  that a sensor on every machine would be evidence from absent equipment,
  that which machines are equipped must be an observable fact (it rules
  causes out), and that a forced hydraulic fault needs its own placement on
  an equipped machine. Understood (Q1 in part, completed).

- **2026-10-26: F4: the servo-drive fault pack (Future Work 8 D, first part).
  Built first at the developer's request ("keep the default draw over the
  original four faults, servo only when forced"); understood: no, to be
  taught in the pre-merge walkthrough.** Hidden: `MachineCondition.axis_health`
  and `MachineState.axis_replaced_tick`. `AxisDriveWear` lowers axis health
  from its start while the machine runs, faster under load, until the drive is
  replaced; ground truth `servo_drive_wear`. Evidence: `FollowingErrorSensor`
  (`following_error`, µm) on every machine, and a following-error alarm at
  20 µm on the line; `defect_mark` adds `DEFECT_FROM_AXIS` 0.35 x axis wear
  squared; `PowerSensor` gains `drive_kw` 1.0 x axis wear squared while
  cutting (asked for by the developer during the walkthrough: a worn drive
  draws more current), so power rises for a worn drive as for a worn
  bearing and stops separating the two. No vibration, temperature or
  working-speed effect. Repair:
  `Simulator.start_servo_drive_replacement` (60 ticks; finding "old drive
  badly worn / worn / in good condition"), action `replace_servo_drive` on the
  desk and in `propose_action`'s description. Pack: agent side
  (`servo_drive_wear`, `replace_servo_drive`), evaluator side (correct action,
  a cause, evidence: following error and events of the machine, inspection
  results), difficulty medium (proposed), `in_default_draw=False`.
  `DEFAULT_DRAW` (the original four, in order) is what a seed draws from and
  what `generator.FAULTS` and `--faults all` mean; `build_scenario` accepts
  any pack's name when forced. Decision: the sensor, alarm and repair are on
  every machine (every CNC has servo axes), so the agent's tool list and
  repair menu gain them in every run; only the fault is opt-in. Proof of no
  change: 602 fingerprints (seeds 0-59, every forced old fault, both bearing
  profiles, readings and events over 700 ticks) identical, with the new
  sensor's readings left out. Checked on forced seeds 1-20: alarm 730-1,680
  ticks after the start, no vibration alarm on the servo machine; no
  following-error alarm in 40 runs of the other faults. Tests: new
  `tests/test_servo_drive.py` (17, CI group Simulator). Not done: hydraulics;
  encoder faults, drive overheating, current in amps, a breakdown, a
  baseline rule, a known-answer case.

- **2026-10-26: PR #80 pre-merge walkthrough (F3).** Three questions.
  Q1 (sorting `PACKS` alphabetically): said everything would change and a
  test would catch it; corrected: the same first draw (seed 6: index 2)
  now names a different fault (false alarm instead of wrong setting), with
  the same machine and start tick, so every seed the generator lets choose
  changes kind, while runs that force the fault (`--faults`, the baseline's
  every-fault runs, the known-answer cases) are unchanged; two tests catch
  it. The developer asked for the timing point to be explained further
  (taught as a fixed deck of draws: fault, machine, start, strength; the
  sort relabels the first draw only) and whether the agent would then see a
  false alarm (yes, as evidence: a passing spike instead of a speed change;
  the agent never sees the label). Q2 (moving `correct_action` to the agent
  side): right that it would hand the agent ground truth, and that two
  copies drift; corrected: `action` is the repair the pack adds to the
  desk's menu (a capability), not the action the agent took. Design caveat
  found while answering: `AgentSide` pairs a kind with its action, so
  printing `agent_side()` whole would leak the mapping; today only the
  unpaired lists reach the agent. Q3 (appending a fifth pack): did not know;
  re-taught with a spinner (the same random number lands in different slices
  of four or five, and Python's choice may use a different number of draws,
  moving machine and start too); fix: keep the default draw over the original
  four and add new packs only on request, from their own stream. The
  developer connected it to the difficulty modes (a mode chooses a pack set;
  extra packs from a separate stream leave base seeds alone). Understood (Q1
  in part, corrected; Q3 after a re-teach).

- **2026-10-26: F3: the fault-pack registry (Future Work 8 "Fault packs",
  steps 1-2). Built first at the developer's request; understood: no, to be
  taught in the pre-merge walkthrough.** The developer asked for servo/axis
  and optional hydraulic failures as fault-pack entries tagged by difficulty;
  the plan's own order is to move the existing four faults into a registry
  first, prove nothing changed, then add the new packs, so this PR is that
  first step only. New `capstone/faults.py`: `FaultPack` (agent side: the
  diagnosis name and the repair action it adds to the desk; evaluator side:
  correct action, `is_cause`, relevant evidence; `build`: adds the scenario,
  drawing from the generator stream exactly as before; `difficulty`),
  `PACKS` (order is part of the seed contract), `BY_KIND`, `agent_side()`
  (the only view agent-facing code may use), `FaultPlace`; `Relevant` and the
  bearing-profile constants moved here (re-exported under their old names).
  Rebuilt from it, names unchanged: `generator.FAULTS` (and its builders),
  `diagnosis.FaultKind` / `FAULT_KINDS`, `actions.ACTIONS`,
  `scoring.CORRECT_ACTION` / `RELEVANT_EVIDENCE` / `CAUSE_KINDS`,
  `baseline.FIX`. Proof of no change: a frozen copy of the old code and the
  new code gave identical fingerprints for 602 builds (seeds 0-59 x default
  and each forced fault x both bearing profiles, plus readings and events
  over 700 ticks on seeds 3 and 17), and identical rule-baseline output line
  by line (seeds 21-60: 153/160 causes; known-answer cases 9/9). Difficulty
  tags proposed by the coding agent, to confirm: bearing and false alarm easy,
  bad batch and wrong setting medium; nothing reads them yet. Tests: new
  `tests/test_fault_packs.py` (14, CI group Evaluation: one name per fault;
  every list built from the packs; the lists keep their old values; a correct
  action is one the desk knows and only causes need one; every pack has a
  difficulty and evidence; the agent side holds only a name and a repair; a
  static guard that `agent/`, `tools/` and `providers/` never read
  `.evaluator`, `PACKS` or `BY_KIND`; every pack builds its own fault; seeds
  0-9 pinned). Not done: keying the fault draw so a new pack leaves other
  seeds alone (next PR, with the servo pack); sensor lists stay where they are.

- **2026-10-26: PR #78 pre-merge walkthrough (F2).** Three questions.
  Q1 (an agent says load and power are two independent confirmations of
  bearing wear): first said power can be used to add noise (true only as a
  side point: a heavier job raises power more than wear does); taught: both
  meters read the same hidden load and the same friction term, so they are one
  fact seen twice and share the job-size confounder; independent evidence comes
  by another path (vibration, temperature, slower jobs, inspections, the
  technician's finding). On a smaller case the developer proposed watching
  power against load to spot wear; corrected with numbers: friction is in both
  readings, so power per load reading stays at 0.190 with a 50%-worn bearing,
  while a wrong setting does move it (speed is in power, not in the load
  reading). Correction of the coding agent's own earlier figure: 18.1 to 19.5
  kW per unit of load was against the hidden true load, which the agent cannot
  see. The developer added that power makes a wrong setting easier to catch
  (agreed; to watch in the scored runs). Q2 (a power meter reading 3 kW high
  versus a machine really drawing more): after one hint, right: the faulty
  meter reads about 3 kW when down and 5 kW when idle; a real extra draw exists
  only while cutting. Q3 (why the power sensor must not heat the machine):
  right: a sensor reads, never writes; added what would break (installing a
  meter would change temperatures and every saved seed, a meter dropout would
  cool the machine, sensor order would matter) and that heat belongs in
  `thermal.py`. Understood (Q1 in part, corrected; Q2 after one hint).

- **2026-10-26: F2: machine power in kW (Brandon's feedback, Future Work 8
  B). Built first at the developer's request; understood: no, to be taught
  in the pre-merge walkthrough.** `simulator/sensors.py` `PowerSensor`
  (sensor `power`, unit kW): down about 0; idle `idle_kw` 2.0; running idle
  plus `spindle_kw` 15.0 x load x speed ratio plus `friction_kw` 1.5 x wear
  squared; noise 0.2 kW; never below 0. Working assumptions for a mid-size
  CNC mill, not measured; Brandon to review. Decisions: standard on every
  machine of the line (unlike the bearing profile, it adds an observation
  without changing how any fault develops; its own stream
  `sensor.<machine>.power` leaves every other reading, alarm and seed
  unchanged) and offered to the agent (`MachineSensor` gains "power"; the
  `get_readings` and `get_sensor_trend` descriptions name it with its unit).
  Power and the load sensor read the same hidden load and wear, so they are
  correlated, not independent; power's own information is the speed. Checked
  on seed 3: idle 2.0 kW, running about 9.5-11 kW; kW per unit of load rose
  from 18.1 to 19.5 with a worn bearing and fell from 18.1 to 16.1 with a slow
  wrong setting. For the scored run: the agent's tool list now includes
  power, so a fresh run is not the same environment as `results-5.jsonl`
  (which also predates many other changes); compare single- and multi-agent
  runs made on the same `main`. Tests: new `tests/test_power_sensor.py` (12:
  down, idle, running, speed, friction; a heavier job outweighs a badly worn
  bearing; reading changes nothing; kW and never negative; adding the meter
  changes no other reading; every machine of the line has one; same seed same
  readings; the agent can ask for it and an unknown sensor is still refused),
  CI group Simulator. Updated for the fourth sensor: `test_build_line.py`
  (readings per tick), `test_factory_provider.py` (the refusal message and the
  offered sensor list). Not done: kWh, current draw in amps, servo and
  hydraulic contributors, power in `RELEVANT_EVIDENCE`.

- **2026-10-26 (C3c): the memory comparison made fair. Built ungated at the
  developer's request; understood after the PR #74 walkthrough (below).** A read of all
  the memory code found five ways `memory_comparison` could report the wrong
  numbers; all five are fixed:
  1. *Semantic mode answered by keyword unseen.* Only the start was checked:
     a search that failed mid-run (an embedding 429) fell back to keyword
     search in `MemoryRecall.recall_memories`, and `MemoryService.search`
     drops the `fell_back` flag. Now `MemoryRecall(fallback=False)` raises
     `SemanticRecallFailed` (no exception text chained) and `memory_for`
     builds every mode that way; `RecallingProvider` turns it into "Recall
     failed.", recorded as a `failed` search. Ordinary runs still fall back.
  2. *Outage runs counted against a mode.* `mode_line` now counts
     `model_unavailable` runs as `outage=` and leaves them out of every other
     total, as `scoring.summarize` does; `case_line` shows them as `outage`.
  3. *Memory modes charged for their searches.* `score.tool_calls` counts
     every call the loop sent, recall included. Each record now keeps
     `factory_calls` (`experiment.count_factory_calls`: decisions with a tool
     other than `recall_memories` / `search_manual`, loop-skipped repeats left
     out, as in `tool_calls`). The report shows both; older results show `n/a`.
  4. *Failed searches invisible.* New `failed=` beside `refused=` (mode line)
     and `failed=` per case.
  5. *Modes run one after another.* `compare_memory` now runs case 1 in every
     mode, then case 2, so a rate limit or provider change lands on all
     modes; `run_experiment(start=...)` keeps run keys numbered over the whole
     case list. A mode named twice is refused.
  Tests: `tests/test_memory_comparison.py` (6 new, 1 changed),
  `tests/test_memory_semantic.py` (1 new). Scripted only; nothing ran against
  a real model.
  **Left as notes, not fixed (developer's decision):**
  6. Keyword and semantic search read different fields: keyword ranks
     category, symptoms, action, machine and lesson (`recall.rank_memories`);
     semantic embeds category, symptoms, diagnosis and lesson
     (`semantic.memory_document`, whose docstring wrongly says keyword uses
     the same text). A keyword/semantic gap is not purely words vs meaning.
  7. Semantic search has no relevance cutoff: it always returns k memories,
     however unrelated, while keyword returns none without a shared word, so
     `recalled=` is not like for like.
  8. One run per case per mode (no repeats, no paired win/loss count); the
     results do not record the store's size, embedding model or policy
     version; nothing checks that memory used on `--held-out` was learned on
     tuning seeds (memories do not keep their seed).
  **PR #74 pre-merge walkthrough (C3c), 2026-10-26.** Three questions.
  Q1 (a semantic search fails mid-run): said the agent sees a failed
  retrieval (right) and that chat and embeddings share NVIDIA so both fail
  together (a good point, not raised before: true for a full outage, which
  ends the run as `model_unavailable`); corrected that the embedding call is
  not retried (only `FallbackClient` chat questions retry, then fall back to
  another provider), so one request can fail while the run goes on. Follow-up
  right: before the PR the search fell back to keyword unseen, so the
  semantic line partly measured keyword. The developer suggested stopping
  the investigation on a failed semantic search instead; discussed as a
  valid alternative (needs those runs counted apart like outages), not
  changed; the PR keeps the run going and shows `failed=`.
  Q2 (`tool_calls` vs `factory_calls` with three repeat searches): budget
  and records right (three asked, two refused, one counts toward the three
  searches); `tool_calls` not reached, then reasoned as a penalty; re-taught
  as mechanism (the loop's same-tick check skips before `call_tool` counts;
  `RecallingProvider`'s any-tick check refuses after), then right for a
  later-tick repeat. Q3 (semantic 5/6 with outage=4 vs none 7/10): right
  that outages are not wrong answers; corrected that the two modes were then
  scored on different cases, the gap is one or two cases, and outages may be
  caused by semantic mode's extra NVIDIA calls, which is why `outage=` stays
  visible. Follow-up: proposed rerunning the outage cases (valid); also
  taught comparing only the cases both modes answered. **Follow-up idea from
  the developer:** a `--cases` option on `run` to rerun chosen cases in
  every mode.

- **2026-10-26: PR #76 pre-merge walkthrough (F1).** Three questions.
  Q1 (why the quiet phase belongs in the scenario, not the vibration
  sensor): said every sensor would need wiring (correct: the temperature
  sensor reads wear too, so a vibration-only mask would make the evidence
  contradict itself) and that the sensor would be changing the truth;
  corrected: the sensor version hides the truth rather than changing it,
  health still falls at the old rate so the machine still fails in about a
  day, and the technician's finding and the evaluator read the real health.
  Q2 (the monitor's 4,000-tick wait with three-day faults): said the agent
  would not see the fault and the run would be inconclusive; corrected: the
  evidence is visible by tick 4,000 (health about 0.6) but nothing points to
  it, and the result would be scored as a missed bearing fault caused by the
  harness, not the agent. The developer asked about raising the wait: three
  problems (more chance a distractor triggers first, histories past the
  300-row cap, the wait must be per profile and recorded); asked whether
  models or memory limit it: the wait runs before the investigation's clock
  (`detect_anomaly` in `run_episode`), the prompt is capped, and memory was
  measured at 316 MB for 8 machines over 12,000 ticks (300,000 readings), fine
  one run at a time. Q3 (why the default-phases test demands exact
  equality): did not know; re-taught (determinism promise, thresholds that
  turn tiny differences into different episodes, a shifted random stream);
  on a smaller case said the alarm would trip a few ticks early (correct);
  added that the investigation then starts earlier on different evidence
  and saved results and labels can no longer be reproduced. Understood (Q1
  and Q2 corrected, Q3 after one re-teach).

- **2026-10-26: F1: an opt-in three-day bearing profile (Brandon's feedback,
  Future Work 8 A). Built first at the developer's request ("add then
  teach"); understood: no, to be taught after the build.** Measured first:
  on seeds 1-40 the existing curve goes from fault start to failure in 9-28
  hours of running (median onset-to-failure 725 running ticks), so a
  three-day ramp is longer than today's, not shorter. Built:
  `BearingDegradation` gains `onset_health` and `quiet_factor` (while health
  is above the onset, wear runs at that fraction of the rate; defaults 1.0
  and 1.0 are the original curve exactly). `build_scenario` gains
  `bearing_profile` (`BEARING_PROFILES`: "compressed", the default and
  unchanged, and "three_day": the same seeded rate draw times 0.17, onset at
  health 0.8, quiet phase at half rate). Result on seeds 1-40: quiet stretch
  median 2,349 running ticks, onset to failure median 4,294 (target 4,320,
  range 2,683-6,241), first alarm a median 5,007 ticks after the fault
  starts. Decisions to confirm in the teaching session: operating rather than
  calendar days (wear already accrues only while running), onset 0.8, quiet
  factor 0.5. Tests: `test_bearing_degradation.py` (nonsense phase settings
  refused; default phases change nothing; quiet rate before onset, full rate
  after; vibration near normal until onset, then climbs),
  `test_generator.py` (unknown profile refused; compressed is the default;
  the profile moves no stream; other faults unchanged; one seed's quiet
  stretch and ramp inside the 40-seed range, against the compressed curve).
  Not done: experiments cannot choose the profile, and the monitor's 4,000-tick
  wait ends before a typical three-day alarm; Brandon has not reviewed the
  curve. Also decided (developer, 2026-10-26): servo/axis and hydraulic faults
  will be built as fault-pack registry entries tagged by difficulty; the
  easy/medium/hard switch waits for the scored single-agent run.

- **2026-10-26: docs: multi-agent work on our own orchestration, no CrewAI
  (developer's decision).** Documentation only; no code or dependencies
  changed, no understanding status changed. Checked on PyPI the same day:
  CrewAI 1.15.30 requires the `openai` SDK (forbidden by AGENTS.md section 9)
  and `pydantic<2.13` (the project pins 2.13.4); LiteLLM also requires
  `openai` (already turned down on 2026-10-15). `docs/MVP_SCOPE.md`: section
  3 and Future Work 3 now say roles are new stages on the existing Pydantic
  Graph stage graph, each role's model comes from the job table through
  `providers/chat.py` (`clients_for_jobs`, `FallbackClient`), handoffs are
  project contracts asked through `ModelPolicy._ask`, and every role spends
  the investigation's one budget; a "Decision" section maps each
  multi-agent need to existing code. The CrewAI MCP client, CrewAI/LiteLLM
  provider integration, `CrewAIProvider`/`ModelRegistry`, LiteLLM rerank and
  LiteLLM Router sections were rewritten for the existing client (the old
  text also cited `providers/llm.py`, which no longer exists). Build one role
  at a time, measured against the single agent. `docs/FUTURE_WORK_REEVALUATION.md`:
  row 25b rejected, row 26 replaced, the baseline line now says the graph is
  implemented.

- **2026-10-24 plan, still open after the scored run: test a 60 s request
  limit, then collect lessons.** The
  developer rotated the NVIDIA key on 2026-10-24; with it, Nemotron answered
  small probes in about 1 s, but the Cloudflare fallback answered HTTP 429.
  A run with Nemotron alone (`FALLBACK_MODEL=""`, bearing fault, seeds 21-25,
  45 s / 90 s, store `.chroma/near-duplicate/run-f`) finished 3 episodes, all
  `model unavailable` after HTTP 500s and timeouts (log kept as
  `run-45s.log`): with no fallback, one question that fails after its retries
  ends the episode. Across the day's runs NVIDIA gave 162 HTTP 500s and 188
  timeouts; the slowest successful answers were 41.5 and 42.5 s, close to
  45 s, while a 120 s limit the day before still timed out at the full 120 s.
  The developer asked for a 60 s request limit (120 s per question, so a
  retry fits with one model); that run (seeds 24-26) was stopped after
  2 minutes with nothing finished. Steps next time: probe both models first;
  run one run at a time with `MODEL_REQUEST_SECONDS=60
  MODEL_QUESTION_SECONDS=120` on store `run-f`, seeds 24 onward; compare its
  HTTP 500 and timeout counts with `run-45s.log`; stop early if episodes keep
  ending `model unavailable`. Lessons so far: 0; the threshold stays 0.909.

- **2026-10-24 (afternoon): a single lesson run stopped, 0 lessons (results
  only; nothing built).** One run at a time, as decided in the morning: seeds
  11-20, bearing and wrong setting, a fresh throwaway store
  (`.chroma/near-duplicate/run-e`), the 45 s / 90 s limits for this run only,
  started 13:55 on the PR #69 branch (so with the episodic-v3 gate). Stopped
  at the developer's request at 14:11 after 5 episodes, every one ending
  `model unavailable` (1 to 15 questions each, 61 to 385 s): NVIDIA's chat
  model timed out or answered HTTP 500, and the Cloudflare fallback answered
  HTTP 429 to each of its retries. NVIDIA had answered a probe in 1.5 s that
  morning, so its chat service is unreliable from one hour to the next.
  Lessons stored: 0; the near-duplicate threshold stays the provisional
  0.909. Next attempt: probe the chat model first, and stop early if the
  first episodes end `model unavailable`.

- **2026-10-24: PR #69 pre-merge walkthrough (G1).** Q1 (why `proposed_action
  is not None` is a safe test for a carried-out action): said no proposal
  means nothing to ask; corrected: the no-action case does reach `verify`,
  and the test is safe only together with "verified", because a rejected or
  not-carried-out proposal routes to `finish` and is never checked. Q2 (why
  bump the policy version): said it labels the check as no-action; re-taught:
  `policy_version` on each stored memory records which rules admitted it, so
  later pruning can target v2 memories; restated correctly (check the older
  versions, the newer ones could not get in). Q3 (a true false alarm under
  v3): said it is thrown out, that patience reveals a false alarm, and that
  the "false alarm" label would be needed; corrected: that label is ground
  truth and must never reach memory; safe evidence must be observable (a
  longer watch, other sensors and inspections agreeing, or a separate weaker
  outcome type). Understood in part, corrected. The developer asked whether
  existing no-action lessons need pruning: the real store (Neon) holds 0
  memories, so no.

- **2026-10-24: G1: no lesson from a "resolved" watch with no action.**
  From finding 2 of the same day: the gate stored "a transient spike, no
  change needed" about a real worn bearing, because a verified outcome with no
  intervention passed (`test_verified_no_action_incident_can_be_promoted`).
  Taught first (gate): the developer explained that a repair links a change
  to a result and doing nothing does not (correct); first said the
  `learn_from` change was a second protective layer, corrected (the gate is
  the authority and runs last; `learn_from` only avoids a model call that can
  never reach memory, A6c's rule); restated the cost role correctly. Built:
  `memory/policy.py`: in the resolved branch, `proposed_action is None` adds
  `no_action_taken`; `version` "episodic-v2" -> "episodic-v3". Checked: the
  verify stage runs only after a carried-out action or a `no_action`
  conclusion (a rejected proposal ends without a check), so "verified with no
  proposed action" is exactly the do-nothing case. `learning.py`: a lesson is
  asked for only when the check was verified and an action was proposed.
  Cost: a real false alarm's "no repair needed" lesson is not kept either;
  keeping it safely would need more evidence (a longer watch or its own
  outcome), not started. Tests: `test_memory_policy.py` (the old "can be
  promoted" test is now `test_a_verified_no_action_watch_is_refused`; a
  carried-out fix still passes; version v3), `test_learning.py` (a real
  no-action episode through the simulator, check verified: audited, model
  never asked, nothing stored). Docs: `docs/EPISODIC_MEMORY.md` criteria and
  table.

- **2026-10-24: four lesson-collecting runs, 1 lesson; two memory-gate
  findings (results only; nothing built).** NVIDIA's chat model answered a
  probe in 1.5 s, so the NEXT SESSION step 3 ran on `main`, as four parallel
  runs (bearing and wrong setting, seeds 1-5 and 6-10), each with its own
  throwaway SQLite store under `.chroma/near-duplicate/run-a` to `run-d`, and
  with MODEL_REQUEST_SECONDS=45 / MODEL_QUESTION_SECONDS=90 set for these runs
  only (the developer's `.env` sets 120 / 240; not edited). All 20 episodes
  finished in about 40 minutes: 14 ended `model unavailable`, 3 on the time
  limit; failed requests were mostly timeouts, HTTP 500 and about 56 HTTP 429.
  The 429s came from running four at once: the developer decided live runs go
  **one at a time**. Only **1 lesson** was stored, too few for pairs, so the
  near-duplicate threshold stays the provisional 0.909. Separately, on the
  wrong-setting runs seeds 1 and 2 blamed a worn bearing on CNC-06.
  - **Finding 1, a correct fix lost.** Run B seed 6 (bearing on CNC-02): the
    agent asked for `replace_bearing CNC-02`, it was carried out and the fault
    was resolved in reality (`resolved=True`), but the agent's own check came
    back `inconclusive` (checked at tick 1025), so the shared record is
    `unverified`, no lesson was asked for and nothing reached the gate. By
    design; to look at later: whether the check runs too soon after the work,
    or the judge is too cautious.
  - **Finding 2, a wrong lesson stored.** Run A seed 2: the real fault was a
    worn bearing on CNC-04, but the agent concluded a one-off vibration spike
    that had cleared, proposed no action, and its check judged it `resolved`
    because the alarm had dropped below its threshold. The gate accepted a
    verified outcome with no intervention (`verified_reusable_lesson`) and
    stored: "For a single-tick vibration alarm that immediately falls back
    below threshold ... a transient event that cleared on its own, so no change
    was needed." A future agent recalling it would learn to dismiss early
    bearing alarms. Gap: with no action, "resolved" only means the symptom
    paused; the lesson rests on the agent's belief alone. It exists only in
    the throwaway store (`run-a`); Neon is untouched. A change to the gate
    (for example refusing or marking no-action "resolved" lessons) changes
    what the agent learns, so it goes through the teaching gate first; not
    started.

- **2026-10-23: near-duplicate lesson run started and stopped (results
  only; nothing built).** Followed the NEXT SESSION steps below on `main`.
  Step 1: re-measuring the drafted pairs gave 0.909 again, so NVIDIA's
  embedding service was back. Step 2: a throwaway SQLite store and Chroma
  index under `.chroma/near-duplicate/` (ignored by git; Neon and `.env`
  untouched), created with `alembic upgrade head`. Step 3: `experiment run
  --name lessons-1 --seeds 1-10 --faults bearing_degradation,wrong_setting
  --memory --audit ...` in the background; stopped at the developer's request
  (out of time) after **1 of 20 episodes, 0 lessons stored**, so the
  threshold stays the provisional 0.909. The one episode (seed 1, bearing on
  CNC-04, 923 s): NVIDIA's chat model (nemotron 120b) timed out on every
  question, most at the full 120 s, though its embeddings answered; Cloudflare
  Llama 3.3 70B, the fallback, answered nearly every question in 1-20 s (one
  `interpret` went unanswered by both). It concluded high vibration on CNC-04
  but recommended "escalate", not a bearing replacement, and ended on the
  time limit with no check, so no lesson could be written. Findings: (1)
  NVIDIA chat may still be degraded, so check it before rerunning, or the run
  measures the fallback; (2) requests waited 120 s, above the code's 45 s
  default, so the developer's local `.env` appears to set
  MODEL_REQUEST_SECONDS (and the question limit) higher, and each question
  spent about 2 minutes on NVIDIA before the fallback was asked. The store,
  audit log (1 record), results and `run.log` remain in
  `.chroma/near-duplicate/` for the rerun; the store can be reused as is.

- **2026-10-23 — Draft diagnosis labels for the 16 live conclusions.** At
  the developer's request, the coding assistant drafted labels
  (`docs/benchmarks/2026-10-23-draft-diagnosis-labels.jsonl`,
  `labelled_by: "claude-draft"`). They label what each conclusion says, not
  whether it is right. They are not hand labels: a model wrote them after
  seeing Jev's proposals. Compared offline with the saved Jev proposals
  (no new calls): 13 of 16 agree, 13 of 15 among unreviewed. The 3
  disagreements are the 3 drafts marked debatable; two were confident Jev
  answers (0.06, 0.11), so the gap is the false-alarm wording, not the
  thresholds (`docs/benchmarks/2026-10-23-jev-auto-labels.md`). Not done:
  the developer's review of the drafts. Docs and data only; no code changed.

- **2026-10-23 — T1: TypeSafe's Jev proposes diagnosis labels.** At the
  developer's request (they added `TYPESAFE_API_KEY` to `.env`), built
  the "evaluator model for diagnosis labels" build candidate of `docs/MVP_SCOPE.md` with TypeSafe's
  System One model Jev, which answers with typed probabilities rather than
  text. Built first, to be taught in the pre-merge walkthrough; not merged.
  - `providers/typesafe.py`: one request holds the state and every
    question; a noul answers yes/no with a probability, a choice picks one
    named option. Malformed or incomplete replies are refused (ValueError);
    service failures are `ModelError`, as for chat models.
  - `evaluation/auto_label.py`: for each run's conclusion, one yes/no
    question per fault kind ("does it settle on this cause?") and, for each
    kind, a choice among the machine or batch ids that code found in the
    text, so the model selects an id and never writes one. Yes at >= 0.7, no
    at <= 0.3, anything between (or a target chosen with confidence below
    0.5) marks the proposal for review. These are TypeSafe's suggested
    starting points, not measured here. Proposals go to their own file;
    `agreement` compares them with hand labels. The truth is never read.
  - Live check: 49 runs, 16 with a real conclusion; my reading agrees with
    most proposals, but these are not hand labels, so no accuracy is
    claimed (`docs/benchmarks/2026-10-23-jev-auto-labels.md`).
  - Not done: the developer's hand labels, needed before proposals can be
    trusted in experiments; `experiment.py` does not read proposals yet.
  - Pre-merge walkthrough (AGENTS.md §11 step 6), three questions:
    1. Why ask every "which machine?" question in one request? Right: one
       round trip instead of two. Corrected: the gain comes from parallel
       answering, not Jev's speed; our code (not Jev) would read the first
       answers; missed the cost, now taught: billed input tokens for unused
       questions, and code must ignore them (the `continue` in `propose`).
    2. What goes wrong if Jev saw the true fault? Partly right ("it would
       have the answer"). Corrected: the harm is bias, not confidence;
       labels would drift toward the truth and credit the agent for
       diagnoses it never made (structured-1/1/seed-9), collapsing belief
       into reality (§4.1).
    3. Why two thresholds and a review band, not one line at 0.5? Right:
       middle values are too uncertain to accept unread. Added: at one line,
       0.51 vs 0.49 silently decides the score; an unread wrong label costs
       more than a review.
  - The developer noted the thresholds must be measured on hand-labelled
    runs, and asked that Jev stay optional given a $5-a-month budget (it
    already runs only through its own command; spending guards proposed).
    Merged at the developer's request after the walkthrough, without the
    spending guards (the developer's choice).

- **2026-10-23: PR #59 pre-merge walkthrough (L7).** Three questions.
  Q1 (why the thread hands every exception to the caller): said a lost 503
  would surface as a timeout after the full limit; correct; filled in the
  mechanism (an escaping exception ends the thread and is printed, nothing
  reaches the queue) and the costs (the share burned, a 401 retried as a
  transient timeout, wrong `outage_reasons`). Q2 (why keep urllib's
  per-read timeout inside the thread): did not know; re-taught with the code
  (the caller's deadline cannot end the thread; only the per-read timeout
  can, else a silent server leaves it stuck until exit); restated correctly.
  The developer then asked why the thread waits 45 s after the last byte:
  the per-read timer also covers the first wait while a non-streamed answer
  is generated (up to 42.2 s for a successful one), so it cannot be shorter
  than the request limit. The developer chose to raise the limits to 50 s /
  100 s (PR #64), then dropped the change on 2026-10-23 (PR closed, not
  merged; `.env.example` could not be updated by the coding agent): the
  limits stay 45 s / 90 s. Q3 (what a trickle did to the fallback before):
  answered "now" correctly, unsure about "before"; corrected: the call did
  not return until 146 s, the question's time was gone, Cohere was "not
  asked, no time left"; the trickle undid L1's equal-share fix, which this PR
  makes enforceable. Understood (Q3 in part, corrected).

- **2026-10-22: L7: the request limit covers the whole request.** From the
  L3 follow-up: urllib's `timeout` limits each wait on the socket and every
  arriving piece of data restarts it, so one xKiro request ran 146 s against
  the 45 s limit. Taught first (gate): the developer explained the chained
  per-read waits correctly and the Requesty one-slot limit; did not know why
  an abandoned request is acceptable; re-taught (the run moves on, the
  daemon thread ends by itself, nothing reads its result, no client can
  cancel the provider's work); restated it, with one correction (the
  provider's late reply is discarded, not saved). The developer proposed a
  240 s total; the saved benchmark calls show no successful request over 45 s
  for any model in use (Nemotron 120b: 113 answered, longest 42.2 s; the
  146 s xKiro request was itself a failure), so the measured 45 s stays.
  Built: `providers/chat.py` `run_with_deadline(work, seconds)` (runs the
  work in a daemon thread, waits at most `seconds`, then TimeoutError; the
  work's own exception reaches the caller unchanged) and `urllib_transport`
  now sends through it, so `MODEL_REQUEST_SECONDS` is a true limit. The
  embedding client uses the same transport, so embedding calls get it too.
  `post_json` still maps TimeoutError to "the model service timed out"
  (transient), so retries and the fallback work as before. Tests: new
  `tests/test_request_deadline.py` (6, a local 127.0.0.1 server that
  trickles its reply), CI group "Tools and provider". Checked against the
  old code with the same server: 0.5 s limit, old transport returned after
  2.5 s, new one stopped at 0.5 s. Not run live.

- **2026-10-22: re-checks of the four items understood in part (L2, L4,
  FD, C3a).** No code changed. A new question each.
  - L2: asked whether a model that concluded 4 runs in 300 s without ever
    proposing a repair should lower the 1,200 s budget. First said run more
    benchmarks and lower it if none ran longer; corrected: more such runs
    stay short because they skip the proposal, the work and the check, so
    first check the runs did the whole job. Asked again (one 700 s resolved
    bearing run, three 250 s runs): said the 700 s run is the complete one
    with the repair and the check. Correct; added that doing nothing is
    right for the batch and the false alarm. Understood.
  - L4: asked what happens when Nemotron's `decide` names a tool not offered.
    Said no fallback, an invalid reply counted against Nemotron, and retry on
    NVIDIA. Correct apart from the retry: the client stops at once; the loop
    records `invalid_decision`, counts an unproductive step and asks
    Nemotron again next turn, stopping after three in a row. Understood.
  - FD: asked what 10 of 30 questions recovering from HTTP 500 shows when the
    run says 30/30 answered. Said the provider failed for a moment and a
    retry fixed it; added the provider-health trend and why MODEL_RETRIES is
    3. Follow-up at 25 of 30: said runs get longer and NVIDIA is the only
    long-context main model; added more fallback answers, possible
    `model unavailable` endings, `outage_reasons` as the evidence that the
    provider is at fault, and what can still be done. Understood.
  - C3a: asked whether to trust a comparison run on the same seeds that
    filled the store. Said no: those are tuning seeds, and the comparison
    must move to other seeds. Correct (`HELD_OUT_SEEDS`, `--held-out`).
    Understood.

- **2026-10-22: the rest of the ungated work taught after the build (E6, FD,
  C4, M1 gap, L3 and L6, C2).** No code changed. One explanation and one
  question each. With this, no row in the table is still "built ungated,
  developer to review".
  - E6 (compound challenge): asked to score KA-09 when only the bearing on
    CNC-07 is named and replaced. Said the replacement is a wrong cause and
    was unsure the bearing was worn; corrected: the bearing is a real cause,
    so causes_found 1 of 2, wrong_causes 0, causes_resolved 1, not
    fully_right because the speed was never named (`fully_right` scores
    naming, not fixing). Follow-up: what makes `fully_right` true with only
    one cause resolved: "name both, fix one". Correct. Understood.
  - FD (failure diagnostics): asked why recovered failures are kept. Said the
    run can continue and that the main model's answers would be lost;
    corrected: the fallback continues either way, and the point is hidden
    unreliability (whose reasoning is measured, time burned, a warning before
    outages). Follow-up: said make NVIDIA the fallback if Cohere does half the
    work; corrected: L2 showed Cohere never asks for fixes, so first find why
    NVIDIA times out, tune the per-request wait, or re-benchmark. Understood
    in part, corrected.
  - C4 (tree-of-thought): asked why pruning is code, not the model. Said code
    is deterministic and the model could hallucinate. Correct; added the
    evidence-citation check and the recorded reason for each drop.
    Understood.
  - M1 gap (walkthrough Q3): taught how `run_episode` wraps providers
    (factory, hazards, recall, manual) and that each layer answers its own
    tool or passes the call inward. Asked whether a hazard on `search_manual`
    could fire: said never, because the manual is outermost. Correct;
    corrected the side remark about repeats and gave the change (wrap the
    hazards layer last). The developer noted the agent can search again
    after a failure; confirmed in `providers/manual.py`: a failed search is
    not counted or treated as a repeat. Understood.
  - L3 and L6 (router providers): asked why Requesty's retry gets HTTP 429
    after our client gave up. Said Requesty is still working on the first
    request. Correct (giving up closes only our side). Understood.
  - C2 (Module 2 gap note): asked what in working memory never reaches
    episodic memory. Said evidence IDs, because each investigation numbers
    its own; correct reason; refined: they are stored for lineage but left
    out of `RecalledMemory`, while decision records, hypotheses and raw
    evidence go only to the audit trail. Understood.

- **2026-10-22: memory group taught after the build (A6c gap, C3b, C3a,
  D1).** No code changed. One explanation and one question each.
  - A6c (gap from 2026-10-14): asked to trace `learn_from` for an approved
    repair whose check was inconclusive. Traced it correctly (refuse an
    unfinished run, audit first, no model asked, no candidate). Corrected:
    `LearningOutcome` is still returned, with `lesson_requested=False` and
    `decision=None`, and `build_candidate` makes a candidate, not a memory.
    Understood.
  - C3b (bounded memory search): asked why a repeated memory search is
    refused whatever the tick while a factory call is not. Said memory is
    frozen, so the same search returns the same evidence, while the factory
    moves on. Correct; added that it is frozen because lessons are added only
    after the run (`learn_from`) and that SQL is the authoritative store.
    Understood. Also answered the developer's question on fault timing: the
    seed draws the start tick between 200 and 600 (`build_scenario`); the
    bad batch is tied to batch 2 or 3; the start is kept in hidden ground
    truth.
  - C3a (memory comparison): asked what goes wrong if the comparison learned
    while running none, keyword, semantic in order. Said `none` would store
    empty memories; corrected: `none` stores ordinary lessons, and later
    searching modes recall answers to the very cases they are tested on, so
    the result measures order and store growth, not the mode. Restated "the
    answers would be handed to it". Follow-up on the reversed order: said the
    first mode gains; corrected: the first is disadvantaged and only
    `keyword` gains. Then restated it correctly. Understood in part,
    corrected.
  - D1 (threshold tool, gaps from the walkthrough): asked what a new
    "different" pair at 0.93 does. Said the threshold rises and catches fewer
    repeats. Correct (0.931; 13 of 23 on current data). Understood.

- **2026-10-22: live-run group taught after the build (L1, L2, L2b, L4,
  L5).** No code changed. One explanation and one question each.
  - L1 (live runs finish): asked why a run cut off by the stage deadline
    should be "timeout", not "model unavailable". Said the label decides the
    fix: check the provider for an outage, add time for timeouts. Correct;
    added that the old label also made reliability numbers blame NVIDIA.
    Understood.
  - L2 (benchmark and limits): asked why lightning 30b's suggested 43 s
    budget is wrong. Said it should come from the longest episode;
    corrected: the formula is 2 x questions x median, and 5.8 questions is
    low because the runs failed early, so it measures time to fail. Follow-up
    on command-a's 142 s: said use more runs and the longest time;
    corrected: the median is doubled on purpose, the per-question limits cap
    slow answers, and command-a never asked for a fix, so its runs skipped
    the proposal, the work and the check (and 142 s is below the 400 s
    follow-up reserve). Afterwards restated "budget from runs that did the
    complete job". Understood in part, corrected.
  - L2b (time-left prompts): asked why "few calls remain" is shown only near
    the end. Said a constant warning would push a rushed decision on a
    warning not yet true. Correct. Understood.
  - L4 (invalid-reply reasons): asked why an outage moves to the fallback
    but an invalid reply does not. Said an outage is a connection issue
    (correct) and that switching would lose the reply; corrected: the reply
    content is never kept, and the loss is knowing which model got it wrong
    (results credited to the wrong model, benchmark counts hiding failures).
    Understood in part, corrected.
  - L5 (NVIDIA structured output): asked why replies are still validated.
    Said other providers have no schema and the schema cannot stop a wrong
    tool or a blank field. Mostly correct; corrected that blank fields can be
    described in a schema, and gave the cross-field rule in `NextStep` and a
    service failing to enforce as further reasons. Understood.

- **NEXT SESSION (run 2026-10-23 and 2026-10-24 without enough lessons;
  see the notes above; rerun one run at a time): re-measure the near-duplicate
  threshold on real lessons.** Postponed from 2026-10-22 because NVIDIA was
  down. The developer approved Claude's draft labels on 2026-10-22, so the
  provisional 0.909 stands for the drafted pairs. Steps, all in one
  PowerShell terminal:
  1. Check NVIDIA is back: rerun `uv run python -m
     capstone.memory.duplicate_threshold --pairs
     docs/benchmarks/near-duplicate-pairs.jsonl`; it should report 0.909
     again.
  2. Point this terminal only at a throwaway store (both paths are under the
     ignored `.chroma/`, and the `.env` and Neon stay untouched):
     `$env:DATABASE_URL = "sqlite:///.chroma/near-duplicate/lessons.sqlite"`
     and `$env:CHROMA_PATH = ".chroma/near-duplicate/index"`. Create the
     folder, then the table: `uv run python -m alembic upgrade head`.
  3. Collect lessons, in the background (episodes took 4 to 30 minutes
     each): `uv run python -m capstone.experiment run --name lessons-1
     --seeds 1-10 --faults bearing_degradation,wrong_setting --memory
     --audit .chroma/near-duplicate/audit.jsonl --out
     .chroma/near-duplicate/results.jsonl`. Only these two faults have a
     repair, so only they can produce lessons.
  4. Build pairs from the stored lessons that share category, outcome and
     machine, with more held-out "same" pairs than the draft had; the
     developer labels them.
  5. Rerun step 1's command on the new pairs file; update
     `docs/benchmarks/`, the plan in `docs/MVP_SCOPE.md` and this file, in a
     PR. Close the terminal afterwards so later runs use the normal store.

- **2026-10-22 — M1: the machine manual and `search_manual`.** The
  developer drafted a simulated maintenance manual and asked for it to be
  retrieved through RAG, like a real plant's machine guide. Design and
  decisions in `docs/MACHINE_MANUAL_RAG.md`; the developer chose option B (no
  station speeds or job times in the manual, so a wrong setting is found from
  its effects; §2.7 rewritten as that method) and approved storing it as
  Markdown, no system-prompt line, a leak check, and measuring on tuning seeds
  first. Every number left in the manual was checked against the code (alarm
  4.5 mm/s; 45, 135 and 10-tick actions). Module by module:
  - `manual/sim-cnc-001.md` (new): the manual, 15 numbered sections.
  - `manual/sections.py` (new): `ManualSection` (number, title, text,
    revision, `citation`), `parse_manual` (only "## §" headings),
    `check_no_leaks` (refuses fault names, seeds, case IDs, "ground truth"),
    `load_manual`.
  - `manual/index.py` (new): `KeywordManualSearch` (shared words, title words
    count double), `ChromaManualIndex` (its own collection; returns only
    sections the manual still has), `open_manual_index`, and the build
    command `python -m capstone.manual.index --rebuild`.
  - `memory/semantic.py`: `open_collection`, the collection-opening part of
    `open_chroma_index`, now shared by memory and the manual.
  - `providers/manual.py` (new): `ManualProvider` and `MANUAL_SPEC`
    (`search_manual(text, limit)`, at most 3 searches, repeats refused,
    errors never shown), mirroring `providers/recall.py`.
  - `contracts/provenance.py` `MANUAL_SOURCE` and origin "manual";
    `agent/loop.py` `ORIGINS`; `agent/model_policy.py` `ORIGIN_LABELS` (the
    "FROM THE MANUAL" mark); `memory/policy.py` `rests_on_manual`.
  - `episode.py` `run_episode(manual=)`; `experiment.py` `run --manual
    [semantic|keyword]`, `open_manual`, `ExperimentRecord.manual_searches`,
    `format_manual` and a `manual=` run-line part; `evaluation/manual.py`
    `ManualSearchRecord`, `build_manual_records`; `settings.py`
    `MANUAL_COLLECTION`; `.env.example`.
  Tests: `tests/test_manual.py` (27: the sections, option B holds, leaks
  refused, retrieval finds each symptom's section in the top three, the
  Chroma index, the tool's answers, refusals and budget, the evidence label,
  no verifying a fix from the manual, the gate) and four in
  `test_experiment.py`. Not run live yet.
  Pre-merge walkthrough (AGENTS.md section 11 step 6), 2026-10-22. Q1 (what
  stops a manual section from verifying a fix): **right**: only "observable"
  evidence counts in `investigation.py` `verify` / `later()`, the loop sets
  the origin from the provider's source, and the gate's `rests_on_manual`
  fires only when every citation is the manual. Q2 (edited manual, no
  rebuild): **partly**: the developer said the agent gets the old text; in
  fact `ChromaManualIndex.search` returns sections from the current file, and
  only the ranking uses the old vectors until `--rebuild`; corrected, and the
  developer restated it correctly. Q3 (can the manual's `get_time` hit a
  hazard): **not known**; after reading `standard_hazards`,
  `UnreliableProvider.call` and `ManualProvider.call`, corrected: no hazard
  is scheduled on `get_time`, the search's data and success never depend on
  the clock, and the only coupling is that its clock calls add to the
  hazards' per-tool call count. Fixed at the developer's request during the
  walkthrough: `verify`'s comments now name the manual.

- **2026-10-22: near-duplicate threshold measured (provisional). Built
  ungated, developer to review (understood: no).** The memory store held no
  lessons, so at the developer's request Claude drafted 60 lesson pairs in the
  real formats (`docs/benchmarks/near-duplicate-pairs.jsonl`, readable `.md`).
  The developer said to go ahead without labelling, so the labels are
  Claude's (23 same, 28 different, 9 unsure; `labelled_by` marks them). New
  `capstone/memory/duplicate_threshold.py`: `pair_text` (the text a memory is
  embedded as), `cosine`, `choose_threshold` (smallest three-decimal value
  above every "different" training pair), `evaluate` (repeats caught,
  different lessons refused), `measure` (embed as passages, hold out every
  5th pair) and a CLI. Measurement only; nothing in the memory service calls
  it. Result with live Nemotron embeddings: threshold 0.909; training 18/21
  repeats caught, 0/19 different refused; held out 1/2 and 0/9. Margin almost
  zero (0.9089 vs 0.9091). The whole memory text beat the lesson alone (19 vs
  10 of 23 caught). Write-up:
  `docs/benchmarks/2026-10-22-near-duplicate-threshold.md`. Tests: new
  `tests/test_duplicate_threshold.py` (8), in CI group "Memory". NEXT: the
  developer reviews the labels; re-measure on real lessons.
  Pre-merge walkthrough (PR #53), three questions. Q1 (relabel P57 "same"):
  said the threshold goes up and catches more; corrected: it falls to 0.898
  (next-highest "different", P21) and catches 21 of 24; afterwards restated
  "above 0.898 is thrown out" correctly. Q2 (why P18 scores 0.910 whole but
  1.000 lesson-only): said the outcome or the ending differs; corrected: the
  outcome is the same by the filter, only the diagnosis differs, and whole
  memories were chosen because they caught 19 vs 10 of 23. Follow-up: said
  only one P18 memory is stored without knowing why; taught: the exact
  fingerprint (category + lesson, unique in SQL) refuses it first. Q3 (model
  changed to local): said re-embed and a new threshold, expecting similar
  results; corrected: scores from different models are not comparable, so
  re-measure; meanwhile the index refuses to open (`IndexModelMismatch`),
  recall falls back to keyword and the planned check would skip to the exact
  check. Understanding: partial, corrected in each case.

- **2026-10-22: plan recorded: near-duplicate memory check (docs only).**
  `docs/MVP_SCOPE.md` Future Work 1 gains "Near-duplicate memory check": in
  `MemoryService.promote`, after the policy accepts and before the SQL
  insert, refuse a memory whose embedding is at or above a measured
  similarity threshold to a stored one with the same category, outcome and
  machine (new reason `similar_lesson`; fall back to the exact check if
  Chroma is unavailable). It also records the machine filter's trade-off,
  that an agent-facing machine filter on `recall_memories` is a separate
  gated change, and the plan for measuring the threshold on developer-labelled
  pairs. Teaching: the developer answered the pre-implementation questions.
  Asked what to do with an `unresolved` lesson whose nearest memory is
  `resolved` at 0.97, they said it goes through because the outcome differs,
  and added that the threshold still applies within the same outcome
  (correct: the filter picks the nearest memory within that group). Asked what
  an agent seeing both "worked" and "failed" does differently, they said it
  looks for more evidence instead of repeating the repair. Concept
  understood; not implemented. Nothing built.

- **2026-10-22: docs-only: memory retention and promotion policy.** At the
  reviewer's request, `docs/EPISODIC_MEMORY.md` gains "Memory retention and
  promotion policy": the audit trail versus episodic memory, a table of what
  each artifact is stored as and whether the agent can retrieve it, the
  `episodic-v2` promotion criteria, how contradicted and abandoned
  hypotheses are (and are not) recorded, why a verified fix does not prove
  the root cause, and that conflicting lessons are not yet handled. Written
  from the code (`memory/policy.py`, `memory/contracts.py`,
  `memory/repository.py`, `agent/completion.py`, `learning.py`,
  `episode.py`). No runtime files or tests changed, and no gate was advanced.

- **2026-10-22 — plan recorded: fault packs (documentation only).** At the
  developer's request, `docs/MVP_SCOPE.md` Future Work 8 gains "Fault packs:
  one registry entry per sensor and its fault": describe each sensor and its
  paired fault once, with agent-visible and evaluator-only data kept apart,
  and build the scattered name lists from it; packs fixed in code and chosen
  per experiment, never added or removed at runtime, with keyed seed draws so
  existing seeds do not shift; done just before the fifth fault, first as a
  no-behaviour-change move of the four faults, then the new sensor and fault
  as the first new pack. Nothing built.

- **2026-10-22: docs-only: pre-merge technical walkthrough added to the
  PR rule.** `AGENTS.md` §11 gains a new step 6 (developer's rule): for a
  PR that implements a feature, after CI is green and before merging, the
  coding agent walks the developer through the actual changed files
  (architecture, then implementation; one real execution path with file
  paths and function names; new concepts; trade-offs, failure modes and
  assumptions), then asks three technical questions one at a time without
  revealing answers until attempted, corrects any misunderstanding with
  pointers to the source, makes no code changes unless asked, and merges
  only after that. Docs-only, CI-only and config-only PRs skip it. The old
  steps 6-8 are now 7-9. No runtime files or tests changed, and no gate
  was advanced.

- **2026-10-21 — the three escalated cases with structured output (results
  only; nothing built).** After PRs #43-#45 (refusal reasons, 16,384 tokens,
  NVIDIA structured output), the developer's main checkout reran seed 6
  bearing, seed 7 batch and seed 9 setting (`results-8.jsonl`, 120 s / 240 s
  waits, Gemini 3.6 Flash as fallback, `--timeout-seconds 2400`). Invalid
  replies fell from 12 (three cases, `results-7`) to 1 in 108 questions, and
  that one is `NextStep`'s stop-step rule, which a schema cannot express.
  NVIDIA wrote every conclusion. Outcomes: bearing, 28/28 answered, "sudden
  spikes", no action (wrong; the previous run fixed it); batch, 39/39,
  blamed "job parity", escalated (wrong); setting, 39/41, right machine
  (CNC-05) but "a failing bearing", escalated, research time ran out (1,634
  s). Availability and format are solved; what is left is the reasoning
  itself, which also varies between runs of the same case. Next, the
  developer's call: domain knowledge for the agent (a short note on fault
  patterns in the prompt, or memory), and several runs per case before
  drawing conclusions.

- **2026-10-21 — L6: LLM7 and Kilo Code added as providers; Z.ai checked
  and dropped. Built ungated, developer to review (understood: no).** The
  developer added the keys for support agents or a fallback. `providers/chat.py`
  gains `llm7` (`https://api.llm7.io/v1`) and `kilo`
  (`https://api.kilo.ai/api/gateway`); `settings.py` gains `LLM7_API_KEY` and
  `KILO_CODE_API_KEY`; `.env.example` lists them;
  AGENTS.md section 9 lists them (never Anthropic or OpenAI models through any
  router). Results, `docs/benchmarks/2026-10-21-llm7-kilo.md`: LLM7 is for a
  support agent only (100,000 tokens a day, the developer's decision); Nemotron
  Nano there answered large prompts but often in the wrong shape, and LLM7
  refuses structured output. Kilo's MiniMax M3.1 Flash answered all seven
  question types on short prompts but ran out of tokens on large ones: a
  support agent, not the fallback. Z.ai was added, tried and removed again at
  the developer's decision: without a balance only GLM Flash 4.7/4.5 answer,
  too slow and too rate-limited to finish an episode. The
  developer's `.env` writes the LLM7 key as `LLM7_API_key`; Settings ignores
  case, so it is read, but `LLM7_API_KEY` matches the project's names. Tests:
  the provider table, each provider's address and key.

- **2026-10-21 — L5: structured output for NVIDIA. Built ungated, developer
  to review (understood: no).** With the reasons recorded (PR #43), most of
  nemotron 120b's refused replies in `results-7` were the wrong shape (4 not
  valid JSON, 2 extra fields on a stop step, 1 arguments not an object), not
  length. `providers/chat.py`: `Provider.structured_output` (True for NVIDIA
  only, the one checked live) makes `ChatClient` send the standard
  `response_format` of type `json_schema` with the answer type's schema, so
  the service itself keeps to the shape; the reply is still validated
  against the type. Checked live on 2026-10-21: NVIDIA's hosted API accepts
  it (its own `nvext.guided_json` form is refused) and returned valid replies
  for all seven answer types, `conclude` in 4 s. Tests in
  `test_chat_client.py`: NVIDIA sends the schema, other providers do not, a
  reply is still checked. Not changed: the policy's own checks after the
  schema (a stop step that also names a question still fails `NextStep`'s
  validator, which a schema cannot express).

- **2026-10-21 — fix: console output never stops a run; output tokens
  16,384 (no gate needed: output handling and a measured setting).** On
  Windows, output sent to a file uses cp1252, and printing a conclusion with
  "→" raised UnicodeEncodeError in `experiment run` after the case was saved,
  which would have stopped every case after it. New `capstone/console.py`
  `safe_console()` keeps each stream's encoding but writes an unencodable
  character as an escape ("\u2192"); `experiment`, `benchmark` and
  `memory_comparison` call it first. `MODEL_MAX_OUTPUT_TOKENS` default 8,192 ->
  16,384: with 120 s waits, 3 of the 120b model's replies were cut off at
  8,192 (the reasons recorded since PR #43). Tests: `tests/test_console.py`
  (CI group "Tools and provider"), the pinned default in `test_chat_client.py`.

- **2026-10-21 — L4: why a model reply was invalid is recorded. Built
  ungated, developer to review (understood: no).** In the 120 s wait test two
  of three `conclude` replies from nemotron 120b were refused, and the record
  said only "invalid reply": cut off at the token limit and the wrong shape
  need different fixes. Now an attempt's outcome is "invalid reply: <why>":
  "cut off at the output-token limit", "not valid JSON", "wrong shape:
  <field>: <what was wrong>" (the first field at fault, from Pydantic's error
  list without the input, so the reply's content never enters the record),
  or the policy's own refusal such as "<tool> is not a tool offered here".
  Module by module: `providers/chat.py` `INVALID_REPLY`, `invalid_outcome`
  (builds the outcome from the ValueError), `is_model_outcome` (an answer or
  an invalid reply, old or new form, against a service failure);
  `agent/model_policy.py` `_refuse` marks the attempt as well as the
  question; `experiment.py` `CallSummary.invalid_reasons` and "invalid
  because: ..." in the model-questions line; `benchmark.py`
  `ModelReport.invalid_reasons` and "invalid replies: ..." in the suggested
  limits. `MODEL_OUTCOMES` stays for older code; membership tests became
  `is_model_outcome`. Older records ("invalid reply" alone) count as "reason
  not recorded". Tests: `test_chat_client.py` (each reason, the field named and
  the content never, old and new outcomes), `test_model_policy.py` (a tool not
  offered), `test_experiment.py`, `test_benchmark.py`.

- **2026-10-21 — fallback candidates and 120 s waits (results only;
  nothing built).** `docs/benchmarks/2026-10-21-ministral-cloudflare.md`.
  Ministral 14B (Mistral) and Llama 3.3 70B (Cloudflare Workers AI) were
  benchmarked against Cohere command-a, the fallback. Llama 3.3 70B matched
  Cohere on actions (2/4) and beat it on every reliability measure (100/100
  valid, no failed requests, 5.7 s slowest-5%), so by the developer's rule it
  is the recommended FALLBACK_MODEL; the developer set it in their `.env`.
  Ministral 14B was reliable but asked for unneeded changes (0/4 right
  actions): a small-agent candidate, not the fallback. A test of nemotron 120b
  with 120 s / 240 s waits on three cases: no timeouts and the fallback never
  used, but two of three `conclude` replies were invalid, so whether it
  commits to a fix is still open. The record does not keep why a reply was
  refused; that is the next thing to build.

- **2026-10-21 — docs-only: optional technician voice input deferred to
  the absolute last roadmap item.** Added Future Work 10 in
  `docs/MVP_SCOPE.md` after sensor-triggered machine vision (Future Work 9),
  and clarified that vision is near-last rather than final. The possible
  voice interface would gather opt-in technician reports for the existing
  investigation agent; it is not an MVP task, implementation commitment,
  new model, or dependency. No runtime files or tests changed, and no
  understanding/implementation gate was advanced.

- **2026-10-21 — L3: Requesty and xKiro added as providers, their free
  models benchmarked. Built ungated, developer to review (understood: no).**
  The developer added both routers' keys and asked for them to be
  benchmarked; AGENTS.md section 9 now lists them (still never Anthropic or
  OpenAI models through them). Code: `providers/chat.py` `PROVIDERS` gains
  `requesty` (`https://router.requesty.ai/v1`) and `xkiro`
  (`https://api.xkiro.com/v1`); a reference is router/model as the router
  lists it, e.g. `xkiro/qwen/qwen3.8-max:free` (the client passes everything
  after the first "/" on). `settings.py` gains `REQUESTY_API_KEY` and
  `XKIRO_API_KEY`; `.env.example` lists both. Tests: `test_chat_client.py`
  (the provider set, each router's address and key, a router passes the whole
  model name on). Results, `docs/benchmarks/2026-10-21-routers.md`: only
  price-0 models were run, and neither free account carried a whole
  investigation. Requesty allows one request in flight at a zero balance, so a
  request our client stops waiting for blocks the retries (HTTP 429); xKiro's
  daily free-model token quota ran out after about three episodes; Requesty
  lists NVIDIA's nemotron nano but NVIDIA answers "Gone". The developer's plan:
  nemotron 120b stays the main investigator; the routers' small models are for
  narrower jobs in a later multi-agent design, measured per job.
  Follow-ups found: a per-provider request limit (wait the whole question on
  Requesty) and a whole-request deadline in the client (an xKiro request ran
  146 s against the 45 s limit, because the limit applies per read).

- **2026-10-21 — fix: `experiment label` asked again on an answer it cannot
  use (repetitive validation, no gate needed per AGENTS.md section 2.2).**
  Pressing Enter with no answer stopped the command with a ValueError while
  the developer labelled `results-5.jsonl`. `ask_label` now asks the cause
  again until the answer is 0-4 or s (any case, spaces ignored), and the batch
  number again until it is a number or blank. Labels already given stay saved,
  and a rerun skips them. Test: `test_an_answer_that_is_not_a_choice_is_asked_again`.

- **2026-10-21 — first complete live run of the known-answer cases
  (results only; nothing built).** Command, from the developer's main
  checkout at `33b03c0` (all of PRs #33-#37):
  `uv run python -m capstone.experiment run --name live-known-4 --known
  --out results-5.jsonl`, with the developer's `.env`: nemotron 120b for
  every job, `FALLBACK_MODEL=cohere/command-a-03-2025`,
  MODEL_REQUEST_SECONDS 60 (the `.env` value; the default is 45),
  MODEL_QUESTION_SECONDS 90, 8,192 output tokens, 3 retries, the
  1,200 s / 400 s budget. Real models, real calls; the results file is the
  developer's local `results-5.jsonl` (holds the truth: experimenter only).
  - **Availability is fixed:** no run ended "model unavailable" (15 of 17
    did on 2026-10-20 before L1). 195 of 215 questions answered; NVIDIA
    still sent 3-11 HTTP 500s and 5-15 timeouts per case, covered by the
    retries and the Cohere fallback.
  - **Reasoning is now the weak point.** Read from the conclusions by the
    coding agent, *not hand-labelled* (run `experiment label` for the
    scored numbers): about 3 of the 8 one-fault cases fully right, against
    the rule baseline's ~96% (R4c).

    | Case | Stop | Seconds | What the agent concluded and did | Read |
    |---|---|---|---|---|
    | KA-01 bearing | diagnosis supported | 410 | Right machine (CNC-02), no cause named; escalated | partly right, no fix |
    | KA-02 bearing | diagnosis supported | 726 | Bearing wear on CNC-05; replacement carried out, fault gone | **fully right** |
    | KA-03 batch | timeout | 850 | A shared machine or process step; escalated | wrong cause |
    | KA-04 batch | timeout | 847 | "A batch-specific issue", no batch named; escalated | close, not named |
    | KA-05 setting | timeout | 847 | The inspection process or criteria; escalated | wrong cause, no fix |
    | KA-06 setting | diagnosis supported | 839 | A machine named, no fix; escalated | partly right, no fix |
    | KA-07 false alarm | diagnosis supported | 619 | Temporary spike on CNC-01; no action | **fully right** |
    | KA-08 false alarm | evidence sufficient | 459 | Short-lived spike on CNC-03; no action | **fully right** |
    | KA-09 challenge | diagnosis supported | 755 | Only the decoy spike on CNC-03, "over"; no action | missed both real causes on CNC-07 |

  - What it shows: evidence gathering is mostly fine (all of the relevant
    evidence on the batch cases, 2-3 of 3 elsewhere; only 1 of 5 on the
    challenge). The weakness is committing to a cause and a fix: 6
    escalations, 1 fix asked for. Three cases reached the research deadline
    (~850 s of the 1,200 s; 400 s are kept for the follow-up). A wrong
    setting was never found. On the challenge the agent stayed on the
    machine monitoring named first, which is the trap the challenge sets.
  - For the deferred difficulty modes (Future Work 8, second part), which
    wait on exactly this comparison: the live agent is well below the rule
    baseline on the ordinary cases, so the next work is the agent's
    diagnosis and its readiness to recommend a fix, not harder cases.
  - Not done: hand labels for these nine conclusions (needed for the scored
    "root causes correctly identified" line), held-out seeds, more than one
    run per case.

- **2026-10-20 — L2: the in-scope models benchmarked, and the limits set from
  the numbers (next build candidate 2). Built ungated, developer to review
  (understood: no).** Results and what was set: `docs/benchmarks/2026-10-20.md`
  (raw calls beside it). Models chosen by the developer: nemotron 120b,
  Cohere command-a-03-2025, nemotron lightning 30b, and (added later) Cohere
  command-a-reasoning-08-2025; Groq and Mistral left out for their rate limits.
  One seed per fault (four episodes per model), for time. Only nemotron 120b
  carried out a needed fix (the bearing); command-a was fast and reliable but
  never asked for a fix; lightning gave mostly invalid replies;
  command-a-reasoning got HTTP 422 on every decide question (cause not found).
  What changed, module by module:
  - `benchmark.py`: `single_model_clients` takes the retries and the question
    limit from settings, as a real run does (it used the client's own 20 s);
    `run_model` times each episode (`EpisodeRecord.wall_seconds`) and hands
    each record to `on_record`, so `main` saves each episode as it ends;
    `ModelReport` gains `concluded`, `median_episode_seconds` and
    `outage_reasons`; `Limits` and `suggested_limits` (request = slowest 5%,
    question = twice that, investigation = 2 x questions per episode x median)
    and `format_limits`; `--timeout-seconds`.
  - `providers/chat.py` `FallbackClient.ask`: retry pauses double (2, 4, 8 s),
    falling back to the shortest when a long one no longer fits;
    `settings.py` MODEL_RETRIES default 1 -> 3 (the 120b model's HTTP 500s).
  - `agent/state.py` `Budgets`: 900/300 -> 1,200/400 s (the 120b model needed
    about 948 s and timed out twice at 900 s).
  - `.env.example`: MODEL_RETRIES=3.
  The job table is unchanged (nemotron 120b for every job); the recommended
  local FALLBACK_MODEL is cohere/command-a-03-2025.
  Tests: `test_benchmark.py` (settings reach each job, each episode timed and
  handed on, conclusions / episode time / failure reasons in the row, the
  suggested limits, nothing measured suggests nothing, the command writes the
  limits), `test_chat_client.py` (pauses 2, 4, 8 s; a pause that no longer
  fits becomes 2 s; the new retry default).

- **2026-10-21 — the prompts show the time left and say how to spend the
  budget (developer's request). Built ungated, developer to review
  (understood: no).** A model cannot sense time passing, so `render`
  (`agent/model_policy.py`) now ends the BUDGET LEFT line with "about N
  seconds for this stage" whenever the loop has set `seconds_for_question`
  (the time the current stage has left). `COMMON`, shown to every job,
  gains a pacing rule: spend the budget where it can change the answer,
  prefer the call most likely to confirm or rule out a hypothesis, being
  thorough matters more than being fast, and once more evidence would not
  change the diagnosis the work is done. The `decide` prompt adds a stop
  case: when the remaining budget is better saved than spent on a call
  unlikely to change the model's view. New `LOW_CALLS` (2) and
  `LOW_BUDGET_NOTE`: only while researching (no conclusion yet) with at
  most two research calls left, the prompt adds "few calls remain; choose
  the one that best separates the hypotheses", so ordinary turns are not
  primed to hurry. Tests: three in `tests/test_model_policy.py`. Not run
  live: whether it changes a real model's behaviour is not yet measured.

- **2026-10-20 — cleanups (next build candidate 7; configuration, no gate
  needed per AGENTS.md section 2.2).** `.env.example` now lists every
  setting `capstone/settings.py` reads (memory store, embedding model, the
  six provider keys under the exact names the code reads, the job table,
  FALLBACK_MODEL, the four model limits), each with a one-line meaning, and
  says that other names (such as `GROQ` or `GOOGLE_GEMINI_API_KEY`) are not
  read. CHROMA_PATH is commented out because a blank value would mean "this
  folder". New `tests/test_env_example.py` (CI group "Tools and provider"):
  every setting is listed, nothing is listed the code does not read, and a
  copy of the file loads to exactly the defaults. Stale worktrees: the
  eval-records and runtime-limits worktrees (sessions done, branches fully
  merged into main, nothing uncommitted) were unregistered and their local
  branches deleted; two empty folders could not be deleted while in use.
  Remote branches `claude/gifted-hamilton-eqyqf4`, `feature/episodic-memory-
  reflection` and `feature/reasoning-working-memory` are fully merged too and
  were left for the developer to delete.

- **2026-10-20 — E6: the compound challenge in experiments (Future Work 8,
  first part; next build candidate 3). Built ungated, developer to review
  (understood: no).** An experiment case can now name the kind of factory it
  runs on, and `run_episode` builds the compound challenge through
  `simulator/challenge.py` `build_challenge`. Monitoring, prompts and scoring
  are unchanged for every kind. Module by module:
  - `episode.py`: `STANDARD` / `CHALLENGE` / `SCENARIO_KINDS`, the kinds of
    factory. `build_world(seed, kind=, fault=, machines=)` builds either one
    (the challenge takes no `fault`: it chooses its own; an unknown kind is
    refused). `run_episode(..., kind=)` uses it; a challenge run's default
    key says "challenge".
  - `evaluation/known_answers.py`: `KnownCase.kind` (default "standard",
    `fault` may be None for the challenge) and the ninth case
    `KA-09-challenge` (seed 3: a worn bearing and a 1.25x speed setting on
    CNC-07, a harmless vibration spike on CNC-03, a drifting and briefly
    silent temperature sensor on CNC-02). Monitoring first notices the
    harmless spike on CNC-03, not the machine with the real faults: that is
    the challenge's trap, and it holds on every seed 0-11 checked.
  - `experiment.py`: `Case.kind`; `challenge_cases(seeds)`;
    `run --challenge SEEDS`; `several_faults(score)`; `report` totals and
    lists one-fault runs and several-fault runs apart when both are present
    (each run line keeps PR #30's failure details).
  Tests: `test_known_answers.py` (KA-09's five truths and what monitoring
  sees; the look-once stand-in collects nothing about the real causes),
  `test_episode.py` (the two kinds, refusals, a challenge episode scored with
  two causes), `test_experiment.py` (challenge cases, the command, a scored
  challenge run, the split report, no split for one kind). Not run live.
  Difficulty modes (the second part) are not started, as the developer
  decided.

- **2026-10-20 — L1: make live runs finish (next build candidate 1). Built
  ungated, developer to review (understood: no).** Why live runs ended
  "model unavailable", found from the records, the code and small live
  checks (request-level timing, no keys or content logged):
  1. *Time limits shorter than the model takes.* The default model
     (nemotron 120b on NVIDIA's hosted API) answered one small question in
     6, 10, 6 and 40 s and once not in 120 s; in a real episode 6-39 s, with
     up to 3,782 reasoning tokens. The defaults were 15 s per request, 20 s
     per question and 180 s per investigation, so results-2 (15 of 17 runs
     "model unavailable") ran out after the first retry.
  2. *A slow model's retry ate the fallback's time* (code). With 60 s per
     request and 90 s per question, a timed-out question was retried on the
     same model and the fallback was never asked.
  3. *Groq refused every request with HTTP 403* (code): its front end
     blocks urllib's default "Python-urllib" User-Agent (Cloudflare error
     1010).
  4. *A question cut off by the stage's deadline counted as an outage*
     (code): the client stops with under a retry pause (2 s) left, and the
     loop then saw time left and ended the run "model unavailable" instead of
     "timeout".
  5. *Settings in the developer's local `.env`* (not code, not changed):
     FALLBACK_MODEL is a Mistral model, and the Mistral key answers HTTP 429
     "Rate limit exceeded" to every model; the Groq and Gemini keys are
     stored as `GROQ` and `GOOGLE_GEMINI_API_KEY`, names the code does not
     read (it reads `GROQ_API_KEY`, `GEMINI_API_KEY`). Groq's
     qwen3.8-27b, once reachable, hit its free tier's input-tokens-per-
     minute limit on our ~5,000-token prompts, so it cannot be this agent's
     fallback; Cohere command-a-03-2025 answered 5/5 large prompts in
     6-23 s and was used as the fallback for the live rerun.
  What changed, module by module:
  - `providers/chat.py`: `USER_AGENT`, sent by `post_json` on every
    request. `FallbackClient.ask` gives each model, retries included, an
    equal share of the time left with the models still to ask, so the
    fallback is asked while there is time ("not asked again, no time left"
    when a retry is skipped). `ModelError.out_of_time` (and
    `no_answer(..., out_of_time=)`): set when the client gave up because
    the caller's time limit, not the question's own, ran out.
  - `agent/loop.py` `ask_policy`: such an error is `OutOfTime` (a timeout),
    not an outage.
  - `settings.py` defaults, each with the measurement beside it:
    MODEL_MAX_OUTPUT_TOKENS 2048 -> 8192, MODEL_REQUEST_SECONDS 15 -> 45,
    MODEL_QUESTION_SECONDS 20 -> 90. `agent/state.py` `Budgets`:
    timeout_seconds 180 -> 900, followup_seconds 60 -> 300. FALLBACK_MODEL
    stays unset by default: a default naming a provider would stop anyone
    without that provider's key.
  - `experiment.py` `CallSummary.outage_reasons` (why requests failed, by
    reason) and a "failed because:" part of the model-questions line.
  Tests: `test_chat_client.py` (User-Agent sent; each model's share; the
  fallback asked after a slow first model; out_of_time set only for the
  caller's limit), `test_model_policy.py` (giving up 1.5 s before the
  deadline ends the stage as a timeout; checked to fail on the old loop),
  `test_experiment.py` (reasons counted and reported),
  `test_agent_investigation.py` (one test pinned to the old 180/60 budget).
  Live rerun of the known-answer cases (`run --name live-fix-2 --known`,
  NVIDIA 120b with Cohere as fallback, started before fix 4): KA-01
  answered 20/20 questions, stopped "diagnosis supported", described CNC-02's
  vibration correctly but recommended escalate instead of a bearing
  replacement; KA-02 and KA-03 answered 29/33 and 28/31 but reached the
  research deadline mid-question and were recorded "model unavailable", the
  bug fix 4 removes. The remaining cases' results are in the final report.

- **2026-10-20 — course Module 4 (tree-of-thought reasoning): an opt-in
  tree-of-thought hypothesize step. Built ungated, developer to review
  (understood: no).** Gap note for Module 4 in `docs/COURSE_MODULES.md`.
  New `capstone/agent/tree_of_thought.py`: `TreeOfThoughtPolicy`, a
  `ModelPolicy` whose `hypothesize` asks one question for up to five
  `Candidate`s (`Candidates`, system prompt `GENERATE`), a second for a
  `Rating` of each (sure / likely / impossible, a confidence, a telling-
  apart question; `Ratings`, system prompt `VALUE`), then `prune` in code
  keeps the best three (drops impossible, uncited-evidence, unrated, and
  lower-ranked candidates, deterministic) and turns them into H1... with
  questions T1...; `Thought` records each tree in `thoughts`.
  `agent/model_policy.py`: `ModelPolicy._ask` takes an optional `system`
  prompt (default unchanged). `experiment.py`: `model_policy_factory(...,
  tree_of_thought=False)` and `run --tree-of-thought`. Off by default; the
  default policy is unchanged. Tests: `tests/test_tree_of_thought.py` (11,
  fake models), including the scripted seed-6 episode run both ways
  through `run_experiment` (same conclusion, resolved, one more question).
  README "Research basis" credits Yao et al. 2023. Not run live.

- **2026-10-20 — course Module 3, piece 2: bounded, recorded memory
  search. Built ungated, developer to review (understood: no).** Closes the
  two gaps found in Module 2. `providers/recall.py`: `RecallingProvider`
  refuses the same search twice in one investigation (same words after
  `normalize`, same limit), whatever the tick, with `REPEATED_SEARCH`, and
  answers at most `max_searches` searches (`MAX_SEARCHES` = 3, the Future
  Work 1 default), refusing later ones with `SEARCHES_SPENT`; both are
  `invalid_arguments` errors whose message the next prompt shows; a store
  failure spends nothing; `RECALL_SPEC` states the limits.
  `evaluation/memory.py`: `RecallSearchRecord` and `build_search_records
  (state)`, one record per search from the loop's decision records (words,
  limit, answered / repeated / budget_spent / failed, memory IDs).
  `experiment.py`: `ExperimentRecord.recall_searches`, and the run line
  shows `searches=` and `refused=`. `memory_comparison.py`: the mode line
  shows refused searches. Tests: 8 more in `tests/test_recall_tool.py`; two
  expected report lines updated in `tests/test_experiment.py` and
  `tests/test_memory_comparison.py`. Limits: per investigation, not per
  knowledge gap; the agent's own usefulness judgement is not recorded.

- **2026-10-20 — experiment model failure diagnostics (built ungated,
  developer to review; understood: no).** Trial-4 answered 33 questions
  but all four cases stopped on a later unanswered question. Previously
  `summarize_calls` discarded the individual attempts, making a timeout
  indistinguishable from HTTP errors in the saved results. In
  `capstone-code/capstone/experiment.py`, `CallSummary.details` now keeps
  the existing ordered `ModelCall` records (job, outcome, answering model,
  attempts with model, safe error and duration). `summarize_calls` copies
  them; `format_call_failures` shows unanswered questions and recovered
  service failures; `report` uses it under each case; the CLI's
  `save_record` appends the record and immediately prints its diagnostics.
  No prompts, response bodies or keys are added. Older files still load
  (`details=None`), with a note when missing diagnostics cannot be shown.
  In `evaluation/scoring.py`, the summary now says a required model
  question was unanswered, instead of saying no model answered at all.
  Scoring exclusions and agent behavior are unchanged. Offline tests in
  `tests/test_experiment.py` exercise timeout plus unreachable/HTTP
  401/429/500 fallback through the real client, policy, episode, CLI file
  and report; private error text stays out; a successful fallback retains
  the failed attempt; old files load; absent attempts do not invent a
  cause. `tests/test_evaluation.py` checks the clarified summary wording.
  No live model run was made. Old trial results cannot recover discarded
  errors; a new run is required to diagnose the service failure.
  Verification: `uv sync --all-extras`; `uv run pytest` (1,107 passed);
  `uv run ruff check`, `uv run ruff format --check` and
  `uv run python .github/test_groups.py check` all passed. Read-only code
  review found no actionable issues.

- **2026-10-20 — course Module 3 (RAG and vector databases), piece 1: the
  memory comparison command. Built ungated, developer to review
  (understood: no).** Gap note for Module 3 added to
  `docs/COURSE_MODULES.md`. New module `capstone/memory_comparison.py`
  (next build candidate 5): `MODES` (none, keyword, semantic);
  `memory_for(mode, repository, index)` gives the memory one mode reads
  (None for "none", so the agent is not offered recall; semantic without an
  index is an error, never a silent keyword fallback); `compare_memory`
  runs the same cases once per mode through `run_experiment` with no audit
  log, so nothing is learned and no mode feeds the next; `mode_of` reads
  the mode back from the run key (`<name>/<mode>/<number>/<case>`);
  `compare_report` prints one line per mode and one line per case, and
  warns when the modes ran different cases; `main` gives `run` and
  `report` commands. Tests: `tests/test_memory_comparison.py` (10, scripted
  policies, SQLite, a fixed fake index). Not run live: that needs the keys,
  DATABASE_URL and a filled store.

- **2026-10-20 — course Module 2 (agent architecture: memory, tools,
  reasoning loops): gap note. Built ungated, developer to review
  (understood: no).** Documentation only. New `docs/COURSE_MODULES.md`
  records, per course module, what the capstone already does and what is
  missing. Module 2: working memory (`InvestigationState`), episodic memory
  (`capstone/memory/`), typed tools (`contracts/tools.py`,
  `providers/factory.py`) and the two-level loop (`agent/loop.py`,
  `agent/investigation.py`) all exist. Two small gaps found, both where
  memory meets the loop, to be built under Module 3: a repeated memory
  search is not recognised as a repeat once the tick has moved, and recall
  has no budget or search record of its own. Scope set by the developer the
  same day: Modules 2-4 only; Modules 5-7 are not a focus now.

- **2026-10-20 — two future-work items recorded (documentation only).**
  At the developer's request, `docs/MVP_SCOPE.md` gains "Future Work 8 —
  harder scenarios": (1) running the compound challenge in experiments:
  scoring of several true faults is ready (E5) but `run_episode` and
  experiments build only the four ordinary scenarios, so `build_challenge`
  cannot be run, recorded or reported yet; (2) easy / intermediate / hard
  modes (1 / 4 / 8 problems) with a frontend button, deferred until the first
  live agent run is compared with the rule baseline, as the developer
  decided. Also a ranked "Next build candidates" table (seven items:
  make live runs finish, benchmark, challenge in experiments, evaluator
  model, memory comparison, live progress view, cleanups) for the developer
  to choose from. Nothing built.

- **2026-10-20 — fix: settings found no `.env` after the folder move
  (packaging, no gate needed per AGENTS.md section 2.2).** After PR #23
  moved the package into `capstone-code/`, `settings.py` still looked for
  `.env` and `.chroma` one folder above itself, which became
  `capstone-code/`: no keys were read ("set NVIDIA_API_KEY") although the
  developer's `.env` at the top was correct. `REPO_ROOT` (two folders above
  `settings.py`, the one holding `pyproject.toml`) now anchors both; a test
  pins them there.

- **2026-10-20 — E4 and E5 closing questions PASSED. All five
  evaluation-record items (E1-E5) are complete.** E5: asked about a
  challenge run naming both CNC-03 causes plus "bearing wear on CNC-01"
  (where only a temperature sensor drifts), the developer gave 2 causes
  found and 1 wrong cause, and said the run is not fully right but gave a
  different reason (the agent might have blamed an open door for the
  temperature). Corrected: it is not fully right because a wrong cause was
  named; the door is about how an agent could be misled, not the rule.
  Asked whether naming only the two CNC-03 causes would be fully right,
  the developer said yes. Correct. E4 (the half taught earlier, on a new
  case): asked whether a 30/40 held-out run may be reported as 30/36 by
  leaving out seed 1005 with a noisy sensor, the developer said nothing can
  be left out; look into why it went wrong or report the noisy sensor.
  Correct.
- **2026-10-20 — A9b: the decide answer as one flat object. Pre-check
  PASSED after one re-teach; built; closing question PASSED after one
  re-teach.**
  Found live: on the developer's trial-2 run most `decide` replies were
  invalid; one case run by hand showed the model answering
  `{"decision": {"CallTool": {...}}}`, the union's definition name used as a
  key, which `NextStep(decision: CallTool | Stop)` refuses. Pre-check: why
  not just unwrap such replies. First answer: arguments would be lost
  (they would not); re-taught that a repair hides each model's real
  invalid-reply rate from the report and the benchmark, and that every
  repair is a guess the agent then acts on. Second answer: the count would
  be lying because replies are repaired. Accepted, filled in: it would stop
  showing how often a model gets the shape wrong.
  Built: `NextStep` is now flat, `choice` (`call_tool` or `stop`),
  `information_needed`, `tool`, `arguments`, `question_id`,
  `hypothesis_id`, `stop_reason`; a validator keeps each choice to its own
  fields (a call names a tool and no stop_reason; a stop gives a
  stop_reason and no tool, arguments or ids), refused as an invalid reply
  otherwise; `NextStep.decision()` returns the loop's own `CallTool` or
  `Stop`, so the loop, the scripted policies and the offered-tools check are
  unchanged. The decide system prompt names the fields. The explanation is
  a comment, not the docstring, because the docstring goes into the schema
  the model reads (a test caught the first version quoting the bad shape).
  Live check (not a test), KA-01 with 60 s / 90 s / 900 s limits: decide
  answered 3 of 3 (before: 0 of 2). The run still ended
  `model_unavailable`: two `interpret` replies were cut off at the 2,048
  output-token limit (33-38 s each), then NVIDIA answered HTTP 500 twice
  with no fallback model set. Both are settings (`MODEL_MAX_OUTPUT_TOKENS`,
  `FALLBACK_MODEL`), not code. Questions took 11-38 s each.
  Closing question: what happens to `{"choice": "stop", "stop_reason":
  "evidence_sufficient", "tool": "get_events", ...}`, which code decides,
  how it shows in the report. The developer did not know; re-taught the
  path (the client validates `NextStep`, `one_kind_of_step` refuses a stop
  that names a tool, `ModelPolicy` records `invalid_reply`, the loop an
  `invalid_decision`, the report one more invalid reply under `decide`).
  Asked about the same reply with `"tool": null`: accepted, and the loop
  moves on. Correct (it ends the stage: investigate goes to hypothesize,
  test to the conclusion). A9b is complete.

- **2026-10-20 — the code folder moved into `capstone-code/` (developer's
  request; packaging only, no gate needed per AGENTS.md section 2.2).**
  `capstone/` is now `capstone-code/capstone/`; its Python name is still
  `capstone`, so every import and `python -m capstone.<module>` command is
  unchanged. `tests/` and `docs/` stay at the top. `pyproject.toml`:
  setuptools finds the package in `capstone-code`, pytest adds it to the
  path, ruff counts it as first-party. Four tests that read source files
  by path now take the folder from `capstone.__file__`. README and AGENTS
  section 6 show the new layout; paths written as `capstone/...` in older
  notes and docs mean `capstone-code/capstone/...`.

- **2026-10-20 — E5: scoring several true faults. Contract agreed with the
  developer; pre-check PASSED; built; closing question NOT YET ASKED.**
  Decisions (the developer's, from three proposed): D1 bearing wear, a wrong
  setting and a bad batch are causes; a false alarm, sensor drift and sensor
  dropout are distractors (blaming one is a wrong cause, a fix on one is
  unnecessary). D2 plain counts: causes found and causes resolved out of the
  total, and "fully right" only when every cause is named and no wrong cause
  is; no severity weights (the developer raised that a wrong setting ruins
  parts rather than breaking the machine; weights were offered and declined
  for now, as they would be invented without data). D3 one score shape:
  a one-fault run is one cause and no distractors, and scores as before.
  Pre-check: the agent names and fixes the bearing but misses the speed
  setting on the same machine; the developer said the run is not fully
  right. Correct (1/2 found, 1/2 resolved, filled in). Built:
  `evaluate` takes every truth; `Cause`, `CAUSE_KINDS`, `COMPOUND`;
  `judge_causes` (naming a false alarm is never a wrong cause); `judge`,
  which `evaluate` and `apply_label` now share, so a row is judged the same
  way at the end of a run and later from a label; `Score.causes`,
  `distractors`, `causes_found`, `wrong_causes`, `causes_resolved`,
  `wanted_actions`, `fully_right`; fixes compared as sets; relevant evidence
  of every cause; summary and report show several-fault runs apart. A
  `Label` may name a list of causes (the console labeller still asks for
  one). Not done: experiments cannot run the challenge yet (`run_episode`
  builds only the four ordinary scenarios); that wiring is a follow-up.
  Also recorded: the developer wants easy / intermediate / hard modes with
  1 / 4 / 8 problems and a frontend button to pick one, after the first live
  agent run is compared with the rule baseline (scenario difficulty stays
  deferred until then, as decided earlier on 2026-10-20).
- **2026-10-20 — E4 closing question PASSED IN PART.** Asked whether
  seeds 1002 and 1007 (where all six wrong bad-batch runs fell) or the
  bad-batch cases may be dropped from a 28/40 held-out report, and what to
  do instead, the developer said to look at those batches to improve the
  process, then that one tunes on those seeds and moves to another set.
  The second half is correct (once reported, the set is spent and becomes
  tuning seeds; the next report uses a fresh range). The first half was
  taught, not answered: the report must say 28/40; dropping seeds after
  seeing results is choosing the cases; a note may say where the misses
  fell.

- **2026-10-20 — A9a: NVIDIA embeddings for memory search. Pre-check
  PASSED after one re-teach; built; closing question PASSED after two
  re-teaches.**
  The developer chose `nvidia/nemotron-3-embed-1b` for memory search.
  Pre-check: why an index built with the local model (384 numbers) cannot be
  searched with NVIDIA's (2,048), and why mixing models is wrong even at one
  length. First answer described how semantic search works, not the
  question; re-taught that each model draws its own map (lengths differ, so
  Chroma refuses; at equal length the same position means different things,
  so "nearest" is wrong without any error). Second answer: the whole index
  must be re-embedded with NVIDIA's model, since only vectors from that
  model can be compared. Correct.
  Built: `providers/embeddings.py` `NvidiaEmbedder` (POST `/v1/embeddings`,
  `input_type` passage or query, vectors back in order, refused if not one
  per text) and `embedders_for(settings)` ((passage, query), None for
  "local", ModelError for a missing key or another provider);
  `providers/chat.py` `post_json`, the chat client's error mapping now
  shared (no behaviour change); `settings.py` `EMBEDDING_MODEL` (default
  `nvidia/nvidia/nemotron-3-embed-1b`, or `local`); `memory/semantic.py`:
  `ChromaMemoryIndex(collection, embed, embed_query)` (memories embedded as
  passages, searches as queries), `open_chroma_index(..., model=,
  rebuild=)` records the model in the collection metadata and raises
  `IndexModelMismatch` for another (a collection with no record counts as
  `local`), `open_configured_index(settings)`; `memory/recall.py` opens the
  index from settings and, on a mismatch, logs the rebuild command and uses
  keyword search; `memory/backfill.py` `--rebuild`. One live check (not a
  test): 2,048 numbers per text, and "machine shaking more and more" scored
  0.385 against a bearing memory and 0.099 against a batch one.
  Limits: every promotion and recall is now a network call (time inside the
  investigation budget); recall repeats exactly only while NVIDIA serves the
  same model; an existing `.chroma` index needs `backfill --rebuild`, and
  until then recall falls back to keyword search; `.env.example` not
  updated (this session cannot read it).
  Closing question: someone sets `EMBEDDING_MODEL=local` without
  rebuilding an index NVIDIA built; what does `recall_memories` do, which
  code makes it, and why is that safer. First answer: recall is misinformed
  until `backfill --rebuild`, safer as it needs no network; re-taught that
  `open_chroma_index` raises `IndexModelMismatch`, recall falls back to
  word search (`fell_back=True`), and the point is avoiding a silent wrong
  answer, not the network. Second answer: no memories, with the models
  reversed; re-taught that word search still returns memories, and which
  model is which. Third answer: word search, because the mismatched
  embeddings cannot be compared. Correct. A9a is complete.

- **2026-10-20 — E4: held-out seeds. Pre-check PASSED after three
  re-teaches; built; closing question NOT YET ASKED.** Pre-check: asked
  what is wrong with reporting the held-out number after changing the
  prompt because seed 1003 failed, the developer said the prompt was
  changed instead of the failure being reported (half of it). Asked what
  the higher number says about an unseen seed, said the prompt would need
  changing again. Re-taught (the number now mixes real improvement with
  fitting to those seeds; a new exam is needed, not more lessons on the
  old one); asked where to check a fix and what to report on, the
  developer first said check on the held-out seeds, then the fresh set.
  Re-taught the rule "any seed you look at while deciding what to change
  becomes a tuning seed"; asked whether seeds 1000-1009 are still held out
  after a fix was checked, failed, tweaked and passed on them, the
  developer said no, they are tuning seeds now and another set is needed.
  Correct. Built: `HELD_OUT_SEEDS = 1000-1009` (10 seeds x 4 faults = 40
  runs; the developer's default to change), `held_out_cases()`,
  `experiment run --held-out`, and a report line `held-out seeds: n/m
  runs`. The rule is written beside `HELD_OUT_SEEDS`: tune on 0-999 (the
  tests, known cases, benchmark and rule baseline use 0-60); never tune on
  the held-out seeds, including dropping hard ones; reproduce a held-out
  failure on a tuning seed and fix it there; once anything was changed
  because of them they are spent and the next report needs a fresh range,
  recorded here; memory for a held-out run is learned on tuning seeds. A
  test fails if the held-out seeds ever overlap the known cases, the
  benchmark defaults or 0-60. No held-out run has been made; the set is
  unspent. No real model has been run.
- **2026-10-20 — E3 closing question PASSED (after one re-teach).** Asked
  about a bearing fault on CNC-02 where the agent asks for
  `replace_bearing CNC-02` and `reset_setting CNC-04`, both approved, the
  developer gave the field definitions, then answered True / none / no
  (both fixes needed). Re-taught: CNC-04 has no fault, so `asked != wanted`
  (False), `unnecessary_actions == ["reset_setting CNC-04"]`, and the run
  counts. Asked a fresh case (bad batch, `replace_bearing CNC-01` asked and
  rejected), the developer answered False, the CNC-01 replacement, yes.
  Correct. E3 is complete.
- **2026-10-20 — agent default model changed (configuration, the
  developer's choice).** `capstone/settings.py` `DEFAULT_MODEL` is now
  `nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b` (was
  `nemotron-3.5-lightning-30b-a3b`); every policy question uses it unless
  its own setting or `.env` names another. Both it and
  `nvidia/nemotron-3-embed-1b` were checked present in NVIDIA's hosted
  `/v1/models` list that day (a read-only listing, no chat request). Not
  measured: a 120B model may answer more slowly than the 30B one, and the
  budgets (20 s per question, 180 s per investigation) were not re-set.
  The embedding model is a separate change (memory search still uses
  Chroma's local default embedder).
  Why it matters: the developer's first live run (`experiment run --name
  trial-1 --known`, on the old default) ended all 8 runs
  `model_unavailable` after one question each, 2 failed attempts, about 20 s.
  One plan question asked by hand through `client_for` with 90 s allowed:
  lightning took 19.5 s and was cut off at the 2,048-token output limit
  (past the 15 s request limit, so in the run it timed out); super-vl
  answered with 5 questions in 5.2 s. One sample each, not a measurement.

- **2026-10-20 — older ungated rows reviewed with the developer: 13b, 13c,
  13d, 14, 15, R1, R2, R3. All eight now understood.** Taught each after
  the fact, one question each; no code changed.
  - 13b (re-explain waived on 2026-10-06): where a wrong setting's rejects
    come from, and why `WrongSetting` writes once. First answer: from the
    vibration and heat readings, and no idea; re-taught that readings are
    evidence, `defect_mark` reads `speed_ratio` alongside them, and that
    writing every tick would undo the 13c reset. Second answer: `defect_mark`;
    a later write would undo the fix. Correct.
  - 13c: a reset approved on a machine whose real fault is bearing wear.
    First answer had the 10 ticks down right, but described the state change
    instead of the event, and said the check verifies the action was taken;
    re-taught that the event says "setting was already standard" and the
    check judges whether the symptoms cleared. Second answer: the symptoms
    did not clear. Correct (noted: the event reports a finding, the agent
    infers the diagnosis was wrong).
  - 13d: two pieces of evidence that tell a false alarm from wear. Gave a
    sudden jump, not a slow climb; after a hint, that it goes back to normal
    and temperature does not move. Correct. The developer then asked whether
    this makes false alarms too easy (always check vibration and
    temperature). Yes: R4c's rules get about 96% this way. Partial
    counterweights exist (temperature lag, load and door noise, R4d gaps);
    making it hard needs new scenarios (a glitch on a real load change,
    lasting sensor drift, recurring glitches, composed faults). Left as an
    open design question for the developer. Note: `simulator/challenge.py`
    (`build_challenge`, 2026-10-18) already composes wear or speed faults
    with a harmless spike, temperature drift and missing samples, but is not
    in the experiments' `FAULTS`.
  - 14: what would change if the generator shared the sensors' stream.
    Readings would differ between the two faults' runs, so they could not be
    compared. Correct (the fault would no longer be the only difference).
  - 15: a correct false-alarm diagnosis plus an approved, carried-out
    bearing replacement: fault yes, target yes, action no (expected none;
    the downtime is wasted), resolved yes (the glitch ends by itself).
    Correct.
  - R1: why a look at tick 945 at ticks 0-99 does not show a repair at tick
    900 worked, and what memory would do with it: the data is from before
    the fix; memory would keep a "verified" lesson whatever the repair did.
    Correct.
  - R2: why the 300-row cap refuses rather than silently returning the
    first 300 rows. First answer: a cut answer would look broken; re-taught
    that it looks complete, hiding the rows that show the fault. Second
    answer: it could conceal a real problem outside the rows returned.
    Correct.
  - R3: how a free-text conclusion becomes `fault_correct`, and why judging
    is after the run: `apply_label` fills it in (from a human label against
    the stored truth), so the agent cannot know or change it during the run.
    Correct; added that asking the agent to pick a fault would hand it the
    list of causes, which no prompt shows.

- **2026-10-20 — E3: unnecessary intervention as its own measure. Pre-check
  PASSED; built; closing question NOT YET ASKED.** Pre-check: asked whether
  a fix asked for on a false alarm and rejected by the human should count
  as unnecessary, and why count what was asked rather than what was done,
  the developer said it should count, because counting only what was
  carried out would show "none" although a human had to step in to get the
  right result. Correct; the wording was tidied: it is the agent's
  unnecessary intervention, and the rejection is the human's catch.
  Built: `Score.unnecessary_actions` (a property read from stored fields,
  so older results have it too): each request the true fault did not need,
  so any request on a false alarm or bad batch and a fix on the wrong
  machine; `summarize` counts runs with one (`unnecessary_interventions`),
  `format_summary` prints "N/n unnecessary interventions asked for", and
  each report line shows `extra=`. `recommendation_correct` and
  `action_correct` are unchanged. No real model has been run.
- **2026-10-20 — E2 closing question PASSED (after one re-teach).** Asked
  whether a recalled, uncited lesson from a wrong diagnosis proves it caused
  a later run's wrong answer, and why `effect` stays unknown, the developer
  first raised a different worry (memory would make later runs nearly
  perfect); answered: a memory is a past belief, can be wrong, and recall is
  a hint, but the same seed and fault repeated would let a lesson name the
  answer, so memory must be tested on cases it did not learn from (taken
  into item 4, held-out seeds). Then said `used=None` meant it could not be
  the reason, and did not know the second part. Re-taught: `None` means
  unknown; two wrong runs side by side do not show cause (the case may be
  hard, the model may misread); "hurt" is a claim about cause and code that
  sees only citations cannot make it. Asked what one could do to find out,
  the developer said look at the evidence and the tool calls after the
  recall and conclude from that. Correct: that is a human assessment, the
  route the contract leaves open (`assessment_source="human_review"`).
  Added: the stronger test is the counterfactual, running the case again
  without the memory and comparing. E2 is complete.

- **2026-10-20 — R4a-R4e reviewed with the developer after they were built
  ungated. All five now understood (three after one re-teach each).**
  Taught each one after the fact and asked one question; no code changed.
  - R4a: why the scoring-integrity test compares the next 30 ticks of
    readings as well as the state. First answer was about the third test
    (a fix lasting); re-taught that `model_dump()` does not hold the random
    generator's position, so a hidden draw leaves state equal but shifts
    every later noise value. Second answer: a hidden draw shifts the noise,
    so the twins' readings stop matching, which the 30 ticks catch. Correct.
  - R4b: a false alarm called bearing wear after both relevant items (the
    machine's vibration and events) were collected. Asked for more context
    first, then: `reasoning_miss`, fix the model or prompt. Correct.
  - R4c: why thresholds are tuned on seeds 1-20 and measured on 21-60.
    First answer gave the procedure, not the reason; re-taught overfitting
    (tuning on the measured seeds fits their quirks and overstates accuracy).
    Asked what 100% on 21-60 after tuning on them says about seed 61: it
    overstates, since seed 61 has nuances the rules were not fitted to.
    Correct.
  - R4d: what an agent could learn if the stale record were placed from the
    ground truth (on the faulty machine, none in false alarms). First answer
    missed it; re-taught that the record's presence would itself reveal the
    fault, a leak across the tool boundary. Second answer: placement from
    the truth would hand the truth to the agent. Correct.
  - R4e: H1 leading at 0.93 with two supporters, Q3 open on rival H2, Q4
    open with no hypothesis: no `diagnosis_supported` stop, because Q3 is
    open; Q4 does not matter. Correct.
  Found while teaching: the R4a note below and the docstring of
  `tests/test_scoring_integrity.py` gave the paper's figures in opposite
  directions. Both were right (flawed evaluator 94.3%, corrected 65.5%),
  checked by the developer against the paper; both now use that one
  wording (PR "docs: one wording for the scorer-inflation figures").

- **2026-10-20 — E2: memory records in experiment results. Pre-check
  PASSED after one follow-up; built; closing question NOT YET ASKED.**
  Pre-check: asked what would go wrong if the memory gate could see
  `diagnosis_correct` (read from the hidden truth), the developer first said
  only the most correct memories would be kept and the agent would base its
  work on those, "which is wrong", but not why. Asked what a real gate would
  judge by and what "12/20 to 17/20 with memory" would then measure, the
  developer said it would be measuring the truth instead of what is
  observed. Correct. Added: a real gate has only observations (the fix
  verified by looking again), which can let a wrong lesson in, and that is
  what these records are there to show. Built: `ExperimentRecord` keeps
  `memory_promotion` (the gate's decision, from `build_promotion_record`,
  with `diagnosis_correct` from the score, written after the gate decided)
  and `memory_uses` (one `MemoryUseRecord` per memory recalled, found in the
  run's `recall_memories` evidence; `used=True` only when a hypothesis, the
  conclusion or the proposal cites it, otherwise unknown, never "not used";
  `effect` always "unknown"). `report` adds a memory line: lessons stored
  (from right, wrong, not-judged diagnoses), recalls, citations, and
  recalled lessons that came from a wrong diagnosis (within the same
  results). Nothing here reaches the agent, a prompt or memory; a test
  checks the store holds no evaluator words. No real model has been run.
- **2026-10-20 — E1 closing question PASSED.** Asked what most likely
  happened in a run with `stop=timeout`, 14 questions all answered, 6
  failed attempts and `answered_by` groq 8 / nvidia 6, and whether it counts
  in the reasoning totals, the developer said Groq answered, then had an
  outage and the NVIDIA model picked up the slack; it counts in the
  reasoning totals, though in a benchmark it would not count the same way.
  Correct (the benchmark gives each model alone, so Groq's outage would end
  that episode as "model unavailable"). Added: the counts do not say the
  order (the 8 and 6 may interleave), and the failed attempts and retries
  spent time, which likely caused the timeout, so a timeout here is partly
  the service's doing although it counts against reasoning. E1 is complete.

- **2026-10-20 — R4e: evidence-completeness stop, kept as small as
  possible at the developer's request. Built ungated (understood: no —
  developer to review).**
  Based on Zheng et al., "AgentLoop" (arXiv 2609.33315): stop when the
  information the task needs is in, not on confidence alone. The loop
  already had the parts: `hypothesize` asks the model for open questions
  tagged with the hypothesis they test, and a call with that
  `question_id` closes one. The only change: `diagnosis_supported` also
  needs that no open question tests a current hypothesis (the leading one
  or a rival). Questions with no hypothesis, or on a hypothesis since
  dropped, do not block. Nothing else stops differently: the policy can
  still conclude by itself, and the time, call and stall limits still end
  research. Not done (the paper's fuller version): no per-fault
  checklist, and unanswered questions are not yet listed in the
  conclusion record (they are already in the prompt `conclude` sees).

- **2026-10-20 — Summary of R4a-R4d (built ungated; developer to review).**
  Four changes chosen from a review of recent papers, built least work
  first, each its own PR (#9-#12), papers credited in `README.md`
  "Research basis". In plain English:
  - R4a (`tests/test_scoring_integrity.py`): proves the scorer only reads
    the finished factory. It changes nothing, gives the same score twice,
    and a right answer stays right as time passes.
  - R4b (`Score.miss_kind`): every wrong diagnosis is labelled "missed
    evidence" (never looked at all of it) or "misread evidence" (looked at
    all of it). Tells you whether to fix the tools/investigation or the
    model/prompt. Overstates evidence misses (see R4c, finding 3).
  - R4c (`capstone/baseline.py`): a no-model diagnostician over the same
    tools. On held-out seeds it gets 96% of causes right, the bar the LLM
    agent must clear. It also shows the four scenarios may be too easy,
    and that early wrong settings can't be pinned on a machine.
  - R4d (`capstone/providers/hazards.py`): scheduled tool faults
    (timeouts, missing rows, a stale record) so an experiment can compare
    the agent on clean and faulty tools, and count its retries.
  Next, needing model keys: run `python -m capstone.experiment run
  --known` with and without `--memory` and with and without `--hazards`,
  and compare each against `python -m capstone.baseline --known`.

- **2026-10-20 — R4d: unreliable tools. Built ungated at the developer's
  direction (understood: no — developer to review).**
  Based on Tian et al., "Beyond Function Calling" (arXiv 2606.25819,
  ToolBench-X): agents that do well on clean tools often fail when tools
  misbehave, even with a way to recover open, and more inference does
  not fix it. `capstone/providers/hazards.py` adds `UnreliableProvider`,
  a wrapper in front of the factory provider (like `RecallingProvider`)
  that puts in three of ToolBench-X's hazards on a fixed schedule, never
  at random: `Timeout(tool, nth)` fails that call with a provider error
  that says asking again may work; `Gap(tool, nth)` silently drops rows
  in the middle third of the requested range from that one answer;
  `StaleRecord(machine, performed_at)` adds one wrong maintenance record
  ("spindle bearing replaced; test run vibration normal") dated a day
  before the run. Nothing touches the simulator. `standard_hazards`
  builds the experiment set from what monitoring noticed (the machine it
  named), never from the truth. `HazardReport` lists what fired and how
  many timeouts or gaps the agent followed with a successful call to the
  same tool. `run_episode(hazards=True)`, `run_experiment(hazards=True)`
  and `experiment run --hazards` switch it on; `ExperimentRecord` gains
  `hazards_fired` and `hazards_retried`, and report lines show them.
  Limits: "retried" means the same tool answered later, not that the
  missing range was asked for; the timeout message itself hints at the
  retry (ToolBench-X found such hints help), so this is the easier form;
  the rule-based baseline (R4c) calls the tools directly and is not run
  under hazards. Not yet run with a real model.
- **2026-10-20 — R4c: rule-based diagnostic baseline. Built ungated at the
  developer's direction (understood: no — developer to review).**
  Based on Kim, "When LLMs Sit Above Diagnostic Tools" (arXiv 2610.05031),
  where an LLM given a specialist's answer ended below the specialist
  alone, and arXiv 2509.23113, where rule-based fault classification beat
  LLMs on accuracy. The agent's numbers mean little without a no-model
  yardstick next to them. `capstone/baseline.py`:
  `diagnose(look, act, anomaly)` gets only the observation tools and
  `wait` (a test hands it proxies that refuse `_sim`) and applies five
  rules: a stopped machine is bearing wear; an alarm that is a sudden
  spike (at least 2x the earlier peak) and has fallen away 30 ticks later
  is a false alarm, otherwise bearing wear; a machine whose last 4 job
  times moved 10%+ from its first 4 has a wrong setting; after waiting 480
  ticks, a batch with 2+ rejects at 3x+ the rest's rate is a bad batch;
  rejects no batch explains are a wrong setting with no machine named;
  else a false alarm. Every call feeds a rule, so its evidence share is
  not padded. `run_baseline(seed, fault)` builds the case, runs the
  monitor and the rules, approves and carries out the fix asked for (as
  `approve_all` does for the agent), waits 200 ticks and scores with
  `evaluate`. `python -m capstone.baseline --known | --seeds 21-60`
  prints one line per run and the usual summary.
  Results. Thresholds were set looking at seeds 1-20 only (80/80 causes,
  75/80 targets) and not changed after the held-out run: seeds 21-60 x 4
  faults, 153/160 causes right (96%), 147/160 right machine or batch,
  148/160 right action, 38% of relevant evidence collected; known cases
  8/8 causes, 7/8 targets. Findings for the developer: (1) a page of
  fixed rules nearly solves the four scenarios, so the LLM agent has to
  beat about 96% to add anything, and the scenarios may need harder
  cases; (2) a wrong setting made before a machine has run a few jobs
  (KA-05 among them) cannot be pinned on a machine from these tools,
  since speeds differ per machine and only job-time change shows it;
  (3) R4b's label overstates evidence misses: the rules are right 96% of
  the time with 38% of `RELEVANT_EVIDENCE`, so that list is evidence that
  is enough, not evidence that is needed.

- **2026-10-20 — R4b: evidence-vs-reasoning miss label. Built ungated at
  the developer's direction (understood: no — developer to review).**
  Based on Gopal & Krishnan, "How Far Can Root Cause Analysis Go on
  Real-World Telemetry Data?" (arXiv 2607.13548), which separates a run
  that never gathered the evidence from one that gathered it and reasoned
  wrongly; they need different fixes. `Score.miss_kind` (a property, so
  stored records need no change) is `evidence_miss` when the cause or the
  machine/batch is wrong and some of `relevant_evidence` was not
  collected, `reasoning_miss` when all of it was collected, and None when
  the diagnosis is right, unjudged, or no model answered. A missing answer
  counts as wrong. `summarize` adds `evidence_misses` and
  `reasoning_misses`; `format_summary` prints "wrong diagnoses: X missed
  evidence, Y misread it"; each experiment report line gets `miss=`.
  Simplification: "all the evidence" means every item in
  `RELEVANT_EVIDENCE` for the fault was looked at, not that the agent
  read it closely.

- **2026-10-20 — R4a: scoring-integrity tests. Built ungated at the
  developer's direction (understood: no — developer to review).**
  First of four changes chosen from a review of recent papers, built in
  order of least work first. Based on Chen, "When Agent Evaluation Becomes
  Unreliable" (arXiv 2610.16067): in a post-run rescoring workflow, a
  flawed evaluator that changed the environment before reading it reported
  a 94.3% success rate; corrected, it dropped to 65.5%, an inflation of 28.8
  percentage points.
  `evaluate()` reads hidden state, so `tests/test_scoring_integrity.py`
  pins, for all eight known-answer cases after the right repair (or none)
  and 200 ticks of waiting: (1) scoring a right and a wrong answer leaves
  the clock, the factory state, the event log and the next 30 ticks of
  readings identical to an unscored twin, so no hidden step or random
  draw happens; (2) the same finished episode, or its twin, gets an equal
  `Score`; (3) a right answer is still right on all four marks after 300
  more ticks. A scorer patched to take one step was caught by test (1).
  No production code changed. Also new: the "Research basis" section in
  `README.md` and rule 8 in `AGENTS.md` §11 (credit papers there).
  Local tests ran on Python 3.13 because this session's uv could not
  download the pinned 3.14.7; CI uses the pin.

- **2026-10-19 — A8d: runtime limits. Pre-check PASSED on the second try
  (after one re-teach); built; closing question PASSED (after one
  re-teach).**
  Pre-check: asked why a test-stage `decide` cut off at the research cutoff
  must not end the run as `model_unavailable`, and what the agent does next.
  First answer: report it as a timeout (right) and then retry or ask a human
  for more time (wrong: a retry spends the follow-up time the cutoff keeps,
  and the budgets are hard limits the loop enforces, not something the agent
  negotiates). Re-taught that the run does not end, only research does: the
  60 s kept go to the conclusion, the proposal, the work and the check.
  Second answer: research runs to its limit, then the agent concludes from
  the evidence it has and reports the timeout so the human knows evidence
  may be missing. Correct. (Not answered: `conclude` then gets min(20, 60) =
  20 s.)
  1. A model question is bounded by its stage's time. `ask_policy` in
     `agent/loop.py` puts every policy question (plan, decide, interpret,
     hypothesize, conclude, judge) on a copy of state carrying
     `seconds_for_question`: research time left
     (`InvestigationState.research_seconds`, also used by
     `check_termination` now) in plan, investigate, hypothesize and test;
     the whole deadline's time left in conclude and verify. `ModelPolicy`
     passes it to `FallbackClient.ask(max_seconds=)` (and
     `ChatClient.ask(max_seconds=)`), which can only shorten its own 20 s.
     A `ModelError` after that time has run out becomes `OutOfTime`: research
     stops with `timeout` and the run goes on to the conclusion; a cut-off
     interpretation keeps its evidence, changes no belief and counts nothing
     against the model; a cut-off conclusion is `undetermined` and a cut-off
     judgement `inconclusive`, both recorded as `timeout` stops. A
     `ModelError` with time left is still an outage (`model_unavailable`).
     The lesson, written after the investigation, keeps only its own limit.
  2. A total size for the evidence in a prompt. `evidence_section` in
     `agent/model_policy.py` keeps the evidence section within
     `MAX_EVIDENCE_SECTION_CHARS` (12,000, an estimate): the newest piece
     whole always, then pieces cited by a hypothesis, the conclusion or the
     check, then the rest, newest first, while they fit; the others are
     listed by ID, call and tick with a note naming them and telling the
     model to ask a narrower question (a repeat at the same tick is refused).
     Hypotheses, questions, conclusion, action, prediction and failed calls
     are never shortened; IDs are only copied from state.
  Known limits: a question cut off before any model was asked is recorded in
  `ModelPolicy.calls` as `no_answer`, like an outage; the 12,000 is not yet
  measured against real models' context windows; budget numbers unchanged.
  No real model was run.
  Closing question: why `ask_policy` checks the clock after a `ModelError`
  instead of calling every research `ModelError` a timeout, with a case
  where the two differ. First answer: `OutOfTime` says the model is not to
  blame, the clock ran out (right), but it called an invalid reply a
  `ModelError` (it is a `ValueError`, the model's mistake) and gave no case.
  Re-taught the three failures (invalid reply / outage / out of time) and
  the case: a service down with 50 s of research left must end
  `model_unavailable`, not `timeout`, or the outage is hidden. Asked which
  case a `decide` still thinking at the research cutoff is, the developer
  said a `ModelError` turned into `OutOfTime`: research stops with a timeout
  and the agent goes on to conclude. Correct. A8d is complete.

- **2026-10-19 — E1: model questions and wall-clock time in experiment
  records. Pre-check PASSED; built; closing question NOT YET ASKED.**
  Pre-check: asked why invalid replies and outages are counted apart rather
  than as one "went wrong" count, the developer said they are two separate
  issues: after an outage a retry could still have given a valid reply,
  while an invalid reply means going back to see what went wrong, so the
  results are more honest. Correct. Added: an invalid reply counts against
  the model's reasoning (or the prompt), an outage only against the
  service's uptime, and a run that ended "model unavailable" is already
  left out of the reasoning totals. Built: `CallSummary` per run (questions,
  answered, invalid replies by job, unanswered, failed attempts, which model
  answered how many, so the fallback shows), `ExperimentRecord.model_calls`
  and `wall_seconds` (both optional, so older results files still read),
  `run_experiment(clock=)`, and a model-questions line plus per-run counts
  in `report`. `test_the_suite_is_repeatable` now leaves the wall clock out
  (real time cannot repeat; everything seeded still must). No real model
  has been run.

- **2026-10-19 — checkpoint 8b-2 closing question PASSED (after one
  re-teach).** Asked what a judge could do if `Judgement` had a prediction
  field (vibration stays high after the fix, temperature drops a little),
  the developer first answered about confounding: high load could keep
  vibration high, so the check could wrongly say the fix failed. A real
  point (it is why "inconclusive" exists and why a check should compare like
  with like) but not the one asked. Re-taught: a judge that writes the
  prediction after seeing the evidence can move the target to whatever
  happened ("temperature drops slightly"), so the check says "resolved" and
  memory keeps a false verified lesson. Asked again why the prediction must
  be fixed before the work, the developer said a prediction written with
  the evidence in hand would not differ from what was found. Correct (it
  matches the observed result by construction, so the check could never
  fail). Checkpoint 8b-2 is complete; no real model has been run yet.

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
- **2026-10-19 — closing questions for 8c (PASSED) and 8b-2 (PASSED IN
  PART).** 8c: asked what per-question limit to set for a model with a 2 s
  median, an 18 s slowest 5%, and 1 of 12 episodes "model unavailable", the
  developer said 18 s: the model will not take that long every time, but it
  can take that long without failing, so the limit must allow it. Correct:
  a limit from the median would cut off about half the answers, and each
  cut-off ends the episode. Added: the slowest 5% still leaves 1 answer in
  20 over 18 s, so add a margin (about x1.5, 27 s); check whether the
  "model unavailable" episode was a timeout (a higher limit helps) or an
  outage (it does not); and the limit times about 14 questions must fit the
  investigation budget. Checkpoint 8c is complete except a live run.
  8b-2: asked why `Judgement` has no prediction field and why `ModelPolicy`
  refuses `propose_action` in a decision though the provider would accept
  it, the developer answered the second half: the code accepts the proposed
  action, the model does not have that authority. Correct; added that the
  loop's fixed procedure first checks the conclusion (confidence at least
  0.9, evidence cited), then submits it, then a human decides, and a model
  calling `propose_action` mid-research would skip both. The `Judgement`
  half is asked again and NOT YET ANSWERED.

- **2026-10-19 — rule: every change through a pull request (developer).**
  New `AGENTS.md` §11: every change, whatever its size, goes on its own
  branch and reaches `main` only through a PR with a detailed description
  (what and why, changes file by file, tests, verification, gate status, not
  done, and any commit that reached `main` without a PR); CI must be green;
  then merge with a merge commit and delete the branch (standing permission
  from the developer). The 2026-10-06 note in §1 and the §10 checklist point
  to it. Two commits reached `main` without a PR before the rule: `eea1fe3`
  (180 s budget) and `fe257d2` (8c benchmark); the PR adding this rule
  documents both.

- **2026-10-19 — checkpoint 8c: the provider benchmark. Pre-check PASSED;
  built; closing question NOT YET ASKED/ANSWERED. No real model has been run.**
  Pre-check: asked why the benchmark turns the fallback model off, the
  developer said a row must describe one model's behaviour, and testing the
  model and its fallback together would not. Correct. Added: the unit is a
  model (`provider/model`), not a provider; and a fallback would hide the
  first model's outages (fewer "model unavailable" endings) and blend two
  models' times and scores into one row.
  Built:
  1. `providers/chat.py` `Attempt.seconds`: each request's duration on the
     client's injected clock; the pause before a retry is not counted.
  2. New `capstone/benchmark.py`: `single_model_clients(reference)` (every
     job that model alone, no fallback); `run_model(model, policy_for,
     faults, seeds)` runs each fault on each seed through `run_episode` with a
     fresh `ModelPolicy` and keeps an `EpisodeRecord` (stop reason,
     diagnosis text, action correct, resolved, every `ModelCall`);
     `summarize` gives a `ModelReport` (valid answers, invalid replies by
     job, outages, median and slowest-5% answer seconds, questions per
     episode, "model unavailable" and timeout endings, right action,
     resolved); `format_table`; `save_records` (JSON lines); and
     `python -m capstone.benchmark MODEL... --seeds 0 2 6 --faults ...
     --out docs/benchmarks` writing `results.md` and `calls.jsonl`.
  3. `tests/test_benchmark.py` (9), CI group "Benchmark": the row's counts,
     the nearest-rank percentile, the table row, one model with nothing
     behind it, a scripted episode recorded, a model that never answers
     ending every episode "model unavailable", the command writing both
     files, an unknown model refused.
  NEXT: the developer names the models to run (only NVIDIA Nemotron is
  named in settings); keys are copied into this checkout's `.env` without
  printing them; Cloudflare also needs CLOUDFLARE_ACCOUNT_ID. Default run is
  4 faults x 3 seeds = 12 episodes per model, up to 3 minutes each.
  Closing question to ask: a model has a median of 2 s but its slowest 5%
  is 18 s, and 1 of 12 episodes ended "model unavailable". What per-question
  limit would you set, and why not set it from the median?

- **2026-10-19 — investigation time budget raised; developer's request,
  understood: n/a (one number changed).** `agent/state.py` `Budgets`:
  `timeout_seconds` 60 -> 180, `followup_seconds` 20 -> 60. Why: a whole
  episode asks about 14 model questions (about 10 in research, about 7 from
  the conclusion on). In `tests/test_model_policy.py`, the seed-6 episode
  replayed at 8 s per answer now finishes (supported diagnosis, fix
  approved, check "resolved"); under 60/20 it timed out after 2 tool calls
  and concluded "undetermined". Both are tests. The numbers are an
  estimate, not a measurement: 8c (a per-provider benchmark) should replace
  them. Still open: a single model question is capped at 20 s on its own,
  not by the time the investigation has left.

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

- **2026-10-23 — MMR episodic-recall roadmap note (documentation only).**
  Added a medium-priority, not-implemented Maximal Marginal Relevance (MMR)
  evaluation candidate to Future Work 1 in `docs/MVP_SCOPE.md`. It applies
  initially to episodic-memory retrieval, not to machine manuals or memory
  promotion. Baseline similarity-search results must be measured before
  implementation. Compare relevance, diversity, root-cause correctness, and
  time/token costs under deterministic offline evaluation. No code or
  dependencies changed; understanding/implementation status is unchanged.
  No tests were added or run for this documentation-only update.

- **2026-10-23 — HIGH-priority simulator fidelity roadmap (documentation only).**
  Recorded manufacturing engineer Brandon Reff's feedback: bearing vibration
  should stay near its normal range initially, then climb moderately faster
  over a shorter period, initially targeted at about three simulated days
  (4,320 one-minute ticks if calendar days). Also prioritized a machine
  electrical power consumption sensor in kW, with kWh derived over elapsed
  time, operating-mode baselines, and realistic causal links to load/settings.
  Added adoption gates in `docs/MVP_SCOPE.md` (Future Work 8 and ranked
  candidates) and `docs/FUTURE_WORK_REEVALUATION.md`. Both are planned,
  not implemented. No simulator, agent, or dependencies changed; no local
  tests run for this documentation-only change. Implementation and developer
  understanding statuses remain unchanged.

- **2026-10-23 — Brandon-feedback completeness cross-check (docs only).**
  Follow-up to PR #61: recorded his remaining suggestions explicitly in
  Future Work 8: investigate **motor current draw (amps)** alongside the
  planned whole-machine power sensor, and add **servo-motor/axis-drive** and
  **hydraulic subsystem** fault candidates so machines have more independent
  failure-capable parts. Current is not automatically independent evidence
  when inferred from the same load model; hydraulics are machine-specific.
  Servo and hydraulic candidates are medium-high priority, after the two
  HIGH-priority bearing and kW updates. No implementation, new sensor,
  dependencies, or tests in this documentation change; understanding
  and implementation statuses are unchanged.

Older notes (2026-10-12 and earlier) are in `docs/PROGRESS_ARCHIVE.md`.
