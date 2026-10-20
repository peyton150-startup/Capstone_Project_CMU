"""Scoring must be a pure read of the finished episode.

Why this file exists: an agent benchmark was found whose scorer changed the
environment before reading it, which moved its reported success rate from
94.3% to 65.5% (Chen, "When Agent Evaluation Becomes Unreliable", 2026,
https://arxiv.org/abs/2610.16067). `evaluate()` reads hidden state from the
simulator, so these tests pin that reading it changes nothing, gives the same
answer twice, and stays right as time moves on after the work.
"""

import pytest

from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.evaluation.scoring import CORRECT_ACTION, evaluate
from capstone.simulator.generator import build_scenario
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.diagnosis import Diagnosis
from tests.helpers import approve_and_run

TICKS = 2400  # long enough for every fault to have started and shown itself


def finished_episode(seed: int, fault: str):
    """A factory run with the right repair (or none) already carried out."""
    sim = build_scenario(seed, fault=fault)
    for _ in range(TICKS):
        sim.step()
    desk = ApprovalDesk(sim)
    act = ActionTools(sim, desk)
    (truth,) = sim.ground_truth()
    action = CORRECT_ACTION[fault]
    if action is not None:
        proposal = act.propose_action(truth.machine_id, action, "test")
        approve_and_run(desk, act, proposal["id"])
    act.wait(200)
    right = Diagnosis(fault=fault, machine_id=truth.machine_id, batch_id=truth.batch_id)
    return sim, desk, act, right


def score(sim, desk, diagnosis):
    return evaluate(sim, diagnosis, desk.proposals(), tool_calls=1, start_tick=TICKS)


def snapshot(sim) -> tuple:
    """Everything a later step depends on that can be compared directly."""
    return (sim.clock.tick, sim.state.model_dump(), len(sim.event_log.events))


def future(sim, ticks: int = 30) -> list:
    """The readings the next few ticks produce. Differs if the rng was touched."""
    return [[r.model_dump() for r in sim.step()] for _ in range(ticks)]


@pytest.mark.parametrize("case", KNOWN_CASES, ids=lambda c: c.scenario_id)
def test_scoring_does_not_change_the_simulator(case):
    scored, desk, _, right = finished_episode(case.seed, case.fault)
    twin, _, _, _ = finished_episode(case.seed, case.fault)
    before = snapshot(scored)

    score(scored, desk, right)
    score(scored, desk, Diagnosis(fault="false_alarm"))  # a wrong answer, too

    assert snapshot(scored) == before == snapshot(twin)
    assert future(scored) == future(twin)


@pytest.mark.parametrize("case", KNOWN_CASES, ids=lambda c: c.scenario_id)
def test_the_same_finished_episode_gets_the_same_score(case):
    sim, desk, _, right = finished_episode(case.seed, case.fault)
    twin, twin_desk, _, _ = finished_episode(case.seed, case.fault)

    first = score(sim, desk, right)
    assert score(sim, desk, right) == first
    assert score(twin, twin_desk, right) == first


@pytest.mark.parametrize("case", KNOWN_CASES, ids=lambda c: c.scenario_id)
def test_a_right_answer_stays_right_as_time_moves_on(case):
    sim, desk, act, right = finished_episode(case.seed, case.fault)
    marks = ("fault_correct", "target_correct", "action_correct", "resolved")

    first = score(sim, desk, right)
    act.wait(300)
    later = score(sim, desk, right)

    assert [getattr(first, m) for m in marks] == [True] * 4
    assert [getattr(later, m) for m in marks] == [True] * 4
