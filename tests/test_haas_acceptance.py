"""No live controller is contacted by this acceptance-gate test."""

from pydantic import ValidationError
import pytest

from capstone.ingestion.haas_acceptance import (
    HaasAcceptanceEvidence,
    assess_haas_field_readiness,
)


def evidence(**kwargs):
    return HaasAcceptanceEvidence.model_validate(
        {
            "machine_identity": "VF4-APPROVED",
            "authorization_reference": "private-shop-approval-reference",
            **kwargs,
        }
    )


def test_empty_checklist_is_blocked():
    result = assess_haas_field_readiness(evidence())
    assert result.status == "blocked"
    assert "approved_scope_verified" in result.missing


def test_offline_success_is_never_field_success():
    offline = {key: True for key in (
        "approved_scope_verified",
        "endpoint_identity_verified",
        "probe_matches_map",
        "source_timestamps_qualified",
        "signal_units_qualified",
        "detector_calibration_qualified",
        "offline_replay_tests_passed",
        "collector_restart_test_passed",
        "no_machine_writes_verified",
    )}
    result = assess_haas_field_readiness(evidence(**offline))
    assert result.status == "offline_qualified"
    assert result.missing == ("physical_connection_verified", "technician_signed_off")


def test_field_acceptance_requires_every_gate():
    complete = {key: True for key, value in evidence().model_dump().items() if type(value) is bool}
    outcome = assess_haas_field_readiness(evidence(**complete))
    assert outcome.status == "field_qualified"
    assert outcome.missing == ()


def test_missing_or_unknown_private_reference_rejected():
    with pytest.raises(ValidationError):
        evidence(authorization_reference="  ")
    with pytest.raises(ValidationError):
        evidence(injected_config=True)
