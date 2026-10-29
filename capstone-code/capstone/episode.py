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
from capstone.agent.critic import Critic
from capstone.agent.investigation import run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.agent.model_policy import ModelCall
from capstone.agent.monitor import detect_anomaly
from capstone.agent.policy import ReasoningPolicy
from capstone.agent.state import Budgets, InvestigationState
from capstone.contracts.investigations import investigation_id_for, run_id_for
from capstone.evaluation.scoring import Score, evaluate
from capstone.learning import LearningOutcome, learn_from
from capstone.memory.service import MemoryService
from capstone.providers.chat import critic_client
from capstone.providers.factory import SimulatorFactoryProvider, research_tools
from capstone.providers.hazards import (
    BLACKOUT_STREAM,
    HazardProfile,
    HazardReport,
    UnreliableProvider,
    blackout_hazards,
    standard_hazards,
)
from capstone.providers.manual import ManualProvider, ManualSearch
from capstone.providers.recall import RecallingProvider
from capstone.settings import get_settings
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
    # The critic's model questions, tagged agent="critic"; empty without one.
    critic_calls: tuple[ModelCall, ...] = ()

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
    # Variables:
    #   desk: The approval desk, which holds every request and what became of it.
    #   start_tick: The tick the investigation began, to measure how long it took.
    #   diagnosis: What the conclusion was turned into, or None if nobody has judged it.
    #   judged: If False, the diagnosis is left unscored instead of counted as wrong.
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
    # Variables:
    #   kind: standard (one seeded fault) or challenge (several faults at once).
    #   fault: Forces which fault appears; the challenge chooses its own.
    #   machines: How many machines the line has; None lets the seed choose.
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
    hazards: bool | HazardProfile = False,
    manual: ManualSearch | None = None,
    watch: Callable[[InvestigationState], None] | None = None,
    critic: Critic | None = None,
) -> EpisodeResult:
    """Run one seeded episode from the fault's start to its score.

    With `memory`, the agent may recall past lessons and, with `log` as well,
    the finished investigation is audited and offered to the memory gate.
    With `hazards`, the agent's tools fail on the standard schedule
    (`capstone.providers.hazards`), built from what monitoring noticed;
    `hazards="blackout"` instead takes the alarmed machine's sensor feed
    down for a seeded 10-50 ticks.
    With `manual`, the agent may search the machine manual
    (`capstone.providers.manual`); its answers are general guidance,
    labelled as such, never a look at the factory.
    `kind` picks the factory (`build_world`); monitoring, the agent's view
    and scoring are the same for every kind.
    With `watch`, someone follows the run as it happens (`capstone.progress`):
    it is shown copies of the agent's working state, never the simulator.
    With `critic`, or with CRITIC=on in settings, a second model reviews the
    two leading hypotheses before the conclusion (review only: it changes
    nothing in the run). It is built from settings before the factory, so a
    missing CRITIC_MODEL fails before the case runs.
    """
    # Variables:
    #   seed: Decides the whole factory, so the same seed repeats the same run.
    #   policy: The decision-maker that reasons about the anomaly.
    #   approver: Stands in for the human who approves or rejects a request.
    #   judge: Turns the agent's conclusion words into a named cause for scoring; None
    #     leaves it unjudged.
    #   memory: Lets the agent recall lessons and, with a log, learn from the run.
    #   log: Where the finished investigation is written for audit.
    #   budgets: Limits on calls, turns and time for the investigation.
    #   clock: Seconds that only move forward; replaced in tests.
    #   run_key: A name that fixes the run's ids, so a rerun gets the same ones.
    #   hazards: If True or "standard", tools fail on the standard schedule;
    #     "blackout", the alarmed machine's sensor feed is down for a while.
    #   manual: Lets the agent search the machine manual.
    #   watch: Called with a copy of the agent's state so someone can follow the run.
    #   critic: Reviews the two leading hypotheses; None builds one from settings
    #     when CRITIC is on, and otherwise runs without one.
    #   settings: The project settings, read for the action bar and step mode.
    #   sim: The factory with its hidden fault; never given to the agent.
    #   desk: The human's approval desk; never given to the agent.
    #   look: The read-only tools.
    #   act: The tools that act, such as wait.
    #   anomaly: What ordinary monitoring noticed first; the agent starts from this.
    #   start_tick: The tick the investigation began.
    #   provider: What the agent calls; layers are added for hazards, memory and the
    #     manual.
    #   unreliable: The provider with scheduled faults, kept to read its report
    #     afterwards.
    #   before_run: A time a day before the run began, used for the stale record.
    #   world: A short label for the kind of factory, part of the run's name.
    #   run_id: The run's identity, derived from its name.
    #   state: The agent's working memory for this investigation.
    #   deps: Everything the loop needs from outside.
    #   learning: What the memory gate decided; None if memory was not used.
    #   diagnosis: The cause the judge read from the conclusion, if a judge was given.
    #   judged: Whether a judge was given.
    settings = get_settings()
    if critic is None and settings.critic:
        critic = Critic(
            critic_client(settings), getattr(policy, "tools", research_tools())
        )
    sim = build_world(seed, kind=kind, fault=fault, machines=machines)
    desk = ApprovalDesk(sim)
    look, act = ObservationTools(sim), ActionTools(sim, desk)
    anomaly = detect_anomaly(look, act)
    start_tick = sim.clock.tick

    def human_review(proposal) -> None:
        # Variables:
        #   approved: Whether the stand-in human said yes.
        #   note: The reason the human gave.
        approved, note = approver(proposal)
        (desk.approve if approved else desk.reject)(proposal.proposal_id, note)

    provider = SimulatorFactoryProvider(look, act)
    unreliable = None
    if hazards == "blackout":
        unreliable = UnreliableProvider(
            provider,
            blackout_hazards(
                anomaly.machine_id, start_tick, sim.rng.stream(BLACKOUT_STREAM)
            ),
        )
        provider = unreliable
    elif hazards:
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
        state_action_bar=settings.state_action_bar,
        step_questions=settings.step_questions,
    )
    if memory is not None:
        provider = RecallingProvider(provider, memory)
    if manual is not None:
        provider = ManualProvider(provider, manual)
    deps = InvestigationDeps(
        provider=provider,
        policy=policy,
        clock=clock,
        human_review=human_review,
        watch=watch,
        min_action_confidence=settings.min_action_confidence,
        state_action_bar=settings.state_action_bar,
        step_questions=settings.step_questions,
        critic=critic,
        critic_seconds=settings.critic_seconds,
        critic_followup=settings.critic_followup,
        # Only a run that offers the manual can search it.
        manual_step=settings.manual_step and manual is not None,
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
        () if critic is None else tuple(critic.calls),
    )
