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
    compact,
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
    machines = look.get_line_screening()["machines"]
    far = {
        machine_id
        for machine_id, sensors in machines.items()
        if isinstance(sensors, dict)
        for scores in sensors.values()
        if isinstance(scores, list) and abs(scores[0]) >= 3 and abs(scores[1]) >= 3
    }
    assert far == {"CNC-02"}
    assert machines["CNC-02"]["vibration"][0] > 3


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
    assert set(result.data) == {"reference", "machines"}


def test_every_machine_on_the_line_gets_an_entry_in_line_order():
    sim = build_world(6, fault="bearing_degradation")
    for _ in range(300):
        sim.step()
    look = ObservationTools(sim)
    machines = [m["machine_id"] for m in look.list_machines()]
    assert list(look.get_line_screening()["machines"]) == machines


def compact_rows(machine_id: str, statuses: dict[str, str]) -> list[dict]:
    """Full rows for one machine: a scored row where the status is "scored"."""
    rows = []
    for sensor, status in statuses.items():
        row = {"machine_id": machine_id, "sensor": sensor, "status": status}
        if status == "scored":
            stage = "steady" if sensor == "temperature" else NO_WARMUP
            row.update(robust_score=1.5, plain_score=2.0, warmup_stage=stage)
        rows.append(row)
    return rows


def test_the_compact_form_keeps_scores_stages_and_reasons():
    rows = compact_rows("CNC-01", {"vibration": "scored", "temperature": "scored"})
    rows += compact_rows(
        "CNC-02", {"vibration": "not_running_yet", "load": "not_running_yet"}
    )
    rows += compact_rows(
        "CNC-03", {"vibration": "scored", "load": "too_few_running_readings"}
    )
    machines = compact(rows)["machines"]
    assert machines["CNC-01"] == {
        "vibration": [1.5, 2.0],
        "temperature": [1.5, 2.0, "steady"],
    }
    # One reason for every sensor folds into that word.
    assert machines["CNC-02"] == "not_running_yet"
    # Mixed: the reason stays on its sensor.
    assert machines["CNC-03"] == {
        "vibration": [1.5, 2.0],
        "load": "too_few_running_readings",
    }


@pytest.mark.parametrize(
    "seed,fault",
    [
        (6, "bearing_degradation"),
        (7, "bad_material_batch"),
        (8, "wrong_setting"),
        (5, "false_alarm"),
        (9, "servo_drive_wear"),
        (13, "hydraulic_leak"),
    ],
)
def test_the_whole_line_fits_what_a_prompt_shows_of_one_evidence(seed, fault):
    # The prompt cuts each piece of evidence at MAX_EVIDENCE_CHARS; the full
    # rows (about 16,000 characters) lost every machine after the first two.
    from capstone.agent.model_policy import MAX_EVIDENCE_CHARS

    sim = build_world(seed, fault=fault)
    look = ObservationTools(sim)
    from capstone.agent.monitor import detect_anomaly

    detect_anomaly(look, ActionTools(sim, None))
    provider = SimulatorFactoryProvider(look, ActionTools(sim, None))
    data = provider.call(ToolRequest(name="get_line_screening")).data
    assert len(json.dumps(data, sort_keys=True)) <= MAX_EVIDENCE_CHARS
    assert len(data["machines"]) == len(sim.state.machines)


def test_a_blackout_takes_away_only_the_dead_machines_entry():
    # Before: the screening showed CNC-02's scores while its feed was refused.
    from capstone.agent.monitor import detect_anomaly
    from capstone.providers.hazards import Blackout, UnreliableProvider

    sim = build_world(6, fault="bearing_degradation")
    look = ObservationTools(sim)
    detect_anomaly(look, ActionTools(sim, None))
    tick = look.get_time()["tick"]
    inner = SimulatorFactoryProvider(look, ActionTools(sim, None))
    honest = inner.call(ToolRequest(name="get_line_screening")).data["machines"]
    provider = UnreliableProvider(inner, (Blackout("CNC-02", tick + 10),))
    during = provider.call(ToolRequest(name="get_line_screening")).data["machines"]
    assert during["CNC-02"] == "feed_unavailable"
    assert {k: v for k, v in during.items() if k != "CNC-02"} == {
        k: v for k, v in honest.items() if k != "CNC-02"
    }
    assert provider.report.fired == [f"blackout on CNC-02 until tick {tick + 10}"]
    assert provider.report.blocked == 0  # not refused, so not counted as a refusal
    for _ in range(10):
        sim.step()
    after = provider.call(ToolRequest(name="get_line_screening")).data["machines"]
    assert isinstance(after["CNC-02"], dict)  # the feed is back


@pytest.mark.parametrize("machine_ids", [[], ["CNC-01"]])
def test_screen_line_keeps_line_order(machine_ids):
    rows = screen_line(machine_ids, {"CNC-01": readings([40.0] * 30, [120.0] * 30)})
    assert [r["machine_id"] for r in rows] == ["CNC-01"] * len(rows)
    assert bool(rows) == bool(machine_ids)
