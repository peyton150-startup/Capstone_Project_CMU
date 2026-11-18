# PR #305 — source-owned hosted integration repairs from #304

**Scope:** focused integration companion stacked on **#303 → #302 → #298 → #292**. It does not replace or merge the independent source branches **#293/#294/#295/#296/#297/#299/#300/#301**. This document is an implementation and review record, **not** a staging or production acceptance certificate.

## Existing PRs cross-referenced
- **#292:** one PostgreSQL job queue with lease fencing, actor scoping, per-run ordered journal.
- **#293/#294:** server-owned `final|triage|deep` audit selection and canonical allowlisted `SafeStageSnapshot`; preserve phase IDs, requirement counts and `stream.closed`.
- **#295/#299/#301:** deterministic Plan/Decide/Hypothesize/Test control and validated one-switch effective triage profile. `RunExecutionConfig.current` in #303 reads `Settings.effective_triage` once when #301 is integrated; this PR does not duplicate its Graph logic or modify Conclude/deep behavior.
- **#296:** Decide selection trace extends the canonical `SafeStageSnapshot` with nested typed events. #302 already aliases the source-owned class when it exists, so no second unsafe sanitizer is introduced.
- **#297:** immutable `SafeModelCall`/`SafeAttempt` source models, sanitized error taxonomy and server-read validation. This PR imports the *unchanged* original file to activate #302's worker bridge, rather than rewriting a new provider client.
- **#300:** source-owned `SafeDeepSignals` projection and `deep_progress.py`. Do not invent action/verification states; the integration inventory reports unavailable until the canonical source class is present.
- **#302:** active-lease fenced `publish_model_event`/`model_events`, hosted adapter timeline; retained.
- **#303:** atomic terminal progress, idle worker heartbeat, RENDER_GIT_COMMIT/strategy mismatch and private migration 0005; retained.

## Incremental changes and triple-pass checks
Each source increment received a source/variable review, a transaction/compatibility review and a privacy/negative-case review. These are **static inspections**, distinct from executable CI.

| Increment | Pass 1 — Contract | Pass 2 — Reliability | Pass 3 — Privacy |
| --- | --- | --- | --- |
| Reuse exact #297 `api/model_calls.py` | Unchanged typed classes and `project_model_call` | Works with #302 event writer and hosted reader | Bounded model name, fixed outcome codes; no provider body |
| Generic SSE journal | SQL query excludes `model.*`; consumer also filters | Sequence cursor advances past hidden events; dedicated `model_events` remains | No model attempt/credential event exposed in public stream |
| Model-call API route | Same route and response shape as #297 | Server-owned run lookup; errors use fixed 503 | Pilot denied, bearer auth via `Access`; no raw exceptions |
| Phase audit route | Same typed `final|triage|deep` as #293 | Legacy final-only snapshots and distinct phase IDs | No arbitrary client-supplied IDs/paths; bounded UUID |
| Source-contract status | Frozen strict Pydantic `HostedIntegrationStatus`, fixed enum keys | Truthful missing/upstream states; no Graph invocation | Viewer authorization, no environment/provider/state serialization |
| Worker observability | Existing fixed event log `record`, count only | Log source mismatch count at worker startup | Never log the missing names, settings or secrets |
| Focused tests | Pure sanitizers + HTTP + DB contract | Idempotent replay with hidden model sequence, terminal cursor and phase fallback | Cross-actor denial, invalid source, provider string redaction |

## PydanticAI/Graph documentation decision
- Official [Pydantic Graph Builder](https://pydantic.dev/docs/ai/graph/builder/) documents `GraphBuilder(state_type=..., deps_type=...)`, `StepContext.state` and `graph.iter()` step events. Retain the already implemented Graph as **authoritative execution**, and validate Pydantic `BaseModel` snapshots at the API/worker boundary. No second graph or new LLM provider call is required.
- Graph iteration events alone are not durable restart checkpoints. Keep the existing *transactional* PostgreSQL journal and prevent replay after lease expiry; no restart-resume claim.
- Official [Pydantic Logfire](https://pydantic.dev/docs/ai/integrations/logfire/) explains `include_content=False` for **PydanticAI Agent** instrumentation but warns this does **not** apply to custom span metadata or HTTP body instrumentation. The project uses a custom model client, so the source-native #297 `ModelCall` projection with explicit redaction remains the safe primary observability contract. No blanket HTTP/provid­er tracing.

## Safe observability contract
- **FastAPI:** authorized run views, phase selector, model-attempt timeline and `GET /api/v1/system/integrations` as a Pydantic-validated source-compatibility inventory. `source_contracts_complete` is **not** a deployment-ready flag.
- **Worker:** original #303 fixed JSON event vocabulary with run/job correlation and code revision; `contracts_checked` reports **number** of unresolved source-owned integration contracts, not their contents; database event journal retains source-safe progress and model attempts separately.
- **Database:** `events_since` excludes model.*. Authenticated `model_events` remains actor-scoped and revalidates read-time rows. Source counts and private audit bytes stay separate from SSE.

## Required checks before merging/activating hosted mode
- Reconcile #293/#294/#296/#297/#300/#301 on the same code head; verify `source_contracts_complete = true` only when all corresponding typed source models actually exist. #305 doesn't merge those branches by itself.
- **Rebuild and commit all four evaluation inventories on final combined source**, then run the repository Ruff, format, full pytest, SNAP/evaluator integrity, frontend build/tests and disposable TLS PostgreSQL. Tests run on another PR head are not acceptance.
- Real separate FastAPI + worker staging on PostgreSQL: queue contention, source revision mismatch, model timeout/429/retry/fallback, triage-only/deep-only/triage→deep, approval expiration/double decision, SIGTERM/recovery without action replay, model/UI history, SSE reconnect and terminal ordering.
- Production Render migration, Siemens integration and private OEM content ingestion are explicitly out of scope; no deployment performed here.

**Release boundary:** The PR may be marked *ready for code review* when its focused diff and tests are reviewable; that does not certify merge-readiness or two-service production readiness.
