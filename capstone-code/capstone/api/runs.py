"""Opt-in, local-only simulator execution with durable status and safe event journal.

The worker calls the existing Pydantic Graph episode and ApprovalDesk. It never
receives, stores or serves simulator hidden truth. Pilot execution is impossible.
Web observers cannot block a watcher: stage snapshots use a bounded queue.
"""

from __future__ import annotations

import hashlib
import json
import queue
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
)

from capstone.agent.triage_hypothesize import CandidateFamily
from capstone.api.deep_progress import (
    SafeDeepCheckpoint,
    SafeDeepSignals,
    checkpoint_from_stage,
    safe_deep_signals,
)
from capstone.settings import Settings, get_settings
from capstone.triage_run_controls import (
    EffectiveTriageRun,
    TriageRunOptions,
    overridden_fields,
    resolve_triage_run,
)

RunState = Literal[
    "queued", "running", "awaiting_review", "completed", "failed", "interrupted"
]


class InvalidRunEnvironment(Exception):
    """This host's run settings or build commit are malformed."""

    # Deliberately neither ValueError nor RuntimeError, so callers that map
    # those to client conflicts (409) cannot mistake a server fault for one.

    MESSAGE = (
        "Run settings on this host are invalid: check CAPSTONE_SOURCE_REVISION,"
        " RENDER_GIT_COMMIT, NF_DEPLOYMENT_SHA and the TRIAGE_* settings"
    )


class StaleRunConfiguration(ValueError):
    """Preview and admission resolved different server settings."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = Field(ge=0, le=1_000_000)
    kind: Literal["standard", "challenge"] = "standard"
    mode: Literal["triage", "deep"] = "triage"
    hazards: bool = False
    tree_of_thought: bool = False
    manual: Literal["none", "keyword", "neon"] = "none"
    # Validated request-specific settings; no environment or credential edits.
    triage_settings: TriageRunOptions | None = None
    # Optional optimistic concurrency token from the visible server preview.
    # Legacy clients may omit it; the UI always includes it.
    configuration_fingerprint: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{20}$"
    )
    _effective_triage: EffectiveTriageRun | None = PrivateAttr(default=None)


def public_run_configuration(
    request: RunRequest,
    settings: Settings,
    *,
    effective: EffectiveTriageRun | None = None,
) -> dict[str, Any]:
    """Pure, allowlisted resolution shared by preview, submit and worker."""
    applied = request.mode == "triage"
    if applied and effective is None:
        effective = resolve_triage_run(settings, request.triage_settings)
    desired = (
        {}
        if request.triage_settings is None
        else request.triage_settings.model_dump(exclude_none=True)
    )
    stages = (
        effective.stage_modes()
        if applied and effective
        else {"deep": "model-backed Graph", "triage": "not run"}
    )
    if applied:
        stages["manual"] = (
            "off"
            if request.manual == "none"
            else "dedicated lookup enabled"
            if settings.manual_step
            else "manual tool available; dedicated lookup off"
        )
        if (
            effective is not None
            and effective.investigate == "deterministic"
            and effective.hypothesize == "model"
            and request.tree_of_thought
        ):
            stages["test"] = "deterministic reads; possible model revaluation"
    body = {
        "schema_version": 1,
        "applied": applied,
        "run_inputs": {
            "seed": request.seed,
            "kind": request.kind,
            "mode": request.mode,
            "hazards": request.hazards,
            "tree_of_thought": request.tree_of_thought,
            "manual": request.manual,
        },
        "requested": desired,
        "effective_triage": (
            effective.model_dump(mode="json") if applied and effective else None
        ),
        "overridden": (
            list(overridden_fields(request.triage_settings, effective))
            if applied and effective
            else []
        ),
        "not_applied": sorted(desired) if not applied else [],
        "stages": stages,
        "configured_conclude_primary": (
            settings.triage_model or settings.conclude_model or settings.default_model
            if applied
            else settings.conclude_model or settings.default_model
        ),
        "model_attempts": (
            "Configured only; inspect run model-call audit for actual attempts"
        ),
        "scope": "simulator only; per-run; no controller operations",
    }
    # Digest is a stable, short correlation aid, never a credential.
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["fingerprint"] = hashlib.sha256(canonical.encode()).hexdigest()[:20]
    return body


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: int = Field(ge=1)
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=200)


# An LLM may suggest question IDs; reject free text, paths, tokens and prompts.
# Only short generated question identifiers can appear in live progress.
_SAFE_QUESTION_ID = re.compile(r"(?:[QqRrTt][0-9]{1,3})\Z")


_SAFE_REQUIREMENT_ID = re.compile(r"Q[0-9]{1,3}:(?:[a-z_]{1,24}|job:[0-9]{1,8})\Z")


class SafeRequirementProgress(BaseModel):
    """Source-independent requirement status; never a diagnostic narrative."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: str = Field(
        pattern=r"^Q[0-9]{1,3}:(?:[a-z_]{1,24}|job:[0-9]{1,8})$"
    )
    status: Literal[
        "pending",
        "satisfied",
        "partial",
        "insufficient",
        "stale",
        "unavailable",
        "unsupported",
        "failed",
    ]
    evidence_count: int = Field(ge=0)


# The live timeline is narrower than the private typed trace: fixed codes only.
# Never copy a free-text reason, model message, tool arguments or evidence into it.
_SAFE_DECIDE_EVENTS = frozenset(
    {
        "requirements.compiled",
        "decide.selected",
        "tool.completed",
        "evidence.validated",
        "triage.requirement_evaluated",
        "question.evaluated",
        "triage.stopped",
    }
)
_SAFE_DECIDE_TOOLS = frozenset(
    {
        "get_sensor_summary",
        "get_events",
        "get_maintenance_history",
        "get_settings",
        "get_inspections",
        "get_job_history",
    }
)
_SAFE_DECIDE_STATUSES = frozenset(
    {
        "active",
        "pending",
        "accepted",
        "rejected",
        "failed",
        "stopped",
        "satisfied",
        "unresolved",
        "partial",
        "insufficient",
        "stale",
        "unavailable",
        "unsupported",
    }
)
_SAFE_DECIDE_REASONS = frozenset(
    {
        "compiled",
        "selected",
        "observed",
        "unresolved",
        "closed",
        "requirements_complete",
        "no_eligible_read",
        "capability_unavailable",
        "data_insufficient",
        "retries_exhausted",
        "max_tool_calls",
        "max_iterations",
        "timeout",
        "not_checked",
        "requirement_satisfied",
        "requirement_pending",
        "requirement_partial",
        "requirement_insufficient",
        "requirement_stale",
        "requirement_unavailable",
        "requirement_unsupported",
        "requirement_failed",
        "historical_setting_unproven",
        "record_coverage_unproven",
        "record_structure_missing",
        "inspection_job_ids_missing",
        "inspection_batches_missing",
        "job_path_missing",
        "inspection_machine_unlinked",
        "inspection_dates_missing",
        "alarm_coverage_missing",
        "measurement_coverage_missing",
        "job_time_coverage_missing",
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
        "read_failed",
    }
)
_SAFE_DECIDE_EVENT_LIMIT = 20
_SAFE_DECIDE_EVENT_IDS = 8


