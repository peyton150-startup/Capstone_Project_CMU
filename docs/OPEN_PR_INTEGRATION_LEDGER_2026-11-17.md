# Open PR integration ledger — manufacturing capstone

**Snapshot:** 2026-11-17; twelve PRs open at audit time: #292–#303.  
**Baseline:** main at e6a2dd399d9faa3ca490bb5216de38eeb9c68c2b (merged #291).  
**Purpose:** make the cross-PR work, technical ownership, dependencies, verification and remaining release gates visible *before* merging. This is a documentation-only ledger; it does not establish that implementation or testing has passed.

## How to read this document

- **Present on branch** means the PR contains source or documentation for a feature, not that the feature is correctly integrated, tested or deployed.
- **Integration needed** means reconciliation, wiring, compatibility or regression work remains to be verified; a missing feature is called out explicitly where established.
- **Acceptance evidence** means tests and checks that must be recorded on the *final merged-source revision*; passing checks on a different branch head do not count.
- **Deferred** means outside the individual PR scope, not permission to claim the overall system is production ready.
- Stacked PRs may merge individually once their *own* scope is correct and validated, but keep hosted mode disabled until the entire two-service path and rollout gates pass.

### Proposed dependency-aware merge order

#292 → #293 → #294 → #295 → #296 → #297 → #300 → #299 → #301 → #298 → #302 → #303.

The order is **not** a requirement to merge a failing PR. It is a conflict-minimizing topological sequence, with #295 independent of the live-progress work and #299/#301 dependent on #295. #298 is physically stacked on #292, #302 on #298, and #303 on #302. Before #298 is allowed to operate in hosted mode, it must reconcile the completed progress, deterministic and model observability stacks; #302/#303 provide the subsequent P0/P1 hosted fixes. Update this ordering if branch/diff inspection exposes another genuine dependency. Retarget stacked PR bases to main *only after* their upstream commits land.

### Mandatory per-PR merge checklist

1. Inspect the *current* PR description, head SHA, base, code diff, reviews and unresolved threads. Identify what is implemented versus documented only. Do not merge a draft or work with an unmet correctness gate.
2. Reconcile branch against current main, preserving **both** legitimate changes in shared code and tests. Rerun this step when a preceding PR merges.
3. **Before qualifying any CI run, rebuild ALL FOUR source-matched inventories** with the repository's coverage/JUnit-backed evaluation/evaltools.build_inventory: FUNCTION_INVENTORY.json, TEST_INVENTORY.json, TOOL_INVENTORY.json and VERIFICATION_MATRIX.json. If the first coverage pass fails solely from stale inventories, use it to bootstrap coverage; never excuse unrelated test failures. Confirm the four files are regenerated for current sources, commit them and remove temporary rebuild workflows. A pre-inventory CI run is not acceptance evidence even if GitHub triggered it automatically.
4. Test the resulting **exact head**: Ruff and format, full pytest and coverage, offline SNAP/evaluator integrity, relevant grouped checks, frontend build/tests, and disposable TLS PostgreSQL migration/integration where applicable. Diagnose failures at the failing job and variable/contract level; do not suppress tests or weaken source/secret gates. Only a still-queued **Tests: Verification** check may be treated as an exception under the user's prior authorization, **not** a failed verification check or any other failed gate.
5. Review privacy/safety boundaries and combined upstream changes; document real browser, cross-process or hosted acceptance gaps explicitly. Merge only when scope and required tests are satisfied, with expected_head_sha. Do not equate merge with rollout.

## Per-PR integration inventory

### #292 — Durable hosted run queue (R1)

**Branch / base:** codex/render-run-persistence → main. **Present on branch:** private SQLAlchemy queue/journal, PostgreSQL migration 0003, idempotent submit, SKIP LOCKED claim, lease fencing, bounded safe events and disposable-DB tests. This is an *infrastructure foundation*, not a functioning independent API + worker.

**Integration needed**
- Preserve merged #291 Siemens/OEM API paths, test-group registrations and PostgreSQL acceptance workflow while introducing run_repository/run_models and test_run_repository. Check migration metadata and ensure private tables have no public/browser grants.
- Verify atomic submit, idempotent retries, two competing workers, stale/expired lease, actor isolation, proposal review, event sequence, empty-schema downgrade protection and interrupted-not-replayed recovery on disposable TLS PostgreSQL.
- **Inventory-first gate:** reconciled branch head 272e84c8 at this snapshot; temporary source-matched rebuild workflow run 44146355865 had not finished. Remove the one-time workflow after inventory commit; count only post-inventory CI.
- Do not route actual hosted traffic into R1 until #298/#302/#303 and two-service acceptance are complete.

**Deferred:** independent worker, web/worker data-flow integration, Render rollout (owned by #298 and later work).

### #293 — Managed triage/deep live progress and final-result audits

**Branch / base:** feat/managed-run-live-progress-20261117 → main. **Present:** phase-aware SQLite/PostgreSQL progress snapshots, constrained investigation projection, triage/deep/final selector and React outcome/detail panels.

**Integration needed**
- Reconcile API app/readers/runs and frontend managed/types with the #291 collector, #294 projection and later #296/#297/#300 consumers. Preserve server-owned investigation IDs and allow only final|triage|deep; no user-supplied audit paths.
- Verify null/legacy record behavior, separate triage versus deep outcomes, review **versus** simulated action execution **versus** actual verification, and uncalibrated confidence labeling. Do not expose simulator truth, private audit JSON, model/provider text or unauthorized pilot information.
- Check SQLite and PostgreSQL journal parity, authenticated and denied reads, React navigation/build and a representative local completed triage→deep browser exercise. Record any external browser/model smoke test not performed.

**Deferred:** role-selector/access redesign (documented separately), raw pre-completion evidence, physical-machine correctness.

### #294 — Source-safe field-level Render progress

**Branch / base:** feature/render-safe-complete-triage-progress-20261117 → #293. **Present:** typed bounded stage/requirement projection, source-clock and packet coverage, phase-aware final reconciliation, terminal replay, SSE stream.closed and resync signaling.

**Integration needed**
- Merge/rebase **after #293** and preserve its phase audit and final-outcome panels. Revalidate that SafeStageSnapshot is the single canonical safe public contract, including 55-field-compatible hosted projection and requirement IDs/statuses.
- Test event ordering, queued-to-running-to-terminal, triage→deep, dropped watcher updates, a stale event after terminal completion, journal restart, SSE CRLF/chunk limits, explicit terminal end-of-replay and browser reconnect. Observer/storage exceptions must never abort an investigation.
- Do not leak free-form questions, source values, tool arguments, ground truth, tokens, prompts or provider exceptions. Verify authenticated local/hosted projections. Remove temporary pr294-inventory-refresh.yml only after successful rebuild and committed inventories.

**Deferred:** independently hosted worker contract, physical Siemens ingestion and production deployment.

### #295 — Deterministic Decide and fixed Plan defaults

**Branch / base:** fix/triage-deterministic-decide-default-20261117 → main. **Present:** deterministic Decide/fixed Plan default configuration changes and associated triage tests.

**Integration needed**
- Reconcile Pydantic Settings, .env.example, agent/triage_decide.py and tests with #299/#301 changes. Explicit deployment environment values may override defaults; inspect stale TRIAGE_PLAN=model / TRIAGE_INVESTIGATE=advisory.
- Verify no LLM Decide/Interpret calls in deterministic Investigate/Test, existing source-quality and clock gates, stable tool selection, no simulator ground-truth access and no unexpected change to deep behavior.
- Confirm the final **Conclude remains model-backed** and that model Hypothesize remains available where explicitly selected. Validate old setting serialization and direct run callers.

**Deferred:** complete deterministic Hypothesize contract (#299) and unified one-switch profile (#301).

### #296 — Durable deterministic Decide timeline

**Branch / base:** feat/triage-decide-safe-live-trace-20261117 → #294. **Present:** pending-selection timeline and safe typed Decide trace from agent selection through managed-run audit/progress UI.

**Integration needed**
- Land after #294. Preserve its phase/requirement progress and #293 completed audit fields; do not duplicate the typed triage event sanitizer or add a second graph/model call.
- Prove a pending selected tool appears **before** completion, ordered selection/validation/requirement/stop events survive audit roundtrip and restart, and older audits remain readable.
- Test strict bounded event projection with malicious/free-text inputs, dropped watcher events, and separate visibility of selected versus executed/failed reads. Coordinate api/runs.py and frontend managed/types edits with #297, #299, #300 and #301.

**Deferred:** LLM model/provider attempt timeline (owned by #297).

### #297 — Local/Render model-call chronology

**Branch / base:** feat/model-call-telemetry-local-render-20261117 → #294. **Present:** canonical api/model_calls.py Pydantic sanitized call/config/attempt contracts, SQLite/PostgreSQL managed-run journal integration, bounded model-call endpoint and React timeline for existing managed-run path.

**Integration needed**
- Merge after #294 (prefer after #296 to resolve shared runs/UI variables once). Preserve model.monitor, model.config, model.call and model.monitor.finished outcomes; include model ID, stage, question type, retry/fallback, latency, token counts and safe failure class where recorded. Never fabricate provider calls from frontend simulator success.
- Validate missing credentials, timeout/429/fallback, restart/partial recording and read-time revalidation. Generic SSE must **not** expose model.* records or private provider/prompt content.
- **Confirmed integration boundary:** #298 worker initially lacks this path. #302 adds a *branch-present* lease-fenced hosted bridge using #297's schemas; after joining branches, verify hosted journal writes, endpoint pagination/auth, no duplicate calls and that provider attempts persist across worker termination. Do not assume #302 alone proves full two-process parity.

**Deferred:** production provider credentials, hosted smoke validation and external telemetry export.

### #298 — Two independent Render services, worker and queue

**Branch / base:** feature/render-two-service-agent-worker-20261117 → #292. **Present:** hosted web adapter, separate Pydantic Graph worker, migrations 0004, private audit/artifact persistence, safe stage events, queue health and a review-only Render blueprint. Not deployed.

**Integration needed (high risk)**
- Integrate merged #293/#294 authorized phase audits and canonical stage/requirement projection; #296 early Decide read timeline; #297 model attempt taxonomy and endpoint via #302; #300 deep lifecycle; #295/#299/#301 resolved triage settings and effective-mode visibility. Do **not** silently discard unknown-but-authorized stage or telemetry fields while adapting an old worker branch.
- Resolve any conflict in app.py, run_models.py, run_repository.py, runs.py, hosted_runs.py, worker/runner.py, test_groups.py, postgres-journal.yml and migration head. Ensure backend selection defaults to the current safe local path and hosted web never launches models in-process.
- Test duplicate submissions, concurrent SKIP LOCKED claims, lease heartbeat during blocking provider I/O, stale-token rejection, SIGTERM/restart interruption **without replaying plant/simulator actions**, exact reviewer decision and expiration, audit-before-terminal commit, triage→deep, reconnect/SSE, private artifact retention and no raw leaks.
- #302 is a stacked **P0 integration companion** and #303 a stacked **P1 reliability companion**; merge or reconcile them sequentially, but do not activate hosted mode based on #298 alone. Verify a real API process plus a separately running worker against disposable PostgreSQL.

**Deferred:** live service provisioning, site credential setup, production migrations, soak, multi-worker capacity planning and Render deployment approval.

### #299 — Deterministic Hypothesize/Test packets (P0–P2)

**Branch / base:** feat/triage-deterministic-hypothesis-hardening-20261117 → #295. **Present:** new hypothesis-rule/packet implementation and tests on a draft branch; the PR text is an implementation contract, not test evidence.

**Integration needed**
- Merge after #295; reconcile api/runs.py/managed/types with #293/#294/#296/#297/#300. Ensure TRIAGE_HYPOTHESIZE=deterministic default is intentional and model remains an explicit comparison arm.
- Validate versioned Pydantic TriageHypothesisPacket, source cutoff/freshness, canonical candidate/requirement references, evidence provenance and precommit validation. An unsupported/missing read must remain *unknown/unavailable*, never a confirmed cause or confidence score.
- Verify repeatability, multiple-machine and coverage-gap possibilities, missing/delayed telemetry, strict safe UI summary and absence of new provider calls/fallback. Do not change deep hypothesis policy.

**Deferred:** empirical model-versus-deterministic accuracy calibration, OEM machine control.

### #300 — Complete deep-investigation execution lifecycle

**Branch / base:** feature/full-investigation-live-lifecycle-20261117 → #294. **Present:** backend deep-progress contract, React stage tracker, tests and documentation.

**Integration needed**
- Land after #294 and reconcile phase progress with #296 Decide events and #297 model attempt chronology; keep separate identities and event semantics for evidence collection, Critique/Recheck, proposal, pending/approved/rejected review, simulated action start/end and verification status/outcome.
- Ensure durable snapshots survive restart and queue drops, terminal state wins over observer timing, null/old records stay unknown, and only typed allowlisted source-safe counts/IDs reach UI.
- Confirm #298/#302/#303 worker emits enough source-owned lifecycle detail through a fenced journal rather than only generic stage counters. Test triage-only, deep-only and triage→deep with browser reconnect.

**Deferred:** automatic graph checkpoint/resume and any claim that proposal equals successful action.

### #301 — One-switch deterministic triage Graph profile

**Branch / base:** feat/triage-one-switch-deterministic-profile-20261117 → #299 → #295. **Present:** triage-specific execution profile, settings/Graph entry changes and test_triage_run_mode.py.

**Integration needed**
- Merge after #299; reconcile Settings, episode, recorded_investigation, direct run_investigation, api/runs.py and state/completion with hosted RunExecutionConfig and #298 worker. Settings resolve once into typed effective values without unchecked model_copy(update=...).
- Test TRIAGE_RUN_MODE=deterministic override of conflicting individual triage knobs, TRIAGE_RUN_MODE=custom compatibility, omitted triage argument enabling triage in deterministic mode even with TRIAGE=off, and **explicit triage=False always remaining deep-only**.
- Require exactly the existing model-backed Conclude in deterministic triage; Plan/Decide/Investigate/Hypothesize/Test/Critique/Recheck do not add model decisions. Preserve original deep settings when TRIAGE_THEN_DEEP escalates; no cross-machine write permission changes.
- Ensure effective mode is accurately shown in authorized UI and persisted run/config, not falsely inferred from environment defaults.

**Deferred:** calibration of deterministic-vs-model outcomes.

### #302 — Render P0 canonical contracts and hosted model-call bridge

**Branch / base:** fix/render-p0-contract-model-bridge-20261117 → #298. **Present on branch (source inspected):** hosted model-calls adapter, source-owned model schema validation, worker publish_model_event hooks and lease-fenced repository writes; optional alias to #294 SafeStageSnapshot.

**Integration needed**
- After #297 and #298 are reconciled on main, confirm the alias actually points to **current** #294/#296 public contract; avoid treating a fallback legacy StagePayload as full parity. Validate schema disagreement fail-closed without crashing an otherwise valid run.
- Prove model.monitor/config/call/finished use the active job fence, reject stale claims, redact and bound data on write and read, keep model events out of generic SSE, and give authenticated callers correct latest-200 chronological history.
- Test missing provider key, retries/fallbacks, late/failed calls, lost lease, incomplete monitor, concurrent progress/model appends, completed run, and no access to private raw events. Ensure #300 deep lifecycle is not dropped.

**Deferred:** worker liveness/compatibility hardening (#303), Render deployment.

### #303 — Render P1 worker recovery and observability

**Branch / base:** fix/render-p1-worker-recovery-observability-20261117 → #302 → #298. **Present on branch (source inspected):** final-progress transaction changes, source-revision resolution including RENDER_GIT_COMMIT, worker heartbeat table/migration 0005, loss/recovery telemetry and structured safe diagnostics.

**Integration needed**
- Validate migration sequence 0003→0004→0005, safe downgradability and private table grants. Merge with latest #292 repository API and #297/#300 telemetry without removing existing code.
- Enforce web/worker immutable configuration **and revision** compatibility on claim; mismatch must not silently run a job under a different deterministic profile. Distinguish running, idle-but-alive, stale and unavailable worker from mere FastAPI/database readiness.
- Test terminal snapshot and final progress **in one fenced transaction**, expired lease and interrupted phase state, late stage updates, duplicate reviewer decisions, backpressure counters, heartbeat across idle/busy/restart, queue contention and sanitized error categories.
- Complete realistic two-process integration, reconnect and worker-kill tests. Maintain safe structured logs, correlation by run/job IDs and absence of prompts, keys, connection strings, ground truth and raw SQL/provider errors.

**Deferred:** production monitoring thresholds, retention policy, actual Render deployment and load/soak.

## High-conflict source ownership (check every merge)

| Shared surface | PRs involved | Integration rule |
| --- | --- | --- |
| api/runs.py and app.py | #291(main), #293, #294, #296, #297, #299, #300, #301, #298 | Preserve the current FastAPI routes and auth; one typed stage contract, separated progress/Decide/model/deep event channels; avoid duplicated watchers |
| api/run_repository.py, run_models.py, hosted_runs.py, worker/runner.py | #292, #298, #302, #303 | One private queue and migrations; active-lease fencing for *all* writes, atomic terminal outcome, no silent telemetry loss |
| frontend/src/pages/managed.tsx and frontend/src/types.ts | #293, #294, #296, #297, #299, #300, #301 | Reconcile widgets/types on merged source; preserve backend selection, phase detail, safe model calls, deterministic mode and distinct action/verification states |
| settings.py, agent/triage_decide.py, agent/investigation.py, episode.py | #295, #296, #299, #301 | Deterministic triage profile only; preserve model Conclude and unchanged deep behavior |
| .github/test_groups.py, postgres-journal.yml | #291(main), #292, #297, #298 | Union all legitimate test registrations and disposable DB groups, without removing Siemens/OEM checks |
| migrations/env.py, 0003, 0004, 0005 and tests/test_migrations.py | #292, #298, #303 | Exactly one valid Alembic upgrade path, additive private schema, no live migration during PR work |
| evaluation/inventory/*.json | ALL PRs | Regenerate ALL FOUR on every rebased final head using coverage-backed builder *before* CI eligibility |

## End-to-end acceptance for the combined stack

- **Path A — Local:** existing single-process simulator still runs triage-only, deep-only, triage→deep, authorized review, completed technical outcome, safe progress, Decide and model-call timeline without regression.
- **Path B — Hosted (not yet production):** API and independent worker on disposable TLS PostgreSQL with real queued jobs, two clients, concurrent workers, lease fencing, code revision compatibility, human approval, restarts and SIGTERM, progress + model + Decide + full deep lifecycle, terminal resync, SSE reconnect and bounded artifact retrieval.
- **Security:** roles checked at every endpoint; no direct browser DB connection; no Siemens writes; no leaked simulator truth/OT payload, prompt/provider response, raw exception, credential or database URL. Private tables/storage and retention reviewed.
- **Observability:** structured safe run/job/phase/model attempt and failure metadata, queue depth, revision mismatch, idle/active/stale worker liveness; distinguish `no telemetry` from `no calls`, and `proposal` from `execution` from `verified success`.
- **Release boundary:** merging code is **not** approval to run migrations on production, connect to Siemens, upload private OEM manuals, or deploy two Render services. Keep these as separate, explicit field/staging sign-offs.

## Maintenance rule

This is a point-in-time ledger. As a PR merges, update its row or move it to an archived section; rescan open PRs for new numbers, cross-branch changes, CI failures and genuine remaining gaps. Any newer PR that fixes an earlier gap must be identified as the owning implementation (not duplicated), then tested **on the combined final branch**. Do not call a workflow queued/pending a passing check.
