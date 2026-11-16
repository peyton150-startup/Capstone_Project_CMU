"""Pre-commit qualification of deterministic triage tool results.

The controller cannot promote a provider response to observable evidence until
this check passes. This module is intentionally read-only and model-free:
Pydantic contracts validate the result, not an LLM's interpretation of it.
"""

from __future__ import annotations

from math import isfinite
from typing import Literal

from pydantic import Field

from capstone.contracts import Contract
from capstone.contracts.tools import ToolRequest, ToolResult

EvidenceReason = Literal[
    "accepted",
    "missing_data",
    "invalid_shape",
    "invalid_numeric",
    "invalid_tick",
    "future_tick",
    "outside_window",
    "wrong_source",
    "invalid_summary",
    "validator_error",
]


class EvidenceQualification(Contract):
    """Safe metadata about one attempted read, never the actual values."""

    accepted: bool
    reason_code: EvidenceReason
    observed_tick: int | None = Field(default=None, ge=0)
    evidence_id: str | None = None
    request_hash: str | None = None


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
    result: ToolResult, request: ToolRequest, cutoff: int
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

    if result.tick > cutoff:
        return checked("future_tick")
    data = result.data
    if data is None:
        return checked("missing_data")
    reason = _bad_number_or_tick(data, cutoff)
    if reason is not None:
        return checked(reason)
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
        for key in ("mean", "delta", "start_value", "end_value"):
            number = data.get(key)
            if number is not None and type(number) not in (int, float):
                return checked("invalid_numeric")
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
    return checked("accepted")