class SafeTriageDecideEvent(BaseModel):
    """One source-safe, chronological Decide trace observation, never a tool result."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    sequence: int = Field(ge=1)
    event: Literal[
        "requirements.compiled",
        "decide.selected",
        "tool.completed",
        "evidence.validated",
        "triage.requirement_evaluated",
        "question.evaluated",
        "triage.stopped",
    ]
    phase: Literal["investigate", "test"]
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    status: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    tool: (
        Literal[
            "get_sensor_summary",
            "get_events",
            "get_maintenance_history",
            "get_settings",
            "get_inspections",
            "get_job_history",
        ]
        | None
    ) = None
    requirement_ids: list[str] = Field(default_factory=list, max_length=8)
    requirement_count: int = Field(default=0, ge=0)
    question_ids: list[str] = Field(default_factory=list, max_length=8)
    question_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    request_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{20}$")
    attempt: int | None = Field(default=None, ge=1)
    iteration: int | None = Field(default=None, ge=0)
    candidate_count: int | None = Field(default=None, ge=0)
    remaining_tool_calls: int | None = Field(default=None, ge=0)
    source_cutoff_tick: int | None = Field(default=None, ge=0)
    duration_ms: float | None = Field(default=None, ge=0)


def safe_decide_events(state: Any) -> list[SafeTriageDecideEvent]:
    """Reduce only validated, typed backend audit events to a public contract.

    The audit may hold more than the current live-window limit. The final
    approved audit stays private; the frontend displays a bounded recent tail.
    """
    from capstone.agent.triage_trace import TriageTraceEvent

    projected: list[SafeTriageDecideEvent] = []
    last_sequence = 0
    for trace in getattr(state, "triage_trace_events", ()):
        if not isinstance(trace, TriageTraceEvent):
            continue
        # Do not advertise a replay timeline that moves backward or duplicates
        # an event sequence. Preserve order even across non-Decide audit events.
        if trace.sequence <= last_sequence:
            continue
        last_sequence = trace.sequence
        if trace.event not in _SAFE_DECIDE_EVENTS or trace.phase not in (
            "investigate",
            "test",
        ):
            continue
        try:
            projected.append(
                SafeTriageDecideEvent(
                    sequence=trace.sequence,
                    event=trace.event,
                    phase=trace.phase,
                    reason_code=(
                        trace.reason_code
                        if trace.reason_code in _SAFE_DECIDE_REASONS
                        else "other"
                    ),
                    status=(
                        trace.status if trace.status in _SAFE_DECIDE_STATUSES else None
                    ),
                    tool=trace.tool if trace.tool in _SAFE_DECIDE_TOOLS else None,
                    requirement_ids=[
                        rid
                        for rid in trace.requirement_ids
                        if isinstance(rid, str) and _SAFE_REQUIREMENT_ID.fullmatch(rid)
                    ][:_SAFE_DECIDE_EVENT_IDS],
                    requirement_count=len(trace.requirement_ids),
                    question_ids=[
                        qid
                        for qid in trace.question_ids
                        if isinstance(qid, str) and _SAFE_QUESTION_ID.fullmatch(qid)
                    ][:_SAFE_DECIDE_EVENT_IDS],
                    question_count=len(trace.question_ids),
                    evidence_count=len(trace.evidence_ids),
                    request_hash=trace.request_hash,
                    attempt=trace.attempt,
                    iteration=trace.iteration,
                    candidate_count=trace.candidate_count,
                    remaining_tool_calls=trace.remaining_tool_calls,
                    source_cutoff_tick=trace.source_cutoff_tick,
                    duration_ms=trace.duration_ms,
                )
            )
        except (AttributeError, TypeError, ValueError, ValidationError):
            # A malformed observer record never reaches a client or affects Decide.
            continue
    return projected


class SafeHypothesisCandidate(BaseModel):
    """Counts for one compiled triage candidate; never its evidence or prose."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    id: str = Field(pattern=r"^TC[1-9][0-9]{0,3}$")
    family: CandidateFamily
    status: Literal["unconfirmed"]
    qualified_sources: int = Field(ge=0)
    required_tests: int = Field(ge=0)
    missing_tests: int = Field(ge=0)
    unavailable_tests: int = Field(ge=0)
    open_questions: int = Field(ge=0)


