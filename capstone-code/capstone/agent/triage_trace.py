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
    "triage.started",
    "observe.read_validated",
    "requirements.compiled",
    "decide.selected",
    "tool.completed",
    "evidence.validated",
    "question.evaluated",
    "conclusion.checked",
    "triage.read_selected",
    "triage.evidence_accepted",
    "triage.evidence_rejected",
    "triage.read_failed",
    "triage.requirement_evaluated",
    "triage.stopped",
]
_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_HASH = re.compile(r"[a-f0-9]{20}\Z")

# Fixed classifications: never export free-form provider or model explanations.
_REQUIREMENT_REASONS = {
    "current settings snapshot does not establish a historical change": (
        "historical_setting_unproven"
    ),
    "empty record response cannot establish complete history": (
        "record_coverage_unproven"
    ),
    "record answer has no usable structure": "record_structure_missing",
    "failed jobs are missing dated identifiers or a second job": (
        "inspection_job_ids_missing"
    ),
    "failed jobs lack comparable batch identifiers": "inspection_batches_missing",
    "job history does not identify the requested job's machine path": (
        "job_path_missing"
    ),
    "inspections do not link affected machine and time": "inspection_machine_unlinked",
    "no dated inspection results": "inspection_dates_missing",
    "observed samples do not span the alarm and minimum sustain interval": (
        "alarm_coverage_missing"
    ),
    "measurement lacks qualified samples or span": "measurement_coverage_missing",
}


def requirement_reason_code(status: str, reason: str) -> str:
    """Machine-readable requirement diagnostics with no untrusted text."""
    if status == "pending":
        return "not_checked"
    if reason in _REQUIREMENT_REASONS:
        return _REQUIREMENT_REASONS[reason]
    if status == "satisfied":
        return "requirement_satisfied"
    return "requirement_" + status


class TriageTraceEvent(Contract):
    """An ordered, structured result of a deterministic operation."""

    schema_version: Literal["1.0", "1.1"] = "1.1"
    sequence: int = Field(ge=1)
    event: TriageEventName
    phase: Literal["observe", "investigate", "test", "conclude"]
    reason_code: str
    status: str | None = None
    tool: str | None = None
    requirement_ids: tuple[str, ...] = ()
    question_ids: tuple[str, ...] = ()
    request_hash: str | None = None
    config_fingerprint: str | None = None
    attempt: int | None = Field(default=None, ge=1)
    iteration: int | None = Field(default=None, ge=0)
    candidate_count: int | None = Field(default=None, ge=0)
    remaining_tool_calls: int | None = Field(default=None, ge=0)
    evidence_ids: tuple[str, ...] = ()
    source_cutoff_tick: int | None = Field(default=None, ge=0)
    duration_ms: float | None = Field(default=None, ge=0)

    @field_validator("reason_code", "status")
    @classmethod
    def validated_code(cls, value: str | None) -> str | None:
        if value is not None and not _CODE.fullmatch(value):
            raise ValueError(
                "trace status and reason must be fixed machine-readable codes"
            )
        return value

    @field_validator("request_hash", "config_fingerprint")
    @classmethod
    def validated_hash(cls, value: str | None) -> str | None:
        if value is not None and not _HASH.fullmatch(value):
            raise ValueError("only truncated SHA-256 hex fingerprints are allowed")
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
    phase: Literal["observe", "investigate", "test", "conclude"],
    reason_code: str,
    status: str | None = None,
    tool: str | None = None,
    requirement_ids: tuple[str, ...] = (),
    question_ids: tuple[str, ...] = (),
    request_hash: str | None = None,
    config_fingerprint: str | None = None,
    attempt: int | None = None,
    iteration: int | None = None,
    candidate_count: int | None = None,
    remaining_tool_calls: int | None = None,
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
        question_ids=question_ids,
        request_hash=request_hash,
        config_fingerprint=config_fingerprint,
        attempt=attempt,
        iteration=iteration,
        candidate_count=candidate_count,
        remaining_tool_calls=remaining_tool_calls,
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
            request_hash=trace.request_hash,
            config_fingerprint=trace.config_fingerprint,
            attempt=trace.attempt,
            iteration=trace.iteration,
            candidate_count=trace.candidate_count,
            remaining_tool_calls=trace.remaining_tool_calls,
            phase=phase,
            tool=tool,
            reason_code=reason_code,
            status=status,
            evidence_id=evidence_ids[0] if evidence_ids else None,
            cutoff_tick=trace.source_cutoff_tick,
            duration_ms=duration_ms,
            counts={
                "requirements": len(requirement_ids),
                "questions": len(question_ids),
            },
        )
    except Exception:
        # Third-party logger failures must never change a safety decision.
        # The diagnostic state survives even if transport/serialization fails.
        state.triage_logging_failures += 1
