# Episodic memory

Completed investigations are observations and beliefs, not evaluator truth.
Callers supply a `ReflectionCandidate` with a reusable lesson and evidence
lineage. `MemoryPromotionPolicy.evaluate()` checks it without I/O.
Two kinds of memory pass (policy `episodic-v2`): advice from a verified fix
(`outcome="resolved"`), and an action the check found did not work
(`outcome="unresolved"`). A failure memory's lesson must be exactly
`failure_lesson(investigation)`: what was tried, on which machine, for which
symptoms. It never says why, and never judges the diagnosis.
`memory/reflection.py` `build_candidate` fills every fact from the finished
record; the model writes only a success's advice sentence.
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
test. Revision `0001_episodic_memory` was applied to Neon on 2026-10-15
(PostgreSQL 18; the database was empty before; the table starts with no rows).

## Runtime integration

`contracts/completed_investigations.py` is the only completion contract; the
loop's richer records live in `agent/artifacts.py`. `agent/completion.py`
produces the completed investigation, `learning.learn_from` audits it and
offers its lesson to the gate, and `capstone/episode.py` chains both after
`run_investigation`. Trusted provenance must be preserved across the handoff;
free-text scans cannot establish the true origin of mislabeled evidence.
Retrieval is bounded lookup by investigation/category, plus free-text recall
through the agent's `recall_memories` tool, below.

## Semantic recall (ChromaDB)

Install with `uv sync --extra semantic`. A ChromaDB collection is a derived
index beside the SQL store, which stays authoritative. `MemoryService(...,
index=...)` upserts each newly stored memory (metadata: `memory_id`, `outcome`,
`timestamp` = source simulation tick); an index failure never undoes the stored
row. `MemoryRecall.recall_memories(query, k=5)` searches the whole collection,
then hydrates records from SQL by ID, skipping IDs SQL does not hold.
`build_memory_recall()` reads `MEMORY_RETRIEVAL_MODE` (`semantic` default,
`keyword`, `none`), `CHROMA_PATH` (default `.chroma/`) and `CHROMA_COLLECTION`
(default `episodic_memories`). If Chroma cannot open or a search fails, recall
falls back to keyword search and reports `fell_back=True`. Embeddings use
Chroma's bundled local all-MiniLM-L6-v2 model (downloaded on first use).
Rebuild the index from SQL with `uv run python -m capstone.memory.backfill`.

The agent reaches this through its one memory tool. `build_memory_service(
repository, settings)` opens one index for both sides: promotion writes to
it and `MemoryService.search` (behind `recall_memories`) asks
`MemoryRecall` in the configured mode, then turns each record into the safe
`RecalledMemory` view, so semantic recall shows the agent exactly the fields
keyword recall does. A `MemoryService` built without `recall` keeps the
plain word search. Reranking is not implemented.

The planned [Future Work 1 agent-directed RAG loop](MVP_SCOPE.md#agent-directed-rag-and-repeat-retrieval-2026-10-18)
uses the same Nemotron investigation agent to judge retrieved evidence and search
again with a revised query when it is insufficient, including when drafting an
answer reveals a gap. The default is three retrieval calls per knowledge gap,
bounded by the overall investigation budget. Exhaustion leaves an explicit
uncertainty; it must not force a confident answer. This is a runtime integration
requirement, not behavior currently provided by `MemoryService.retrieve()`.

## Evaluation and API use

For a caller-supplied, validated `candidate` and SQLAlchemy `engine`, use:

```python
from capstone.evaluation.memory import build_promotion_record, build_use_record
from capstone.memory.contracts import MemoryQuery
from capstone.memory.repository import SQLMemoryRepository
from capstone.memory.service import MemoryService

service = MemoryService(SQLMemoryRepository(engine))
decision = service.promote(candidate)
promotion_record = build_promotion_record(candidate.investigation, decision)
promotion_json = promotion_record.model_dump_json()

memories = service.retrieve(MemoryQuery(category="bearing", limit=5))
if memories:
    # later_investigation is a caller-supplied completed consumer report.
    use_record = build_use_record(later_investigation, memories[0])
    assert use_record.effect == "unknown"
```

`MemoryPromotionRecord` keeps acceptance, actual storage, reasons, policy version,
and new/existing memory IDs. Policy acceptance alone does not set `stored=True`.
The builder rejects inconsistent investigation/run identities and policy versions.
Its optional `diagnosis_correct` field is evaluator-only; it never changes the
promotion decision or becomes part of an agent-visible memory.

`MemoryUseRecord` distinguishes retrieval, actual use (`None` means unknown),
and attributed effect. To record `helped`, `hurt`, or `neutral`, the caller must
report use and supply an assessment source (`agent_report`, `human_review`, or
`evaluator`), an explanation, and unique evidence references from the consumer
investigation. Those requirements make an assessment traceable, not causal proof.
The builder does not ask an agent, inspect hidden truth, or infer usefulness from
success. Assessment and retrieval observations are supplied by the caller.

These evaluation records are immutable, JSON-serializable artifacts for reporting.
They have no database table or automatic report writer. Their builders perform no
I/O and add no wall-clock timestamps or random IDs. The dependency runs from
evaluation to memory contracts; memory does not import evaluation.
