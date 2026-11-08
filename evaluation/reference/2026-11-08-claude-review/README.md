# Claude's answers to a small SNAP calibration sample (2026-11-08)

**Reviewer: Claude (Claude Code, the coding assistant), at the developer's
request. Not the developer.** The developer has not checked these answers.

They are not the independent human reference that `evaluation/reference/README.md`
(PR #196) asks for. If SNAP's answers agree with these, that is agreement between
two models, which that README says does not establish correctness. Use them in
one of two ways: as a draft reference that the developer confirms or overrules
question by question, or as a second model's view next to SNAP's.

## What is here

| File | What it is |
|---|---|
| `answers.json` | The 49 answers under rubric 1.1.0, keyed by opaque review id, in the format `reference_review import` reads |
| `answers.rubric-1.0.0.json` | Round 1: the first 47 answers under rubric 1.0.0, kept so the changes stay visible |
| `RATIONALE.md` | The reason for each answer; rows that differ from round 1 are marked |
| `manifest.json`, `blinded/*.json` | The rubric 1.1.0 export exactly as answered. Each packet holds the state SNAP would receive, plus the question criteria |

Not committed: `private_mapping.json` and the imported reference, which hold
internal item ids, and the private strata file. All three can be regenerated
(see "Reproduce and import").

SHA-256 of `answers.json`:
`094e67925ff6470bfe926f1b8110c37e5a4f2bd0e0701eaa44d90406af16d9af`

## The sample

This follows the recommendation to start with roughly 30 to 50 questions,
including both a well-supported and a misleading investigation, rather than the
default 31-item sample (up to 163 questions).

| Family | Items | Questions |
|---|---|---|
| RUN (agent investigations, all full traces) | 3 | 32 (11, 11, 10) |
| FN (functions) | 2 | 6 |
| TS (tests) | 2 | 6 |
| TL (agent tools) | 1 | 3 |
| BT (experiment comparisons) | 1 | 2 |
| **Total** | **9** | **49** |

Rubric 1.1.0 asks RUN-09 of the two runs whose conclusion names a cause. Under
1.0.0 the final check's escalate hid one of them from RUN-09, so round 1 had 47
questions. RUN-10 is not asked of these runs, because none recommended
no_action.

## How it was made

1. **Code.** `evaltools/reference_review.py` exists only on PR #196, so the
   sample came from a local merge of PR #196's head (`ffd8349`) with this PR
   (`cb04768`). That merge is commit `18ac5b8`, tree `6113c5bf`. It had one
   conflict, in `run_packet.py`: I kept `PACKET_SCHEMA_VERSION = "1.4.0"` from
   #196 and `RUBRIC_VERSION = "1.1.0"` from this PR. One local-only commit
   refreshed the source hashes of the three files the merge changed
   (`run_packet.py`, `snap_request.py`, `tests/test_evaluation_tools.py`) in
   `VERIFICATION_MATRIX.json` instead of rebuilding #196's inventory. None of the
   nine sampled items lives in those files. Python 3.14.6 was used, because uv
   could not fetch the pinned 3.14.7.
2. **Offline dry run.** No API key was used and nothing was sent.

   ```sh
   cd evaluation
   ../.venv/bin/python -m evaltools.full_evaluation --commit <local merge commit> \
     --provider snap --snap-full-context \
     --archive ../docs/benchmarks/2026-11-01-tot13-pairs \
     --archive ../docs/benchmarks/2026-11-02-audited-known-cases \
     --out full-eval/claude-calibration-1.1
   ```

   It planned 2,674 requests and sent none. `.github/verify_snap_dry_run.py`
   stops at its scope check, because the two functions this PR adds are not in
   #196's inventory. That is expected until #196 rebuilds its inventory.
3. **Strata.** A short script (below) read the truth-side code facts of the
   five full-trace RUN items and wrote a private `{item_id: "sound" |
   "misleading"}` file, printing only counts: 4 of 5 classified, both strata
   present. The file is the same as in round 1.
   - The rule uses each packet's `evaluator_only` half. It counts only runs
     whose label is judged, whose model was available, and that committed (did
     not abstain).
   - `sound`: `fully_right`, with no false intervention.
   - `misleading`: not fully right, or a false intervention.
   - Abstentions were left out.

   This is a code-fact stand-in for the "independent, pre-model review" the
   README describes, not that review.
4. **Export.**
   `reference_review export --run 3 --function 2 --test 2 --tool 1 --batch 1 --run-strata <private file>`
   gave the same nine items as round 1. The RUN, FN, TL and BT states are
   unchanged. The two TS states gained `decorators` and `module_helpers`.
5. **Answers.** I re-checked all 47 round-1 answers against the 1.1.0 wording
   and answered the two new RUN-09 questions. `reference_review import` accepted
   all 49.

## What changed from round 1

| Review id | Question | 1.0.0 | 1.1.0 | The rubric change that decided it |
|---|---|---|---|---|
| `230bb91f581d295e` | RUN-02 | 4 | 3 | Level 4 now needs the hypothesis set to cover the kinds of cause the retrieved manual names |
| `230bb91f581d295e` | RUN-04 | unnecessary | ignored | New option: the conclusion goes against a caution the retrieved manual states |
| `230bb91f581d295e` | RUN-07 | reasoning | evidence_gathering | New option: the agent stopped before a reading the manual called for |
| `230bb91f581d295e` | RUN-09 | not asked | true | Asked when a check lowered a named cause to escalate |
| `c552284a9d4329d3` | RUN-02 | 3 | 4 | Readings count in any phase, and confidences that fall when more rivals are added are not moving without evidence |
| `c552284a9d4329d3` | RUN-09 | not asked | false | Asked of every conclusion that names a cause |
| `c552284a9d4329d3` | RUN-11 | used | no_feedback | A check that cannot be carried out when given is no_feedback |
| `26b1f92dbf2b1844` | RUN-01 | 2 | 3 | Exclusive levels: one discriminating reading reaches level 3 |

The other 41 answers are unchanged. Round 1's seven borderline calls were
settled by the new wording.

These are still judgment calls a second reviewer might make differently:

- RUN-02 for `c552284a9d4329d3`: whether E18 contradicts the leading
  hypothesis.
- RUN-07 for `c552284a9d4329d3`: whether the earliest failure is the flat-power
  dismissal (reasoning) or the time limit (tooling).
- RUN-04 for `c552284a9d4329d3`: whether skipping the maintenance history
  counts as ignoring the manual.

## What the reviewer did and did not see

- The RUN and BT answers come from the blinded packets alone. The FN, TS and TL
  answers also used the repository source where the packet left something out.
  `RATIONALE.md` says where.
- Not opened before the answers were frozen: `private_mapping.json`, the
  imported reference, the dry run's truth-side packets and `report.md`, the
  archives' `summary.json` and `README.md` files, and the earlier SNAP answers
  in `docs/benchmarks/2026-11-04-snap-live-1`.
- In round 1, the RUN, TL, FN and TS answers were written down before the BT
  packet was opened, because a BT packet shows per-case right and wrong.
- Limits of the blinding:
  - The same agent built the strata and answered the questions. The script
    printed only counts, but the reviewer knew the three RUN items include at
    least one of each kind.
  - While finding the tools, the reviewer saw packet file names (which name
    scenarios) for the record-only tot13 archive. It also saw, on `main`, the
    `verification_calibration` values of the older `master-single-2026-10-27`
    packets. Neither source supplied a sampled RUN item: all three are full
    traces from the audited cases.
  - Round 2 is a re-check under new wording by the same reviewer, after
    reading round 1, not an independent second review. A round-1 reproduction
    check also showed that without the strata file the same limits select a
    different RUN item.

## Answers at a glance

| Review id | Family | Subject | Answers |
|---|---|---|---|
| `230bb91f581d295e` | RUN | Vibration alarm on CNC-02; named a cause at 0.92, final check lowered intervene to escalate | RUN-01 3, RUN-02 3, RUN-03 ineffective, RUN-04 ignored, RUN-05 not_applicable, RUN-06 inappropriate, RUN-07 evidence_gathering, RUN-08 2, RUN-09 true, RUN-11 used, RUN-12 false |
| `c552284a9d4329d3` | RUN | Vibration alarm on CNC-05; escalated between sensor bias and a normal band | RUN-01 3, RUN-02 4, RUN-03 ineffective, RUN-04 useful, RUN-05 not_applicable, RUN-06 appropriate, RUN-07 reasoning, RUN-08 2, RUN-09 false, RUN-11 no_feedback, RUN-12 false |
| `26b1f92dbf2b1844` | RUN | 3 of 4 jobs failed inspection; escalated unresolved at 0.4 | RUN-01 3, RUN-02 2, RUN-03 unknown, RUN-04 misleading, RUN-05 not_applicable, RUN-06 appropriate, RUN-07 reasoning, RUN-08 2, RUN-11 no_feedback, RUN-12 true |
| `1260f9b4e44f1ac3` | TL | `get_maintenance_history` | TL-01 true, TL-02 true, TL-03 0 |
| `012cf733fced8b7d` | FN | `capstone.ingestion.channel_map:main` | FN-01 false, FN-02 partly, FN-03 insufficient |
| `014845a67471fce4` | FN | `capstone.evaluation.auto_label:main` | FN-01 false, FN-02 uncovered, FN-03 insufficient |
| `000105d208db21de` | TS | `test_state.py::test_bearing_health_outside_unit_interval_is_rejected_on_assignment` | TS-01 true, TS-02 true, TS-03 3 |
| `000a7e2d5a39a74a` | TS | `test_failure.py::test_same_seed_fails_at_the_same_tick` | TS-01 true, TS-02 true, TS-03 3 |
| `124952c4943081f1` | BT | master-tot13-anchored vs master-tot13-blind | BT-01 valid, BT-02 insufficient_sample |

## Reproduce and import

1. Merge this PR into PR #196's head, or check out any commit that has both
   (once #196 takes `main`). Refresh or rebuild the inventory so
   `full_evaluation` accepts the source hashes, then commit.
2. Run the dry run above into a new folder. Recreate the strata file with the
   script below, then export with the same limits. With the same code, the
   blinded packets and manifest match this folder byte for byte (checked on
   2026-11-08).
3. Import:

   ```sh
   ../.venv/bin/python -m evaltools.reference_review import \
     --review-dir <export folder> \
     --answers reference/2026-11-08-claude-review/answers.json \
     --out reference/2026-11-08-claude-reference.json
   ```

4. If the imported file is passed to `full_evaluation --reference`, report its
   agreement figures as agreement with a model-made reference, not with the
   developer.

<details>
<summary>Strata script (run with <code>python -I make_strata.py &lt;dry-run folder&gt; &lt;out.json&gt;</code>)</summary>

```python
import json
import sys
from pathlib import Path

cohort, out = Path(sys.argv[1]), Path(sys.argv[2])
full_ids = set()
for path in cohort.glob("requests/*.request.json"):
    saved = json.loads(path.read_text(encoding="utf-8"))
    tags, body = saved.get("tags", {}), saved.get("body")
    if (
        tags.get("family") == "RUN"
        and body is not None
        and body["state"].get("trace", {}).get("completeness") == "full"
    ):
        full_ids.add(tags["item_id"])
strata = {}
for path in cohort.glob("packets/*/*.json"):
    packet = json.loads(path.read_text(encoding="utf-8"))
    key = packet.get("meta", {}).get("episode_key")
    if key not in full_ids:
        continue
    ev = packet["evaluator_only"]
    if ev["label_status"] != "judged" or ev["model_unavailable"]:
        continue
    if ev["abstained"] is not False:
        continue
    if ev["fully_right"] is True and not ev["false_intervention"]:
        strata[key] = "sound"
    elif ev["fully_right"] is False or ev["false_intervention"]:
        strata[key] = "misleading"
out.write_text(json.dumps(strata, indent=1) + "\n", encoding="utf-8")
labels = set(strata.values())
print(
    json.dumps(
        {
            "full_trace_run_items": len(full_ids),
            "classified": len(strata),
            "both_strata_present": {"sound", "misleading"} <= labels,
        }
    )
)
```

</details>
