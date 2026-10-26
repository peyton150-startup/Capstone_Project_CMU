# The action tools: waiting, proposing a repair, carrying it out, and the approval desk.
# Responsibility: move time forward and require human approval before any repair.
from pydantic import BaseModel

# The repairs the approval desk knows come from the fault packs (`capstone/faults.py`).
from capstone.faults import ACTIONS
from capstone.simulator.simulator import Simulator
from capstone.tools.errors import ToolInputError


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
    # Approval is permission only. These stay empty until the work is started.
    executed_tick: int | None = None
    finish_tick: int | None = None


class ApprovalDesk:
    """The human's side. Never handed to the agent.

    Nothing the agent proposes touches the factory until someone approves
    it here. Approving is permission, not the work: the factory changes
    only when an approved proposal is carried out.
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
        """Give permission for the proposed action. The factory does not change yet."""
        return self._decide(self._pending(proposal_id), "approved", note)

    def carry_out(self, proposal_id: int) -> dict:
        """Start the work of an approved proposal, once.

        Refuses anything not approved, so reaching this is not a way round
        the human. If the work cannot start, the proposal stays approved
        and not carried out.
        """
        proposal = next((p for p in self._proposals if p.id == proposal_id), None)
        if proposal is None:
            raise ToolInputError(f"no proposal {proposal_id}")
        if proposal.status != "approved":
            raise ToolInputError(
                f"proposal {proposal_id} is {proposal.status}, not approved"
            )
        if proposal.executed_tick is not None:
            raise ToolInputError(f"proposal {proposal_id} was already carried out")
        if proposal.action == "replace_bearing":
            finish = self._sim.start_bearing_replacement(proposal.machine_id)
        elif proposal.action == "replace_servo_drive":
            finish = self._sim.start_servo_drive_replacement(proposal.machine_id)
        elif proposal.action == "repair_hydraulics":
            finish = self._sim.start_hydraulic_repair(proposal.machine_id)
        else:
            finish = self._sim.start_setting_reset(proposal.machine_id)
        proposal.executed_tick, proposal.finish_tick = self._sim.clock.tick, finish
        return {
            "proposal_id": proposal.id,
            "machine_id": proposal.machine_id,
            "action": proposal.action,
            "started_tick": proposal.executed_tick,
            "finish_tick": finish,
        }

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
    The agent can ask for a change to the factory and can start one a
    human has approved. It cannot approve: that is done at the
    ApprovalDesk, which it is never given.
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
            raise ToolInputError(
                f"ticks must be a whole number from 1 to {self.max_wait}"
            )
        for _ in range(ticks):
            self._sim.step()
        clock = self._sim.clock
        return {"tick": clock.tick, "time": clock.now.isoformat()}

    def propose_action(self, machine_id: str, action: str, reason: str) -> dict:
        """Ask for a change to the factory, saying why. Nothing happens until a human approves."""
        if machine_id not in self._sim.state.machines:
            raise ToolInputError(f"unknown machine {machine_id}")
        if action not in ACTIONS:
            raise ToolInputError(
                f"unknown action {action}; choose from {', '.join(ACTIONS)}"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise ToolInputError("a reason is required")
        if (
            action == "repair_hydraulics"
            and not self._sim.state.machines[machine_id].has_hydraulics
        ):
            raise ToolInputError(f"{machine_id} has no hydraulic system")
        return self._desk.submit(machine_id, action, reason.strip()).model_dump()

    def get_proposals(self) -> list[dict]:
        """Every proposal so far, the human's decision, and whether it was carried out."""
        return self._desk.proposals()

    def execute_action(self, proposal_id: int) -> dict:
        """Start the work of a proposal a human has approved. Says when it will finish."""
        if not isinstance(proposal_id, int) or isinstance(proposal_id, bool):
            raise ToolInputError("proposal_id must be a whole number")
        return self._desk.carry_out(proposal_id)
