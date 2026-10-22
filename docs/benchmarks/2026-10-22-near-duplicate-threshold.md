# Near-duplicate threshold: provisional measurement (2026-10-22)

**Result: 0.909 (provisional).** Refusing a new memory whose similarity to a
stored one with the same category, outcome and machine is at or above 0.909
caught 19 of 23 repeats and refused none of the 28 different lessons. The
margin is almost zero, and the data is drafted, so re-measure on real lessons
before relying on it. This is the plan in `docs/MVP_SCOPE.md`, "Near-duplicate
memory check", step "Measuring the threshold".

## Why provisional

- **Draft data.** The memory store held no lessons (no run had used
  `--memory --audit`), so Claude drafted 60 pairs in the real formats:
  anomaly kinds as categories, `replace_bearing` and `reset_setting`, machines
  `CNC-01` to `CNC-05`, and the code-written sentence for a failed repair.
  Real model-written lessons may vary differently.
- **Draft labels.** The developer asked Claude to go ahead, so the labels are
  Claude's (23 same, 28 different, 9 unsure), marked `labelled_by` in the data.
  The developer reviewed and approved them on 2026-10-22, so 0.909 stands for
  this data; it is provisional only because the lessons are drafted.

## How it was measured

`uv run python -m capstone.memory.duplicate_threshold --pairs
docs/benchmarks/near-duplicate-pairs.jsonl` embeds both sides of every pair
as passages with the configured model (`nvidia/nvidia/nemotron-3-embed-1b`,
2,048 numbers per text, live calls) and scores them by cosine similarity. The
text is what a stored memory is embedded as: category, symptoms, diagnosis,
lesson. Every 5th pair (12) was held out. The threshold is the smallest
three-decimal value above every "different" training pair; "unsure" pairs are
never used.

| | Same pairs caught | Different pairs refused |
|---|---|---|
| Training (48 pairs) | 18 of 21 | 0 of 19 |
| Held out (12 pairs) | 1 of 2 | 0 of 9 |
| All labelled pairs | 19 of 23 | 0 of 28 |

## Findings

1. **No safety margin.** The highest "different" pair scored 0.9089 (P57) and
   the lowest "same" pair caught scored 0.9091 (P43). Four repeats scored
   below it (0.877 to 0.905). A safer 0.92 still refuses nothing different
   but catches only 15 of 23.
2. **The held-out check is weak.** Only 2 of the 12 held-out pairs are "same",
   so it says little about catching repeats. It does show no different lesson
   refused (0 of 9).
3. **Compare the whole memory, not the lesson alone.** Embedding only the
   lesson sentence gives a threshold of 0.868 that catches 10 of 23. The
   highest "different" pair there is the two failure sentences that differ by
   one repair name (P13, 0.867), which the diagnosis then separates.
4. **The diagnosis pulls scores both ways.** Two lessons with the same
   diagnosis text score high even when the advice differs (P57: 0.909 whole,
   0.614 lesson only). Identical failure sentences with differently worded
   diagnoses score only 0.910 and 0.932 (P18, P22); the existing exact
   check catches those anyway. Real diagnoses are model-written and vary more
   than these drafts, so this is the main thing to watch when re-measuring.
5. **Unsure pairs that would be refused.** P02, P29 and P42 (0.929 to 0.940)
   pair lesson B5, which combines "one machine" with "the batch ran fine
   elsewhere", with simpler lessons. At 0.909 they count as repeats. The
   developer should decide whether that is wanted.

## Re-measuring on real lessons

Planned for 2026-10-23 (NVIDIA was down on 2026-10-22). The steps are in
`docs/PROGRESS.md`, "NEXT SESSION: re-measure the near-duplicate threshold".
In short: run episodes with `--memory --audit` into a separate local SQLite
store, build pairs from the stored lessons (same category, outcome and
machine), have the developer label them, and rerun the command above with
more held-out "same" pairs than this draft has. Record the model and
threshold again.

Data: [`near-duplicate-pairs.jsonl`](near-duplicate-pairs.jsonl) (readable
copy: [`near-duplicate-pairs.md`](near-duplicate-pairs.md)); every score:
[`2026-10-22-near-duplicate-scores.json`](2026-10-22-near-duplicate-scores.json).
