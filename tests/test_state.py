import pytest
from pydantic import ValidationError

from capstone.simulator.state import MachineCondition, MachineState, MachineStatus


def test_new_machine_is_healthy_and_running():
    m = MachineState(id="CNC-04")
    assert m.status == MachineStatus.RUNNING
    assert m.condition.bearing_health == 1.0


def test_can_start_already_degraded():
    m = MachineState(id="CNC-04", condition=MachineCondition(bearing_health=0.7))
    assert m.condition.bearing_health == 0.7


def test_scenario_can_lower_bearing_health_in_place():
    m = MachineState(id="CNC-04")
    m.condition.bearing_health -= 0.3
    assert m.condition.bearing_health == pytest.approx(0.7)


def test_action_can_restore_bearing_health():
    m = MachineState(id="CNC-04", condition=MachineCondition(bearing_health=0.15))
    m.condition.bearing_health = 1.0
    assert m.condition.bearing_health == 1.0


def test_step_logic_can_change_status():
    m = MachineState(id="CNC-04")
    m.status = MachineStatus.DOWN
    assert m.status == MachineStatus.DOWN


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_bearing_health_outside_unit_interval_is_rejected_on_construction(bad):
    with pytest.raises(ValidationError):
        MachineCondition(bearing_health=bad)


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_bearing_health_outside_unit_interval_is_rejected_on_assignment(bad):
    m = MachineState(id="CNC-04")
    with pytest.raises(ValidationError):
        m.condition.bearing_health = bad
    assert m.condition.bearing_health == 1.0


def test_empty_id_is_rejected():
    with pytest.raises(ValidationError):
        MachineState(id="")


def test_condition_is_structurally_separable_from_observable_facts():
    m = MachineState(id="CNC-04", status=MachineStatus.DOWN)
    observable = m.model_dump(exclude={"condition"})
    assert observable == {"id": "CNC-04", "status": "down", "load": 0.5}
    assert "bearing_health" not in str(observable)
