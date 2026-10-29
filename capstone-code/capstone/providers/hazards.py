# Tools that go wrong on purpose, on a fixed schedule, in front of the factory provider.
# Responsibility: inject recoverable tool faults and keep a list of what fired.
"""Unreliable tools, to test whether the agent recovers.

    provider = UnreliableProvider(factory_provider, standard_hazards(...))

Why it exists: tool-using agents that do well with clean tools often fail
when a tool times out, returns part of an answer, or two sources disagree,
even when a way to recover is open to them (Tian et al., 2026, "Beyond
Function Calling: Benchmarking Tool-Using Agents under Tool-Environment
Unreliability", arXiv 2606.25819, ToolBench-X). An agent that scores well
on clean tools proves little about the real thing. Three of ToolBench-X's
hazards, each with a way out:

- `Timeout`: the nth call to a tool fails as a service fault would.
  Asking again works.
- `Gap`: the nth call to a list tool silently loses the rows in the middle
  third of the requested range, as a sensor feed with a dropout would.
  Asking again, or asking another tool, gives the whole picture.
- `StaleRecord`: the maintenance history carries one record that is wrong,
  saying a machine's bearing was just replaced and ran smoothly. The
  sensors say otherwise when the bearing is in fact worn: the fresh
  readings should win over the record.

One more, for a dropped sensor feed (`blackout_hazards`):

- `Blackout`: the alarmed machine's sensor feed is dead from the start of
  the run until a tick drawn from the seeded stream `hazard.blackout`
  (10 to 50 ticks later). Every sensor call for that machine fails until
  then, however often it is asked; asking again only works once factory
  time has passed (the `wait` tool). The agent is never told when it ends.
  A failed call is not a normal reading: an agent that concludes "nothing
  is wrong" from it has read missing data as evidence.

Faults sit on the tool boundary only. The simulator is never touched: a
`Gap` hides rows from the answer, not from the factory. Which calls are hit
is fixed by the schedule; the blackout's length comes from a seeded stream
of the simulator's own random source, so a run still repeats exactly. The
schedule is built from what monitoring noticed (observable), never from the
hidden truth.
"""

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import JsonValue

from capstone.contracts.tools import ToolError, ToolRequest, ToolResult
from capstone.providers.factory import FactoryProvider

TIMEOUT_MESSAGE = "The tool timed out. It may answer if asked again."
# Says the feed is down, never for how long: the agent is not told when it ends.
BLACKOUT_MESSAGE = "The sensor feed for {machine_id} is not responding."
# The sensor tools a dead feed takes down, for the one machine.
BLACKOUT_TOOLS = ("get_readings", "get_sensor_trend", "get_sensor_summary")
# How long the feed stays down, in ticks from the start of the run; the
# length is drawn from the seeded stream named here. Chosen by the developer
# (2026-10-29): short enough that one small wait clears it.
BLACKOUT_TICKS = (10, 50)
BLACKOUT_STREAM = "hazard.blackout"
# List tools whose rows carry a tick, so part of a range can go missing.
GAP_TOOLS = ("get_readings", "get_factory_readings", "get_events", "get_inspections")


@dataclass(frozen=True)
class Timeout:
    tool: str
    nth: int = 1

    def describe(self) -> str:
        return f"timeout on {self.tool} call {self.nth}"


@dataclass(frozen=True)
class Gap:
    tool: str
    nth: int = 1

    def __post_init__(self):
        if self.tool not in GAP_TOOLS:
            raise ValueError(f"{self.tool} has no ticked rows to leave out")

    def describe(self) -> str:
        return f"gap in {self.tool} call {self.nth}"


@dataclass(frozen=True)
class StaleRecord:
    machine_id: str
    performed_at: str  # ISO time, before the run began
    kind: str = "spindle service"
    note: str = "spindle bearing replaced; test run vibration normal"

    def describe(self) -> str:
        return f"stale maintenance record on {self.machine_id}"


@dataclass(frozen=True)
class Blackout:
    machine_id: str
    # The first tick at which the feed answers again.
    until_tick: int
    tools: tuple[str, ...] = BLACKOUT_TOOLS

    def describe(self) -> str:
        return f"blackout on {self.machine_id} until tick {self.until_tick}"


Hazard = Timeout | Gap | StaleRecord | Blackout
# Which set of faults a run uses: the standard schedule, or a dead sensor feed.
HazardProfile = Literal["standard", "blackout"]


def blackout_hazards(
    machine_id: str | None, start_tick: int, stream: random.Random
) -> tuple[Hazard, ...]:
    """A dead sensor feed on the machine monitoring named, for a seeded number
    of ticks. With no machine named there is no feed to take down."""
    # Variables:
    #   stream: The seeded stream the length is drawn from (`BLACKOUT_STREAM`).
    #   low, high: The shortest and longest blackout, in ticks.
    if machine_id is None:
        return ()
    low, high = BLACKOUT_TICKS
    return (Blackout(machine_id, start_tick + stream.randint(low, high)),)


def standard_hazards(machine_id: str | None, run_start: str) -> tuple[Hazard, ...]:
    """The set used in experiments: one of each kind, on the first calls an
    investigator is likely to make. `machine_id` is the machine monitoring
    named, if any; with none there is no stale record."""
    hazards: list[Hazard] = [
        Timeout("get_readings", 1),
        Timeout("get_sensor_trend", 1),
        Timeout("get_sensor_summary", 1),
        Gap("get_readings", 2),
        Gap("get_events", 1),
        Gap("get_inspections", 1),
    ]
    if machine_id is not None:
        hazards.append(StaleRecord(machine_id, run_start))
    return tuple(hazards)


