# Full-project SNAP evaluation — run later

This is the handoff for the **SubQ Snap 1.1** evaluation of the capstone.
The live evaluation is **not** run by CI and does **not** start automatically.

## What can be checked now

The CI job **Full SNAP project evaluation (offline, no API calls)** runs
`evaltools.full_evaluation` on a clean checkout using the committed
inventories and two archived cohorts:

- `docs/benchmarks/2026-11-01-tot13-pairs`: 52 historical episodes
  (record-only traces; evidence-dependent questions stay **unknown**).
- `docs/benchmarks/2026-11-02-audited-known-cases`: 5 archived episodes
  with audit files, not a complete 13-case study.
- `docs/benchmarks/2026-11-10-snap-calibration-pair`: 23 episodes with full
  audits (10 baseline, 13 treatment), but no independently reviewed
  diagnosis labels or saved complete arm configurations. Only 10 cases pair.

It prepares SNAP-only questions for **FN, TS, TL, RUN and BT**, writes the
request files, `ledger.jsonl`, `scope_manifest.json`, `report.json` and
`report.md`, and verifies identity/count reconciliation, source hashes,
scope, all five question families, and that **no answer file or live send**
was created. The CI artifact `snap-full-dry-run` contains its report,
ledger and `readiness-check.json`. A green job confirms that the offline
pipeline runs on the checked-out revision, **not** that the API will answer,
that SNAP judgments are accurate, or that old record-only traces are full.

The `--commit` argument must equal the clean, checked-out Git revision.
After adding/editing project or test Python files, regenerate inventories
from that same revision's full pytest coverage/JUnit run before using
`full_evaluation`. Never reuse an earlier inventory with a changed source.

## Reproduce the offline check on Windows PowerShell

From the root of the checked-out repository:

```powershell
git status --short
uv sync --locked --all-extras
$commit = (git rev-parse HEAD).Trim()
cd evaluation
uv run --locked --all-extras python -m evaltools.full_evaluation `
  --commit $commit `
  --provider snap --snap-full-context `
  --archive ../docs/benchmarks/2026-11-01-tot13-pairs `
  --archive ../docs/benchmarks/2026-11-02-audited-known-cases `
  --archive ../docs/benchmarks/2026-11-10-snap-calibration-pair `
  --out full-eval/snap-full-dry-run
cd ..
uv run --locked --all-extras python .github/verify_snap_dry_run.py `
  --out evaluation/full-eval/snap-full-dry-run `
  --expected-episodes 80 --commit $commit
```

**No API key is needed** for these commands; do **not** add `--send`.
Outputs stay under the git-ignored `evaluation/full-eval/` directory.
Inspect `report.md` and `readiness-check.json`. Re-running the dry run
in the same folder is safe only when the source, archives and rubric
are unchanged; for a new evaluation cohort, use a new output folder.

## Before paying for any SNAP evaluation

1. Check a green **Full SNAP project evaluation (offline, no API calls)**
   job on the **exact commit** you intend to evaluate, and that
   `report.json` contains no `scope.unexplained` or `scope.stale`.
2. Check `report.json` for `record_only_traces`, refused packets,
   `unfittable`, `unknown` and pending review. The 52 historical episodes
   cannot answer all reasoning-quality questions; **do not infer zero
   quality from unknown evidence**. For strict reasoning-quality judgments,
   first record a **new fully audited** cohort using
   `capstone.experiment` or `evaltools.traced_run`, and select only
   that cohort with `--require-full-traces`.
3. Export **blinded reference questions** from your prepared requests
   with `evaltools.reference_review export`. Review and import the answers
   independently **before** seeing SNAP answers. For sound/misleading RUN
   calibration, use a private `--run-strata` file, with at least one valid
   full trace in each category. No calibration is complete until you do
   this review.
