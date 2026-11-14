# Triage conclusion latency: findings (2026-11-14)

Sources: the developer's run folders `triage-main-all-20261114-143118` (brief on, plus fixed plan,
investigate, packet, evidence tests, hypothesis reserve 25 s) and
`triage-main-control-20261114-150656` (all off), from the
[afternoon runs](2026-11-14-triage-brief-and-reserve.md). 26 episodes each. Both had
DECIDE_REASONING_EFFORT=low and LATE_MODEL=Lightning 30B for decide only (LATE_CONCLUDE off).
Conclude chain: Super 120B first, then Command-A.

## The brief does not make the prompt or the answer much bigger

| conclude job, answered attempts | brief arm | control |
|---|---|---|
| prompt chars, mean | 16,640 | 15,531 (+7%) |
| input tokens, mean | 5,180 | 4,839 (+340) |
| Command-A output tokens / seconds | 240 / 4.0 s | 236 / 3.9 s |

Command-A writes the same size of answer in the same time with or without the brief.

## The time goes to Super's thinking, which fills whatever window it gets

- Super answers with 2,300–5,100 output tokens (mostly reasoning), at about 110 tokens/s, so it needs
  17–48 s. The JSON answer itself is about 200–400 tokens (Command-A's size).
- Super gets 2/3 of the time left (`TRIAGE_FIRST_SHARE`). With a 20 s window it is cut off at
  about 13.5 s, and Command-A answers in the remaining 3–6 s. Super answered first time 2 of 26 in
  control, 7 of 26 in the brief arm.
- So in a normal triage Super's 13 s are wasted and Command-A writes the conclusion (43 of 52
  conclusions over both arms).

## Why the brief arm averaged 37.5 s: research ended early, not the brief

| | brief arm | control |
|---|---|---|
| research ended early (`no_useful_action`) | 15 of 26, research over at **4.0 s** mean | 4 of 26, at 33.5 s |
| conclude seconds, early-end runs | 50.0 | 29.9 |
| conclude seconds, full-time runs | 20.5 | 17.8 |
| conclude seconds, all | 37.5 (max 64.5) | 19.6 (max 52.9) |

When research ends at ~4 s, the conclusion gets ~86 s; Super is given 2/3 of that (~58 s), thinks
for all of it, is cut off, and Command-A then answers. Control shows the same behaviour on its own
early ends (KA-01 r1: Super cut off at 47.9 s, conclude 52.9 s). Like for like (full-time runs),
the arms differ by ~3 s, and the brief arm's full-time runs also had slightly bigger windows
(research ended at 64.4 s vs 69.3 s). The "all" arm changes eight settings at once, so the brief's
own effect cannot be isolated; any effect on Super's thinking length is not measurable from 9
Super answers whose windows differed.

## Conclusion on the three suggested fixes

- **Shorter brief**: would save ~340 input tokens, well under a second. Does not address the cause. Not recommended.
- **Output cap (`max_tokens`)**: Super's output is reasoning before the JSON; a cap truncates it and
  returns no answer. Not recommended. (A thinking cap, `reasoning_budget`, is different, but whether
  Super honours it is unverified live.)
- **Window sized from measured time**: the window is already 20 s in normal runs and Command-A fits.
  The problem is the opposite: an early end hands Super ~86 s.

## Recommendation (a design choice for the developer: which model writes a triage conclusion)

1. **Decide whether Super should answer triage conclusions at all.** Measured: it needs 17–48 s and
   answers 2/24 times in a 20 s window. Choices:
   - a. Cap the triage conclusion question at `TRIAGE_CONCLUDE_SECONDS` even when research ends
     early (small code change in `conclude`/`seconds_for_question`). Saves ~30–45 s on early ends;
     Command-A keeps writing nearly every conclusion, as it does now.
   - b. Route the triage conclusion to a fast model first: either Command-A as CONCLUDE_MODEL for
     triage, or existing config `LATE_CONCLUDE=on` (Lightning, thinking off; but it only applies
     under LATE_MODEL_SECONDS=60 left, so early ends with ~86 s left still go to Super unless that
     threshold rises, which also moves every triage decide). Conclusion ~1–4 s; quality of the
     new author needs a live run.
   - c. Keep Super but cap its thinking (`reasoning_budget` / `reasoning_effort` low on conclude);
     needs one live check that Super honours it.
   Built: (a), as `TRIAGE_CONCLUDE_CAP` (on by default; off restores the old window). (b) and (c)
   stay open as live comparisons for the developer.
2. **Separate, bigger issue**: in the "all" arm research ended after ~4 s in 15 of 26 episodes
   (`no_useful_action`, investigate advice `no_candidate` / `no_live_explanation`). The triage used
   about 4 s of its 70 s research time. That, not the brief, drove the long conclusions. The
   repeated `get_line_screening` requests behind it are addressed separately (PR 266, refused
   repeats shown to the model).

No live runs: the figures come from the developer's records only.
