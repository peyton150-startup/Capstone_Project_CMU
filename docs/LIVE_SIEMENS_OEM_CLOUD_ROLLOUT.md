# Live Siemens → Supabase and approved OEM manuals → Neon

**PR #291 is a draft, stacked on Neon PR #290.** Supabase simulator-journal PR #289
is independent. No real controller, production DB, Supabase Storage bucket,
or OEM document was touched by creating this PR.

## Deployment architecture / exact endpoints

```text
Approved Siemens OPC UA server  [on OT network; NO internet exposure]
  └─ SiemensOpcUaCollector --durable ── approved v2 JSONL + audit
      └─ cloud_uplink --scope --collector-config --cursor
          ├─ exact server/node/approval/time/quality gate before egress
          ├─ durable atomic cursor; complete lines only; bounded batches
          ├─ HTTPS POST /api/v1/ingest/siemens/batches (collector-only bearer)
          │   └─ Render FastAPI → independent Supabase PostgreSQL session pool
          │       └─ capstone_ingest.streams, batches, records (transaction)
          └─ ACK digest + next_line → fsynced local cursor; retry on outage

Authorized OEM PDF + reviewed, page-numbered JSON manifest [operator workstation]
  └─ manual.oem --apply (explicit)
      ├─ verify PDF SHA-256, approval, site/machine/controller identity, expiry
      ├─ check actual private Supabase bucket metadata, immutable PDF upload
      └─ Neon capstone_knowledge.manual_documents, manual_approvals,
          manual_sections, with exact revision and source object key
              └─ ScopedOEMManualSearch(site, machine, controller family,
                 controller fingerprint, query) → approved manual citations
```

Render has no CNC controller connection and does not need a persistent disk for
received observations. Local capture must be on **persistent encrypted** storage
outside this public Git repository; neither cloud databases nor a successful
HTTP request substitutes for the local buffer while offline.

The data model distinguishes:
* **received**: authorized, typed observation retained, including Bad/Uncertain
  quality and gap/reconnect events; no values fabricated.
* **numeric_quality_qualified**: approved numeric field + verified unit,
  finite Good value with source timestamp, permitted sample age and no overflow.
* **analysis_eligible = false at ingestion**: real anomaly analysis needs
  a *second* RMI/SDC gate: comparable machine state, baseline, coverage,
  mapping, human approval and evidence independence.

No external model calls during capture, receipt, classification or manual import.

## Two separate schema migrations

1. Supabase: `migrations/supabase/live_siemens_0001.sql` is **independent**
   of PR #289's simulator journal Alembic migration. It creates a private
   `capstone_ingest` schema with RLS, revoked browser grants, ordered
   observation keys, receipt digests and retention timestamps. Use a dedicated
   TLS PostgreSQL connection with server-only privileges; do not expose
   `CAPSTONE_LIVE_DB_URL` in Vercel or the browser.
2. Neon: after PR #290's
   `migrations/neon/0001_manual_knowledge.sql`, apply
   `migrations/neon/0002_oem_approvals.sql` to add approval, exact
   controller/machine identity and reviewed PDF page lineage. Never point
   the simulator's Alembic migration runner at this SQL.

Review migrations, backup/restore, RLS privileges, Supabase pool settings
(session port 5432 or supported direct connection; **not** transaction port
6543 for session-dependent workloads), role allocation and verified TLS before
enabling any deployed writer. No schema is created on FastAPI startup.

## Field gate required BEFORE configuring any production credential

A named IT/OT + vendor-authorized person must verify:

- Explicit read-only Siemens host/application URI, identity, certificate,
  controller family, exact NCU/PPU/software/license and approved NodeRefs.
- Signed source-profile reference and approval expiry, exact plant/machine,
  node-specific text/value permission, permitted cloud use and data retention.
- Approved rate, on-site capture path, no restricted program/customer/PLC
  values, approved TLS route to Render, and stop/revocation owner.
- Local loss-aware spool, encrypted private disk, disk-space alert,
  reconnect and power-loss tests, physical field capture, human event audit.
- A scheduled retention/delete job **and its audit evidence** (this PR records
  `retained_until` but intentionally does not silently delete live records).
- Separate external-model consent (not granted by approving capture or manual).

Missing any one means **do not enable production ingestion**.

## Operator configuration and safe dry-run

Two independent strong tokens: the collector token is **not** a UI/operator
token. Use a private secret manager; never place tokens in `.env.example`,
the public repository, Vercel `VITE_*`, model prompts or client logs.

Render service-only:
- `CAPSTONE_LIVE_INGEST_ENABLED=1`
- `CAPSTONE_LIVE_INGEST_TOKEN=<distinct 32+ character secret>`
- `CAPSTONE_LIVE_DB_URL=<explicit PostgreSQL TLS connection URL>`
- `CAPSTONE_LIVE_SCOPE_FILE=<absolute private signed scope JSON path>`

Private on-site uploader:
- `CAPSTONE_LIVE_INGEST_TOKEN` with the same scoped secret
- `--capture` points at a durable recorder JSONL outside Git
- `--cursor` points at an immutable private cursor file outside Git
- `--collector-config` points at the same approved Siemens collector
  configuration; the uploader refuses config nodes outside the cloud approval
- `--scope` points at the approved, versioned JSON source profile
- `--endpoint` points at Render's HTTPS
  `/api/v1/ingest/siemens/batches` route.

```bash
# At the factory, ONLY after field approval. Read-only collector.
uv run python -m capstone.ingestion.siemens_opcua_adapter \
  --config /private/siemens-approved.json \
  --out /private/capture/siemens.jsonl \
  --durable

# Separate process or controlled scheduled worker; safe to restart.
uv run python -m capstone.ingestion.cloud_uplink \
  --capture /private/capture/siemens.jsonl \
  --cursor /private/capture/siemens.cloud-cursor.json \
  --scope /private/siemens-cloud-approved.json \
  --collector-config /private/siemens-approved.json \
  --endpoint https://RENDER_HOST/api/v1/ingest/siemens/batches \
  --follow
```

