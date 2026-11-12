# One stored Siemens OPC UA reading, shaped by what the OPC UA server delivers.
# Responsibility: define the version 2 record shape; no I/O, no network, no
# interpretation of what a node means.
"""The version 2 lines a read-only OPC UA collector writes (S-0, SDC-03).

Version 1 (`record.py`) is shaped by MTConnect: every observation has an agent
`sequence` and `instance_id`, and its value is text. OPC UA has neither, so
this module does not pretend it does. A version 2 file holds two kinds of
line, told apart by `record_type`:

- `data_change` (an OpcUaDataChange): one value a monitored node reported,
  kept as the server's DataValue gave it: the value with its type, the
  StatusCode, the source and server timestamps. The collector adds only what
  OPC UA cannot know: when the value was received and on which connection.
- `opcua_session` (an OpcUaSessionMarker): the collector connected, is alive,
  stopped, or lost data.

Four rules hold for every line:

1. Nothing is invented. A timestamp the server did not send is None, not the
   collector's clock. There is no MTConnect-style sequence number.
2. A value is only a number when its status is Good. `number()` gives None
   for Bad and Uncertain values, for NaN and infinity, and for words and
   flags, so a value the server could not vouch for never becomes a zero or
   a healthy reading.
3. Every timestamp carries its timezone.
4. A node is named by its namespace URI, not its namespace index. A server
   may renumber its namespaces when it restarts; the URI does not change.

What a node means and what unit it is in live in the channel map, not here,
so this file only lists the value types the Siemens adapter needs. More types
are added to VALUE_RANGES and ValueType when a source needs them.
"""

import json
import math
from collections.abc import Iterable
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

Severity = Literal["good", "uncertain", "bad"]

ValueType = Literal[
    "Boolean",
    "SByte",
    "Byte",
    "Int16",
    "UInt16",
    "Int32",
    "UInt32",
    "Int64",
    "UInt64",
    "Float",
    "Double",
    "String",
]

# The inclusive range of each OPC UA whole-number type.
VALUE_RANGES: dict[str, tuple[int, int]] = {
    "SByte": (-(2**7), 2**7 - 1),
    "Byte": (0, 2**8 - 1),
    "Int16": (-(2**15), 2**15 - 1),
    "UInt16": (0, 2**16 - 1),
    "Int32": (-(2**31), 2**31 - 1),
    "UInt32": (0, 2**32 - 1),
    "Int64": (-(2**63), 2**63 - 1),
    "UInt64": (0, 2**64 - 1),
}
FLOAT_TYPES = frozenset({"Float", "Double"})

NonFinite = Literal["nan", "inf", "-inf"]

# In a StatusCode, the two highest bits give the severity; bits 10-11 equal
# to 01 say the low bits describe a data value, and bit 7 then means the
# server's queue for this node overflowed and older values were dropped.
SEVERITY_SHIFT = 30
DATA_VALUE_INFO = 0x0400
INFO_TYPE_MASK = 0x0C00
OVERFLOW_BIT = 0x0080


def severity_of(code: int) -> Severity:
    """Good, uncertain or bad, read from a StatusCode's two highest bits."""
    # Variables:
    #   code: The 32-bit OPC UA StatusCode.
    #   top: Its two highest bits: 0 good, 1 uncertain, 2 or 3 bad.
    top = code >> SEVERITY_SHIFT
    if top == 0:
        return "good"
    return "uncertain" if top == 1 else "bad"


