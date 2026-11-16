"""Safe, typed audit events for deterministic triage.

These events explain which evidence checks ran without carrying tool payloads,
machine messages, secrets, or model-written prose. They are retained in state
regardless of whether optional operational JSON logging is enabled.
"""

from __future__ import annotations

import re
from math import isfinite
from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator

from capstone.contracts import Contract

if TYPE_CHECKING:
    from capstone.agent.loop import InvestigationDeps
    from capstone.agent.state import InvestigationState

TriageEventName = Literal[
    "triage.read_selected",
    "triage.evidence_accepted",
    "triage.evidence_rejected",
    "triage.read_failed",
    "triage.requirement_evaluated",
    "triage.stopped",
]
_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class TriageTraceEvent(Contract):
    """An ordered, structured result of a deterministic operation."""

    sequence: int = Field(ge=1)
    event: TriageEventName
    phase: Literal["investigate", "test"]
    reason_code: str
    status: str | None = None
    tool: str | None = None
    requirement_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    source_cutoff_tick: int | None = Field(default=None, ge=0)
    duration_ms: float | None = Field(default=None, ge=0)

    @field_validator("reason_code", "status")
    @classmethod
    def validated_code(cls, value: str | None) -> str | None:
        if value is not None and not _CODE.fullmatch(value):
            raise ValueError("trace status and reason must be fixed machine-readable codes")
        return value

    @field_validator("duration_ms")
    @classmethod
    def finite_duration(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("duration must be finite")
        return value


def emit_triage_event(
    state: InvestigationState,
    deps: InvestigationDeps,
    *,
    event: TriageEventName,
    phase: Literal["investigate", "test"],
    reason_code: str,
    status: str | None = None,
    tool: str | None = None,
    requirement_ids: tuple[str, ...] = (),
    evidence_ids: tuple[str, ...] = (),
    duration_ms: float | None = None,
) -> None:
    """Persist audit first; optional logging cannot change controller behavior."""
    # Variables:
    #   trace: A validated, ordered event containing metadata only.
    #   logger: Opt-in operational stream; never receives source payloads.
    #   trace.sequence: Monotonic investigation-local event sequence.
    trace = TriageTraceEvent(
        sequence=len(state.triage_trace_events) + 1,
        event=event,
        phase=phase,
        reason_code=reason_code,
        status=status,
        tool=tool,
        requirement_ids=requirement_ids,
        evidence_ids=evidence_ids,
        source_cutoff_tick=state.triage_observation_cutoff_tick,
        duration_ms=duration_ms,
    )
    state.triage_trace_events.append(trace)
    logger = deps.event_logger
    if logger is None:
        return
    try:
        logger.log_event(
            event,
            run_id=str(state.run_id),
            investigation_id=str(state.investigation_id),
            sequence=trace.sequence,
            phase=phase,
            tool=tool,
            reason_code=reason_code,
            status=status,
            evidence_id=evidence_ids[0] if evidence_ids else None,
            cutoff_tick=trace.source_cutoff_tick,
            duration_ms=duration_ms,
            counts={"requirements": len(requirement_ids)},
        )
    except (ValueError, TypeError, OSError):
        # Logging is never a prerequisite for a safety decision.
        state.triage_logging_failures += 1
