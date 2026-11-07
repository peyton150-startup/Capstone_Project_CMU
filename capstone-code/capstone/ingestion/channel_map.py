# Builds a versioned map of a machine's channels from its saved /probe document.
# Responsibility: say what each data item is, as the probe states it; never guess units or meaning.
"""The channel map (SM-1 in docs/MVP_SCOPE.md).

An MTConnect agent's /probe lists every data item the machine exposes: its
id, category (SAMPLE, EVENT, CONDITION), type, subtype and units. The
channel map records exactly that, one entry per data item, and adds two
things only a person can supply:

- `measures`: what the item measures physically on this machine, in words.
- `tool_sensor`: which of the agent's sensor names it feeds, or none.

Both come from an assignment file a person writes after reading the probe
and the machine's documentation. Nothing is inferred from an item's name,
and a unit the probe does not state stays None.

The map is tied to a hash of the probe's device description, so a
controller update that changes a channel cannot silently keep an old map:
`verify_probe` refuses a probe whose hash differs. The probe's header is
left out of the hash because its creation time and instance id change on
every request.

`check_capture` then compares a recorded capture with the map: every
observation maps to one entry or is reported as unmapped, and the map can
record which channels the machine actually reported.

    uv run python -m capstone.ingestion.channel_map build --probe ../pilot-data/probe.xml         [--assign ../pilot-data/assignments.json] --out ../pilot-data/channel-map.json
    uv run python -m capstone.ingestion.channel_map check --map ../pilot-data/channel-map.json         --capture ../pilot-data/telemetry.jsonl [--probe ../pilot-data/probe.xml]         [--update-reported]

The assignment file is JSON: {"<data item id>": {"measures": "...",
"tool_sensor": "vibration"}}. Output paths inside a git checkout are refused.
"""

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from capstone.ingestion.mtconnect import _child, _local
from capstone.ingestion.privacy import ALLOW_FLAG, ALLOW_HELP, refusal
from capstone.ingestion.record import Category, Line, TelemetryRecord, parse_line

# The sensor names the agent's observation tools accept (providers/factory.py
# MachineSensor and FactorySensor); a test keeps the two lists equal.
ToolSensor = Literal[
    "vibration",
    "temperature",
    "load",
    "power",
    "following_error",
    "hydraulic_pressure",
    "air_temperature",
]

# Element-name endings MTConnect adds for non-VALUE representations.
_REPRESENTATION_SUFFIXES = ("DataSet", "TimeSeries", "Table")

_CATEGORIES: dict[str, Category] = {
    "SAMPLE": "SAMPLE",
    "EVENT": "EVENT",
    "CONDITION": "CONDITION",
}


class ChannelMapMismatch(ValueError):
    """A probe does not match the probe the channel map was built from."""


class ChannelEntry(BaseModel):
    """One data item the machine exposes, as its probe describes it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   device, device_uuid: The probe's Device name and uuid; a capture's
    #     records name their device by one of the two.
    #   component, component_type: The nearest enclosing component's name
    #     (or id) and its element name, e.g. "S1" and "Rotary".
    #   category, type, sub_type: As the probe states them, e.g. SAMPLE,
    #     ROTARY_VELOCITY, ACTUAL.
    #   units, native_units, native_scale: As the probe states them; None
    #     when the probe gives none, never filled in from elsewhere.
    #   measures: What the item measures physically, from a person's
    #     assignment; None until someone states it.
    #   tool_sensor: Which agent sensor name it feeds, from a person's
    #     assignment; None means it feeds none.
    #   reported: Whether a checked capture held an available value for it;
    #     None until a capture has been checked.
    device: str
    device_uuid: str | None = None
    component: str
    component_type: str
    data_item_id: str
    name: str | None = None
    category: Category
    type: str
    sub_type: str | None = None
    units: str | None = None
    native_units: str | None = None
    native_scale: str | None = None
    measures: str | None = None
    tool_sensor: ToolSensor | None = None
    reported: bool | None = None


class Assignment(BaseModel):
    """A person's statement of what one data item means on this machine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    measures: str | None = None
    tool_sensor: ToolSensor | None = None


