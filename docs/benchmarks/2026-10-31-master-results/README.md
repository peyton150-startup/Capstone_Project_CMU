# October 30–31 master experiments

Seven saved live master runs, 35 episodes, are archived here. These are real
provider runs executed by the developer, not scripted tests. This archive adds
results and notes only; it does not change code or rerun episodes or Jev.

## Latest ToT comparison

Both run-2 files now contain five unique episodes. Their original two episodes
match their before-resume backups byte for byte; three episodes were appended to
each. Each episode used the manual. All three appended episodes in each run have
saved ToT thoughts. The critic-off run contains no critique; the critic answered
in all three appended critic-on episodes, using Ministral 14B.

| Case | Seed | Critic off | Critic on |
| --- | --- | --- | --- |
| KA-01-bearing | 6 | Wrong | Wrong |
| KA-03-batch | 7 | Wrong | Wrong |
| KA-05-setting | 9 | Wrong / no committed diagnosis | Jev label needs review |
| KA-07-false-alarm | 8 | Correct | Correct |
| KA-09-challenge | 3 | Wrong | Wrong |

Critic off is **1/5 (20%)**; critic on is **1/4 judged (25%), with one case
awaiting review**. Both have one confirmed correct case. These percentages have
different denominators and are not evidence that the critic improves accuracy.
Among just the three appended cases, off is 1/3 and on is 1/2 judged plus one
awaiting review. The challenge contains bearing degradation and a wrong setting;
both agents instead concluded a transient sensor disturbance, at confidence 0.90.
The critic favoured that incorrect explanation in the critic-on challenge.

The critic's extra evidence step did not execute a tool in any appended case:

| Case | Critic | Follow-up outcome |
| --- | --- | --- |
| Setting | Objected; favoured an incorrect common-cause explanation | Skipped: no tool calls left |
| False alarm | Objected; favoured the correct transient explanation | Policy stopped without a tool call |
| Challenge | No objection; favoured an incorrect transient explanation | Skipped: leading hypothesis already at action bar |

Thus this pair exercises critic review, but does not demonstrate successful
critic-driven evidence gathering or correction. No verdict/pick mismatch flag
was recorded in these three critiques. The critic's objections and manual sections
are preserved in the raw records for review.

## Reliability of the appended episodes

| Measure, last three episodes only | Critic off | Critic on |
| --- | --- | --- |
| Model questions | 69 | 72 |
| Answered | 69 | 71 |
| Invalid replies | 0 | 1 |
| Unanswered questions | 0 | 0 |
| HTTP 429 attempts | 0 | 0 |
| HTTP 422 attempts | 0 | 0 |
| HTTP 500 attempts | 3 | 1 |
| Timeout attempts | 2 | 1 |

Retries/fallbacks recovered the listed outages. The on-run invalid reply occurred
in the false-alarm episode: a `call_tool` step omitted its tool. Do not conflate
these appended-episode counts with the older first two episodes, which retain
timeouts, invalid replies and HTTP 422 records from before the fixes.

## All archived runs

Every run has five episodes. Correctness is taken from the saved provisional Jev
report, not inferred from prose by this archival task.

| Run name | Correct / judged | Needs review | Qualification |
| --- | --- | --- | --- |
| master-manual-20261030-115707 | 2/4 (50%) | 1 | Original report unlabelled; separate saved Jev report archived |
| master-manual-critic-followup-20261030-131716 | 1/4 (25%) | 1 | Overlapped with other critic run; no saved config |
| master-manual-critic-followup-parallel-20261030-131537-83a5d0cf | 2/5 (40%) | 0 | Overlapped with other critic run; no saved config |
| master-tot-critic-off-run-1 | 0/5 (0%) | 0 | Provider failures; not a clean ToT accuracy baseline |
| master-tot-critic-on-run-1 | 1/5 (20%) | 0 | Provider failures; only one answered critique |
| master-tot-critic-off-run-2 | 1/5 (20%) | 0 | Two old episodes plus three after fixes/settings changes |
| master-tot-critic-on-run-2 | 1/4 (25%) | 1 | Two old episodes plus three after fixes/settings changes |

**All seven saved runs use the same ordered seeds: 6, 7, 9, 8, 3.** In
particular, the run called `parallel` did not use a different simulator seed set.
Different model responses do not make these independent simulator seed samples.

The original manual-only `.report.json` has no labels. Its separate
`.jev-report.json`, previously saved in the Codex worktree, supplies the 2/4
provisional result above. Both are preserved. No new label was requested from Jev
while preparing this archive. Cases marked for review remain unjudged.

## Configuration and comparison limits

The original `master-manual-20261030-115707.config.json` supplies the ordered case
IDs, seeds and fault kinds. It is not a full execution-environment snapshot for
the other runs. No missing configuration has been reconstructed and presented as
an original. Early overlapping critic runs violate the project's one-live-run
rule; any effect on outages is unmeasured.

For run 2, the saved resume configs specify ToT, semantic manual, manual step on,
one question per step, NVIDIA Nemotron 3.5 Super VL as investigator, Cohere
Command A as its fallback, and Mistral Ministral 14B as critic with its own Cohere
fallback. Critic time is 40 seconds and follow-up time is 90 seconds. The only
on/off configuration difference in those snapshots is critic and follow-up.

The last three episodes ran after [PR #145](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/145)
(Cohere JSON mode) and [PR #146](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/146)
(sampling and critic backup settings). Sampling snapshots are NVIDIA 1.0/0.95,
Cohere 0.3/0.75, and Mistral 0/service-default top_p. The first two saved episodes
were not rerun. These are mixed-configuration continuations, not fresh five-case
baselines. Resume timestamps indicate off began at 14:09 and on at 14:45 on
October 31, America/New_York; off's report was saved before on began.

The generated `summary.json` contains per-case outcomes, seeds, manual and ToT
counts, provider reliability and follow-up states. It is derived from source
files and is not a substitute for the complete raw records.

## Provenance and verification

`manifest.json` lists 23 original source files, their byte lengths and SHA-256
hashes. All were copied unchanged: seven raw runs, eight reports (including the
extra manual-only Jev report), three label files, one original case config, two
resume configs, and two before-resume backups. The source field distinguishes
the experiment checkout from the previously saved Codex-worktree Jev report.
No `.env`, credentials or API keys are included. The original files remain in
place.

Validation parsed every JSON/JSONL artifact, checked all seven raw runs against
the configured case order/seeds, confirmed five unique run keys each, matched
each report to its raw cases, and verified both backup prefixes. Some saved
report text already contains Windows encoding artifacts (for example `µ`
rendered as `Âµ`). The exact affected cases are listed as
`report_text_encoding_differences` in `summary.json`. Every differing conclusion
matches its raw counterpart after a CP1252-to-UTF-8 decoding correction; the
archive preserves the original bytes instead of silently rewriting them.

Tests were not rerun for this results-only documentation change. No source code,
evaluation rules, original labels, original reports or original results changed.
No new model calls were made. Understanding status is unchanged; these notes do
not claim a teaching gate was completed.

## Remaining work

- Review the three setting-case labels currently held out: manual-only, the
  first non-ToT critic run, and ToT critic-on run 2.
- Investigate the setting-case route interpretation and the common-cause
  explanation; do not silently replace provisional labels to improve a score.
- Investigate why critic follow-up adds no evidence in this pair, especially
  tool-budget exhaustion and policy refusal to run the critic's check.
- Run fresh matched-seed baselines under one fixed configuration if a causal
  critic/ToT comparison is required. Further seed sets are needed for broader
  claims.
- Blackout and degraded matrices are not part of these seven archived runs.
