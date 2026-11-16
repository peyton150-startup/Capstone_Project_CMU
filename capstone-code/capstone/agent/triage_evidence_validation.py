"""Pre-commit qualification of deterministic triage tool results.

The controller cannot promote a provider response to observable evidence until
this check passes. This module is intentionally read-only and model-free:
Pydantic contracts validate the result, not an LLM's interpretation of it.
"""

from __future__ import annotations

import json
from math import isfinite
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from capstone.contracts.observations import (
    ClockObservation,
    EventObservation,
    InspectionObservation,
    LineScreeningObservation,
    MachineObservation,
    MaintenanceObservation,
    SettingObservation,
)

from capstone.contracts import Contract
from capstone.contracts.tools import ToolRequest, ToolResult

EvidenceReason = Literal[
    "accepted",
    "missing_data",
    "invalid_shape",
    "invalid_numeric",
    "invalid_tick",
    "future_tick",
    "out_of_order",
    "outside_window",
    "wrong_source",
    "wrong_provider",
    "unsupported_tool",
    "invalid_summary",
    "provider_error",
    "untrusted_response",
    "malformed_result",
    "repeated_call",
    "unknown_tool",
    "invalid_arguments",
    "invalid_result",
    "validator_error",
]


class EvidenceQualification(Contract):
    """Safe metadata about one attempted read, never the actual values."""

    accepted: bool
    reason_code: EvidenceReason
    observed_tick: int | None = Field(default=None, ge=0)
    evidence_id: str | None = None
    request_hash: str | None = None

    @model_validator(mode="after")
    def consistent_verdict(self):
        """A rejected observation cannot carry the accepted reason, or vice versa."""
        # Variables:
        #   accepted: Whether a result may cross the evidence/provenance boundary.
        #   reason_code: Stable explanation of that same admission decision.
        if self.accepted != (self.reason_code == "accepted"):
            raise ValueError("qualification reason and accepted flag disagree")
        return self


def _bad_number_or_tick(value: object, cutoff: int) -> EvidenceReason | None:
    """Check nested results without converting missing values into zero."""
    # Variables:
    #   value: One nested item of provider data.
    #   cutoff: Immutable as-known source horizon for this triage.
    if type(value) is float and not isfinite(value):
        return "invalid_numeric"
    if isinstance(value, list):
        for item in value:
            reason = _bad_number_or_tick(item, cutoff)
            if reason is not None:
                return reason
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"tick", "first_tick", "last_tick", "from_tick", "to_tick"}:
                if item is not None and (type(item) is not int or item < 0):
                    return "invalid_tick"
                if type(item) is int and item > cutoff:
                    return "future_tick"
            reason = _bad_number_or_tick(item, cutoff)
            if reason is not None:
                return reason
    return None