**Sample source-profile fields** (illustrative only, NOT authorization):
`site_id`, `machine_id`, `server_uri`,
`controller_fingerprint`, `source_profile_revision`,
`approval_reference`, `approved_by`, `expires_at`,
`retention_days`, `max_sample_age_seconds`,
`cloud_transfer_approved` and exact `nodes` with
`node: {namespace_uri, identifier, identifier_type}`,
`permit_numeric_analysis`, `unit`, `permit_text`,
`retain_value`. A changed approval requires a new stream/cursor; changing
the source file underneath a cursor is a fatal, visible failure.

**Failure behavior:** 401/403/409/413/422/503 do not advance the cursor;
a lost ACK resubmits the same digest and gets the same receipt. Rows and stream
cursor commit atomically. No partial-line skip, silent cross-node scope
merging, or automatic deletion on failure. App restart does not lose DB rows.
The uploader must not be deployed inside ephemeral Render storage.

## OEM manual import (private admin workstation only)

1. Obtain separately signed permission for this exact OEM document, machine,
   controller build, cloud storage and retrieval; verify restrictive rights.
2. Privately stage the PDF (12 MiB maximum) and a **human-reviewed** JSON
   `OEMApproval` manifest, including a verified PDF SHA-256 and each approved
   section's exact text, `section_id`, `page_start`, `page_end`. Do not
   assume arbitrary extracted/OCR text is authoritative.
3. Select a Supabase bucket whose **actual public flag is false**. Set
   server/admin-only `SUPABASE_STORAGE_URL`,
   `SUPABASE_STORAGE_SERVICE_KEY`, and
   `SUPABASE_PRIVATE_OEM_BUCKET` (name begins `private-`). Never use the
   service key in the frontend or in a factory collector.
4. With `NEON_KNOWLEDGE_DATABASE_URL` configured privately, run:

```bash
python -m capstone.manual.oem \
  --manifest /private/approved-oem.json \
  --source-pdf /private/authorized-document.pdf       # preview only

python -m capstone.manual.oem \
  --manifest /private/approved-oem.json \
  --source-pdf /private/authorized-document.pdf --apply
```

The uploader creates immutable private object
`site/machine/document/revision/sha256.pdf`. If the object already exists,
retry performs a byte-for-byte hash check instead of overwriting it. Neon
publishes reviewed sections and machine/controller eligibility in one
transaction. A partial cross-provider failure may leave an **unpublished
orphan PDF** that must be reconciled by an authorized operator; never silently
garbage-collect customer source files. A change to the source or reviewed
section text requires a new revision and a new approval.

`ScopedOEMManualSearch` requires exact `site_id`, `machine_id`,
`controller_family`, and `controller_fingerprint` and filters expiry and
publication inside SQL. It never silently falls back to SIM-CNC-001, another
plant, or an old controller build. The existing simulator
`search_manual` behavior is unaffected. Automatic live investigator injection
and pilot browser access are **not** enabled until a separate source-eligibility
and field validation gate is satisfied.

## Postimplementation PydanticAI architecture review

Official PydanticAI docs reviewed:
- https://ai.pydantic.dev/dependencies/
- https://ai.pydantic.dev/tools/
- https://ai.pydantic.dev/toolsets/
- https://ai.pydantic.dev/graph/
- https://ai.pydantic.dev/testing-evals/

**Keep the new pipeline deterministic.** Pydantic validation already owns
`CloudScope`, `IngestBatch`, `OEMApproval` and `ReviewedOEMSection`.
Introducing an `Agent` into permission validation, telemetry capture,
database transactions, PDF provenance or uploader retries would increase
cost, latency and ambiguity with no benefit.

**Simpler downstream agent, in a separate focused PR:**
- A single typed `ReadOnlyPilotDeps` object passed via
  `RunContext[ReadOnlyPilotDeps]` holds the qualified snapshot reader,
  authorized `ScopedOEMManualSearch`, evidence cutoff, authenticated
  machine identity and a DB-neutral query service. No direct SQL credentials
  become tool arguments.
- A PydanticAI `FunctionToolset` can register `get_signal_samples`,
  `get_quality_and_gaps`, `search_oem_manual` only after the source
  applicability gate passes. Keep manual snippets marked **reference** and
  observed telemetry marked **observation**.
- Preserve the existing deterministic Pydantic Graph orchestration and
  verification rules; use PydanticAI tool signature/type validation to reduce
  duplicated adapters, not to replace consent or physical control checks.
- Test offline using substituted `RunContext` dependencies and representative
  incident fixtures; monitor tool parity, latency and rejected unauthorized
  calls. No new agent/model dependency was added in this PR.

## Acceptance and known limits

Added offline tests for out-of-scope node, disallowed text, bad/uncertain/
stale data, missing source timestamps, gap-marker redaction, auth/revocation,
multipart/oversize rejection, ACK replay, truncation/corruption, PDF hash,
actual bucket privacy and machine/controller retrieval scope. Disposable
PostgreSQL 17 (Supabase) and PostgreSQL 18/pgvector (Neon) integration workflow
exercises the actual migrations and transactional behavior.

**This PR does NOT yet verify** real Siemens licensing, a field-captured
seven-day soak, on-site disk exhaustion behavior, production credentials,
actual PDF rights, PDF extraction quality, field-approved retention job,
multi-machine token registry, real-machine incident detection, or whether
Supabase/Neon render-to-Render networking is permitted by plant IT.
These are explicit deployment blockers, not successful test claims.