4. Confirm your SubQ account exposes `subq-snap-1.1`, has available
   credits and provides a working `SUBQ_API_KEY` (not committed).
   SNAP's current official documentation confirms `POST /v1/systemone`,
   the named `noul|choice|score` question schema, `criteria` lists for
   score levels, `usage.input_tokens`, and zero output charge:
   https://docs.subq.ai/endpoints/decisions-api/
   and https://docs.subq.ai/using-the-api/models/.
   This is a **documentation-level** check; there has been no live,
   account-specific request or calibration.
5. Store the key in the git-ignored root `.env`, e.g.
   `SUBQ_API_KEY=...`, and verify this is not staged in Git.

## Independent calibration gate (rubric 1.1.1)

The next calibration sample should be **30–50 questions answered by the
developer**, blinded to SNAP and to Claude's earlier answers. Freeze the
selection and your answers before making any paid requests. Use a fresh sample
rather than the nine-item Claude review from 2026-11-08. That review is
model-generated diagnostic feedback, **not human ground truth**.

TL-01 was repaired in rubric 1.1.1: its question asks whether the access
boundary is enforced (true), aligning its instructions with its answer key.
Do not score or reuse human TL-01 answers prepared using the inverted 1.1.0
instructions.

The blind export now presents exactly the provider-visible instructions and
criteria, with the question ID added only for answer mapping. Its private
mapping is checked again on import. A FN or TL question whose test source,
decorator, or local helper context is incomplete must explicitly remain
unknown instead of receiving an invented judgment. Comparisons refuse answers
with different rubric versions or missing version provenance: answers under
1.0.0 and 1.1.0 are **not** pooled with 1.1.1.

The developer endorsed all 44 selections in the 2026-11-10 reviewer PDF as
final independent answers before any SNAP responses were viewed. The private
reference and PDF are held outside Git. Its two RUN cases both raise
reasoning concerns; it does not by itself calibrate sound versus misleading
RUN judgments or verify a repair.

After the developer submits the independent answers, run SNAP on precisely the
same versioned request bodies. Report agreement per question family, missing
or unanswerable questions, and disagreements for review; do not turn agreement
with Claude's earlier answers into an independent calibration statistic.

## Optional small live SNAP pilot — only when you choose to run it

From `evaluation/`, use the **same output directory** used to prepare
your dry run, and the same commit, archives, state budget and question
versions. Do not use a new directory when resuming an existing paid run:

```powershell
uv run --locked --all-extras python -m evaltools.full_evaluation `
  --commit $commit `
  --provider snap --snap-full-context `
  --env-file ../.env `
  --archive ../docs/benchmarks/2026-11-01-tot13-pairs `
  --archive ../docs/benchmarks/2026-11-02-audited-known-cases `
  --archive ../docs/benchmarks/2026-11-10-snap-calibration-pair `
  --out full-eval/snap-full-dry-run `
  --send --max-requests 5 --batch-size 5 --max-usd 0.10 --max-seconds 600
```

This command is **not** run by CI. `--max-requests` limits new posts
per invocation; `--max-usd` is a cumulative ceiling for this output
directory. The sender reserves up to **393,216 input tokens** for each
SNAP post and settles the reserve against measured usage. It does not
blindly retry an uncertain charge. Review `report.md` live stop reasons
and saved reservations before resuming. Change the archive options for a
new strict full-trace cohort, then use a new output folder and
`--require-full-traces`; do not send the historical record-only archive
under a false full-trace claim.

The SNAP provider currently lists **$0.04 per million input tokens**
and free output, but pricing, availability and account limits can change.
See https://docs.subq.ai/using-the-api/models/.

## What a successful run will and will not prove

It will produce verified provenance, unique packet identities, structured
FN/TS/TL/RUN/BT judgments, missingness, deterministic outcome reports,
and optional agreement with independently frozen reviewer answers.
It will **not** establish comprehensive functional correctness, live
machine reliability, model calibration, causal improvement, or 100%
statement/branch coverage. Keep those evidence categories separate.

**Status:** offline pipeline validation is enforced by CI; the paid SNAP
run and independent reference calibration are deliberately left for later.