@dataclass
class HazardReport:
    """What the hazards did to one run, for the experimenter."""

    fired: list[str] = field(default_factory=list)
    # Of the timeouts and gaps that fired, how many the agent followed with
    # a later successful call to the same tool: the recovery ToolBench-X asks for.
    retried: int = 0
    # Sensor calls a blackout refused, and whether the agent read the machine's
    # sensors again after the feed came back. None: there was no blackout.
    blocked: int = 0
    blackout_recovered: bool | None = None


class UnreliableProvider:
    """The tools behind it, with the scheduled faults put in."""

    def __init__(self, inner: FactoryProvider, hazards: tuple[Hazard, ...]):
        # Variables:
        #   inner: The real provider whose answers are spoiled on schedule.
        #   hazards: The scheduled faults.
        #   _counts: How many times each tool has been called, so a fault can hit the
        #     nth call.
        #   _waiting: Tools with a fired fault that the agent has not yet retried
        #     successfully.
        self._inner = inner
        self._hazards = hazards
        self._counts: Counter[str] = Counter()
        # (tool, call number) of each fired timeout or gap still waiting for a retry.
        self._waiting: list[str] = []
        self.report = HazardReport()
        if any(isinstance(hazard, Blackout) for hazard in hazards):
            self.report.blackout_recovered = False

    def call(
        self,
        request: ToolRequest,
        *,
        run_id: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> ToolResult[JsonValue]:
        # Variables:
        #   nth: How many times this tool has now been called.
        #   context: The run and investigation ids, passed through unchanged.
        #   timeout: A scheduled timeout for this call, if any.
        #   gap: A scheduled gap for this call, if any.
        #   low: First tick of the middle third, which is removed.
        #   high: First tick after the middle third.
        #   kept: The rows left after the gap.
        #   asked_for: The machine whose history was requested; None means all machines.
        #   stale: A scheduled wrong record to add to the history.
        name = request.name
        self._counts[name] += 1
        nth = self._counts[name]
        context = {"run_id": run_id, "investigation_id": investigation_id}

        blackout = self._blackout_for(request)
        if blackout is not None:
            clock = self._inner.call(ToolRequest(name="get_time"), **context)
            if clock.tick is not None and clock.tick < blackout.until_tick:
                if blackout.describe() not in self.report.fired:
                    self.report.fired.append(blackout.describe())
                self.report.blocked += 1
                return ToolResult[JsonValue](
                    success=False,
                    tool=name,
                    source=clock.source,
                    tick=clock.tick,
                    timestamp=clock.timestamp,
                    error=ToolError(
                        code="provider_error",
                        message=BLACKOUT_MESSAGE.format(machine_id=blackout.machine_id),
                    ),
                    **context,
                )

        timeout = self._find(Timeout, name, nth)
        if timeout is not None:
            self._fire(timeout)
            clock = self._inner.call(ToolRequest(name="get_time"), **context)
            return ToolResult[JsonValue](
                success=False,
                tool=name,
                source=clock.source,
                tick=clock.tick,
                timestamp=clock.timestamp,
                error=ToolError(code="provider_error", message=TIMEOUT_MESSAGE),
                **context,
            )

        result = self._inner.call(request, **context)
        if not result.success:
            return result
        if blackout is not None and self.report.blocked:
            # The feed is back and the agent asked again after being refused.
            self.report.blackout_recovered = True
        if name in self._waiting:
            self._waiting.remove(name)
            self.report.retried += 1

        gap = self._find(Gap, name, nth)
        if gap is not None and isinstance(result.data, list):
            self._fire(gap)
            low, high = self._middle_third(request.arguments)
            kept = [row for row in result.data if not low <= row["tick"] < high]
            return result.model_copy(update={"data": kept})

        if name == "get_maintenance_history" and isinstance(result.data, list):
            asked_for = request.arguments.get("machine_id")
            for stale in self._hazards:
                if isinstance(stale, StaleRecord) and asked_for in (
                    None,
                    stale.machine_id,
                ):
                    if stale.describe() not in self.report.fired:
                        self.report.fired.append(stale.describe())
                    result = result.model_copy(
                        update={"data": self._with_record(result.data, stale)}
                    )
        return result

    def _blackout_for(self, request: ToolRequest) -> Blackout | None:
        """The blackout covering this sensor call, if any (whether or not it
        has ended yet)."""
        machine_id = request.arguments.get("machine_id")
        for hazard in self._hazards:
            if (
                isinstance(hazard, Blackout)
                and request.name in hazard.tools
                and machine_id == hazard.machine_id
            ):
                return hazard
        return None

    def _find(self, kind, tool: str, nth: int):
        for hazard in self._hazards:
            if isinstance(hazard, kind) and (hazard.tool, hazard.nth) == (tool, nth):
                return hazard
        return None

    def _fire(self, hazard) -> None:
        self.report.fired.append(hazard.describe())
        self._waiting.append(hazard.tool)

    @staticmethod
    def _middle_third(arguments: dict) -> tuple[int, int]:
        # Variables:
        #   third: A third of the requested range, in ticks.
        low, high = int(arguments["from_tick"]), int(arguments["to_tick"])
        third = (high - low + 1) // 3
        return low + third, low + 2 * third

    @staticmethod
    def _with_record(rows: list, stale: StaleRecord) -> list:
        """The rows with the stale record put last among the records from
        before the run, so the history still reads oldest first."""
        # Variables:
        #   record: The wrong maintenance record, in the same shape as a real one.
        #   before: Records from before the run.
        #   during: Records from this run.
        record = {
            "machine_id": stale.machine_id,
            "performed_at": stale.performed_at,
            "tick": None,
            "kind": stale.kind,
            "note": stale.note,
        }
        before = [row for row in rows if row["tick"] is None]
        during = [row for row in rows if row["tick"] is not None]
        return [*before, record, *during]
