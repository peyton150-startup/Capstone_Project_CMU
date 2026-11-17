"""Safe source-contract inventory for hosted FastAPI/worker integration.

This is code-surface readiness, not deployment health, provider availability,
data correctness, or a claim that a two-service staging smoke test passed.
No environment values, graph state, errors, credentials or raw model data.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MissingContract = Literal[
    "stage_progress", "decide_trace", "deep_lifecycle",
    "deterministic_profile", "model_attempts",
]


class HostedIntegrationStatus(BaseModel):
    """Bounded, read-only compatibility flags from actual source contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1] = 1
    stage_progress: bool
    decide_trace: bool
    deep_lifecycle: bool
    deterministic_profile: bool
    model_attempts: bool
    source_contracts_complete: bool
    missing: list[MissingContract] = Field(max_length=5)


def inspect_hosted_contracts() -> HostedIntegrationStatus:
    """Inspect source-owned Pydantic models; never try to run an agent."""
    from capstone.api import runs
    from capstone.api.model_calls import SafeModelCall
    from capstone.settings import Settings

    stage = getattr(runs, "SafeStageSnapshot", None)
    fields = getattr(stage, "model_fields", {})
    if not isinstance(fields, dict):
        fields = {}
    states = {
        "stage_progress": {
            "investigation_id", "requirement_statuses", "triage_decide_reads",
        }.issubset(fields),
        "decide_trace": {
            "decide_event_total", "decide_events_recent",
        }.issubset(fields),
        "deep_lifecycle": {
            "deep_signals", "deep_checkpoints_recent",
        }.issubset(fields),
        "deterministic_profile": (
            hasattr(Settings, "effective_triage")
            and "triage_run_mode" in Settings.model_fields
        ),
        "model_attempts": {
            "job", "attempts", "outcome",
        }.issubset(SafeModelCall.model_fields),
    }
    missing = [name for name, available in states.items() if not available]
    return HostedIntegrationStatus(
        **states,
        source_contracts_complete=not missing,
        missing=missing,
    )
