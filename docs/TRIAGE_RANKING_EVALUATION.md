# Evaluating the two-candidate triage ranking

Part 5 of the two-candidate ranking (parts: 1 contract, PR 329; 2 Conclude
wiring behind `TRIAGE_RANKING`; 3 events and terminal summary; 4 report, API
and UI; 5 this offline evaluation). The scorer is
`capstone-code/capstone/evaluation/ranking_accuracy.py`; its tests are
`tests/test_ranking_accuracy.py`. Nothing here calls a model. The live run
is Codex's (AGENTS.md §12), described in the handoff at the end.

## What is scored

Deterministic triage compiles candidates TC1..TCn. Each is a cause *family*
on the anomaly's machine (`triage_hypothesize.py`), not a physical part and
not a diagnosis. With `TRIAGE_RANKING=on` the conclusion model names its two
most plausible candidates, each with its own 0-1 confidence (uncalibrated,
independent, need not add to 1), or abstains. `check_ranking` turns the answer
into a `RankingVerdict`: accepted, abstained or rejected, with one fixed reason
code. The run keeps the verdict and the frozen `RankingSnapshot` it answers
(`InvestigationState.triage_ranking` and `triage_ranking_snapshot`).

The evaluator scores each verdict against the case's true causes
(`Score.causes`: one per standard case, two in the KA-09 challenge). Hidden
truth is used only here, after the run. It never reaches the snapshot, the
prompt, the check or memory.

## Family → fault mapping (`FAMILY_FAULTS`)

A pick counts as naming a true cause when the candidate's family lists that
fault **and** its machine passes the family's machine rule:

- `same_machine`: the candidate names a machine, and it is the faulty one.
- `if_named`: a candidate that names a machine must name the faulty one; one
  that names none (inspection anomalies have no machine) still counts.
- `not_needed`: the family is not about one machine (a material batch).

| Family | Counts as naming | Machine rule | Why |
|---|---|---|---|
| `machine_condition` | bearing_degradation, servo_drive_wear, hydraulic_leak | same_machine | "machine or process condition": a wearing part |
| `process_condition` | bearing_degradation, servo_drive_wear, hydraulic_leak | same_machine | a stop's only family for the machine's own condition |
| `sensor_or_transient` | false_alarm | same_machine | a transient or measurement issue |
| `setting_shift` | wrong_setting | if_named | a changed setting; names no machine after an inspection anomaly |
| `service_context` | wrong_setting | same_machine | "service or settings" on the stopped machine |
| `common_material_batch` | bad_material_batch | not_needed | the candidate names no batch id |
| `operating_load`, `related_quality` | nothing | | a symptom or effect, not a cause |
| `stoppage_event`, `preceding_events`, `observed_event`, `quality_signal` | nothing | | evidence, not a cause |
| `common_machine_path` | nothing | | a shared machine says where, not what |
| `cross_machine_review`, `telemetry_coverage_gap` | nothing | | a comparison or a coverage gap |

The mapping is strict on purpose: a family counts only for the fault its own
explanation names. `operating_load` (load or temperature) is a symptom of a
wearing part but would make any alarm's top-2 nearly always right if it
counted. `common_machine_path` localises without naming a fault kind. A test
fails if a new `CandidateFamily` is added without a mapping.

## Metrics (`score_case`, `aggregate`)

Per case (`CaseRankingScore`): status (accepted / abstained / rejected /
missing), reason code, valid (accepted or abstained), abstained, top-1 correct,
top-2 correct, true cause among the candidates, candidate count, top-pick
confidence. A verdict whose fingerprint differs from the snapshot given is
refused (`ValueError`): it was joined to the wrong question.

Over cases (`RankingAccuracy`):

- **Form:** validity rate, abstention rate, invalid rate, and invalid cases by
  reason code (`"missing"` when no verdict was stored).
- **Accuracy:** top-1 and top-2 accuracy over accepted rankings, and over all
  cases (abstained, rejected and missing count as not right).
- **Blame:** candidate-coverage rate (a true cause was offered at all), and
  top-2 accuracy over accepted rankings of covered cases only. A miss on an
  uncovered case is the candidate compiler's, not the model's.
- **Confidence:** mean top-pick confidence when right and when wrong, with
  `confidence_note` saying they are uncalibrated and `warning` set below 30
  cases (`SMALL_SAMPLE_CASES`).

### What they do and do not show

- **Form** shows whether the model can follow the contract (two known TC ids,
  cited evidence the snapshot offers, checks the candidate owns). It says
  nothing about being right.
- **Accuracy** on 13 cases (26 with two repetitions) is a functionality check:
  it shows whether rankings point the right way at all, not an accuracy
  estimate. One case moves a rate by 4-8 points.
