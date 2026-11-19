"""Typed, opt-in mapping of approved MTConnect events to triage events.

The adapter does not assert a root cause or simulate jobs/inspection/settings.
Actual provider registration remains gated on a qualified capture and source.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from capstone.contracts.observations import EventObservation
from capstone.ingestion.channel_map import ChannelMap, disagreement
from capstone.ingestion.record import TelemetryRecord

EventRefusal = Literal[
    "not_authorized",
    "unmapped",
    "wrong_type",
    "unknown_state",
    "invalid_time",
    "invalid_epoch",
    "invalid_sequence",
]


class NormalizedMTConnectEvent(BaseModel):
    """EventObservation with source/sequence retained for evidence provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event: EventObservation
    source: str
    source_epoch: str = Field(min_length=1)
    data_item_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    source_timestamp: AwareDatetime
    received_at: AwareDatetime
    mapping_revision: str = Field(pattern=r"^[a-f0-9]{64}$")


class EventAdmission(BaseModel):
    """Exactly one admitted event or a stable, safe refusal reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: NormalizedMTConnectEvent | None = None
    reason: EventRefusal | None = None

    @model_validator(mode="after")
    def exclusive(self) -> "EventAdmission":
        if (self.value is None) == (self.reason is None):
            raise ValueError("event admission requires either an event or refusal")
        return self


def qualify_event(
    record: TelemetryRecord,
    channel_map: ChannelMap,
    *,
    approved_item_ids: frozenset[str],
    tick: int,
) -> EventAdmission:
    """Safely translate only whitelisted controller states and alarm levels.

    Neither arbitrary machine text nor a native controller alarm code is put
    into the generic triage message. They remain in separately protected raw
    capture records and must never be added to metadata-only logs.
    """
    # Variables:
    #   approved_item_ids: Event data items a person approved; others are
    #     refused before anything else is read.
    #   entry: The probe's description of this data item, which must agree
    #     with the record's category and type.
    #   kind, message: The triage event built only from a fixed list of
    #     controller states and condition levels, never from machine text.
    #   severity: "warning" or "fault" for a condition alarm, so the two
    #     levels stay apart although both are kind "alarm"; None otherwise.
    if record.data_item_id not in approved_item_ids:
        return EventAdmission(reason="not_authorized")
    entry = channel_map.entry_for(record)
    if entry is None:
        return EventAdmission(reason="unmapped")
    if disagreement(entry, record):
        return EventAdmission(reason="wrong_type")
    if record.sequence < 1 or tick < 0:
        return EventAdmission(reason="invalid_sequence")
    if not record.instance_id:
        return EventAdmission(reason="invalid_epoch")
    if (
        record.source_timestamp.utcoffset() is None
        or record.received_at.utcoffset() is None
    ):
        return EventAdmission(reason="invalid_time")

    kind: str
    message: str
    severity: Literal["warning", "fault"] | None = None
    if record.category == "EVENT" and entry.type == "EXECUTION":
        allowed_states = {
            "ACTIVE",
            "READY",
            "INTERRUPTED",
            "STOPPED",
            "OPTIONAL_STOP",
            "PROGRAM_STOPPED",
        }
        # UNAVAILABLE is not listed: an unavailable record is refused by the
        # `record.available` check below before its value is read.
        if not record.available or record.value not in allowed_states:
            return EventAdmission(reason="unknown_state")
        kind = "status"
        message = f"MTConnect execution {record.value}"
    elif record.category == "CONDITION":
        levels = {
            "FAULT": "alarm",
            "WARNING": "alarm",
            "NORMAL": "condition_clear",
        }
        if not record.available or record.value not in levels:
            return EventAdmission(reason="unknown_state")
        kind = levels[record.value]
        message = f"MTConnect condition {record.value}"
        if record.value in ("WARNING", "FAULT"):
            severity = "warning" if record.value == "WARNING" else "fault"
    else:
        return EventAdmission(reason="wrong_type")

    return EventAdmission(
        value=NormalizedMTConnectEvent(
            event=EventObservation(
                tick=tick,
                machine_id=entry.device,
                kind=kind,
                message=message,
                job_id=None,
                severity=severity,
            ),
            source=record.source,
            source_epoch=record.instance_id,
            data_item_id=record.data_item_id,
            sequence=record.sequence,
            source_timestamp=record.source_timestamp,
            received_at=record.received_at,
            mapping_revision=channel_map.probe_sha256,
        )
    )
