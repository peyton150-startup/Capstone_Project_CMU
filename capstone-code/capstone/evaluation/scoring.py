"""Scoring one investigation against the hidden truth (docs/MVP_SCOPE.md section 9).

The only place outside the simulator allowed to read the ground truth and
the hidden condition of the machines. It runs after the investigation is
over, so nothing it reads can reach the agent.
"""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from capstone.faults import PACKS, Relevant
from capstone.simulator.simulator import Simulator
from capstone.tools.diagnosis import Diagnosis

# From the fault packs' evaluator side (`capstone/faults.py`). Read only here,
# after the run; never shown to the agent.
# What a good investigator does about each fault. None: leave the factory alone.
CORRECT_ACTION = {pack.kind: pack.evaluator.correct_action for pack in PACKS}

# What an investigator could look at that bears on each fault: the "relevant
# evidence available" of MVP section 9. The agent must find these by itself.
RELEVANT_EVIDENCE: dict[str, tuple[Relevant, ...]] = {
    pack.kind: pack.evaluator.relevant for pack in PACKS
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


# A run with more than one true fault (e.g. `capstone.simulator.challenge`).
COMPOUND = "compound"

# The faults that need fixing or naming as a cause. In a run with several
# true faults the others (a passing spike, a drifting or silent sensor) are
# distractors: nothing to fix, and blaming one is a wrong cause. A run with
# one true fault has that one as its cause, whatever it is.
CAUSE_KINDS = tuple(pack.kind for pack in PACKS if pack.evaluator.is_cause)


class Cause(BaseModel):
    """One true fault in a run's record. Evaluator-side only."""

    model_config = ConfigDict(frozen=True)

    fault: str
    machine_id: str | None = None
    batch_id: int | None = None

    @classmethod
    def of(cls, truth) -> "Cause":
        return cls(
            fault=truth.fault, machine_id=truth.machine_id, batch_id=truth.batch_id
        )

    def describe(self) -> str:
        where = self.machine_id if self.batch_id is None else f"batch {self.batch_id}"
        return f"{self.fault} {where}"

    def named_by(self, diagnosis: Diagnosis) -> bool:
        """Does this named cause name this fault, on the right machine or batch?"""
        # Variables:
        #   diagnosis: A cause the agent named, which must match both the fault kind and
        #     the machine or batch.
        if diagnosis.fault != self.fault:
            return False
        if self.batch_id is not None:
            return diagnosis.batch_id == self.batch_id
        return diagnosis.machine_id == self.machine_id


def judge_causes(
    causes: Sequence[Cause], named: Sequence[Diagnosis]
) -> tuple[int, int]:
    """How many true causes are named, and how many wrong causes are named.

    Naming a false alarm says nothing needs fixing there, so it is never a
    wrong cause; any other named fault that matches no true cause is one
    (including blaming a distractor's machine).
    """
    # Variables:
    #   causes: The true faults that need naming.
    #   named: The causes the agent's conclusion named.
    #   found: How many true causes were named.
    #   wrong: How many named faults match no true cause; a named false alarm is never
    #     wrong.
    found = sum(any(cause.named_by(d) for d in named) for cause in causes)
    wrong = sum(
        d.fault != "false_alarm" and not any(cause.named_by(d) for cause in causes)
        for d in named
    )
    return found, wrong


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
    # Every true cause, and with several true faults the distractors. Empty in
    # results from before these were kept.
    causes: list[Cause] = Field(default_factory=list)
    distractors: list[Cause] = Field(default_factory=list)
    # Partial credit: causes named, wrong causes named (None: not judged), and
    # causes gone from reality at the end.
    causes_found: int | None = None
    wrong_causes: int | None = None
    causes_resolved: int = 0
    # The fixes the true causes needed, as "action machine".
    wanted_actions: list[str] = Field(default_factory=list)

    @property
    def fully_right(self) -> bool | None:
        """Every cause named and no wrong cause; None until judged."""
        if self.causes_found is None:  # not judged, or results from before
            return None
        return self.causes_found == len(self.causes) and self.wrong_causes == 0

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

    @property
    def unnecessary_actions(self) -> list[str]:
        """What the agent asked for that the true fault did not need.

        Apart from a missed fix: on a false alarm or a bad batch any request
        is unnecessary, and a fix on the wrong machine is too. Counted from
        what was asked, whatever the human decided: a rejection is the
        human's catch, not the agent's judgement. Read from stored fields,
        so older results files have it too.
        """
        # Variables:
        #   needed: The fixes the true causes called for, as 'action machine'.
        #   wanted: In a one-fault run, the single fix the fault needed, or None if it
        #     needed none.
        if self.causes:
            needed = set(self.wanted_actions)
            return [asked for asked in self.recommended_actions if asked not in needed]
        wanted = (
            None
            if self.expected_action is None
            else f"{self.expected_action} {self.true_machine_id}"
        )
        return [asked for asked in self.recommended_actions if asked != wanted]


def evaluate(
    sim: Simulator,
    diagnosis: Diagnosis | Sequence[Diagnosis] | None,
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

    With several true faults (`COMPOUND`), the causes (`CAUSE_KINDS`) are what
    must be named, fixed and gone; the rest are distractors. The fixes are
    compared as a set, `resolved` means every cause is gone, and relevant
    evidence is that of every cause. With one true fault, the same numbers
    come out as they always have.

    `calls` are the investigation's answered tool calls as (tool, arguments),
    used only to see which relevant evidence the agent collected.
    """
    # Variables:
    #   sim: The simulator as it stands at the end of the run; its hidden truth is read
    #     here.
    #   diagnosis: What the agent's conclusion was turned into, if anything.
    #   proposals: Every request the agent made, with the human's decision.
    #   tool_calls: How many tool calls the investigation made.
    #   start_tick: The tick the investigation began, to measure how long it took.
    #   judged: If False, the diagnosis is left unscored instead of counted as wrong.
    #   calls: The answered tool calls as (tool, arguments), used to see which evidence
    #     was collected.
    #   iterations: How many loop turns were used.
    #   truths: The real faults, read from the simulator.
    #   compound: True when more than one real fault was present.
    #   causes: The faults that must be named, fixed and gone.
    #   distractors: Faults that need nothing done, such as a passing spike or a
    #     drifting sensor.
    #   done: Proposals whose work actually started; approval alone changes nothing.
    #   taken: Fixes carried out, as 'action machine'.
    #   wanted: Fixes the true causes needed.
    #   asked: Everything the agent asked for, whatever the human decided.
    #   relevant: Evidence that bears on a cause, paired with that cause's machine.
    #   seen: Relevant evidence the agent actually looked at.
    #   described: Each relevant item once, in words.
    #   gone: For each cause, whether it is gone from reality now.
    #   single: The one true fault in a one-fault run; None when there are several.
    truths = sim.ground_truth()
    compound = len(truths) > 1
    if compound:
        causes = [t for t in truths if t.fault in CAUSE_KINDS]
        distractors = [t for t in truths if t.fault not in CAUSE_KINDS]
    else:
        causes, distractors = list(truths), []
    # Approval alone changes nothing; only work that was started counts.
    done = [p for p in proposals if p.get("executed_tick") is not None]
    taken = [f"{p['action']} {p['machine_id']}" for p in done]
    wanted = [
        f"{CORRECT_ACTION[t.fault]} {t.machine_id}"
        for t in causes
        if CORRECT_ACTION[t.fault] is not None
    ]
    asked = [f"{p['action']} {p['machine_id']}" for p in proposals]
    relevant = [(r, t.machine_id) for t in causes for r in RELEVANT_EVIDENCE[t.fault]]
    seen = {
        r.describe(machine)
        for r, machine in relevant
        if any(r.met_by(tool, args, machine) for tool, args in calls)
    }
    described = list(dict.fromkeys(r.describe(machine) for r, machine in relevant))
    gone = [_resolved(sim, t) for t in causes]
    single = None if compound else truths[0]

    score = Score(
        true_fault=COMPOUND if single is None else single.fault,
        true_machine_id=None if single is None else single.machine_id,
        true_batch_id=None if single is None else single.batch_id,
        diagnosed_fault=None,
        diagnosed_machine_id=None,
        diagnosed_batch_id=None,
        fault_correct=None,
        target_correct=None,
        expected_action=None if single is None else CORRECT_ACTION[single.fault],
        actions_taken=taken,
        action_correct=sorted(taken) == sorted(wanted),
        recommended_actions=asked,
        recommendation_correct=sorted(asked) == sorted(wanted),
        recommendation_status=[p["status"] for p in proposals],
        resolved=all(gone),
        tool_calls=tool_calls,
        ticks_elapsed=sim.clock.tick - start_tick,
        iterations=iterations,
        termination_reason=termination_reason,
        relevant_evidence=described,
        relevant_evidence_collected=[d for d in described if d in seen],
        causes=[Cause.of(t) for t in causes],
        distractors=[Cause.of(t) for t in distractors],
        causes_resolved=sum(gone),
        wanted_actions=wanted,
    )
    return judge(score, diagnosis) if judged else score


def _named(diagnosis: Diagnosis | Sequence[Diagnosis] | None) -> list[Diagnosis]:
    if diagnosis is None:
        return []
    if isinstance(diagnosis, Diagnosis):
        return [diagnosis]
    return list(diagnosis)


def judge(score: Score, diagnosis: Diagnosis | Sequence[Diagnosis] | None) -> Score:
    """The same row with its root cause judged from what the conclusion names.

    `diagnosis` is one cause or a list of them (a conclusion may name
    several); None or an empty list means it names no recognisable cause,
    which counts as wrong. Uses only the truth already in the row, so a run
    can be judged long after it ended.

    One true fault: right cause and right machine or batch, as always. Several
    (`COMPOUND`): the run is right only when every cause is named and no wrong
    cause is, and `causes_found` / `wrong_causes` give the partial credit.
    """
    # Variables:
    #   score: The row built from the simulator, with the diagnosis still unfilled.
    #   diagnosis: One named cause or several; None or empty counts as wrong.
    #   named: The named causes as a list.
    #   update: The fields to change on the row.
    #   found: How many true causes were named.
    #   wrong: How many wrong causes were named.
    #   shown: The one named cause the row is judged and reported by.
    #   right: True when every cause is named and no wrong one is.
    #   truth: The real fault of a one-fault run, rebuilt from the row.
    named = _named(diagnosis)
    update: dict = {}
    found, wrong = judge_causes(score.causes, named)
    if score.causes or score.true_fault == COMPOUND:  # not in older results
        update.update(causes_found=found, wrong_causes=wrong)
    if score.true_fault == COMPOUND:
        shown = named[0] if named else None
        right = found == len(score.causes) and wrong == 0
        fault_correct = target_correct = right
    else:
        truth = Cause(
            fault=score.true_fault,
            machine_id=score.true_machine_id,
            batch_id=score.true_batch_id,
        )
        shown = _closest(truth, named)
        if shown is None:
            fault_correct = target_correct = False
        else:
            fault_correct = shown.fault == truth.fault
            target_correct = (
                shown.batch_id == truth.batch_id
                if truth.fault == "bad_material_batch"
                else shown.machine_id == truth.machine_id
            )
    update.update(
        diagnosed_fault=None if shown is None else shown.fault,
        diagnosed_machine_id=None if shown is None else shown.machine_id,
        diagnosed_batch_id=None if shown is None else shown.batch_id,
        fault_correct=fault_correct,
        target_correct=target_correct,
    )
    return score.model_copy(update=update)


def _closest(truth: Cause, named: list[Diagnosis]) -> Diagnosis | None:
    """The named cause to judge a one-fault run by: the one that names the
    truth, else one of the right kind, else the first."""
    # Variables:
    #   fits: Tests tried in turn: names the truth exactly, then right kind of fault,
    #     then anything.
    for fits in (truth.named_by, lambda d: d.fault == truth.fault, lambda d: True):
        for diagnosis in named:
            if fits(diagnosis):
                return diagnosis
    return None


def _resolved(sim: Simulator, truth) -> bool:
    """Is the cause gone from reality now? Read from hidden state, never from evidence."""
    # Variables:
    #   truth: One real fault from the ground-truth record.
    #   state: The factory's true state; this reads hidden state, never evidence.
    #   machine: The machine the fault was on.
    #   replaced: The tick the faulty part was replaced or repaired, if ever. A
    #     servo drive or hydraulic leak never clears by itself, so only its repair
    #     after the fault began counts.
    state = sim.state
    if truth.fault == "bad_material_batch":
        return state.batch is not None and state.batch.id > truth.batch_id
    machine = state.machines[truth.machine_id]
    repaired_at = {
        "bearing_degradation": machine.bearing_replaced_tick,
        "servo_drive_wear": machine.axis_replaced_tick,
        "hydraulic_leak": machine.hydraulics_repaired_tick,
    }
    if truth.fault in repaired_at:
        replaced = repaired_at[truth.fault]
        return replaced is not None and replaced >= truth.start_tick
    if truth.fault == "wrong_setting":
        return machine.speed_setting is None
    if truth.fault == "false_alarm":
        return machine.condition.vibration_sensor_offset == 0.0  # over by itself
    raise ValueError(f"no resolved check for fault {truth.fault!r}")


def summarize(scores: list[Score]) -> dict:
    """Totals over many runs, e.g. "18/20 root causes correctly identified".

    Runs interrupted by an unanswered required model question are counted in `runs` and
    `model_unavailable` but left out of every other total: they measure the
    model services' uptime, not the agent's reasoning.
    """
    # Variables:
    #   scores: One row per run.
    #   reasoned: Runs where a model answered; runs cut off by an outage measure uptime,
    #     not reasoning, and are left out.
    #   n: How many runs are counted in the totals.
    #   compound: The counted runs that had several true faults.
    #   available: Relevant evidence items that existed across the counted runs.
    #   collected: How many of those the agent looked at.
    if not scores:
        return {"runs": 0}
    reasoned = [s for s in scores if not s.model_unavailable]
    n = len(reasoned)

    def count(field: str) -> int:
        return sum(bool(getattr(s, field)) for s in reasoned)

    def mean(values: list[float]) -> float:
        return sum(values) / n if n else 0.0

    compound = [s for s in reasoned if s.true_fault == COMPOUND]
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
        # Runs where the agent asked for a fix the fault did not need.
        "unnecessary_interventions": sum(bool(s.unnecessary_actions) for s in reasoned),
        # Runs with several true faults: partial credit per cause, and how
        # many were fully right (`fault_correct` above counts those too).
        "compound_runs": len(compound),
        "compound_fully_right": sum(s.fully_right is True for s in compound),
        "compound_causes": sum(len(s.causes) for s in compound),
        "compound_causes_found": sum(s.causes_found or 0 for s in compound),
        "compound_causes_resolved": sum(s.causes_resolved for s in compound),
    }


def format_summary(summary: dict) -> str:
    if summary["runs"] == 0:
        return "no runs"
    n = summary["scored"]
    judged = summary["judged"]
    unjudged = f" ({n - judged} not judged)" if judged < n else ""
    down = summary["model_unavailable"]
    tail = (
        f"; {down} run(s) left out: a required model question was unanswered"
        if down
        else ""
    )
    several = summary.get("compound_runs", 0)
    if several:
        causes = summary["compound_causes"]
        tail = (
            f"; runs with several faults: {summary['compound_fully_right']}/"
            f"{several} fully right, {summary['compound_causes_found']}/{causes} "
            f"causes found, {summary['compound_causes_resolved']}/{causes} "
            f"causes resolved{tail}"
        )
    return (
        f"{summary['fault_correct']}/{judged} root causes correctly identified"
        f"{unjudged}; "
        f"{summary['target_correct']}/{judged} right machine or batch; "
        f"{summary['recommendation_correct']}/{n} right recommendations; "
        f"{summary['unnecessary_interventions']}/{n} unnecessary interventions "
        "asked for; "
        f"{summary['action_correct']}/{n} appropriate interventions; "
        f"{summary['resolved']}/{n} resolved; "
        f"{summary['relevant_evidence_share']:.0%} of relevant evidence collected; "
        f"wrong diagnoses: {summary['evidence_misses']} missed evidence, "
        f"{summary['reasoning_misses']} misread it; "
        f"average {summary['mean_tool_calls']:.1f} tool calls, "
        f"{summary['mean_iterations']:.1f} iterations and "
        f"{summary['mean_ticks']:.0f} ticks{tail}"
    )
