"""Strict, versioned Siemens-to-cloud contracts. No network or model calls."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from capstone.ingestion.siemens_opcua_record import (
    NodeRef,
    OpcUaDataChange,
    OpcUaSessionMarker,
)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SHA = re.compile(r"^[a-f0-9]{64}$")


class ApprovedNode(BaseModel):
    """A specifically authorized OPC UA node, not a broad machine permission."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    node: NodeRef
    permit_numeric_analysis: bool = False
    permit_text: bool = False
    retain_value: bool = True
    unit: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def valid_permission(self):
        if self.permit_numeric_analysis and (
            not self.retain_value or not self.unit
        ):
            raise ValueError("numeric analysis requires authorized value and units")
        if self.permit_text and not self.retain_value:
            raise ValueError("text approval requires authorized value retention")
        return self


class CloudScope(BaseModel):
    """Local, operator-reviewed approval also enforced on Render before storage.

    This is not itself proof of consent: the referenced signed approval must
    be checked by a named human before deployment. Reloaded on every request
    so withdrawal or expiry is not silently cached.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    site_id: str
    machine_id: str
    server_uri: str = Field(min_length=1, max_length=300)
    controller_fingerprint: str = Field(min_length=8, max_length=180)
    source_profile_revision: str = Field(min_length=1, max_length=64)
    approval_reference: str = Field(min_length=8, max_length=180)
    approved_by: str = Field(min_length=2, max_length=120)
    expires_at: AwareDatetime
    retention_days: int = Field(ge=1, le=365)
    max_sample_age_seconds: int | None = Field(default=None, ge=1, le=3600)
    nodes: tuple[ApprovedNode, ...] = Field(min_length=1, max_length=100)
    cloud_transfer_approved: bool = False

    @field_validator("site_id", "machine_id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("invalid site or machine identifier")
        return value

    @model_validator(mode="after")
    def unique_nodes(self):
        keys = [item.node.key for item in self.nodes]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate approved node")
        return self

    def assert_active(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if not self.cloud_transfer_approved or self.expires_at <= now:
            raise PermissionError("cloud export permission missing or expired")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            self.model_dump_json(exclude_none=True).encode("utf-8")
        ).hexdigest()

    def approved(self, node: NodeRef) -> ApprovedNode:
        for entry in self.nodes:
            if node.key == entry.node.key:
                return entry
        raise PermissionError("unapproved OPC UA node")


def validate_record(scope: CloudScope, raw: dict[str, Any]) -> dict[str, Any]:
    """Refuse unknown, sensitive or malformed data *before* HTTP and DB writes.

    Never turn a bad/uncertain/stale value into accepted numeric evidence.
    Free-text marker reasons are removed; no field is guessed or coerced.
    """
    if not isinstance(raw, dict) or raw.get("schema_version") != 2:
        raise ValueError("only Siemens OPC UA schema v2 is authorized")
    if raw.get("record_type") == "data_change":
        record = OpcUaDataChange.model_validate(
            {k: v for k, v in raw.items() if k not in ("analysis_eligible", "verified_unit")}
        )
        if record.server_uri != scope.server_uri:
            raise PermissionError("OPC UA server identity changed")
        permission = scope.approved(record.node)
        if record.value is not None and not permission.retain_value:
            raise PermissionError("value retention not approved")
        if record.value_type == "String" and not permission.permit_text:
            raise PermissionError("sensitive text retention not approved")
        payload = record.model_dump(mode="json")
        lag_seconds = (
            (record.received_at - record.source_timestamp).total_seconds()
            if record.source_timestamp is not None else None
        )
        eligible = (
            permission.permit_numeric_analysis
            and scope.max_sample_age_seconds is not None
            and lag_seconds is not None
            and 0 <= lag_seconds <= scope.max_sample_age_seconds
            and record.number() is not None
            and record.source_timestamp is not None
            and record.source_timestamp <= record.received_at
            and record.status.severity == "good"
            and not record.status.overflow
        )
        payload["analysis_eligible"] = bool(eligible)
        payload["verified_unit"] = permission.unit if eligible else None
        return payload
    if raw.get("record_type") == "opcua_session":
        record = OpcUaSessionMarker.model_validate(
            {k: v for k, v in raw.items() if k not in ("analysis_eligible", "verified_unit")}
        )
        if record.server_uri != scope.server_uri:
            raise PermissionError("OPC UA server identity changed")
        if record.gap is not None and record.gap.node is not None:
            scope.approved(record.gap.node)
        payload = record.model_dump(mode="json")
        payload["reason"] = None  # Free-form text may reveal machine/program data.
        payload["analysis_eligible"] = False
        return payload
    raise ValueError("unsupported OPC UA record type")


def scope_from_file(path: Path) -> CloudScope:
    """Reload current approval every batch to honor revocation/expiry."""
    try:
        if not path.is_absolute() or path.stat().st_size > 32_768:
            raise ValueError
        return CloudScope.model_validate_json(path.read_bytes())
    except (OSError, ValueError):
        raise RuntimeError("Approved Siemens source profile unavailable") from None


class IngestBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    site_id: str
    machine_id: str
    stream_id: UUID
    first_line: int = Field(ge=0)
    records: list[dict[str, Any]] = Field(min_length=1, max_length=64)
    digest: str

    @field_validator("digest")
    @classmethod
    def digest_format(cls, value: str) -> str:
        if not SHA.fullmatch(value):
            raise ValueError("invalid digest")
        return value

    @property
    def computed_digest(self) -> str:
        fields = self.model_dump(mode="json", exclude={"digest"})
        return hashlib.sha256(
            json.dumps(
                fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def build(
        cls, *, scope: CloudScope, stream_id: UUID, first_line: int,
        records: list[dict[str, Any]],
    ) -> "IngestBatch":
        raw = dict(
            schema_version=1,
            site_id=scope.site_id,
            machine_id=scope.machine_id,
            stream_id=stream_id,
            first_line=first_line,
            records=records,
            digest="0" * 64,
        )
        batch = cls.model_validate(raw)
        return batch.model_copy(update={"digest": batch.computed_digest})

    def authorized_lines(self, scope: CloudScope) -> list[dict[str, Any]]:
        scope.assert_active()
        if (self.site_id, self.machine_id) != (scope.site_id, scope.machine_id):
            raise PermissionError("site/machine scope mismatch")
        if self.computed_digest != self.digest:
            raise ValueError("batch payload digest mismatch")
        rows = [validate_record(scope, line) for line in self.records]
        if rows != self.records:
            # Uplink must have minimized data before cloud transfer.
            raise ValueError("batch contains unminimized or inconsistent records")
        return rows
