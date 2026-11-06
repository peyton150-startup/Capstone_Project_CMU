"""The line screening: every machine against a saved healthy "before" file."""

import copy
import json

import pytest

from capstone.contracts.tools import ToolRequest
from capstone.episode import build_world
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.tools.actions import ActionTools
from capstone.tools.observation import ObservationTools
from capstone.tools.screening import (
    GENERATOR_SETTINGS,
    NO_WARMUP,
    REFERENCE_PATH,
    load_reference,
    make_reference,
    screen_line,
    screen_machine,
    stage_of,
)

HIDDEN_WORDS = ("bearing", "health", "degradation", "fault", "scenario", "ground")


def reference_with(**settings) -> dict:
    """The saved file with some settings changed, for tests that steer them."""
    changed = copy.deepcopy(load_reference())
    changed["settings"].update(settings)
    return changed


def readings(load: list[float], temperature: list[float], start: int = 1) -> dict:
    """One machine's load and temperature readings, one per tick from `start`."""
    return {
        "load": [(start + i, v) for i, v in enumerate(load)],
        "temperature": [(start + i, v) for i, v in enumerate(temperature)],
    }


def test_the_saved_file_is_what_the_generator_writes_now():
    # The file is the one place the settings live; regenerating must not
    # change it, so a changed sensor model shows up here, not as quiet drift.
    assert make_reference() == json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def test_the_settings_in_the_file_are_the_generators():
    assert load_reference()["settings"] == GENERATOR_SETTINGS


def test_the_screening_reads_its_settings_from_the_file():
    machine = readings([40.0] * 30, [120.0] * 30)
    strict = reference_with(min_recent=40)
    loose = reference_with(min_recent=10)
    by_strict = {r["sensor"]: r for r in screen_machine("CNC-01", machine, strict)}
    by_loose = {r["sensor"]: r for r in screen_machine("CNC-01", machine, loose)}
    assert by_strict["load"]["status"] == "too_few_running_readings"
    assert by_loose["load"]["status"] == "scored"


def test_a_machine_that_has_not_cut_yet_is_not_running_yet_never_scored():
    rows = screen_machine("CNC-01", readings([0.5] * 40, [70.0] * 40), load_reference())
    assert {r["status"] for r in rows} == {"not_running_yet"}
    assert all(r["robust_score"] is None for r in map(defaulted, rows))


def defaulted(row: dict) -> dict:
    """A row with the optional numbers filled in as None, as the contract gives them."""
    return {"robust_score": None, "plain_score": None, **row}


def test_only_ticks_where_the_machine_cuts_count():
    # Ten idle ticks, then twenty cutting: the window holds the twenty only.
    load = [0.5] * 10 + [40.0] * 20
    rows = screen_machine("CNC-01", readings(load, [120.0] * 30), load_reference())
    by = {r["sensor"]: r for r in rows}
    assert by["load"]["running_readings"] == 20
    assert by["load"]["window_from_tick"] == 11


def test_a_machine_with_no_saved_range_says_so():
    rows = screen_machine(
        "CNC-99", readings([40.0] * 30, [120.0] * 30), load_reference()
    )
    assert {r["status"] for r in rows} == {"no_reference"}


def test_only_temperature_has_warm_up_stages():
    settings = load_reference()["settings"]
    first, middle, last = (0, *settings["warmup_boundaries"])
    assert stage_of("temperature", first, settings) == "start"
    assert stage_of("temperature", middle, settings) == "warming"
    assert stage_of("temperature", last, settings) == "steady"
    assert stage_of("vibration", first, settings) == NO_WARMUP
    for machine in load_reference()["ranges"].values():
        assert set(machine["temperature"]) == {"start", "warming", "steady"}
        assert set(machine["load"]) == {NO_WARMUP}


def test_a_cold_start_is_compared_with_the_cold_start_range():
    # Temperature at the healthy "start" level scores near zero during the
    # first readings, though it is far below the steady level.
    ranges = load_reference()["ranges"]["CNC-01"]["temperature"]
    cold = [ranges["start"]["median"]] * 30
    rows = screen_machine("CNC-01", readings([40.0] * 30, cold), load_reference())
    temperature = next(r for r in rows if r["sensor"] == "temperature")
    assert temperature["warmup_stage"] == "start"
    assert abs(temperature["robust_score"]) < 1


def test_a_wearing_bearing_scores_high_on_its_machine_only():
    # KA-01: a bearing wears on CNC-02. At the alarm, only CNC-02 sits far
    # from the healthy line, and its vibration is higher, not lower.
    sim = build_world(6, fault="bearing_degradation")
    look = ObservationTools(sim)
    from capstone.agent.monitor import detect_anomaly

    detect_anomaly(look, ActionTools(sim, None))
    rows = look.get_line_screening()
    far = {
        r["machine_id"]
        for r in rows
        if r["status"] == "scored"
        and abs(r["robust_score"]) >= 3
        and abs(r["plain_score"]) >= 3
    }
    assert far == {"CNC-02"}
    vibration = next(
        r for r in rows if r["machine_id"] == "CNC-02" and r["sensor"] == "vibration"
    )
    assert vibration["robust_score"] > 3


def test_the_same_seed_screens_the_same():
    def screened():
        sim = build_world(9, fault="servo_drive_wear")
        for _ in range(400):
            sim.step()
        return ObservationTools(sim).get_line_screening()

    assert screened() == screened()


def test_the_tool_answer_carries_no_hidden_truth():
    sim = build_world(6, fault="bearing_degradation")
    for _ in range(600):
        sim.step()
    provider = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim, None))
    result = provider.call(ToolRequest(name="get_line_screening"))
    assert result.error is None
    text = json.dumps(result.data).lower()
    for word in HIDDEN_WORDS:
        assert word not in text
    assert "truth" not in text
    assert not any(isinstance(r.get("label"), str) for r in result.data)


def test_every_machine_on_the_line_gets_rows():
    sim = build_world(6, fault="bearing_degradation")
    for _ in range(300):
        sim.step()
    look = ObservationTools(sim)
    machines = [m["machine_id"] for m in look.list_machines()]
    rows = look.get_line_screening()
    assert [m for m in machines if m in {r["machine_id"] for r in rows}] == machines


@pytest.mark.parametrize("machine_ids", [[], ["CNC-01"]])
def test_screen_line_keeps_line_order(machine_ids):
    rows = screen_line(machine_ids, {"CNC-01": readings([40.0] * 30, [120.0] * 30)})
    assert [r["machine_id"] for r in rows] == ["CNC-01"] * len(rows)
    assert bool(rows) == bool(machine_ids)
