# PR #289 verification — Supabase run journal (opt-in)

## Release boundary
This PR adds an opt-in, server-only PostgreSQL journal for **simulator** runs, with the local SQLite default unchanged. It does not apply production Supabase migrations, change Render environment variables, persist Siemens live telemetry, connect OEM manuals, or start additional workers. Production enablement still requires explicit migration, access/security review, and deployment preflight.

## Conflict reconciliation
- Combined the PR with `main` after #285–#288 at integration merge `d65ffd4`, preserving newer triage and frontend work.
- Retained `main`'s strict `.env.example` contract and the `TRIAGE_HYPOTHESIZE` entry; API-specific runtime keys are documented in `docs/SUPABASE_STORAGE_PLAN.md`, not falsely presented as central `Settings` model fields.
- Added `test_postgres_journal` to the active Industrial frontend API group without dropping `test_triage_deterministic_hypothesize`.
- Preserved the `main` evaluator inventories until source-matched regeneration.

## Verified runs
- [Integrated source CI](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/44121010373): initial run had **3,075 passing** tests, three skips and one stale file-inventory assertion, as expected.
- [One-time inventory rebuild](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/44120991077): source-matched bootstrap, first inventory generation, complete suite verification, final inventory and self-removal **all passed**. The verified suite had **3,076 passing** tests, three skips.
- [Disposable TLS PostgreSQL 17 journal acceptance](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/44121010543): **passed**.
- [Industrial frontend checks](https://github.com/peyton150-startup/Capstone_Project_CMU/actions/runs/44121010715): **both passed**.
- The stale initial SNAP hashes are resolved by the regenerated inventories.

## Final merge gate
This documentation and workflow-comment commit triggers an ordinary user-authored PR validation run because GitHub Actions bot-authored commits do not trigger normal PR CI. **Merge only after latest-head full CI, lint, SNAP, Evaluation and PostgreSQL 17 acceptance are green**, the PR is conflict-free, and no unresolved reviews remain. No live Render/Supabase deployment test is claimed.
