from datetime import datetime, timedelta
from uuid import UUID

from capstone.agent.artifacts import DetectedAnomaly, TerminationReason
from capstone.agent.policy import CallTool, Interpretation, Stop
from capstone.agent.state import Budgets, InvestigationState
from capstone.contracts.tools import ToolError, ToolRequest, ToolResult
from capstone.tools.actions import ActionTools, ApprovalDesk


def approve_and_run(desk: ApprovalDesk, act: ActionTools, proposal_id: int) -> dict:
    """The human says yes, then the approved work is started."""
    desk.approve(proposal_id)
    return act.execute_action(proposal_id)


START = datetime(2026, 1, 5, 6, 0)
RUN, INVESTIGATION = UUID(int=1), UUID(int=2)


class FakeProvider:
    """Answers from a function, so a test decides exactly what the factory says."""

    def __init__(self, respond=None, tick: int = 10):
        self.tick = tick
        self.calls: list[ToolRequest] = []
        self._respond = respond or (lambda request: {"ok": True})

    def call(self, request, *, run_id=None, investigation_id=None):
        self.calls.append(request)
        if request.name == "wait":
            self.tick += request.arguments["ticks"]
        answer = self._respond(request)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, ToolResult) or answer == "not a result":
            return answer
        failed = answer == "error"
        return ToolResult(
            success=not failed,
            tool=request.name,
            source="fake",
            tick=self.tick,
            timestamp=START + timedelta(minutes=self.tick),
            run_id=run_id,
            investigation_id=investigation_id,
            data=None if failed else answer,
            error=ToolError(code="provider_error", message="Tool execution failed.")
            if failed
            else None,
        )


class ScriptedPolicy:
    """Plays back prepared decisions. An entry may be a function of the state."""

    def __init__(
        self,
        decisions=(),
        interpret=None,
        *,
        questions=(),
        hypothesize=None,
        conclude=None,
        judge=None,
        lesson=None,
    ):
        # One list for every phase, or a dict of lists keyed by phase.
        self.decisions = (
            {phase: list(items) for phase, items in decisions.items()}
            if isinstance(decisions, dict)
            else list(decisions)
        )
        self._interpret = interpret
        self._questions = questions
        self._hypothesize = hypothesize
        self._conclude = conclude
        self._judge = judge
        self._lesson = lesson
        self.seen_states: list[InvestigationState] = []
        self.asked: list[str] = []

    def plan(self, state):
        self.asked.append("plan")
        return self._questions(state) if callable(self._questions) else self._questions

    def decide(self, state, phase):
        self.seen_states.append(state)
        queue = (
            self.decisions.get(phase, [])
            if isinstance(self.decisions, dict)
            else self.decisions
        )
        if not queue:
            return Stop(reason=TerminationReason.NO_USEFUL_ACTION)
        item = queue.pop(0)
        return item(state) if callable(item) else item

    def hypothesize(self, state):
        self.asked.append("hypothesize")
        if self._hypothesize is None:
            return Interpretation()
        return self._hypothesize(state)

    def conclude(self, state):
        self.asked.append("conclude")
        if self._conclude is None:
            raise ValueError("no conclusion was scripted")
        return self._conclude(state)

    def judge_verification(self, state):
        self.asked.append("judge")
        if self._judge is None:
            raise ValueError("no judgement was scripted")
        return self._judge(state)

    def write_lesson(self, state):
        self.asked.append("lesson")
        return None if self._lesson is None else self._lesson(state)

    def interpret(self, state, step, evidence):
        if self._interpret is None:
            return Interpretation()
        return self._interpret(state, step, evidence)


def ask(tool="get_events", question_id=None, hypothesis_id=None, **arguments):
    return CallTool(
        information_needed=f"what {tool} shows",
        request=ToolRequest(name=tool, arguments=arguments),
        question_id=question_id,
        hypothesis_id=hypothesis_id,
    )


def new_state(**budgets) -> InvestigationState:
    return InvestigationState(
        run_id=RUN,
        investigation_id=INVESTIGATION,
        anomaly=DetectedAnomaly(
            tick=10, machine_id="CNC-02", kind="alarm", description="High vibration"
        ),
        budgets=Budgets(**budgets),
        last_tick=10,
    )
