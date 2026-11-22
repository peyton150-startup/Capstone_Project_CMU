# 2026-11-21: deterministic triage arms and the first ranking batches

Two live batches of deterministic master triage arms, run by the developer one arm at a time in the kept Docker container (`triage-docker/triage-batch.ps1`). Each arm is one set of the 13 known-answer cases (KA-01 to KA-13), so 13 triages per arm.

Claude Code recorded them from the saved records. Ranking accuracy below was recomputed with `capstone.evaluation.ranking_accuracy` as of main after PR 338. No model was called to write this note.

## Where the data is

Everything the batches saved is in [`2026-11-21-triage-ranking/`](2026-11-21-triage-ranking/), one folder per batch and one per arm:

| File | What it holds |
|---|---|
| `compare.txt` (per batch) | The batch's side-by-side comparison table, as the script printed it (converted from UTF-16 to UTF-8) |
| `arms.txt` (per batch) | Arm label and the original run folder under `C:\Users\nicol\CapstoneRuns` |
| `config.json` | The commit and every setting the arm ran with |
| `*.records.jsonl` | One full record per triage: conclusion, model calls, ranking snapshot, raw ranking, verdict, scores |
| `*.report.txt` | The run's scored report |
| `*.failures.jsonl` | The failure log (`--failure-log`) |
| `*.audit.jsonl.gz` | The full trace (`--trace`), gzipped |
| `*.log.gz`, `tests-targeted.log.gz` | The run log and the targeted tests run in the container before the arm, gzipped |

`container.log` was left out: it repeats the run log with Docker's output around it.

## Setup

Shared by every arm: `TRIAGE=on`, `TRIAGE_THEN_DEEP=off`, `TRIAGE_RUN_MODE=deterministic` (Observe, Plan, Investigate, Hypothesize and Test are model-free; only Conclude asks a model, at temperature 0), 90 s, `STEP_QUESTIONS=1`, `DECIDE_CALLS=1`, `LINE_CONTEXT=off`, `STAGE_CONTEXT=off`, `MANUAL_STEP=on`, `TRIAGE_MODEL=nvidia/nvidia/nemotron-3.5-lightning-30b-a3b`, `--trace`, `--failure-log`.

| Batch | Code (main) | Ranking prompt | Arms |
|---|---|---|---|
| `batch-20261121-160326` (A) | `f9758c0` | version 2 (before PRs 336/337) | D0–D5, R0–R4 |
| `batch-20261121-191330` (B) | `0f2e006` (PRs 336 and 337) | version 4: only cause candidates may be ranked; context is shown apart | D0, R0, R1, R4 |
| `batch-20261122-125932` (C, 2026-11-22) | `0461597` (PR 338) | version 5: candidate ids as a schema enum | R0 ×2, R5 (Super 120B) ×2 |

| Arm | Change from D0 |
|---|---|
| D0-baseline | 8 reads, conclusion brief on, conclusion time cap on, thinking off |
| D1-reads6 | `TRIAGE_TOOL_CALLS=6` |
| D2-reads12 | `TRIAGE_TOOL_CALLS=12` |
| D3-no-brief | `TRIAGE_CONCLUDE_BRIEF=off` |
| D4-no-cap | `TRIAGE_CONCLUDE_CAP=off` |
| D5-thinking | `TRIAGE_MODEL_THINKING=on` |
| R0-ranking | `TRIAGE_RANKING=on` |
| R1-ranking-no-cap | ranking, `TRIAGE_CONCLUDE_CAP=off` |
| R2-ranking-no-brief | ranking, `TRIAGE_CONCLUDE_BRIEF=off` |
| R3-ranking-thinking | ranking, `TRIAGE_MODEL_THINKING=on` |
| R4-ranking-reads12 | ranking, `TRIAGE_TOOL_CALLS=12` |

## Results: the conclusion (all arms)

From each arm's `report.txt`. Root causes are "not judged": these batches were not labelled.

