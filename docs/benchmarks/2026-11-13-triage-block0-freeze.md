# 2026-11-13: Triage Block 0 — frozen control and safety invariants

**Status:** Block 0 of [the 2026-11-13 triage schedule](../2026-11-13-schedule.md). Records the control every triage feature branch is compared against, and adds the safety and deep-mode tests in `tests/test_triage_safety_baseline.py`. No runtime code changed. Nothing ran against a live model.

## Frozen control

| Item | Value |
|---|---|
| `main` commit | `0b0d3c45ae5378c3f39e371b95d97a7c039cc977` (merge of PR #248, 2026-11-13) |
| Integration branch | `integration/triage-deterministic-20261113`, cut from that commit |
| Triage budget | `TRIAGE_SECONDS=90`, `TRIAGE_TOOL_CALLS=6`; `triage_budgets` keeps `min(20 s, 90/4)` = 20 s for the conclusion, 0 follow-up and 0 critic calls, 8 iterations (`agent/state.py`) |
| Triage switches | `TRIAGE=off` by default; the A0 runs used `TRIAGE=on`, `TRIAGE_THEN_DEEP=off` |
| Other defaults (`settings.py`) | `STEP_QUESTIONS=1`, `DECIDE_CALLS=1`, `LINE_CONTEXT=off`, `STAGE_CONTEXT=off`, `MANUAL_STEP=on`, `LATE_CONCLUDE=off`, `LATE_MODEL_THINKING=off`, `LATE_MODEL_SECONDS=60` |
| Models (A0, as the CLI reported) | early: `nvidia/nemotron-3.5-super-vl-120b-a12b`; late decide: `nvidia/nemotron-3.5-lightning-30b-a3b`; fallback: `command-a-03-2025`. Re-read `.env` and record the exact routing next to each new run's records; the provider configuration is not in Git. |
| Known-answer cases (seed) | KA-01-bearing (6), KA-02-bearing (9), KA-03-batch (7), KA-04-batch (8), KA-05-setting (9), KA-06-setting (10), KA-07-false-alarm (8), KA-08-false-alarm (11), KA-09-challenge (3, two faults), KA-10-servo (16), KA-11-servo (13), KA-12-hydraulic (4), KA-13-hydraulic (15) — `evaluation/known_answers.py` |
| Held-out seeds | **Not chosen yet — the developer's decision.** The schedule asks for held-out seeds before any tuning; none exist in the repository. |

## A0 comparators

From [the 2026-11-12 A0 note](2026-11-12-triage-a0.md) (two repetitions, 26 episodes). The raw `triage-a0-r1/r2.records.jsonl` were kept outside Git and could not be found on this machine, so nothing below was recomputed.

| Comparator | A0 value | Available? |
|---|---|---|
| Triage latency p50 / p95 | 87 s / 89–90 s | yes |
| Timeouts | 25/26 | yes |
| Final `supported` | 1/26 | yes |
| Unsafe `supported/no_action` | 1 (KA-09, repetition 2) | yes |
| Runs entering `hypothesize` / `test` | 6/26 / 2/26 (stage visits, not hypothesis counts) | yes |
| New test-stage observations | 0/26 | yes |
| Diagnostic reads marked `uninterpreted` | 16 of 58 | yes |
| Model questions; time-cut-off attempts | 170; 93 | yes |
| Root-cause accuracy | **not judged** (0/0, labels missing) | no |
| Model calls **by stage** | not in the A0 note | **no: needs the raw records** |
| Time to first valid hypothesis | not recorded | **no: needs instrumentation** |
| Qualified evidence per run; reported unknowns | not recorded | **no: needs instrumentation** |

The missing rows are why the schedule's later blocks need per-stage triage metrics in the run records. Until they exist, comparisons can use only the rows marked "yes".

## Safety and deep-mode tests added

`tests/test_triage_safety_baseline.py`, in the CI group "Episode":

| Test | Rule (backlog) | Today on main | Expected fix branch |
|---|---|---|---|
| `test_a_triage_cannot_clear_on_a_timestamp_alone` | TRI-02 | **fails** (xfail) | `feature/triage-conclusion-gates` |
| `test_a_triage_cannot_clear_when_the_screening_omits_a_machine_on_the_roster` | TRI-22/33 | **fails** (xfail) | `feature/triage-conclusion-gates` |
| `test_a_triage_cannot_clear_on_a_screening_read_before_the_alarm` | TRI-21/33 | **fails** (xfail) | `feature/triage-conclusion-gates` |
| `test_a_triage_cannot_clear_while_a_rival_separating_question_is_open` (KA-09 shape) | TRI-02/03 | **fails** (xfail) | `feature/triage-conclusion-gates` |
| `test_an_open_rival_question_keeps_a_triage_diagnosis_unsupported` | TRI-03 | **fails** (xfail) | `feature/triage-evidence-tests` |
| `test_two_views_of_one_sensor_do_not_support_a_triage_diagnosis` | TRI-04 | **fails** (xfail) | `feature/triage-evidence-tests` |
| `test_a_triage_citing_a_full_screening_may_still_clear`, `test_two_different_sensors_support_a_triage_diagnosis` | over-blocking controls | pass | must keep passing |
| Three `test_deep_mode_…` pins and `test_a_scripted_deep_episode_takes_the_same_path_as_on_the_frozen_main` | deep mode unchanged | pass | must keep passing |

The `xfail` marks are strict: when a branch fixes one of these, the test passes, CI turns red, and the branch must remove the mark so the test becomes a permanent guard. A deep pin that fails means a triage branch changed deep mode.
