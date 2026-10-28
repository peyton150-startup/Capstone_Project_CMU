# An adapter that exposes the allowed factory tools through one call.
# Responsibility: check each request and result, and never expose approval or truth.
"""A concrete adapter over the existing allowlisted observation/action tools."""

from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID

from pydantic import ConfigDict, Field, JsonValue, ValidationError, model_validator

from capstone.contracts import Contract
from capstone.contracts.observations import (
    ClockObservation,
    EventObservation,
    ExecutionObservation,
    InspectionObservation,
    MachineObservation,
    MaintenanceObservation,
    ProposalObservation,
    SensorObservation,
    SensorSummaryObservation,
    SensorTrendObservation,
    SettingObservation,
)
from capstone.contracts.tools import (
    ToolError,
    ToolRequest,
    ToolResult,
    ToolSpec,
    TraceContext,
)
from capstone.tools.actions import ActionTools
from capstone.tools.errors import ToolInputError
from capstone.tools.observation import ObservationTools

if TYPE_CHECKING:
    from capstone.observability import EventLogger


def argument_problems(invalid: ValidationError) -> str:
    """Which arguments were wrong and why, without repeating what was sent."""
    return "; ".join(
        f"{'.'.join(str(part) for part in problem['loc']) or 'arguments'}: "
        f"{problem['msg']}"
        for problem in invalid.errors(include_url=False, include_input=False)
    )


# The most rows one answer may hold. Raw readings over a few hundred ticks
# run to tens of kilobytes, which no prompt built from the evidence can
# carry; a longer answer is refused with a way to ask for less.
MAX_ROWS = 300


def run_tool(entry, raw_arguments: dict[str, JsonValue]):
    """Check the request, run the tool, check its answer: (data, error).

    Each failure says only what is safe to say: which arguments were wrong
    and why; a tool's own refusal (`ToolInputError`) as the tool wrote it;
    an answer longer than `MAX_ROWS`, with how to ask for less; any other
    failure, or an answer outside its contract, without detail.
    """
    # Variables:
    #   entry: How one tool is wired: its argument model, its output model, the
    #     function, and whether it returns a list.
    #   raw_arguments: The arguments the caller sent, before they are checked.
    #   arguments: The arguments after checking against the tool's model.
    #   raw: The tool's own answer, before it is rebuilt from the contract.
    #   checked: The answer rebuilt field by field from the output model, so nothing
    #     outside the contract gets out.
    argument_model, output_model, execute, many = entry
    try:
        arguments = argument_model.model_validate(raw_arguments)
    except ValidationError as invalid:
        return None, ToolError(
            code="invalid_arguments", message=argument_problems(invalid)
        )
    try:
        raw = execute(**arguments.model_dump())
    except ToolInputError as refused:
        return None, ToolError(code="invalid_arguments", message=str(refused))
    except Exception:
        # Raw driver/provider errors may contain secrets; never return them.
        return None, ToolError(code="provider_error", message="Tool execution failed.")
    if many and isinstance(raw, list) and len(raw) > MAX_ROWS:
        return None, ToolError(
            code="invalid_arguments",
            message=(
                f"{len(raw)} rows is more than {MAX_ROWS}; narrow the tick range, "
                "or use get_sensor_trend or get_sensor_summary"
            ),
        )
    try:
        checked = [
            output_model.model_validate(row).model_dump(mode="json", exclude_unset=True)
            for row in (raw if many else [raw])
        ]
    except (ValueError, TypeError):
        # Never pass this error on: it names what the contract refused to let out.
        return None, ToolError(
            code="invalid_result", message="The tool's answer was invalid."
        )
    return (checked if many else checked[0]), None


