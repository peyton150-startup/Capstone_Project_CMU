# Managed-run settings editor — implementation contract (written before code)

## Purpose
Make the **Simulated managed-run launch** controls actually configure the Pydantic Graph execution, not merely render switches. Operators can turn the triage **deterministic override ON/OFF** per run, see all effective stage settings (including forced overrides and model-backed Conclude), submit them with the simulator run, and inspect the exact resolved configuration in persisted run details. Do **not** mutate global environment variables or secrets; changes apply to *new runs only*.

## Dependencies and scope
Draft PR stacked on **#301 → #299 → #295**. Preserve #293/#294/#296 Render event/logging work for later integration. Current API is FastAPI in-process simulator runner, durable SQLite/PostgreSQL journal and browser SSE; no Siemens pilot execution or controller writes. Maintain operator-only submit and viewer-readable previews/results. No new PydanticAI agent; use Pydantic v2 models + existing Pydantic Graph StepContext state/deps.

## Planned contract and runtime behavior
- Introduce strict `TriageRunOptions` for per-run requested values and immutable, validated `EffectiveTriageRun` for resolved values. Explicit allowed knobs: `run_mode` (custom/deterministic), `plan`, `investigate`, `hypothesize`, `evidence_tests`, `packet`, `packet_prompt`, `observe_calls`, `then_deep`, `conclude_brief`, `conclude_cap`, `seconds`, `tool_calls`, `hypothesis_seconds`. Existing launcher inputs `seed`, `kind`, `mode`, `hazards`, `tree_of_thought`, `manual` remain effective.
- **Deterministic ON** wins over stage-specific options for Plan/Investigate/Decide/Interpret/Hypothesize/Test/Observe and disables model Critique/Recheck, sets hypothesis reserve zero; **Conclude stays model-backed** and uses configured model routing. Deep remains independent. Model-backed custom mode exposes individual stage controls; reject invalid combinations with a safe 422 instead of fallbacks.
- Add a viewer-safe POST preview/resolve route and GET launch defaults route. Both use the same resolver as submit. No keys, prompt text, evidence, source identifiers, provider responses or fault truth in these responses. UI shows **requested vs effective** for every listed setting, disabled overridden controls, conditional sections, and resolved process boundaries. A separate effective-state snapshot is persisted **at submission**, so a later global env change cannot silently change settings of a queued run. Distinguish deep-only effective stages and triage-specific settings not applied.
- Wire the immutable resolution into `run_episode` / `run_triage_then_deep` only for this run, overriding budget, conditional stage, packet, Conclude brief/cap and escalation behavior without mutation of global `Settings` or deep deps. Capture planned and actual profile, and a safe configuration hash/manifest in the durable run snapshot, GET run details and event journal. Do not regress idempotency keys: same key + different settings must conflict.
- Launcher has working controls, validated input and preview displayed before submit; any change resets idempotency key. Run detail/list show immutable requested/effective configuration, actual triage/deep status and effective path; link from Engineering Settings to launcher, clarifying that server env remains read-only.
- The profile is *per run*, not shared mutable state. `mode=deep` means no triage settings apply; no hidden forcing of triage. Existing live Siemens data and review permissions unchanged.

## Review passes / acceptance
1. **API/contract pass:** exact validation, defaults, forbidden keys, custom invalid combinations, role boundaries, pilot denial, idempotency, immutable stored snapshot/recovery.
2. **Runtime/variable pass:** follow each field from frontend → FastAPI → journal → worker → `run_episode` → Graph state/deps, Conclude still a model call, deep untouched; test two runs with opposing configurations.
3. **Frontend/reliability pass:** switches/selects submit actual values, preview and persisted result agree, overridden controls clearly marked, no silent stale preview, operator auth errors, replay/Render path and frontend type checks; run automated tests/CI and declare any unverified results.
4. **Security/observability pass:** validate public projection fields, prompt/key/ground truth exclusion, safe log events, reject env or tool-catalog mutation; check overlap with #293/#294/#296 and describe merge prerequisites.

