# Claude's answers to a small SNAP calibration sample (2026-11-08)

**Reviewer: Claude (Claude Code, the coding assistant), at the developer's
request. Not the developer.** The developer has not checked these answers.

They are not the independent human reference that `evaluation/reference/README.md`
(PR #196) asks for. If SNAP's answers agree with these, that is agreement between
two models, and that README says model agreement does not establish correctness.
Use these answers in one of two ways: as a draft reference that the developer
confirms or overrules question by question, or as a second model's view next to
SNAP's.

## What is here

| File | What it is |
|---|---|
| `answers.json` | The 47 answers, keyed by opaque review id, in the format `reference_review import` reads |
| `RATIONALE.md` | The reason for each answer, citing evidence ids and source lines |
| `manifest.json`, `blinded/*.json` | The exported sample exactly as answered. Each packet holds the state SNAP would receive, plus the question criteria |

Not committed: `private_mapping.json` and the imported reference, which hold
internal item ids, and the private strata file. All three can be regenerated
(see "Reproduce and import").

SHA-256 of `answers.json`:
`5459dadaed2657e26f5f5a94cf18cb7f127d611aeeb3084c86bc968aa4a30c10`

## The sample

This follows the recommendation to start with roughly 30 to 50 questions,
including both a well-supported and a misleading investigation, rather than the
default 31-item sample (up to 163 questions).

| Family | Items | Questions each | Questions |
|---|---|---|---|
| RUN (agent investigations, all full traces) | 3 | 10 | 30 |
| FN (functions) | 2 | 3 | 6 |
| TS (tests) | 2 | 3 | 6 |
| TL (agent tools) | 1 | 3 | 3 |
| BT (experiment comparisons) | 1 | 2 | 2 |
| **Total** | **9** | | **47** |

RUN-09 and RUN-10 were not part of these runs' requests, so they were not asked.

## How it was made

1. **Code.** The head of PR #196 (`codex/evaluator-full-audit`, commit
   `ffd8349bb1feed1e2b5dca9aa9d6549ed82eec05d`), where
   `evaltools/reference_review.py` lives. `main` does not have that tool yet.
2. **Offline dry run.** No API key was used and nothing was sent. It ran on
   Python 3.14.6 because uv could not fetch the pinned 3.14.7. The dry run reads
   the committed inventories and archives, so the Python version does not change
   the requests.

   ```sh
   cd evaluation
   ../.venv/bin/python -m evaltools.full_evaluation --commit ffd8349bb1feed1e2b5dca9aa9d6549ed82eec05d \
     --provider snap --snap-full-context \
     --archive ../docs/benchmarks/2026-11-01-tot13-pairs \
     --archive ../docs/benchmarks/2026-11-02-audited-known-cases \
     --out full-eval/claude-calibration-2026-11-08
   ```

   `.github/verify_snap_dry_run.py --expected-episodes 57` passed: 2,674
   requests planned, 0 sent. Of the 46 RUN items with a request, 5 have full
   traces.
3. **Strata.** A short script (below) read the truth-side code facts of the
   five full-trace RUN items and wrote a private `{item_id: "sound" |
   "misleading"}` file. It printed only counts: 4 of 5 classified, both strata
   present. The rule, from each packet's `evaluator_only` half: the label is
   judged, the model was available, and the run committed (did not abstain).
   `sound` means `fully_right` with no false intervention. `misleading` means not
   fully right, or a false intervention. Abstentions were left out. This is a
   code-fact stand-in for the "independent, pre-model review" the README
   describes, not that review.
4. **Export.**

   ```sh
   ../.venv/bin/python -m evaltools.reference_review export \
     --requests full-eval/claude-calibration-2026-11-08/requests \
     --out reference/2026-11-08-claude-calibration-review \
     --run 3 --function 2 --test 2 --tool 1 --batch 1 \
     --run-strata <private strata file>
   ```

5. **Answers.** Written to `answers.json` and checked with
   `reference_review import`: 9 items, 47 questions, every value valid for its
   question.

## What the reviewer did and did not see

- The RUN and BT answers come from the blinded packets alone. The FN, TS and TL
  answers also used the repository source at `ffd8349` where the packet left
  something out, such as `parametrize` values and test helpers.
  `RATIONALE.md` says where.
- Not opened before the answers were frozen: `private_mapping.json`, the
  imported reference, the dry run's truth-side packets and `report.md`, the
  archives' `summary.json` and `README.md` files, and the earlier SNAP answers
  in `docs/benchmarks/2026-11-04-snap-live-1`.
- The RUN, TL, FN and TS answers were written down before the BT packet was
  opened, because a BT packet shows per-case right and wrong.
