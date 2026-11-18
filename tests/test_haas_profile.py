"""Offline policy tests; never contact a CNC controller."""

import pytest
from pydantic import ValidationError

from capstone.ingestion.haas_profile import HaasConnectionProfile


def profile(**changes):
    values = {
        "controller_family": "NGC",
        "controller_software": "100.24.000.1200",
        "machine_model": "VF-4",
        "machine_identity": "APPROVED-VF4",
        "approved_ip": "192.168.10.4",
        "endpoint_device": "VF-4",
        "acquisition_scope": "full_agent_stream",
        "full_stream_approved": True,
        "authorization_reference": "approved-paperwork-reference",
        "approved_by": "shop-ot-contact",
        "poll_seconds": 5.0,
    }
    values.update(changes)
    return HaasConnectionProfile.model_validate(values)


def test_approved_profile_builds_one_literal_agent_url():
    approved = profile()
    assert approved.base_url == "http://192.168.10.4:8082/VF-4"
    assert len(approved.endpoint_fingerprint) == 20
    assert "192.168." not in approved.endpoint_fingerprint
    with pytest.raises(ValidationError):
        approved.port = 1234


@pytest.mark.parametrize("device", ["../x", "VF-4/other", "%2e%2e", "VF-4?count=1", ""])
def test_device_path_cannot_expand_requests(device):
    with pytest.raises(ValidationError):
        profile(endpoint_device=device)


@pytest.mark.parametrize("ip", ["127.0.0.1", "0.0.0.0", "224.0.0.1"])
def test_rejects_non_machine_targets(ip):
    with pytest.raises(ValidationError):
        profile(approved_ip=ip)


def test_no_unapproved_full_stream_reads():
    with pytest.raises(ValidationError, match="full-stream approval"):
        profile(full_stream_approved=False)


def test_filtered_gateway_is_distinct_from_full_stream_authorization():
    approved = profile(
        acquisition_scope="shop_filtered_gateway",
        full_stream_approved=False,
    )
    assert approved.acquisition_scope == "shop_filtered_gateway"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.5])
def test_rejects_invalid_or_unsafe_poll_intervals(bad):
    with pytest.raises(ValidationError):
        profile(poll_seconds=bad)


def test_refuses_missing_permissions_and_extra_keys():
    with pytest.raises(ValidationError):
        profile(authorization_reference=" ")
    with pytest.raises(ValidationError):
        profile(unknown_field="anything")
