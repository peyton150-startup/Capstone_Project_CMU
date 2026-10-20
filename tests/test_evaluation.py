import pytest
from pydantic import ValidationError

from capstone.evaluation.scoring import evaluate, format_summary, summarize
from capstone.simulator.generator import FAULTS, build_scenario
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.diagnosis import FAULT_KINDS, Diagnosis
from tests.helpers import approve_and_run


def episode(fault: str, seed: int = 4, ticks: int = 700):
    sim = build_scenario(seed, fault=fault)
    for _ in range(ticks):
        sim.step()
    desk = ApprovalDesk(sim)
    return sim, desk, ActionTools(sim, desk)


def truth(sim):
    (t,) = sim.ground_truth()
    return t


def test_the_agent_and_the_generator_agree_on_the_four_kinds_of_fault():
    assert set(FAULT_KINDS) == set(FAULTS)
    with pytest.raises(ValidationError):
        Diagnosis(fault="gremlins")


def test_a_perfect_bearing_investigation_scores_full_marks():
    sim, desk, act = episode("bearing_degradation")
    t = truth(sim)
    approve_and_run(
        desk,
        act,
        act.propose_action(t.machine_id, "replace_bearing", "vibration creeping up")[
            "id"
        ],
    )
    act.wait(60)
    score = evaluate(
        sim,
        Diagnosis(fault="bearing_degradation", machine_id=t.machine_id),
        desk.proposals(),
        tool_calls=9,
        start_tick=700,
    )
    assert (
        score.fault_correct,
        score.target_correct,
        score.action_correct,
        score.resolved,
    ) == (True,) * 4
    assert score.actions_taken == [f"replace_bearing {t.machine_id}"]
    assert (score.tool_calls, score.ticks_elapsed) == (9, 60)


def test_the_wrong_machine_and_the_wrong_repair_are_each_caught():
    sim, desk, act = episode("wrong_setting")
    t = truth(sim)
    other = next(m for m in sim.state.machines if m != t.machine_id)
    approve_and_run(
        desk, act, act.propose_action(other, "replace_bearing", "guess")["id"]
    )
    act.wait(50)
    score = evaluate(
        sim,
        Diagnosis(fault="bearing_degradation", machine_id=other),
        desk.proposals(),
        tool_calls=3,
        start_tick=700,
    )
    assert not (
        score.fault_correct
        or score.target_correct
        or score.action_correct
        or score.resolved
    )


def test_a_reset_resolves_a_wrong_setting():
    sim, desk, act = episode("wrong_setting")
    t = truth(sim)
    approve_and_run(
        desk,
        act,
        act.propose_action(t.machine_id, "reset_setting", "jobs faster in one step")[
            "id"
        ],
    )
    act.wait(20)
    score = evaluate(
        sim,
        Diagnosis(fault="wrong_setting", machine_id=t.machine_id),
        desk.proposals(),
        tool_calls=5,
        start_tick=700,
    )
    assert score.action_correct and score.resolved


@pytest.mark.parametrize("fault", ["false_alarm", "bad_material_batch"])
def test_doing_nothing_is_the_right_action_for_a_false_alarm_or_a_bad_batch(fault):
    sim, desk, act = episode(fault, ticks=2400)
    t = truth(sim)
    right = Diagnosis(fault=fault, machine_id=t.machine_id, batch_id=t.batch_id)
    score = evaluate(sim, right, desk.proposals(), tool_calls=4, start_tick=2400)
    assert (
        score.fault_correct
        and score.target_correct
        and score.action_correct
        and score.resolved
    )

    any_machine = next(iter(sim.state.machines))
    approve_and_run(
        desk,
        act,
        act.propose_action(any_machine, "replace_bearing", "just in case")["id"],
    )
    act.wait(50)
    score = evaluate(sim, right, desk.proposals(), tool_calls=5, start_tick=2400)
    assert not score.action_correct  # a needless repair is the wrong action


def test_rejected_proposals_do_not_count_as_actions():
    sim, desk, act = episode("false_alarm")
    desk.reject(
        act.propose_action(truth(sim).machine_id, "replace_bearing", "spike")["id"]
    )
    score = evaluate(
        sim,
        Diagnosis(fault="false_alarm", machine_id=truth(sim).machine_id),
        desk.proposals(),
        tool_calls=2,
        start_tick=700,
    )
    assert score.actions_taken == [] and score.action_correct


