# 2026-11-14: triage with every new block on vs the A0 control

Live runs by the developer, in the kept Docker container (`triage-docker.ps1`). Each arm ran the 13 known-answer cases twice (26 triages per arm), one arm at a time. Results are on the developer's machine in `C:\Users\nicol\CapstoneRuns\triage-main-all-20261114-104837` and `...\triage-main-control-20261114-112954`.

Recorded by Claude Code from those records and reports. No model was called to write this note.

## Setup

| | all | control |
|---|---|---|
| Code | main `41c11fe` (PR 259 merged) | same |
| Shared settings | `TRIAGE=on`, `TRIAGE_THEN_DEEP=off`, 90 s, 6 tool calls, `STEP_QUESTIONS=1`, `DECIDE_CALLS=1`, `LINE_CONTEXT=off`, `STAGE_CONTEXT=off`, `MANUAL_STEP=on` | same |
| `TRIAGE_PLAN` | fixed | model |
| `TRIAGE_INVESTIGATE` | on | off |
| `TRIAGE_PACKET` / `TRIAGE_PACKET_PROMPT` | on / on | off / off |
| `TRIAGE_EVIDENCE_TESTS` | on | off |
| Not in this code | PR 260 (conclude brief), PR 261 (comparison report), PR 262 (hypothesis reserve) | same |

The pre-run triage tests passed in the container for both arms. The full suite was skipped (`-SkipFullSuite`).

## Results (26 triages per arm)

| | all | control |
|---|---|---|
| Hypothesize question asked | **20 / 26** | 10 / 26 |
| First hypothesis formed (r1, r2) | 5/13, 9/13 (p50 33 s, 54 s) | 3/13, 3/13 (p50 61 s, 40 s) |
| Rival hypothesis tested | 3 | 0 |
| Plan model question | 0 (fixed table) | 26, 29.4 s mean, 367 s and 397 s per set |
| Ended by timeout | 19 | 24 |
| Ended by tool budget / no useful action | 4 / 2 | 1 / 1 |
| Final recommendation | escalate 26 / 26 | escalate 26 / 26 |
| Supported conclusions | 0 | 0 |
| Final clearances (`no_action`) | 0 | 0 |
| Model proposed `no_action` | 1 (KA-07 r2, a false alarm: right) | 4: KA-07 r1, r2 (false alarm: right), **KA-01 r1 (bearing fault), KA-13 r2 (hydraulic leak)** |
| Report outcome | 23 model conclusion, 2 refused, 1 no model answer | 26 model conclusion |
| Cleared without a model conclusion | 0 | 0 |
| Model questions per set (answered) | 73 (62), 79 (65) | 89 (76), 95 (84) |
| Cut off by a question's time limit | 48, 41 | 48, 43 |
| Answered by a fallback model | 29, 26 | 31, 26 |
| Factory reads observed / repeated | 164 / 40 | 128 / 38 |
| Relevant evidence collected | 51%, 44% | 41%, 38% |
| Mean seconds per triage | 87–88 | 85–88 |

Mean model seconds per question:

| | all | control |
|---|---|---|
| decide | 13.4 s (106 questions, 12 unanswered) | 7.1 s (122, 16 unanswered) |
| hypothesize | 17.6 s (20, 10 unanswered) | 13.2 s (10, 8 unanswered) |
| conclude | 18.3 s (26, 3 unanswered) | 17.3 s (26, 0 unanswered) |

Block-specific lines, from the run reports:

| Block | Set 1 | Set 2 |
|---|---|---|
| Evidence tests (Block 3) | changed an outcome in 2; 7 questions closed by a measured verdict, 1 kept open | changed an outcome in 4; 8 closed, 3 kept open |
| Evidence tests (Block 3), rival question | 1 conclusion held open | 1 conclusion held open |
| Investigate compiler (Block 4, on) | 45 turns: replaced decide 4 times, no candidate 39 | 49 turns: replaced 4, no candidate 41 |

Root causes: **not judged.** No hand labels exist for these runs, and the report counts 0/0. "Right recommendations" is 4/13 in every set of both arms. Every final answer was escalate, and escalate is the right recommendation on the four cases that expect it.

## What this shows

1. **The fixed plan does what it was built for.** It removed a 29 s average plan question, which used about 380 s per set. That time went to the stages after it: hypothesize was reached twice as often (20 vs 10 of 26), and hypotheses formed earlier.
2. **Safety held in both arms.** No triage cleared anything. In the control, the model twice proposed `no_action` on a real fault: KA-01 r1 (bearing) and KA-13 r2 (hydraulic leak). The Python checks held both open. With every block on, the model proposed `no_action` only once, on KA-07, which really is a false alarm. That is fewer unsafe proposals, though two sets are too few to call it an effect.
3. **Timeouts are still the norm** (19 of 26 vs 24 of 26). Decide questions got slower with every block on (13.4 s vs 7.1 s). They had more time to spend, since plan no longer used it, and the evidence packet makes their prompts longer.
4. **Two answers were refused, both for the same bug.** On KA-01 r2 and KA-08 r2, the conclusion model wrote `end_value` as a numeric-claim metric. That is a Block 3 predicate statistic, and the conclusion schema only accepts `minimum`, `maximum`, `mean`, `delta` or `sample_count`. Either the schema accepts `end_value` or the prompt stops using that word. This needs a fix.
5. **The investigate compiler rarely compiles** (no candidate in 80 of 94 turns). It only compiles a question that names exactly one sensor on a known machine, and the fixed plan's questions mostly don't.
6. **The evidence packet's reads were repeated by research** (40 repeated reads vs 38 in the control, with more reads overall). Research does not yet treat packet readings as already gathered for the questions they answer.
7. **The 7th "tool call" is the manual search.** Factory reads stayed within the 6-call budget.

## Not covered

- PRs 260 (conclude brief) and 262 (hypothesis reserve, 25 s, on) were not in this code. They are next, together, with the next Docker script.
- Root-cause accuracy needs hand labels. The comparison command in PR 261 will report them as "not judged" until labels exist.
- Two sets per arm is a small sample. Model cut-offs vary from run to run.