class ChannelMap(BaseModel):
    """Every channel of one probe, tied to that probe by its hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   probe_sha256: Hash of the probe's device description (header left
    #     out); a different value means a different channel layout.
    #   entries: One entry per data item, in probe order.
    schema_version: Literal[1] = 1
    probe_sha256: str
    entries: list[ChannelEntry]

    def verify_probe(self, probe_xml: str) -> None:
        """Raise ChannelMapMismatch unless the probe is the one this map is from."""
        # Variables:
        #   actual: The given probe's hash, compared with probe_sha256.
        actual = probe_hash(probe_xml)
        if actual != self.probe_sha256:
            raise ChannelMapMismatch(
                f"probe hash {actual[:12]} does not match the map's "
                f"{self.probe_sha256[:12]}; rebuild the map from this probe"
            )

    def entry_for(self, record: TelemetryRecord) -> ChannelEntry | None:
        """The entry a record belongs to, or None if the map has none."""
        # Variables:
        #   record: An observation; it names its device by name or by uuid,
        #     so either one matches.
        for entry in self.entries:
            if entry.data_item_id == record.data_item_id and record.device in (
                entry.device,
                entry.device_uuid,
            ):
                return entry
        return None

    def with_reported(self, check: "CaptureCheck") -> "ChannelMap":
        """A copy where each entry records whether the capture reported it."""
        # Variables:
        #   seen: Each entry's data item id mapped to True if the capture held
        #     at least one available value for it.
        seen = {use.data_item_id: use.available > 0 for use in check.uses}
        return self.model_copy(
            update={
                "entries": [
                    e.model_copy(update={"reported": seen.get(e.data_item_id, False)})
                    for e in self.entries
                ]
            }
        )


class ChannelUse(BaseModel):
    """How often a capture held one mapped channel."""

    model_config = ConfigDict(frozen=True)

    data_item_id: str
    observations: int
    available: int


class Unmapped(BaseModel):
    """Observations in a capture that no channel entry describes."""

    model_config = ConfigDict(frozen=True)

    device: str
    data_item_id: str
    observations: int


class CaptureCheck(BaseModel):
    """A capture compared with a channel map."""

    model_config = ConfigDict(frozen=True)

    # Variables:
    #   uses: One row per map entry, with how many observations the capture
    #     held for it and how many were available (not UNAVAILABLE).
    #   unmapped: Observations whose data item the map does not describe.
    #   mismatched: Records whose category or type disagrees with their
    #     entry, as plain-English lines; each means the map or the capture
    #     is from a different configuration.
    uses: list[ChannelUse]
    unmapped: list[Unmapped]
    mismatched: list[str]

    @property
    def clean(self) -> bool:
        """True when every observation maps to an entry that agrees with it."""
        return not self.unmapped and not self.mismatched


def probe_hash(probe_xml: str) -> str:
    """SHA-256 of the probe's device description, ignoring its header."""
    # Variables:
    #   devices: The <Devices> element: everything that describes channels.
    #     The <Header> is left out because it changes on every request.
    #   canonical: The element in canonical XML with whitespace between tags
    #     removed, so formatting changes do not change the hash.
    root = ET.fromstring(probe_xml)
    devices = _devices(root)
    canonical = ET.canonicalize(
        ET.tostring(devices, encoding="unicode"), strip_text=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_probe(probe_xml: str) -> list[ChannelEntry]:
    """Every data item in an MTConnectDevices document, in document order."""
    # Variables:
    #   entries: The entries found so far, appended by _walk.
    root = ET.fromstring(probe_xml)
    entries: list[ChannelEntry] = []
    for device in _devices(root):
        if _local(device.tag) not in ("Device", "Agent"):
            continue
        _walk(
            device,
            device_name=device.get("name") or device.get("uuid") or "",
            device_uuid=device.get("uuid"),
            component=device.get("name") or device.get("id") or "",
            component_type=_local(device.tag),
            entries=entries,
        )
    return entries


def build_channel_map(
    probe_xml: str, assignments: Mapping[str, Assignment] | None = None
) -> ChannelMap:
    """The channel map of a probe, with a person's assignments applied.

    An assignment for a data item id the probe does not have is refused, so
    a typo cannot leave a channel silently unassigned.
    """
    # Variables:
    #   assignments: Data item id to what a person says it measures and which
    #     tool sensor it feeds; ids not listed keep both as None.
    #   entries: The probe's entries before assignments are applied.
    #   unknown: Assigned ids the probe does not describe.
    assignments = assignments or {}
    entries = parse_probe(probe_xml)
    unknown = sorted(set(assignments) - {e.data_item_id for e in entries})
    if unknown:
        raise ValueError(f"assignments name data items the probe lacks: {unknown}")
    return ChannelMap(
        probe_sha256=probe_hash(probe_xml),
        entries=[
            e.model_copy(update=assignments[e.data_item_id].model_dump())
            if e.data_item_id in assignments
            else e
            for e in entries
        ],
    )


def check_capture(channel_map: ChannelMap, lines: Iterable[Line]) -> CaptureCheck:
    """Compare a capture's observations with the map; markers are skipped."""
    # Variables:
    #   observations, available: Per mapped data item id, how many records
    #     the capture held and how many of those had a value.
    #   unmapped: Per (device, data item id) with no entry, how many records.
    #   mismatched: One line per distinct disagreement between a record's
    #     category or type and its entry.
    #   index: Each entry under (device name, id) and (device uuid, id), so
    #     each record is looked up once instead of scanning every entry.
    index: dict[tuple[str | None, str], ChannelEntry] = {}
    for e in channel_map.entries:
        index[(e.device, e.data_item_id)] = e
        if e.device_uuid:
            index[(e.device_uuid, e.data_item_id)] = e
    observations: Counter[str] = Counter()
    available: Counter[str] = Counter()
    unmapped: Counter[tuple[str, str]] = Counter()
    mismatched: dict[str, None] = {}
    for line in lines:
        if not isinstance(line, TelemetryRecord):
            continue
        entry = index.get((line.device, line.data_item_id))
        if entry is None:
            unmapped[(line.device, line.data_item_id)] += 1
            continue
        observations[entry.data_item_id] += 1
        available[entry.data_item_id] += line.available
        problem = _disagreement(entry, line)
        if problem:
            mismatched[problem] = None
    return CaptureCheck(
        uses=[
            ChannelUse(
                data_item_id=e.data_item_id,
                observations=observations[e.data_item_id],
                available=available[e.data_item_id],
            )
            for e in channel_map.entries
        ],
        unmapped=[
            Unmapped(device=device, data_item_id=item, observations=count)
            for (device, item), count in sorted(unmapped.items())
        ],
        mismatched=list(mismatched),
    )


def _devices(root: ET.Element) -> ET.Element:
    """The <Devices> element of an MTConnectDevices document."""
    if _local(root.tag) != "MTConnectDevices":
        raise ValueError(f"expected MTConnectDevices, got {_local(root.tag)}")
    devices = _child(root, "Devices")
    if devices is None:
        raise ValueError("MTConnectDevices document has no Devices")
    return devices


def _walk(
    element: ET.Element,
    *,
    device_name: str,
    device_uuid: str | None,
    component: str,
    component_type: str,
    entries: list[ChannelEntry],
) -> None:
    """Add the data items under one device or component, then its children's."""
    # Variables:
    #   element: A Device or component element; its <DataItems> belong to it.
    #   component, component_type: The element's own name and element name,
    #     recorded on each of its data items.
    #   data_items: The element's <DataItems>; each DataItem becomes an entry.
    #   category: The item's category as the probe states it; an item without
    #     a valid one is refused rather than guessed.
    #   children: The <Components> element holding nested components.
    data_items = _child(element, "DataItems")
    for item in data_items if data_items is not None else []:
        if _local(item.tag) != "DataItem":
            continue
        category = _CATEGORIES.get(item.get("category", ""))
        if category is None:
            raise ValueError(f"data item {item.get('id')} has no valid category")
        entries.append(
            ChannelEntry(
                device=device_name,
                device_uuid=device_uuid,
                component=component,
                component_type=component_type,
                data_item_id=item.get("id", ""),
                name=item.get("name"),
                category=category,
                type=item.get("type", ""),
                sub_type=item.get("subType"),
                units=item.get("units"),
                native_units=item.get("nativeUnits"),
                native_scale=item.get("nativeScale"),
            )
        )
    children = _child(element, "Components")
    for child in children if children is not None else []:
        _walk(
            child,
            device_name=device_name,
            device_uuid=device_uuid,
            component=child.get("name") or child.get("id") or "",
            component_type=_local(child.tag),
            entries=entries,
        )


def _probe_type(stream_type: str) -> str:
    """A streams element name in the probe's spelling: RotaryVelocity -> ROTARY_VELOCITY."""
    # Variables:
    #   name: The element name without a representation suffix; a DATA_SET,
    #     TABLE or TIME_SERIES item's element is its type name plus "DataSet",
    #     "Table" or "TimeSeries".
    #   letters: The name's characters, with "_" put before each capital
    #     that follows a lower-case letter or digit.
    name = stream_type
    for suffix in _REPRESENTATION_SUFFIXES:
        if name.endswith(suffix) and name != suffix:
            name = name[: -len(suffix)]
            break
    letters: list[str] = []
    for index, char in enumerate(name):
        previous = name[index - 1] if index else ""
        if char.isupper() and (previous.islower() or previous.isdigit()):
            letters.append("_")
        letters.append(char.upper())
    return "".join(letters)


def _disagreement(entry: ChannelEntry, record: TelemetryRecord) -> str | None:
    """Why a record does not fit its entry, or None if it does."""
    # Variables:
    #   recorded_type: The record's type in the probe's spelling. Samples and
    #     events carry the element name (RotaryVelocity); conditions carry the
    #     probe's own type attribute already.
    if record.category != entry.category:
        return (
            f"{entry.data_item_id}: capture says {record.category}, "
            f"probe says {entry.category}"
        )
    recorded_type = _probe_type(record.type)
    if recorded_type != entry.type:
        return (
            f"{entry.data_item_id}: capture type {record.type} does not match "
            f"probe type {entry.type}"
        )
    return None


def load_assignments(path: Path) -> dict[str, Assignment]:
    """Read a person's assignment file: data item id to its meaning."""
    # Variables:
    #   raw: The file's JSON object; each value is checked as an Assignment,
    #     so an unknown field or tool sensor name is refused.
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {item: Assignment.model_validate(value) for item, value in raw.items()}


def read_capture(path: Path) -> list[Line]:
    """Every line of a telemetry JSONL file, skipping blank ones."""
    with path.open(encoding="utf-8") as source:
        return [parse_line(text) for text in source if text.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    """Build a channel map from a probe, or check a capture against one."""
    # Variables:
    #   argv: Command-line arguments; None means the real ones.
    #   args: The chosen command and its files.
    #   channel_map: The map built from --probe, or read from --map.
    #   check: The capture compared with the map, printed as a report.
    #   outcome: 0 when every observation maps cleanly, 1 when some are
    #     unmapped or disagree with their entry, so a script can stop on it.
    parser = argparse.ArgumentParser(prog="python -m capstone.ingestion.channel_map")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build a channel map from a probe")
    build.add_argument("--probe", type=Path, required=True)
    build.add_argument("--assign", type=Path, help="JSON assignment file")
    build.add_argument("--out", type=Path, required=True)
    build.add_argument(ALLOW_FLAG, action="store_true", help=ALLOW_HELP)
    check_cmd = commands.add_parser("check", help="check a capture against a map")
    check_cmd.add_argument("--map", type=Path, required=True)
    check_cmd.add_argument("--capture", type=Path, required=True)
    check_cmd.add_argument("--probe", type=Path, help="refuse if it is not the map's")
    check_cmd.add_argument(
        "--update-reported",
        action="store_true",
        help="write which channels the capture reported back into the map",
    )
    check_cmd.add_argument(ALLOW_FLAG, action="store_true", help=ALLOW_HELP)
    args = parser.parse_args(argv)

    if args.command == "build":
        problem = not args.allow_inside_repo and refusal(args.out, "--out")
        if problem:
            parser.error(problem)
        channel_map = build_channel_map(
            args.probe.read_text(encoding="utf-8"),
            load_assignments(args.assign) if args.assign else None,
        )
        args.out.write_text(channel_map.model_dump_json(indent=2), encoding="utf-8")
        print(f"wrote {len(channel_map.entries)} channels to {args.out}")
        return 0

    problem = (
        args.update_reported
        and not args.allow_inside_repo
        and refusal(args.map, "--map")
    )
    if problem:
        parser.error(problem)
    channel_map = ChannelMap.model_validate_json(args.map.read_text(encoding="utf-8"))
    if args.probe:
        try:
            channel_map.verify_probe(args.probe.read_text(encoding="utf-8"))
        except ChannelMapMismatch as error:
            print(f"refused: {error}", file=sys.stderr)
            return 2
    check = check_capture(channel_map, read_capture(args.capture))
    silent = [u.data_item_id for u in check.uses if u.available == 0]
    print(f"{len(check.uses) - len(silent)} of {len(check.uses)} channels reported")
    if silent:
        print("never reported a value: " + ", ".join(silent))
    for item in check.unmapped:
        print(f"unmapped: {item.device}/{item.data_item_id} ({item.observations})")
    for line in check.mismatched:
        print(f"mismatch: {line}")
    if args.update_reported:
        updated = channel_map.with_reported(check)
        args.map.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
        print(f"recorded reported channels in {args.map}")
    return 0 if check.clean else 1


if __name__ == "__main__":
    sys.exit(main())