class FactoryProvider(Protocol):
    """Future adapters implement this same request/result boundary."""

    def call(
        self,
        request: ToolRequest,
        *,
        run_id: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> ToolResult[JsonValue]: ...


class NoArguments(Contract):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class TickRange(NoArguments):
    from_tick: int = Field(ge=0)
    to_tick: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered_range(self):
        if self.from_tick > self.to_tick:
            raise ValueError("from_tick must not be after to_tick")
        return self


# The sensors a request may name. Any other name is refused with this list,
# instead of quietly returning no readings.
MachineSensor = Literal[
    "vibration", "temperature", "load", "power", "following_error", "hydraulic_pressure"
]
FactorySensor = Literal["air_temperature"]


class ReadingsArguments(TickRange):
    machine_id: str
    sensor: MachineSensor


class TrendArguments(ReadingsArguments):
    bucket_ticks: int = Field(default=60, ge=1)


class FactoryReadingsArguments(TickRange):
    sensor: FactorySensor


class SensorSummaryArguments(TickRange):
    machine_id: str | None
    sensor: Literal[MachineSensor, FactorySensor]

    @model_validator(mode="after")
    def sensor_belongs_to_target(self):
        if (self.sensor == "air_temperature") != (self.machine_id is None):
            raise ValueError(
                "air_temperature belongs to the factory (machine_id null); "
                "vibration, temperature, load, power, following_error and "
                "hydraulic_pressure need a machine_id"
            )
        return self


class EventsArguments(TickRange):
    machine_id: str | None = None


class MaintenanceArguments(NoArguments):
    machine_id: str | None = None


class JobArguments(NoArguments):
    job_id: int = Field(ge=1)


class WaitArguments(NoArguments):
    ticks: int = Field(ge=1)


class ProposalArguments(NoArguments):
    machine_id: str
    action: str
    reason: str


class ExecuteArguments(NoArguments):
    proposal_id: int = Field(ge=1)


# What each tool does, in words a model can read. The model policy shows
# these with each tool's argument schema. They name no possible causes and
# no fault signatures.
TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_time": "The current tick and clock time.",
    "list_machines": (
        "Every machine on the line in order, its status (running / idle / down), "
        "current job, and whether it has a hydraulic system."
    ),
    "get_settings": (
        "Each machine's current spindle speed in rpm. Standard speeds differ by "
        "machine and are not shown."
    ),
    "get_readings": (
        "Raw readings from one machine sensor (vibration mm/s, temperature °F, "
        "load %, power: electrical demand in kW, or following_error: how far "
        "the axis lags its commanded position, in µm; or hydraulic_pressure in "
        "bar, only on machines with hydraulics) "
        "in a tick range. One tick is one minute. At most 300 rows; for longer "
        "ranges use get_sensor_trend."
    ),
    "get_sensor_trend": (
        "One machine sensor (vibration, temperature, load, power, following_error "
        "or hydraulic_pressure) "
        "summarised per block "
        "of ticks: mean, min, max and count for each block (bucket_ticks, default "
        "60). Shows whether a change is gradual or a single jump, at a fraction of "
        "the size of get_readings. Idle readings are included, which pulls a "
        "block's mean down while a machine waits."
    ),
    "get_factory_readings": (
        "The factory air thermometer (sensor 'air_temperature', °F) in a tick range."
    ),
    "get_sensor_summary": (
        "Count, mean, minimum, maximum, first and last reading of one sensor in a "
        "tick range. Use machine_id null for air_temperature. The rate is the "
        "change from the first to the last reading, not a fitted trend."
    ),
    "get_events": (
        "Event log in a tick range: alarms, machine stops, job "
        "started/finished/blocked, inspections, material batches, loading door, "
        "maintenance. Optionally one machine only."
    ),
    "get_job_history": "Everything the event log says about one job, across machines.",
    "get_maintenance_history": (
        "Service records for one machine or all (machine_id null), oldest first: "
        "visits from the months before the run (a date, tick null) and maintenance "
        "during it (with its tick). What a technician did and wrote, not a cause."
    ),
    "get_inspections": (
        "Pass/fail inspection results (with material batch) for jobs that left "
        "the line in a tick range."
    ),
    "wait": "Let the factory run for some ticks. The only way time passes; looking is free.",
    "propose_action": (
        "Ask a human to approve a change to the factory. replace_bearing stops the "
        "machine about 45 ticks (135 if it has broken down); reset_setting stops it "
        "10 ticks and puts its speed back to standard; replace_servo_drive stops it "
        "60 ticks and fits a new axis servo drive; repair_hydraulics (machines "
        "with hydraulics only) stops it 40 ticks and replaces its seals. "
        "Nothing happens until a "
        "human decides; check with get_proposals. The reason says why, and what "
        "you expect to see afterwards."
    ),
    "get_proposals": "Every proposal so far and whether it was approved or rejected.",
    "execute_action": (
        "Start the work of a proposal a human has approved. Says when it will finish."
    ),
}

# Each tool's arguments, the same models the provider checks requests with.
# A test keeps this in step with the provider's own table.
TOOL_ARGUMENTS: dict[str, type[Contract]] = {
    "get_time": NoArguments,
    "list_machines": NoArguments,
    "get_settings": NoArguments,
    "get_readings": ReadingsArguments,
    "get_sensor_trend": TrendArguments,
    "get_factory_readings": FactoryReadingsArguments,
    "get_sensor_summary": SensorSummaryArguments,
    "get_events": EventsArguments,
    "get_job_history": JobArguments,
    "get_maintenance_history": MaintenanceArguments,
    "get_inspections": TickRange,
    "wait": WaitArguments,
    "propose_action": ProposalArguments,
    "get_proposals": NoArguments,
    "execute_action": ExecuteArguments,
}

