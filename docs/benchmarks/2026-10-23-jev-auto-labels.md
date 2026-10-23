# Jev auto-labels on the saved live conclusions (2026-10-23)

**What ran:** `python -m capstone.evaluation.auto_label results*.jsonl
diagnostic*.jsonl --out <scratch>/proposals.jsonl`, live against TypeSafe
(`jev-latest`, which answered as `jev-1.14.0`). It covered 49 run keys. 33 were
"undetermined" and were labelled "no cause" without a request. The other 16
were asked, one request each.

**Cost:** $0.0008 for the 16 requests (TypeSafe dashboard, read by the
developer), about $0.00005 per labelled conclusion; undetermined runs cost
nothing. The developer's $5 a month covers roughly 100,000 conclusions.

**These are not hand labels.** The "my reading" column is the coding
assistant's reading of each conclusion, written to sanity-check the tool. No
accuracy figure is claimed until the developer's hand labels exist.

| Run | Proposed | Notes / my reading |
|---|---|---|
| trial-2/8/KA-08 | no cause | "investigation in progress": agrees |
| live-known-4/1/KA-01 | no cause | "cause is unclear": agrees |
| live-known-4/2/KA-02 | bearing CNC-05 (0.98) | agrees |
| live-known-4/3/KA-03 | no cause | "potentially due to a shared machine": agrees |
| live-known-4/4/KA-04 | no cause (batch 0.06) | "a batch-specific issue", no batch named: debatable |
| live-known-4/5/KA-05 | no cause | agrees |
| live-known-4/6/KA-06 | no cause | "CNC-01 may be contributing": debatable |
| live-known-4/7/KA-07 | false alarm CNC-01 (0.89) | agrees |
| live-known-4/8/KA-08 | false alarm CNC-03 (0.80) | agrees |
| live-known-4/9/KA-09 | no cause (false alarm 0.11) | "returned to normal": debatable |
| wait-120/1/seed-6 | false alarm CNC-02 (0.90) | "nuisance alarms from ordinary variation": agrees |
| reasons-1/1/seed-6 | bearing CNC-02 (0.97) | agrees |
| reasons-1/1/seed-9 | no cause | "root cause is not yet determined": agrees |
| structured-1/1/seed-6 | no cause, **review** (false alarm 0.51) | "no confirmed fault": a borderline case, correctly sent to review |
| structured-1/1/seed-7 | no cause | mentions batch 2 only to rule it out: agrees (a hard case) |
| structured-1/1/seed-9 | bearing CNC-05 (0.97) | "most consistent with a failing bearing": agrees |

The proposals judge what each conclusion *says*, not whether it is right. A
wrong diagnosis labelled faithfully (structured-1/1/seed-9 was really a wrong
setting) is still a correct label.

## Draft labels compared (2026-10-23, later the same day)

At the developer's request, the coding assistant drafted labels for the 16
runs: [`2026-10-23-draft-diagnosis-labels.jsonl`](2026-10-23-draft-diagnosis-labels.jsonl)
(a `LabelBook` file, every label `labelled_by: "claude-draft"`, each with a
note). **These are still not hand labels.** A model wrote them, after seeing
Jev's proposals, so agreement may be flattered. Until the developer confirms
or corrects them, they must not be used to set thresholds.

Compared with the saved proposals using `agreement` (no new Jev calls):

- agree **13 of 16**; among proposals not marked for review, **13 of 15**;
- the 3 disagreements are the 3 drafts noted as debatable:

| Run | Jev | Draft | Jev's probability |
|---|---|---|---|
| live-known-4/4/KA-04 | no cause | bad batch (no batch named) | batch 0.06 |
| live-known-4/9/KA-09 | no cause | false alarm CNC-03 | false alarm 0.11 |
| structured-1/1/seed-6 | no cause (**review**) | false alarm CNC-02 | false alarm 0.51 |

**What this says about the thresholds:** two of the three disagreements were
answered confidently (0.06, 0.11), well outside the 0.3-0.7 review band, so no
threshold change would catch them. The gap is in the question: Jev counts a
false alarm only when the conclusion says so outright, while the drafts also
count "returned to normal, nothing needs fixing". If the developer's labels
agree with the drafts here, the next fix is the false-alarm criteria in
`CAUSES` (then re-ask those runs), not the thresholds.

**Next:** the developer reviews the 16 drafts, correcting any they read
differently and relabelling the rest under their own name (`labelled_by`).
Then the comparison is rerun.
