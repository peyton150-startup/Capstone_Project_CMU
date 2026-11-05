import pytest
from pydantic import ValidationError

from capstone.simulator.state import MachineCondition, MachineState, MachineStatus


def test_new_machine_is_healthy_and_running():
    m = MachineState(id="CNC-04")
    assert m.status == MachineStatus.RUNNING
    assert m.condition.bearing_health == 1.0


def test_can_start_already_degraded():
    """A scenario may start a machine worn: health is set, and it still runs."""
    m = MachineState(id="CNC-04", condition=MachineCondition(bearing_health=0.7))
    assert m.condition.bearing_health == 0.7
    assert m.status == MachineStatus.RUNNING


def test_scenario_can_lower_bearing_health_in_place():
    m = MachineState(id="CNC-04")
    m.condition.bearing_health -= 0.3
    assert m.condition.bearing_health == pytest.approx(0.7)


def test_condition_accepts_a_full_restore_in_place():
    """Setting health back to the 1.0 bound passes the check made on assignment.

    The repair action itself is tested in `tests/test_bearing_replacement.py`.
    """
    m = MachineState(id="CNC-04", condition=MachineCondition(bearing_health=0.15))
    condition = m.condition
    m.condition.bearing_health = 1.0
    assert m.condition is condition
    assert m.model_dump()["condition"]["bearing_health"] == 1.0


def test_a_status_change_shows_in_the_observable_facts():
    """Status is writable, and the change is what an observer is shown.

    The step logic that takes a machine down is tested in `tests/test_failure.py`.
    """
    m = MachineState(id="CNC-04")
    m.status = MachineStatus.DOWN
    assert m.model_dump(exclude={"condition"})["status"] == "down"


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
    assert (observable["id"], observable["status"]) == ("CNC-04", "down")
    assert "condition" not in observable
    assert "bearing_health" not in str(observable)
