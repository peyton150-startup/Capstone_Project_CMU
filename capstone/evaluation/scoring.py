"""Scoring one investigation against the hidden truth (docs/MVP_SCOPE.md section 9).

The only place outside the simulator allowed to read the ground truth and
the hidden condition of the machines. It runs after the investigation is
over, so nothing it reads can reach the agent.
"""

from pydantic import BaseModel

from capstone.simulator.simulator import Simulator
from capstone.tools.diagnosis import Diagnosis

# What a good investigator does about each fault. None: leave the factory alone.
CORRECT_ACTION = {
    "bearing_degradation": "replace_bearing",
    "wrong_setting": "reset_setting",
    "bad_material_batch": None,
    "false_alarm": None,
}


# Stands in for a missing answer; never counts as right.
_NO_ANSWER = Diagnosis(fault="false_alarm", summary="no diagnosis submitted")


class Score(BaseModel):
    """One row of the results table."""

    true_fault: str
    true_machine_id: str | None
    true_batch_id: int | None
    diagnosed_fault: str | None  # None: the agent never gave an answer
    diagnosed_machine_id: str | None
    diagnosed_batch_id: int | None
    fault_correct: bool
    target_correct: bool
    expected_action: str | None
    actions_taken: list[str]  # actions carried out, as "action machine"
    action_correct: bool
    resolved: bool
    tool_calls: int
    ticks_elapsed: int


def evaluate(
    sim: Simulator,
    diagnosis: Diagnosis | None,
    proposals: list[dict],
    *,
    tool_calls: int,
    start_tick: int,
) -> Score:
    """Judge the agent's answer and actions, given the simulator as it stands at the end."""
    (truth,) = sim.ground_truth()
    if diagnosis is None:
        diagnosis = _NO_ANSWER
    expected = CORRECT_ACTION[truth.fault]
    # Approval alone changes nothing; only work that was started counts.
    done = [p for p in proposals if p.get("executed_tick") is not None]
    taken = [f"{p['action']} {p['machine_id']}" for p in done]
    wanted = [] if expected is None else [f"{expected} {truth.machine_id}"]

    if truth.fault == "bad_material_batch":
        target_correct = (
            diagnosis is not _NO_ANSWER and diagnosis.batch_id == truth.batch_id
        )
    else:
        target_correct = (
            diagnosis is not _NO_ANSWER and diagnosis.machine_id == truth.machine_id
        )

    return Score(
        true_fault=truth.fault,
        true_machine_id=truth.machine_id,
        true_batch_id=truth.batch_id,
        diagnosed_fault=None if diagnosis is _NO_ANSWER else diagnosis.fault,
        diagnosed_machine_id=diagnosis.machine_id,
        diagnosed_batch_id=diagnosis.batch_id,
        fault_correct=diagnosis is not _NO_ANSWER and diagnosis.fault == truth.fault,
        target_correct=target_correct,
        expected_action=expected,
        actions_taken=taken,
        action_correct=taken == wanted,
        resolved=_resolved(sim, truth),
        tool_calls=tool_calls,
        ticks_elapsed=sim.clock.tick - start_tick,
    )


def _resolved(sim: Simulator, truth) -> bool:
    """Is the cause gone from reality now? Read from hidden state, never from evidence."""
    state = sim.state
    if truth.fault == "bad_material_batch":
        return state.batch is not None and state.batch.id > truth.batch_id
    machine = state.machines[truth.machine_id]
    if truth.fault == "bearing_degradation":
        replaced = machine.bearing_replaced_tick
        return replaced is not None and replaced >= truth.start_tick
    if truth.fault == "wrong_setting":
        return machine.speed_setting is None
    return (
        machine.condition.vibration_sensor_offset == 0.0
    )  # false alarm: over by itself


def summarize(scores: list[Score]) -> dict:
    """Totals over many runs, e.g. "18/20 root causes correctly identified"."""
    n = len(scores)
    if n == 0:
        return {"runs": 0}
    count = lambda field: sum(getattr(s, field) for s in scores)  # noqa: E731
    return {
        "runs": n,
        "fault_correct": count("fault_correct"),
        "target_correct": count("target_correct"),
        "action_correct": count("action_correct"),
        "resolved": count("resolved"),
        "mean_tool_calls": sum(s.tool_calls for s in scores) / n,
        "mean_ticks": sum(s.ticks_elapsed for s in scores) / n,
    }


def format_summary(summary: dict) -> str:
    n = summary["runs"]
    if n == 0:
        return "no runs"
    return (
        f"{summary['fault_correct']}/{n} root causes correctly identified; "
        f"{summary['target_correct']}/{n} right machine or batch; "
        f"{summary['action_correct']}/{n} appropriate interventions; "
        f"{summary['resolved']}/{n} resolved; "
        f"average {summary['mean_tool_calls']:.1f} tool calls and {summary['mean_ticks']:.0f} ticks"
    )
