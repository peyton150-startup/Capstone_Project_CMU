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
| C3b | Bounded memory search: no repeated search, at most three per investigation, each recorded | yes (after the build, 2026-10-22) | n/a | yes | yes | `providers/recall.py` (`RecallingProvider`, `MAX_SEARCHES`, `REPEATED_SEARCH`, `SEARCHES_SPENT`), `evaluation/memory.py` (`build_search_records`); session note 2026-10-20 (Module 3, piece 2) |
| D1 | Near-duplicate threshold measurement tool (provisional 0.909) | yes (walkthrough, 2026-10-22) | n/a | yes | yes (after corrections) | `capstone/memory/duplicate_threshold.py`; session notes 2026-10-22 |
| T1 | TypeSafe Jev client and the auto-labeller (proposed diagnosis labels, compared with hand labels) | yes (pre-merge walkthrough, 2026-10-23) | n/a | yes | yes (after corrections: Q1 cost of speculative questions, Q2 why truth would bias labels) | `providers/typesafe.py` (`Noul`, `Choice`, `JudgmentClient`, `read_judgments`, `judgment_client`), `evaluation/auto_label.py` (`propose`, `Proposal`, `agreement`, `conclusions`, `main`), `settings.py` (`TYPESAFE_API_KEY`, `TYPESAFE_MODEL`), `.env.example`, AGENTS.md section 9, `docs/benchmarks/2026-10-23-jev-auto-labels.md`; session note 2026-10-23 (T1) |

Every row above with four "yes" marks (or "n/a") is complete: no question is
outstanding on it. Still to build after 12c, from `docs/MVP_SCOPE.md`: the
other three fault scenarios (material batch, machine configuration, false
alarm), then evaluation, then the agent itself.

## Session notes

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