# Asking for a change, reading the human's decision and starting the work are
# a fixed procedure the loop runs itself, so a policy is never offered them.
PROCEDURE_TOOLS = ("propose_action", "get_proposals", "execute_action")


def tool_spec(name: str) -> ToolSpec:
    """One provider tool as a model sees it: name, description, argument schema."""
    return ToolSpec(
        name=name,
        description=TOOL_DESCRIPTIONS[name],
        arguments=TOOL_ARGUMENTS[name].model_json_schema(),
    )


def research_tools() -> tuple[ToolSpec, ...]:
    """Every factory tool a policy may choose: all but the fixed procedure."""
    return tuple(
        tool_spec(name) for name in TOOL_DESCRIPTIONS if name not in PROCEDURE_TOOLS
    )


class SimulatorFactoryProvider:
    """No approval or ground-truth tools; old tool APIs remain unchanged."""

    def __init__(
        self,
        observations: ObservationTools,
        actions: ActionTools,
        *,
        logger: "EventLogger | None" = None,
    ):
        # Variables:
        #   observations: The read-only tools.
        #   actions: The tools that act, such as wait and the approval requests.
        #   logger: Optional place to record each call.
        #   _tools: For each tool name: its arguments model, output model, function and
        #     whether it returns a list.
        self._observations = observations
        self._logger = logger
        # Each entry names arguments, output fields, callable, and whether a list.
        self._tools = {
            "get_time": (NoArguments, ClockObservation, observations.get_time, False),
            "list_machines": (
                NoArguments,
                MachineObservation,
                observations.list_machines,
                True,
            ),
            "get_settings": (
                NoArguments,
                SettingObservation,
                observations.get_settings,
                True,
            ),
            "get_readings": (
                ReadingsArguments,
                SensorObservation,
                observations.get_readings,
                True,
            ),
            "get_sensor_trend": (
                TrendArguments,
                SensorTrendObservation,
                observations.get_sensor_trend,
                True,
            ),
            "get_factory_readings": (
                FactoryReadingsArguments,
                SensorObservation,
                observations.get_factory_readings,
                True,
            ),
            "get_sensor_summary": (
                SensorSummaryArguments,
                SensorSummaryObservation,
                observations.get_sensor_summary,
                False,
            ),
            "get_events": (
                EventsArguments,
                EventObservation,
                observations.get_events,
                True,
            ),
            "get_maintenance_history": (
                MaintenanceArguments,
                MaintenanceObservation,
                observations.get_maintenance_history,
                True,
            ),
            "get_job_history": (
                JobArguments,
                EventObservation,
                observations.get_job_history,
                True,
            ),
            "get_inspections": (
                TickRange,
                InspectionObservation,
                observations.get_inspections,
                True,
            ),
            "wait": (WaitArguments, ClockObservation, actions.wait, False),
            "propose_action": (
                ProposalArguments,
                ProposalObservation,
                actions.propose_action,
                False,
            ),
            "get_proposals": (
                NoArguments,
                ProposalObservation,
                actions.get_proposals,
                True,
            ),
            "execute_action": (
                ExecuteArguments,
                ExecutionObservation,
                actions.execute_action,
                False,
            ),
        }

    def call(
        self,
        request: ToolRequest,
        *,
        run_id: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> ToolResult[JsonValue]:
        # Variables:
        #   context: The run and investigation ids, copied onto the result.
        #   error: What went wrong, or None.
        #   data: The checked answer, or None.
        #   entry: The tool's wiring, or None if the tool name is unknown.
        #   clock: The factory's time, read after the call so every result is stamped.
        context = TraceContext(run_id=run_id, investigation_id=investigation_id)
        error, data = None, None
        entry = self._tools.get(request.name)
        if entry is None:
            error = ToolError(code="unknown_tool", message="Tool is not available.")
        else:
            data, error = run_tool(entry, request.arguments)
        clock = ClockObservation.model_validate(self._observations.get_time())
        result = ToolResult[JsonValue](
            success=error is None,
            tool=request.name,
            source="simulator",
            tick=clock.tick,
            timestamp=clock.time,
            run_id=context.run_id,
            investigation_id=context.investigation_id,
            data=data,
            error=error,
        )
        if self._logger is not None:
            self._logger.log_event(
                "factory_tool",
                run_id=str(context.run_id) if context.run_id else None,
                investigation_id=str(context.investigation_id)
                if context.investigation_id
                else None,
                tick=result.tick,
                tool=request.name if entry else "unknown_tool",
                success=result.success,
            )
        return result
