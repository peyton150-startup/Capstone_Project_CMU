"""The known-answer regression suite: fixed cases, pinned truth, offline runs.

The first test pins what each case is, so a simulator change that moves a
case fails here instead of silently changing results. The rest run every
case end to end through the harness with a scripted stand-in for the model
(MVP_SCOPE.md: "use scripted model stand-ins for deterministic offline
workflow tests"). The stand-in reads only working memory, looks once, and
admits it cannot tell; the suite checks the workflow and the scoring, not
the stand-in's skill. A live model is run on the same cases with
`python -m capstone.experiment run --known`.
"""

import pytest

from capstone.agent.artifacts import AgentConclusion
from capstone.agent.monitor import detect_anomaly
from capstone.episode import build_world
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.evaluation.scoring import COMPOUND, CORRECT_ACTION, _resolved
from capstone.experiment import known_cases, run_experiment
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.helpers import ScriptedPolicy, approve_and_run, ask

# scenario id: (true machine, true batch, what monitoring notices, on which machine)
PINNED = {
    "KA-01-bearing": ("CNC-02", None, "alarm", "CNC-02"),
    "KA-02-bearing": ("CNC-05", None, "alarm", "CNC-05"),
    "KA-03-batch": (None, 2, "inspection_failures", None),
    "KA-04-batch": (None, 2, "inspection_failures", None),
    "KA-05-setting": ("CNC-05", None, "inspection_failures", None),
    "KA-06-setting": ("CNC-03", None, "inspection_failures", None),
    "KA-07-false-alarm": ("CNC-01", None, "alarm", "CNC-01"),
    "KA-08-false-alarm": ("CNC-03", None, "alarm", "CNC-03"),
    # Several faults: no single machine. Monitoring first sees the harmless
    # spike on CNC-03, not the machine with the two real faults.
    "KA-09-challenge": (None, None, "alarm", "CNC-03"),
    # Forced-only faults: the servo controller's following-error alarm, and
    # the low-pressure alarm on a station fitted with hydraulics.
    "KA-10-servo": ("CNC-04", None, "alarm", "CNC-04"),
    "KA-11-servo": ("CNC-02", None, "alarm", "CNC-02"),
    "KA-12-hydraulic": ("CNC-05", None, "alarm", "CNC-05"),
    "KA-13-hydraulic": ("CNC-02", None, "alarm", "CNC-02"),
}

# The compound challenge: each true fault and where it is.
CHALLENGE_TRUTH = {
    ("bearing_degradation", "CNC-07"),
    ("wrong_setting", "CNC-07"),
    ("false_alarm", "CNC-03"),
    ("sensor_drift", "CNC-02"),
    ("sensor_dropout", "CNC-02"),
}

# What the look-once stand-in collects, and whether the cause is gone at the
# end. A batch is gone once the line has moved on to the next batch, which
# depends on how long the case ran, so this is pinned per case.
EXPECTED = {
    "KA-01-bearing": (["vibration of CNC-02"], False),
    "KA-02-bearing": (["vibration of CNC-05"], False),
    "KA-03-batch": (["inspection results"], True),
    "KA-04-batch": (["inspection results"], False),
    "KA-05-setting": (["inspection results"], False),
    "KA-06-setting": (["inspection results"], False),
    "KA-07-false-alarm": (["vibration of CNC-01"], True),
    "KA-08-false-alarm": (["vibration of CNC-03"], True),
    # Looking once at the decoy collects nothing about the two real causes.
    "KA-09-challenge": ([], False),
    # The stand-in reads vibration, which neither fault moves, and nothing is
    # repaired, so the cause is still there at the end.
    "KA-10-servo": ([], False),
    "KA-11-servo": ([], False),
    "KA-12-hydraulic": ([], False),
    "KA-13-hydraulic": ([], False),
}


def test_every_forced_only_case_needs_its_one_repair():
    """A servo drive or a hydraulic leak never clears by itself: the evaluator
    expects exactly its repair, so "leave it alone" scores as a miss."""
    # Variables:
    #   repairs: The one repair the evaluator should expect for each forced-only fault.
    #   forced: The known cases whose fault is one of them.
    repairs = {
        "servo_drive_wear": "replace_servo_drive",
        "hydraulic_leak": "repair_hydraulics",
    }
    forced = [c for c in KNOWN_CASES if c.fault in repairs]
    assert len(forced) == 4
    for case in forced:
        sim = build_world(case.seed, kind=case.kind, fault=case.fault)
        (truth,) = sim.ground_truth()
        assert CORRECT_ACTION[truth.fault] == repairs[case.fault]


