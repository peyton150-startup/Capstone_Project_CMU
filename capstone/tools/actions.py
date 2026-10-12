# The action tools: waiting, proposing a repair, and the approval desk.
# Responsibility: move time forward and require human approval before any repair.
from pydantic import BaseModel

from capstone.simulator.simulator import Simulator

ACTIONS = ("replace_bearing", "reset_setting")


class Proposal(BaseModel):
    """A request from the agent to change the factory, and what became of it."""

    id: int
    machine_id: str
    action: str
    reason: str
    proposed_tick: int
    status: str = "pending"  # pending, approved or rejected
    decided_tick: int | None = None
    note: str = ""


class ApprovalDesk:
    """The human's side. Never handed to the agent.

    Nothing the agent proposes touches the factory until someone approves
    it here.
    """

    def __init__(self, simulator: Simulator):
        self._sim = simulator
        self._proposals: list[Proposal] = []

    def submit(self, machine_id: str, action: str, reason: str) -> Proposal:
        proposal = Proposal(
            id=len(self._proposals) + 1,
            machine_id=machine_id,
            action=action,
            reason=reason,
            proposed_tick=self._sim.clock.tick,
        )
        self._proposals.append(proposal)
        return proposal

    def proposals(self) -> list[dict]:
        return [p.model_dump() for p in self._proposals]

    def pending(self) -> list[dict]:
        return [p.model_dump() for p in self._proposals if p.status == "pending"]

    def approve(self, proposal_id: int, note: str = "") -> dict:
        """Carry out the proposed action. If it cannot start, the proposal stays pending."""
        proposal = self._pending(proposal_id)
        if proposal.action == "replace_bearing":
            self._sim.start_bearing_replacement(proposal.machine_id)
        elif proposal.action == "reset_setting":
            self._sim.start_setting_reset(proposal.machine_id)
        return self._decide(proposal, "approved", note)

    def reject(self, proposal_id: int, note: str = "") -> dict:
        return self._decide(self._pending(proposal_id), "rejected", note)

    def _pending(self, proposal_id: int) -> Proposal:
        for proposal in self._proposals:
            if proposal.id == proposal_id:
                if proposal.status != "pending":
                    raise ValueError(
                        f"proposal {proposal_id} was already {proposal.status}"
                    )
                return proposal
        raise ValueError(f"no proposal {proposal_id}")

    def _decide(self, proposal: Proposal, status: str, note: str) -> dict:
        proposal.status, proposal.note, proposal.decided_tick = (
            status,
            note,
            self._sim.clock.tick,
        )
        return proposal.model_dump()


class ActionTools:
    """The agent's tools that are not plain look-ups. Kept apart from the read-only ones.

    Looking is free: only `wait` moves the clock. So what an agent finds
    at a given tick never depends on how many times it looked first.
    The agent can ask for a change to the factory but cannot make one:
    approving is done at the ApprovalDesk, which it is never given.
    """

    def __init__(
        self,
        simulator: Simulator,
        desk: ApprovalDesk | None = None,
        *,
        max_wait: int = 480,
    ):
        self._sim = simulator
        self._desk = desk or ApprovalDesk(simulator)
        self.max_wait = max_wait

    def wait(self, ticks: int) -> dict:
        """Let the factory run for `ticks` ticks, then report the new time."""
        if (
            not isinstance(ticks, int)
            or isinstance(ticks, bool)
            or not 1 <= ticks <= self.max_wait
        ):
            raise ValueError(f"ticks must be a whole number from 1 to {self.max_wait}")
        for _ in range(ticks):
            self._sim.step()
        clock = self._sim.clock
        return {"tick": clock.tick, "time": clock.now.isoformat()}

    def propose_action(self, machine_id: str, action: str, reason: str) -> dict:
        """Ask for a change to the factory, saying why. Nothing happens until a human approves."""
        if machine_id not in self._sim.state.machines:
            raise ValueError(f"unknown machine {machine_id}")
        if action not in ACTIONS:
            raise ValueError(
                f"unknown action {action}; choose from {', '.join(ACTIONS)}"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a reason is required")
        return self._desk.submit(machine_id, action, reason.strip()).model_dump()

    def get_proposals(self) -> list[dict]:
        """Every proposal made so far and whether it was approved or rejected."""
        return self._desk.proposals()
