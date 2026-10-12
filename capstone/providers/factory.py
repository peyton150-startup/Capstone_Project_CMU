# An adapter that exposes the allowed factory tools through one call.
# Responsibility: check each request and result, and never expose approval or truth.
"""A concrete adapter over the existing allowlisted observation/action tools."""

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from pydantic import ConfigDict, Field, JsonValue, model_validator

from capstone.contracts import Contract
from capstone.contracts.observations import (
    ClockObservation,
    EventObservation,
    InspectionObservation,
    MachineObservation,
    ProposalObservation,
    SensorObservation,
    SensorSummaryObservation,
    SettingObservation,
)
from capstone.contracts.tools import ToolError, ToolRequest, ToolResult, TraceContext
from capstone.tools.actions import ActionTools
from capstone.tools.observation import ObservationTools

if TYPE_CHECKING:
    from capstone.observability import EventLogger


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


class ReadingsArguments(TickRange):
    machine_id: str
    sensor: str


class FactoryReadingsArguments(TickRange):
    sensor: str


class SensorSummaryArguments(TickRange):
    machine_id: str | None
    sensor: str


class EventsArguments(TickRange):
    machine_id: str | None = None


class JobArguments(NoArguments):
    job_id: int = Field(ge=1)


class WaitArguments(NoArguments):
    ticks: int = Field(ge=1)


class ProposalArguments(NoArguments):
    machine_id: str
    action: str
    reason: str


class SimulatorFactoryProvider:
    """No approval or ground-truth tools; old tool APIs remain unchanged."""

    def __init__(
        self,
        observations: ObservationTools,
        actions: ActionTools,
        *,
        logger: "EventLogger | None" = None,
    ):
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
        }

    def call(
        self,
        request: ToolRequest,
        *,
        run_id: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> ToolResult[JsonValue]:
        context = TraceContext(run_id=run_id, investigation_id=investigation_id)
        error, data = None, None
        entry = self._tools.get(request.name)
        if entry is None:
            error = ToolError(code="unknown_tool", message="Tool is not available.")
        else:
            argument_model, output_model, execute, many = entry
            try:
                arguments = argument_model.model_validate(request.arguments)
                raw = execute(**arguments.model_dump())
                if many:
                    data = [
                        output_model.model_validate(row).model_dump(
                            mode="json", exclude_unset=True
                        )
                        for row in raw
                    ]
                else:
                    data = output_model.model_validate(raw).model_dump(
                        mode="json", exclude_unset=True
                    )
            except ValueError:
                error = ToolError(
                    code="invalid_arguments",
                    message="Tool arguments or result are invalid.",
                )
            except Exception:
                # Raw driver/provider errors may contain secrets; never return them.
                error = ToolError(
                    code="provider_error", message="Tool execution failed."
                )
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