- **Calibration** is not measured. A gap between the two mean confidences
  hints at whether confidence tracks correctness; a reliability curve needs
  hundreds of cases.
- Accuracy is per family, not per part: "machine_condition on CNC-02" is
  right for a bearing, a servo drive or a hydraulic leak there. Telling those
  apart is the deep investigation's job.

## Offline coverage check (no model)

`test_known_case_candidates_cover_the_true_cause` runs each of the 13 known
cases through deterministic triage with a scripted conclusion and asks
whether `ranking_snapshot(state)` holds a candidate naming a true cause.
Result on 2026-11-20 (hypothesis rules 1.2): **12 of 13 covered.**

- **KA-09-challenge (gap):** the first alarm is the false-alarm distractor on
  CNC-03, so every candidate is on CNC-03, while both true causes (bearing
  wear and a wrong setting) are on CNC-07. `cross_machine_review` names no
  fault. A ranking can at best say "false alarm on CNC-03" (true of the
  distractor, not a cause). The test fails when the gap closes, so the list
  stays honest.

So the live run's best possible top-2 accuracy over all 13 cases is 12/13.

## Codex handoff: the live 13-case run

Run after parts 2-4 are merged. One live run at a time (AGENTS.md §12).

**Source:** `main` at `<SHA — fill in after parts 2-4 merge>`. Record it in
the benchmark note.

**Settings:** the deterministic arm of `triage-docker\triage-docker.ps1`
(`TRIAGE_RUN_MODE=deterministic`, `TRIAGE_MODEL=nvidia/nvidia/nemotron-3.5-lightning-30b-a3b`,
`TRIAGE_MODEL_THINKING=off`, `TRIAGE_CONCLUDE_BRIEF=on`,
`TRIAGE_CONCLUDE_CAP=on`, with `TRIAGE=on`, `TRIAGE_THEN_DEEP=off`,
`TRIAGE_SECONDS=90`), plus `TRIAGE_RANKING=on` and `TRIAGE_TOOL_CALLS=8`.

**Command** (from `C:\Users\nicol\Capstone_Project_CMU`, Docker Desktop
running; the script's targeted tests must pass before any model call):

```powershell
powershell -ExecutionPolicy Bypass -File .\triage-docker\triage-docker.ps1 -Arm deterministic -Label "ranking-live" -Set "TRIAGE_RANKING=on,TRIAGE_TOOL_CALLS=8"
```

Two repetitions (the default): 26 triages.

**Artifacts to keep** (results land in `C:\Users\nicol\CapstoneRuns\triage-ranking-live-<time>`):
`config.json` (check `TRIAGE_RANKING=on` and `TRIAGE_TOOL_CALLS=8` are in it),
`container.log`, the `*.records.jsonl` per repetition, the
`*.failures.jsonl` per repetition, the audit logs, and the run header lines.
Copy the records and config into `docs/benchmarks/<date>-triage-ranking-live/`
with a README, as for earlier triage runs.

**Computing the metrics.** Each record's `score.causes` holds the true causes.
The ranking verdict and its snapshot are written to the record by part 4;
replace `SNAPSHOT_KEY` and `VERDICT_KEY` below with the keys it uses (part 2
names the state fields `triage_ranking_snapshot` and `triage_ranking`). Then:

```python
import json
from pathlib import Path

from capstone.agent.triage_ranking import RankingSnapshot, RankingVerdict
from capstone.evaluation.ranking_accuracy import aggregate, score_case
from capstone.evaluation.scoring import Cause


def dig(record, dotted):
    """record["a"]["b"] for "a.b"; None when any step is missing."""
    for key in dotted.split("."):
        record = record.get(key) if isinstance(record, dict) else None
    return record


SNAPSHOT_KEY = "<fill in from part 4>"
VERDICT_KEY = "<fill in from part 4>"
scores = []
for path in sorted(Path("<results folder>").glob("*.records.jsonl")):
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        snap, verdict = dig(record, SNAPSHOT_KEY), dig(record, VERDICT_KEY)
        scores.append(
            score_case(
                record["scenario_id"],
                RankingSnapshot.model_validate(snap) if snap else None,
                RankingVerdict.model_validate(verdict) if verdict else None,
                [Cause.model_validate(c) for c in record["score"]["causes"]],
            )
        )
print(aggregate(scores).model_dump_json(indent=2))
```

Report in the benchmark note: the aggregate JSON; a per-case table
(scenario, status, reason, top-1/top-2 correct, covered, top-1 confidence);
the invalid reasons; and whether KA-09's ranking said anything about CNC-07.
Say that 26 triages are a functionality check, and that confidences are
uncalibrated.
