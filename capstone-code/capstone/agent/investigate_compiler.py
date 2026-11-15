# The triage Investigate stage's request compiler (Block 4, TRIAGE_INVESTIGATE).
# Responsibility: turn open questions into allowed reads and rank them; never pick a cause.
"""Compile and rank the reads a triage could make next, without a model.

Used only in a triage, with TRIAGE_INVESTIGATE set to "advisory" or "on". A
deep run never reaches it.

- `compile_requests`: one candidate `get_sensor_summary` read per open
  question that names exactly one sensor and at least one known machine, or
  that carries a measured predicate. A predicate (the fixed plan's Q1 for an
  alarm, `agent.triage_plan`) gives the machine, sensor and window itself, so
  its words are not parsed, and a fixed-plan question without one compiles
  nothing (its words ask for a screening, events, settings or inspections,
  not the sensor they mention). Otherwise machines come from the evidence
  packet's roster, or the alarmed machine when there is no roster, and the
  window runs from WINDOW_TICKS before the alarm to the latest observed tick.
  A read already observed over a window that covers this one is never
  offered again (the duplicate guard), and nothing is offered once the
  research calls are spent.
- Before any explanation is formed (investigate runs before hypothesize),
  only predicate reads are offered: the plan already chose what they
  measure, so no live explanation is needed to pick them. A read parsed from
  a question's words still waits for an explanation.
- `rank`: orders candidates by what the read could settle, with no invented
  probabilities: how many live rivals the question separates, whether it
  could tell against the current favourite, how direct its signal is, how
  often that sensor was already read, and its cost. Ties break on the
  question's order and the machine id, so the order is always the same.
- `escape_reason`: why the model must decide instead. No live explanation
  and no predicate read, or no open question that names a single sensor on a
  known machine: that is ambiguous or unknown causality, which stays the
  model's call.
- `model_target` and `agreement`: how the model's own choice compares, for
  the advisory record.

A summary is always one row, so a read never returns more rows than a
prompt can hold. Nothing here reads hidden truth or calls a model.
"""

import re
from typing import NamedTuple

