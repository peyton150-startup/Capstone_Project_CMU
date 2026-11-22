# PR #290 verification — Neon synthetic manual knowledge

## Scope and deployment boundary
Opt-in server-side Neon PostgreSQL/pgvector knowledge store and scoped synthetic simulator manual search. No live Neon database migration, OEM manual import, pilot access expansion, or change to the Supabase simulator journal's SQLite default is included.

## Reconciliation with merged PR #289
- Merged `main` (`a68a1f7`) into the Neon PR with two-parent commit `8990508` after Supabase PR #289.
- Preserved Supabase's Postgres journal, TLS and migration; integrated Neon API manual controls and the same run executor with Neon manual cleanup.
- Preserved the existing frontend Local/Render switch, and test groups for deterministic triage and the PostgreSQL journal.
- Maintained separate, private migration files for the Neon knowledge schema and Supabase journal.

## Verified jobs before the final head
- [Combined source CI](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/44128288468): 16/19 test/check jobs passed. Three initial evaluator checks failed on *stale inventories* (new Neon source file and source hashes), not on functional tests. Full suite recorded **3,092 passed, three skipped, one stale-inventory assertion**.
- [Source-matched two-pass rebuild](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/44128274226): all steps passed. The refreshed full suite completed with **3,093 passed and three skipped**, and the workflow committed the new inventories and removed itself.
- [Neon PostgreSQL 18/pgvector](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/44128288294): passed the real SQL manual/embedding/keyword fallback/publishing acceptance suite.
- [Supabase PostgreSQL 17 TLS journal](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/44128288740): passed the journal acceptance suite.
- [Industrial frontend](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/44128288236): both jobs passed.

## Final merge gate
This documentation/workflow-comment commit triggers ordinary CI after the bot-authored inventory commit produced `action_required` checks. **Do not merge until the final current head has 19/19 CI jobs green, both PostgreSQL integrations green, both frontend jobs green, no unresolved reviews, and no conflicts.** No field Siemens, production Render, or live Neon/Supabase deployment test has been claimed.
