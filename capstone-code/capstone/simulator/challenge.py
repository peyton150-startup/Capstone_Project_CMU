"""Opt-in compound investigation exercise; ordinary build_line stays unchanged."""

from datetime import datetime

from capstone.simulator.disturbances import SensorDrift, SensorDropout, TransientAnomaly
from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation, WrongSetting
from capstone.simulator.simulator import Simulator


def build_challenge(
    seed: int,
    *,
    machines: int | None = None,
    start: datetime = datetime(2026, 1, 5, 6, 0),
) -> Simulator:
    """Combine two physical faults with independent instrument disturbances.

    Repairing the worn bearing leaves the excessive speed setting unchanged.
    A second machine has a harmless vibration spike. A third has drifting
    temperature measurements and a short signal loss. All causes are hidden;
    existing tools expose only their consequences. The profile RNG has its own
    named stream so selecting targets does not shift normal factory variation.
    """
    # Variables:
    #   sim: A standard line to which the compound faults are added.
    #   choices: A separate random stream for choosing targets, so normal variation does
    #     not shift.
    #   target: The machine with the worn bearing and the wrong speed together.
    #   nuisance: The machine with a harmless vibration spike.
    #   instrument: The machine whose temperature sensor drifts and drops out.
    #   onset: The tick the physical faults begin.
    sim = build_line(seed, machines=machines, start=start)
    choices = sim.rng.stream("challenge.profile")
    target, nuisance, instrument = choices.sample(list(sim.state.machines), 3)
    onset = choices.randint(40, 80)
    sim.add_scenario(
        BearingDegradation(
            "challenge.bearing",
            sim.rng,
            machine_id=target,
            start_tick=onset,
            rate=0.0006,
        )
    )
    sim.add_scenario(
        WrongSetting(
            "challenge.speed",
            sim.rng,
            machine_id=target,
            start_tick=onset,
            factor=1.25,
        )
    )
    sim.add_scenario(
        TransientAnomaly(
            "challenge.spike",
            sim.rng,
            machine_id=nuisance,
            sensor="vibration",
            start_tick=onset + 10,
            duration=8,
            offset=5,
        )
    )
    sim.add_scenario(
        SensorDrift(
            "challenge.drift",
            sim.rng,
            machine_id=instrument,
            sensor="temperature",
            start_tick=onset,
            duration=180,
            per_tick=0.05,
        )
    )
    sim.add_scenario(
        SensorDropout(
            "challenge.dropout",
            sim.rng,
            machine_id=instrument,
            sensor="temperature",
            start_tick=onset + 60,
            duration=20,
        )
    )
    return sim