| Batch | Arm | Right recommendations | Unnecessary interventions | Resolved | Relevant evidence | Avg tool calls |
|---|---|---|---|---|---|---|
| A | D0-baseline | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| A | D1-reads6 | 4/13 | 0/13 | 3/13 | 77% | 10.3 |
| A | D2-reads12 | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| A | D3-no-brief | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| A | D4-no-cap | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| A | D5-thinking | 4/12 | 0/12 | 3/12 | 75% | 10.8 |
| A | R0-ranking | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| A | R1-ranking-no-cap | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| A | R2-ranking-no-brief | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| A | R3-ranking-thinking | 4/11 | 0/11 | 3/11 | 73% | 10.8 |
| A | R4-ranking-reads12 | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| B | D0-baseline | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| B | R0-ranking | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| B | R1-ranking-no-cap | 4/13 | 0/13 | 3/13 | 77% | 10.7 |
| B | R4-ranking-reads12 | 4/13 | 0/13 | 3/13 | 77% | 10.7 |

Timing and model calls, batch A (from `compare.txt`):

| | D0 | D1 | D2 | D3 | D4 | D5 | R0 | R1 | R2 | R3 | R4 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Model calls (time) | 13 (50 s) | 13 (37 s) | 13 (41 s) | 13 (41 s) | 13 (60 s) | 13 (213 s) | 15 (53 s) | 13 (67 s) | 14 (50 s) | 15 (250 s) | 17 (63 s) |
| Triage p50 / p95 | 3 / 17 s | 3 / 4 s | 4 / 6 s | 3 / 6 s | 4 / 18 s | 18 / 21 s | 4 / 10 s | 5 / 16 s | 4 / 7 s | 20 / 21 s | 6 / 9 s |
| Model conclusion | 13 | 13 | 13 | 13 | 13 | 12 | 13 | 13 | 13 | 11 | 13 |

Batch B: model calls 13 (49 s), 15 (70 s), 16 (53 s), 18 (68 s); p50 / p95 4 / 9 s, 5 / 11 s, 4 / 13 s, 4 / 20 s (D0, R0, R1, R4). Every arm in both batches: 0 timeouts, 0 unsafe clearances, all 13 held open by checks, evidence tests kept 2 open and closed 11.

**What it shows:** the conclusion is the same in every arm, as designed. The ranking does not change it, and neither do the reads, the brief or the cap at this size. Thinking (D5, R3) costs about 15 s a triage and loses one or two conclusions to the time limit.

## Results: the ranking (R arms)

Top-1: the true cause's candidate is ranked first. Top-2: it is one of the two picks. "Top-2 unforced" leaves out cases with exactly two cause candidates, where top-2 is automatic. Coverage: the true cause is among the candidates at all (KA-09 never is). By chance, with the candidates offered, top-1 is about 36% and top-2 about 72%.

### Batch A (prompt version 2)

| Arm | Accepted | Abstained | Rejected (reasons) | Top-1 | Top-2 | Top-2 unforced | Coverage |
|---|---|---|---|---|---|---|---|
| R0-ranking | 13/13 | 0 | 0 (-) | 10/13 (77%) | 11/13 (85%) | 89% | 92% |
| R1-ranking-no-cap | 13/13 | 0 | 0 (-) | 8/13 (62%) | 10/13 (77%) | 89% | 92% |
| R2-ranking-no-brief | 13/13 | 0 | 0 (-) | 7/13 (54%) | 9/13 (69%) | 78% | 92% |
| R3-ranking-thinking | 9/13 | 0 | 4 (conclusion_deadline_exceeded 4) | 4/13 (31%) | 5/13 (38%) | 60% | 92% |
| R4-ranking-reads12 | 13/13 | 0 | 0 (-) | 6/13 (46%) | 10/13 (77%) | 89% | 92% |

Per case (1 = ranked first, 2 = ranked second, . = ranked but missed, x = no accepted ranking, n = true cause not among the candidates):

