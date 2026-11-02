# Five audited known-answer cases, November 2, 2026

This archive contains one live, blind-critic ToT run at commit
`31ddd79eb3ab6a3bc0c01f43fb3b137348346394`. It covers **5 of 13** ordered
known-answer cases: KA-01-bearing, KA-02-bearing, KA-03-batch, KA-04-batch,
and KA-05-setting. The developer stopped the run by hand for time. Cases 6–13
were not run. This is one arm, so there is no paired comparison. **No accuracy
or improvement claim is made from these five cases.**

The run folder follows the pair archive layout: records, audit, Jev label
proposals, critic-pick proposals, Jev report, and configuration are beside
each other. `summary.json` names the source commit and raw counts; the
`manifest.json` SHA-256 hashes every archived file. The five audit entries
correspond to the five completed records; there is no partial sixth audit
entry. No original record or audit line was edited after the live run.

## Commands and configuration

From the isolated results worktree:

```text
uv sync --all-extras
uv run pytest -q
uv run python run_audited.py
uv run python continue_audited.py
uv run python label_audited.py
uv run python package_audited.py
```

The first command ran cases 1–4, then was interrupted after case 4 was saved
when the developer shortened the target to eight. The continuation checked
the four saved records and audits, then ran case 5. It was interrupted after
case 5 when the developer shortened the target again. The three run and label
scripts are saved verbatim as `.py.txt` files in the run folder. The packaging
script only created metadata and copied those scripts; it did not change raw
results. The `*.config.json` file records every effective non-secret setting,
budgets, source hashes, and the commands. Credentials came from the local
`.env` and are absent from the archive.

The setup matches the previous ToT13 blind arm: NVIDIA Nemotron 3.5 Super VL
120B investigator, Cohere Command A fallback, Mistral Ministral 14B critic,
Cohere critic fallback, critic and one bounded follow-up on, blind critic on,
semantic manual search with NVIDIA Nemotron 3 Embed 1B, one question per step,
no memory or hazards, and simulator approval policy `all`. The developer
explicitly allowed the embedding call. A fresh manual index was built at the
start; its path and the manual source hash are in the config. Provider responses
are nondeterministic even with the same scenario seeds and settings.

## What was observed

Jev proposed five diagnosis labels and two critic-pick labels. It flagged no
diagnosis label for review, so the saved report has five provisionally judged
cases. **No person reviewed those labels.** The report's raw count of three
correct labels is preserved for provenance, not used as an accuracy estimate.
Jev calls here were for the project's ordinary diagnosis-label step; no
EVAL-09 judge request was sent.

Across the five records, model calls logged 19 outage attempts: 18 timeouts and
one HTTP 500. Those are attempt counts, including retries and fallback tries,
not 19 failed episodes. Raw per-question attempts and unanswered questions
remain in the record files. The interrupted command left no partial audit
tail; the audit log has five entries. No sixth episode record exists.

These traces can supply evidence for the evaluator's RUN questions. They do
not cover a second arm, the remaining eight known cases, a human reference
set, or live verification of the evaluator's Jev request/answer contract.
