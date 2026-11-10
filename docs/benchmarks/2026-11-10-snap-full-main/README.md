# Full-project SNAP evaluation, 2026-11-10

**Status: complete live pass, exploratory and uncalibrated.** All 2,965
planned SNAP requests have complete answers and settled charge reservations.
The independent reference agrees with SNAP on 27 of 44 answers. This is a
record of what the evaluator judged, not proof that those judgments are right.

## Scope and provenance

- Evaluated repository commit: `345f9d3bf298b63207f2564e8124ba5abd397f87`
  (`main` at run time), with clean tracked files and verified source-inventory
  hashes. Rubric 1.1.1, packet schema 1.4.0, normalization 1.1.0.
- Evidence: `2026-11-01-tot13-pairs`, `2026-11-02-audited-known-cases`, and
  `2026-11-10-snap-calibration-pair`. These are historical run archives, not
  fresh agent episodes at the evaluated code commit. The last archive has
  missing arm configuration and diagnosis labels, as its README explains.
- 80 episodes: 28 full traces and 52 record-only. FN, TS, TL, RUN, and BT
  question families were all planned. The inventory includes 976 functions,
  1,926 test definitions and 18 tools. The report covers every source file;
  its scope has zero unexplained or stale paths.
- The developer endorsed the 44 independent rubric selections before the
  SNAP replies were viewed. The frozen PDF and import remain private and
  outside Git. The frozen reference JSON SHA-256 is
  `02b8a23c6984df9b6d8059a664ba1f99edd381791a1d9751cba259426226f8cb`.

## Live run

The full dry plan was prepared with `--provider snap --snap-full-context`
and a pinned commit. A two-request pilot used the same request bodies and
fingerprints. Those two successful, settled pilot answers were reused; a
separate failed sandbox-network attempt was never reused. The remaining
2,963 requests were sent with `--max-requests 2965 --max-usd 2.00
--max-seconds 3600`, using the same plan and frozen reference. Each request
was handled by `subq-snap-1.1`. There were no failed or unresolved
reservations. Actual measured input cost, including the pilot, was
**$0.28799644**, below the $2 cumulative cap. The dry estimate was $0.4026.

The ledger has 9,726 rows: 8,126 answered, 258 not applicable, and 1,342
unknown. In particular, record-only archives cannot answer full-trace RUN
questions; unknown is an evidence limit, not a negative judgment. The
deterministic correctness figures in `report.md` come from known-case
scoring, not from SNAP. The baseline/treatment calibration pair has 10
matched cases but zero independently judged cases in both arms, so its
BT-02 result is `insufficient_sample`; no treatment effect is claimed.

## Independent reference check

| Family | Agreement | Disagreement |
|---|---:|---:|
| FN | 6 | 3 |
| TS | 8 | 1 |
| TL | 2 | 0 |
| RUN | 9 | 13 |
| BT | 2 | 0 |
| **Total** | **27** | **17** |

The two reviewed RUN packets account for 13 disagreements, including
categorical calls about intervention effectiveness, critic use, escalation,
and failure source. SNAP scored several parts of these traces more favorably
than the human reviewer. FN disagreed on `check_capture` coverage and
evidence sufficiency and on `LoadingDoor.ground_truth` evidence sufficiency.
TS-02 disagreed on `test_the_same_state_twice_prints_nothing_new`. The
reference includes two problematic RUN traces, so the 44 answers do not
establish evaluator calibration across sound and misleading investigations.
Review these disagreements against the code and rubric before using SNAP
scores as an acceptance gate.

## Files and limits

- `report.md`: readable aggregate, deterministic outcomes, coverage and
  missingness.
- `report.json`: all 3,003 item findings, reference comparisons, provenance,
  and cumulative spend.
- `ledger.jsonl`: one normalized status/value per planned question.
- `scope_manifest.json`: per-file inclusion and source status.
- `answers.jsonl.gz`: 2,965 saved SNAP answers, including each raw model reply
  and provider-reported usage, sorted by request filename and gzip-compressed.
- `reservations.jsonl.gz`: 2,965 settled charge records in the same order.

The ignored local run folder holds the complete request files. Its report,
ledger and scope manifest were copied byte-for-byte here; the answer and
reservation streams preserve the saved JSON objects, one per line.
This pass evaluates the code inventory and available historical episodes;
it cannot verify a real Prestige controller, field reliability, a physical
repair, a causal baseline/treatment improvement, or correctness of every
source path. No Jev or other model was sent as part of this SNAP pass.
