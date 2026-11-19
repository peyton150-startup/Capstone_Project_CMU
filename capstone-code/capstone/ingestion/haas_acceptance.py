"""Offline readiness gate for a single authorized Haas read-only capture.

Human claims in this checklist are self-reported. A passing result does not
prove that a technician actually signed off or that a physical VF-4 is safe.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HaasAcceptanceEvidence(BaseModel):
    """Versioned, explicitly documented evidence for each pilot readiness gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    machine_identity: str = Field(min_length=1)
    authorization_reference: str = Field(min_length=1)
    approved_scope_verified: bool = False
    endpoint_identity_verified: bool = False
    probe_matches_map: bool = False
    source_timestamps_qualified: bool = False
    signal_units_qualified: bool = False
    detector_calibration_qualified: bool = False
    offline_replay_tests_passed: bool = False
    collector_restart_test_passed: bool = False
    no_machine_writes_verified: bool = False
    physical_connection_verified: bool = False
    technician_signed_off: bool = False

    @model_validator(mode="after")
    def no_blank_private_references(self) -> "HaasAcceptanceEvidence":
        if (
            not self.machine_identity.strip()
            or not self.authorization_reference.strip()
        ):
            raise ValueError("identity and approval evidence cannot be blank")
        return self


class HaasAcceptanceReport(BaseModel):
    """Conservative readiness verdict with actionable missing gate names."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["blocked", "offline_qualified", "field_qualified"]
    missing: tuple[str, ...]
    note: str = (
        "Self-reported checklist; human authorization and machine behavior "
        "must be independently verified."
    )


_OFFLINE_GATES = (
    "approved_scope_verified",
    "endpoint_identity_verified",
    "probe_matches_map",
    "source_timestamps_qualified",
    "signal_units_qualified",
    "detector_calibration_qualified",
    "offline_replay_tests_passed",
    "collector_restart_test_passed",
    "no_machine_writes_verified",
)
_FIELD_GATES = ("physical_connection_verified", "technician_signed_off")


def assess_haas_field_readiness(
    evidence: HaasAcceptanceEvidence,
) -> HaasAcceptanceReport:
    """Do not report field readiness until every required gate is supported."""
    # Variables:
    #   evidence: The self-reported checklist; a gate counts only when it is
    #     exactly True.
    #   missing: Every offline and field gate not yet supported, in order, so
    #     the report says what to do next.
    #   status: field_qualified only with nothing missing; offline_qualified
    #     when every offline gate passed but a field gate did not; else blocked.
    missing = tuple(
        name
        for name in (*_OFFLINE_GATES, *_FIELD_GATES)
        if getattr(evidence, name) is not True
    )
    status: Literal["blocked", "offline_qualified", "field_qualified"] = (
        "field_qualified"
        if not missing
        else "offline_qualified"
        if all(getattr(evidence, name) is True for name in _OFFLINE_GATES)
        else "blocked"
    )
    return HaasAcceptanceReport(status=status, missing=missing)
