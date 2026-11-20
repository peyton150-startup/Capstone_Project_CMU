"""The fixed triage questions ask for evidence that can tell causes apart.

Covers the four question-gap fixes (2026-11-20): a wrong setting found from job
times rather than a settings snapshot, the failed jobs the anomaly names read
over a long enough lookback, per-batch failure rates, and a sustained-reading
margin. Each unit check uses hand-made rows; two cases run the real simulator.
"""

import pytest

from capstone.agent.artifacts import DetectedAnomaly, TerminationReason
from capstone.agent.triage_decide import (
    SHIFT_FRACTION,
    batch_failure_rates,
    cycle_time_result,
    job_durations,
    job_time_baseline_result,
)
from capstone.agent.triage_plan import (
    BASELINE_JOB,
    RECORD_LOOKBACK_TICKS,
    fixed_requirements,
    named_failed_jobs,
)
from capstone.agent.triage_requirements import ReadRequirement
from tests.test_triage_graph_invariants import ConcludeOnly


def job(machine, number, start, worked):
    """The two events one finished job leaves on a station."""
    return [
        {"tick": start, "machine_id": machine, "kind": "job",
         "message": f"job {number} started", "job_id": number},
        {"tick": start + worked, "machine_id": machine, "kind": "job",
         "message": f"job {number} finished", "job_id": number},
    ]  # fmt: skip


def jobs(machine, times, first=1, start=0):
    """Back-to-back jobs on one station with the given ticks worked."""
    rows = []
    for offset, worked in enumerate(times):
        rows += job(machine, first + offset, start, worked)
        start += worked
    return rows


# --- which failed jobs the anomaly names --------------------------------------


def test_named_failed_jobs_reads_the_monitor_sentence():
    said = "3 of the last 10 jobs failed inspection (jobs 11, 13, 15)"
    anomaly = DetectedAnomaly(tick=900, kind="inspection_failures", description=said)
    assert named_failed_jobs(anomaly) == (11, 13, 15)


@pytest.mark.parametrize(
    ("kind", "said"),
    [
        ("inspection_failures", "3 parts failed"),
        ("alarm", "alarm on CNC-02: vibration 4.80 mm/s above 4.50 (jobs 1, 2)"),
    ],
)
def test_named_failed_jobs_is_empty_without_a_named_list(kind, said):
    anomaly = DetectedAnomaly(tick=40, kind=kind, description=said)
    assert named_failed_jobs(anomaly) == ()


def test_named_failed_jobs_belong_only_to_inspection_requirements():
    with pytest.raises(ValueError, match="inspection requirements"):
        ReadRequirement(
            requirement_id="Q1:x", question_id="Q1", tool="get_events",
            failed_job_ids=(3,),
        )  # fmt: skip


# --- the requirements each anomaly gets --------------------------------------


def test_inspection_failures_read_named_jobs_over_the_lookback_and_job_one():
    said = "3 of the last 10 jobs failed inspection (jobs 11, 13, 15)"
    anomaly = DetectedAnomaly(tick=1000, kind="inspection_failures", description=said)
    made = fixed_requirements(anomaly, cutoff_tick=1000)
    for rid in ("Q1:failed_jobs", "Q2:inspections"):
        assert made[rid].failed_job_ids == (11, 13, 15)
        assert (made[rid].from_tick, made[rid].to_tick) == (
            1000 - RECORD_LOOKBACK_TICKS,
            1000,
        )
    baseline = made["Q3:baseline_job"]
    assert baseline.tool == "get_job_history"
    assert baseline.job_id == BASELINE_JOB
    assert baseline.qualification == "job_time_baseline"
    assert not any(r.tool == "get_settings" for r in made.values())


def test_an_alarm_asks_for_job_times_since_the_start_not_a_settings_snapshot():
    said = "alarm on CNC-02: vibration 4.80 mm/s above 4.50"
    anomaly = DetectedAnomaly(
        tick=900, kind="alarm", machine_id="CNC-02", description=said
    )
    made = fixed_requirements(anomaly, cutoff_tick=905)
    shift = made["Q4:cycle_time"]
    assert (shift.tool, shift.machine_id) == ("get_events", "CNC-02")
    assert (shift.from_tick, shift.to_tick) == (0, 905)
    assert shift.qualification == "cycle_time_shift"
    assert "Q4:setting_change" not in made


# --- job times --------------------------------------------------------------------


def test_job_durations_pairs_starts_with_finishes_and_drops_unfinished_jobs():
    rows = jobs("CNC-01", [50, 52]) + [
        {"tick": 200, "machine_id": "CNC-01", "kind": "job",
         "message": "job 9 started", "job_id": 9},
        {"tick": 210, "machine_id": "CNC-01", "kind": "alarm",
         "message": "job 9 finished", "job_id": 9},
    ]  # fmt: skip
    assert job_durations(rows) == {"CNC-01": [(0, 50), (50, 52)]}


def test_a_step_in_job_times_is_reported_with_its_size_and_tick():
    rows = jobs("CNC-03", [50, 51, 50, 64, 65, 64]) + jobs("CNC-01", [40] * 6)
    result = cycle_time_result(rows, ("e1",))
    assert result.status == "satisfied"
    assert result.reason.startswith("largest change in mean job time at one point:")
    assert "CNC-03 50.3 to 64.3 ticks per job (+28%) around tick 151" in result.reason
    assert "CNC-01" not in result.reason