Pydantic references: https://pydantic.dev/docs/ai/graph/builder/ ; https://pydantic.dev/docs/validation/latest/concepts/models/ ; https://pydantic.dev/docs/validation/latest/concepts/validators/ ; https://pydantic.dev/docs/ai/integrations/logfire/ . GraphBuilder state persistence is owned by the existing journal, not Pydantic Graph.

**Do not merge** until PR #301 dependency is integrated, CI and frontend pass, and concurrent Render/managed-progress changes are reconciled.

## Implemented data flow and fixed source-of-truth boundaries

1. Managed launcher reads `GET /api/v1/lab/runs/configuration`, edits an explicit typed allowlist, and POSTs full launch input to `/api/v1/lab/runs/preview`. A change to any input (seed, mode, hazards, Tree-of-Thought, manual, or triage switches) invalidates the confirmed preview and idempotency key. Launch requires a matching preview fingerprint.
2. The server resolves `RunRequest.triage_settings` through `TriageRunOptions` and `EffectiveTriageRun`. Strict Pydantic schemas reject unknown keys and invalid interstage combinations. Deterministic mode forces fixed Plan, deterministic Investigate/Decide/Interpret/Hypothesize/Test and qualified evidence; model-backed Conclude and its independently editable brief/cap are retained.
3. `SimulatorRuns.submit` freezes the effective configuration inside the existing durable `runs.requested` JSON (same SQLite/PostgreSQL schema), with a short SHA-256 correlation fingerprint in the initial snapshot and run-start event. The worker receives the already-resolved private Pydantic object, not a newly resolved environment state, and injects it into `run_episode` and `run_triage_then_deep`. The final record includes both the immutable submitted manifest and sanitized observed triage stage flags.
4. The completed-run view distinguishes requested, effective, overridden, and observed values. Settings page displays validated **global** scalars and an actual stage-routing matrix; it links to the **per-run editor**. Global .env mutation, machine control, arbitrary provider credentials, and pilot execution are not exposed.

### Four static review passes
- **Contract/authorization:** viewer-only preview; operator-only launch; pilot denied; unknown settings rejected; exact per-run immutable capture; stale-preview 409; explicit idempotency; CORS POST preflight and allowlisted conflict messages.
- **Variable-level execution:** `RunRequest` → Pydantic resolver → durable journal → private worker request → `run_episode` → Graph state/deps; triage-only budgets, packet, plan, evidence gates, Conclude flags and deep escalation. No process-wide Settings changes.
- **Frontend correctness:** forced fields visibly display effective choices while preserving custom selections; whole launcher input in hash; stale preview invalidated when edited; confirmed preview required for launch; deep-only ignores triage controls; run list/detail make the true escalation mode, active fingerprint, and observed stage flags explicit.
- **Reliability/privacy:** no exception/provider details or arbitrary env keys in the public manifest; safe timing/status metadata only; Graph trace is not claimed to be a successful model provider call. A changed configuration after preview is rejected and the frontend revalidates. Local CORS origin and Idempotency-Key preflight are covered by tests.

### Verification not yet established
Tests were **authored but have not been executed in this connector-only session**:
`tests/test_triage_run_controls.py` and
`tests/test_web_run_controls.py`, plus preexisting
`tests/test_web_runs.py`, triage suites, and frontend tests/build.
GitHub Actions statuses were queued for recent heads. Do not merge/deploy
until CI, Ruff, frontend TypeScript build, PostgreSQL journal integration,
and scenario-based Graph tests pass at the *exact final head SHA*.

The older concurrent #293/#294/#296 Render progress stack modifies managed
run API and React files. Reconcile that stack explicitly rather than
overwriting durable live progress, role-based Access, sanitized model-call
observability, or startup/reconnect safety.

### Scope limitations
Actual fallback model attempts, credentials, provider latency and complete
model-call history remain under the separate observability work.
The configured Conclude model name is a *route*, not a claim that a request
was sent or answered. Frontend editing is scoped to safe per-run simulator
settings, not unrestricted server model/provider/OT variables. Running
investigations and global environment are never mutated.
