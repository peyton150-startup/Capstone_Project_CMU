# One complete run: seeded factory, anomaly, investigation, learning, score.
# Responsibility: hold both sides of the boundary, and keep them apart.
"""The runner that chains every stage of one episode.

    sim      = build_world(seed, kind=..., fault=...) # reality, with hidden faults
    anomaly  = detect_anomaly(look, act)              # what monitoring noticed
    state    = run_investigation(state, deps)         # the agent, through tools only
    learning = learn_from(state, policy, memory, log) # audit, then the memory gate
    score    = evaluate(sim, diagnosis, ...)          # against the hidden truth

This is the only module that holds the simulator and the agent at once. It
gives the agent a provider over the observation and action tools, keeps the
approval desk for the human, and hands the finished run to evaluation. The
agent gets nothing else from here: not the simulator, not the desk, not the
score. Like `learning`, it lives outside `capstone.agent`, which may not
import memory.

The agent concludes in words. Root cause and target are scored only when a
`judge` turns those words into a `Diagnosis` (a hand label, or later an
evaluator model that is not the investigator); otherwise they are left
unjudged. `rescore` applies a label afterwards, without running again.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic

from capstone.agent.completion import AuditLog
from capstone.agent.investigation import run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.agent.monitor import detect_anomaly
from capstone.agent.policy import ReasoningPolicy
from capstone.agent.state import Budgets, InvestigationState
from capstone.contracts.investigations import investigation_id_for, run_id_for
from capstone.evaluation.scoring import Score, evaluate
from capstone.learning import LearningOutcome, learn_from
from capstone.memory.service import MemoryService
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.providers.hazards import (
    HazardReport,
    UnreliableProvider,
    standard_hazards,
)
from capstone.providers.recall import RecallingProvider
from capstone.simulator.challenge import build_challenge
from capstone.simulator.generator import build_scenario
from capstone.simulator.simulator import Simulator
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.diagnosis import Diagnosis
from capstone.tools.observation import ObservationTools

# What kind of factory an episode is run on. "standard": the line with one
# seeded fault (simulator/generator.py). "challenge": the compound challenge
# (simulator/challenge.py): a worn bearing and a wrong speed setting on one
# machine, a harmless vibration spike on a second, a drifting and briefly
# silent temperature sensor on a third.
STANDARD, CHALLENGE = "standard", "challenge"
SCENARIO_KINDS = (STANDARD, CHALLENGE)

# The human: shown one submitted proposal, answers (approve?, note).
Approver = Callable[[object], tuple[bool, str]]
# Reads the agent's conclusion text and names the cause it gave, if any.
Judge = Callable[[str], Diagnosis | None]


def approve_all(proposal) -> tuple[bool, str]:
    """A trusting human, for experiments: the score then shows whether the
    agent asked for the right thing."""
    return True, "approved"


def reject_all(proposal) -> tuple[bool, str]:
    """A human who leaves the factory alone."""
    return False, "rejected"


def ask_on_console(proposal) -> tuple[bool, str]:
    print(
        f"\nProposal {proposal.proposal_id}: {proposal.action} on "
        f"{proposal.machine_id}\n  {proposal.reason}"
    )
    yes = input("Approve? [y/N] ").strip().lower().startswith("y")
    return yes, "approved at console" if yes else "rejected at console"


@dataclass
class EpisodeResult:
    """One episode, for the experimenter. Holds the simulator, so it holds the
    hidden truth: it must never be handed to an agent or a memory."""

    seed: int
    state: InvestigationState
    score: Score
    learning: LearningOutcome | None
    sim: Simulator
    desk: ApprovalDesk
    start_tick: int
    # What the scheduled tool faults did; None when the tools were reliable.
    hazards: HazardReport | None = None

    @property
    def conclusion(self) -> str | None:
        """The agent's diagnosis in its own words; None if it reached none."""
        concluded = self.state.conclusion
        return None if concluded is None else concluded.diagnosis


def score_episode(
    sim: Simulator,
    desk: ApprovalDesk,
    state: InvestigationState,
    start_tick: int,
    diagnosis: Diagnosis | None,
    *,
    judged: bool,
) -> Score:
    return evaluate(
        sim,
        diagnosis,
        desk.proposals(),
        tool_calls=state.tool_call_count,
        start_tick=start_tick,
        judged=judged,
        calls=answered_calls(state),
        iterations=state.iteration_count,
        termination_reason=(
            None if state.termination_reason is None else state.termination_reason.value
        ),
    )