def test_a_bad_batch_is_not_resolved_while_it_is_still_in_use():
    sim = build_scenario(4, fault="bad_material_batch")
    t = truth(sim)
    while sim.state.batch is None or sim.state.batch.id < t.batch_id:
        sim.step()
    score = evaluate(
        sim,
        Diagnosis(fault="bad_material_batch", batch_id=t.batch_id),
        [],
        tool_calls=1,
        start_tick=0,
    )
    assert not score.resolved


def test_summary_counts_and_averages():
    sim, desk, _ = episode("false_alarm")
    t = truth(sim)
    good = evaluate(
        sim,
        Diagnosis(fault="false_alarm", machine_id=t.machine_id),
        [],
        tool_calls=4,
        start_tick=600,
    )
    bad = evaluate(
        sim,
        Diagnosis(fault="wrong_setting", machine_id=t.machine_id),
        [],
        tool_calls=8,
        start_tick=500,
    )
    summary = summarize([good, bad])
    assert summary == {
        "runs": 2,
        "model_unavailable": 0,
        "scored": 2,
        "judged": 2,
        "fault_correct": 1,
        "target_correct": 2,
        "recommendation_correct": 2,
        "action_correct": 2,
        "resolved": 2,
        "mean_tool_calls": 6.0,
        "mean_iterations": 0.0,
        "mean_ticks": 150.0,
        "relevant_evidence_share": 0.0,
        "evidence_misses": 1,
        "reasoning_misses": 0,
    }
    assert format_summary(summary).startswith("1/2 root causes correctly identified")
    assert summarize([]) == {"runs": 0}


def test_no_answer_scores_nothing_right_even_on_a_false_alarm():
    sim, desk, _ = episode("false_alarm")
    score = evaluate(sim, None, desk.proposals(), tool_calls=30, start_tick=700)
    assert (
        score.diagnosed_fault is None
        and not score.fault_correct
        and not score.target_correct
    )


def test_an_unlabelled_diagnosis_is_left_unscored_not_counted_wrong():
    sim, desk, _ = episode("false_alarm")
    score = evaluate(
        sim, None, desk.proposals(), tool_calls=4, start_tick=700, judged=False
    )
    assert (score.fault_correct, score.target_correct) == (None, None)
    assert score.diagnosed_fault is None
    assert score.action_correct and score.resolved  # still scored from reality
    right = evaluate(
        sim, Diagnosis(fault="false_alarm"), [], tool_calls=4, start_tick=700
    )
    summary = summarize([score, right])
    assert (summary["runs"], summary["judged"], summary["fault_correct"]) == (2, 1, 1)
    assert format_summary(summary).startswith(
        "1/1 root causes correctly identified (1 not judged)"
    )


# --- MVP section 9 fields: recommendation, evidence, model outages -------------


def test_a_rejected_recommendation_is_still_credited_as_the_right_request():
    sim, desk, act = episode("bearing_degradation")
    t = truth(sim)
    proposal = act.propose_action(t.machine_id, "replace_bearing", "vibration")
    desk.reject(proposal["id"], "not today")
    score = evaluate(sim, None, desk.proposals(), tool_calls=3, start_tick=600)
    assert score.recommended_actions == [f"replace_bearing {t.machine_id}"]
    assert score.recommendation_status == ["rejected"]
    assert score.recommendation_correct and not score.action_correct


def test_a_wrong_recommendation_is_not_credited():
    sim, desk, act = episode("false_alarm")
    t = truth(sim)
    act.propose_action(t.machine_id, "replace_bearing", "vibration spike")
    score = evaluate(sim, None, desk.proposals(), tool_calls=3, start_tick=600)
    assert not score.recommendation_correct


