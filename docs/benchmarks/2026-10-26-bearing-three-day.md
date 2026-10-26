# Bearing progression: the three-day profile (2026-10-26)

Calibration for `build_scenario(..., bearing_profile="three_day")`
(`capstone/simulator/generator.py`), from Brandon Reff's feedback recorded in
`docs/MVP_SCOPE.md` Future Work 8 (A). No model was called; simulator only.

## The question

Brandon: a worn bearing's vibration should stay near normal at first, then
climb continuously and somewhat faster, with the visible progression lasting
about three days. At the one-minute tick, three days is 4,320 ticks.

## What the old curve does (seeds 1-40, bearing fault forced)

| Profile | Quiet stretch: fault start to health 0.8 (running ticks, median) | Onset (health 0.8) to failure (health 0.1), running ticks: median (range) | Fault start to first vibration alarm, ticks (median) | Fault start to failure, ticks (median) |
|---|---|---|---|---|
| compressed (default, unchanged) | 222 | 725 (421-1,396) | 663 | 983 |
| three_day | 2,349 | **4,294** (2,683-6,241) | 5,007 | 6,975 |

So the old curve reaches failure in about 9 to 28 hours of running. The
three-day ramp is therefore *longer* than today's, not shorter; "faster" in the
feedback is read as the steeper climb after onset, not a shorter total life.

## Decisions taken (to confirm in the teaching session)

- **Operating days, not calendar days.** Wear already accrues only while the
  machine runs (`BearingDegradation.apply`), so the target is 4,320 *running*
  ticks; machines ran 86-100% of the time in these runs.
- **Onset at health 0.8.** Below it, the vibration sensor's wear term
  (`6 x (1 - health)^2`, 0.24 at onset) starts to stand out of its noise
  (standard deviation 0.15).
- **Quiet phase at half the rate** (`quiet_factor` 0.5), so wear before onset
  is slower and the slope steepens at onset.
- **Rate scale 0.17** of the same seeded draw (0.0004-0.0008 per tick): 0.16
  gave a median of 4,594; 0.17 gave 4,294.
- **Opt-in.** The default stays `compressed`, so every known-answer case,
  held-out seed and earlier result is unchanged.

## How to repeat

```python
# uv run python <this script> three_day
import sys, statistics
from capstone.simulator.generator import build_scenario

profile, rows = sys.argv[1], []
for seed in range(1, 41):
    sim = build_scenario(seed, fault="bearing_degradation", bearing_profile=profile)
    (truth,) = sim.ground_truth()
    m = sim.state.machines[truth.machine_id]
    run = 0
    onset = None
    for _ in range(20_000):
        sim.step()
        if sim.clock.tick > truth.start_tick and m.status.name == "RUNNING":
            run += 1
        h = m.condition.bearing_health
        if onset is None and h <= 0.8:
            onset = run
        if h <= 0.1:
            break
    rows.append((onset, run - onset))
print(statistics.median(q for q, _ in rows), statistics.median(r for _, r in rows))
```

## Not done

- Experiments cannot yet choose the profile (`experiment run` builds the
  default). Before they can: the monitor (`agent/monitor.py`,
  `wait_for_anomaly`) stops waiting at tick 4,000 and starts a routine check,
  but a three-day fault's first alarm comes at a median of about 5,000 ticks
  after the fault starts, so most episodes would begin before any alarm. The
  monitor's limit and the agent's evidence windows need a decision first.
- Brandon has not reviewed the new curve.
