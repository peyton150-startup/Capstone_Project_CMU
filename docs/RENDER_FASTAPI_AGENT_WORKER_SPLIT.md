# Render: separate FastAPI web service and agent background worker

**Status:** implementation roadmap. R1 hosted run persistence is being implemented in a separate PR; the independent worker, hosted API wiring, security gates and Render deployment are not yet complete.
**Business requirement:** deploy the Manufacturing Research Assistant to Render as **two separate compute services**: `capstone-fastapi` (Web Service) and `capstone-agent-worker` (Background Worker). Both will use managed Render Postgres. The database is a shared managed dependency, not a third compute deployment.  
**Audit baseline:** `main` at `13067ed146d9770298ba42b0e86bb664e8b1cb67`, November 16, 2026. The updated main branch includes the latest deterministic triage changes.  
**Hosting change (2026-11-18):** the FastAPI web service stays on Render, but the background worker now runs on **Northflank** (service `capstone-project-cmu`, project `capstone-cmu`), not as a Render Background Worker. The two share only PostgreSQL. What that needs:
- **Same commit on both hosts.** Each side stamps its build commit through `source_revision()` (`capstone/api/run_repository.py`): `CAPSTONE_SOURCE_REVISION`, then Render's `RENDER_GIT_COMMIT`, then Northflank's runtime `NF_DEPLOYMENT_SHA`. The worker refuses a run stamped with a different commit (`check_strategy`), and readiness reports `revision_mismatch`, so deploy both from the same `main` commit.
- **Same triage settings on both hosts.** `check_strategy` also compares every resolved triage setting, so each `TRIAGE_*` value set on Render must be set the same way on Northflank.
- **Northflank service settings.** Build context `/` (the repo root, where `pyproject.toml` and `uv.lock` are); start command `python -m capstone.worker` (the buildpack's runtime image has no `uv`); `CAPSTONE_WORKER_ENABLED=1`; and `CAPSTONE_UI_RUN_DATABASE_URL` set to the same direct or session-pooler PostgreSQL URL as the web service.
- `deploy/render-two-services.yaml` describes the original all-Render plan; its worker entry is not used.

**Boundaries:** simulator-first; no live Siemens connection, CNC actuation, physical alarm acknowledgement or pilot capture sent to Render. Existing Pydantic Graph / PydanticAI orchestration remains the agent framework; a queue is transport, not a new reasoning framework.

## Decision

Use **Postgres-backed durable jobs** initially instead of adding Redis/Celery. The repository already uses `SQLAlchemy`, `psycopg`, `DATABASE_URL` and `Alembic` for its memory database, but this **does not** mean the web run journal is already in Postgres. The current web runner is **SQLite plus threads**. Build a separate run repository and a small polling worker with transactional row claims. Scale to Render Key Value/Redis only if measurements require it.

~~~text
Browser (React + /api same-origin reverse proxy)
                 |
              HTTPS
                 v
Render WEB SERVICE: capstone-fastapi
 auth, validate, POST run, GET run, POST review, SSE
                 |
        Render internal network
                 v
Render POSTGRES
 runs / durable queue / reviews / events / artifact manifest
                 ^
        Render internal network
                 |
Render BACKGROUND WORKER: capstone-agent-worker
 claim -> Pydantic Graph -> model/tool calls -> proposed simulator action
             -> persisted human approval -> execute -> verification -> audit
                 |
       model provider API and private artifact storage
~~~

**Do not create the worker deployment from the current repository.** There is no `capstone.worker` module/command yet, and neither service can read the other's Python `threading.Event`, `self.active` set or local disk.

## Code audit — PASS ONE: trace the whole existing execution path

| Existing path / symbol | What the code does now | What moves or changes |
| --- | --- | --- |
| `capstone-code/capstone/api/app.py:create_app` | Reads `UiConfig.from_env` and instantiates `SimulatorRuns(cfg.run_db)` **inside FastAPI** when simulator runs are on. | Web injects Postgres-backed run repository/service. Do not initialize an agent in the web process. |
| `app.py:POST /api/v1/lab/runs` | Validates `RunRequest`, role and `Idempotency-Key`, calls `runner.submit`, returns 202. | Keep API contract, atomically persist + enqueue job; never execute model from HTTP handler. |
| `capstone-code/capstone/api/runs.py:RunRequest` | Typed `seed`, `kind`, `mode`, `hazards`, `tree_of_thought` and `manual`; rejects extra fields. | Preserve typed payload; store immutable sanitized effective settings/version. |
| `runs.py:SimulatorRuns.submit` | SQLite INSERT, process-local `self.active`, then `threading.Thread(target=self._execute, daemon=True)`. | Database-only enqueue plus idempotency constraint. Worker independently claims. |
| `runs.py:SimulatorRuns._execute` | Calls `model_policy_factory` and `run_episode`; keeps result, snapshots and audit/operational JSONL. | Move to independent worker entrypoint. Preserve agent semantics and instrumentation. |
| `runs.py:_await_review / decide` | SQLite records approvals, but resumption requires `self.waiters[(run_id, proposal_id)]` and `threading.Event`. | Postgres durable request and decision; worker awaits committed verdict by polling/notification. |
| `runs.py:__init__` | On startup, marks in-progress/awaiting-review rows `interrupted` and pending reviews `expired`. | Only worker ownership recovery can interrupt runs; a web restart must not touch active jobs. |
| `runs.py:_emit / events_since` | SQLite snapshot plus event journal with a cursor and recent event list. | Postgres atomic snapshot/transition/event with per-run monotonic sequence and retention. |
| `app.py:/events` | SSE via `StreamingResponse`, `since`, `Last-Event-ID`, keepalives, terminal close. | Keep public wire contract, query shared events; reconnect across API instances. |
| `capstone-code/capstone/episode.py:run_episode` | Creates synthetic CNC world and `ApprovalDesk`; injects human `approver` callback, `watch` and event log; Pydantic Graph performs triage/deep steps and verification. | Keep inside worker; inject durable callback/sinks. Simulator truth stays worker-side. |
| `capstone-code/capstone/experiment.py:model_policy_factory` | Creates provider/model-backed policy from settings. | Worker-only; no model keys in public API. |
| `capstone-code/capstone/settings.py` | Has `TRIAGE_PLAN`, `TRIAGE_INVESTIGATE`, `TRIAGE_MODEL` and model routing. Deterministic investigation **requires** a fixed plan. PR #285 adds the opt-in `TRIAGE_HYPOTHESIZE=deterministic` setting. | Preserve settings validator; snapshot mode/config, including the hypothesis strategy, to explain observed behavior. |
| `capstone-code/capstone/database/connection.py`, `migrations/` | Existing Postgres connectivity + Alembic for episodic memory. | Add independent run tables and migration. `DATABASE_URL` does NOT currently replace `CAPSTONE_UI_RUN_DB`. |
| `frontend/src/pages/managed.tsx` | React posts runs/reviews, GETs runs, streams with authenticated `fetch`. | Preserve URLs, run IDs, response names; use a production same-origin `/api` reverse proxy. |
| `capstone-code/capstone/api/__main__.py` | Starts Uvicorn bound to localhost (`127.0.0.1:8000`). | Render web starts ASGI on `0.0.0.0:$PORT`, not the current localhost launcher. |

Current supported HTTP paths to preserve (simulator only):

- `POST /api/v1/lab/runs` (202; operator; `Idempotency-Key` of 16–96 allowed characters; identical request/key returns prior run, conflicting body/key 409).
- `GET /api/v1/lab/runs`, `GET /api/v1/lab/runs/{run_id}` and `/investigation`, `/triage`, `/observability`.
- `GET /api/v1/lab/runs/{run_id}/events`: numeric event IDs, `since` and `Last-Event-ID` cursor reconnect.
- `GET /api/v1/simulator/reviews`; `POST /api/v1/simulator/reviews/{run_id}`: approve/reject once, with review tied to an exact proposal.
- `GET /api/v1/health` liveness; add a different DB-aware `/api/v1/ready` readiness route before production.

## Code audit — PASS TWO: test evidence, hazards, negative cases

Reviewed actual bodies of `runs.py:submit`, `_await_review`, `decide`, `_execute`, `episode.py:run_episode`, `app.py` auth/SSE handlers, `settings.py`, database/migration paths, `tests/test_web_runs.py` and `tests/test_web_api.py`. The merged deterministic triage update on main does **not** remove the web thread/approval split problem.

1. **Cross-process review is broken today.** `self.waiters` stores process-local `threading.Event`. `decide` rejects a pending review if there is no corresponding local waiter. Two independent services cannot approve a run using this implementation.
2. **Web restarts currently cancel active work.** `SimulatorRuns.__init__` updates `queued`/`running`/`awaiting_review` to `interrupted` and expires reviews. Under the target system, web restarts only reconnect readers; a worker lease controls run recovery.
3. **Concurrency relies on one process.** `self.active` is not a distributed lock. Two web instances or a web and worker deployment could duplicate execution without an atomic database claim.
4. **Local JSONL cannot be shared.** `investigation_audit_path` and `investigation_event_path` write under the SQLite DB parent. Render disks belong to one service, so no worker-to-web shared mount; replace with private approved object storage and safe Postgres projections/manifest. Never claim a complete audit if storage failed.
5. **Authentication is local-first.** In `api/app.py`, `authorize` returns if `cfg.token is absent`; when enabled, multiple role tokens can pass generic reads, including pending reviews. Hosted API must fail closed, restrict run/review/SSE by role and actor, and hide pilot data. `/events` **already uses** the `Access` dependency; retain it, tighten access and actor ownership.
6. **Browser CORS is loopback-only and GET-only.** Current `allow_origins` are localhost and `allow_methods=["GET"]`. Browser POST and `Idempotency-Key` need approved CORS/preflight or, preferably, a same-origin reverse proxy.
7. **Test coverage is mainly in-process.** `test_run_roles_and_idempotency`, `test_durable_pending_approval_and_double_decision`, `test_review_decision_is_durable_before_episode_resumes`, `test_restart_interruption_and_private_token_validation` and `test_sse_reconnect_resumes_from_last_event_id` patch `SimulatorRuns._execute`. They do **not** establish process-separated web-to-worker behavior.
8. **Event ordering and secrecy matter.** `_emit` keeps a snapshot/event transaction; preserve this atomically and fence stale workers. `EventLogger` and `safe_stage` limit operational fields; exclude prompts, provider error messages, keys, hidden simulator truth, private audit content and real pilot telemetry from API and logs.
9. **Deterministic triage is not a wholly deterministic LLM-free episode.** `TRIAGE_PLAN=fixed` and `TRIAGE_INVESTIGATE=deterministic` gate the deterministic plan/decide path. PR #285 adds optional `TRIAGE_HYPOTHESIZE=deterministic`, which compiles unscored, evidence-linked candidates without a model call; the default/model Hypothesize and Conclude remain model-backed. The worker must preserve these distinct modes, their conservative no-action behavior, and evaluation settings.
10. **Every restart/timeout is a safety event.** Render `SIGTERM` and an expired lease must not silently rerun a possibly approved simulator action or mark an interrupted run as verified. No automatic retry of a started episode without separate idempotent checkpoint design.

### Existing tests that must remain valid

`tests/test_web_runs.py` currently covers role/idempotency behavior; durable-before-wake approval ordering; double review 409; interruption after local restart; safe operational event projection; SSE cursor replay. `tests/test_web_api.py` covers private signal/audit and pilot separation. Keep these as contract tests but add real two-process tests below. The CI inventory and SNAP evaluation gates stay enabled.

## Target Postgres contract and work flow

Use typed SQLAlchemy models + a new Alembic revision (do not modify the existing episodic memory migration). The tables below are **proposed**, not present:

| Table | Minimum columns / keys | Owner |
| --- | --- | --- |
| `sim_runs` | `run_id UUID PK`, `actor_id`, `idempotency_key`, `request_hash`, `request JSONB`, `effective_config JSONB`, `state`, `snapshot JSONB`, `version`, `created_at`, `updated_at`; unique (`actor_id`, `idempotency_key`) | API writes on submit; worker writes state |
| `sim_jobs` | `job_id UUID PK`, `run_id UNIQUE FK`, `status`, `enqueued_at`, `priority`, `lease_owner`, `lease_token`, `lease_until`, `heartbeat_at`, `attempt` | Worker owns claim/heartbeat |
| `sim_run_reviews` | (`run_id`, `proposal_id`) PK; safe proposal, `pending/approve/reject/expired`, `decision_actor`, `decision_at`, `deadline_at`, version | Worker requests; reviewer API commits |
| `sim_run_events` | (`run_id`, `seq`) unique, `event_name`, bounded safe `payload JSONB`, timestamp | API and worker append atomic transitions |
| `sim_run_artifacts` | `artifact_id`, `run_id`, kind, private `storage_key`, content hash, byte count, retention, visibility | Worker uploads, API projects authorized summary |

### Claim algorithm and state discipline

~~~sql
BEGIN;
SELECT job_id, run_id
FROM sim_jobs
WHERE status = 'queued'
ORDER BY priority DESC, enqueued_at, job_id
FOR UPDATE SKIP LOCKED
LIMIT 1;
-- On selected row: set status='claimed', owner, unique fencing token,
-- attempt, lease_until; atomically transition the run and append event.
COMMIT;
~~~

- Short transactions only. Do not hold SQL locks during model calls, tool reads, human wait or artifact uploads.
- Single worker concurrency initially (`1`); claim/poll interval around `1–2 seconds`. Heartbeat around `10 seconds` and lease around `60 seconds` as **starting hypotheses**, validated with real latency tests. Every stage completion/write must check the current `lease_token` to prevent a stale worker from overwriting state.
- State machine: `queued -> running -> awaiting_review -> running -> completed/failed`, plus explicit `interrupted` and `expired` states. Terminal state cannot regress.
- Submissions commit run+job in one transaction. Concurrency and duplicate-key collisions: same actor/key/request hash returns same run; same key with different request is 409. No double enqueue.
- Persist a safe `review.requested` event and proposal **before** waiting. Review API commits verdict (or rejects a second/late verdict) **before** the worker observes it. Worker polls durable review row using the same proposal identity, bounded timeout (~240 seconds existing default), and independently renews its lease.
- Recovery: untouched queued jobs may be claimed again. If a worker stops after entering `running`/`awaiting_review`, mark `interrupted`, expire approval, record reason; an operator can explicitly create a new run. **Do not blindly retry a started graph or a previously approved action.** True resumability requires future checkpoint and side-effect idempotency work.
- Emit event+state snapshot atomically with monotonically increasing per-run sequences. SSE must preserve `since`/`Last-Event-ID`, reconnection, bounded retention and a resync signal if old events are unavailable.
- Worker writes audit/diagnostic artifacts to approved private storage; DB stores manifest/hash and only safe projections. No disk shared between services. Guard against partially uploaded or unverified artifacts.

## Modules and implementation PR sequence

Use small reviewable PRs. These paths name **new files to implement**, not files already in the repository.

| PR | Change | Required acceptance |
| --- | --- | --- |
| **R1 — Postgres run persistence** | New `capstone/api/run_repository.py` (or dedicated package), SQLAlchemy models, run/event/review/job migration, typed configs, DB-backed idempotency, state/event atomicity. | Concurrent duplicate request -> one run; 409 mismatch; migrations forward/back; no missing audit or leaked data. |
| **R2 — agent worker extraction** | Implement `capstone/worker/__main__.py` and `runner.py` to claim jobs and call existing `model_policy_factory` / `run_episode`. No agent import/execution in API. | API and worker run as separate OS processes; genuine triage and deep model-fixture runs; web restart does not kill work. |
| **R3 — persistent approvals and progress** | Implement worker `approver` adapter, durable `watch`/event recorder, approval timeout/fencing, DB-backed SSE. | Review committed before worker resume, double-decision 409, disconnected clients replay correctly, worker restart does not auto-replay action. |
| **R4 — security, artifact and recovery gates** | Hosted fail-closed auth, actor-scoped reads/reviews/SSE, safe object storage, sanitized telemetry, SIGTERM and lease recovery, API readiness, rate limits, browser proxy/CORS. | Unauthenticated and wrong-role requests denied; no pilot routes/actions; no local-disk or process-memory dependency; crash injection tests. |
| **R5 — real Render deployment** | Add reviewed `render.yaml`, typed env config, controlled Alembic pre-deploy migration, two service startup commands, monitoring, staging runbook. | Current-head CI+SNAP green, staging cross-process E2E passed, rollback practiced; only then deploy two services. |

Keep Pydantic Graph / PydanticAI for the reasoning pipeline. Postgres leasing supplies job delivery and lifecycle; it is **not** a replacement agent framework.

## Render fields verified in current documentation

These are **future deployment settings**. Web may currently serve local-only API experiments, but no independent worker can be deployed until R1–R4 exist.

| Dashboard field | Web Service | Background Worker |
| --- | --- | --- |
| Name | `capstone-fastapi` | `capstone-agent-worker` |
| Service type | **Web Service** | **Background Worker** |
| Repository / branch | `peyton150-startup/Capstone_Project_CMU`, `main` | same |
| Runtime | `Python 3` | `Python 3` |
| Region | **Virginia** | **Virginia**, same as Postgres |
| Root Directory | **Blank**: `pyproject.toml` / `uv.lock` at repo root | Blank |
| Plan | Initial **Standard** (`1c-2g`), benchmark later | Initial Standard (`1c-2g`) |
| Build Command | `uv sync --locked --all-extras --no-dev && uv pip install --python .venv/bin/python -r frontend/requirements-api.txt` | `uv sync --locked --all-extras --no-dev` |
| Start Command | `uv run --no-sync uvicorn capstone.api.app:app --host 0.0.0.0 --port $PORT --workers 1` | **Proposed only:** `uv run --no-sync python -m capstone.worker` |
| Auto Deploy | **After CI Checks Pass** | same |
| Health Check Path | `/api/v1/health` now; add `/api/v1/ready` DB/schema-aware | **None**: worker is portless |
| Disk | None once Postgres/artifacts are real | None; **never** assume shared disk |
| Pre-Deploy | Run new Alembic migrations once via coordinated release path | Blank; don't race migrations |
| Replicas | 1 initially; independent scaling after hardening | 1 initially; DB claims protect overlap |

Render's documented Blueprint equivalents: `type: web` / `type: worker`, `runtime: python`, `region: virginia`, `plan: 1c-2g`, `autoDeployTrigger: checksPass`, `healthCheckPath` (web only), `envVars`, and `fromDatabase: {name: capstone-runs, property: connectionString}`. **Do not add an active render.yaml in this docs PR:** it could be deployed prematurely with a nonexistent worker entrypoint.

Create Render Postgres in **Virginia**, use the **internal** `DATABASE_URL` for both services, and arrange a single controlled migration operation. Render's pre-deploy command runs on a separate compute environment and cannot access a disk. A separate worker receives no public incoming network traffic. An attached disk cannot be shared across services and disables zero-downtime deploys.

### Environment ownership and existing-versus-future settings

| Variable | Web | Worker | Status |
| --- | --- | --- | --- |
| `PYTHON_VERSION=3.14.7`, `UV_VERSION=0.13.0` | yes | yes | Current repo / CI pins; Render supports both |
| `DATABASE_URL` | yes | yes | Existing for memory, **new run tables required** |
| `NVIDIA_API_KEY` / approved provider keys | **no** | yes | Worker only; secrets never to browser |
| `DEFAULT_MODEL`, `TRIAGE_MODEL`, `TRIAGE_PLAN`, `TRIAGE_INVESTIGATE`, and (after PR #285) `TRIAGE_HYPOTHESIZE` | only safe resolved mode metadata | yes | Fixed plan required for deterministic investigate; preserve optional deterministic hypothesis mode |
| `CAPSTONE_UI_TOKEN` | yes; replace with stronger hosted identity | no | Existing read token, mandatory when hosted |
| `CAPSTONE_UI_RUN_TOKEN` / `CAPSTONE_UI_REVIEW_TOKEN` | distinct role secrets | no | Existing role settings, adapt to actor scoping |
| `CAPSTONE_UI_EVALUATOR_TOKEN` | only if evaluator enabled | no | Distinct evaluator role |
| `CAPSTONE_UI_SIM_RUNS` | opt-in after R1–R4 | no | Existing enabled path **requires local `CAPSTONE_UI_RUN_DB`**; update config validation first |
| `CAPSTONE_UI_RUN_DB` | remove on PG migration | not used | Existing SQLite filename, not shared storage |
| `CAPSTONE_UI_CAPTURE`, `CAPSTONE_UI_MTCONNECT`, `CAPSTONE_UI_CAPTURE_AUDIT` | **unset** | **unset** | Local Siemens/MTConnect pilot data must not enter cloud simulator |
| `RUN_BACKEND=postgres` | proposed | proposed | **Not implemented**; don't set until config supports it |
| `RUN_WORKER_CONCURRENCY=1`, `RUN_LEASE_SECONDS=60` | no | proposed | **Not implemented** |
| `ARTIFACT_STORE_*` | only restricted read capability | approved write capability | **Not implemented** |

Current `api/__main__.py` binds `127.0.0.1`; Render Web Services must bind `0.0.0.0` and the Render-provided `PORT`. Web should not carry provider API keys; worker should not carry private API session tokens. Ensure `CAPSTONE_UI_SIM_RUNS`/`CAPSTONE_UI_RUN_DB` validation is refactored in R1 so the new Postgres service starts without a local SQLite file.

## Failure-mode and observability requirements

- **SIGTERM / deploy:** stop claiming, finish or interrupt safely, preserve lease fencing. Render's normal shutdown grace is 30s; tuning a longer delay (up to platform limits) does not make a long agent resumable.
- **Lost DB:** reject submissions with 503, never launch in-process fallback; worker cannot claim or report success without persistence.
- **Provider failure:** preserve model retry/fallback and timeout budgets; log only safe class, timing, and routing metadata, not prompt/error body.
- **Reviewer offline:** durable pending review with deadline, explicit expired state; no action without matching committed approval.
- **Duplicate/reordered events:** conditional state version and seq, cursor gap handling; no state regression after terminal status.
- **Worker overlap:** fencing token prevents stale worker committing; expired active run requires controlled interruption, not silent replay.
- **Artifact failure:** mark audit unavailable/incomplete; don't present a verified outcome absent required durable evidence.
- **Alerts:** queue age, worker heartbeat age, run stage age, lease expirations, approval age, drop counts, SIGTERM count, provider timeouts/429, DB failures. Correlate by run ID without secrets or pilot data.
- **Data quality:** missing/uncertain Siemens data is never labeled healthy; this cloud split is simulator-only and must not imply pilot field validation.

## Validation and merge gates for R5

1. API and worker launch in **separate processes/containers** with shared Postgres; API accepts 202 and never calls `run_episode`.
2. Start real simulated triage and deep runs with model fixtures and assert stage trace, deterministic decision where configured, hypothesis, conclusion and verification.
3. Concurrent same-key submissions -> one job; conflicting payload -> 409. Parallel workers -> one claim. Stale claim cannot overwrite later result.
4. Independent browser/API reviewer can approve and reject while worker waits; late/duplicate approval -> 409; no simulator action before approval.
5. Restart **web** mid-run and mid-review: work continues. Crash **worker** at claim, model call, review, action and verification: safe interruption, no duplicated action or fictional completion.
6. SSE reconnect after web restart restores ordered events and final state, with bounded retention and no disclosure of private fields.
7. User/role authorization for every read, SSE, reviews and submit; CORS/proxy integration; pilot requests fail closed.
8. Shared artifact failure injection and Postgres outages; no local JSONL or SQLite dependency across services.
9. Render staging: two compute services + Postgres same region; smoke readiness, one controlled migration, health/queue observability, secure environment secrets, rollback.
10. Existing `.github/workflows/ci.yml` tests, Ruff, full coverage/inventory and SNAP evaluation must pass; **never** disable the evaluator integrity gate to make deployment green.

## Rollout and rollback

**Stage A:** Keep local single-process implementation while R1–R4 land behind opt-in defaults.  
**Stage B:** Exercise local web+worker+Postgres integration; no pilot capture, no physical actuation.  
**Stage C:** Create Render Postgres, apply migrations once, start worker, then start web with production role boundaries and reverse proxy.  
**Stage D:** Test end-to-end approvals, logs, restart/failure injection, model routing, replay and staging rollback before exposing any public user access.  
**Rollback:** stop new submissions, drain or explicitly interrupt current jobs, keep schema backward compatible during service rollback, expire abandoned reviews; never silently retry a completed or previously approved action.

## Current Render documentation checked

- https://render.com/docs/deploy-fastapi — web service Python, build and Uvicorn launch.
- https://render.com/docs/background-workers — continuously running worker without incoming network traffic.
- https://render.com/docs/blueprint-spec — actual `web`/`worker`, `python`, `virginia`, `1c-2g` and `checksPass` fields, env references and health checks.
- https://render.com/docs/python-version — `PYTHON_VERSION` and `.python-version`.
- https://render.com/docs/uv-version — `UV_VERSION`; repo-root `uv.lock`.
- https://render.com/docs/deploys — CI-gated deploys, pre-deploy command, shutdown/replacement behavior.
- https://render.com/docs/disks — ephemeral filesystem, one-service disks, no shared mount.
- https://render.com/docs/key-value — later optional Redis-compatible queue, not required for initial two-compute-service plan.

### Documentation PR checklist

- [x] First pass: traced current FastAPI -> SQLite/thread -> `run_episode` -> approval -> verification -> local journals.
- [x] Second pass: re-read method bodies/tests and the newer main triage merge; addressed auth, concurrent claims, crash recovery, event ordering, artifacts and Render requirements.
- [x] Exact future service settings, existing versus proposed environment variables, PR implementation sequence and acceptance gates.
- [ ] No new code or infrastructure is implemented by this documentation PR.
- [ ] Leave this PR open for review; implementation requires R1–R5 before two Render deployments are ready.
