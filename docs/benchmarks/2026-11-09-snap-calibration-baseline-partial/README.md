# Partial audited SNAP calibration baseline (November 9, 2026)

This is a **source-evidence archive** for the first **10 completed** cases of a 13-case known-answer model-backed baseline run. The live command was interrupted by the operator during case 11. The 10 completed records and 10 corresponding audit records were saved intact. **There is no completed case-11 record or audit entry.**

The run was reported to have originated at pinned source commit `c49fdd60884d874a6d7877590d2be9ab1b7eb70e` (SNAP rubric **1.1.1**). The source commit is **operator-attested, not embedded in the source JSONL records**. The original .env was not captured or committed; a complete environment snapshot from collection time cannot now be reconstructed. Its results are **not** human-reviewed labels, a completed 13-case benchmark, a matched A/B experiment, or frozen SNAP calibration data. No live SNAP calibration calls were made as part of this archive.

## Original files

- `pair-01/baseline.records.jsonl`: 10 complete experiment records, preserved without edits
- `pair-01/baseline.audit.jsonl`: 10 corresponding full investigation audit records, preserved without edits
- `summary.json`: source revision, archive-reader metadata, scope and missing cases
- `validation.json`: original `run_packet` summary and strict trace preflight result
- `manifest.json`: SHA-256 hashes and byte sizes of the two original JSONL files
- `case_status.json`: per-case observed provider timeouts and unanswered calls, model IDs, stop reasons, and conservative final-conclusion screening flags
- `check_archive.py.txt`: zero-dependency, read-only verification script; stored as `.py.txt` to avoid changing inventoried Python source

Outages affected **all 10 cases**: there were **36 model-service timeout attempts** and **7 unanswered questions**. Three cases (KA-01, KA-06, KA-10) terminated on the investigation time budget, and KA-04 ended with `model_unavailable`. KA-05's saved conclusion starts "Investigation in progress"; KA-04 and KA-09 report "undetermined". Consequently only **4** of the 10 cases pass the neutral `conclusion_final` screening flag (KA-02, KA-03, KA-07, KA-08). This flag is **not** a diagnostic-quality label and does not establish the applicability of a SNAP rubric question. The model call details identify NVIDIA Nemotron 3.5 Super VL, Command A, and Ministral 14B attempted/used across decisions and critiques, but do not reproduce the complete environment.

The files are **simulated factory investigations**, not data collected from a real shop. No local `.env` or API credentials were archived.

## Collection configuration and limits

Observed run configuration: `python -m capstone.experiment run --name baseline --known --manual keyword --approve all --stage-context off`, with the audit log enabled. Console and record evidence show blind Critic with follow-up on, no Tree of Thoughts or simulated hazards, `DECIDE_CALLS=3`, and NVIDIA decision reasoning effort low. Other settings were inherited from the operator's local `.env`; a complete non-secret settings snapshot was **not** captured. Do **not** claim controlled treatment comparability without verifying that snapshot independently.

Case order was KA-01 through KA-10 from `evals/scenarios.json`. Case 11 (KA-11-servo) was started but interrupted; KA-12 and KA-13 were not started. This batch is **partial**. **Do not append a restarted 13-case run onto either archived file**, and do not present it as one arm of an uninterrupted matched-pair comparison.

## Reproduce the packet generation and strict preflight

Use a separate clean checkout of the original commit for source-bound evaluation. From its `evaluation` directory, with this archive present under `docs/benchmarks` in that checkout:

```powershell
uv run --locked --all-extras python -m evaltools.run_packet `
  --archive "../docs/benchmarks/2026-11-09-snap-calibration-baseline-partial" `
  --out "full-eval/2026-11-09-baseline-packets"
```

Then verify the generated `*.json` packets:

```powershell
uv run --locked --all-extras python -c "from pathlib import Path; from evaltools.run_packet import RunEvidencePacket; from evaltools.audit_preflight import require_full_traces; folder=Path('full-eval/2026-11-09-baseline-packets'); p=[RunEvidencePacket.model_validate_json(f.read_text(encoding='utf-8')) for f in folder.glob('*.json') if f.name != 'BATCH_SUMMARY.json']; require_full_traces(p); print(f'PASS: {len(p)} audited packets')"
```

The operator's actual `run_packet` results: **10 runs; 10 full traces; 0 refused**. The strict `require_full_traces` check printed **`PASS: 10 audited packets`**. These are trace-quality checks, not labels or performance estimates. `judged: 0` means no diagnosis labels were supplied. To run the read-only archive identity/integrity check from the repository root:

```powershell
uv run --locked --all-extras python docs/benchmarks/2026-11-09-snap-calibration-baseline-partial/check_archive.py.txt
```

**Metric provenance:** `judged: 0` means no human diagnosis label is attached. `recommendation_correct: 3` is determined by the simulator's scenario ground truth, not a human reviewer. The `run_packet` and `require_full_traces` success results were reported by the operator; the archive integrity script checks raw digests, run/audit identity and model statistics separately.

The derivable per-run SNAP packet JSON is deliberately **not duplicated** in this source archive; regenerate it from the canonical records and audits using the pinned implementation.

## Calibration status

This partial archive may supply candidates for RUN evidence, but **not** BT-01 or BT-02: there is no matched treatment arm and no completed 13-case pair. A separate single-case no-fault pilot exists outside this archive, and the audited cohort still lacks a performed repair with post-action sensor verification. Keep private calibration selection/strata mappings separate from blinded reviewer exports. Reviewers must never be given `score`, `evaluator_only`, source scenario labels, or other hidden-truth fields; use `reference_review export` on saved dry-run request bodies.

## Public archive / blinding caveat

This repository and PR branch are **public**. Original record fields include hidden simulator ground truth (e.g., `score.true_fault` and fault-bearing scenario identifiers). A blinded reviewer could search for distinctive conclusion text and discover the answer. **Holding this PR as draft does not make its uploaded raw files private.** Treat this as potential reference contamination: use reviewers who explicitly agree not to consult the repository, document that limitation, and consider keeping future calibration source archives private until the human reference is frozen. The run selection/strata labels must remain outside the reviewer export. No calibration judgment was made here.

**Do not send live SNAP calibration requests until an eligible cohort has been exported, independently human-reviewed, imported and frozen.**
