# Render dual-service execution and observability — PR #298

**Status:** Draft implementation, stacked on open PR #292. No production Render changes. Build ungated; developer understanding **not verified**. Do not merge/deploy before the listed acceptance gates. Initial audit 2026-11-17.

## Decision and explicit boundaries

- Deploy two independent **compute** processes: existing Render **Web Service** `Capstone_Project_CMU` and portless Render **Background Worker** `capstone-agent-worker`. Shared PostgreSQL is a managed storage dependency, not another web/worker process.
- The API validates authorization, idempotency, simulator-vs-pilot scope, reads authorized safe results and SSE events, and persists submissions. It **never** calls an LLM, builds a simulator, owns a run thread or waits in process for a human approval.
- The worker polls the R1 `RunRepository`, claims exactly one queued job with `FOR UPDATE SKIP LOCKED`, renews a fenced lease while model calls block, invokes the **existing Pydantic Graph** through `run_episode`, waits for durable human review, stores private completed audit/operational JSONL in PostgreSQL and transitions to terminal exactly once. A claim that loses its lease is **not retried**.
- Local SQLite/in-process modes remain operational for local development; opt-in `CAPSTONE_UI_RUN_BACKEND=hosted` selects this split. Only synthetic simulator episodes are accepted. No Siemens CNC connection, write/acknowledge, or production telemetry collection is provided.
- One tenant per deployment for now: the three distinct API role tokens identify viewer/operator/reviewer for the fixed server-owned `hosted-simulator` principal. This is **not** multi-tenant SSO, per-human identity or RBAC. A later identity provider requires a separate actor migration.

## Prior PR and code audits

1. **#292** (open, foundation): introduces five `capstone_private.sim_*` tables, atomic enqueue + idempotency, durable monotonic events, claims/leases and expired-claim interruption. The legacy `PostgresSimulatorRuns` is still a single owner using local Python threads and `threading.Event`.
2. **#293/#294** (open): persist triage and deep safe stage snapshots, completed audits and full requirement-level live progress. This PR mirrors **all 55 named safe progress fields** from #294 with strict Pydantic validation and omitted-key semantics; it does not duplicate the #293 React frontend. The actual #293/#294 branch must be reconciled at merge.
3. **#297** (open): model/provider `ModelCall`/`Attempt` chronology with strict promptless projections, built on #294's existing journal. **Not yet connected to the new R1 queue.** Rebase and add claim-fenced `model.call`, `model.config` and `model.monitor` once that branch is available. Do not claim that model-call history is complete before that gate.
4. **#295/#296** (open): deterministic triage defaults and Decide telemetry must be preserved as code is merged; #298 does not replace the triage reasoning/control implementation.

### What each new module does

| Module | Responsibility | Trusted inputs / outputs |
| --- | --- | --- |
| `api/run_repository.py` | R1 queue plus fenced `StagePayload`, progress/reviews/resync/private audit mutations | Worker lease and typed safe contracts in; actor-scoped progress/review/results out |
| `api/run_models.py`, migration `0004_worker_artifacts` | Add bounded private `BYTEA` artifact storage without deleting R1 tables | Server-owned bytes only; no browser binary response |
| `api/hosted_runs.py` | Compatibility facade for managed API routes with **no agent import** | Authenticated fixed actor, repository reads, strict server-side safe audit/operational projection |
| `api/config.py`, `api/app.py` | Explicit hosted config, fail-closed role tokens and DB schema, HTTPS browser allowlist, readiness, replay and audit projection | `/api/v1/ready`; existing managed routes and SSE |
| `worker/runner.py`, `worker/__main__.py` | Independent portless process, poll/claim/heartbeat, Pydantic Graph episode, durable review, journal/progress/logging | DB queue and provider secrets; no inbound web traffic |
| `deploy/render-two-services.yaml` | Review-only Blueprint for Render web + worker, no auto-deploy | Requires separate manual secret/DB setup |

## Worker lifecycle (one run)

1. FastAPI accepts a simulator run from the **operator** role with idempotency key. `RunRepository.submit` atomically commits run, job and safe `run.queued` event. HTTP returns `202` without calling models.
2. Worker claims job with new lease token; `run.started` and running snapshot are durable. Web app restart cannot revoke the claim or mutate run state.
3. A heartbeat thread renews the 60-second lease every 10 seconds during potentially 45+ second model I/O. A sticky loss flag prevents future approval and final writes; every DB mutation additionally fences the lease token.
4. Pydantic Graph stage watcher projects into a strict Pydantic `StagePayload`, queues no more than 128 updates and persists approved, typed `stage.updated` events and phase-specific snapshots. Zero raw Graph serialization.
5. Before acting on a simulator proposal, worker commits an exact bounded `review.requested` record. Authorized reviewer API commits approve/reject atomically; a second or late verdict returns 409. Worker polls Postgres and rechecks lease immediately before handing back simulator approval.
6. Worker stores the full private audit and private operational trace in the restricted database; the server-side reader hashes and projects them through pre-existing safe readers. Both bounded to 8 MiB; no cross-service filesystem.
7. Worker reconciles final Graph state, emits a bounded `resync.required` event if live updates were dropped, and atomically commits a safe terminal snapshot/event. Previously persisted triage/deep progress remains in the final run snapshot. No fabricated verification.
8. If worker crashes or loses authority, `recover_expired` marks started job **interrupted**, expires pending review, and refuses automatic action replay. An operator must submit a new run explicitly after investigating uncertainty.

## Structured logging, metrics and signal provenance

**No raw exception string or provider HTTP body ever becomes a log field.** Only fixed event names, run/job UUIDs and bounded numeric fields are emitted. Application traces are separate from browser-facing safe run events and private audit content.

