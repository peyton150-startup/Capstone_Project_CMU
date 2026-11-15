# 2026-11-14 (evening): triage with Ministral 14B in place of Command-A

Third pair of live triage arms on 2026-11-14, run after PRs 268 (screening questions answered from the packet), 269 (the investigate compiler reads the fixed plan's predicates) and 270 (`TRIAGE_CONCLUDE_CAP`) were merged. They follow [the afternoon's runs](2026-11-14-triage-brief-and-reserve.md).

The developer ran both arms in the kept Docker container, one at a time: 2 sets of the 13 known-answer cases, so 26 triages per arm. Results are on the developer's machine in `C:\Users\nicol\CapstoneRuns\triage-main-all-ministral-20261114-190059` and `...\triage-main-control-ministral-20261114-201458`. Claude Code recorded them from the run logs and records. No model was called to write this note, apart from the two one-word test calls described below.

## Why Ministral

The first evening `all` run (`triage-main-all-20261114-180130`, main `240973d`) is discarded:
- In set 1, all 13 triages ended with no model answer. Command-A answered 3 times and returned HTTP 429 61 times.
- In set 2, the developer's internet also dropped during KA-06. Every call after that returned "could not be reached".

A one-call test of Command-A then returned HTTP 429 with Cohere's message that the trial key is limited to 1,000 API calls a month. Across this month's triage runs, the logs show about 610 answered Command-A calls, and other runs used the key as well.

For this test only, the developer swapped the fallback to Ministral 14B. The run command added `-Set "FALLBACK_MODEL=mistral/ministral-14b-2512,CRITIC_FALLBACK_MODEL=mistral/ministral-14b-2512"`. `.env` and the code still name Command-A, which comes back once the key allows calls again. A one-call test of Ministral 14B answered with HTTP 200 before the runs. The control run that was started on the exhausted key was stopped during its targeted tests, before any model call.

## Setup

| | all | control |
|---|---|---|
| Code | main `240973d` | same |
| Models | NVIDIA Super 120B first, then Ministral 14B (`FALLBACK_MODEL`), Lightning 30B | same |
| Shared | `TRIAGE=on`, `TRIAGE_THEN_DEEP=off`, 90 s, 6 tool calls, `STEP_QUESTIONS=1`, `DECIDE_CALLS=1`, `LINE_CONTEXT=off`, `STAGE_CONTEXT=off`, `MANUAL_STEP=on` | same |
| `TRIAGE_PLAN` / `TRIAGE_INVESTIGATE` | fixed / on | model / off |
| `TRIAGE_PACKET` / `_PROMPT` / `TRIAGE_EVIDENCE_TESTS` | on / on / on | off / off / off |
| `TRIAGE_CONCLUDE_BRIEF` / `TRIAGE_HYPOTHESIS_SECONDS` / `TRIAGE_CONCLUDE_CAP` | on / 25 / on | off / 0 / off |

Before each arm, the targeted triage tests passed in the container (387 passed). The full suite was skipped.

## Results (26 triages per arm)

| | all | control | all, Cohere (afternoon, `0bfd9b4`) |
|---|---|---|---|
| Model conclusion / no model answer / refused | 13 / 12 / 1 | 8 / 18 / 0 | 25 / 0 / 1 |
| Runs judged (a required question answered) | 14 | 8 | 26 |
| Right recommendations, of judged | 5 / 14 | 4 / 8 | 8 / 26 |
| How research ended | 20 timeout, 3 no useful action, 3 tool budget | 17 timeout, 8 no useful action, 1 tool budget | 15 no useful action, 9 tool budget, 2 timeout |
| Hypothesize ran out of time | 22 | 6 | |
| Triage seconds, p50 | 89–90 | 90 | 67 |
| Calls refused as repeats | **9** | 28 | 61 |
| `get_line_screening` calls | **61** | 47 | 111 |

Model outcomes, counted over every attempt in the logs:

| | all | control |
|---|---|---|
| Ministral 14B: answered / cut off / HTTP 429 / skipped after 429 / wrong shape | 56 / 58 / 20 / 42 / 2 | 28 / 64 / 2 / 0 / 4 |
| Super 120B: answered / cut off | 4 / 98 | 2 / 60 |
| Lightning 30B: answered / cut off | 10 / 74 | 2 / 58 |

The table also counts the answers to the start-of-run model checks.

## What it shows

- **The NVIDIA models almost never answer a triage question inside its time limit.** This is not new tonight. In every 2026-11-14 run, Super answered 2–4 times and was cut off 52–98 times, and Lightning answered 2–20 times and was cut off 26–74 times. Command-A had been writing nearly every answer. With Command-A gone, more than half the triages ended without a model conclusion.
- **Ministral 14B does not replace Command-A here.** It was cut off about as often as it answered. Mistral's rate limit refused it 20 times in the `all` arm, which then skipped it 42 more times. It sent 6 replies of the wrong shape:
  - `numeric_claims[].metric` with a value outside the allowed list;
  - `new_questions[].hypothesis_id` as a non-string;
  - `contradicting_evidence_ids` as a non-list.
- **PR 268 shows in the records.** In the `all` arm, calls refused as repeats fell from 61 (afternoon) to 9, and `get_line_screening` calls from 111 to 61.
- **The `all` arm ran out of time at hypothesize 22 times, against 6 in control.** With this few model answers, the fixed plan's extra reads and slow models cannot be told apart.
- **These arms do not compare `all` with control.** With 14 and 8 judged triages, the recommendation counts are noise. Neither arm shows the effect of PR 270's conclude cap or PR 269's compiled reads, because few runs reached those steps with a model answering.

## Next

- Rerun both arms once Command-A answers again (monthly reset or a new key), or with a fallback that answers inside the triage's limits.
- The NVIDIA cut-offs need their own look. They happen in every run, whichever fallback is set.