class StatusInfo(BaseModel):
    """A value's OPC UA StatusCode, kept whole, with its severity spelled out."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   code: The full 32-bit StatusCode as the server sent it; 0 is Good.
    #   severity: Good, uncertain or bad. It must agree with the code, so a
    #     hand-edited line cannot call a Bad value good.
    #   name: The code's symbolic name when the client library knows it,
    #     e.g. "BadNoCommunication"; for people reading the file.
    code: int = Field(ge=0, le=2**32 - 1)
    severity: Severity
    name: str | None = None

    @model_validator(mode="after")
    def severity_matches_code(self):
        """Refuse a severity that disagrees with the code's top bits."""
        if self.severity != severity_of(self.code):
            raise ValueError(
                f"severity {self.severity!r} does not match status code "
                f"0x{self.code:08X} ({severity_of(self.code)})"
            )
        return self

    @property
    def overflow(self) -> bool:
        """True if the server dropped older values of this node before this one."""
        return (self.code & INFO_TYPE_MASK) == DATA_VALUE_INFO and bool(
            self.code & OVERFLOW_BIT
        )


def status_from_code(code: int, name: str | None = None) -> StatusInfo:
    """A StatusInfo whose severity is worked out from the code."""
    return StatusInfo(code=code, severity=severity_of(code), name=name)


class NodeRef(BaseModel):
    """Which node a value came from, in a form that survives a server restart."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   namespace_uri: The namespace's URI, not its index: the index (the 2
    #     in "ns=2;s=...") can change between sessions, the URI cannot.
    #   identifier: The node's id inside that namespace, as text, e.g. a
    #     SINUMERIK path. Case and brackets are kept exactly.
    #   identifier_type: Which kind of OPC UA identifier the text is.
    namespace_uri: str = Field(min_length=1)
    identifier: str = Field(min_length=1)
    identifier_type: Literal["string", "numeric", "guid", "opaque"] = "string"

    @property
    def key(self) -> tuple[str, str, str]:
        """The node as one hashable key, for grouping records by channel."""
        return (self.namespace_uri, self.identifier_type, self.identifier)


class OpcUaDataChange(BaseModel):
    """One value a monitored node reported, as the server's DataValue gave it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   record_type: Always "data_change"; tells this line from a marker.
    #   schema_version: Always 2; version 1 is the MTConnect record.
    #   source: Always "opcua"; the protocol the line came from.
    #   server_uri: The server's application URI, so values from two servers
    #     (CNC, PLC, a cell controller) never mix silently.
    #   node: The node the value came from.
    #   value: The value in its own type, as delivered, even when the status
    #     is Bad (kept as a record of what was sent, never as evidence).
    #     None when the server sent no value or the value was not finite.
    #   value_type: The value's OPC UA type; None only when value is None
    #     and no type was sent.
    #   non_finite: Set when the server sent NaN or infinity: which one.
    #     value is then None, because JSON cannot hold those numbers.
    #   status: The StatusCode that came with the value.
    #   source_timestamp: When the device says the value was observed; None
    #     if the server sent none.
    #   server_timestamp: When the server stamped it; None if not sent.
    #   received_at: When the collector received it, on its own clock.
    #   session_epoch: 1 for the collector's first connection, one more
    #     after every reconnect. Values from different epochs are not joined.
    #   subscription_id: The server's id for the subscription, when the
    #     value came from one; None for a single read.
    #   notification_seq: The subscription's own counter for the message the
    #     value arrived in. A jump means messages were missed. It restarts
    #     with each subscription, so it is not a file-wide sequence.
    record_type: Literal["data_change"] = "data_change"
    schema_version: Literal[2] = 2
    source: Literal["opcua"] = "opcua"
    server_uri: str = Field(min_length=1)
    node: NodeRef
    value: StrictBool | StrictInt | StrictFloat | StrictStr | None
    value_type: ValueType | None
    non_finite: NonFinite | None = None
    status: StatusInfo
    source_timestamp: AwareDatetime | None
    server_timestamp: AwareDatetime | None
    received_at: AwareDatetime
    session_epoch: int = Field(ge=1)
    subscription_id: int | None = Field(default=None, ge=0)
    notification_seq: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def value_fits_its_type(self):
        """Refuse a value that is not what its declared type says."""
        # Variables:
        #   kind: The declared OPC UA type.
        #   value: The stored value, checked against that type.
        kind, value = self.value_type, self.value
        if self.non_finite is not None:
            if kind not in FLOAT_TYPES or value is not None:
                raise ValueError(
                    "non_finite needs a Float or Double type and a None value"
                )
            return self
        if value is None:
            return self
        if kind is None:
            raise ValueError("a value needs its value_type")
        if kind == "Boolean":
            ok = isinstance(value, bool)
        elif kind == "String":
            ok = isinstance(value, str)
        elif kind in FLOAT_TYPES:
            ok = isinstance(value, float) and math.isfinite(value)
        else:
            low, high = VALUE_RANGES[kind]
            ok = (
                isinstance(value, int)
                and not isinstance(value, bool)
                and low <= value <= high
            )
        if not ok:
            raise ValueError(f"value {value!r} is not a valid {kind}")
        return self

    def number(self, allow_uncertain: bool = False) -> float | None:
        """The value as a float, or None if it may not be used as a number.

        None for a Bad status, for an Uncertain one unless the caller allows
        it, for a missing or non-finite value, and for words and flags.
        """
        # Variables:
        #   allow_uncertain: True to accept Uncertain values; a caller sets
        #     it only where a doubtful reading is still wanted.
        #   accepted: The severities this call treats as usable.
        accepted = ("good", "uncertain") if allow_uncertain else ("good",)
        if self.status.severity not in accepted:
            return None
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            return None
        return float(self.value)


