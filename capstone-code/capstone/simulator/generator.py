"""Seeded scenarios: one call turns a seed into a factory with one hidden fault.

The seed decides everything: the line (through `build_line`), which of
the four MVP faults is present, where it is (a machine or a material
batch), when it starts and how strong it is. The choice is drawn from its
own stream, `generator`, so it never shifts any other stream. The answer
is kept where it always is, in the scenario's ground truth.
"""

from capstone.faults import (
    BEARING_PROFILES,
    BY_KIND,
    FAULT_KINDS,
    THREE_DAY_ONSET_HEALTH,
    THREE_DAY_QUIET_FACTOR,
    THREE_DAY_RATE_SCALE,
    FaultPlace,
)
from capstone.simulator.line import build_line
from capstone.simulator.simulator import Simulator

# The faults a seed can have, from the fault packs (`capstone/faults.py`).
FAULTS = FAULT_KINDS

# Faults start inside this window, so the agent has a normal stretch to compare against.
EARLIEST_START, LATEST_START = 200, 600

# Smaller batches than the standard line's 25, so a bad batch arrives (and ends)
# within a working day rather than two.
JOBS_PER_BATCH = 10

# Re-exported: the bearing profiles now live with the bearing pack.
__all__ = [
    "BEARING_PROFILES",
    "EARLIEST_START",
    "FAULTS",
    "JOBS_PER_BATCH",
    "LATEST_START",
    "THREE_DAY_ONSET_HEALTH",
    "THREE_DAY_QUIET_FACTOR",
    "THREE_DAY_RATE_SCALE",
    "build_scenario",
]


def build_scenario(
    seed: int,
    *,
    machines: int | None = None,
    fault: str | None = None,
    bearing_profile: str = "compressed",
) -> Simulator:
    """A standard line with one seeded fault added after it. Not yet run: the clock is at 0.

    `fault` forces which of the four faults appears (for tests and
    balanced experiments); everything else still comes from the seed.
    `bearing_profile` picks how fast a bearing fault progresses
    (`BEARING_PROFILES`); it changes nothing for the other faults and draws
    nothing extra, so no stream moves.
    """
    if fault is not None and fault not in FAULTS:
        raise ValueError(f"unknown fault {fault}; choose from {', '.join(FAULTS)}")
    if bearing_profile not in BEARING_PROFILES:
        raise ValueError(
            f"unknown bearing profile {bearing_profile}; "
            f"choose from {', '.join(BEARING_PROFILES)}"
        )
    sim = build_line(seed, machines=machines, jobs_per_batch=JOBS_PER_BATCH)
    pick = sim.rng.stream("generator")
    chosen = pick.choice(FAULTS)
    fault = fault or chosen
    machine_id = pick.choice(sorted(sim.state.machines))
    start_tick = pick.randint(EARLIEST_START, LATEST_START)

    place = FaultPlace(machine_id, start_tick, bearing_profile)
    sim.add_scenario(BY_KIND[fault].build(sim, pick, place))
    return sim
