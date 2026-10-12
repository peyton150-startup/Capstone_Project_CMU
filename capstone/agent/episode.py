"""One complete run: seeded factory, anomaly, investigation, human approval, score.

This is the only place that holds both sides of the boundary at once: it
gives the agent its tools, keeps the approval desk for the human, and
hands the finished run to evaluation.
"""

from dataclasses import dataclass, field
from typing import Callable

from capstone.agent.agent import ResearchAgent
from capstone.agent.models import Model
from capstone.agent.monitor import wait_for_anomaly
from capstone.agent.toolbox import Toolbox
from capstone.evaluation.scoring import Score, evaluate
from capstone.simulator.generator import build_scenario
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools

# The human: shown a pending proposal, returns (approve?, note).
Approver = Callable[[dict], tuple[bool, str]]


def approve_all(proposal: dict) -> tuple[bool, str]:
    """A trusting human, for experiments: the score then shows whether the agent asked for the right thing."""
    return True, "approved"


def ask_on_console(proposal: dict) -> tuple[bool, str]:
    print(
        f"\nProposal {proposal['id']}: {proposal['action']} on {proposal['machine_id']}\n  {proposal['reason']}"
    )
    answer = input("Approve? [y/N] ").strip().lower()
    return answer.startswith("y"), "approved at console" if answer.startswith(
        "y"
    ) else "rejected at console"


@dataclass
class EpisodeResult:
    seed: int
    anomaly: str | None
    score: Score
    hypotheses: list[list[dict]] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    said: list[str] = field(default_factory=list)


def run_episode(
    seed: int,
    model: Model,
    *,
    fault: str | None = None,
    machines: int | None = None,
    approver: Approver = approve_all,
    max_turns: int = 40,
    memory=None,
) -> EpisodeResult:
    sim = build_scenario(seed, machines=machines, fault=fault)
    desk = ApprovalDesk(sim)
    look, act = ObservationTools(sim), ActionTools(sim, desk)

    anomaly = wait_for_anomaly(look, act)
    start_tick = sim.clock.tick
    if anomaly is None:
        anomaly = f"tick {start_tick}: no alarm, but the shift supervisor asks for a routine check of the line"

    def decide_pending() -> None:
        for proposal in desk.pending():
            approved, note = approver(proposal)
            (desk.approve if approved else desk.reject)(proposal["id"], note)

    toolbox = Toolbox(look, act, extra=memory.tools() if memory else None)
    agent = ResearchAgent(
        model, toolbox, max_turns=max_turns, after_tools=decide_pending
    )
    investigation = agent.investigate(anomaly)

    notebook = toolbox.notebook
    score = evaluate(
        sim,
        notebook.diagnosis,
        desk.proposals(),
        tool_calls=toolbox.tool_calls,
        start_tick=start_tick,
    )
    result = EpisodeResult(
        seed, anomaly, score, notebook.history, notebook.calls, investigation.text
    )
    if memory is not None:
        outcome = [
            e["message"]
            for e in look.get_events(start_tick, sim.clock.tick)
            if e["kind"] == "maintenance"
        ]
        memory.record(
            anomaly=anomaly,
            notebook=notebook,
            proposals=desk.proposals(),
            outcome=outcome,
        )
    return result
