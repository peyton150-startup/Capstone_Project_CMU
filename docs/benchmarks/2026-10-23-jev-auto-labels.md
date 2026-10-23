# Jev auto-labels on the saved live conclusions (2026-10-23)

**What ran:** `python -m capstone.evaluation.auto_label results*.jsonl
diagnostic*.jsonl --out <scratch>/proposals.jsonl`, live against TypeSafe
(`jev-latest`, which answered as `jev-1.14.0`). It covered 49 run keys. 33 were
"undetermined" and were labelled "no cause" without a request. The other 16
were asked, one request each.

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

**Next:** the developer hand-labels these 16 runs, then
`--hand <labels.jsonl>` reports how many proposals agree.
