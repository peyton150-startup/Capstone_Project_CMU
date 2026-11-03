# Parses MTConnect agent responses into telemetry records.
# Responsibility: XML in, records out; no network access and no interpretation.
"""Parse MTConnectStreams and MTConnectError documents.

Shape checked against a live agent (demo.mtconnect.org, MTConnect 2.8):

    MTConnectStreams
      Header  instanceId, nextSequence, firstSequence, lastSequence
      Streams
        DeviceStream  name, uuid
          ComponentStream  component, name, componentId
            Samples | Events   <SpindleSpeed dataItemId=.. sequence=.. timestamp=..>1200</..>
            Condition          <Normal|Warning|Fault|Unavailable dataItemId=.. type=..>text</..>

Elements are matched by local name so that any schema version (1.x or 2.x
namespace) parses the same way. A value of UNAVAILABLE, or a condition
<Unavailable/>, becomes a record with available=False and value=None.
"""

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

from capstone.ingestion.record import Category, TelemetryRecord

UNAVAILABLE = "UNAVAILABLE"

_SECTIONS: dict[str, Category] = {
    "Samples": "SAMPLE",
    "Events": "EVENT",
    "Condition": "CONDITION",
}


class MTConnectError(Exception):
    """The agent answered with an MTConnectError document (e.g. OUT_OF_RANGE)."""

    def __init__(self, codes: list[str], message: str) -> None:
        # Variables:
        #   codes: The agent's error codes, e.g. ["OUT_OF_RANGE"]; the collector
        #     uses them to decide how to recover.
        super().__init__(message)
        self.codes = codes


@dataclass(frozen=True)
class StreamsDocument:
    """One parsed MTConnectStreams response: its header and its records."""

    # Variables:
    #   instance_id: The agent's run id; a change means it restarted.
    #   next_sequence: Where the next /sample request should start.
    #   first_sequence: The oldest sequence the agent still holds; data before
    #     it is gone.
    #   last_sequence: The newest sequence the agent holds; if next_sequence is
    #     not past it, more data is waiting.
    instance_id: str | None
    next_sequence: int
    first_sequence: int
    last_sequence: int
    records: list[TelemetryRecord] = field(default_factory=list)


def _local(tag: str) -> str:
    """The element name without its XML namespace."""
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    """The first direct child with this local name, if any."""
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _value(element: ET.Element) -> str | None:
    """An observation's value as text: plain text, or JSON for DataSet entries."""
    entries = [child for child in element if _local(child.tag) == "Entry"]
    if entries:
        return json.dumps(
            {entry.get("key", ""): (entry.text or "").strip() for entry in entries},
            sort_keys=True,
        )
    text = (element.text or "").strip()
    return text or None


def raise_if_error(root: ET.Element) -> None:
    """Raise MTConnectError if this is an error document (1.x or 2.x form)."""
    if _local(root.tag) != "MTConnectError":
        return
    # Variables:
    #   codes: Every errorCode attribute found. 1.x writes <Error errorCode=..>,
    #     2.x writes a named element such as <OutOfRange errorCode=..>.
    codes: list[str] = []
    texts: list[str] = []
    errors = _child(root, "Errors")
    for error in errors if errors is not None else []:
        codes.append(error.get("errorCode", "UNKNOWN"))
        message = _child(error, "ErrorMessage")
        text = message.text if message is not None else error.text
        texts.append((text or "").strip())
    raise MTConnectError(codes or ["UNKNOWN"], "; ".join(t for t in texts if t))


def parse_streams(
    xml_text: str, *, source: str, received_at: datetime
) -> StreamsDocument:
    """Parse an MTConnectStreams response into records, in sequence order.

    Raises MTConnectError for an error document and ValueError for anything
    that is not a streams document.
    """
    # Variables:
    #   source: The agent's base URL, copied onto every record.
    #   received_at: When the collector got this response, copied onto every record.
    #   instance_id: Read from the header and copied onto every record, so a
    #     later reader can tell runs of the agent apart.
    root = ET.fromstring(xml_text)
    raise_if_error(root)
    if _local(root.tag) != "MTConnectStreams":
        raise ValueError(f"expected MTConnectStreams, got {_local(root.tag)}")
    header = _child(root, "Header")
    if header is None:
        raise ValueError("MTConnectStreams document has no Header")
    instance_id = header.get("instanceId")

    records: list[TelemetryRecord] = []
    streams = _child(root, "Streams")
    for device in streams if streams is not None else []:
        if _local(device.tag) != "DeviceStream":
            continue
        for component in device:
            if _local(component.tag) != "ComponentStream":
                continue
            for section in component:
                category = _SECTIONS.get(_local(section.tag))
                if category is None:
                    continue
                for item in section:
                    records.append(
                        _record(
                            item,
                            category,
                            device=device.get("name") or device.get("uuid") or "",
                            component=component.get("name")
                            or component.get("component")
                            or "",
                            source=source,
                            instance_id=instance_id,
                            received_at=received_at,
                        )
                    )
    records.sort(key=lambda record: record.sequence)
    return StreamsDocument(
        instance_id=instance_id,
        next_sequence=int(header.get("nextSequence", "0")),
        first_sequence=int(header.get("firstSequence", "0")),
        last_sequence=int(header.get("lastSequence", "0")),
        records=records,
    )


def _record(
    item: ET.Element,
    category: Category,
    *,
    device: str,
    component: str,
    source: str,
    instance_id: str | None,
    received_at: datetime,
) -> TelemetryRecord:
    """Turn one observation element into a record."""
    # Variables:
    #   tag: The element's own name. For samples and events it is the
    #     observation type (SpindleSpeed); for a condition it is the level
    #     (Normal, Warning, Fault, Unavailable) and the type is an attribute.
    #   available: False when the agent says it has no value for the channel.
    tag = _local(item.tag)
    if category == "CONDITION":
        available = tag != "Unavailable"
        value = tag.upper() if available else None
        observed_type = item.get("type", tag)
        message = (item.text or "").strip() or None
    else:
        raw = _value(item)
        available = raw != UNAVAILABLE
        value = raw if available else None
        observed_type = tag
        message = None
    return TelemetryRecord(
        source=source,
        instance_id=instance_id,
        device=device,
        component=component,
        data_item_id=item.get("dataItemId", ""),
        name=item.get("name"),
        category=category,
        type=observed_type,
        sub_type=item.get("subType"),
        value=value,
        available=available,
        message=message,
        native_code=item.get("nativeCode"),
        sequence=int(item.get("sequence", "0")),
        source_timestamp=item.get("timestamp"),
        received_at=received_at,
    )
