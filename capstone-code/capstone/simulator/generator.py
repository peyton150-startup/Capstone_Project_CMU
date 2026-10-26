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

# How fast a worn bearing progresses. "compressed" is the original curve (fault
# start to failure in about 9-28 hours of running), kept as the default so every
# existing case and result stays the same. "three_day" follows the engineering
# feedback of 2026-10-23: a quiet stretch first, then a visible ramp from onset
# to failure of about three operating days (4,320 one-minute ticks of running).
BEARING_PROFILES = ("compressed", "three_day")
# three_day: the same seeded rate draw, scaled so that the median onset-to-failure
# time is about 4,320 running ticks (measured on seeds 1-40,
# tests/test_generator.py).
THREE_DAY_RATE_SCALE = 0.17
THREE_DAY_ONSET_HEALTH = 0.8  # below this, vibration starts to stand out of the noise
THREE_DAY_QUIET_FACTOR = 0.5  # before onset, wear runs at half the rate


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

    if fault == "bearing_degradation":
        rate = pick.uniform(0.0004, 0.0008)
        phases = {}
        if bearing_profile == "three_day":
            rate *= THREE_DAY_RATE_SCALE
            phases = {
                "onset_health": THREE_DAY_ONSET_HEALTH,
                "quiet_factor": THREE_DAY_QUIET_FACTOR,
            }
        sim.add_scenario(
            BearingDegradation(
                "fault",
                sim.rng,
                machine_id=machine_id,
                start_tick=start_tick,
                rate=rate,
                **phases,
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