def test_steady_job_times_are_reported_as_no_shift():
    result = cycle_time_result(jobs("CNC-01", [50, 52, 51, 50, 52]), ("e1",))
    assert result.status == "satisfied"
    assert result.reason == (
        f"no station's mean job time changed by {SHIFT_FRACTION:.0%} or more at "
        "any one point (CNC-01 compared)"
    )


def test_too_few_jobs_keep_the_job_time_question_open():
    result = cycle_time_result(jobs("CNC-01", [50, 60, 61]), ("e1",))
    assert result.status == "insufficient"
    assert result.reason == "too few finished jobs to compare job times"


# --- failed jobs against the first job ------------------------------------------


def test_a_station_slower_on_every_failed_job_than_on_job_one_is_named():
    baseline = job("CNC-03", 1, 0, 53) + job("CNC-01", 1, 60, 40)
    failed = {
        14: job("CNC-03", 14, 700, 68) + job("CNC-01", 14, 800, 41),
        19: job("CNC-03", 19, 990, 65) + job("CNC-01", 19, 1100, 40),
    }
    result = job_time_baseline_result(baseline, failed, ("e1", "e2"))
    assert result.status == "satisfied"
    assert result.reason == (
        "a station worked every failed job at a different pace than the first "
        "job: CNC-03 53 ticks on the first job, 68, 65 on failed jobs 14, 19 (+25%)"
    )


def test_a_pace_change_on_only_some_failed_jobs_is_not_named():
    baseline = job("CNC-03", 1, 0, 50)
    failed = {14: job("CNC-03", 14, 700, 65), 19: job("CNC-03", 19, 990, 51)}
    result = job_time_baseline_result(baseline, failed, ("e1",))
    assert result.status == "satisfied"
    assert result.reason.startswith("no station worked every failed job at a pace")


def test_one_failed_job_is_too_few_to_compare_against_job_one():
    result = job_time_baseline_result(
        job("CNC-03", 1, 0, 50), {14: job("CNC-03", 14, 700, 70)}, ("e1",)
    )
    assert result.status == "insufficient"


# --- per-batch failure rates ----------------------------------------------------


def test_batch_rates_contrast_the_failing_batch_with_the_others():
    rows = [
        {"tick": t, "job_id": j, "batch_id": b, "result": r}
        for t, j, b, r in [
            (1, 1, 1, "passed"), (2, 2, 1, "passed"), (3, 3, 2, "failed"),
            (4, 4, 2, "failed"), (5, 5, 2, "passed"),
        ]
    ]  # fmt: skip
    # A job read twice (two overlapping reads) counts once.
    assert batch_failure_rates([("e1", rows), ("e2", rows[:2])]) == (
        " (inspected jobs: batch 1: 0 of 2 failed; batch 2: 2 of 3 failed)"
    )


def test_batch_rates_say_when_no_other_batch_was_inspected():
    rows = [{"tick": 1, "job_id": 4, "batch_id": 2, "result": "failed"}]
    assert batch_failure_rates([("e1", rows)]) == (
        " (inspected jobs: batch 2: 1 of 1 failed; no other batch inspected "
        "in the read)"
    )
    assert batch_failure_rates([("e1", {"not": "rows"})]) == ""


# --- the real simulator ------------------------------------------------------------


def run_known_case(scenario_id, monkeypatch):
    """Run one known case through deterministic triage with a scripted conclusion."""
    from capstone.episode import run_episode
    from capstone.evaluation.known_answers import KNOWN_CASES
    from capstone.settings import get_settings

    for key, value in {
        "TRIAGE_RUN_MODE": "deterministic",
        "TRIAGE": "on",
        "TRIAGE_THEN_DEEP": "off",
        "CRITIC": "off",
    }.items():
        monkeypatch.setenv(key, value)
    if hasattr(get_settings, "cache_clear"):
        get_settings.cache_clear()
    case = next(c for c in KNOWN_CASES if c.scenario_id == scenario_id)
    try:
        return run_episode(
            case.seed, ConcludeOnly(), kind=case.kind, fault=case.fault, triage=True
        ).state
    finally:
        if hasattr(get_settings, "cache_clear"):
            get_settings.cache_clear()


def test_a_wrong_setting_shows_as_one_station_pacing_differently(monkeypatch):
    """KA-06 (offline probe, 2026-11-20): CNC-03 works the failed jobs slower."""
    state = run_known_case("KA-06-setting", monkeypatch)
    result = state.triage_requirement_results["Q3:baseline_job"]
    assert result.status == "satisfied"
    assert result.reason.startswith("a station worked every failed job")
    assert "CNC-03" in result.reason


def test_a_bad_batch_case_completes_with_contrasting_batch_rates(monkeypatch):
    """KA-03: every question settles, and the batch reason shows the contrast."""
    state = run_known_case("KA-03-batch", monkeypatch)
    assert state.termination_reason is TerminationReason.EVIDENCE_SUFFICIENT
    batch = state.triage_requirement_results["Q2:inspections"]
    assert batch.status == "satisfied"
    assert "(inspected jobs: batch" in batch.reason
    assert "no other batch inspected" not in batch.reason