def data_change(
    *,
    server_uri: str,
    node: NodeRef,
    value: bool | int | float | str | None,
    value_type: ValueType | None,
    status_code: int,
    status_name: str | None = None,
    source_timestamp,
    server_timestamp,
    received_at,
    session_epoch: int,
    subscription_id: int | None = None,
    notification_seq: int | None = None,
) -> OpcUaDataChange:
    """Build a record from one delivered value, moving NaN/infinity aside."""
    # Variables:
    #   value: The value as the client library decoded it.
    #   non_finite: Which non-finite number it was, if any; the stored value
    #     is then None so the line stays valid JSON.
    #   whole: True for a Float/Double that arrived as a whole number (5
    #     rather than 5.0), which is stored as a float.
    non_finite: NonFinite | None = None
    whole = isinstance(value, int) and not isinstance(value, bool)
    if value_type in FLOAT_TYPES and whole:
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        non_finite = "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
        value = None
    return OpcUaDataChange(
        server_uri=server_uri,
        node=node,
        value=value,
        value_type=value_type,
        non_finite=non_finite,
        status=status_from_code(status_code, status_name),
        source_timestamp=source_timestamp,
        server_timestamp=server_timestamp,
        received_at=received_at,
        session_epoch=session_epoch,
        subscription_id=subscription_id,
        notification_seq=notification_seq,
    )


OpcUaGapCause = Literal[
    "session_lost",
    "subscription_lost",
    "notification_missed",
    "queue_overflow",
    "server_restart",
]


