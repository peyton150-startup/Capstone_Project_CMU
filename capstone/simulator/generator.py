"""Seeded scenarios: one call turns a seed into a factory with one hidden fault.

The seed decides everything: the line (through `build_line`), which of
the four MVP faults is present, where it is (a machine or a material
batch), when it starts and how strong it is. The choice is drawn from its
own stream, `generator`, so it never shifts any other stream. The answer
is kept where it always is, in the scenario's ground truth.
"""

from capstone.simulator.line import build_line
from capstone.simulator.scenarios import (
    BadMaterialBatch,
    BearingDegradation,
    FalseAlarm,
    WrongSetting,
)
from capstone.simulator.simulator import Simulator

FAULTS = ("bearing_degradation", "bad_material_batch", "wrong_setting", "false_alarm")

# Faults start inside this window, so the agent has a normal stretch to compare against.
EARLIEST_START, LATEST_START = 200, 600

# Smaller batches than the standard line's 25, so a bad batch arrives (and ends)
# within a working day rather than two.
JOBS_PER_BATCH = 10


def build_scenario(
    seed: int, *, machines: int | None = None, fault: str | None = None
) -> Simulator:
    """A standard line with one seeded fault added after it. Not yet run: the clock is at 0.

    `fault` forces which of the four faults appears (for tests and
    balanced experiments); everything else still comes from the seed.
    """
    if fault is not None and fault not in FAULTS:
        raise ValueError(f"unknown fault {fault}; choose from {', '.join(FAULTS)}")
    sim = build_line(seed, machines=machines, jobs_per_batch=JOBS_PER_BATCH)
    pick = sim.rng.stream("generator")
    chosen = pick.choice(FAULTS)
    fault = fault or chosen
    machine_id = pick.choice(sorted(sim.state.machines))
    start_tick = pick.randint(EARLIEST_START, LATEST_START)

    if fault == "bearing_degradation":
        rate = pick.uniform(0.0004, 0.0008)
        sim.add_scenario(
            BearingDegradation(
                "fault",
                sim.rng,
                machine_id=machine_id,
                start_tick=start_tick,
                rate=rate,
            )
        )
    elif fault == "wrong_setting":
        factor = pick.choice((0.80, 0.82, 1.18, 1.20))
        sim.add_scenario(
            WrongSetting(
                "fault",
                sim.rng,
                machine_id=machine_id,
                start_tick=start_tick,
                factor=factor,
            )
        )
    elif fault == "bad_material_batch":
        batch = pick.randint(2, 3)
        risk = pick.uniform(0.35, 0.50)
        sim.add_scenario(
            BadMaterialBatch("fault", sim.rng, batch_number=batch, added_risk=risk)
        )
    else:
        duration = pick.randint(3, 8)
        sim.add_scenario(
            FalseAlarm(
                "fault",
                sim.rng,
                machine_id=machine_id,
                start_tick=start_tick,
                duration=duration,
            )
        )
    return sim
