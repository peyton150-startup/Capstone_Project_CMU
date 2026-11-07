"""The SM-1 channel map: built from /probe, tied to it by hash, checked on captures.

The probe copies the shape of a live MTConnect 2.x agent (demo.mtconnect.org);
the machine and its items are synthetic. No test touches the network.
"""

import json
import typing
from datetime import UTC, datetime

import pytest

from capstone.ingestion.channel_map import (
    Assignment,
    ChannelMapMismatch,
    ToolSensor,
    build_channel_map,
    check_capture,
    main,
    parse_probe,
    probe_hash,
)
from capstone.ingestion.record import CollectorMarker, TelemetryRecord

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
NS = "urn:mtconnect.org:MTConnectDevices:2.8"


def probe(*, created: str = "2026-11-07T12:00:00Z", load_units: str = "PERCENT") -> str:
    """A probe for one machine: a spindle, one axis, a controller path."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<MTConnectDevices xmlns="{NS}">
  <Header creationTime="{created}" instanceId="1700000000" sender="agent"
          version="2.8" bufferSize="131072"/>
  <Devices>
    <Device id="vf2" name="VF2" uuid="haas-vf2">
      <DataItems>
        <DataItem id="avail" category="EVENT" type="AVAILABILITY"/>
      </DataItems>
      <Components>
        <Axes id="ax">
          <Components>
            <Rotary id="s1" name="S1">
              <DataItems>
                <DataItem id="S1speed" name="S1speed" category="SAMPLE"
                          type="ROTARY_VELOCITY" subType="ACTUAL"
                          units="REVOLUTION/MINUTE"/>
                <DataItem id="S1load" category="SAMPLE" type="LOAD"
                          units="{load_units}"/>
                <DataItem id="S1temp" category="CONDITION" type="TEMPERATURE"/>
              </DataItems>
            </Rotary>
            <Linear id="x" name="X">
              <DataItems>
                <DataItem id="Xpos" category="SAMPLE" type="POSITION"
                          subType="ACTUAL" units="MILLIMETER"
                          nativeUnits="INCH" nativeScale="1"/>
              </DataItems>
            </Linear>
          </Components>
        </Axes>
        <Controller id="cont">
          <Components>
            <Path id="p1" name="path">
              <DataItems>
                <DataItem id="exec" category="EVENT" type="EXECUTION"/>
                <DataItem id="vars" category="EVENT" type="VARIABLE"
                          representation="DATA_SET"/>
              </DataItems>
            </Path>
          </Components>
        </Controller>
      </Components>
    </Device>
  </Devices>
</MTConnectDevices>"""


def record(item: str, category: str, type_: str, value: str | None = "1", **kw):
    return TelemetryRecord(
        source="http://agent:8082",
        instance_id="1",
        device=kw.get("device", "VF2"),
        component="c",
        data_item_id=item,
        category=category,
        type=type_,
        value=value,
        available=value is not None,
        sequence=kw.get("sequence", 1),
        source_timestamp=NOW,
        received_at=NOW,
    )


# --- reading the probe -----------------------------------------------------


def test_every_data_item_is_read_with_units_only_as_the_probe_states_them():
    entries = {e.data_item_id: e for e in parse_probe(probe())}
    assert list(entries) == [
        "avail",
        "S1speed",
        "S1load",
        "S1temp",
        "Xpos",
        "exec",
        "vars",
    ]
    speed = entries["S1speed"]
    assert (speed.device, speed.device_uuid, speed.component, speed.component_type) == (
        "VF2",
        "haas-vf2",
        "S1",
        "Rotary",
    )
    assert (speed.category, speed.type, speed.sub_type, speed.units) == (
        "SAMPLE",
        "ROTARY_VELOCITY",
        "ACTUAL",
        "REVOLUTION/MINUTE",
    )
    x = entries["Xpos"]
    assert (x.units, x.native_units, x.native_scale) == ("MILLIMETER", "INCH", "1")
    # No unit in the probe means no unit in the map: nothing is guessed.
    assert entries["S1temp"].units is None and entries["exec"].units is None
    # A component with no name is recorded by its id.
    assert entries["exec"].component == "path" and entries["avail"].component == "VF2"


def test_meaning_and_tool_sensor_stay_empty_until_a_person_assigns_them():
    channel_map = build_channel_map(probe())
    assert all(
        e.measures is None and e.tool_sensor is None for e in channel_map.entries
    )
    assert all(e.reported is None for e in channel_map.entries)


def test_assignments_are_applied_and_a_typo_is_refused():
    channel_map = build_channel_map(
        probe(),
        {"S1load": Assignment(measures="spindle motor load", tool_sensor="load")},
    )
    load = next(e for e in channel_map.entries if e.data_item_id == "S1load")
    assert (load.measures, load.tool_sensor) == ("spindle motor load", "load")
    with pytest.raises(ValueError, match="S1lod"):
        build_channel_map(probe(), {"S1lod": Assignment(tool_sensor="load")})


def test_tool_sensor_names_match_what_the_observation_tools_accept():
    from capstone.providers.factory import FactorySensor, MachineSensor

    tools = set(typing.get_args(MachineSensor)) | set(typing.get_args(FactorySensor))
    assert set(typing.get_args(ToolSensor)) == tools