class SafeHypothesisProgress(BaseModel):
    """Deterministic Hypothesize compiler metadata (#299) for live progress."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    rule_version: Literal["1.1", "1.2"] | None = None
    last_action: (
        Literal["compiled", "refreshed", "no_candidates", "rejected"] | None
    ) = None
    candidate_count: int = Field(ge=0)
    candidates_truncated: bool
    candidates: list[SafeHypothesisCandidate] = Field(max_length=12)
    test_requirements: int = Field(ge=0)
    trace_records: int = Field(ge=0)
    logging_failures: int = Field(ge=0)


class SafeExecutedTriage(BaseModel):
    """Which triage stages actually ran (#306), as observed flags and counts."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    run_mode: Literal["custom", "deterministic"]
    fixed_plan_executed: bool
    packet_enabled: bool
    packet_collected: bool
    observe_calls_separate: bool
    conclude_brief_enabled: bool
    conclude_cap_enabled: bool
    hypothesis_reserve_seconds: float = Field(ge=0)
    deadline_seconds: float = Field(ge=0)
    research_tool_call_budget: int = Field(ge=0)
    actual_research_tool_calls: int = Field(ge=0)
    deterministic_decide_reads: int = Field(ge=0)
    compiled_candidates: int = Field(ge=0)
    conclusion_available: bool
    deep_recommended: bool
    # TRIAGE_RANKING (2026-11-20): whether the ranking was asked, how it was
    # judged (fixed codes only), and how many questions carried it. Defaults
    # keep payloads saved before it valid.
    ranking_enabled: bool = False
    ranking_status: (
        Literal["accepted", "abstained", "rejected", "unavailable"] | None
    ) = None
    ranking_reason: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    ranking_requests: int = Field(default=0, ge=0, le=2)


class SafeStageSnapshot(BaseModel):
    """Allowlisted metadata snapshot of the existing Pydantic Graph state.

    Never serialize the model state itself: it contains simulator truth,
    raw tool results, tool arguments, hypothesis text and provider content.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    investigation_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    mode: Literal["triage", "deep"]
    stage: (
        Literal[
            "observe",
            "manual",
            "plan",
            "investigate",
            "hypothesize",
            "test",
            "critique",
            "recheck",
            "conclude",
            "decide",
            "propose",
            "execute",
            "verify",
        ]
        | None
    ) = None
    iteration_count: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    hypothesis_count: int = Field(ge=0)
    unresolved_question_ids: list[str] = Field(max_length=25)
    unresolved_question_count: int = Field(default=0, ge=0)
    termination_reason: str | None = Field(default=None, pattern=r"^[a-z][a-z_]{0,63}$")
    conclusion_available: bool
    triage_run_mode: Literal["custom", "deterministic"] | None = None
    # Nested contracts, not free-form dicts: every key is allowlisted.
    hypothesis_progress: SafeHypothesisProgress | None = None
    executed_triage: SafeExecutedTriage | None = None
    # The additional deep lifecycle (#300) is a strict nested Pydantic contract.
    # A triage state never has deep signals, even when escalation is expected.
    deep_signals: SafeDeepSignals | None = None

    # Every additional field is a *derived count or authorization flag*, not
    # the underlying data. All values are bounded by the Pydantic contract.
    answered_question_count: int = Field(default=0, ge=0)
    decision_count: int = Field(default=0, ge=0)
    remaining_iterations: int = Field(default=0, ge=0)
    remaining_tool_calls: int = Field(default=0, ge=0)
    repeated_calls: int = Field(default=0, ge=0)
    failed_tool_calls: int = Field(default=0, ge=0)
    malformed_results: int = Field(default=0, ge=0)
    interpretation_failures: int = Field(default=0, ge=0)
    unproductive_steps: int = Field(default=0, ge=0)
    followup_tool_calls: int = Field(default=0, ge=0)
    screening_tool_calls: int = Field(default=0, ge=0)
    observe_tool_calls: int = Field(default=0, ge=0)
    last_observed_tick: int | None = Field(default=None, ge=0)
    observation_cutoff_tick: int | None = Field(default=None, ge=0)
    clock_verified: bool | None = None
    triage_requirement_total: int = Field(default=0, ge=0)
    triage_requirement_satisfied: int = Field(default=0, ge=0)
    triage_requirement_open: int = Field(default=0, ge=0)
    triage_question_gaps: int = Field(default=0, ge=0)
    triage_evidence_accepted: int = Field(default=0, ge=0)
    triage_evidence_rejected: int = Field(default=0, ge=0)
    triage_decide_reads: int = Field(default=0, ge=0)
    triage_decide_stops: int = Field(default=0, ge=0)
    triage_candidates: int = Field(default=0, ge=0)
    triage_test_requirements: int = Field(default=0, ge=0)
    triage_trace_events: int = Field(default=0, ge=0)
    triage_logging_failures: int = Field(default=0, ge=0)
    deep_recommended: bool | None = None
    # The packet is source coverage, never its readings or screening scores.
    packet_roster_verified: bool | None = None
    packet_roster_size: int = Field(default=0, ge=0)
    packet_screened_machines: int = Field(default=0, ge=0)
    packet_missing_machines: int = Field(default=0, ge=0)
    packet_calls_mandatory: int = Field(default=0, ge=0)
    packet_calls_optional: int = Field(default=0, ge=0)
    packet_calls_qualified: int = Field(default=0, ge=0)
    packet_calls_unavailable: int = Field(default=0, ge=0)
    packet_items_qualified: int = Field(default=0, ge=0)
    packet_items_missing: int = Field(default=0, ge=0)
    triage_test_records: int = Field(default=0, ge=0)
    requirement_statuses: list[SafeRequirementProgress] = Field(
        default_factory=list, max_length=32
    )
    requirement_statuses_truncated: bool = False
    # A bounded chronological tail; counts refer to the entire validated trace.
    decide_event_total: int = Field(default=0, ge=0)
    decide_events_truncated: bool = False
    decide_events_recent: list[SafeTriageDecideEvent] = Field(
        default_factory=list, max_length=_SAFE_DECIDE_EVENT_LIMIT
    )

    @field_validator("unresolved_question_ids")
    @classmethod
    def validate_public_question_ids(cls, ids: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value) for value in ids):
            raise ValueError("Unapproved question identifier")
        return ids


# Explicit projection only. Never infer a public schema from state.model_dump().
SAFE_STAGE_FIELDS = frozenset(SafeStageSnapshot.model_fields)


def safe_executed_triage(state: Any) -> dict[str, Any] | None:
    """Observed, allowlisted stage flags; excludes sensor values and prompts."""
    # Variables:
    #   state: The finished triage Graph state, or None when no triage ran; a
    #     deep state also yields None, because these flags describe triage only.
    #   ranking: The checked ranking verdict; only its status, reason code and
    #     request count cross to the browser here (the picks are in the report).
    if state is None or state.mode != "triage":
        return None
    ranking = state.triage_ranking
    return SafeExecutedTriage.model_validate(
        {
            "run_mode": state.triage_run_mode,
            "fixed_plan_executed": state.fixed_plan_used,
            "packet_enabled": state.triage_packet_enabled,
            "packet_collected": state.triage_packet is not None,
            "observe_calls_separate": state.triage_observe_separate,
            "conclude_brief_enabled": state.triage_conclude_brief,
            "conclude_cap_enabled": state.triage_conclude_cap,
            "hypothesis_reserve_seconds": state.triage_hypothesis_seconds,
            "deadline_seconds": state.budgets.timeout_seconds,
            "research_tool_call_budget": state.budgets.max_tool_calls,
            "actual_research_tool_calls": state.research_tool_calls,
            "deterministic_decide_reads": state.triage_deterministic_reads,
            "compiled_candidates": len(state.triage_candidates),
            "conclusion_available": state.conclusion is not None,
            "deep_recommended": bool(state.deep_recommended),
            "ranking_enabled": state.triage_ranking_enabled,
            "ranking_status": None if ranking is None else ranking.status,
            "ranking_reason": None if ranking is None else ranking.reason,
            "ranking_requests": state.triage_ranking_requests,
        }
    ).model_dump(mode="json")


def safe_hypothesis_progress(state: Any) -> dict[str, Any] | None:
    """Allowlisted typed compiler metadata; no prose or source payloads."""
    # Variables:
    #   candidates: Compiled triage candidates, each revalidated from its own
    #     values so a mutated instance cannot carry extra data to the browser.
    #   last: The newest valid Hypothesize trace record, which names the rule
    #     version and what the compiler last did.
    if state.mode != "triage":
        return None
    from capstone.agent.triage_hypothesize import TriageCandidate, TriageHypothesisTrace

    candidates = []
    for value in state.triage_candidates:
        if not isinstance(value, TriageCandidate):
            continue
        try:
            # Do not trust Pydantic instances produced by unchecked model_copy
            # updates or mutated nested references. Validate actual values.
            candidates.append(TriageCandidate.model_validate(value.model_dump()))
        except (TypeError, ValueError):
            continue
    last = None
    for value in reversed(state.triage_hypothesis_trace):
        if not isinstance(value, TriageHypothesisTrace):
            continue
        try:
            last = TriageHypothesisTrace.model_validate(value.model_dump())
            break
        except (TypeError, ValueError):
            continue
    return SafeHypothesisProgress.model_validate(
        {
            "rule_version": None if last is None else last.rule_version,
            "last_action": None if last is None else last.action,
            "candidate_count": len(candidates),
            "candidates_truncated": len(candidates) > 12,
            "candidates": [
                {
                    "id": c.id,
                    "family": c.family,
                    "status": c.status,
                    "qualified_sources": len(c.observation_evidence_ids),
                    "required_tests": len(c.discriminating_requirement_ids),
                    "missing_tests": len(c.missing_requirement_ids),
                    "unavailable_tests": len(c.unavailable_requirement_ids),
                    "open_questions": len(c.open_question_ids),
                }
                for c in candidates[:12]
            ],
            "test_requirements": len(state.triage_test_requirement_ids),
            "trace_records": len(state.triage_hypothesis_trace),
            "logging_failures": state.triage_hypothesis_logging_failures,
        }
    ).model_dump(mode="json")


def safe_stage(state: Any) -> dict[str, Any]:
    """Provide field-level progress, without publishing agent-private values."""
    # All values are already tracked by the same Graph state. The observer
    # calls no new models/tools, and never reads hidden simulator ground truth.
    # Variables:
    #   decide_events: The sanitized Decide trace (#296); only its latest
    #     entries are published, with the full count alongside.
    #   safe_requirements: Requirement statuses whose IDs match the public
    #     pattern; any other ID is left out rather than shown.
    #   ids: Open question IDs that pass the strict public pattern.
    #   deep_signals (field): Deep-loop milestones (#300), set only for a deep
    #     state so a triage snapshot never claims deep progress.
    results = getattr(state, "triage_requirement_results", {})
    checks = getattr(state, "triage_evidence_checks", ())
    requirements = getattr(state, "triage_requirements", {})
    raw_reason = getattr(state, "termination_reason", None)
    reason = getattr(raw_reason, "value", None)
    packet = getattr(state, "triage_packet", None)
    packet_calls = () if packet is None else packet.calls
    packet_items = () if packet is None else packet.items
    decide_events = safe_decide_events(state) if state.mode == "triage" else []
    satisfied_requirements = sum(
        results[rid].status == "satisfied" for rid in requirements if rid in results
    )
    safe_requirements = [
        SafeRequirementProgress(
            requirement_id=rid,
            status=result.status,
            evidence_count=len(getattr(result, "evidence_ids", ())),
        )
        for rid, result in sorted(results.items())
        if rid in requirements and _SAFE_REQUIREMENT_ID.fullmatch(rid)
    ]
    ids = [
        q.id
        for q in getattr(state, "unanswered_questions", ())[:25]
        if isinstance(q.id, str) and _SAFE_QUESTION_ID.fullmatch(q.id)
    ]
    return SafeStageSnapshot(
        investigation_id=str(state.investigation_id),
        mode=state.mode,
        stage=state.stage,
        iteration_count=state.iteration_count,
        tool_calls=state.tool_call_count,
        evidence_count=len(state.evidence),
        hypothesis_count=len(state.hypotheses),
        unresolved_question_ids=ids,
        unresolved_question_count=len(getattr(state, "unanswered_questions", ())),
        termination_reason=reason,
        conclusion_available=state.conclusion is not None,
        answered_question_count=len(getattr(state, "answers", {})),
        decision_count=len(getattr(state, "decisions", ())),
        remaining_iterations=getattr(state, "remaining_iterations", 0),
        remaining_tool_calls=getattr(state, "remaining_tool_calls", 0),
        repeated_calls=getattr(state, "repeated_calls", 0),
        failed_tool_calls=getattr(state, "failed_tool_calls", 0),
        malformed_results=getattr(state, "malformed_results", 0),
        interpretation_failures=getattr(state, "interpretation_failures", 0),
        unproductive_steps=getattr(state, "unproductive_steps", 0),
        followup_tool_calls=getattr(state, "followup_tool_calls_used", 0),
        screening_tool_calls=getattr(state, "screening_tool_calls_used", 0),
        observe_tool_calls=getattr(state, "observe_tool_calls_used", 0),
        last_observed_tick=getattr(state, "last_tick", None),
        observation_cutoff_tick=getattr(state, "triage_observation_cutoff_tick", None),
        clock_verified=getattr(state, "triage_clock_verified", None),
        triage_requirement_total=len(requirements),
        triage_requirement_satisfied=satisfied_requirements,
        triage_requirement_open=len(requirements) - satisfied_requirements,
        triage_question_gaps=len(getattr(state, "triage_question_gaps", {})),
        triage_evidence_accepted=sum(c.accepted for c in checks),
        triage_evidence_rejected=sum(not c.accepted for c in checks),
        triage_decide_reads=getattr(state, "triage_deterministic_reads", 0),
        triage_decide_stops=getattr(state, "triage_deterministic_stops", 0),
        triage_candidates=len(getattr(state, "triage_candidates", ())),
        triage_test_requirements=len(getattr(state, "triage_test_requirement_ids", ())),
        triage_trace_events=len(getattr(state, "triage_trace_events", ())),
        triage_logging_failures=getattr(state, "triage_logging_failures", 0),
        deep_recommended=getattr(state, "deep_recommended", None),
        packet_roster_verified=None if packet is None else packet.roster_verified,
        packet_roster_size=0 if packet is None else len(packet.roster),
        packet_screened_machines=0 if packet is None else len(packet.screened_machines),
        packet_missing_machines=(
            0 if packet is None else len(packet.absent_from_screening)
        ),
        packet_calls_mandatory=sum(c.role == "mandatory" for c in packet_calls),
        packet_calls_optional=sum(c.role == "optional" for c in packet_calls),
        packet_calls_qualified=sum(c.qualified for c in packet_calls),
        packet_calls_unavailable=sum(
            c.outcome == "skipped_unavailable" for c in packet_calls
        ),
        packet_items_qualified=sum(i.status == "qualified" for i in packet_items),
        packet_items_missing=sum(i.status == "missing" for i in packet_items),
        triage_test_records=len(getattr(state, "triage_test_records", ())),
        requirement_statuses=safe_requirements[:32],
        requirement_statuses_truncated=len(safe_requirements) > 32,
        decide_event_total=len(decide_events),
        decide_events_truncated=len(decide_events) > _SAFE_DECIDE_EVENT_LIMIT,
        decide_events_recent=decide_events[-_SAFE_DECIDE_EVENT_LIMIT:],
        triage_run_mode=getattr(state, "triage_run_mode", None)
        if state.mode == "triage"
        else None,
        hypothesis_progress=(
            safe_hypothesis_progress(state)
            if hasattr(state, "triage_hypothesis_trace")
            else None
        ),
        executed_triage=(
            safe_executed_triage(state) if hasattr(state, "triage_run_mode") else None
        ),
        deep_signals=safe_deep_signals(state) if state.mode == "deep" else None,
    ).model_dump(mode="json")


class SimulatorRuns:
    """Single-host runner; SQLite recovers status but never resumes an approval.

    At most one active episode per local service. SQLite carries events/snapshots
    across browser reconnects. An API process restart fails interrupted runs.
    """

    def __init__(self, database: Path, *, approval_timeout_seconds: float = 240):
        self.database = database
        self.artifact_root = database.parent
        self.approval_timeout_seconds = approval_timeout_seconds
        self.lock = threading.RLock()
        self.waiters: dict[tuple[str, int], threading.Event] = {}
        self.active: set[str] = set()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._initialize_store()

    def _initialize_store(self) -> None:
        """Create or recover the local journal; remote stores override this."""
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, request_key TEXT UNIQUE,
                    requested TEXT NOT NULL, state TEXT NOT NULL,
                    snapshot TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL, seq INTEGER NOT NULL,
                    event TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY (run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS run_reviews (
                    run_id TEXT NOT NULL, proposal_id INTEGER NOT NULL,
                    status TEXT NOT NULL, details TEXT NOT NULL,
                    PRIMARY KEY (run_id, proposal_id)
                );
            """)
            db.execute(
                "UPDATE runs SET state='interrupted', updated_at=? "
                "WHERE state IN ('queued', 'running', 'awaiting_review')",
                (utc_now(),),
            )
            db.execute("UPDATE run_reviews SET status='expired' WHERE status='pending'")

    @contextmanager
    def _db(self):
        con = sqlite3.connect(str(self.database), timeout=5)
        con.execute("PRAGMA busy_timeout=5000")
        try:
            with con:
                yield con
        finally:
            con.close()

    def investigation_audit_path(self, run_id: str) -> Path:
        """Private, server-owned path derived from an existing UUID run id."""
        if str(uuid.UUID(run_id)) != run_id:
            raise ValueError("Invalid run identifier")
        return self.artifact_root / "simulator-investigations" / (run_id + ".jsonl")

    def investigation_event_path(self, run_id: str) -> Path:
        """Server-owned safe operational event log, separate from private audits."""
        return self.investigation_audit_path(run_id).with_suffix(".events.jsonl")

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self.lock, self._db() as db:
            row = db.execute(
                "SELECT run_id, requested, state, snapshot, created_at, updated_at "
                "FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row[0],
            "requested": json.loads(row[1]),
            "state": row[2],
            "snapshot": json.loads(row[3]),
            "created_at": row[4],
            "updated_at": row[5],
        }

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.lock, self._db() as db:
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT run_id FROM runs ORDER BY created_at DESC LIMIT ?",
                    (min(limit, 100),),
                ).fetchall()
            ]
        return [r for id_ in ids if (r := self.get(id_)) is not None]

    def events_since(
        self, run_id: str, seq: int, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Generic SSE excludes model rows; only the typed endpoint serves them."""
        if self.get(run_id) is None:
            return []
        with self.lock, self._db() as db:
            rows = db.execute(
                "SELECT seq, event, payload FROM run_events WHERE run_id=? AND seq>? "
                "AND event NOT LIKE 'model.%' ORDER BY seq LIMIT ?",
                (run_id, seq, min(limit, 100)),
            ).fetchall()
        return [
            {"seq": n, "event": name, "data": json.loads(payload)}
            for n, name, payload in rows
        ]

    def _append_model_event(
        self,
        run_id: str,
        event: Literal[
            "model.monitor", "model.call", "model.config", "model.monitor.finished"
        ],
        payload: dict[str, Any],
    ) -> None:
        """Durably append safe telemetry WITHOUT changing the run snapshot.

        The same transactional run_events journal is backed by local SQLite
        or Render PostgreSQL, so reconnect and process restart cannot erase
        committed model calls. Independent of the lossy stage progress queue.
        """
        from capstone.api.model_calls import (
            SafeModelCall,
            SafeModelConfiguration,
            SafeModelSummary,
        )

        if event == "model.call":
            payload = SafeModelCall.model_validate(payload).model_dump(mode="json")
        elif event == "model.config":
            payload = SafeModelConfiguration.model_validate(payload).model_dump(
                mode="json"
            )
        elif event == "model.monitor.finished":
            payload = SafeModelSummary.model_validate(payload).model_dump(mode="json")
        else:
            payload = {"schema_version": 1}
        with self.lock, self._db() as db:
            self._lock_event_sequence(db, run_id)
            next_seq = db.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM run_events WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO run_events VALUES(?,?,?,?,?)",
                (run_id, next_seq, event, json.dumps(payload), utc_now()),
            )

    def record_model_call(self, run_id: str, call: Any, index: int) -> None:
        """Persist only the allowlisted ModelCall/Attempt projection."""
        from capstone.api.model_calls import project_model_call

        self._append_model_event(run_id, "model.call", project_model_call(call, index))

    def model_calls(self, run_id: str) -> dict[str, Any]:
        """Latest bounded chronological calls, readable after reconnect."""
        from capstone.api.model_calls import (
            MAX_CALLS,
            SafeModelCall,
            SafeModelConfiguration,
            SafeModelSummary,
        )

        if self.get(run_id) is None:
            raise LookupError("Run not found")
        with self.lock, self._db() as db:
            marker = db.execute(
                "SELECT 1 FROM run_events WHERE run_id=? "
                "AND event='model.monitor' LIMIT 1",
                (run_id,),
            ).fetchone()
            rows = db.execute(
                "SELECT seq, payload FROM run_events WHERE run_id=? "
                "AND event='model.call' ORDER BY seq DESC LIMIT ?",
                (run_id, MAX_CALLS + 1),
            ).fetchall()
            configured = db.execute(
                "SELECT payload FROM run_events WHERE run_id=? "
                "AND event='model.config' ORDER BY seq DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            finished = db.execute(
                "SELECT payload FROM run_events WHERE run_id=? "
                "AND event='model.monitor.finished' ORDER BY seq DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        configuration = None
        if configured is not None:
            try:
                configuration = SafeModelConfiguration.model_validate_json(
                    configured[0]
                ).outcome
            except (ValueError, TypeError):
                pass
        summary = None
        if finished is not None:
            try:
                summary = SafeModelSummary.model_validate_json(finished[0]).model_dump(
                    mode="json"
                )
            except (ValueError, TypeError):
                pass
        items = []
        invalid_rows = 0
        for seq, raw in reversed(rows[:MAX_CALLS]):
            try:
                # Revalidate on reads: storage is NOT an API serializer.
                clean = SafeModelCall.model_validate_json(raw).model_dump(mode="json")
            except (ValueError, TypeError):
                invalid_rows += 1
                continue
            items.append({"seq": seq, **clean})
        return {
            "availability": "available" if marker is not None else "not_recorded",
            "window_scope": "latest_200",
            "truncated": len(rows) > MAX_CALLS,
            "invalid_rows": invalid_rows,
            "configuration": configuration,
            "summary": summary,
            "items": items,
        }

    def _lock_event_sequence(self, db: Any, run_id: str) -> None:
        """SQLite uses its existing transaction lock; remote stores may lock a row."""

    def _lock_submission(self, db: Any) -> None:
        """Remote stores may enforce cross-process admission before insertion."""

    def _store_has_active_run(self, db: Any) -> bool:
        """Local admission is guarded by the process lock and restart recovery."""
        return False

    def _persist_artifacts(self, run_id: str) -> None:
        """SQLite keeps the original private JSONL files locally."""

    def close(self) -> None:
        """Local SQLite connections are closed after each transaction."""

    def _emit(
        self,
        run_id: str,
        event: str,
        payload: dict[str, Any],
        *,
        state: RunState | None = None,
    ) -> None:
        """Atomically journal and snapshot safe progress for SQLite/PostgreSQL.

        A terminal run is immutable to late observer events. The last
        authoritative Graph state is included in completion/failure, so a
        bounded watcher queue cannot cause a permanently missing phase.
        """
        # Variables:
        #   current_state: The run's stored state; once terminal, late
        #     stage.updated events are ignored.
        #   progress: The snapshot's per-path progress (triage, deep, latest,
        #     deep_timeline, deep_transition_total), carried over from the
        #     prior snapshot and updated by this event before it is saved.
        #   final_progress: The authoritative progress sent with run.completed
        #     or run.failed; it replaces whatever the watcher last delivered.
        #   next_seq: This event's journal sequence, also used as the deep
        #     checkpoint's sequence so the timeline matches the journal.
        #   timeline: The bounded (48) list of observed deep stage changes.
        with self.lock, self._db() as db:
            self._lock_event_sequence(db, run_id)
            row = db.execute(
                "SELECT state, snapshot FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise LookupError("Run not found")
            current_state, prior = row
            if current_state in ("completed", "failed", "interrupted"):
                # A late stage writer cannot replace terminal results.
                if event == "stage.updated":
                    return
            previous = json.loads(prior)
            previous_progress = (
                previous.get("progress") if isinstance(previous, dict) else None
            )
            progress = (
                {
                    key: val
                    for key, val in previous_progress.items()
                    if key
                    in (
                        "triage",
                        "deep",
                        "latest",
                        "deep_timeline",
                        "deep_transition_total",
                    )
                }
                if isinstance(previous_progress, dict)
                else {}
            )
            if event == "stage.updated":
                # Prevent a future producer from bypassing the watcher contract.
                validated = SafeStageSnapshot.model_validate(payload)
                payload = validated.model_dump(mode="json")
                progress[validated.mode] = payload
                progress["latest"] = validated.mode
            elif event in ("run.completed", "run.failed"):
                # Final snapshots come from the actual episode return value
                # (or the last observed state after a failure). No queue
                # delivery/flush timing may discard the final triage path.
                final_progress = payload.get("progress")
                if isinstance(final_progress, dict):
                    for mode in ("triage", "deep"):
                        source = final_progress.get(mode)
                        if source is not None:
                            checked = SafeStageSnapshot.model_validate(source)
                            if checked.mode != mode:
                                raise ValueError("Progress mode mismatch")
                            progress[mode] = checked.model_dump(mode="json")
                    latest = final_progress.get("latest")
                    if latest in ("triage", "deep") and latest in progress:
                        progress["latest"] = latest
                    payload = {
                        key: value
                        for key, value in payload.items()
                        if key != "progress"
                    }
            next_seq = db.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM run_events WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
            if event == "stage.updated" and payload["mode"] == "deep":
                # The Pydantic Graph can revisit stages. Record each *observed*
                # transition exactly once, using the same source sequence as
                # the durable event journal. Never infer a skipped stage.
                earlier = progress.get("deep_timeline")
                timeline: list[dict[str, Any]] = []
                if isinstance(earlier, list):
                    for item in earlier[-48:]:
                        try:
                            checked = SafeDeepCheckpoint.model_validate(item)
                        except ValueError:
                            continue
                        timeline.append(checked.model_dump(mode="json"))
                current_stage = payload.get("stage")
                if current_stage is not None and (
                    not timeline or timeline[-1]["stage"] != current_stage
                ):
                    checkpoint = checkpoint_from_stage(next_seq, payload)
                    timeline.append(checkpoint.model_dump(mode="json"))
                    prev_total = progress.get("deep_transition_total")
                    if type(prev_total) is not int or prev_total < 0:
                        prev_total = len(timeline) - 1
                    progress["deep_transition_total"] = prev_total + 1
                if timeline:
                    progress["deep_timeline"] = timeline[-48:]
            db.execute(
                "INSERT INTO run_events VALUES(?,?,?,?,?)",
                (run_id, next_seq, event, json.dumps(payload), utc_now()),
            )
            # The event journal holds immutable source events; the snapshot
            # keeps the latest validated progress per path, computed above in
            # this same locked transaction (SQLite or PostgreSQL row lock).
            # Never rebuild it from the prior snapshot here: that discarded
            # the reconciled final progress of run.completed/run.failed.
            snapshot = {**payload, "progress": progress} if progress else payload
            if state is not None:
                db.execute(
                    "UPDATE runs SET state=?, snapshot=?, updated_at=? WHERE run_id=?",
                    (state, json.dumps(snapshot), utc_now(), run_id),
                )
            else:
                db.execute(
                    "UPDATE runs SET snapshot=?, updated_at=? WHERE run_id=?",
                    (json.dumps(snapshot), utc_now(), run_id),
                )

    def submit(self, request: RunRequest, request_key: str) -> dict[str, Any]:
        """At most one active episode; freeze its effective settings at admission."""
        settings = get_settings()
        effective = (
            resolve_triage_run(settings, request.triage_settings)
            if request.mode == "triage"
            else None
        )
        request._effective_triage = effective
        configuration = public_run_configuration(request, settings, effective=effective)
        if (
            request.configuration_fingerprint is not None
            and request.configuration_fingerprint != configuration["fingerprint"]
        ):
            raise StaleRunConfiguration(
                "preview fingerprint does not match effective settings"
            )
        # Stored alongside the request for durable replay and UI inspection.
        # Do not reconstruct effective settings from a future process environment.
        serialized = json.dumps(
            {
                **request.model_dump(mode="json"),
                "effective_configuration": configuration,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.lock:
            with self._db() as db:
                self._lock_submission(db)
                existing = db.execute(
                    "SELECT run_id, requested FROM runs WHERE request_key=?",
                    (request_key,),
                ).fetchone()
                if existing:
                    if existing[1] != serialized:
                        raise ValueError(
                            "idempotency key reused for different settings"
                        )
                    return self.get(existing[0])
                if self.active or self._store_has_active_run(db):
                    raise RuntimeError("one simulator run is already active")
                id_ = str(uuid.uuid4())
                initial = {
                    "stage": None,
                    "mode": request.mode,
                    "status": "queued",
                    "configuration_fingerprint": configuration["fingerprint"],
                }
                db.execute(
                    "INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                    (
                        id_,
                        request_key,
                        serialized,
                        "queued",
                        json.dumps(initial),
                        utc_now(),
                        utc_now(),
                    ),
                )
            self.active.add(id_)
        threading.Thread(
            target=self._execute,
            args=(id_, request),
            daemon=True,
            name="simulator-run-" + id_[:8],
        ).start()
        return self.get(id_)

    def pending_reviews(self) -> list[dict[str, Any]]:
        with self.lock, self._db() as db:
            rows = db.execute(
                "SELECT run_id, proposal_id, details FROM run_reviews WHERE status='pending' "
                "ORDER BY run_id LIMIT 50",
            ).fetchall()
        return [{"run_id": r[0], "proposal_id": r[1], **json.loads(r[2])} for r in rows]

    def decide(self, run_id: str, decision: ReviewDecision) -> dict[str, Any]:
        key = (run_id, decision.proposal_id)
        with self.lock:
            with self._db() as db:
                row = db.execute(
                    "SELECT status FROM run_reviews WHERE run_id=? AND proposal_id=?",
                    key,
                ).fetchone()
                if row is None:
                    raise LookupError("review request not found")
                if row[0] != "pending" or key not in self.waiters:
                    raise ValueError("review is not pending")
                details = json.loads(
                    db.execute(
                        "SELECT details FROM run_reviews WHERE run_id=? AND proposal_id=?",
                        key,
                    ).fetchone()[0]
                )
                details["note"] = decision.note
                db.execute(
                    "UPDATE run_reviews SET status=?, details=? "
                    "WHERE run_id=? AND proposal_id=? AND status='pending'",
                    (decision.decision, json.dumps(details), *key),
                )
            # Record the decision before waking the episode. Otherwise the
            # worker may finish and a late review event can regress the run
            # from completed back to running.
            self._emit(
                run_id,
                "review.decided",
                {
                    "proposal_id": decision.proposal_id,
                    "decision": decision.decision,
                    "status": "decided_not_executed",
                    "mode": "deep",
                },
                state="running",
            )
            self.waiters[key].set()
        return {
            "run_id": run_id,
            "proposal_id": decision.proposal_id,
            "decision": decision.decision,
        }

    def _await_review(self, run_id: str, proposal: Any) -> tuple[bool, str]:
        """Called only from episode worker, never the HTTP request thread."""
        id_ = int(proposal.proposal_id)
        key = (run_id, id_)
        fields = {
            "proposal_id": id_,
            "machine_id": str(proposal.machine_id)[:80],
            "action": str(proposal.action)[:160],
            "reason": str(proposal.reason)[:600],
            "predicted_effect": str(getattr(proposal, "predicted_effect", "") or "")[
                :600
            ],
            "note": "",
        }
        waiter = threading.Event()
        with self.lock:
            with self._db() as db:
                db.execute(
                    "INSERT INTO run_reviews VALUES(?,?,?,?)",
                    (run_id, id_, "pending", json.dumps(fields)),
                )
            self.waiters[key] = waiter
        self._emit(run_id, "review.requested", fields, state="awaiting_review")
        accepted = waiter.wait(self.approval_timeout_seconds)
        with self.lock:
            with self._db() as db:
                row = db.execute(
                    "SELECT status, details FROM run_reviews WHERE run_id=? AND proposal_id=?",
                    key,
                ).fetchone()
                if not accepted and row and row[0] == "pending":
                    db.execute(
                        "UPDATE run_reviews SET status='expired' "
                        "WHERE run_id=? AND proposal_id=? AND status='pending'",
                        key,
                    )
            self.waiters.pop(key, None)
        status = row[0] if row else "expired"
        if status == "pending":
            status = "expired"
        # A committed approval is not enough to resume an episode: the
        # in-process reviewer waiter must also have received the signal.
        # If event delivery failed after the DB update, fail closed rather
        # than treating a stale "approve" as permission to act.
        if status == "approve" and accepted:
            return True, json.loads(row[1]).get(
                "note", ""
            ) or "approved by simulator reviewer"
        if status == "approve":
            return False, "review notification not confirmed"
        return False, "review timed out" if status == "expired" else (
            json.loads(row[1]).get("note", "") or "rejected by simulator reviewer"
        )

    def _execute(self, run_id: str, request: RunRequest) -> None:
        """Run one episode in the worker thread and journal its lifecycle."""
        # Variables:
        #   progress: Bounded queue between the Graph watcher and the journal
        #     writer, so a slow database never blocks the investigation.
        #   latest_observed: The last safe snapshot per path, sent with a
        #     failure so a crash still reports how far each path got.
        #   configuration: The effective settings frozen at submission (#306);
        #     its fingerprint goes into run.started and the whole record into
        #     run.completed, so a reconnecting browser sees what actually ran.
        #   triage: The triage state of this episode, or None for a deep-only
        #     run; the source of the triage report and triage_execution flags.
        progress: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=128)
        missed = [0]
        latest_observed: dict[str, dict[str, Any]] = {}
        policy: Any = None
        recorded_calls = [0]
        telemetry_failures = [0]

        def flush_model_calls() -> None:
            """Persist each finished question once; retry after journal outages."""
            if policy is None:
                return
            calls = getattr(policy, "calls", ())
            while recorded_calls[0] < len(calls):
                try:
                    self.record_model_call(
                        run_id, calls[recorded_calls[0]], recorded_calls[0] + 1
                    )
                except Exception:
                    # An observer cannot abort a model decision or expose the
                    # exception: provider messages may contain private content.
                    telemetry_failures[0] += 1
                    return
                recorded_calls[0] += 1

        def finish_model_monitor(questions_seen: int, questions_persisted: int) -> None:
            try:
                self._append_model_event(
                    run_id,
                    "model.monitor.finished",
                    {
                        "schema_version": 1,
                        "questions_seen": questions_seen,
                        "questions_persisted": questions_persisted,
                        "write_failures": telemetry_failures[0],
                        "complete": questions_seen == questions_persisted,
                    },
                )
            except Exception:
                telemetry_failures[0] += 1

        def watch(state: Any) -> None:
            flush_model_calls()
            try:
                snapshot = safe_stage(state)
                if latest_observed.get(snapshot["mode"]) == snapshot:
                    return  # No change to the public contract; avoid DB churn.
                latest_observed[snapshot["mode"]] = snapshot
                progress.put_nowait(snapshot)
            except Exception:
                # Never log observer errors; they may contain private evidence.
                # The terminal envelope will reconcile the last valid snapshot.
                missed[0] += 1

        def publish() -> None:
            while True:
                row = progress.get()
                try:
                    if row is None:
                        return
                    try:
                        self._emit(run_id, "stage.updated", row)
                    except Exception:
                        # PostgreSQL driver/validation failures are not sqlite3.Error.
                        # The observer must not die, deadlock progress.join(), or
                        # influence the Graph's model/tool decisions.
                        missed[0] += 1
                finally:
                    progress.task_done()

        writer = threading.Thread(
            target=publish, name="run-events-" + run_id[:8], daemon=True
        )
        writer.start()
        manual = None
        try:
            submitted = self.get(run_id)
            configuration = (
                None
                if submitted is None
                else submitted["requested"].get("effective_configuration")
            )
            self._emit(
                run_id,
                "run.started",
                {
                    "status": "running",
                    "mode": request.mode,
                    # Lets a reconnecting browser match the preview it approved.
                    "configuration_fingerprint": (
                        None
                        if configuration is None
                        else configuration.get("fingerprint")
                    ),
                },
                state="running",
            )
            self._append_model_event(run_id, "model.monitor", {"schema_version": 1})
            from capstone.agent.completion import AuditLog
            from capstone.episode import run_episode
            from capstone.experiment import model_policy_factory, open_manual
            from capstone.observability import EventLogger

            audit_path = self.investigation_audit_path(run_id)
            audit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            manual = open_manual(request.manual) if request.manual != "none" else None
            try:
                policy = model_policy_factory(
                    with_recall=False,
                    with_manual=manual is not None,
                    tree_of_thought=request.tree_of_thought,
                )()
            except Exception as error:
                from capstone.providers.chat import ModelError

                missing = (
                    isinstance(error, ModelError)
                    and str(error).startswith("set ")
                    and "_API_KEY" in str(error)
                )
                try:
                    self._append_model_event(
                        run_id,
                        "model.config",
                        {
                            "schema_version": 1,
                            "outcome": (
                                "missing_credentials"
                                if missing
                                else "invalid_configuration"
                            ),
                        },
                    )
                except Exception:
                    telemetry_failures[0] += 1
                raise
            self._append_model_event(
                run_id,
                "model.config",
                {"schema_version": 1, "outcome": "configured"},
            )
            # Keep structured operational metadata in a separate private file.
            # EventLogger rejects free text, evidence, provider secrets and
            # unvalidated metadata; it is not the investigator's audit.
            with self.investigation_event_path(run_id).open(
                "a", encoding="utf-8"
            ) as event_stream:
                result = run_episode(
                    request.seed,
                    policy,
                    kind=request.kind,
                    triage=request.mode == "triage",
                    triage_configuration=request._effective_triage,
                    hazards=request.hazards,
                    manual=manual,
                    watch=watch,
                    log=AuditLog(audit_path),
                    event_logger=EventLogger(event_stream, name="ui-" + run_id),
                    approver=lambda proposal: self._await_review(run_id, proposal),
                    run_key="ui/" + run_id,
                )
            flush_model_calls()
            research_questions = len(getattr(policy, "calls", ()))
            critic_recorded = 0
            for number, critic_call in enumerate(
                result.critic_calls, start=research_questions + 1
            ):
                try:
                    self.record_model_call(run_id, critic_call, number)
                except Exception:
                    telemetry_failures[0] += 1
                else:
                    critic_recorded += 1
            finish_model_monitor(
                research_questions + len(result.critic_calls),
                recorded_calls[0] + critic_recorded,
            )
            # PostgreSQL is remote; a stalled publisher must not indefinitely
            # block the worker's terminal state. The terminal snapshot is
            # independently rebuilt from the returned Graph state below.
            flush_deadline = time.monotonic() + 3.0
            while progress.unfinished_tasks and time.monotonic() < flush_deadline:
                time.sleep(0.02)
            if progress.unfinished_tasks:
                missed[0] += 1
            if missed[0]:
                try:
                    self._emit(
                        run_id,
                        "resync.required",
                        {
                            "dropped_ui_updates": missed[0],
                            "mode": request.mode,
                        },
                    )
                except Exception:
                    # A failed optional warning must not turn a valid episode
                    # into run.failed; the terminal snapshot still reconciles.
                    pass
            triage = (
                result.triage
                if result.triage is not None
                else (result.state if result.state.mode == "triage" else None)
            )
            report = (
                None
                if triage is None or triage.triage_report is None
                else (triage.triage_report.model_dump(mode="json"))
            )
            # A completed run must have a durable audit before it can report
            # success on a hosted backend; SQLite's artifact hook is a no-op.
            self._persist_artifacts(run_id)
            # Use the returned, authoritative episode states; a full watcher
            # queue is never a reason to lose triage or deep final progress.
            final_progress = dict(latest_observed)
            if result.triage is not None:
                final_progress["triage"] = safe_stage(result.triage)
            final_progress[result.state.mode] = safe_stage(result.state)
            final_progress["latest"] = result.state.mode
            # The immutable submission manifest is the source of truth for
            # effective settings, including after browser reconnection (#306).
            persisted = self.get(run_id)
            configuration = (
                None
                if persisted is None
                else persisted["requested"].get("effective_configuration")
            )
            final = {
                "status": "completed",
                "progress": final_progress,
                "mode": request.mode,
                "effective_configuration": configuration,
                "triage_execution": safe_executed_triage(triage),
                "investigation": safe_stage(result.state),
                "triage_report": report,
                "diagnosis": None
                if result.state.conclusion is None
                else result.state.conclusion.diagnosis[:1000],
                "recommendation": None
                if result.state.conclusion is None
                else result.state.conclusion.recommendation,
                "action_executed": result.state.action_started_tick is not None,
                "verification_outcome": None
                if result.state.verification is None
                else result.state.verification.outcome,
                "deep_ran": result.triage is not None
                and result.state is not result.triage,
                "review_count": len(result.desk.proposals()),
            }
            self._emit(run_id, "run.completed", final, state="completed")
        except Exception as error:
            flush_model_calls()
            finish_model_monitor(
                0 if policy is None else len(getattr(policy, "calls", ())),
                recorded_calls[0],
            )
            # Never persist exception messages: providers may include private details.
            try:
                self._emit(
                    run_id,
                    "run.failed",
                    {
                        "status": "failed",
                        "error_class": type(error).__name__,
                        "mode": request.mode,
                        "progress": {
                            **latest_observed,
                            "latest": "deep" if "deep" in latest_observed else "triage",
                        }
                        if latest_observed
                        else {},
                    },
                    state="failed",
                )
            except Exception:
                # An interrupted run is marked by the next exclusive owner.
                pass
        finally:
            if manual is not None and hasattr(manual, "close"):
                try:
                    manual.close()
                except Exception:
                    pass  # Cleanup failure must not change the recorded outcome.
            try:
                progress.put_nowait(None)
            except queue.Full:
                # The producer is shutting down: discard one stale intermediate
                # snapshot to ensure the publisher can receive its sentinel.
                try:
                    progress.get_nowait()
                    progress.task_done()
                    missed[0] += 1
                    progress.put_nowait(None)
                except queue.Empty:
                    pass
            with self.lock:
                self.active.discard(run_id)