@pytest.mark.parametrize(
    "case",
    [c for c in KNOWN_CASES if c.fault in ("servo_drive_wear", "hydraulic_leak")],
    ids=lambda c: c.scenario_id,
)
def test_a_forced_only_fault_counts_as_resolved_only_after_its_repair(case):
    """Scoring reads the repair tick the simulator sets, so waiting never
    clears the fault and the right repair always does."""
    # Variables:
    #   truth: The case's one real fault, with its machine and start tick.
    #   action: The repair the fault pack asks for.
    #   finish: The tick the repair ends, as the simulator reports it.
    sim = build_world(case.seed, kind=case.kind, fault=case.fault)
    (truth,) = sim.ground_truth()
    while sim.clock.tick <= truth.start_tick + 200:
        sim.step()
    assert not _resolved(sim, truth)  # still there after hundreds of ticks
    action = CORRECT_ACTION[truth.fault]
    desk = ApprovalDesk(sim)
    act = ActionTools(sim, desk)
    approve_and_run(
        desk, act, act.propose_action(truth.machine_id, action, "test")["id"]
    )
    finish = sim.state.machines[truth.machine_id].maintenance_until
    while sim.clock.tick <= finish:
        sim.step()
    assert _resolved(sim, truth)


@pytest.mark.parametrize("case", KNOWN_CASES, ids=lambda c: c.scenario_id)
def test_each_case_builds_its_pinned_fault_and_symptom(case):
    sim = build_world(case.seed, kind=case.kind, fault=case.fault)
    anomaly = detect_anomaly(ObservationTools(sim), ActionTools(sim, ApprovalDesk(sim)))
    machine, batch, kind, where = PINNED[case.scenario_id]
    assert (anomaly.kind, anomaly.machine_id) == (kind, where)
    if case.kind == "challenge":
        truths = {(t.fault, t.machine_id) for t in sim.ground_truth()}
        assert truths == CHALLENGE_TRUTH
        return
    (truth,) = sim.ground_truth()
    assert truth.fault == case.fault
    assert (truth.machine_id, truth.batch_id) == (machine, batch)


def look_once(state):
    """One look at the symptom monitoring named, from working memory only."""
    a = state.anomaly
    window = {"from_tick": max(0, a.tick - 300), "to_tick": a.tick}
    if a.machine_id is not None:
        return ask(
            "get_sensor_trend", machine_id=a.machine_id, sensor="vibration", **window
        )
    return ask("get_inspections", **window)


def stand_in():
    return ScriptedPolicy(
        {"investigate": [look_once]},
        conclude=lambda state: (
            AgentConclusion(
                diagnosis="undetermined", confidence=0.2, recommendation="escalate"
            ),
            None,
        ),
    )


@pytest.fixture(scope="module")
def records():
    return run_experiment(known_cases(), stand_in, name="known-answer-suite")


def test_every_case_gives_one_complete_record(records):
    assert [r.scenario_id for r in records] == [c.scenario_id for c in KNOWN_CASES]
    for record, case in zip(records, KNOWN_CASES, strict=True):
        score = record.score
        machine, batch, _, _ = PINNED[case.scenario_id]
        assert (score.true_fault, score.true_machine_id, score.true_batch_id) == (
            case.fault or COMPOUND,
            machine,
            batch,
        )
        if case.kind == "challenge":  # the two real causes, the rest distractors
            assert len(score.causes) == 2 and len(score.distractors) == 3
        assert record.conclusion == "undetermined"
        assert score.fault_correct is None  # free text, not yet labelled
        assert score.relevant_evidence  # every fault has evidence to find
        assert score.iterations > 0 and score.termination_reason is not None


def test_scores_match_the_pinned_expectations(records):
    for record in records:
        score = record.score
        collected, resolved = EXPECTED[record.scenario_id]
        assert score.relevant_evidence_collected == collected, record.scenario_id
        assert score.resolved is resolved, record.scenario_id
        # Asking for nothing is right exactly when nothing should be done.
        assert score.recommendation_correct is (not score.wanted_actions)
        assert score.actions_taken == []


def test_the_suite_is_repeatable(records):
    again = run_experiment(known_cases(), stand_in, name="known-answer-suite")
    # Everything seeded repeats; the wall clock is real time, so it cannot.
    real_time = {"wall_seconds"}
    assert [r.model_dump(exclude=real_time) for r in again] == [
        r.model_dump(exclude=real_time) for r in records
    ]


def test_no_record_shows_the_truth_to_the_policy(records):
    """The stand-in saw only working memory; the truth lives in the score."""
    seen = []

    def watching():
        policy = stand_in()
        seen.append(policy)
        return policy

    run_experiment(known_cases()[:2], watching, name="watch")
    for policy in seen:
        text = " ".join(s.model_dump_json() for s in policy.seen_states)
        assert "bearing_degradation" not in text and "ground_truth" not in text
