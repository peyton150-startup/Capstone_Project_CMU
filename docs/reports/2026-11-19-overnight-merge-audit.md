# Overnight merge audit, 2026-11-18 to 2026-11-19

This report covers every pull request that was open on the evening of
2026-11-18, what happened to it, how it was checked, and what is still missing
or could conflict. It is for the developer to read in the morning. Nothing here
changes code; the follow-ups are listed so they can be planned.

All walkthroughs (AGENTS.md §11.6) were **skipped at the developer's request**
for tonight and are owed (see "Walkthroughs owed").

## 1. What was merged or closed

| PR | What | Result | Merge commit |
|----|------|--------|--------------|
| #308 | Repairs for #307 (named host config fault, run-queue panel) | merged into #307 | `98b233b` |
| #307 | Hosted runs: Render API + Northflank worker over PostgreSQL | merged into main | `67c5b7f` |
| #313 | Worker failure trace (failure codes, heartbeat problems, migration 0006) | merged into main | `3b11863` |
| #309 | Haas A: MTConnect preflight, bounded transport, durable capture | merged into main | `eb69273` |
| #310 | Haas B: qualified signals, calibrated anomaly detector | merged into main | `e7ac3a6` |
| #311 | Haas C: approved MTConnect events, recorded triage tools | merged into main | `43cfb5e` |
| #312 | Haas D: field-readiness checklist, trace context keys | merged into main | `3b3e584` |
| #298, #299, #300, #301, #302, #303, #305, #306 | Source PRs folded into #307 | closed as superseded (branches kept) | none |

Superseded PRs were checked line by line (whitespace- and
punctuation-insensitive) against main: 96.0 to 99.4 % of each PR's added lines
are present, and every remaining difference was read and is a deliberate
replacement made in #307/#308, not lost work.

## 2. How each merge was checked

Each PR was merged with the latest main (no rebase, no force-push), then:

1. `ruff check`, `ruff format --check`, `.github/test_groups.py check`, and the
   touched tests, locally.
2. **Docker Desktop**, on a Linux checkout of the exact commit: TLS
   PostgreSQL 17 journal tests (80), real-FastAPI API tests (31), the full
   suite on Python 3.14.7 against live Postgres, lint, the offline SNAP dry
   run, and the frontend (`npm run build`, `npm test`, 22 tests).
3. GitHub CI (22 checks, 25 to 26 for the hosted PRs).
4. When new modules changed the evaluator inventory, it was rebuilt from that
   commit's CI `evaluator-inventory` artifact, committed, the offline SNAP run
   repeated in Docker (0 live requests), and CI rerun to green.
5. A variable-level read of the PR's code, then a second pass after each fix.

Merged only on all-green CI. No live model run.

| PR | Docker full suite | SNAP (Docker) | CI |
|----|-------------------|---------------|----|
| #308 (into #307) | 3213 passed | ok | 25/25 |
| #313 | 3233 passed | ok, 0 live requests | 25/25 |
| #309 | 3267 passed + inventory test (fixed) | ok | 22/22 |
| #310 | 3278 passed + inventory test (fixed) | ok | 22/22 |
| #311 | 3290 passed + inventory test (fixed) | ok | 22/22 |
| #312 | 3296 passed + inventory test (fixed) | ok | 22/22 |

"Inventory test (fixed)": `test_the_repository_has_no_unexplained_python_file`
fails on the first CI run of any PR that adds modules, because the committed
inventory does not list them yet. It passed after the inventory rebuild on the
next commit.

## 3. Problems found and fixed during the merges

These were real breaks, not style.

1. **#309 broke a main test after the merge.** Main's
   `tests/test_coverage_telemetry_edges.py` faked
   `run_collector(obj, path, *, interval, max_polls)`; #309's CLI now passes
   `enforce_poll_interval`, `safe_errors` and `event_logger`, so the fake raised
   `TypeError`. The fake now takes `**haas_options` and asserts they are all
   off on the generic `--url` path, which also proves the Haas-only behaviour
   never leaks into it.
