# Episodic memory

Completed investigations are observations and beliefs, not evaluator truth.
Callers supply a `ReflectionCandidate` with a reusable lesson and evidence
lineage. `MemoryPromotionPolicy.evaluate()` checks it without I/O.
`MemoryService.promote()` applies that policy and sends qualifying memories to
its store. The SQL store preserves originals on duplicate investigation IDs or
normalized category/lesson fingerprints. Paraphrases are not semantic duplicates.

## Database lifecycle

`capstone/memory/schema.py` describes the table for application code.
`migrations/versions/0001_episodic_memory.py` freezes its initial definition in
an explicit Alembic revision. `upgrade()` creates the memory table, constraints,
and category index; it inserts no memories. `downgrade()` drops that table and
all memories it contains. It does not undo past investigations or repairs.

The table contains identity, category, source tick, fingerprint, and a validated
memory JSON payload (JSONB on PostgreSQL). That payload retains the lesson,
diagnosis, proposed intervention, verification, and evidence provenance.
Alembic maintains its own `alembic_version` table to track applied revisions.

Neon is the intended PostgreSQL store for real runs. `DATABASE_URL` is read
through the existing typed settings. A repository constructor does not create
tables or connect; reads and writes use the caller's SQLAlchemy engine.

The reviewed initial PostgreSQL upgrade SQL is in
[`EPISODIC_MEMORY_MIGRATION.sql`](EPISODIC_MEMORY_MIGRATION.sql). It was generated
offline with a synthetic URL, without connecting to Neon. To apply the revision
to the configured database, use an explicit migration command:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
```

Inspect the applied revision separately:

```powershell
.venv/Scripts/python.exe -m alembic current
```

Do not use downgrade as a routine cleanup step on a database containing lessons;
it deletes them. Tests use temporary SQLite databases for creation, removal,
restart, and duplicate checks. PostgreSQL SQL compilation is not a live-server
test. No migration has been applied to Neon by this increment.

## Remaining integration

Agent 1 currently uses a different completion contract in `contracts/completed.py`.
Reconcile that contract with `contracts/completed_investigations.py` before
connecting the runtime. Trusted provenance must be preserved across the handoff;
free-text scans cannot establish the true origin of mislabeled evidence.
Memory evaluation records and runtime wiring remain to implement. Retrieval is
bounded lookup by investigation/category; embeddings and RAG are not implemented.
