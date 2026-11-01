# Two completed 13-case ToT anchored/blind pairs

Archived November 1, 2026. Four live runs, **52 episodes**, completed in the
developer's terminal. This is a results-only archive: no model calls, new Jev
judgments, scoring changes or original-file edits were performed while archiving.

Pair A is `tot13-20261031-184429-543214a2`.
Pair B is `tot13-20261031-210256-3910997b`.
Each pair's subdirectory keeps its source files separate.

## Provisional results

| Pair | Critic | Correct / judged | Reported accuracy | Labels awaiting review |
| --- | --- | --- | --- | --- |
| A | Anchored | 3/12 | 25.0% | KA-05-setting |
| A | Blind | 3/12 | 25.0% | KA-07-false-alarm |
| B | Anchored | 6/13 | 46.2% | None |
| B | Blind | 6/11 | 54.5% | KA-02-bearing, KA-04-batch |

**Neither pair has more confirmed correct diagnoses in blind mode.** Pair B's
higher blind percentage excludes two uncertain labels; it is not evidence of
improvement. On cases judged in both arms of a pair, the counts are also tied:
3/11 in each arm of A, and 6/11 in each arm of B. Different individual cases
were solved, so equal totals do not mean identical behavior. These are small,
same-seed, disruption-affected comparisons, not causal estimates of blinding.

| Case | Seed | A anchored | A blind | B anchored | B blind |
| --- | --- | --- | --- | --- | --- |
| KA-01-bearing | 6 | Right | Wrong | Wrong | Wrong |
| KA-02-bearing | 9 | Wrong | Wrong | Wrong | Review |
| KA-03-batch | 7 | Wrong | Wrong | Wrong | Right |
| KA-04-batch | 8 | Right | Wrong | Wrong | Review |
| KA-05-setting | 9 | Review | Wrong | Wrong | Wrong |
| KA-06-setting | 10 | Wrong | Wrong | Wrong | Wrong |
| KA-07-false-alarm | 8 | Wrong | Review | Right | Wrong |
| KA-08-false-alarm | 11 | Wrong | Wrong | Right | Right |
| KA-09-challenge | 3 | Wrong | Wrong | Wrong | Wrong |
| KA-10-servo | 16 | Wrong | Right | Right | Right |
| KA-11-servo | 13 | Wrong | Right | Right | Right |
| KA-12-hydraulic | 4 | Right | Right | Right | Right |
| KA-13-hydraulic | 15 | Wrong | Wrong | Right | Right |

The stored Jev labels remain provisional and unchanged. No held-out label was
silently converted to a correct or incorrect answer to equalize denominators.

## Frozen configuration and identity