2. **#311 refused every capture with a collector restart.** #311 added a check
   that source timestamps never go backwards across the whole capture file.
   After a buffer overrun the collector re-reads `/current`, which repeats
   unchanged values with their original, older timestamps. Proven with a
   scratch test: such a capture raised "capture source timestamps are out of
   order" on #311 while main accepted it. **Fix (developer to review):** the
   check is now per channel (source, device, data item); a channel going back
   in time is still refused (#311's own test still passes, plus
   `test_a_channel_going_back_in_time_is_still_refused`). New test
   `test_a_capture_with_a_collector_restart_is_still_replayable`. To revert,
   restore the `zip()` check in `RecordedObservationTools.__init__`
   (`capstone/providers/replay.py`).
3. **#311 would list a restart's repeated state as a new event.**
   `get_events` now lists each (source, instance, sequence) observation once.
4. **Every Haas PR (#309 to #312)** failed `ruff format`/import order and left
   its new test files out of the CI test groups (so CI never ran them as a
   group). Fixed on each; all 11 haas test files are in the "Live telemetry"
   group.
5. **#308**: a malformed revision or `TRIAGE_*` value crashed the worker and
   gave a misleading 409; a `toneFor` call broke `npm run build` (only Docker's
   real build caught it). Fixed before the merge (see PROGRESS.md).

§7.1 `# Variables:` blocks were added on every function these PRs created or
changed that lacked one: `validate_haas_get`, `haas_get`, `verify_haas_probe`,
`validate_streams_metadata`, `run_collector` (new parameters),
`qualify_numeric`, `assess_calibrated_window`, `qualify_event`,
`RecordedObservationTools.__init__`, `get_events`, `replay_tool_specs`,
`run_recorded_investigation`, `recorded_investigation.main`,
`assess_haas_field_readiness`, `EventLogger.log_event`.

## 4. Open issues for tomorrow (most important first)

**Fix status (2026-11-19, afternoon).** This report records issues; it fixes
none of them. Code fixes so far, both open for review and not merged:

- PR #316 fixes three: the replay cutoff hiding earlier evidence, `ready()`
  checking one of 0006's three columns, and the triage record's
  `evidence_tests` coming from the server instead of the run.
- PR #317 connects the #310 Haas detector to recorded captures (the High item
  below), for recorded captures only, not the live collector.
- Done outside code: migration 0006 on Supabase (see "Database state").

Every other item below is still open and has no fix yet.

### High

- **Deploy order for #313.** Migration `0006_worker_problems` must run
  (`alembic upgrade head`) **before** the new web service or worker starts:
  `ready()` now refuses an unmigrated database, and the worker writes the new
  heartbeat columns. **Update 2026-11-19 (daytime): done on Supabase.** See
  "Database state after the merges" below. Still needed: point
  `CAPSTONE_UI_RUN_DATABASE_URL` on Render and Northflank at Supabase's
  session-pooler connection string.
