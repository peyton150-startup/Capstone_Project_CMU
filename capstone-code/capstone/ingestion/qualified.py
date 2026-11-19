"""Pydantic qualification of one MTConnect numeric observation.

This boundary never guesses units or converts unavailable to zero. It is a
building block for an approved real-machine detector, not the detector itself.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from capstone.ingestion.channel_map import ChannelMap, _disagreement
from capstone.ingestion.record import TelemetryRecord

RejectReason = Literal[
    "not_authorized",
    "unmapped",
    "wrong_shape",
    "unavailable",
    "non_numeric",
    "nonfinite",
    "unit_unstated",
    "epoch_missing",
    "timestamp_untrusted",
    "invalid_sequence",
]


class QualifiedNumericObservation(BaseModel):
    """One accepted, traceable numeric MTConnect SAMPLE, with probe-stated unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    instance_id: str = Field(min_length=1)
    device: str = Field(min_length=1)
    component: str
    data_item_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    timestamp: AwareDatetime
    received_at: AwareDatetime
    value: float = Field(allow_inf_nan=False)
    units: str = Field(min_length=1)
    probe_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Qualification(BaseModel):
    """Exactly one accepted sample or a safe rejection reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sample: QualifiedNumericObservation | None = None
    reason: RejectReason | None = None

    @model_validator(mode="after")
    def exclusive_verdict(self) -> "Qualification":
        if (self.sample is None) == (self.reason is None):
            raise ValueError("qualification must contain exactly one sample or reason")
        return self

    @property
    def accepted(self) -> bool:
        return self.sample is not None


def qualify_numeric(
    record: TelemetryRecord,
    channel_map: ChannelMap,
    *,
    authorized_item_ids: frozenset[str],
) -> Qualification:
    """Check an observation before allowing a detector or tool to consume it.

    The caller must first establish that the whole MTConnect reply was
    authorized to acquire; this function is NOT a network privacy filter.
    """
    # Variables:
    #   authorized_item_ids: The data items a person approved for analysis;
    #     anything else is refused first, before any other check.
    #   entry: The probe's description of this data item (type, units,
    #     device); None means the probe never listed it.
    #   value: The reading as a finite number; any other text is refused,
    #     never guessed or treated as zero.
    if record.data_item_id not in authorized_item_ids:
        return Qualification(reason="not_authorized")
    entry = channel_map.entry_for(record)
    if entry is None:
        return Qualification(reason="unmapped")
    if record.category != "SAMPLE" or _disagreement(entry, record):
        return Qualification(reason="wrong_shape")
    if not record.available or record.value is None:
        return Qualification(reason="unavailable")
    try:
        value = float(record.value)
    except (TypeError, ValueError):
        return Qualification(reason="non_numeric")
    if not math.isfinite(value):
        return Qualification(reason="nonfinite")
    if not entry.units or not entry.units.strip():
        return Qualification(reason="unit_unstated")
    if not record.instance_id:
        return Qualification(reason="epoch_missing")
    if record.sequence < 1:
        return Qualification(reason="invalid_sequence")
    if (
        not isinstance(record.source_timestamp, datetime)
        or record.source_timestamp.utcoffset() is None
        or record.received_at.utcoffset() is None
    ):
        return Qualification(reason="timestamp_untrusted")
    return Qualification(
        sample=QualifiedNumericObservation(
            source=record.source,
            instance_id=record.instance_id,
            device=entry.device,
            component=entry.component,
            data_item_id=entry.data_item_id,
            sequence=record.sequence,
            timestamp=record.source_timestamp,
            received_at=record.received_at,
            value=value,
            units=entry.units,
            probe_sha256=channel_map.probe_sha256,
        )
    )