All four runs pin commit `e59208d584938ed96a606bc317354882fcc8e01c`, the
[PR #152](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/152)
merge, including #150's reasoning/completion changes and #149's new cases/manual
1.3. They do not use later main changes, including #154's progress-view update.

Both use the same ordered 13 cases and seeds, ToT (five candidates, breadth
three), semantic manual and automatic manual step, critic and follow-up on,
one-question steps, no episodic memory, no hazards, and the normal simulator
experiment `approve_all` policy. Models are NVIDIA Nemotron 3.5 Super VL with
Cohere Command A fallback, and Ministral 14B critic with its own Cohere fallback.
Sampling is NVIDIA 1.0/0.95, Cohere 0.3/0.75, Mistral 0/service-default top_p.
Manual embeddings use NVIDIA Nemotron Embed 1B. Critic time is 40 seconds;
follow-up time is 90 seconds. Every actual setting and budget is preserved.

Within each pair, the effective settings differ only in `CRITIC_BLIND`.
Between pairs, the only public-setting difference is the isolated `CHROMA_PATH`.
Code, case/lock/manual/runner hashes, Python version and budgets match. Each
original `run-pair.py` is saved as `run-pair.py.txt`; its bytes match the runner
hash in the corresponding shared config. No credentials are stored in these
configs or runner texts.

**Raw run keys repeat between pairs**, because both launchers use the names
`master-tot13-anchored` and `master-tot13-blind`. The unique identity is
`(pair_id, run_key)`. Do not concatenate label books into a single dictionary
keyed only by run key: one pair would overwrite the other. There are 52 unique
composite identities, with 13 unique run keys inside each individual run.

Only the configured treatment changes within a pair. The treatment is the
entire blind mode: shuffled neutral labels, hidden confidence/leader markers,
its prompt and code-derived verdict. It does not isolate each of those changes.
Provider nondeterminism and availability remain uncontrolled.

## Reliability and actual manual access

| Measure | A anchored | A blind | B anchored | B blind |
| --- | --- | --- | --- | --- |
| Model questions | 223 | 223 | 208 | 285 |
| Answered | 211 | 212 | 198 | 276 |
| Invalid replies | 3 | 1 | 1 | 2 |
| Unanswered | 9 | 10 | 9 | 7 |
| Timeout attempts | 19 | 18 | 17 | 27 |
| Unreachable attempts | 28 | 30 | 42 | 0 |
| HTTP 429 attempts | 0 | 0 | 0 | 4 |
| HTTP 502 attempts | 0 | 0 | 0 | 1 |
| Investigator manual searches answered | 10 | 11 | 9 | 13 |
| Investigator manual searches failed | 4 | 2 | 4 | 0 |

Attempts are not questions: retries/fallbacks can recover an attempt failure.
All four 429 attempts occurred on NVIDIA in B blind, KA-13-hydraulic; the 502
also came from NVIDIA, in KA-04-batch. They are distinct from the internet
interruption the developer reported. The overlap below is not proof of what
caused those errors.

Failed investigator manual searches:

- A anchored: KA-08, KA-09, KA-10, KA-11.
- A blind: KA-03, KA-06.
- B anchored: KA-02, KA-03, KA-05, KA-06.
- B blind: none recorded; all 13 automatic searches answered.

Thus these were configured manual-on runs, **not four manual-off runs**. Access
was intermittently lost, and a successful lookup does not establish that its
sections were relevant or correctly applied. These counts describe investigator
search records only. Separate critic manual-section lookups are not fully
represented by them; empty critic section lists do not identify the cause.

## Critic follow-up and finishing

| Outcome | A anchored | A blind | B anchored | B blind |
| --- | --- | --- | --- | --- |
| Critic answered | 9 | 10 | 9 | 11 |
| Critic invalid reply | 0 | 0 | 0 | 2 |
| Critic not run | 4 | 3 | 4 | 0 |
| Follow-up gathered evidence | 6 | 9 | 6 | 8 |
| Follow-up reused evidence | 3 | 1 | 1 | 3 |
| Follow-up returned no evidence | 0 | 0 | 2 | 0 |
| Follow-up skipped | 0 | 0 | 0 | 2 |

The separate follow-up allowance now does gather observations, unlike the
previous three-case continuation. That does not prove those observations
corrected a diagnosis. B blind's two invalid critiques were extra schema fields:
`discriminating_check_explanation` in KA-06 and
`discriminating_check_expected_outcomes` in KA-07. Their follow-ups were skipped.
Other invalid answers include missing/forbidden step fields, invalid JSON and
output-token truncation; the raw records and derived summary retain the reasons.

**All 52 final recommendations were `escalate`.** Of the completion assessments,
39 were `unresolved` and 13 were absent (for example fallback/undetermined endings).
None was recorded as `supported`. Some diagnoses are labelled correct while
their completion remains unresolved; diagnosis correctness is separate from
action authorization or successful repair. These runs do not demonstrate an
effective end-to-end autonomous repair policy. Both setting cases and the
compound challenge remain unsolved under the saved confirmed labels.

## Timing, overlap and maintenance

Times below are America/New_York, **EDT (UTC−04)**, before the November 1 DST
fallback. Starts use the variant config file's original write time; finishes use
the completion marker, including the short Jev-labelling step.

| Run | Start | Finish |
| --- | --- | --- |
| A anchored | Oct 31 18:45:13 | Oct 31 20:57:02 |
| A blind | Oct 31 20:57:02 | Oct 31 23:15:28 |
| B anchored | Oct 31 21:03:20 | Oct 31 23:06:53 |
| B blind | Oct 31 23:06:53 | Nov 1 01:54:41 |

Each pair was sequential internally, but the pairs overlapped after the
developer explicitly requested removal of the other-run guard. A blind overlaps
B anchored for about 123.54 minutes, then B blind for about 8.59 minutes. This
departs from the normal one-live-run protocol and limits clean comparison.

At the developer's request, A's active manual collection was re-embedded in
place twice, at Oct 31 20:27:41–20:27:48 and 20:30:24–20:30:30 EDT. Both records
report the same model/collection, 17 sections, a non-deleting upsert and three
verified matches. The first was performed by Codex; the source folder also
contains the second completed event. Both events and their before-upsert
document/vector backups are preserved. The actor of the second event is not
inferred from its file alone.

The original config files stayed frozen, but **index maintenance occurred during
A anchored**. Therefore A was not operationally uninterrupted even though model
and corpus names stayed the same. Re-embedding did not repair earlier saved
episodes or eliminate the online query-embedding dependency. B had its own
separate index, so A's rebuild did not rebuild B's index. Neither pair should be
presented as a clean outage-free confirmation that blinding improves reasoning.

## Provenance and validation

`manifest.json` records byte lengths, SHA-256 hashes and original UTC modification
times for 36 original artifacts. JSON/JSONL source artifacts and runner text are
copied unchanged. `.gitattributes` prevents Git newline conversion from changing
their committed bytes. `summary.json` is derived, includes each case's outcomes,
review state, outages, gaps and follow-up record, and uses pair-separated identity.

Validation checked all four complete markers and reports, 13 unique episodes per
run, matching case order/seeds/fault configuration, all 52 unique composite keys,
report accuracy/denominators, saved-label/report equality, source/config/manual/
lock/runner hashes and the single within-pair settings difference. Files were
decoded explicitly as UTF-8; report conclusions match the raw records exactly.
No locale-decoding artifacts were treated as source corruption.

This archive does not recalculate scores against a newer simulator, relabel
uncertain cases, alter original records or launch new live requests. Local pytest
was skipped under the project's results/docs-only rule; archive validation and
committed-blob hash checks provide the relevant local verification, and the PR
still requires green CI before merge.

Remaining work: review the four held-out labels, investigate unresolved endings
despite apparently useful evidence, and assess manual availability/critic schema
failures before a clean, non-overlapping matched comparison. Keep those fixes and
future runs separate from this historical archive.