- **The Haas detector is not connected to anything (#310).**
  `qualify_numeric` (`ingestion/qualified.py`) and `assess_calibrated_window`
  (`ingestion/real_detector.py`) have no caller under `capstone/`; only their
  tests call them. Real Haas telemetry is collected and replayable, but no
  sample is qualified and no anomaly is scored from it, so nothing can start
  an investigation from live data. This is disclosed in #310's own
  description ("not yet wired to the live collector, background detector, or
  incident dispatcher"), but it was missing from this report. #310's
  description was also headed "DRAFT, DO NOT MERGE"; it was merged because
  the developer listed #309 to #312 for merging. Treat the detector as a
  tested library, not as working anomaly detection, until a PR connects it.
  (Found by the Savant review on 2026-11-19, confirmed by a call search.)
- **Northflank worker not yet deployed.** It needs start command
  `python -m capstone.worker`, the migration above, and a runtime check that
  `NF_DEPLOYMENT_SHA` is the full 40-character commit (a short or empty value
  leaves runs queued forever, or disables the commit check: see next item).
  The Northflank session was sent these details.
- **Missing commit on both hosts disables the commit check.**
  `source_revision()` returns `None` when no variable is set; `None == None`
  matches, so a web and worker on different code would accept each other.
  Policy decision: should hosted mode refuse a missing revision?
- **#311 behaviour change to review**: per-channel ordering (section 3.2).

### Medium

- **Stale worker problem never clears.** `serve_worker`'s `problem` is set by
  `note()` and never reset, so after one `poll_failed` the worker re-sends the
  same problem on every pulse until restart. `queue_metrics` also picks the
  newest problem across all heartbeat rows, including long-dead workers
  (`run_repository.py`, query ordered by `last_problem_at`). The System page
  can therefore show an old problem indefinitely. Fix: clear after N good
  polls, and read only fresh heartbeat rows.
- **Bad `TRIAGE_*` values give inconsistent errors.** The worker stops with
  `invalid_configuration` and submission returns 503 (#308), but
  `GET /api/v1/settings/effective` and `GET /api/v1/lab/runs/configuration`
  call `get_settings()` unguarded and return **500**, while preview and
  submission return **422** "Incompatible triage settings". Pick one answer
  (503 named fault) for all four.
- **The replay status tool refuses STOPPED/INTERRUPTED machines (#311).** Any
  Execution state other than running or READY now raises instead of mapping
  to idle, so `list_machines` fails whenever a machine is stopped. The tool
  contract has no "unknown" state; adding one would keep the tool usable.
- **`classify_failure` labels.** A pydantic `ValidationError` during model
  setup is classified `contract`, not `model_setup`, because `ValueError` is
  checked first. Also its final `assert code in RUN_FAILURE_CODES` vanishes
  under `python -O` (the repository re-checks, so still safe).
- **The saved triage record can show the wrong evidence-tests setting.**
  `triage_record()` (`capstone/experiment.py`) sets `evidence_tests` from
  `get_settings().effective_triage.evidence_tests`, the server's settings at
  the time the record is written. A hosted run can override triage settings
  per run (`triage_settings` on the request, resolved by
  `resolve_triage_run` and passed to `run_episode` as
  `triage_configuration` in `api/runs.py` and `worker/runner.py`). The other
  triage fields come from the run itself (`first.fixed_plan_used`,
  `first.triage_run_mode`). So a run submitted with evidence tests off, on a
  server where they are on, is stored as "on", and `format_evidence_tests`
  then counts it in the wrong group when runs are compared. Fix: take the
  value from the run's `triage_configuration` (keep the settings value only
  when none was given). (Savant review; confirmed by reading the call path,
  not reproduced by a test.)
- **`uv sync --all-extras` alone gives a broken local test run.** FastAPI is
  not in `pyproject.toml`; CI installs `frontend/requirements-api.txt`
  separately. A developer who follows AGENTS.md §9 literally gets
  `ModuleNotFoundError: fastapi`. Make it an extra or update §9.

### Low

- #310/#311 import the private helper `channel_map._disagreement` from two
  modules; make it public.
- #310's detector compares `observation.device` (the MTConnect device name)
  with `baseline.machine_id`; the baseline must store the device name, which
  the field name does not say.
- #311 maps condition WARNING and FAULT both to kind `alarm`; the triage event
  log cannot tell them apart.
- #311 lists `UNAVAILABLE` as an allowed Execution state, but unavailable
  records are refused earlier, so that entry is dead.
- #309's CLI checks `--out is required` twice (early and late); harmless.
- The generic `--url` collector path still prints `str(error)`, which can hold
  a host address; only the Haas path uses `safe_errors`.
- `list_runs` rows carry no `heartbeat_age_seconds` (only `get()` does), so a
  frozen run is only visible on its detail page.
- **The replay cutoff can hide earlier evidence (#311, made reachable by the
  section 3.2 fix).** `RecordedObservationTools._visible()`
  (`providers/replay.py`) stops at the first observation, in file order,
  whose timestamp is after the cutoff. Since captures whose channels
  interleave in time are now accepted, a later line with an earlier
  timestamp can be hidden: cutoff t=5, file order (channel A, t=10) then
  (channel B, t=3) hides B. Mostly this hides repeats re-sent after a
  collector restart, which were already visible earlier in the file; real
  evidence is lost only when a channel first appears after a restart with an
  older timestamp. Fix: skip observations after the cutoff instead of
  stopping, and keep markers bounded by the cutoff. (Savant review; confirmed
  by reading, not yet reproduced by a test.)
- **`ready()` checks one of 0006's three columns.** It checks
  `sim_worker_heartbeats.last_problem_code` but not `last_problem_at` or
  `last_problem_count` (`api/run_repository.py`, `ready`). 0006 adds all three
  in one `ALTER TABLE`, so Alembic cannot apply it partially; only a schema
  edited by hand would pass `ready()` and then fail on every worker pulse.
  Fix: count all three columns. (Savant review rated this medium; low here
  because the migration is atomic.)
- 4 old CI runs (43097153882, 43097957678, 43098045589, 43098122407) are stuck
  "queued" with no jobs; GitHub refused cancel and delete (403/409). They block
  nothing; GitHub support or time will clear them.

### Possible future conflicts

- `#312`'s readiness gate `collector_restart_test_passed` depends on the
  section 3.2 fix: without it a real restart capture could not replay.
- Every PR that adds or changes a module must rebuild
  `evaluation/inventory/*.json` from its own CI artifact, or SNAP and the
  inventory test fail. Two PRs open at once will conflict on these four files;
  rebuild after merging main, never hand-merge them.
- Branches of the closed PRs #298 to #306 still exist; delete them once you
  are sure nothing else is needed from them.

### Database state after the merges (2026-11-19, daytime)

The PRs split storage this way: **Supabase** (Capstone-CMU) holds the hosted
run journal in `capstone_private` (#289, `docs/SUPABASE_STORAGE_PLAN.md`);
**Neon** holds episodic memory (`DATABASE_URL`) and, later, the manual-knowledge
tables (#290, `docs/NEON_KNOWLEDGE_ROLLOUT.md`).

- **Supabase:** migrations 0001 to 0006 applied (revision
  `0006_worker_problems`). Ten `capstone_private` tables plus
  `episodic_memories`, all empty, row-level security on every table including
  `alembic_version`.
- **Neon:** revision `0001_episodic_memory`, with only `episodic_memories` and
  `alembic_version`. Migrations 0002 to 0006 were applied here by mistake
  first (the local `.env` has no `CAPSTONE_UI_RUN_DATABASE_URL`, so Alembic
  used the Neon `DATABASE_URL`); the empty `capstone_private` schema was
  dropped and the revision reset to 0001. No other Neon data was touched.
- **Neon manual knowledge, v1 (added later the same day at the developer's
  request):** `migrations/neon/0001_manual_knowledge.sql` and
  `0002_oem_approvals.sql` applied to the same Neon database (pgvector 0.8.7;
  `capstone_knowledge.manual_documents`, `manual_sections`, `manual_approvals`,
  row-level security on all three). Seeded with
  `python -m capstone.manual.neon --apply`: the synthetic `SIM-CNC-001`
  revision 1.3, published, 17 sections, each with a 2048-dimension NVIDIA
  embedding (17 embedding calls, no chat-model calls). Keyword and semantic
  search both return the expected sections (for example "vibration rising on
  the spindle" finds 2.1 Abnormal Vibration first). No Neon branch backup was
  taken first; the change only adds a schema, and `episodic_memories` (0 rows)
  was not touched. No OEM or pilot manual was imported.
- **Still to set for the manual to be used:** `NEON_KNOWLEDGE_DATABASE_URL`
  (server-only, `sslmode=require`) in the local `.env` and on the hosts, then
  `--manual neon` for agent runs, and `CAPSTONE_UI_NEON_MANUAL=1` for the
  dashboard (steps 3, 6 and 7 of `docs/NEON_KNOWLEDGE_ROLLOUT.md`). The seed
  used the Neon `DATABASE_URL` in-process, since the two point at the same
  database.
- The stored embedding model name is `nvidia/nvidia/nemotron-3-embed-1b`
  (provider prefix doubled). Seeding and search use the same setting, so
  retrieval works, but changing `EMBEDDING_MODEL` to fix the prefix would make
  every stored section ineligible until the manual is re-seeded under a new
  revision.
- The local `.env` line `REQUESTY-BASE-URL` has a hyphenated name, which stops
  `uv --env-file` at that line; it should be `REQUESTY_BASE_URL`.

## 5. Walkthroughs owed (§11.6)

Skipped tonight at the developer's request; each is "built ungated, developer
to review; understood: no":

- #308's repairs (the #307 walkthrough itself was done: understood partly)
- #313 worker failure trace
- #309, #310, #311 (including the overnight fix in section 3.2), #312
