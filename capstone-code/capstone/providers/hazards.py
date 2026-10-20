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

Faults sit on the tool boundary only. The simulator is never touched: a
`Gap` hides rows from the answer, not from the factory. Which calls are hit
is fixed by the schedule, never random, so a run repeats exactly. The
schedule is built from what monitoring noticed (observable), never from the
hidden truth.
"""

from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import JsonValue

from capstone.contracts.tools import ToolError, ToolRequest, ToolResult
from capstone.providers.factory import FactoryProvider

TIMEOUT_MESSAGE = "The tool timed out. It may answer if asked again."
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


Hazard = Timeout | Gap | StaleRecord


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


class UnreliableProvider:
    """The tools behind it, with the scheduled faults put in."""

    def __init__(self, inner: FactoryProvider, hazards: tuple[Hazard, ...]):
        self._inner = inner
        self._hazards = hazards
        self._counts: Counter[str] = Counter()
        # (tool, call number) of each fired timeout or gap still waiting for a retry.
        self._waiting: list[str] = []
        self.report = HazardReport()

    def call(
        self,
        request: ToolRequest,
        *,
        run_id: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> ToolResult[JsonValue]:
        name = request.name
        self._counts[name] += 1
        nth = self._counts[name]
        context = {"run_id": run_id, "investigation_id": investigation_id}

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
        low, high = int(arguments["from_tick"]), int(arguments["to_tick"])
        third = (high - low + 1) // 3
        return low + third, low + 2 * third

    @staticmethod
    def _with_record(rows: list, stale: StaleRecord) -> list:
        """The rows with the stale record put last among the records from
        before the run, so the history still reads oldest first."""
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
