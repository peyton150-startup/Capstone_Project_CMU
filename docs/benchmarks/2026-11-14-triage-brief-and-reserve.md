# 2026-11-14 (afternoon): triage with the conclusion brief and hypothesis reserve

Second pair of live triage arms on 2026-11-14. These ran after PRs 260 (conclusion brief), 261 (comparison report), 262 (hypothesis reserve) and 264 (`end_value` metric fix) were merged. They follow [the morning's runs](2026-11-14-triage-all-blocks-vs-control.md).

The developer ran both arms in the kept Docker container, one at a time. Each arm was 2 sets of the 13 known-answer cases (26 triages per arm). Results are on the developer's machine in `C:\Users\nicol\CapstoneRuns\triage-main-all-20261114-143118` and `...\triage-main-control-20261114-150656`. Claude Code recorded them from the records, using `python -m capstone.experiment compare` and a short script over the records. No model was called to write this note.

## Setup

| | all | control |
|---|---|---|
| Code | main `0bfd9b4` | same |
| Shared | `TRIAGE=on`, `TRIAGE_THEN_DEEP=off`, 90 s, 6 tool calls, `STEP_QUESTIONS=1`, `DECIDE_CALLS=1`, `LINE_CONTEXT=off`, `STAGE_CONTEXT=off`, `MANUAL_STEP=on` | same |
| `TRIAGE_PLAN` / `TRIAGE_INVESTIGATE` | fixed / on | model / off |
| `TRIAGE_PACKET` / `_PROMPT` / `TRIAGE_EVIDENCE_TESTS` | on / on / on | off / off / off |
| `TRIAGE_CONCLUDE_BRIEF` | on | off |
| `TRIAGE_HYPOTHESIS_SECONDS` | 25 | 0 |

The targeted triage tests passed in the container before each arm: 342 passed. The full suite was skipped.

## Results (26 triages per arm; morning arms for reference)

| | all (pm) | control (pm) | all (am) | control (am) |
|---|---|---|---|---|
| How research ended | 15 no useful action, 9 tool budget, **2 timeout** | 20 timeout, 4 no useful action, 2 max iterations | 19 timeout | 24 timeout |
| Triage seconds, p50 / p95 | **67 / 86** | 87 / 89 | 87 / 90 | 87 / 88 |
| Hypothesize asked (hypotheses formed) | **11** | 11 | 20 | 10 |
| Reserve stopped research | 3 of 26 | (off) | (not in code) | (not in code) |
| Conclusion: mean / max seconds | **37.5 / 64.5 s** | 19.6 / 52.9 s | 18.3 s | 17.3 s |
| Model assessment | 7 supported, 18 unresolved, 1 refused | 5 supported, 21 unresolved | 6 supported | 6 supported |
| Final recommendation | escalate 26/26 | escalate 26/26 | escalate 26/26 | escalate 26/26 |
| Model proposed `no_action` | 1: KA-08 r1, a false alarm (right) | 2: **KA-01 r2 (bearing fault)**, KA-08 r2 (false alarm) | 1 (false alarm) | 4, two on real faults |
| Cleared without a model conclusion | 0 | 0 | 0 | 0 |
| Report refused | 1 (KA-12 r1) | 0 | 2 (`end_value`, fixed by PR 264) | 0 |
| Repeated reads of `get_line_screening` | **59** | 36 | 38 | — |
| Runs where research stopped right after a repeated screening read | **22** | 11 | 16 | — |
| Investigate compiler: compiled / model | 2 / 88 | — | 8 / 86 | — |
| Relevant evidence collected (mean share) | 41% | 35% | 50% | 44% |

Root causes were **not judged**, because no hand labels exist for these runs. The checks held every `no_action` proposal open, so no triage cleared anything.

## What this shows

1. **Research now ends early instead of at the time limit, but for the wrong reason.** With every block on, only 2 of 26 triages timed out (19 in the morning). Most ended with "no useful action". The model asked for `get_line_screening` again (the evidence packet had already read it) until the repeat guard stopped research. That happened in 22 of 26 triages, and 59 times in total. Because research stopped before hypothesize, hypothesize was asked only 11 times, against 20 in the morning. The reserve stopped research only 3 times, because research rarely ran long enough to reach it.
2. **The conclusion got about twice as slow with the brief** (37.5 s mean, up to 64.5 s, against 18–20 s without it). It still answered every time, because research ended early and left it time. With research that runs to its limit, the 20 s kept for the conclusion would not be enough.
3. **One refusal is a new kind.** On KA-12 r1, the conclusion named a hypothesis ID although hypothesize had never run, and the checks refused it ("the conclusion names a hypothesis that was never formed"). No `end_value` refusals happened in either arm.
4. **Safety held.** The control's model again proposed `no_action` on a real bearing fault (KA-01 r2), and the checks held it open. With every block on, the only `no_action` proposal was on a real false alarm.
5. **The investigate compiler still almost never compiles** (2 of 90 turns).

## Follow-ups

- Stop research from asking again for a no-argument read it already holds (`get_line_screening`). Today the repeat counts toward the stop rule and ends research before hypothesize.
- Do not let a conclusion cite a hypothesis when none was formed. Either the brief says so plainly, or the selected ID is dropped instead of refusing the whole answer.
- Look at why the conclusion is slower with the brief (larger output), and whether the 20 s conclusion window needs to change with it.
