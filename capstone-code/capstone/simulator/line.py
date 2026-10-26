# The standard production line, built from a seed in one call.
# Responsibility: wire machines, sensors, and alarms together before any fault is added.
"""The standard factory: one call that sets up a complete, realistic line.

Everything a normal day needs is wired in here, in the right order, so a
run cannot be built with a piece missing. Unless a size is given, the
seed decides how many machines the line has. Faults are added afterwards by
the caller, which keeps them running after the line's own scenarios.
"""

from datetime import datetime, timedelta

from capstone.simulator.events import ThresholdAlarm
from capstone.simulator.maintenance import past_maintenance
from capstone.simulator.scenarios import AmbientTemperature, LoadingDoor, ProductionLine
from capstone.simulator.sensors import (
    FactoryThermometer,
    FollowingErrorSensor,
    LoadSensor,
    PowerSensor,
    TemperatureSensor,
    VibrationSensor,
)
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState

MIN_MACHINES, MAX_MACHINES = 3, 8

# Working time per job at each position on the line. Mildly uneven on
# purpose: the second machine is the slowest step, so some waiting is normal.
STANDARD_TICKS_PER_JOB = (60, 70, 55, 65, 60, 68, 58, 62)

# Spindle speed each position is meant to run at, in rpm. Different on every
# machine, so a speed means nothing without knowing that machine's own normal.
STANDARD_SPEEDS = (1000.0, 850.0, 1200.0, 900.0, 1100.0, 950.0, 1050.0, 800.0)

WARMEST_HOUR = 16  # 4 pm


def machine_names(machines: int) -> list[str]:
    return [f"CNC-{position:02d}" for position in range(1, machines + 1)]


def build_line(
    seed: int,
    *,
    machines: int | None = None,
    start: datetime = datetime(2026, 1, 5, 6, 0),
    tick_duration: timedelta = timedelta(minutes=1),
    ticks_per_job: tuple[int, ...] | None = None,
    thermal_lag_ticks: float = 20.0,
    vibration_alarm: float = 4.5,
    following_error_alarm: float = 20.0,
    time_variation: int = 2,
    jobs_per_batch: int = 25,
) -> Simulator:
    sim = Simulator(seed, start, tick_duration, thermal_lag_ticks=thermal_lag_ticks)

    if machines is None:
        # The seed picks the size. Its own stream, so nothing else shifts.
        machines = sim.rng.stream("line.size").randint(MIN_MACHINES, MAX_MACHINES)
    if not MIN_MACHINES <= machines <= MAX_MACHINES:
        raise ValueError(
            f"a line has {MIN_MACHINES} to {MAX_MACHINES} machines, not {machines}"
        )
    times = ticks_per_job or STANDARD_TICKS_PER_JOB[:machines]
    if len(times) != machines:
        raise ValueError("ticks_per_job needs one entry per machine")
    names = machine_names(machines)

    ticks_per_day = round(timedelta(days=1) / tick_duration)
    first_peak = start.replace(hour=WARMEST_HOUR, minute=0, second=0, microsecond=0)
    warmest_tick = round((first_peak - start) / tick_duration) % ticks_per_day
    sim.add_scenario(
        AmbientTemperature(
            "ambient", sim.rng, ticks_per_day=ticks_per_day, warmest_tick=warmest_tick
        )
    )
    sim.add_scenario(LoadingDoor("door", sim.rng))

    for name, per_job, speed in zip(names, times, STANDARD_SPEEDS):
        sim.add_machine(
            MachineState(id=name, ticks_per_job=per_job, standard_speed=speed)
        )
        for sensor in (
            VibrationSensor,
            TemperatureSensor,
            LoadSensor,
            PowerSensor,
            FollowingErrorSensor,
        ):
            sim.add_sensor(sensor(name, sim.rng))
    sim.add_factory_sensor(FactoryThermometer(sim.rng))
    # Past service records. Their own stream, drawn before any fault exists.
    sim.state.maintenance_history = past_maintenance(
        list(names), start, sim.rng.stream("maintenance.history")
    )
    sim.add_alarm(ThresholdAlarm("vibration", vibration_alarm))
    # The servo controller's own "excess following error" alarm.
    sim.add_alarm(ThresholdAlarm("following_error", following_error_alarm))

    # After the machines exist, and before any fault the caller adds.
    sim.add_scenario(
        ProductionLine(
            "line",
            sim.rng,
            machine_ids=names,
            time_variation=time_variation,
            jobs_per_batch=jobs_per_batch,
        )
    )
    return sim