def validate_triage_result(
    result: ToolResult,
    request: ToolRequest,
    cutoff: int,
    *,
    min_result_tick: int | None = None,
    allowed_sources: tuple[str, ...] | None = None,
) -> EvidenceQualification:
    """Reject malformed or future data before the gather evidence append."""

    # Variables:
    #   data: The provider's untrusted payload.
    #   args: Already-authorized request arguments, not model output.
    #   reason: First stable, safe-to-log validation error code.
    #   checked: Constructs the typed verdict without any source values.
    def checked(reason: EvidenceReason) -> EvidenceQualification:
        return EvidenceQualification(
            accepted=reason == "accepted",
            reason_code=reason,
            observed_tick=result.tick if type(result.tick) is int else None,
        )

    # Only the six fixed-plan read capabilities can cross this boundary.
    # A provider-reported tool name does not authorize a different operation.
    supported = {
        "get_sensor_summary",
        "get_events",
        "get_inspections",
        "get_job_history",
        "get_maintenance_history",
        "get_settings",
    }
    if result.tool != request.name:
        return checked("wrong_source")
    if request.name not in supported or not result.success:
        return checked("unsupported_tool")
    if allowed_sources is not None and result.source not in allowed_sources:
        return checked("wrong_provider")
    if result.tick > cutoff:
        return checked("future_tick")
    if min_result_tick is not None and result.tick < min_result_tick:
        return checked("out_of_order")
    data = result.data
    if data is None:
        return checked("missing_data")
    # Give nonfinite numbers their specific reason before checking whether
    # the whole provider payload can be represented as JSON evidence.
    reason = _bad_number_or_tick(data, cutoff)
    if reason is not None:
        return checked(reason)
    try:
        json.dumps(data, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError, OverflowError):
        return checked("invalid_shape")
    args = request.arguments
    name = request.name
    if name == "get_sensor_summary":
        if not isinstance(data, dict):
            return checked("invalid_shape")
        if data.get("machine_id") != args.get("machine_id") or data.get(
            "sensor"
        ) != args.get("sensor"):
            return checked("wrong_source")
        count = data.get("sample_count")
        if type(count) is not int or count < 0:
            return checked("invalid_summary")
        start, end = data.get("from_tick"), data.get("to_tick")
        if type(start) is not int or type(end) is not int or start > end:
            return checked("invalid_summary")
        if start < args["from_tick"] or end > args["to_tick"]:
            return checked("outside_window")
        first, last = data.get("first_tick"), data.get("last_tick")
        if count > 0:
            if (
                type(first) is not int
                or type(last) is not int
                or not start <= first <= last <= end
            ):
                return checked("invalid_summary")
        elif first is not None or last is not None:
            return checked("invalid_summary")
        if count > 0 and last > result.tick:
            return checked("invalid_tick")
        for key in (
            "mean", "delta", "start_value", "end_value", "minimum",
            "maximum", "rate_of_change",
        ):
            number = data.get(key)
            if number is not None and type(number) not in (int, float):
                return checked("invalid_numeric")
        if count == 0 and any(
            data.get(key) is not None
            for key in ("mean", "start_value", "end_value", "minimum", "maximum")
        ):
            return checked("invalid_summary")
    elif name in {"get_readings", "get_sensor_trend", "get_factory_readings"}:
        if not isinstance(data, list):
            return checked("invalid_shape")
        for row in data:
            if not isinstance(row, dict):
                return checked("invalid_shape")
            tick = row.get("tick", row.get("from_tick"))
            if type(tick) is not int:
                return checked("invalid_tick")
            if not args["from_tick"] <= tick <= args["to_tick"]:
                return checked("outside_window")
            if row.get("to_tick", tick) > args["to_tick"]:
                return checked("outside_window")
            if "machine_id" in row and row["machine_id"] != args.get("machine_id"):
                return checked("wrong_source")
            if "sensor" in row and row["sensor"] != args.get("sensor"):
                return checked("wrong_source")
            if name in {"get_readings", "get_factory_readings"} and (
                type(row.get("value")) not in (int, float)
            ):
                return checked("invalid_numeric")
    elif name in {
        "get_events",
        "get_inspections",
        "get_job_history",
        "get_maintenance_history",
        "get_settings",
    }:
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            return checked("invalid_shape")
        for row in data:
            # Timestamped records must not claim observations beyond the
            # provider envelope, the authorized horizon, or requested window.
            tick = row.get("tick")
            if name != "get_settings":
                if tick is None and name != "get_maintenance_history":
                    return checked("invalid_tick")
                if tick is not None and type(tick) is not int:
                    return checked("invalid_tick")
                if type(tick) is int and tick > result.tick:
                    return checked("invalid_tick")
            if name in {"get_events", "get_inspections"}:
                if not args["from_tick"] <= tick <= args["to_tick"]:
                    return checked("outside_window")
            if name == "get_events":
                machine = args.get("machine_id")
                if machine is not None and row.get("machine_id") != machine:
                    return checked("wrong_source")
            if name == "get_job_history":
                if row.get("job_id") != args.get("job_id"):
                    return checked("wrong_source")
            if name == "get_maintenance_history":
                machine = args.get("machine_id")
                if machine is not None and row.get("machine_id") != machine:
                    return checked("wrong_source")
            if name == "get_inspections" and (
                type(row.get("job_id")) is not int
                or row["job_id"] < 1
                or row.get("result") not in {"passed", "failed"}
            ):
                return checked("invalid_shape")
            if name == "get_settings" and (
                not isinstance(row.get("machine_id"), str)
                or not row["machine_id"]
                or type(row.get("speed_rpm")) not in (int, float)
            ):
                return checked("invalid_shape")
            # Identity/time checks above take precedence; then require the
            # complete observable contract, not merely plausible row keys.
            model = {
                "get_events": EventObservation,
                "get_job_history": EventObservation,
                "get_inspections": InspectionObservation,
                "get_maintenance_history": MaintenanceObservation,
                "get_settings": SettingObservation,
            }[name]
            try:
                model.model_validate(row)
            except ValidationError:
                return checked("invalid_shape")
    return checked("accepted")


def validate_triage_observe_result(
    result: ToolResult,
    request: ToolRequest,
    cutoff: int,
    *,
    min_result_tick: int | None = None,
    allowed_sources: tuple[str, ...] | None = None,
) -> EvidenceQualification:
    """Admit only valid pre-plan clock, screening and roster observations.

    The first clock read establishes the horizon; subsequent Observe reads
    cannot advance or rewind it without explicit replay handling.
    """
    # Variables:
    #   cutoff: Trusted observation horizon, or the first clock's own tick.
    #   min_result_tick: Previously accepted timestamp for monotonic checks.
    #   data: Provider payload; never included in a diagnostic verdict.
    def verdict(reason: EvidenceReason) -> EvidenceQualification:
        return EvidenceQualification(
            accepted=reason == "accepted",
            reason_code=reason,
            observed_tick=result.tick,
        )

    if result.tool != request.name:
        return verdict("wrong_source")
    if allowed_sources is not None and result.source not in allowed_sources:
        return verdict("wrong_provider")
    if not result.success or request.name not in {
        "get_time", "get_line_screening", "list_machines"
    }:
        return verdict("unsupported_tool")
    if result.tick > cutoff:
        return verdict("future_tick")
    if min_result_tick is not None and result.tick < min_result_tick:
        return verdict("out_of_order")
    data = result.data
    if data is None:
        return verdict("missing_data")
    reason = _bad_number_or_tick(data, cutoff)
    if reason is not None:
        return verdict(reason)
    try:
        json.dumps(data, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError, OverflowError):
        return verdict("invalid_shape")
    try:
        if request.name == "get_time":
            if not isinstance(data, dict) or type(data.get("tick")) is not int:
                return verdict("invalid_shape")
            if data["tick"] != result.tick:
                return verdict("invalid_tick")
            ClockObservation.model_validate(data)
        elif request.name == "get_line_screening":
            LineScreeningObservation.model_validate(data)
        else:
            if not isinstance(data, list):
                return verdict("invalid_shape")
            machines = [MachineObservation.model_validate(row) for row in data]
            if len({machine.machine_id for machine in machines}) != len(machines):
                return verdict("invalid_shape")
    except (ValidationError, TypeError, ValueError):
        return verdict("invalid_shape")
    return verdict("accepted")
