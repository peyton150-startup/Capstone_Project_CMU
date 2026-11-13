# The triage Investigate stage's request compiler (Block 4, TRIAGE_INVESTIGATE).
# Responsibility: turn open questions into allowed reads and rank them; never pick a cause.
"""Compile and rank the reads a triage could make next, without a model.

Used only in a triage, with TRIAGE_INVESTIGATE set to "advisory" or "on". A
deep run never reaches it.

- `compile_requests`: one candidate `get_sensor_summary` read per open
  question that names exactly one sensor and at least one known machine (or
  has a measured predicate, which names both). Machines come from the
  evidence packet's roster, or the alarmed machine when there is no roster.
  The window runs from WINDOW_TICKS before the alarm to the latest observed
  tick. A read already observed over a window that covers this one is never
  offered again (the duplicate guard), and nothing is offered once the
  research calls are spent.
- `rank`: orders candidates by what the read could settle, with no invented
  probabilities: how many live rivals the question separates, whether it
  could tell against the current favourite, how direct its signal is, how
  often that sensor was already read, and its cost. Ties break on the
  question's order and the machine id, so the order is always the same.
- `escape_reason`: why the model must decide instead. No live explanation,
  or no open question that names a single sensor on a known machine: that is
  ambiguous or unknown causality, which stays the model's call.
- `model_target` and `agreement`: how the model's own choice compares, for
  the advisory record.

A summary is always one row, so a read never returns more rows than a
prompt can hold. Nothing here reads hidden truth or calls a model.
"""

import re

from capstone.agent.policy import CallTool, CallTools, Decision, Stop
from capstone.agent.state import InvestigationState, Question
from capstone.contracts import Contract
from capstone.contracts.tools import ToolRequest

# How far before the alarm a compiled window starts, as the packet's window.
WINDOW_TICKS = 60
# The one tool the compiler asks with: a single-row summary of one sensor.
SUMMARY_TOOL = "get_sensor_summary"
# Reads that measure one machine sensor over a window, for the duplicate guard.
WINDOW_TOOLS = frozenset({"get_readings", "get_sensor_summary", "get_sensor_trend"})
# Sensors the compiler never names: not every machine has one, so a request
# could be refused; the model decides those.
UNSURE_SENSORS = frozenset({"hydraulic_pressure"})
TRUST = {"direct": 2, "indirect": 1, "unknown": 0}


class Candidate(Contract):
    """One read the compiler could make, and the signals that rank it."""

    question_id: str
    hypothesis_id: str | None = None
    machine_id: str
    sensor: str
    from_tick: int
    to_tick: int
    # Larger is better for the first three; smaller is better for the rest.
    rivals_separated: int
    could_contradict_leader: int
    signal_trust: int
    prior_reads: int
    cost: int
    question_order: int

    @property
    def root(self) -> str:
        return f"{self.machine_id}:{self.sensor}"

    def key(self) -> tuple:
        """The ranking key: most to settle first, then cheapest, then stable."""
        # Variables:
        #   rivals_separated, could_contradict_leader, signal_trust: Negated, so
        #     the read that could settle most sorts first.
        #   prior_reads, cost: Fewer earlier reads of this sensor, then fewer
        #     calls, win the next ties.
        #   question_order, machine_id: The plan's own order, then the id, so
        #     equal reads always come out in the same order.
        return (
            -self.rivals_separated,
            -self.could_contradict_leader,
            -self.signal_trust,
            self.prior_reads,
            self.cost,
            self.question_order,
            self.machine_id,
        )

    def signals(self) -> dict[str, int]:
        return {
            "rivals_separated": self.rivals_separated,
            "could_contradict_leader": self.could_contradict_leader,
            "signal_trust": self.signal_trust,
            "prior_reads": self.prior_reads,
            "cost": self.cost,
        }

    def step(self) -> CallTool:
        """The read as a CallTool the loop can run, linked to its question."""
        # Variables:
        #   question_id: Ties the read to its question, so the loop marks it
        #     answered (and, with a predicate, judges it) like a model's read.
        return CallTool(
            information_needed=(
                f"compiled for {self.question_id}: {self.sensor} on "
                f"{self.machine_id}, ticks {self.from_tick}-{self.to_tick}"
            ),
            request=ToolRequest(
                name=SUMMARY_TOOL,
                arguments={
                    "machine_id": self.machine_id,
                    "sensor": self.sensor,
                    "from_tick": self.from_tick,
                    "to_tick": self.to_tick,
                },
            ),
            question_id=self.question_id,
            hypothesis_id=self.hypothesis_id,
        )


def known_machines(state: InvestigationState) -> tuple[str, ...]:
    """The machines a request may name: the packet's roster, else the alarmed one."""
    # Variables:
    #   packet: The triage's Observe packet; its roster is the verified line.
    packet = state.triage_packet
    if packet is not None and packet.roster:
        return packet.roster
    return (state.anomaly.machine_id,) if state.anomaly.machine_id else ()


def sensors_named(text: str) -> set[str]:
    """Every sensor a question's words name, by the alarm's own sensor phrases."""
    # Variables:
    #   words: The text lowered, with underscores read as spaces.
    from capstone.agent.incident_context import SENSOR_WORDS

    words = text.lower().replace("_", " ")
    return {sensor for phrase, sensor in SENSOR_WORDS if phrase in words}


def machines_named(text: str, machines: tuple[str, ...]) -> list[str]:
    """Known machines the text names, in roster order; whole ids only."""
    # Variables:
    #   machines: The ids a request may name; one inside a longer id (CNC-021
    #     for CNC-02) does not count.
    return [
        m
        for m in machines
        if re.search(rf"(?<![\w-]){re.escape(m)}(?![\w-])", text, re.IGNORECASE)
    ]


