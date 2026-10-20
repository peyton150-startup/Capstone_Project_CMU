"""The rule-based baseline: tools only, repeatable, and pinned on the known cases."""

import pytest

from capstone.agent.monitor import detect_anomaly
from capstone.baseline import (
    _job_time_changes,
    _standout_batch,
    diagnose,
    run_baseline,
)
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.simulator.generator import build_scenario
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools

OBSERVATION_TOOLS = {
    name
    for name in dir(ObservationTools)
    if not name.startswith("_") and callable(getattr(ObservationTools, name))
}


class PublicOnly:
    """Forwards public methods only: reaching for `_sim` raises, as it should."""

    def __init__(self, tools):
        self._tools = tools

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(f"the baseline reached for {name}")
        return getattr(self._tools, name)


def setup(case):
    sim = build_scenario(case.seed, fault=case.fault)
    desk = ApprovalDesk(sim)
    look, act = ObservationTools(sim), ActionTools(sim, desk)
    anomaly = detect_anomaly(look, act)
    return sim, desk, PublicOnly(look), PublicOnly(act), anomaly


@pytest.mark.parametrize("case", KNOWN_CASES, ids=lambda c: c.scenario_id)
def test_the_rules_use_only_the_agents_tools_and_ask_for_nothing_themselves(case):
    sim, desk, look, act, anomaly = setup(case)
    verdict = diagnose(look, act, anomaly)
    assert {tool for tool, _ in verdict.calls} <= OBSERVATION_TOOLS | {"wait"}
    assert desk.proposals() == []  # proposing is the runner's job, as for the agent


# What the rules make of each known case: (cause named, right machine or batch).
# KA-05: the setting went wrong before CNC-05 had run any jobs, so there is
# no "before" to compare its job times with; the rules name the cause only.
EXPECTED = {
    "KA-01-bearing": ("bearing_degradation", True),
    "KA-02-bearing": ("bearing_degradation", True),
    "KA-03-batch": ("bad_material_batch", True),
    "KA-04-batch": ("bad_material_batch", True),
    "KA-05-setting": ("wrong_setting", False),
    "KA-06-setting": ("wrong_setting", True),
    "KA-07-false-alarm": ("false_alarm", True),
    "KA-08-false-alarm": ("false_alarm", True),
}


@pytest.mark.parametrize("case", KNOWN_CASES, ids=lambda c: c.scenario_id)
def test_known_cases_score_as_pinned_and_repeat_exactly(case):
    score = run_baseline(case.seed, case.fault)
    assert (score.diagnosed_fault, score.target_correct) == EXPECTED[case.scenario_id]
    assert score.fault_correct
    assert run_baseline(case.seed, case.fault) == score


def test_the_right_repair_is_carried_out_and_nothing_for_a_false_alarm():
    bearing = run_baseline(6, "bearing_degradation")
    false_alarm = run_baseline(8, "false_alarm")
    assert bearing.actions_taken and bearing.action_correct and bearing.resolved
    assert false_alarm.actions_taken == [] and false_alarm.action_correct


def job(tick, machine, job_id, what):
    return {"tick": tick, "machine_id": machine, "kind": "job", "job_id": job_id,
            "message": f"job {job_id} {what}"}  # fmt: skip


def jobs_on(machine, lengths):
    events, tick = [], 0
    for number, length in enumerate(lengths, start=1):
        events += [job(tick, machine, number, "started")]
        tick += length
        events += [job(tick, machine, number, "finished")]
    return events


def test_job_times_compare_the_last_jobs_with_the_first():
    events = jobs_on("A", [50] * 4 + [40] * 4) + jobs_on("B", [30] * 8)
    assert _job_time_changes(events) == {"A": 0.8, "B": 1.0}
    assert _job_time_changes(jobs_on("C", [30] * 7)) == {}  # too few to compare


def inspections(batch, fails, total):
    return [
        {"batch_id": batch, "result": "failed" if n < fails else "passed"}
        for n in range(total)
    ]


def test_a_batch_must_stand_far_above_the_rest_of_the_line():
    line = inspections(1, 0, 10) + inspections(3, 0, 10)
    assert _standout_batch(line + inspections(2, 3, 10)) == 2
    assert _standout_batch(line + inspections(2, 1, 10)) is None  # one reject is noise
    spread = inspections(1, 3, 10) + inspections(2, 3, 10)
    assert _standout_batch(spread) is None  # rejects everywhere: not a batch