class OpcUaGap(BaseModel):
    """Where and why values were lost, as far as the collector can know it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   cause: session_lost (the connection dropped), subscription_lost (the
    #     server ended the subscription), notification_missed (its counter
    #     jumped), queue_overflow (the server dropped values of a node) or
    #     server_restart (the server came back as a new run).
    #   subscription_id: The subscription affected, when the loss is in one.
    #   node: The node affected, for a queue overflow; None when the loss
    #     covers every node.
    #   lost_from_seq, lost_to_seq: The notification counters missed,
    #     inclusive, when the cause is a jump; otherwise None.
    #   last_received_at: When the last value before the loss was received;
    #     None if none had been. With the marker's `at` it bounds the gap.
    cause: OpcUaGapCause
    subscription_id: int | None = Field(default=None, ge=0)
    node: NodeRef | None = None
    lost_from_seq: int | None = Field(default=None, ge=0)
    lost_to_seq: int | None = Field(default=None, ge=0)
    last_received_at: AwareDatetime | None = None


class OpcUaSessionMarker(BaseModel):
    """A line saying the collector connected, is alive, stopped, or lost data.

    A heartbeat is written when the connection is up but no value has
    changed, so silence in the file means the collector or its connection is
    down, not that the machine is idle. A crash writes nothing, so a
    `connected` line not preceded by `stopped` or `disconnected` means the
    previous run did not end cleanly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   record_type: Always "opcua_session"; tells this line from a value.
    #   server_uri: The server the collector was reading.
    #   event: "connected" when a session opens, "heartbeat" when it is
    #     alive with nothing new, "disconnected" when the session ends
    #     without being asked to, "stopped" when the collector ends on
    #     purpose, "gap" when values were lost just before this line.
    #   at: The collector's clock when the event happened.
    #   session_epoch: The connection the event belongs to; a `connected`
    #     line carries the new epoch.
    #   reason: Why, in words, e.g. "interrupted" or the error's name.
    #   gap: For a gap only: what was lost and why.
    record_type: Literal["opcua_session"] = "opcua_session"
    schema_version: Literal[2] = 2
    source: Literal["opcua"] = "opcua"
    server_uri: str = Field(min_length=1)
    event: Literal["connected", "heartbeat", "disconnected", "stopped", "gap"]
    at: AwareDatetime
    session_epoch: int = Field(ge=1)
    reason: str | None = None
    gap: OpcUaGap | None = None

    @model_validator(mode="after")
    def gap_detail_only_on_a_gap(self):
        """Refuse a gap with no detail, or detail on any other marker."""
        if (self.event == "gap") != (self.gap is not None):
            raise ValueError("a gap marker, and only a gap marker, carries gap")
        return self


OpcUaLine = OpcUaDataChange | OpcUaSessionMarker


def parse_opcua_line(text: str) -> OpcUaLine:
    """Read one version 2 JSONL line as a value or a session marker.

    Raises pydantic.ValidationError, or ValueError for bad JSON or for a line
    that is not a version 2 OPC UA line (a version 1 MTConnect line is
    refused here rather than read as something it is not).
    """
    # Variables:
    #   text: One line of the capture file, without its newline.
    #   data: The line's JSON object.
    #   kind: The line's record_type, which picks the model.
    data = json.loads(text)
    kind = data.get("record_type") if isinstance(data, dict) else None
    if kind == "data_change":
        return OpcUaDataChange.model_validate(data)
    if kind == "opcua_session":
        return OpcUaSessionMarker.model_validate(data)
    raise ValueError(f"not a version 2 OPC UA line: record_type {kind!r}")


def to_json_line(line: OpcUaLine) -> str:
    """One line of JSON for the capture file, without a newline."""
    return line.model_dump_json()


def continuous_runs(lines: Iterable[OpcUaLine]) -> list[list[OpcUaDataChange]]:
    """The values split wherever collection was broken, in file order.

    A run ends at a `gap`, `connected` or `disconnected` marker, and where
    the session epoch changes between two values even if the marker between
    them is missing (a crash writes none). Anything computed over values,
    such as a mean or a slope, should stay inside one run so it never joins
    two values across time that was not collected. Empty runs are left out.

    A queue-overflow gap names one node but still ends the run for all of
    them: the split is deliberately the cautious one.
    """
    # Variables:
    #   runs: The finished runs.
    #   current: Values since the last break.
    runs: list[list[OpcUaDataChange]] = []
    current: list[OpcUaDataChange] = []
    for line in lines:
        if isinstance(line, OpcUaSessionMarker):
            if line.event in ("gap", "connected", "disconnected") and current:
                runs.append(current)
                current = []
            continue
        if current and current[-1].session_epoch != line.session_epoch:
            runs.append(current)
            current = []
        current.append(line)
    if current:
        runs.append(current)
    return runs
