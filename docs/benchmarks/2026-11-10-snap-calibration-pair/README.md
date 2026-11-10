# SNAP calibration pair, 2026-11-10

This archive freezes one interrupted 10-case baseline and one completed
13-case treatment from the simulator master run. The four JSONL files are
copied byte-for-byte from the operator's local calibration folder; their
SHA-256 hashes are in `manifest.json`. Each records file has a matching
audit file, and all 23 episode keys validated through `evaltools.run_packet`.

The two arms share 10 scenario/seed cases. KA-11 servo and KA-12/13 hydraulic
occur only in the treatment, so they cannot support a paired comparison.
The saved records do not include the full settings/configuration file or
independently reviewed diagnosis labels. `summary.json` names the historical
source commit `c49fdd60884d874a6d7877590d2be9ab1b7eb70e`: the baseline
commit was operator-attested in the earlier partial archive, and the
treatment commit is inferred from the unchanged frozen checkout after the
run. The commit is not embedded in the JSONL records. This is historical
behavior, not a fresh run of the current `main` code.

Observed treatment results: 13 records and 13 audits; all final
recommendations are `escalate`; no physical corrective action was taken.
Both false-alarm cases also end in escalation, without a repair. Across both
arms, packet validation reports 23 full traces, two model-unavailable
endings, zero independently judged diagnoses, and zero refused packets.
The automated BT sample rule reports `insufficient_sample` (10 matched
cases, zero matched judged cases). Missing settings make causal attribution
of an arm difference invalid. No accuracy improvement or calibration claim
is made.

For a full-project SNAP plan, combine this archive with the two older
archives named in `evaluation/SNAP_EVALUATION_RUNBOOK.md`. This adds complete
trace evidence for RUN questions while leaving the 52 older record-only
episodes explicitly incomplete. The offline plan sends no API requests.
