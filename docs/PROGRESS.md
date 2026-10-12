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
| 13c | Action: put a machine's setting right (via the approval desk) | n/a | n/a | no | no | Built ungated; developer to review |
| 13d | False alarm / transient anomaly (fault scenario 4) | n/a | n/a | no | no | Built ungated; developer to review |
| 14 | Seeded scenario generator (fault, machine or batch, start tick) | n/a | n/a | no | no | Built ungated; developer to review |
| 15 | Evaluation | n/a | n/a | no | no | Built ungated; developer to review |
| 16 | The research agent | n/a | n/a | no | no | Built ungated; developer to review |
| 17 | Memory | n/a | n/a | no | no | Built ungated; developer to review |

Every row above with four "yes" marks (or "n/a") is complete: no question is
outstanding on it. Still to build after 12c, from `docs/MVP_SCOPE.md`: the
other three fault scenarios (material batch, machine configuration, false
alarm), then evaluation, then the agent itself.

## Session notes

- **2026-10-12 — Agent 2 storage increment.** Built after the persistence
  pre-implementation checkpoint passed; post-implementation understanding
  remains unverified. `memory/schema.py` defines `episodic_memories`: unique
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
     `ANTHROPIC_API_KEY`. Tests must not need a key: drive the loop with
     a scripted stand-in model. Human approval stays a separate step the
     agent cannot perform.
  6. **17 memory.** One JSON record per investigation (anomaly,
     evidence, hypotheses, conclusion, action, outcome) and a simple
     look-up of similar past cases.