- Limits of the blinding:
  - The same agent built the strata and answered the questions. The script
    printed only counts, but the reviewer knew the three RUN items include at
    least one of each kind.
  - While finding the tools, the reviewer saw packet file names (which name
    scenarios) for the record-only tot13 archive. It also saw, on `main`, the
    `verification_calibration` values of the older `master-single-2026-10-27`
    packets. Neither source supplied a sampled RUN item: all three are full
    traces from the audited cases.

## Answers at a glance

| Review id | Family | Subject | Answers |
|---|---|---|---|
| `230bb91f581d295e` | RUN | Vibration alarm on CNC-02; named a cause at 0.92, final check lowered intervene to escalate | RUN-01 3, RUN-02 4, RUN-03 ineffective, RUN-04 unnecessary, RUN-05 not_applicable, RUN-06 inappropriate, RUN-07 reasoning, RUN-08 2, RUN-11 used, RUN-12 false |
| `c552284a9d4329d3` | RUN | Vibration alarm on CNC-05; escalated between sensor bias and a normal band | RUN-01 3, RUN-02 3, RUN-03 ineffective, RUN-04 useful, RUN-05 not_applicable, RUN-06 appropriate, RUN-07 reasoning, RUN-08 2, RUN-11 used, RUN-12 false |
| `26b1f92dbf2b1844` | RUN | 3 of 4 jobs failed inspection; escalated unresolved at 0.4 | RUN-01 2, RUN-02 2, RUN-03 unknown, RUN-04 misleading, RUN-05 not_applicable, RUN-06 appropriate, RUN-07 reasoning, RUN-08 2, RUN-11 no_feedback, RUN-12 true |
| `1260f9b4e44f1ac3` | TL | `get_maintenance_history` | TL-01 true, TL-02 true, TL-03 0 |
| `012cf733fced8b7d` | FN | `capstone.ingestion.channel_map:main` | FN-01 false, FN-02 partly, FN-03 insufficient |
| `014845a67471fce4` | FN | `capstone.evaluation.auto_label:main` | FN-01 false, FN-02 uncovered, FN-03 insufficient |
| `000105d208db21de` | TS | `test_state.py::test_bearing_health_outside_unit_interval_is_rejected_on_assignment` | TS-01 true, TS-02 true, TS-03 3 |
| `000a7e2d5a39a74a` | TS | `test_failure.py::test_same_seed_fails_at_the_same_tick` | TS-01 true, TS-02 true, TS-03 3 |
| `124952c4943081f1` | BT | master-tot13-anchored vs master-tot13-blind | BT-01 valid, BT-02 insufficient_sample |

## Borderline calls worth a second look

In each of these, the answer depends on how the rubric is read. They may be
worth clarifying in `SNAP_QUESTIONS.json` before the live pass.

1. **TS-01, `000105d208db21de`:** answered `true` from the code. The
   missing-evidence rule ("no exercised project function: unknown") would leave
   it unanswered, but coverage cannot see a bound declared on a Pydantic model.
2. **TL-03, `1260f9b4e44f1ac3`:** answered `0` because the stale-record hazard
   is designed, and the question asks for undesigned failures. Level 3's own
   wording names "a stale record", which would give `3`.
3. **RUN-04, `c552284a9d4329d3`:** answered `useful`, although E2 is never cited
   by id, because the plan visibly follows it. Strictly, neither "useful" (needs
   a citation) nor "unnecessary" (needs no use) fits.
4. **RUN-11, `c552284a9d4329d3`:** answered `used`, although the critic's check
   asked for ticks that had not happened yet and returned one sample. The other
   reading is `no_feedback`.
5. **RUN-02, `26b1f92dbf2b1844`:** answered `2`, counting readings from the
   investigate phase. A literal test-phase reading gives `1`, since the test
   phase made no readings.
6. **RUN-02 in general:** level 4 is level 3 plus a hypothesis that needs no
   change to the factory, which almost every run holds. So a run that meets
   level 3 nearly always reaches 4 (`230bb91f581d295e`).
7. **FN-01, `012cf733fced8b7d`:** answered `false` because return code 2 and the
   argparse exit fall outside the stated 0/1 outcome. The CLI help does describe
   both refusals.

## Reproduce and import

1. Check out `ffd8349` and run the dry run above into a new folder.
2. Recreate the strata file with the script below. Without it, the same limits
   select a different RUN item, so the strata file is needed to get this exact
   sample.
3. Export with the same limits and strata file. The blinded packets and
   manifest match this folder byte for byte (checked on 2026-11-08).
4. Import:

   ```sh
   ../.venv/bin/python -m evaltools.reference_review import \
     --review-dir <export folder> \
     --answers reference/2026-11-08-claude-review/answers.json \
     --out reference/2026-11-08-claude-reference.json
   ```

5. If the imported file is passed to `full_evaluation --reference`, report its
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
print(json.dumps({
    "full_trace_run_items": len(full_ids),
    "classified": len(strata),
    "both_strata_present": {"sound", "misleading"} <= labels,
}))
```

</details>
