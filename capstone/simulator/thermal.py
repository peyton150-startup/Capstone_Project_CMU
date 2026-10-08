"""How warm a machine is, and how fast that changes.

Part of the factory's own physics: applied to every machine on every
tick by the simulator, whatever scenarios are running.
"""

from capstone.simulator.state import NORMAL_LOAD, MachineState, MachineStatus

OWN_HEAT_F = 43.0  # a healthy machine at normal load, above the air around it
LOAD_HEAT_F = 30.0  # per unit of load above normal
WEAR_HEAT_F = 45.0  # for a completely worn bearing
SPEED_HEAT_F = 40.0  # per unit of speed above standard: 15% fast is 6 °F


def settling_temperature(machine: MachineState, air_temperature: float) -> float:
    """Where the machine's temperature is heading if nothing changes."""
    if machine.status is not MachineStatus.RUNNING:
        return air_temperature
    wear = 1.0 - machine.condition.bearing_health
    work = LOAD_HEAT_F * (machine.load - NORMAL_LOAD)
    speed = SPEED_HEAT_F * (machine.speed_ratio - 1.0)
    return air_temperature + OWN_HEAT_F + work + speed + WEAR_HEAT_F * wear


def settle(machine: MachineState, air_temperature: float) -> MachineState:
    """Put the machine at its settling temperature, as if it had been like this for hours."""
    machine.temperature = settling_temperature(machine, air_temperature)
    return machine


def warm_or_cool(
    machine: MachineState, air_temperature: float, lag_ticks: float
) -> None:
    """Move one tick closer to the settling temperature. `lag_ticks` of 1 means at once."""
    gap = settling_temperature(machine, air_temperature) - machine.temperature
    machine.temperature += gap / lag_ticks