def observed_windows(state: InvestigationState) -> dict[tuple[str, str], list]:
    """Each (machine, sensor) already read, with the windows that were observed."""
    # Variables:
    #   args: The arguments of one answered read of a machine sensor.
    windows: dict[tuple[str, str], list] = {}
    for decision in state.decisions:
        if decision.tool not in WINDOW_TOOLS or decision.outcome != "observed":
            continue
        args = decision.arguments
        machine, sensor = args.get("machine_id"), args.get("sensor")
        start, end = args.get("from_tick"), args.get("to_tick")
        if all(isinstance(v, str) for v in (machine, sensor)) and all(
            type(t) is int for t in (start, end)
        ):
            windows.setdefault((machine, sensor), []).append((start, end))
    return windows


def targets(
    state: InvestigationState, question: Question, machines: tuple[str, ...]
) -> list[tuple[str, str, int, int]]:
    """The (machine, sensor, from, to) reads that answer one question, or none.

    A measured predicate names its own target and window. Otherwise the words
    must name exactly one sensor and at least one known machine.
    """
    # Variables:
    #   predicate: The measured condition a planner attached, when there is one.
    #   start, end: The default window: before the alarm up to the latest tick.
    predicate = getattr(state, "question_predicates", {}).get(question.id)
    if predicate is not None:
        if predicate.machine_id not in machines:
            return []
        return [
            (
                predicate.machine_id,
                predicate.sensor,
                predicate.from_tick,
                predicate.to_tick,
            )
        ]
    if state.last_tick is None:
        return []
    sensors = sensors_named(question.text)
    if len(sensors) != 1:
        return []
    (sensor,) = sensors
    start = max(0, state.anomaly.tick - WINDOW_TICKS)
    end = max(state.last_tick, start)
    return [(m, sensor, start, end) for m in machines_named(question.text, machines)]


def compile_requests(state: InvestigationState) -> list[Candidate]:
    """Every allowed read for the open questions, ranked best first."""
    # Variables:
    #   live: Ids of the explanations still in play.
    #   leader: The current favourite, which a counter-check could tell against.
    #   machines: Machines a request may name.
    #   seen: Windows already observed per machine sensor (the duplicate guard).
    #   offered: Roots already offered, so two questions do not ask for one read.
    if state.remaining_tool_calls <= 0:
        return []
    live = {h.id for h in state.hypotheses}
    leader = state.leading_hypothesis
    machines = known_machines(state)
    seen = observed_windows(state)
    found: list[Candidate] = []
    for order, question in enumerate(state.unanswered_questions):
        named = set(question.distinguishes_hypothesis_ids) & live
        about = named | ({question.hypothesis_id} & live)
        for machine, sensor, start, end in targets(state, question, machines):
            if sensor in UNSURE_SENSORS:
                continue
            windows = seen.get((machine, sensor), [])
            if any(a <= start and end <= b for a, b in windows):
                continue
            found.append(
                Candidate(
                    question_id=question.id,
                    hypothesis_id=question.hypothesis_id,
                    machine_id=machine,
                    sensor=sensor,
                    from_tick=start,
                    to_tick=end,
                    rivals_separated=len(named) if len(named) >= 2 else 0,
                    could_contradict_leader=int(
                        leader is not None and leader.id in about
                    ),
                    signal_trust=TRUST[question.signal_reliability],
                    prior_reads=len(windows),
                    cost=question.estimated_calls,
                    question_order=order,
                )
            )
    found.sort(key=Candidate.key)
    offered: set[tuple[str, int, int]] = set()
    ranked = []
    for candidate in found:
        mark = (candidate.root, candidate.from_tick, candidate.to_tick)
        if mark not in offered:
            offered.add(mark)
            ranked.append(candidate)
    return ranked


def escape_reason(state: InvestigationState, ranked: list[Candidate]) -> str | None:
    """Why the model must decide this turn, or None when a compiled read stands."""
    # Variables:
    #   state.hypotheses: With no live explanation, what to test is the model's
    #     call, not a ranking's.
    #   ranked: The compiled reads; none means no question named one sensor on
    #     a known machine.
    if not state.hypotheses:
        return "no_live_explanation"
    if not state.unanswered_questions:
        return "no_open_question"
    if not ranked:
        return "no_question_names_one_sensor_on_a_known_machine"
    return None


def model_target(decision: Decision | None) -> tuple[str | None, str | None, tuple]:
    """The model's chosen tool, its machine sensor root, and its window."""
    # Variables:
    #   step: The model's single call, or the first of its list.
    if isinstance(decision, CallTools):
        decision = decision.steps[0]
    if not isinstance(decision, CallTool):
        return None, None, ()
    args = decision.request.arguments
    machine, sensor = args.get("machine_id"), args.get("sensor")
    root = f"{machine}:{sensor}" if machine and sensor else None
    return (
        decision.request.name,
        root,
        (args.get("from_tick"), args.get("to_tick")),
    )


def agreement(choice: Candidate, decision: Decision | None) -> str:
    """How the model's decision compares with the compiled read."""
    # Variables:
    #   tool, root, window: What the model asked for.
    if isinstance(decision, Stop):
        return "model_stopped"
    if decision is None:
        return "model_failed"
    tool, root, window = model_target(decision)
    if tool not in WINDOW_TOOLS or root != choice.root:
        return "different"
    if tool == SUMMARY_TOOL and window == (choice.from_tick, choice.to_tick):
        return "same_request"
    return "same_target"
