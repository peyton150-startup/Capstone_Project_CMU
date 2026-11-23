# 2026-11-22 ranking triage and deep follow-up runs

## Source and scope

Local run batch: `C:\Users\nicol\CapstoneRuns\batch-20261122-165008` (`arms.txt`, `compare.txt`). The five run folders named below contain config, per-repeat records, audit, logs and reports. These are live model runs, not scripted tests. No new run was made for this note.

R0, R6, R5 and R7 each cover the same 13 named KA cases twice (26 triages per arm). All use deterministic triage, fixed plan, eight triage research calls, a 90-second triage budget, manual step on, conclude brief on and ranking on. Deep follow-up is disabled in all four ranking arms. R0/R6 used main `c16d53c`; R5/R7 used later main `c91567c`. Thus the R0/R6 versus R5/R7 differences cannot be attributed solely to model choice. R5 and R7 share a code revision and model; the explicit setting difference is `TRIAGE_CONCLUDE_CAP=on` versus `off`.

| Arm and local folder | Conclusion model | Accepted / abstained / rejected / unavailable ranking | Corrected (saved) | Decide calls | Triage p50 / p95 |
| --- | --- | --- | --- | --- | --- |
| R0 `triage-R0-ranking-20261122-165008` | Nemotron 3.5 Lightning 30B | 23 / 2 / 0 / 1 | 1 (1) | 27, 95 s | 4 / 8 s |
| R6 `triage-R6-ranking-ministral-20261122-171918` | Ministral 14B | 23 / 0 / 1 / 2 | 4 (1) | 30, 215 s | 8 / 21 s |
| R5 `triage-R5-ranking-super-20261122-172936` | Nemotron 3.5 Super VL 120B | 19 / 0 / 7 / 0 | 23 (16) | 49, 227 s | 9 / 15 s |
| R7 `triage-R7-ranking-super-no-cap-20261122-173816` | Nemotron 3.5 Super VL 120B | 20 / 0 / 6 / 0 | 24 (18) | 50, 233 s | 10 / 14 s |

The counts are those printed by `compare.txt`; “corrected” and “saved” are its separate ranking counters, not scored root-cause accuracy. In R5/R7 the six or seven rejected rankings were reported as `evidence_reference_repeated`; the validation boundary declined those outputs. R6's report shows Ministral was sometimes skipped after a recent refusal and Command A answered instead, so R6 is not a pure Ministral result. R5 also records a Command A fallback on one conclusion.

## Outcomes and limitations

Across each 26-run ranking arm: 26 deep runs were requested, zero ran because `TRIAGE_THEN_DEEP=off`; 26 fixed plans, zero model plans; evidence tests ran on all 26, with four questions kept open and 22 closed; 0 unsafe clearances, 0 clearances without a model conclusion, and 0 timeouts. R0 had one episode with no model answer. Model conclusions were present in 25/26 R0 and 26/26 of each other arm. Checks held 25 R0, 25 R6, 26 R5 and 25 R7 open. One R7 episode was supported. These are safety/continuation observations, not evidence of correct diagnoses.

No root causes were labeled in any arm: 0 right, 0 wrong, **26 not judged** per arm. The report's `0/0` cause and machine metrics therefore cannot be read as zero accuracy or perfect accuracy. The aggregate “wrong-machine 0 of 0” also has no scored denominator. The 13-case reports show the same recommendation pattern across arms: four appropriate interventions among twelve single-fault cases, three resolved, with no interventions for the two bearing, two setting, two servo or two hydraulic cases; the two batch and two false-alarm cases account for the four actions. KA-09's two-fault challenge collected 0/5 relevant evidence in each repeat. Setting cases collected 1/3 each. The deterministic read path is identical in these reports (139 triage reads per repeat, zero repeated or failed), so changing the ranking conclusion alone did not address those evidence gaps.

R5/R7 have far more corrected rankings than R0/R6, while using roughly twice the decide calls and about twice to three times the median triage time. R5 versus R7 is too close and small to justify removing the conclusion cap: 23 (16 saved) versus 24 (18 saved), with 9 versus 10 second median. R7's p95 was 14 seconds versus R5's 15 seconds; latency is noisy at this sample size. The cap-off arm did not demonstrate a material safety or accuracy advantage because diagnoses are unlabeled.

## Separate deep follow-up

`triage-F0-deep-4cases-20261122-174708` ran four KA cases once, with triage off, Super VL as default model, critic and critic follow-up on, a 600-second model-question allowance and five retries. Its combined source included `feature/deep-run-budgets` (`353f50e`) on main `c91567c`, so it is not directly comparable with a ranking arm. It made 99 model questions (94 answered, five invalid replies, two timed-out attempts), averaged 1,008 seconds per episode, collected 91% of relevant evidence, recommended two appropriate interventions and resolved two cases. All four root causes remained unjudged. KA-01 bearing and KA-05 setting did not resolve; KA-04 batch and KA-07 false alarm resolved. The KA-04 final conclude reply was cut off at the output-token limit despite the reported resolution. The invalid replies were three wrong-shape `$defs` responses and two output-token cutoffs. This suggests that the long deep path needs targeted reliability and cost review before wider use.

## Candidate fixes to evaluate next (none implemented here)

1. **Label the 104 ranking conclusions before choosing an arm.** Use the existing label-book flow and inspect records/audits for each case. Score correct root cause, target machine/batch and whether a correction improved the final answer. A “saved” ranking is an internal counter, not proof of a true causal win. Keep labels blind to arm if practical.
2. **Study the repeated-evidence rejection in R5/R7.** Sample the six to seven rejected packets, identify whether the model duplicated one evidence reference or the contract/prompt made duplication likely, then test a minimal prompt or structured-output repair offline. Preserve the rejection guard; never count one observation twice to inflate support.
3. **Address the shared evidence bottleneck separately.** Trace why KA-05/06 setting cases stop with only 1/3 relevant evidence and KA-09 with 0/5 despite 139 successful reads per repeat. Compare deterministic read selection and available observable channels against the case requirements before adding budget or model calls.
4. **Check whether ranking-correction calls earn their cost.** R5/R7 use about 49–50 decide calls versus R0's 27. After labeling, compare only corrections that improve a true outcome against added seconds/calls. A selective correction trigger is a candidate if many calls do not help.
5. **Keep the conclusion cap pending a paired, labeled comparison.** The R5/R7 pair gives no strong reason to turn it off. Verify same case seeds and code, label results, and look at deadline failures and tail latency.
6. **Repair deep-response reliability before scaling F0.** Reproduce wrong-shape `$defs` and truncated conclude outputs with saved prompts and bounded offline tests. Investigate per-stage token limits and schema handling; measure whether the 600-second allowance and five retries produce useful outcomes or mainly extend runs.

## Verification, gate, and status

This is documentation of existing live runs. Source checked: batch `arms.txt` and `compare.txt`, five `config.json` files and their per-repeat `*.report.txt` summaries. No simulator or agent code changed; no tests or real model calls were run for this PR. Findings are observational and the proposed fixes are unimplemented. Developer understanding of these findings has not been checked; pause for review before selecting a code change. The run folders are local and are not copied into the repository, so a remote reviewer cannot independently inspect raw records until a suitable safe artifact is attached or summarized.