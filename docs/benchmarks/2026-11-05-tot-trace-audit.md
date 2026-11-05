# Offline audit of the 13-case ToT traces

Audited November 5, 2026 from the [two archived 13-case pairs](2026-11-01-tot13-pairs/README.md). This is a read-only analysis of 52 previously saved live episodes. It made no model calls, changed no labels or scores, and did not replay the simulator. All four runs used frozen commit `e59208d584938ed96a606bc317354882fcc8e01c`; their operational disruptions and comparison limits are described in the archive.

## Where the tree was reached

| Pair and critic mode | Episodes | Trees saved | Candidates generated | Kept | Dropped as “impossible” | Dropped by rank |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A anchored | 13 | 7 | 35 | 19 | 10 | 6 |
| A blind | 13 | 8 | 40 | 22 | 8 | 10 |
| B anchored | 13 | 6 | 30 | 14 | 10 | 6 |
| B blind | 13 | 12 | 60 | 33 | 15 | 12 |
| **Total** | **52** | **33** | **165** | **88** | **43** | **34** |

Each saved tree contains five generated candidates. Nineteen episodes have no saved tree. In 16, the model-call log has no `hypothesize` question: the run ended earlier (nine `model_unavailable`, seven `timeout`). In the other three, one `hypothesize` question was attempted and received `no_answer` (two `timeout`, one `model_unavailable`). **No archived episode shows an answered generate call followed by a failed value call.** Thus missing trees in this sample primarily reflect earlier-stage availability or time loss, rather than a demonstrated value-stage failure. A missing tree is not evidence that no cause could have been generated.

The 43 “impossible” drops have a cited factory evidence ID under the frozen pruning rule. The archive does not establish that each citation semantically contradicts its candidate. The 34 rank drops are deferred alternatives, not refuted causes. None of the saved trees lists an `unresolved` candidate; that field only records a kept `impossible` rating without a factory contradiction, so zero does not mean every investigation was resolved.

## Compound-fault case: a candidate lost at the width cap

KA-09's hidden answer has **bearing degradation and a wrong setting on CNC-07**. The first alarm instead comes from a transient CNC-03 vibration spike. Pair A anchored saved no tree: its generate call got no answer. Pair A blind saved a tree focused on CNC-03 and generated no CNC-07 candidate. In pair B anchored, C5 proposed that the real fault might be on an unchecked machine including CNC-07; in pair B blind, C5 similarly named uninspected CNC-04–07. Both C5 candidates were rated `likely` but ranked below the top three and deferred. Neither named both actual faults, so retaining C5 alone would not prove a correct diagnosis.

In B blind, the critic's `alternative` objection explicitly mentioned dropped C5. The recorded follow-up obtained one `get_sensor_summary` result for CNC-04, CNC-06 and CNC-07 during the alarm window. The leading H1 then rose from 0.92 to 0.95, and the final answer still explained only CNC-03. This shows that exposing a deferred candidate to the critic can raise the omission, but one observation and the present controller did not recover the two CNC-07 causes in this run. The saved record does not prove whether the new summary contained enough information to do so.

## What to build and measure next

1. **Fix the earlier-stage reachability problem before adding a second ToT depth.** Most missing trees occurred before the generate question. Measure where time and provider attempts were spent, then test a bounded routing or budget change without altering the historical runs. The new `value` job proposed by [P5](../TOT_CRITIC_EVALUATION_FUTURE_WORK.md#p5--bounded-second-depth-through-observation-not-more-model-reasoning) would not have helped those 16 episodes.
2. **Evaluate deferred alternatives separately from hard eliminations.** P1's top-three cap discarded both broad unchecked-machine candidates in the compound case. A bounded multi-cause retention rule is worth testing, but it must reserve enough calls to check retained alternatives and preserve the action/verification budget. The archived data alone cannot establish that a fourth survivor would improve diagnosis.
3. **Use a matched, clean experiment for any accuracy claim.** Compare the changed policy with its frozen baseline on the same seeds, with the four held-out labels reviewed and provider/manual availability recorded. Track tree reachability, cause generation, cause retention, final diagnosis, calls and wall time separately. The existing anchored/blind pairs had outages and overlap, so their differing tree counts are descriptive, not a causal effect of critic mode.

## Reproduction

Counts were derived from each archived `master-tot13-{anchored,blind}.records.jsonl`: `thoughts` supplies generated/kept/dropped candidates; `model_calls.details` distinguishes a missing generate attempt from a `no_answer`; `score.termination_reason` supplies the run ending. KA-09's C5, critic objection, `recheck` and conclusion were read from the same pair B records. Original records, reports and Jev proposals remain unchanged.
