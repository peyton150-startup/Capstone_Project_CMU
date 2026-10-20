"""Scoring one investigation against the hidden truth (docs/MVP_SCOPE.md section 9).

The only place outside the simulator allowed to read the ground truth and
the hidden condition of the machines. It runs after the investigation is
over, so nothing it reads can reach the agent.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from capstone.simulator.simulator import Simulator
from capstone.tools.diagnosis import Diagnosis

# What a good investigator does about each fault. None: leave the factory alone.
CORRECT_ACTION = {
    "bearing_degradation": "replace_bearing",
    "wrong_setting": "reset_setting",
    "bad_material_batch": None,
    "false_alarm": None,
}


# The tools that read one machine sensor, by any route.
_SENSOR_TOOLS = ("get_readings", "get_sensor_trend", "get_sensor_summary")


@dataclass(frozen=True)
class Relevant:
    """One kind of evidence that bears on a fault. Evaluator-side only."""

    label: str
    tools: tuple[str, ...]
    sensor: str | None = None  # the sensor the call must name, if any
    on_machine: bool = False  # the call must be about the faulty machine

    def describe(self, machine_id: str | None) -> str:
        return self.label.format(machine=machine_id)

    def met_by(self, tool: str, arguments: Mapping, machine_id: str | None) -> bool:
        if tool not in self.tools:
            return False
        if self.sensor is not None and arguments.get("sensor") != self.sensor:
            return False
        if self.on_machine:
            # An event query for the whole factory also covers the machine.
            named = arguments.get("machine_id")
            whole_factory = tool == "get_events" and named is None
            return named == machine_id or whole_factory
        return True


# What an investigator could look at that bears on each fault: the "relevant
# evidence available" of MVP section 9. Read only by the evaluator, after the
# run; never shown to the agent, which must find these by itself.
RELEVANT_EVIDENCE: dict[str, tuple[Relevant, ...]] = {
    "bearing_degradation": (
        Relevant("vibration of {machine}", _SENSOR_TOOLS, "vibration", True),
        Relevant("temperature of {machine}", _SENSOR_TOOLS, "temperature", True),
        Relevant("events of {machine}", ("get_events",), on_machine=True),
    ),
    "wrong_setting": (
        Relevant("machine settings", ("get_settings",)),
        Relevant("inspection results", ("get_inspections",)),
        Relevant("vibration of {machine}", _SENSOR_TOOLS, "vibration", True),
    ),
    "bad_material_batch": (
        Relevant("inspection results", ("get_inspections",)),
        Relevant("events (material batches)", ("get_events",)),
        Relevant("a job's history", ("get_job_history",)),
    ),
    "false_alarm": (
        Relevant("vibration of {machine}", _SENSOR_TOOLS, "vibration", True),
        Relevant("events of {machine}", ("get_events",), on_machine=True),
    ),
}

# Ended because no model service answered: not a reasoning result.
MODEL_UNAVAILABLE = "model_unavailable"


# Why a diagnosis was wrong (Gopal & Krishnan 2026, arXiv 2607.13548): the
# agent never looked at some of the evidence that bore on the true fault, or
# it looked at all of it and still concluded wrongly. They need different
# fixes: better tools or investigation policy for the first, a better model
# or prompt for the second.
EVIDENCE_MISS = "evidence_miss"
REASONING_MISS = "reasoning_miss"


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
    # None: nobody has judged the agent's free-text diagnosis yet. Only a
    # label (by hand, or later an evaluator model) turns it into a Diagnosis.
    fault_correct: bool | None
    target_correct: bool | None
    expected_action: str | None
    actions_taken: list[str]  # actions carried out, as "action machine"
    action_correct: bool
    # What the agent asked for, whatever the human decided, as "action machine".
    recommended_actions: list[str] = Field(default_factory=list)
    # Did the agent ask for the right thing? Apart from whether it was allowed.
    recommendation_correct: bool = False
    # How each recommendation was decided: approved, rejected or pending.
    recommendation_status: list[str] = Field(default_factory=list)
    resolved: bool
    tool_calls: int
    ticks_elapsed: int
    iterations: int = 0
    # Why the investigation stopped. "model_unavailable" runs are left out of
    # the reasoning totals in `summarize`: the agent never got to reason.
    termination_reason: str | None = None
    # MVP section 9: the evidence that bore on the true fault, and which of it
    # the agent actually looked at.
    relevant_evidence: list[str] = Field(default_factory=list)
    relevant_evidence_collected: list[str] = Field(default_factory=list)

    @property
    def model_unavailable(self) -> bool:
        return self.termination_reason == MODEL_UNAVAILABLE

    @property
    def miss_kind(self) -> str | None:
        """Why the diagnosis was wrong: missed evidence, or misread it.

        None when the cause and the machine or batch were both right, when
        the diagnosis is not judged yet, and when no model answered. A
        missing answer counts as wrong like any other.
        """
        if self.model_unavailable or self.fault_correct is None:
            return None
        if self.fault_correct and self.target_correct:
            return None
        if len(self.relevant_evidence_collected) < len(self.relevant_evidence):
            return EVIDENCE_MISS
        return REASONING_MISS


def evaluate(
    sim: Simulator,
    diagnosis: Diagnosis | None,
    proposals: list[dict],
    *,
    tool_calls: int,
    start_tick: int,
    judged: bool = True,
    calls: Sequence[tuple[str, Mapping]] = (),
    iterations: int = 0,
    termination_reason: str | None = None,
) -> Score:
    """Judge the agent's answer and actions, given the simulator as it stands at the end.

    With `judged=False` the diagnosis is left unscored (None), not counted as
    wrong: the agent answered in words that nobody has labelled yet. The
    action and whether the cause is gone are scored either way.

    `calls` are the investigation's answered tool calls as (tool, arguments),
    used only to see which relevant evidence the agent collected.
    """
    (truth,) = sim.ground_truth()
    if diagnosis is None:
        diagnosis = _NO_ANSWER
    expected = CORRECT_ACTION[truth.fault]
    # Approval alone changes nothing; only work that was started counts.
    done = [p for p in proposals if p.get("executed_tick") is not None]
    taken = [f"{p['action']} {p['machine_id']}" for p in done]
    wanted = [] if expected is None else [f"{expected} {truth.machine_id}"]
    asked = [f"{p['action']} {p['machine_id']}" for p in proposals]
    relevant = RELEVANT_EVIDENCE[truth.fault]
    collected = [
        r
        for r in relevant
        if any(r.met_by(tool, args, truth.machine_id) for tool, args in calls)
    ]

    if truth.fault == "bad_material_batch":
        target_correct = (
            diagnosis is not _NO_ANSWER and diagnosis.batch_id == truth.batch_id
        )
    else:
        target_correct = (
            diagnosis is not _NO_ANSWER and diagnosis.machine_id == truth.machine_id
        )

    if not judged:
        diagnosis, fault_correct, target_correct = _NO_ANSWER, None, None
    else:
        fault_correct = diagnosis is not _NO_ANSWER and diagnosis.fault == truth.fault
    return Score(
        true_fault=truth.fault,
        true_machine_id=truth.machine_id,
        true_batch_id=truth.batch_id,
        diagnosed_fault=None if diagnosis is _NO_ANSWER else diagnosis.fault,
        diagnosed_machine_id=diagnosis.machine_id,
        diagnosed_batch_id=diagnosis.batch_id,
        fault_correct=fault_correct,
        target_correct=target_correct,
        expected_action=expected,
        actions_taken=taken,
        action_correct=taken == wanted,
        recommended_actions=asked,
        recommendation_correct=asked == wanted,
        recommendation_status=[p["status"] for p in proposals],
        resolved=_resolved(sim, truth),
        tool_calls=tool_calls,
        ticks_elapsed=sim.clock.tick - start_tick,
        iterations=iterations,
        termination_reason=termination_reason,
        relevant_evidence=[r.describe(truth.machine_id) for r in relevant],
        relevant_evidence_collected=[r.describe(truth.machine_id) for r in collected],
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
    """Totals over many runs, e.g. "18/20 root causes correctly identified".

    Runs that ended because no model answered are counted in `runs` and
    `model_unavailable` but left out of every other total: they measure the
    model services' uptime, not the agent's reasoning.
    """
    if not scores:
        return {"runs": 0}
    reasoned = [s for s in scores if not s.model_unavailable]
    n = len(reasoned)

    def count(field: str) -> int:
        return sum(bool(getattr(s, field)) for s in reasoned)

    def mean(values: list[float]) -> float:
        return sum(values) / n if n else 0.0

    available = sum(len(s.relevant_evidence) for s in reasoned)
    collected = sum(len(s.relevant_evidence_collected) for s in reasoned)
    return {
        "runs": len(scores),
        "model_unavailable": len(scores) - n,
        "scored": n,
        "judged": sum(s.fault_correct is not None for s in reasoned),
        "fault_correct": count("fault_correct"),
        "target_correct": count("target_correct"),
        "recommendation_correct": count("recommendation_correct"),
        "action_correct": count("action_correct"),
        "resolved": count("resolved"),
        "mean_tool_calls": mean([s.tool_calls for s in reasoned]),
        "mean_iterations": mean([s.iterations for s in reasoned]),
        "mean_ticks": mean([s.ticks_elapsed for s in reasoned]),
        # Share of the relevant evidence the agent looked at, over all runs.
        "relevant_evidence_share": collected / available if available else 0.0,
        # Wrong diagnoses, split by why: see `Score.miss_kind`.
        "evidence_misses": sum(s.miss_kind == EVIDENCE_MISS for s in reasoned),
        "reasoning_misses": sum(s.miss_kind == REASONING_MISS for s in reasoned),
    }


def format_summary(summary: dict) -> str:
    if summary["runs"] == 0:
        return "no runs"
    n = summary["scored"]
    judged = summary["judged"]
    unjudged = f" ({n - judged} not judged)" if judged < n else ""
    down = summary["model_unavailable"]
    outage = f"; {down} run(s) left out: no model answered" if down else ""
    return (
        f"{summary['fault_correct']}/{judged} root causes correctly identified"
        f"{unjudged}; "
        f"{summary['target_correct']}/{judged} right machine or batch; "
        f"{summary['recommendation_correct']}/{n} right recommendations; "
        f"{summary['action_correct']}/{n} appropriate interventions; "
        f"{summary['resolved']}/{n} resolved; "
        f"{summary['relevant_evidence_share']:.0%} of relevant evidence collected; "
        f"wrong diagnoses: {summary['evidence_misses']} missed evidence, "
        f"{summary['reasoning_misses']} misread it; "
        f"average {summary['mean_tool_calls']:.1f} tool calls, "
        f"{summary['mean_iterations']:.1f} iterations and "
        f"{summary['mean_ticks']:.0f} ticks{outage}"
    )