| Arm | KA-01 bearing | KA-02 bearing | KA-03 batch | KA-04 batch | KA-05 setting | KA-06 setting | KA-07 false alarm | KA-08 false alarm | KA-09 challenge | KA-10 servo | KA-11 servo | KA-12 hydraulic | KA-13 hydraulic |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R0-ranking | 1 | 1 | 2 | 1 | . | 1 | 1 | 1 | n | 1 | 1 | 1 | 1 |
| R1-ranking-no-cap | 1 | 1 | 1 | 1 | . | . | 2 | 2 | n | 1 | 1 | 1 | 1 |
| R2-ranking-no-brief | . | 1 | 1 | 1 | . | . | 2 | 2 | n | 1 | 1 | 1 | 1 |
| R3-ranking-thinking | 1 | 2 | 1 | 1 | . | . | . | x | n | x | x | x | 1 |
| R4-ranking-reads12 | 1 | 1 | 2 | 1 | . | . | 2 | 2 | n | 1 | 1 | 1 | 2 |

### Batch B (prompt version 4)

| Arm | Accepted | Abstained | Rejected (reasons) | Top-1 | Top-2 | Top-2 unforced | Coverage |
|---|---|---|---|---|---|---|---|
| R0-ranking | 13/13 | 0 | 0 (-) | 8/13 (62%) | 12/13 (92%) | 89% | 92% |
| R1-ranking-no-cap | 8/13 | 2 | 3 (context_candidate_picked 1, evidence_reference_repeated 1, unknown_candidate_id 1) | 5/13 (38%) | 7/13 (54%) | 80% | 92% |
| R4-ranking-reads12 | 9/13 | 0 | 4 (context_candidate_picked 1, evidence_reference_invalid 1, unknown_candidate_id 2) | 6/13 (46%) | 8/13 (62%) | 86% | 92% |

| Arm | KA-01 bearing | KA-02 bearing | KA-03 batch | KA-04 batch | KA-05 setting | KA-06 setting | KA-07 false alarm | KA-08 false alarm | KA-09 challenge | KA-10 servo | KA-11 servo | KA-12 hydraulic | KA-13 hydraulic |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R0-ranking | 1 | 2 | 1 | 1 | 2 | 2 | 1 | 2 | n | 1 | 1 | 1 | 1 |
| R1-ranking-no-cap | 1 | 1 | 1 | 1 | x | 2 | x | 2 | n | 1 | x | x | x |
| R4-ranking-reads12 | 1 | x | 1 | x | x | 2 | 2 | x | n | 1 | 1 | 1 | 1 |

### Batch C (prompt version 5, 2026-11-22, R0 only, 2 repetitions)

The first arm of the R0 vs `R5-ranking-super` batch (`batch-20261122-125932`). It ran on main `0461597`, after PR 338 (prompt version 5: candidate ids as an enum in the answer schema, bracketed ids, valid ids listed in the correction). The full test suite passed in the container before it (3501 passed, 26 skipped). An earlier start of the same batch (`batch-20261122-124755`) stopped before any triage and saved nothing.

| Repetition | Accepted | Abstained | Rejected | Top-1 | Top-2 | Top-2 unforced | Coverage |
|---|---|---|---|---|---|---|---|
| r1 | 13/13 | 0 | 0 | 8/13 (62%) | 12/13 (92%) | 89% | 92% |
| r2 | 12/13 | 1 (KA-09) | 0 | 10/13 (77%) | 12/13 (92%) | 100% | 92% |
| **Both** | **25/26** | **1** | **0** | **18/26 (69%)** | **24/26 (92%)** | **94%** | 92% |

| Repetition | KA-01 | KA-02 | KA-03 | KA-04 | KA-05 | KA-06 | KA-07 | KA-08 | KA-09 | KA-10 | KA-11 | KA-12 | KA-13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1 | 1 | 1 | 1 | 1 | 2 | 2 | 2 | 2 | n | 1 | 1 | 1 | 1 |
| r2 | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 2 | n (abstained) | 1 | 1 | 1 | 1 |

Conclusion in both repetitions: 4/13 right recommendations, 0/13 unnecessary interventions, 3/13 resolved, 77% of relevant evidence, 10.7 tool calls on average: the same as every other arm.

**R5-ranking-super** (the same settings, `TRIAGE_MODEL=nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b`, thinking off), 2 repetitions:

| Repetition | Accepted | Abstained | Rejected (reasons) | Top-1 | Top-2 | Top-2 unforced | Coverage |
|---|---|---|---|---|---|---|---|
| r1 | 7/13 | 0 | 6 (evidence_reference_repeated 5, conclusion_deadline_exceeded 1) | 3/13 (23%) | 6/13 (46%) | 80% | 92% |
| r2 | 11/13 | 0 | 2 (evidence_reference_repeated 2) | 7/13 (54%) | 10/13 (77%) | 88% | 92% |
| **Both** | **18/26** | **0** | **8** | **10/26 (38%)** | **16/26 (62%)** | **85%** | 92% |

| Repetition | KA-01 | KA-02 | KA-03 | KA-04 | KA-05 | KA-06 | KA-07 | KA-08 | KA-09 | KA-10 | KA-11 | KA-12 | KA-13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1 | 1 | 1 | x | x | 2 | 2 | x | 2 | n | x | x | x | 1 |
| r2 | 1 | 1 | x | 1 | 2 | 1 | 2 | 2 | n | 1 | 1 | 1 | x |

Batch C side by side (from `compare.txt`):

| | R0 (Lightning 30B) | R5 (Super 120B) |
|---|---|---|
| Model calls (time) | 26 (99 s) | 49 (253 s) |
| Triage p50 / p95 | 4 / 7 s | 10 / 15 s |
| Ranking accepted / abstained / rejected / unavailable | 25 / 1 / 0 / 0 | 18 / 0 / 7 / 1 |
| Ranking corrected (saved) | 0 (0) | 23 (15) |
| Model conclusion | 26 | 26 |

Super 120B needed a correction in 23 of 26 triages, mostly for citing the same evidence id twice, and 8 rankings were still lost. The developer saw its questions repeatedly cut off by the question time limit. When it was accepted it was right first in 10 of 18 triages, against R0's 18 of 25. The conclusion was unchanged (4/13 right recommendations in both repetitions).

Corrections (from `compare.txt`): batch A R0 2 (2 saved), R1 0, R2 1 (1 saved), R3 2 (0 saved), R4 4 (4 saved); batch B R0 2 (2 saved), R1 3 (0 saved), R4 5 (1 saved).

## Findings

- **R0 is the best ranking arm in both batches.** Batch A: 77% top-1, 85% top-2. Batch B: 62% top-1, 92% top-2. Both are well above chance (36% / 72%).
- **Version 2 to 4 is not a clean comparison.** One set of 13 per arm. R0's top-1 fell by two cases and top-2 rose by one, within what a single repetition can move. Version 2 also let context candidates be picked, which the current scorer can never count as right.
- **Every change from R0 made the ranking worse:** no cap (R1), no brief (R2), thinking (R3: four conclusions out of time) and 12 reads (R4).
- **The setting cases are the weak spot.** KA-05 is missed in every batch-A arm, and KA-05/06 are at best second in batch B: the model ranks the material batch above the setting.
- **KA-09 cannot be ranked right.** Its true cause is never among the candidates (coverage 92%).
- **Batch B's rejections were mostly id format.** `unknown_candidate_id` rejections were ids like `TC1_machine_`, cut to the schema's 12 characters after the model copied the candidate line. PR 338 (prompt version 5) makes the ids an enum in the answer schema.
- **With version 5, R0 had no rejected ranking in 26 triages** (batch C): 25 accepted, and the one abstention was KA-09, the case whose true cause is never offered, which is the right answer there. Top-1 was 18/26 (69%) and top-2 24/26 (92%). Both top-2 misses are KA-09. KA-07/08 (false alarms) were second in both repetitions, and KA-05/06 were second in r1 and first in r2, so the remaining errors are order, not coverage.

## Next

Super 120B (R5) did worse than Lightning 30B (R0): mostly rejected answers and time cut-offs, not better picks. A bigger model on its own is not the next step. The developer's next comparison is Lightning 30B (R0) against Ministral 14B (`R6-ranking-ministral`, `TRIAGE_MODEL=mistral/ministral-14b-2512`). Typed numeric evidence per candidate (B2) remains open.