def test_a_streams_document_is_not_a_probe():
    with pytest.raises(ValueError, match="MTConnectDevices"):
        parse_probe('<MTConnectStreams xmlns="x"><Header/></MTConnectStreams>')


# --- tying the map to its probe --------------------------------------------


def test_the_hash_ignores_the_header_and_formatting_but_not_a_channel_change():
    base = probe_hash(probe())
    assert probe_hash(probe(created="2026-12-01T08:00:00Z")) == base
    assert probe_hash(probe().replace("\n      ", " ")) == base
    assert probe_hash(probe(load_units="WATT")) != base


def test_a_map_refuses_a_probe_from_a_changed_controller():
    channel_map = build_channel_map(probe())
    channel_map.verify_probe(probe(created="2026-12-01T08:00:00Z"))
    with pytest.raises(ChannelMapMismatch, match="rebuild the map"):
        channel_map.verify_probe(probe(load_units="WATT"))


# --- checking a capture ----------------------------------------------------


def test_every_observation_maps_to_one_entry_or_is_reported_unmapped():
    channel_map = build_channel_map(probe())
    lines = [
        CollectorMarker(source="s", event="started", at=NOW),
        record("S1speed", "SAMPLE", "RotaryVelocity"),
        record("S1speed", "SAMPLE", "RotaryVelocity", device="haas-vf2"),
        record("S1load", "SAMPLE", "Load", value=None),
        record("S1temp", "CONDITION", "TEMPERATURE", value="NORMAL"),
        record("vars", "EVENT", "VariableDataSet", value="{}"),
        record("feed", "SAMPLE", "PathFeedrate"),
        record("feed", "SAMPLE", "PathFeedrate"),
    ]
    check = check_capture(channel_map, lines)
    uses = {u.data_item_id: (u.observations, u.available) for u in check.uses}
    assert uses["S1speed"] == (2, 2)  # matched by device name and by uuid
    assert uses["S1load"] == (1, 0)  # present, but only ever UNAVAILABLE
    assert uses["Xpos"] == (0, 0)
    assert [(u.device, u.data_item_id, u.observations) for u in check.unmapped] == [
        ("VF2", "feed", 2)
    ]
    assert check.mismatched == [] and not check.clean


def test_a_record_that_disagrees_with_its_entry_is_reported():
    channel_map = build_channel_map(probe())
    check = check_capture(
        channel_map,
        [
            record("S1speed", "EVENT", "RotaryVelocity"),
            record("Xpos", "SAMPLE", "PathPosition"),
            record("Xpos", "SAMPLE", "PathPosition"),
        ],
    )
    assert check.mismatched == [
        "S1speed: capture says EVENT, probe says SAMPLE",
        "Xpos: capture type PathPosition does not match probe type POSITION",
    ]


def test_reported_records_which_channels_held_a_value():
    channel_map = build_channel_map(probe())
    check = check_capture(
        channel_map,
        [
            record("S1speed", "SAMPLE", "RotaryVelocity"),
            record("S1load", "SAMPLE", "Load", value=None),
        ],
    )
    reported = {
        e.data_item_id: e.reported for e in channel_map.with_reported(check).entries
    }
    assert reported["S1speed"] is True
    assert reported["S1load"] is False and reported["Xpos"] is False


# --- command line ----------------------------------------------------------


def test_command_line_builds_checks_and_records_reported_channels(tmp_path, capsys):
    probe_file, assign, out, capture = (
        tmp_path / "probe.xml",
        tmp_path / "assign.json",
        tmp_path / "map.json",
        tmp_path / "telemetry.jsonl",
    )
    probe_file.write_text(probe(), encoding="utf-8")
    assign.write_text(json.dumps({"S1load": {"tool_sensor": "load"}}), encoding="utf-8")
    capture.write_text(
        record("S1speed", "SAMPLE", "RotaryVelocity").model_dump_json() + "\n\n",
        encoding="utf-8",
    )
    allow = "--allow-inside-repo"
    build = [
        "build",
        "--probe",
        str(probe_file),
        "--assign",
        str(assign),
        "--out",
        str(out),
    ]
    assert main([*build, allow]) == 0
    assert "wrote 7 channels" in capsys.readouterr().out
    check = [
        "check",
        "--map",
        str(out),
        "--capture",
        str(capture),
        "--probe",
        str(probe_file),
    ]
    assert main([*check, "--update-reported", allow]) == 0
    report = capsys.readouterr().out
    assert "1 of 7 channels reported" in report and "never reported a value" in report
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert [e["reported"] for e in saved["entries"]].count(True) == 1
    probe_file.write_text(probe(load_units="WATT"), encoding="utf-8")
    assert main(check) == 2
    assert "refused" in capsys.readouterr().err


def test_command_line_refuses_to_write_a_map_inside_the_repository(tmp_path, capsys):
    probe_file = tmp_path / "probe.xml"
    probe_file.write_text(probe(), encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        main(["build", "--probe", str(probe_file), "--out", str(tmp_path / "m.json")])
    assert stop.value.code == 2
    assert "inside the git checkout" in capsys.readouterr().err
