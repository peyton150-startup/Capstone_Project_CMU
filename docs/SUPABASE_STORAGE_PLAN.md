# Supabase storage implementation and controlled rollout

**Scope:** opt-in PostgreSQL backend for the **managed simulator** journal and its
private per-run audit artifacts. This is not a Siemens live telemetry sink, a
multi-worker scheduler, a production authorization system, or a replacement for
all file-based evaluation tooling.

## Code inventory and recommended destinations

| System | Current authoritative source | Implemented by this PR | Next bounded change |
| --- | --- | --- | --- |
| Managed simulator run state/idempotency | `api/runs.py`, SQLite `runs` | Private PostgreSQL `capstone_private.runs`; SQLite default unchanged | Move thread execution to an independent leased worker |
| Event cursor / SSE replay | SQLite `run_events` | PostgreSQL PK `(run_id, seq)` with row lock for ordered append | Outbox dispatcher / streaming worker |
| Pending human simulator decisions | SQLite `run_reviews` + process-local waiters | PostgreSQL persisted decisions, but **process-local review waiters remain** | Durable job queue and cross-instance review broker |
| Per-run investigation audits | `simulator-investigations/<uuid>.jsonl` | Bounded private `run_artifacts` BYTEA copy after completion, checksum and on-demand rehydration | Incremental durable audit stream / private object storage |
| Per-run safe operational events | `*.events.jsonl` | Same bounded artifact copy, separate `observability` type | Queryable indexed safe events, collector/worker traces |
| Accepted episodic memory | `SQLMemoryRepository`, `DATABASE_URL` | Existing `episodic_memories` PostgreSQL table can use Supabase; revised migration enables RLS | Measure retrieval scaling, migration and embeddings |
| Semantic search | Chroma and NVIDIA embeddings | **Not moved** | pgvector benchmark and explicit model/version tracking |
| Benchmarks, evals, scorecards, labels | JSONL under evaluation/run output | **Not moved** | Private immutable objects + normalized experiment/run/label metadata |
| Siemens OPC UA / MTConnect captures | Approved local v1/v2 JSONL sources | **Not moved** | Field-approved, redacted batch upload to private Storage, immutable ingest receipts |
| Controller identity, quality, timestamp lineage | Local collector/acceptance output | **Not moved** | Versioned sessions and quality-gated observation batches, per plant permissions |
| Manuals and factory documents | Local synthetic manual + authorized files | **Not moved** | Permissioned object storage with OEM rights and version-aware retrieval |

Never present absent pilot data as healthy or assume a persisted sensor value
is analysis-eligible. Siemens capture ingestion remains read-only and requires
the existing SDC acceptance requirements.

## Live project boundary

Connected Supabase account: **Capstone-CMU** (project ref
`wlkytwonwyzwjboqidem`, `us-east-2`). At review time, its public schema had
no tables. **This PR never runs a migration against the hosted project.**
The existing Render FastAPI service is a distinct deployment.

PostgreSQL is a server-side dependency. The React browser calls FastAPI, not
PostgreSQL. Do not set `VITE_DATABASE_URL`, `NEXT_PUBLIC_DATABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY` or a database password in Vercel.

## Remote journal semantics

- SQLite is still the default. Only `CAPSTONE_UI_SIM_RUNS=1` **and**
  `CAPSTONE_UI_RUN_BACKEND=postgres` opt into PostgreSQL.
- `CAPSTONE_UI_RUN_DB` remains required as an absolute path and supplies a
  private local staging directory for per-run audits; no SQLite file is used
  in remote mode. On Render use a writable directory such as
  `/tmp/capstone-ui/managed.sqlite`; this is **not durable** by itself.
- `CAPSTONE_UI_RUN_DATABASE_URL` is **required explicitly** for the remote
  journal and never falls back to the legacy `DATABASE_URL` (which may still
  point to Neon for episodic memory). This avoids silently sending journal
  data to the wrong database. The URL is server-only and redacted in config
  representations.
- SQLAlchemy's psycopg driver uses TLS `sslmode=require`, pre-ping,
  a **maximum of 4 pooled sessions**, 5-second pool timeout, and 10-second
  connection timeout. Use the Supabase **session pooler** (typically
  port 5432 with username `postgres.<project-ref>`) on Render, or a direct
  IPv6 connection if available. Port 6543 (shared transaction pooling) is
  explicitly refused: it does not preserve the run owner's session advisory
  lock. Do not weaken SSL enforcement to resolve a connection failure.
- Only one FastAPI process owns the PostgreSQL simulator run journal via a
  dedicated session advisory lock. A second process fails initialization.
  This preserves the existing in-memory approval callback and prevents
  multiple concurrent independent local episodes. Use **one worker, one
  instance** until the worker split is implemented. Rolling deployments
  with overlap may temporarily fail closed.
- A transaction-level advisory lock serializes cross-process submission.
  A partial unique index rejects more than one active run. Run row locking
  serializes event sequence allocation. Idempotency keys are unique.
- When the old owner exits, the next exclusive owner marks incomplete runs
  interrupted and pending reviews expired. **It never resumes a machine
  action or an unacknowledged approval.**
