# Neon manual knowledge storage: audit, rollout and boundaries

**Status:** Implemented as opt-in application code and migration; **not deployed**.
Neon holds versioned manuals and the already-existing episodic-memory SQL table.
Supabase PR #289 independently handles simulator journal persistence. Neither
database is changed by this PR. No OEM/Siemens manual is uploaded or claimed.

## Endpoint and data flow map (main as of 2026-11-17)

| Caller | API / function | Storage | Boundary |
| --- | --- | --- | --- |
| React dashboard | GET /api/v1/knowledge/manuals?workspace=simulator&q=... | Local synthetic Markdown by default; Neon if explicitly enabled | Bearer token; pilot rejected |
| React dashboard | GET /api/v1/knowledge/memories?workspace=simulator | SQLMemoryRepository via DATABASE_URL | Memory read flag and simulator-only access |
| Agent investigate/plan | ManualProvider.search_manual -> experiment.open_manual | Chroma/keyword by default; opt-in Neon (published SIM-CNC-001) | Manual is guidance, never an observation |
| Agent recall | RecallingProvider -> MemoryService -> SQLMemoryRepository | DATABASE_URL (Neon supported) | Only promoted verified/failed lessons; not evaluator truth |
| Simulator API | POST /api/v1/lab/runs -> SimulatorRuns._execute -> run_episode | SQLite, plus PR #289 opt-in Supabase journal | Role checks; in-process worker, no pilot actions |
| Simulator API | GET /api/v1/lab/runs/{id}/events | SQLite/Supabase journal | Cursor replay; authenticated |
| Siemens/MTConnect | On-site collectors -> JSONL | Local disk, not Neon | SDC checks; **no cloud ingestion yet** |
| Read API | GET /api/v1/recordings/... | Allowlisted local capture JSONL | Read-only; file may be missing on Render |
| Vercel frontend | /api/* reverse proxy | Render FastAPI | No DB credentials in browser |
| Future pilot manuals | Approved OEM PDF -> private Supabase Storage -> authorized text/chunks | Neon knowledge tables, future controlled import | No OEM rights assumed; must validate machine/controller |

## Neon schema

The separate migration **migrations/neon/0001_manual_knowledge.sql** provides:
- private schema, documents with one published revision per document;
- revision-addressed numbered sections with full text and exact 2048-dimension
  NVIDIA embeddings; GIN full-text index and exact vector similarity search;
- source checksum, optional private Supabase object key and approval reference;
- no browser/Data API grants. Pilot rows require an approval reference, but
  **no pilot importer or reader is permitted by this PR**.

No HNSW index: pgvector's ordinary vector HNSW index caps at 2,000 dimensions
and the current NVIDIA Nemotron model emits 2,048. Exact vector retrieval on a
small/manual-scoped corpus is adequate; benchmark halfvec/ANN in a separate PR
if retrieval latency calls for it. Model name and document revision are
enforced during retrieval; no mixing embeddings from different models.

## Controlled rollout (no live changes automatically)

1. Review/merge after CI and evidence review. Back up the Neon DB. Confirm
   the existing production branch and current memory table are not modified.
2. Review the SQL. Apply **once** to Neon via an authenticated PostgreSQL
   session with TLS; do not point shared Alembic at this file or Supabase.
3. Set server-only NEON_KNOWLEDGE_DATABASE_URL with psycopg Postgres URL and
   sslmode=require or verify-full. Prefer a limited, nonbrowser Postgres role.
   This URL is required explicitly even if DATABASE_URL already points Neon.
4. Preview: python -m capstone.manual.neon
5. Seed the synthetic SIM-CNC-001 only, explicitly:
   python -m capstone.manual.neon --apply
   The seed requires an NVIDIA key and compatible 2048-dimensional model.
   For offline keyword-only seed, use --apply --keyword-only.
   Repeated seed of the identical revision is a no-op; edits to an existing
   revision fail until the revision is bumped. Old versions remain stored.
6. Opt in to agent retrieval with --manual neon (simulator only). It keeps the
   same ManualProvider tool, bounded searches and provenance guardrails.
7. For the simulator dashboard, separately set CAPSTONE_UI_NEON_MANUAL=1,
   and CAPSTONE_UI_TOKEN (24+ characters). This routes the existing manuals
   GET endpoint to Neon and permits simulator manual="neon" run requests.
   It does not grant pilot/OEM manual retrieval.
8. Verify document_id, revision and section citations, keyword/semantic hits,
   model-outage keyword degradation, DB-outage 503, denied pilot access, and
   memory retrieval. Disable the opt-in flag for rollback; local Markdown,
   Chroma and the SQL memory table remain unchanged.

Security: do not expose either DATABASE_URL or NEON_KNOWLEDGE_DATABASE_URL
in React/Vercel or API responses/logs. Configure backup/restore tests, role
privileges, machine/model/revision eligibility and retention before importing
any OEM document. Do not present synthetic SIM-CNC-001 as a Siemens manual.

## Failure and data ownership

- **Neon down:** SQL retrieval fails with a sanitized error; no cross-plant
  manual substitution. NVIDIA embedder down: keyword search stays within the
  authorized published document.
- **Supabase down:** on-site telemetry collection/buffering is a separate
  required system; it must remain operational without Neon. PR #289 does not
  ingest Siemens or MTConnect recordings.
- **Changes to manual:** must increment revision; publication is atomic and
  one revision per document is published at a time. Existing citations carry
  revision; older documents remain available for audit but not ordinary search.
- **Episodic memory:** SQLMemoryRepository in Neon already has the
  episodic_memories table. Memory promotion policy, verification requirements,
  and Chroma recall remain unchanged. Neon is not yet a vector store for
  episodic memory; that is a separate measured migration.
