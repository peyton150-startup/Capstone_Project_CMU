# Second full-project SNAP pass and comparison, 2026-11-10

**Status: complete repeat; exploratory and uncalibrated.** This is an
independent second send of the same 2,965 SNAP request bodies. It compares
with the [first pass](../2026-11-10-snap-full-main/README.md) without
changing the rubric, evidence archives, source inventory or frozen human
reference. The comparison shows exact repeatability of saved judgments;
it does not establish that the judgments are correct.

## Repeat run

- Evaluated clean `main` commit
  `0b089d83065eaa0eea8cb0928d895e75ba6994a7`. The first pass used
  `345f9d3bf298b63207f2564e8124ba5abd397f87`; the intervening PR
  archived the first results and changed no project Python source.
  Inventory and coverage hashes match between reports. Rubric 1.1.1,
  packet schema 1.4.0 and normalization 1.1.0 match.
- The same three historical archives provide 80 episodes: 28 full traces
  and 52 record-only. The plan spans FN, TS, TL, RUN and BT, covering 976
  functions, 1,926 test definitions and 18 tools. It has no unexplained or
  stale source paths.
- A fresh output folder contained zero answer files before the live send.
  The dry run verified 2,965 planned requests and identical request
  filenames/fingerprints to pass one. No prior answer was imported.
- All **2,965 requests were newly sent** to `subq-snap-1.1` with a $2
  cumulative cap. All 2,965 answers completed and all charge reservations
  settled. Actual measured input cost was **$0.28799644**. The ledger has
  9,726 rows: 8,126 answered, 258 not applicable, 1,342 unknown.
- The same developer-endorsed, independently frozen 44-answer reference was
  used (SHA-256
  `02b8a23c6984df9b6d8059a664ba1f99edd381791a1d9751cba259426226f8cb`).
  It remains private outside Git.

## Pass-to-pass comparison

The comparison matched rows by family, item, provider and question. It
compared each status and normalized value, then matched saved answer files
by request filename and compared their raw provider replies. Differences
in `answered_at`, request build time and evaluated commit are metadata,
not question results.

| Measure | First pass | Second pass | Difference |
|---|---:|---:|---:|
| Planned requests | 2,965 | 2,965 | 0 |
| Newly sent requests | 2,963 (2 pilot replies reused) | 2,965 | 2 |
| Ledger rows | 9,726 | 9,726 | 0 keys |
| Status or normalized value changes | — | — | **0** |
| Raw SNAP reply changes | — | — | **0 / 2,965** |
| Actual input cost | $0.28799644 | $0.28799644 | $0 |
| Agreement with frozen reference | 27 / 44 | 27 / 44 | 0 |

Both passes agree with the human reference on 6/9 FN, 8/9 TS, 2/2 TL,
9/22 RUN and 2/2 BT answers. The 17 disagreements persist exactly,
including 13 RUN disagreements on two reviewed investigations. The
historical baseline/treatment pair still has no independently judged
diagnosis pairs and cannot establish a treatment effect. Record-only
episodes still leave trace questions unknown.

Exact identical replies may reflect deterministic model behavior, provider
caching, or another service behavior; these artifacts do not distinguish
among them. Repeatability therefore does not calibrate SNAP, resolve the
human disagreements, validate real Prestige controller behavior, or prove
project-wide functional correctness. Review the 17 disagreements against
the code and rubric before using SNAP judgments as an acceptance gate.

## Files

- `comparison.json`: machine-readable counts, matched provenance, answer
  times, spend and family-level reference agreement for both passes.
- `report.md`, `report.json`, `ledger.jsonl`, `scope_manifest.json`: the
  repeat evaluator outputs, copied byte-for-byte from the ignored run folder.
- `answers.jsonl.gz`: all 2,965 saved repeat answers and raw provider replies,
  sorted by request filename, one JSON object per line inside gzip.
- `reservations.jsonl.gz`: all 2,965 settled charge records in the same order.

The ignored local folder retains full request files. No simulator or agent
code changed in this PR.
