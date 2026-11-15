# 2026-11-15: triage with `TRIAGE_MODEL` set to Lightning 30B, thinking off

This is the first live pair of triage arms with PR 272's `TRIAGE_MODEL` setting. It follows [the 2026-11-14 Ministral runs](2026-11-14-triage-ministral-swap.md).

The developer ran both arms in the kept Docker container, one at a time: 2 sets of the 13 known-answer cases, so 26 triages per arm. Results are on the developer's machine:
- `C:\Users\nicol\CapstoneRuns\triage-main-all-lightning-20261115-131113`
- `C:\Users\nicol\CapstoneRuns\triage-main-control-lightning-20261115-134426`

Claude Code recorded them from the run logs and records. No model was called to write this note.

> **Corrected on 2026-11-15.** The first version of this note said Lightning 30B answered no triage question and Ministral wrote every answer. That was wrong. The log count missed Lightning's answers and counted each cut-off twice: 94 and 52 against 47 and 26 in the records. The model table and the findings below now come from each record's `model_calls` (every triage question, without the start-of-run checks). The other figures are unchanged.

## A first pair that did not count

An earlier pair the same morning (`triage-main-*-lightning-20261115-093757` and `-103337`) ran on the same code, but `TRIAGE_MODEL` was not in its settings:
- the run header has no `RUN: triage model` line;
- Super 120B was still asked first, and was cut off 100 and 72 times;
- the control run also lost its network in set 2, KA-11 to KA-13.

It is set aside. The pair below passed `TRIAGE_MODEL` through the Docker script's `-Set`, so `config.json` records it.

## Setup

| | all | control |
|---|---|---|
| Code | main `5e4f47e` (PR 272) | same |
| `TRIAGE_MODEL` / `TRIAGE_MODEL_THINKING` | `nvidia/nvidia/nemotron-3.5-lightning-30b-a3b` / off | same |
| `FALLBACK_MODEL` | `mistral/ministral-14b-2512` (run-only; the Cohere trial key is out of calls for the month) | same |
| Shared | `TRIAGE=on`, `TRIAGE_THEN_DEEP=off`, 90 s, 6 tool calls, `STEP_QUESTIONS=1`, `DECIDE_CALLS=1`, `LINE_CONTEXT=off`, `STAGE_CONTEXT=off`, `MANUAL_STEP=on` | same |
| `TRIAGE_PLAN` / `TRIAGE_INVESTIGATE` | fixed / on | model / off |
| `TRIAGE_PACKET` / `_PROMPT` / `TRIAGE_EVIDENCE_TESTS` | on / on / on | off / off / off |
| `TRIAGE_CONCLUDE_BRIEF` / `TRIAGE_HYPOTHESIS_SECONDS` / `TRIAGE_CONCLUDE_CAP` | on / 25 / on | off / 0 / off |

Both run headers show `RUN: triage model nvidia/nvidia/nemotron-3.5-lightning-30b-a3b (every triage question; thinking off)`. Before each arm, the targeted triage tests passed in the container (412 passed). Neither arm had a "could not be reached" error.

## Results (26 triages per arm)

| | all | control |
|---|---|---|
| Model conclusion / no model answer | 26 / 0 | 26 / 0 |
| Right recommendations | 8 / 26 | 8 / 26 |
| Resolved | 6 / 26 | 6 / 26 |
| Unnecessary interventions | 0 | 0 |
| Relevant evidence collected (set 1 / set 2) | **46% / 51%** | 23% / 28% |
| Calls refused as repeats | **10** | 53 |
| `get_line_screening` calls | 62 | 71 |
| Triage seconds, p50 (set 1 / set 2) | **52 / 53** | 68 / 71 |
| Timed out (set 1 + set 2) | 1 + 4 | 5 + 6 |
| How research ended | 20 timeout, 3 no useful action, 3 tool budget | 12 no useful action, 9 timeout, 3 tool budget, 2 max iterations |

Model outcomes, over every attempt at a triage question (from the records' `model_calls`):

| | all | control |
|---|---|---|
| Lightning 30B: answered / cut off / wrong shape / HTTP 502 | **92** / 47 / 1 / 0 | **159** / 26 / 3 / 1 |
| Lightning: mean seconds when it answered / when cut off | 2.6 s / 16.9 s | 2.0 s / 25.2 s |
| Ministral 14B: answered / cut off / wrong shape | 19 / 8 / 3 | 12 / 9 / 1 |
| Questions answered by Lightning / Ministral | 92 / 19 | 159 / 12 |
| Lightning's answers by job | decide 41, hypothesize 25, conclude 26 | plan 26, decide 100, hypothesize 7, conclude 26 |

The triage's own `termination_reason` in the records reads differently from the "How research ended" row above:
- all: 20 `max_tool_calls`, 5 timeout, 1 no useful action;
- control: 11 timeout, 9 no useful action, 4 max iterations, 2 `max_tool_calls`.

## What it shows

- **Lightning 30B with thinking off answered most triage questions, quickly, but stalled on about a third.** It wrote 92 of 111 answers in `all` and 159 of 171 in control, every conclusion included. When it answered it took 2–2.6 s. When it did not, it waited until the question's time limit cut it off, 17–25 s on average. That left Ministral too little time on some decide questions. In `all`, 24 of 88 decide questions got no answer.
- **Ministral 14B answered only after a Lightning cut-off:** 19 answers in `all` and 12 in control, about 10 s each.
- **The `all` arm gathers about twice the relevant evidence.** It collected 46–51% against 23–28%, and it repeats far fewer calls: 10 against 53, so PR 268's fix holds. It also finished about 15 s sooner at p50.
- **Final recommendations are the same in both arms:** 8/26 right, 6/26 resolved and no unnecessary intervention. The extra evidence did not change what the triage recommended.
- **Ministral's one recurring wrong shape:** `interpretation.hypotheses[].contradicting_evidence_ids` not given as a list (8 times across both arms).

## Next

- Lightning either answers in a few seconds or stalls. A short time limit on its attempt (about 6–8 s) before falling back would leave the fallback room to answer.
- In `all`, 25 of 26 triages ended unresolved with the fixed plan's record questions (events, settings, follow-up sensor) still open. PRs 274 (`TRIAGE_OBSERVE_CALLS`) and the investigate compiler's planned reads address that.
- Rerun on Command-A, or another fallback that answers in time, once the Cohere key allows calls again.