| Event / diagnostic | Producer | Persistence / visibility |
| --- | --- | --- |
| `run_submitted` | FastAPI | Render stdout JSON; run UUID, no request payload |
| `claimed`, `ready`, `finished`, `failed` | Worker | Render stdout JSON; run/job UUID, queue wait / attempt / duration when known |
| `lease_lost`, `poll_failed`, `recovered` | Worker | Render stdout JSON; loss/recovery counts without exception messages |
| Queue depth, active/stale claims, backlog age and last heartbeat age | API repository/system | Authenticated aggregate counts, no lease owner/token; idle worker explicitly **unverified** |
| `review_requested`, `review_decided` | Worker + repository | Operational stdout and durable ordered journal; actual verdict is distinct from simulator execution |
| `stage.updated`, `resync.required` | Graph watcher + repository | Durable source-filtered event sequence, strict field-level typed snapshot |
| Private audit + operational JSONL | Worker | Hash-verified restricted `BYTEA`; bounded and never raw-returned |
| Provider attempts, tokens, fallback, retries | Existing PR #297 | **Integration pending** into fenced hosted journal and model-calls endpoint |

**Observability acceptance questions:** Is the API ready? Is DB schema current? Was the job claimed? How long was it queued? Who owns the current lease? Is heartbeating healthy? Which deterministic Plan/Decide/Test stage and requirement is pending? Did an authorized reviewer approve the exact proposal? Were final audit and verification persisted? Did the client miss an event? Did provider calls actually occur? The last item is explicitly **unverified** until #297 is wired.

Logs/metrics must not carry `DATABASE_URL`, API tokens, prompts, model completions, tool arguments, raw sensor values, Siemens recordings, simulator ground truth, stack traces with secrets or unredacted SQL errors. Never enable generic request/response body tracing on these routes.

## PydanticAI/Graph decision

- The project's existing `GraphBuilder` workflow and `InvestigationState` stay authoritative. Pydantic v2 `BaseModel` + `ConfigDict(extra="forbid")` handle the web/worker schema boundary; reusing `safe_stage` makes the implementation smaller and testable.
- Pydantic Graph V2 **does not snapshot graph state automatically** ([official graph docs](https://pydantic.dev/docs/ai/graph/builder/)). Do not substitute Graph persistence for the R1 SQL journal or promise automatic resume after a crashed run.
- The project uses a custom model policy/client, so `logfire.instrument_pydantic_ai()` alone does not automatically capture its provider calls. PR #297's explicit, sanitized `ModelCall`/`Attempt` projection remains the correct place to integrate model metadata.
- Future optional OpenTelemetry/Logfire tracing requires an allowlisted metadata-only span design; its `include_content=False` option is documented for **PydanticAI Agent** spans ([Logfire docs](https://pydantic.dev/docs/ai/integrations/logfire/)), and does not by itself protect custom clients or every transport header. No generic auto-instrumentation is enabled by this patch.

## Safe configuration and staged Render rollout

The submitted `deploy/render-two-services.yaml` is intentionally **not** at the special `render.yaml` path. Both services set `autoDeployTrigger: 'off'`. It does not create/modify any Render service. A read-only Render workspace check confirmed existing `Capstone_Project_CMU` (web, `main`, Virginia) and **no capstone background worker**; the Blueprint adopts the existing web service name rather than provisioning a redundant web service. Reviewed Render [Blueprint reference](https://render.com/docs/blueprint-spec) and [background worker instructions](https://render.com/docs/background-workers).

**Release order:** merge #292 once green; reconcile #293/#294/#295/#296/#297 into a tested staging integration branch; rebase #298 and resolve both sets of same-file edits; perform one controlled `uv run --no-sync alembic upgrade head` on authorized staging PostgreSQL; provision matching private `CAPSTONE_UI_RUN_DATABASE_URL` values; set distinct 24+ character viewer/operator/reviewer credentials only on web; provider keys only on worker; deploy worker and web from the **same immutable SHA** to the same region; verify `/api/v1/ready` and the complete end-to-end acceptance. Keep pilot/physical machine integrations disabled.

**Required acceptance:** web restart during worker model wait, simultaneous API submissions and worker claims, idempotent duplicate 202 versus conflict 409, wrong-role review denial, double approval 409, approval-after-expiry rejection, missing provider key, model timeout/fallback, triage-only and triage-to-deep, long running heartbeat, worker SIGTERM and stale worker fencing, interrupted no-replay, safe audit and hash mismatch rejection, browser SSE disconnect/reconnect with cursor replay and `stream.closed`, dropped-update resync, private artifact bounds, source-matched frontend #294 counts, model-call timeline #297, schema migration downgrade protections, full Ruff/pytest/CI+SNAP and real Render/Vercel staging smoke. **None of these runtime/live gates is claimed complete merely because its test exists.**

**Rollback:** disable new run submission first, drain completed jobs, back up hosted private tables, revert both services to the previous known-good app code without changing old state; never downgrade 0004 while it holds private audit content. Avoid re-enqueuing interrupted/approved run IDs.

## Triple-pass review record and limits

Every small source change is reviewed against three distinct concerns: **(1)** precise input/output types and old API contracts; **(2)** atomicity, fencing, ordering, cancellation/restart and error recovery; **(3)** roles, privacy, hidden-truth and injection/secret leakage. Focused tests and GitHub CI still determine whether those review findings hold at runtime. Static reviews are **not** a substitute for full-suite and real two-process acceptance.

Known incomplete work: #297 provider-call journal integration; #293/#294's updated progress and final-results frontend compatibility requires cross-branch rebase; multi-actor SSO is not implemented; storage retention and service-level metrics exporters require operational approval; no live Render service or Siemens integration has been touched. Keep PR #298 **draft and unmerged**.
