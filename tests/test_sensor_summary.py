import pytest

from capstone.contracts.tools import ToolRequest
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.line import build_line
from capstone.simulator.sensors import SensorReading
from capstone.tools.actions import ActionTools
from capstone.tools.observation import ObservationTools


def sample(tick, value, machine_id="CNC-01", sensor="temperature", unit="°F"):
    return SensorReading(
        tick=tick, machine_id=machine_id, sensor=sensor, value=value, unit=unit
    )


def test_summary_orders_and_filters_readings_and_uses_elapsed_ticks():
    sim = build_line(42, machines=3)
    sim._readings.extend(
        [
            sample(10, 20),
            sample(2, 8),
            sample(4, 2),
            sample(1, 999),
            sample(11, 999),
            sample(4, 999, "CNC-02"),
            sample(4, 999, sensor="vibration"),
        ]
    )
    summary = ObservationTools(sim).get_sensor_summary("CNC-01", "temperature", 2, 10)
    assert summary == {
        "machine_id": "CNC-01",
        "sensor": "temperature",
        "from_tick": 2,
        "to_tick": 10,
        "sample_count": 3,
        "unit": "°F",
        "first_tick": 2,
        "last_tick": 10,
        "start_value": 8.0,
        "end_value": 20.0,
        "minimum": 2.0,
        "maximum": 20.0,
        "mean": 10.0,
        "delta": 12.0,
        "rate_of_change": 1.5,
    }


def test_empty_summary_has_no_invented_values_or_units():
    sim = build_line(42, machines=3)
    summary = ObservationTools(sim).get_sensor_summary("CNC-01", "missing", 0, 10)
    assert summary["sample_count"] == 0
    for field in (
        "unit",
        "first_tick",
        "last_tick",
        "start_value",
        "end_value",
        "minimum",
        "maximum",
        "mean",
        "delta",
        "rate_of_change",
    ):
        assert summary[field] is None


def test_single_sample_has_zero_delta_but_no_rate():
    sim = build_line(42, machines=3)
    sim._readings.append(sample(4, 12))
    summary = ObservationTools(sim).get_sensor_summary("CNC-01", "temperature", 0, 10)
    assert summary["sample_count"] == 1
    assert summary["first_tick"] == summary["last_tick"] == 4
    assert summary["minimum"] == summary["maximum"] == summary["mean"] == 12
    assert summary["delta"] == 0
    assert summary["rate_of_change"] is None


def test_factory_summary_selects_only_factory_observations():
    sim = build_line(42, machines=3)
    sim._readings.extend([sample(2, 80, None), sample(6, 72, None), sample(2, 999)])
    summary = ObservationTools(sim).get_sensor_summary(None, "temperature", 0, 10)
    assert summary["machine_id"] is None
    assert summary["sample_count"] == 2
    assert summary["mean"] == 76
    assert summary["rate_of_change"] == -2


@pytest.mark.parametrize("start,end", [(-1, 4), (5, 4), (True, 4), (0, 4.5)])
def test_invalid_window_is_rejected_directly_and_through_provider(start, end):
    sim = build_line(42, machines=3)
    obs = ObservationTools(sim)
    with pytest.raises(ValueError):
        obs.get_sensor_summary("CNC-01", "temperature", start, end)
    result = SimulatorFactoryProvider(obs, ActionTools(sim)).call(
        ToolRequest(
            name="get_sensor_summary",
            arguments={
                "machine_id": "CNC-01",
                "sensor": "temperature",
                "from_tick": start,
                "to_tick": end,
            },
        )
    )
    assert not result.success
    assert result.error.code == "invalid_arguments"
    assert sim.clock.tick == 0


def test_unknown_machine_is_rejected():
    sim = build_line(42, machines=3)
    with pytest.raises(ValueError, match="unknown machine"):
        ObservationTools(sim).get_sensor_summary("unknown", "temperature", 0, 10)


def test_provider_summary_is_read_only_and_independent_of_hidden_truth():
    sim = build_line(42, machines=3)
    for _ in range(5):
        sim.step()
    factory = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim))
    request = ToolRequest(
        name="get_sensor_summary",
        arguments={
            "machine_id": "CNC-01",
            "sensor": "temperature",
            "from_tick": 0,
            "to_tick": 5,
        },
    )
    before_state = sim.state.model_dump()
    before_readings = sim.readings
    result = factory.call(request)
    assert result.success
    assert result.data["sample_count"] == 5
    assert sim.state.model_dump() == before_state
    assert sim.readings == before_readings
    assert sim.clock.tick == 5
    sim.state.machines["CNC-01"].condition.bearing_health = 0.2
    assert factory.call(request).data == result.data
    assert not any(
        secret in result.model_dump_json()
        for secret in (
            "bearing_health",
            "defect_risk",
            "standard_speed",
            "ground_truth",
        )
    )


def test_same_seed_produces_same_summary_without_consuming_randomness():
    first, second = build_line(42, machines=3), build_line(42, machines=3)
    for _ in range(5):
        first.step()
        second.step()
    assert ObservationTools(first).get_sensor_summary("CNC-01", "vibration", 0, 5) == (
        ObservationTools(second).get_sensor_summary("CNC-01", "vibration", 0, 5)
    )
    ObservationTools(first).get_sensor_summary("CNC-01", "vibration", 0, 5)
    first.step()
    second.step()
    assert first.readings == second.readings


def test_mixed_units_are_rejected_instead_of_combined():
    sim = build_line(42, machines=3)
    sim._readings.extend([sample(2, 80), sample(4, 20, unit="°C")])
    with pytest.raises(ValueError, match="unit"):
        ObservationTools(sim).get_sensor_summary("CNC-01", "temperature", 0, 5)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_values_are_rejected(value):
    sim = build_line(42, machines=3)
    sim._readings.append(sample(2, value))
    with pytest.raises(ValueError, match="finite"):
        ObservationTools(sim).get_sensor_summary("CNC-01", "temperature", 0, 5)


@pytest.mark.parametrize("machine_id", ["CNC-01", None])
@pytest.mark.parametrize("has_samples", [False, True])
def test_provider_preserves_empty_and_populated_summary_results(
    machine_id, has_samples
):
    sim = build_line(42, machines=3)
    # The factory's own thermometer is air_temperature; machines have temperature.
    sensor = "temperature" if machine_id else "air_temperature"
    if has_samples:
        sim._readings.extend(
            [sample(2, 80, machine_id, sensor), sample(6, 72, machine_id, sensor)]
        )
    factory = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim))
    result = factory.call(
        ToolRequest(
            name="get_sensor_summary",
            arguments={
                "machine_id": machine_id,
                "sensor": sensor,
                "from_tick": 0,
                "to_tick": 10,
            },
        )
    )
    assert result.success
    assert result.data["machine_id"] == machine_id
    assert result.data["sample_count"] == (2 if has_samples else 0)
    assert result.data["mean"] == (76 if has_samples else None)
    assert result.data["rate_of_change"] == (-2 if has_samples else None)
