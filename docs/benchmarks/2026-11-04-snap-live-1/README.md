# 2026-11-04: first full live Snap evaluation (exploratory, uncalibrated)

The Snap half of the full-project evaluator, run live once over the whole plan.
Snap is SUBQ's `subq-snap-1.1`. Jev was not run: its live sending stays blocked
until Gate C.

**Status: exploratory and uncalibrated.** There are no independent human
reference judgments yet (EVAL-10 / F07). The numbers below therefore say what
Snap answered, not whether Snap is right. This is not a completed full-project
evaluation.

## How it was run

- **Code:** commit `0ca0b16` (PR #174, stacked on #172), with no uncommitted
  tracked changes. Rubric 1.0.0, packet schema 1.3.0, normalize 1.1.0.
- **Evidence:** archives `2026-11-01-tot13-pairs` and
  `2026-11-02-audited-known-cases`. That is 57 episodes: 5 with full traces and
  52 record-only. The truth check refused 0 packets.
- **Who ran it:** Claude Code, at the developer's direction in the session.
  AGENTS.md §12 normally gives live runs to Codex.
- **Slices:** two, run from `evaluation/`.

  ```
  uv run python -m evaltools.full_evaluation --commit <sha> \
    --archive ../docs/benchmarks/2026-11-01-tot13-pairs \
    --archive ../docs/benchmarks/2026-11-02-audited-known-cases \
    --provider snap --env-file <git-ignored .env> --out full-eval/snap-1 \
    --send --max-requests 20 --max-usd 0.50 --max-seconds 600   # slice 1
    # slice 2: --max-requests 2296 --max-usd 1.00 --max-seconds 86400
  ```

  Slice 1 sent 20 requests and stopped on the request limit. Slice 2 resumed
  and sent the other 2,276, then stopped with the plan complete.
- **Timing:** answers were saved between 21:50 and 22:44 UTC. Slice 2 itself
  took about 11 minutes.

## Spend and completeness

| | |
|---|---|
| Requests | 2,296 sent, each answered on its first attempt |
| Answers | 6,564, all with a value (0 empty) |
| Model reported | `subq-snap-1.1` for every answer |
| Spend | **$0.311** measured, under the $1.00 cumulative cap; the dry run estimated $0.43 |
| Ledger | 7,504 rows: 6,564 answered, 726 unknown, 214 not applicable |

"Unknown" rows are questions the evidence can't answer. Examples are trace
questions for record-only episodes, and FN-02/FN-03 where a function's test
sources were cut to fit the budget. They are not failures.

## What Snap answered

| Question | n | Result |
|---|---|---|
| BT-01 comparison valid | 2 | valid, valid |
| BT-02 sample rule | 2 | insufficient_sample, insufficient_sample. This agrees with the rule in code. |
| RUN-01 / RUN-02 (reasoning, 1–5) | 5 each | means 3.96 / 3.85. Only the 5 full-trace episodes could be judged. |
| RUN-03 intervention | 46 | effective 31, ineffective 8, unknown 5, not required 2 |
| RUN-11 critic feedback | 46 | used 28, ignored 13, no feedback 5 |
| RUN-07 failure source | 46 | unknown 31, none observed 6, tooling 5, critic 3, retrieval 1 |
| FN-01 implementation matches contract | 749 | mean 0.71; 202 below 0.5 |
| FN-02 failure paths covered | 550 | covered 219, partly 78, uncovered 35, n/a 218 |
| FN-03 evidence sufficient | 550 | sufficient 341, insufficient 148, n/a 61 |
| TS-01 / TS-02 (tests) | 1,482 each | means 0.95 / 0.97 |
| TL-01..03 (tools) | 17 each | means 1.00 / 0.93 / 0.76 |

The lowest FN-01 scores are small helpers, for example `baseline._seeds`,
`memory_comparison.searches`, `RandomSource.seed` and
`UnreliableProvider._fire`. These scored about 0.01 to 0.02. The rubric says
to answer false when a function has no docstring or variable block. A
function with no docstring and no variable block counts as having "no
contract", so these low scores may point to missing documentation rather than
to wrong code. That has not been checked by a person.

The correctness rates in `report.md` (for example 3/12 and 6/13) are
**deterministic**. They come from the code comparing each episode with its
hidden ground truth, not from Snap.

## Files

- **`report.md` / `report.json`:** the evaluator's report for this run,
  including provenance, scope, deterministic correctness, comparisons,
  reliability, judging counts and live budget.
- **`ledger.jsonl`:** one row per (item, question), with its status and
  request fingerprint.
- **`answers.jsonl`:** one line per request, holding its tags and normalized
  answers. Each answer has a value, confidence, probabilities, latency, input
  tokens and cost. The repeated question text is dropped from the tags; it is
  defined by rubric 1.0.0 in `evaltools`. The raw replies are dropped too,
  because they duplicate the normalized answers.
- **`scope_manifest.json`:** which repository files were inventoried, which
  were excluded and why.

The request bodies themselves (about 41 MB) are not committed. They can be
rebuilt from the pinned commit and the two archives, and each answer's
`request_fingerprint` identifies the exact body that was sent.

## Checks made before archiving

- **Key:** no file here, or in the run's output folder or logs, contains the
  API key value.
- **Request bodies:** scanned for case names (`KA-0…`), fault labels and truth
  fields. The only matches were the agent's own hypotheses and the public
  manual's list of repairs. The fault-naming `item_id` sits in the local
  `tags`, which are never posted; only `body` is sent.