def test_relevant_evidence_lists_what_bore_on_the_fault_and_what_was_seen():
    sim, desk, _ = episode("bearing_degradation")
    t = truth(sim)
    calls = [
        ("get_sensor_trend", {"machine_id": t.machine_id, "sensor": "vibration"}),
        ("get_readings", {"machine_id": "CNC-99", "sensor": "temperature"}),
        ("get_events", {"from_tick": 0, "to_tick": 10}),  # the whole factory
    ]
    score = evaluate(
        sim, None, [], tool_calls=3, start_tick=600, calls=calls, iterations=5
    )
    assert score.relevant_evidence == [
        f"vibration of {t.machine_id}",
        f"temperature of {t.machine_id}",
        f"events of {t.machine_id}",
    ]
    # The temperature of a different machine does not count.
    assert score.relevant_evidence_collected == [
        f"vibration of {t.machine_id}",
        f"events of {t.machine_id}",
    ]
    assert score.iterations == 5
    assert summarize([score])["relevant_evidence_share"] == 2 / 3


def test_relevant_evidence_for_a_batch_fault_needs_no_machine():
    sim, desk, _ = episode("bad_material_batch")
    score = evaluate(
        sim,
        None,
        [],
        tool_calls=1,
        start_tick=600,
        calls=[("get_inspections", {"from_tick": 0, "to_tick": 600})],
    )
    assert score.relevant_evidence_collected == ["inspection results"]


def test_runs_without_a_model_are_left_out_of_the_reasoning_totals():
    sim, desk, _ = episode("false_alarm")
    t = truth(sim)
    right = Diagnosis(fault="false_alarm", machine_id=t.machine_id)
    reasoned = evaluate(sim, right, [], tool_calls=4, start_tick=600)
    outage = evaluate(
        sim,
        None,
        [],
        tool_calls=1,
        start_tick=600,
        termination_reason="model_unavailable",
    )
    assert outage.model_unavailable and not reasoned.model_unavailable
    summary = summarize([reasoned, outage])
    assert summary["runs"] == 2 and summary["model_unavailable"] == 1
    assert summary["scored"] == 1 and summary["judged"] == 1
    assert summary["fault_correct"] == 1 and summary["mean_tool_calls"] == 4.0
    text = format_summary(summary)
    assert text.startswith("1/1 root causes correctly identified")
    assert "1 run(s) left out: no model answered" in text


def test_only_outages_report_nothing_scored():
    sim, desk, _ = episode("false_alarm")
    outage = evaluate(
        sim, None, [], tool_calls=1, start_tick=600,
        termination_reason="model_unavailable",
    )  # fmt: skip
    summary = summarize([outage])
    assert summary["scored"] == 0 and summary["mean_tool_calls"] == 0.0


def scored(fault_right: bool, target_right: bool, seen: int, *, judged=True, stop=None):
    """A score with two relevant pieces of evidence, `seen` of them looked at."""
    sim, desk, _ = episode("false_alarm")
    t = truth(sim)
    fault = "false_alarm" if fault_right else "wrong_setting"
    machine = t.machine_id if target_right else "nowhere"
    calls = [("get_readings", {"machine_id": t.machine_id, "sensor": "vibration"})]
    calls += [("get_events", {"machine_id": t.machine_id})]
    return evaluate(
        sim,
        Diagnosis(fault=fault, machine_id=machine),
        [],
        tool_calls=seen,
        start_tick=700,
        calls=calls[:seen],
        judged=judged,
        termination_reason=stop,
    )


def test_a_wrong_diagnosis_without_all_the_evidence_is_an_evidence_miss():
    assert scored(False, True, seen=1).miss_kind == "evidence_miss"
    assert scored(True, False, seen=0).miss_kind == "evidence_miss"


def test_a_wrong_diagnosis_with_all_the_evidence_is_a_reasoning_miss():
    assert scored(False, True, seen=2).miss_kind == "reasoning_miss"
    assert scored(True, False, seen=2).miss_kind == "reasoning_miss"


def test_a_right_unjudged_or_unanswered_run_has_no_miss_kind():
    assert scored(True, True, seen=0).miss_kind is None
    assert scored(False, False, seen=0, judged=False).miss_kind is None
    assert scored(False, False, seen=0, stop="model_unavailable").miss_kind is None


def test_the_summary_counts_each_kind_of_miss():
    runs = [
        scored(False, True, seen=1),
        scored(False, True, seen=2),
        scored(True, False, seen=2),
        scored(True, True, seen=2),
    ]
    summary = summarize(runs)
    assert (summary["evidence_misses"], summary["reasoning_misses"]) == (1, 2)
    assert "wrong diagnoses: 1 missed evidence, 2 misread it" in format_summary(summary)