def answered_calls(state: InvestigationState) -> list[tuple[str, dict]]:
    """Each tool call that produced evidence, as (tool, arguments)."""
    return [
        (d.tool, d.arguments)
        for d in state.decisions
        if d.tool is not None and d.evidence_ids
    ]


def rescore(result: EpisodeResult, diagnosis: Diagnosis | None) -> Score:
    """Score again with a label read off the conclusion afterwards (None: the
    conclusion names no recognisable cause, which counts as wrong)."""
    return score_episode(
        result.sim,
        result.desk,
        result.state,
        result.start_tick,
        diagnosis,
        judged=True,
    )


def build_world(
    seed: int,
    *,
    kind: str = STANDARD,
    fault: str | None = None,
    machines: int | None = None,
) -> Simulator:
    """The seeded factory an episode runs on, not yet run (clock at 0).

    The challenge composes its own faults, so it takes no `fault`.
    """
    if kind == STANDARD:
        return build_scenario(seed, machines=machines, fault=fault)
    if kind == CHALLENGE:
        if fault is not None:
            raise ValueError("the challenge chooses its own faults; give no fault")
        return build_challenge(seed, machines=machines)
    raise ValueError(f"unknown scenario kind {kind}; choose from {SCENARIO_KINDS}")


def run_episode(
    seed: int,
    policy: ReasoningPolicy,
    *,
    kind: str = STANDARD,
    fault: str | None = None,
    machines: int | None = None,
    approver: Approver = approve_all,
    judge: Judge | None = None,
    memory: MemoryService | None = None,
    log: AuditLog | None = None,
    budgets: Budgets | None = None,
    clock: Callable[[], float] = monotonic,
    run_key: str | None = None,
    hazards: bool = False,
) -> EpisodeResult:
    """Run one seeded episode from the fault's start to its score.

    With `memory`, the agent may recall past lessons and, with `log` as well,
    the finished investigation is audited and offered to the memory gate.
    With `hazards`, the agent's tools fail on the standard schedule
    (`capstone.providers.hazards`), built from what monitoring noticed.
    `kind` picks the factory (`build_world`); monitoring, the agent's view
    and scoring are the same for every kind.
    """
    sim = build_world(seed, kind=kind, fault=fault, machines=machines)
    desk = ApprovalDesk(sim)
    look, act = ObservationTools(sim), ActionTools(sim, desk)
    anomaly = detect_anomaly(look, act)
    start_tick = sim.clock.tick

    def human_review(proposal) -> None:
        approved, note = approver(proposal)
        (desk.approve if approved else desk.reject)(proposal.proposal_id, note)

    provider = SimulatorFactoryProvider(look, act)
    unreliable = None
    if hazards:
        # A day before the run began: older than anything the run itself did.
        before_run = (sim.clock.time_at(0) - timedelta(days=1)).isoformat()
        unreliable = UnreliableProvider(
            provider, standard_hazards(anomaly.machine_id, before_run)
        )
        provider = unreliable
    world = "challenge" if kind == CHALLENGE else f"fault-{fault or 'any'}"
    run_id = run_id_for(run_key or f"episode/seed-{seed}/{world}")
    state = InvestigationState(
        run_id=run_id,
        investigation_id=investigation_id_for(run_id, 1),
        anomaly=anomaly,
        budgets=budgets or Budgets(),
    )
    deps = InvestigationDeps(
        provider=provider if memory is None else RecallingProvider(provider, memory),
        policy=policy,
        clock=clock,
        human_review=human_review,
    )
    run_investigation(state, deps)

    learning = None
    if memory is not None and log is not None:
        learning = learn_from(state, policy, memory, log)

    diagnosis, judged = None, judge is not None
    if judge is not None and state.conclusion is not None:
        diagnosis = judge(state.conclusion.diagnosis)
    score = score_episode(sim, desk, state, start_tick, diagnosis, judged=judged)
    return EpisodeResult(
        seed,
        state,
        score,
        learning,
        sim,
        desk,
        start_tick,
        None if unreliable is None else unreliable.report,
    )
