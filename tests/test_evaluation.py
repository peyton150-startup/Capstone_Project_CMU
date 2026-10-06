import pytest
from pydantic import ValidationError

from capstone.evaluation.scoring import evaluate, format_summary, summarize
from capstone.simulator.generator import FAULTS, build_scenario
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.diagnosis import FAULT_KINDS, Diagnosis


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
    desk.approve(act.propose_action(t.machine_id, "replace_bearing", "vibration creeping up")["id"])
    act.wait(60)
    score = evaluate(sim, Diagnosis(fault="bearing_degradation", machine_id=t.machine_id), desk.proposals(),
                     tool_calls=9, start_tick=700)
    assert (score.fault_correct, score.target_correct, score.action_correct, score.resolved) == (True,) * 4
    assert score.actions_taken == [f"replace_bearing {t.machine_id}"]
    assert (score.tool_calls, score.ticks_elapsed) == (9, 60)


def test_the_wrong_machine_and_the_wrong_repair_are_each_caught():
    sim, desk, act = episode("wrong_setting")
    t = truth(sim)
    other = next(m for m in sim.state.machines if m != t.machine_id)
    desk.approve(act.propose_action(other, "replace_bearing", "guess")["id"])
    act.wait(50)
    score = evaluate(sim, Diagnosis(fault="bearing_degradation", machine_id=other), desk.proposals(),
                     tool_calls=3, start_tick=700)
    assert not (score.fault_correct or score.target_correct or score.action_correct or score.resolved)


def test_a_reset_resolves_a_wrong_setting():
    sim, desk, act = episode("wrong_setting")
    t = truth(sim)
    desk.approve(act.propose_action(t.machine_id, "reset_setting", "jobs faster in one step")["id"])
    act.wait(20)
    score = evaluate(sim, Diagnosis(fault="wrong_setting", machine_id=t.machine_id), desk.proposals(),
                     tool_calls=5, start_tick=700)
    assert score.action_correct and score.resolved


@pytest.mark.parametrize("fault", ["false_alarm", "bad_material_batch"])
def test_doing_nothing_is_the_right_action_for_a_false_alarm_or_a_bad_batch(fault):
    sim, desk, act = episode(fault, ticks=2400)
    t = truth(sim)
    right = Diagnosis(fault=fault, machine_id=t.machine_id, batch_id=t.batch_id)
    score = evaluate(sim, right, desk.proposals(), tool_calls=4, start_tick=2400)
    assert score.fault_correct and score.target_correct and score.action_correct and score.resolved

    any_machine = next(iter(sim.state.machines))
    desk.approve(act.propose_action(any_machine, "replace_bearing", "just in case")["id"])
    act.wait(50)
    score = evaluate(sim, right, desk.proposals(), tool_calls=5, start_tick=2400)
    assert not score.action_correct  # a needless repair is the wrong action


def test_rejected_proposals_do_not_count_as_actions():
    sim, desk, act = episode("false_alarm")
    desk.reject(act.propose_action(truth(sim).machine_id, "replace_bearing", "spike")["id"])
    score = evaluate(sim, Diagnosis(fault="false_alarm", machine_id=truth(sim).machine_id), desk.proposals(),
                     tool_calls=2, start_tick=700)
    assert score.actions_taken == [] and score.action_correct


def test_a_bad_batch_is_not_resolved_while_it_is_still_in_use():
    sim = build_scenario(4, fault="bad_material_batch")
    t = truth(sim)
    while sim.state.batch is None or sim.state.batch.id < t.batch_id:
        sim.step()
    score = evaluate(sim, Diagnosis(fault="bad_material_batch", batch_id=t.batch_id), [], tool_calls=1, start_tick=0)
    assert not score.resolved


def test_summary_counts_and_averages():
    sim, desk, _ = episode("false_alarm")
    t = truth(sim)
    good = evaluate(sim, Diagnosis(fault="false_alarm", machine_id=t.machine_id), [], tool_calls=4, start_tick=600)
    bad = evaluate(sim, Diagnosis(fault="wrong_setting", machine_id=t.machine_id), [], tool_calls=8, start_tick=500)
    summary = summarize([good, bad])
    assert summary == {"runs": 2, "fault_correct": 1, "target_correct": 2, "action_correct": 2, "resolved": 2,
                       "mean_tool_calls": 6.0, "mean_ticks": 150.0}
    assert format_summary(summary).startswith("1/2 root causes correctly identified")
    assert summarize([]) == {"runs": 0}