- Completion requires an atomic, checksum-labelled copy of the JSONL audit
  and sanitized operational event file into private PostgreSQL. The current
  limit is 8 MiB **per artifact**, not suitable for bulk telemetry. When
  the local file is missing on a later request, the API can restore it from
  PostgreSQL into a permission-restricted staging directory. If completion
  persistence fails, the run is not reported as successful.
- A hard process crash during an investigation can still lose the
  in-progress local JSONL; the PostgreSQL run journal remains recoverable.
  This PR does **not** guarantee in-progress audit durability.
- The journal is intentionally in the **non-Data-API**
  `capstone_private` schema, has RLS enabled without client policies, and
  revokes public/anon/authenticated access. Existing public
  `episodic_memories` is also protected by RLS. SQL writes happen only
  with a trusted server-owned database connection. Do not expose this
  schema in Supabase Data API settings.

## Migration order — no live changes in the PR

1. Review / merge this branch after CI passes. Inspect existing live service
   permissions and prepare a backup/export before any database changes.
2. In a disposable PostgreSQL database, run:
   `uv run --locked --extra database alembic upgrade head`. Confirm revision
   `0002_simulator_journal`, tables under `capstone_private`, RLS,
   `one_active_simulator_run`, and `episodic_memories`.
3. Configure Supabase's **session pooler** connection string in Render's
   protected `CAPSTONE_UI_RUN_DATABASE_URL`. Use a dedicated least-privileged
   database login if provisioned with only the necessary schema privileges.
   Do not paste credentials into code, issues, or prompts.
4. Keep managed simulator execution disabled on the public Render endpoint
   until the operator/reviewer authentication and rate limits have undergone
   production security review. Database persistence is not authorization.
5. To inspect an existing SQLite database without touching Supabase:
   `uv run --locked --extra database python -m capstone.api.import_sqlite
   --sqlite /absolute/path/to/managed.sqlite`
6. For a reviewed, explicit import into the **empty** migrated project,
   supply the secret URL in your shell environment and run
   `python -m capstone.api.import_sqlite --sqlite /absolute/path/to/managed.sqlite
   --apply --confirm-project-ref wlkytwonwyzwjboqidem`.
   Apply validates that the host or username matches that Supabase project
   and copies existing runs/events/reviews/artifacts in **one transaction**.
   Any queued/running/review state becomes interrupted/expired. The source is
   untouched, and non-empty target journals are refused to prevent merges.
7. Enable `CAPSTONE_UI_RUN_BACKEND=postgres` only after preflight checks.
   Test `/api/v1/health`, authenticated `/api/v1/lab/runs`,
   `/api/v1/lab/runs/{run_id}/events`, a real simulator-only run,
   completed audit after restart, idempotent submit, review token isolation,
   concurrent submissions, and outage recovery.
8. For the earlier episodic memories table, verify a database smoke query,
   duplicate detection and approved memory retrieval using the same
   `DATABASE_URL` (or a separate authorized DB URL for the memory service).
   It must already exist through migration `0001`.
9. Observe connection utilization, pool timeout count, event p50/p95,
   artifact size, and DB errors before permitting longer-running tests.

**Do not automatically delete the SQLite journal or call a downgrade on
production**. The PostgreSQL revision deliberately refuses destructive
downgrades.

## Storage design for the next PRs

**A. Captures and raw evidence.** Use a private Supabase Storage bucket for
immutable JSONL/Parquet batches, organized by authorization scope, plant,
machine, session epoch and UTC day. Store **object keys, checksum, source
and receive times, schema version, quality statistics, continuity/gaps,
sequence range and retention expiry** in PostgreSQL. Reconcile object upload
and metadata through an explicit committed state; never treat a partial
upload as a valid sensor sample. Upload only approved channels and redact
part-program contents or identifiers not authorized for storage. No browser
direct-write access.

**B. Investigations and evaluation.** Store a typed investigation header,
evidence references, hypothesis/diagnosis versions, decision predicates,
verification outcome, calibration/evaluator identity, and agent/model
configuration hashes separately from the immutable audit object. Keep
simulator hidden truth in evaluator-only storage. Support filtering by
run, incident, machine, time and source quality without scanning JSONL.

**C. Memory and semantic retrieval.** Keep the existing promotion gate and
SQL unique constraints. Use `pgvector` only after comparing precision/recall,
latency and cost with Chroma. Separate each tenant/plant's memory policy,
and never promote unverified pilot diagnoses.

**D. Lifecycle.** Formalize retention and deletion by data class and
customer agreement before actual machine uploads. Add periodic backup
restore tests, schema-versioned replay, idempotent ingest batches, access
audit, quotas, and an independent worker service with leases/heartbeats.
A full web/worker split must replace process-local review waiters and
session ownership; the present design is deliberately **not**
horizontally scalable.

## Sources verified for this change (November 2026)

- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits
- https://supabase.com/docs/guides/api/securing-your-api
- https://supabase.com/changelog/supabase-cli-v3
- https://render.com/articles/how-to-connect-a-render-service-to-supabase-postgres

Supabase CLI v3 (Nov 4, 2026) defaults database commands to local; explicit
`--remote` is needed for hosted Supabase work, and hosted changes ask for
confirmation. This project uses existing Alembic revisions rather than
implicitly running the Supabase CLI on a hosted database.
