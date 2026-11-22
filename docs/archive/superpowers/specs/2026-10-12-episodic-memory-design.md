# Agent 2: episodic memory, reflection, and evaluation

Agent 2 consumes completed investigation artifacts. It does not change the
reasoning loop, Graph transitions, tools, termination, or simulator. The
developer reinstated understanding checkpoints on 2026-10-12, with a commit
and push after each passed checkpoint. The additive shared contract lives in
`capstone/contracts/completed_investigations.py`; Agent 1 can produce it without
depending on persistence. Existing shared contracts are unchanged.

## Data flow

`CompletedInvestigation -> ReflectionCandidate -> MemoryPromotionPolicy ->
MemoryService -> MemoryStore -> SQLMemoryRepository`. Reflection is a caller-supplied explicit
artifact, not generated chain-of-thought or an LLM call. Diagnosis correctness
in reflection means observational support/refutation; evaluator correctness is
recorded separately and never copied into memory.

The completed artifact includes anomaly, existing evidence/hypotheses,
conclusion, optional proposed action, optional verification, and runtime counts
and termination reason. It describes runtime output without controlling runtime.

Episodic memory keeps investigation/run IDs, category, qualitative symptoms,
important evidence references, diagnosis, intervention, observed outcome,
verification, reusable lesson, confidence, source provenance, source tick,
policy version, and deterministic ID/fingerprint. It does not retain raw sensor
samples or evaluator truth. All times/IDs are caller-supplied or derived; no
wall clock, simulator RNG, model, or external service is required for promotion.

## Promotion rules

Accept only a verified, resolved outcome with verification evidence, a supported
diagnosis with evidence, a reusable non-transient lesson with evidence, matching
source provenance for every retained reference, and confidence >= 0.8 by default
(configurable). References must exist in the completed artifact. Reject hidden
simulator/evaluator provenance and recognizable hidden-field markers. Reject
transient-only lessons, unverified/failed outcomes, refuted diagnoses, and
failed interventions. Reasons are stable codes and policy version is explicit.

The provenance labels are supplied by the trusted artifact producer; this is
not a semantic truth detector. Mislabeled arbitrary prose cannot be proven safe
by a deterministic policy. The memory path never imports ground truth or an
evaluator. Evaluation records are structurally separate from promotion input.

## Persistence and deduplication

Use existing optional SQLAlchemy/Alembic dependencies. Accepted memories are
relational rows with typed identity/category/source-tick/fingerprint columns
and a validated memory payload in JSONB (JSON on SQLite for offline tests).
That payload preserves evidence references and provenance. Database unique
constraints enforce one memory per investigation and one normalized
category/lesson fingerprint across investigations. Normalization uses Unicode
NFKC, case folding, whitespace/punctuation collapse; paraphrases are not semantic
duplicates. Deduplication never silently overwrites original provenance.

Repository writes use transactional INSERT ON CONFLICT DO NOTHING, returning
whether a row was inserted or matched an existing investigation/lesson. Queries
support investigation ID and bounded category retrieval with an explicit query
contract. Future semantic retrieval can implement the same protocol; no vector
columns, embeddings, RAG, or automatic prompt insertion are introduced.

Migration 0001 creates only the memory table and indexes. Alembic metadata is
wired to this schema. No live database migration runs as part of this work.

## Evaluation

Add separate evaluation contracts for promotion/storage reasons and later
retrieval uses, including consumer investigation, memory ID, helped/hurt/neutral/
unknown assessment, and evidence references. A record builder associates
promotion with a completed artifact. It neither invents retrieval effects nor
feeds evaluator-only diagnosis correctness back into promotion. Existing
scenario-scoring implementation remains outside this task (none exists yet).

## Verification

Test acceptance and every gate, dangling references, provenance retention,
hidden-source rejection, transient-only rejection, no-action incidents,
determinism, persistence across repository instances, both duplicate classes,
constraints and migration round trips. Use local SQLite for executable repository
tests and offline PostgreSQL SQL compilation for PostgreSQL migration/insert
coverage. State explicitly that no live PostgreSQL server was exercised.
