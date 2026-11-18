"""Validated, offline Haas NGC connection authorization (no network I/O).

This is a preflight configuration boundary, not proof that the shop granted
permission or that the actual CNC accepts MTConnect requests. The technician
must confirm machine identity and endpoint before enabling the collector.
"""

from __future__ import annotations

import hashlib
import re
from ipaddress import IPv4Address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HaasConnectionProfile(BaseModel):
    """Explicit single-controller MTConnect endpoint and acquisition scope.

    The profile is immutable and deliberately does not discover controllers or
    accept arbitrary URLs. Its URL is an operator-approved *candidate* only.
    Actual /probe identity and field validation must happen before recording.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    controller_family: Literal["NGC"]
    controller_software: str = Field(min_length=1, max_length=80)
    machine_model: str = Field(min_length=1, max_length=80)
    machine_identity: str = Field(min_length=1, max_length=128)
    approved_ip: IPv4Address
    endpoint_device: str = Field(min_length=1, max_length=80)
    port: Literal[8082] = 8082
    acquisition_scope: Literal["full_agent_stream", "shop_filtered_gateway"]
    full_stream_approved: bool = False
    authorization_reference: str = Field(min_length=1, max_length=256)
    approved_by: str = Field(min_length=1, max_length=128)
    poll_seconds: float = Field(ge=1.0, le=3600.0, allow_inf_nan=False)

    @field_validator(
        "controller_software",
        "machine_model",
        "machine_identity",
        "authorization_reference",
        "approved_by",
    )
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        """Reject whitespace-only identifiers without logging their content."""
        if not value.strip() or value != value.strip():
            raise ValueError("a nonempty, trimmed value is required")
        return value

    @field_validator("endpoint_device")
    @classmethod
    def literal_single_device_segment(cls, value: str) -> str:
        """No slash, query, encoding or path traversal in an approved device."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
            raise ValueError("endpoint_device must be one literal device segment")
        if value in {".", ".."}:
            raise ValueError("endpoint_device cannot be a path traversal segment")
        return value

    @field_validator("approved_ip")
    @classmethod
    def unicast_machine_address(cls, value: IPv4Address) -> IPv4Address:
        if value.is_unspecified or value.is_multicast or value.is_loopback:
            raise ValueError("approved_ip must be an approved unicast machine address")
        return value

    @model_validator(mode="after")
    def require_full_reply_permission(self) -> "HaasConnectionProfile":
        if self.acquisition_scope == "full_agent_stream" and not self.full_stream_approved:
            raise ValueError("full MTConnect replies require explicit full-stream approval")
        return self

    @property
    def base_url(self) -> str:
        """A fixed on-site HTTP endpoint; no arbitrary user-supplied URL."""
        return f"http://{self.approved_ip}:{self.port}/{self.endpoint_device}"

    @property
    def endpoint_fingerprint(self) -> str:
        """Safe correlation ID: never log raw shop IP or program data."""
        return hashlib.sha256(self.base_url.encode("ascii")).hexdigest()[:20]
