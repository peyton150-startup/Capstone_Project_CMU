# Episodic Memory Implementation Plan

**Goal:** Store verified reusable investigation lessons behind deterministic gates.
**Spec:** `docs/superpowers/specs/2026-10-12-episodic-memory-design.md`
**Execution:** Agent 2 implements inline with developer understanding
checkpoints, reinstated by the developer on 2026-10-12. Explain each meaningful
increment and verify understanding before implementation; verify it again
afterwards. Earlier ungated wording in the design is superseded for this work.
Commit and push after every passed checkpoint, as requested by the developer.
**Stack:** Pydantic v2, optional SQLAlchemy 2/Alembic, PostgreSQL/SQLite, pytest.

## Constraints

No edits to live reasoning, Graph, tools, simulator, or existing shared contracts.
No LLM calls, embeddings, MCP, CrewAI, new dependencies, or live database writes.
Add purpose/responsibility comments to all new capstone modules.

## Task 1 — contracts and deterministic promotion

- [ ] Add failing tests in `tests/test_memory_policy.py` for a completed artifact,
  reflection, successful promotion, failed/unverified outcomes, low confidence,
  missing references/provenance, hidden sources, transient lessons, and no action.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_memory_policy.py` and
  confirm missing memory interfaces prevent the specified behavior.
- [x] Add `capstone/contracts/completed_investigations.py`,
  `capstone/memory/contracts.py`, `policy.py`, and package initializer.
  `MemoryPromotionPolicy.evaluate(candidate) -> PromotionDecision` returns
  a validated memory or stable rejection reasons, without I/O.
- [x] Run focused tests and Ruff, then commit the increment.

## Task 2 — persistence and retrieval

- [x] Write failing persistence tests using real local SQLite connections for
  stored memories, read-after-reopen, category filters, duplicates, and constraints.
- [x] Add `capstone/memory/schema.py`, `repository.py`, and `service.py`.
  `MemoryService.promote(candidate) -> PromotionDecision` applies policy then
  writes through a protocol; `retrieve(MemoryQuery) -> tuple[EpisodicMemory, ...]`
  delegates bounded retrieval. SQL repository enforces atomic deduplication.
  Verified fresh-engine reopen and competing inserts. Storage's
  post-implementation duplicate-handling checkpoint passed on 2026-10-12.
- [x] Add migration 0001, wire metadata in `migrations/env.py`, and update old
  scaffold expectations to reflect the newly implemented schema. Test upgrade,
  downgrade, and PostgreSQL offline SQL without a network connection.
- [x] Run focused tests and Ruff, then commit the increment.
  Migration post-implementation checkpoint passed on 2026-10-12; live Neon
  application remains a separate step. The full offline suite passed: 453 tests.

## Task 3 — evaluation and handoff

- [x] Write failing tests for accepted/rejected storage records and later memory
  use assessments, including identity consistency and unknown effects.
- [x] Add `capstone/evaluation/memory.py` and package initializer with separate
  evaluator-only fields. No dependency from memory to evaluation.
- [x] Document API examples, limits, migration command, modules/classes/functions,
  and the Agent 1 contract in `docs/EPISODIC_MEMORY.md`. Update progress with
  implementation status separate from developer understanding.
  Evaluation post-implementation checkpoint remains outstanding. Full offline
  verification: 475 tests passed; Ruff lint/format and whitespace checks passed.
- [ ] Run the full offline test suite, Ruff lint/format, and diff checks. Review
  the final diff against the scope; commit and push the Agent 2 branch.

## Review focus

Untrusted free text is not a truth classifier; source lineage must be trusted.
Verification needs observations, not only a success flag. Deduplication must
survive restart and database races. Rejected artifacts must never be inserted.
Retrieval must not claim helpfulness without a later assessed use record.