from capstone.agent.policy import CallTool, CallTools, Decision, Stop
from capstone.agent.state import InvestigationState, Question
from capstone.agent.triage_plan import PlannedRead, fixed_plan, planned_reads
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
    # The read: a sensor summary unless the fixed plan's table named another
    # tool (events, settings, inspections, service records) for the question.
    tool: str = SUMMARY_TOOL
    # None only for a planned read about the whole line.
    machine_id: str | None
    # A sensor summary's sensor; None for the other tools.
    sensor: str | None = None
    # The window; None for a tool that takes none (settings, service records).
    from_tick: int | None = None
    to_tick: int | None = None
    # Larger is better for the first three; smaller is better for the rest.
    rivals_separated: int
    could_contradict_leader: int
    signal_trust: int
    prior_reads: int
    cost: int
    question_order: int
    # True when a measured predicate gave the target and window, not the words.
    measured: bool = False
    # True when the fixed plan's table named the read (`planned_reads`).
    planned: bool = False

    @property
    def root(self) -> str:
        """What the read is about: machine and sensor, or machine (or line) and tool."""
        if self.tool == SUMMARY_TOOL:
            return f"{self.machine_id}:{self.sensor}"
        return f"{self.machine_id or 'line'}:{self.tool}"

    @property
    def chosen_without_explanation(self) -> bool:
        """Whether the plan, not the words, chose this read, so it needs no live
        explanation to be worth making."""
        return self.measured or self.planned

    def arguments(self) -> dict:
        """The tool's arguments: only those it takes and the candidate has."""
        # Variables:
        #   fields: Every argument the candidate could carry, None for unused.
        fields = {
            "machine_id": self.machine_id,
            "sensor": self.sensor,
            "from_tick": self.from_tick,
            "to_tick": self.to_tick,
        }
        return {k: v for k, v in fields.items() if v is not None}

    def key(self) -> tuple:
        """The ranking key: most to settle first, then cheapest, then stable."""
        # Variables:
        #   rivals_separated, could_contradict_leader, signal_trust: Negated, so
        #     the read that could settle most sorts first.
        #   prior_reads, cost: Fewer earlier reads of this sensor (or tool),
        #     then fewer calls, win the next ties.
        #   question_order, machine_id, tool: The plan's own order, then the
        #     id (a line-wide read sorts as ""), then the tool, so equal reads
        #     always come out in the same order.
        return (
            -self.rivals_separated,
            -self.could_contradict_leader,
            -self.signal_trust,
            self.prior_reads,
            self.cost,
            self.question_order,
            self.machine_id or "",
            self.tool,
        )

    def signals(self) -> dict[str, int]:
        return {
            "rivals_separated": self.rivals_separated,
            "could_contradict_leader": self.could_contradict_leader,
            "signal_trust": self.signal_trust,
            "prior_reads": self.prior_reads,
            "cost": self.cost,
            "measured": int(self.measured),
            "planned": int(self.planned),
        }

    def step(self) -> CallTool:
        """The read as a CallTool the loop can run, linked to its question."""
        # Variables:
        #   question_id: Ties the read to its question, so the loop marks it
        #     answered (and, with a predicate, judges it) like a model's read.
        #   about: The read in words: sensor or tool, machine or line, window.
        about = f"{self.sensor or self.tool} on {self.machine_id or 'the line'}"
        if self.from_tick is not None:
            about += f", ticks {self.from_tick}-{self.to_tick}"
        return CallTool(
            information_needed=f"compiled for {self.question_id}: {about}",
            request=ToolRequest(name=self.tool, arguments=self.arguments()),
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


def from_fixed_plan(state: InvestigationState, question: Question) -> bool:
    """True when the question is one the fixed triage plan wrote, word for word."""
    # Variables:
    #   state.fixed_plan_used: Set when TRIAGE_PLAN=fixed gave the first
    #     questions; otherwise every question came from a model.
    #   question.text: Compared as well as the id, so a model's later question
    #     that reuses an id is still parsed as before.
    if not state.fixed_plan_used:
        return False
    return any(
        q.id == question.id and q.text == question.text
        for q in fixed_plan(state.anomaly)
    )


class Target(NamedTuple):
    """One read that answers a question, before it is ranked."""

    tool: str
    machine_id: str | None
    sensor: str | None
    from_tick: int | None
    to_tick: int | None
    measured: bool = False
    planned: bool = False


def planned_target(
    state: InvestigationState, read: PlannedRead, machines: tuple[str, ...]
) -> list[Target]:
    """The fixed plan's own read for a question, with its window filled in.

    Empty when the read names a machine the request may not name, or when no
    tick is known yet to end a window at.
    """
    # Variables:
    #   read: The table's tool, machine and sensor for the question.
    #   start, end: Before the anomaly up to the latest observed tick, for a
    #     windowed read; None for a tool that takes no window.
    if read.machine_id is not None and read.machine_id not in machines:
        return []
    start = end = None
    if read.windowed:
        if state.last_tick is None:
            return []
        start = max(0, state.anomaly.tick - WINDOW_TICKS)
        end = max(state.last_tick, start)
    return [Target(read.tool, read.machine_id, read.sensor, start, end, planned=True)]


def targets(
    state: InvestigationState, question: Question, machines: tuple[str, ...]
) -> list[Target]:
    """The reads that answer one question.

    A measured predicate names its own target and window, exactly, and its
    reads are marked measured. A fixed-plan question without one compiles the
    read the plan's table names for it (`planned_reads`: events, settings,
    inspections, service records or a follow-up sensor), marked planned, or
    nothing when the table names none: a sensor its words mention is not the
    read that answers it. Otherwise the words must name exactly one sensor and
    at least one known machine. Empty when none of these gives a read.
    """
    # Variables:
    #   predicate: The measured condition a planner attached, when there is one;
    #     its window is used unchanged, so the read is one its verdict accepts.
    #   read: The fixed plan's own read for the question, if the table has one.
    #   start, end: The default window: before the alarm up to the latest tick.
    predicate = state.question_predicates.get(question.id)
    if predicate is not None:
        if predicate.machine_id not in machines:
            return []
        return [
            Target(
                SUMMARY_TOOL,
                predicate.machine_id,
                predicate.sensor,
                predicate.from_tick,
                predicate.to_tick,
                measured=True,
            )
        ]
    if from_fixed_plan(state, question):
        read = planned_reads(state.anomaly).get(question.id)
        return [] if read is None else planned_target(state, read, machines)
    if state.last_tick is None:
        return []
    sensors = sensors_named(question.text)
    if len(sensors) != 1:
        return []
    (sensor,) = sensors
    start = max(0, state.anomaly.tick - WINDOW_TICKS)
    end = max(state.last_tick, start)
    return [
        Target(SUMMARY_TOOL, m, sensor, start, end)
        for m in machines_named(question.text, machines)
    ]


def earlier_reads(state: InvestigationState, target: Target) -> tuple[int, bool]:
    """For a read that is not a sensor read: how often its tool was already
    answered about the same machine (or line), and whether this exact read
    already was (the duplicate guard)."""
    # Variables:
    #   wanted: The target's arguments, as the tool would be asked.
    #   same: Answered calls of the same tool about the same machine (or line).
    wanted = {
        k: v
        for k, v in {
            "machine_id": target.machine_id,
            "from_tick": target.from_tick,
            "to_tick": target.to_tick,
        }.items()
        if v is not None
    }
    same = [
        d
        for d in state.decisions
        if d.tool == target.tool
        and d.outcome == "observed"
        and d.arguments.get("machine_id") == target.machine_id
    ]
    return len(same), any(d.arguments == wanted for d in same)


def compile_requests(state: InvestigationState) -> list[Candidate]:
    """Every allowed read for the open questions, ranked best first."""
    # Variables:
    #   live: Ids of the explanations still in play; with none, only reads the
    #     plan chose (a predicate's or the table's) are kept, since a reading
    #     parsed from words needs an explanation to be worth choosing.
    #   leader: The current favourite, which a counter-check could tell against.
    #   machines: Machines a request may name.
    #   seen: Windows already observed per machine sensor (the duplicate guard
    #     for sensor reads); other tools are guarded by `earlier_reads`.
    #   offered: Reads already offered, so two questions do not ask for one.
    #   target.measured: Whether a predicate gave this read. Only those may
    #     name a sensor in UNSURE_SENSORS (the predicate's alarm came from
    #     that very sensor).
    #   target.planned: Whether the fixed plan's table named this read.
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
        for target in targets(state, question, machines):
            if not (target.measured or target.planned) and not live:
                continue
            if not target.measured and target.sensor in UNSURE_SENSORS:
                continue
            if target.tool in WINDOW_TOOLS:
                windows = seen.get((target.machine_id, target.sensor), [])
                if any(
                    a <= target.from_tick and target.to_tick <= b for a, b in windows
                ):
                    continue
                prior = len(windows)
            else:
                prior, repeat = earlier_reads(state, target)
                if repeat:
                    continue
            found.append(
                Candidate(
                    question_id=question.id,
                    hypothesis_id=question.hypothesis_id,
                    tool=target.tool,
                    machine_id=target.machine_id,
                    sensor=target.sensor,
                    from_tick=target.from_tick,
                    to_tick=target.to_tick,
                    rivals_separated=len(named) if len(named) >= 2 else 0,
                    could_contradict_leader=int(
                        leader is not None and leader.id in about
                    ),
                    signal_trust=TRUST[question.signal_reliability],
                    prior_reads=prior,
                    cost=question.estimated_calls,
                    question_order=order,
                    measured=target.measured,
                    planned=target.planned,
                )
            )
    found.sort(key=Candidate.key)
    offered: set[tuple] = set()
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
    #     call, not a ranking's, unless the plan (a predicate or the fixed
    #     table) already fixed the read.
    #   ranked: The compiled reads; none means no question named one sensor on
    #     a known machine (or, with no explanation, had a read the plan chose).
    if not state.hypotheses and not any(c.chosen_without_explanation for c in ranked):
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


def model_arguments(decision: Decision | None) -> dict:
    """The arguments of the model's single call, or of the first of its list."""
    if isinstance(decision, CallTools):
        decision = decision.steps[0]
    return decision.request.arguments if isinstance(decision, CallTool) else {}


def agreement(choice: Candidate, decision: Decision | None) -> str:
    """How the model's decision compares with the compiled read."""
    # Variables:
    #   tool, root, window: What the model asked for.
    #   choice.tool: A sensor read is compared by machine sensor and window; a
    #     planned record read by tool, machine (or line) and arguments.
    #   args: The arguments of the model's call, for a planned record read.
    if isinstance(decision, Stop):
        return "model_stopped"
    if decision is None:
        return "model_failed"
    tool, root, window = model_target(decision)
    if choice.tool not in WINDOW_TOOLS:
        # A planned record read: the same tool about the same machine (or the
        # whole line) is the same target; with the same window, the same request.
        args = model_arguments(decision)
        if tool != choice.tool or args.get("machine_id") != choice.machine_id:
            return "different"
        return "same_request" if args == choice.arguments() else "same_target"
    if tool not in WINDOW_TOOLS or root != choice.root:
        return "different"
    if tool == SUMMARY_TOOL and window == (choice.from_tick, choice.to_tick):
        return "same_request"
    return "same_target"
