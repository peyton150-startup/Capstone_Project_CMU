# Progress Log

Two separate completion criteria per component (see CLAUDE.md §1):

- **Implemented** — code written, tests passing.
- **Understood** — the developer explained the component back correctly
  (both the pre-implementation gate and the post-implementation re-explain).

A component is complete only when both columns are checked.

| # | Component                     | Taught | Understood (pre) | Implemented | Understood (post) | Notes |
|---|-------------------------------|--------|------------------|-------------|-------------------|-------|
| 1 | SimulationClock               | yes    | yes              | yes         | yes               | `capstone/simulator/clock.py` — COMPLETE |
| 2 | Deterministic random source   | yes    | yes              | yes         | yes               | `capstone/simulator/rng.py` — COMPLETE |
| 3 | Machine identity / MachineState | yes  | yes              | yes         | yes               | `capstone/simulator/state.py` — COMPLETE |
| 4 | Sensor abstraction + 1 reading | yes   | yes              | yes         | yes               | `capstone/simulator/sensors.py` — COMPLETE |
| 5 | FactoryState + step()         | yes    | yes              | yes         | yes               | `state.py` (`FactoryState`), `simulator.py` (`Simulator.step`) — COMPLETE |
| 6 | Event log                     | yes    | yes              | yes         | yes               | `capstone/simulator/events.py` — COMPLETE |
| 7 | Scenario abstraction          | yes    |                  |             |                   | gate question asked, awaiting answer |
| 8 | BearingDegradation scenario   |        |                  |             |                   | |
| 9 | Ground truth + observation boundary (tools) | |          |             |                   | |

## Session notes

- **Session 1** — Repo was empty. Created CLAUDE.md, package skeleton,
  this log. Recommended SimulationClock as the first component; asked
  the first comprehension question. No simulator logic implemented.
- **Session 1 (cont.)** — Clock gate passed (developer explained single
  ownership of time, intermittent same-seed failures with multiple
  counters, and corrupted-ordering consequences for the agent).
  Implemented `SimulationClock` + 8 tests, all passing. Deliberate
  simplification: `clock.py` is a module, not the `clock/` package in
  CLAUDE.md §6; promote it if it grows.
- **Session 1 (cont.)** — Random source gate passed after two corrections
  (clock does not advance streams; sequence depends on `(seed, name)`,
  not seed alone — developer then correctly derived that renaming a
  stream changes its history). Implemented `RandomSource` + 9 tests, 17
  total passing. Stream names are frozen contracts once histories are
  recorded.
- **Session 1 (cont.)** — MachineState gate passed after teaching the
  cause-vs-evidence distinction (developer: "bearing_health is the
  beginning of the chain, vibration is the end — what the sensor says").
  Implemented `MachineStatus`, `MachineCondition` (hidden), `MachineState`
  with pydantic bounds validation; 11 tests, 28 total passing.
- **Session 2** — Sensor gate passed (developer explained read-only role,
  shared-reality correlation, status dependence, many-causes-one-symptom;
  Claude filled in noise → trend-over-readings). Implemented
  `SensorReading` (frozen), `Sensor` base, `VibrationSensor` with
  monotonic squared wear curve and status dependence; 11 tests, 39 total.
- **Session 3** — Sensor post-implementation gate passed. Needed
  teaching first on `super().__init__`, `gauss`, and noise vs. drift
  (corrected: bearings do not degrade unless a scenario writes to them;
  noise averages out as `noise_sd / sqrt(N)`). Developer then correctly
  judged that the same 3.1 mm/s reading implicates CNC-01 (baseline 2.0)
  but not CNC-04 (baseline 3.0), and that the agent must compare a
  machine against its own past readings. Claude filled in: 3-4 readings
  is too few against the noise, and per-sensor constructor parameters
  are what rule out a single global threshold. Taught FactoryState +
  `step()`; gate question asked. Tests run under Python 3.13 on this
  machine (3.11 not installed).
- **Session 3 (cont.)** — FactoryState + `step()` gate passed after
  several corrections (FactoryState holds truth, not how it changes;
  the log holds evidence, not past states; readings are evidence, not a
  partial copy of state). Developer derived that read-then-update logs
  the undamaged bearing at tick 50 and the damage at 51, and that
  update-then-read records damage in the step it happens. Claude filled
  in: the tick stamp, not the delay, is what makes the other ordering
  wrong. Implemented `FactoryState`, `Simulator` with `step()`; 9 tests,
  48 total. Debt: `_update_reality` is an empty hook, and the ordering
  test overrides it in a subclass until scenarios exist (row 7).
- **Session 3 (cont.)** — `step()` post-implementation gate passed
  (developer: tick first, damage before the reading, both sensors read
  and write to the reading log). Claude filled in where each result
  lands (clock / FactoryState / log). Taught the event log, with a
  vibration threshold alarm as the first event; gate question asked.
- **Session 3 (cont.)** — Event log gate passed (developer: an alarm on
  `bearing_health` would hint the hidden truth to the agent; an alarm
  can fire on a healthy machine and that ambiguity is wanted). Developer
  proposed heavy load as the cause; load is not modelled yet — candidate
  for the unrelated-anomaly source in CLAUDE.md §5.1. Implemented
  `Event` (frozen), `EventLog` (append-only, tick-ordered),
  `ThresholdAlarm`, and an alarm stage in `step()`; 9 tests, 57 total.
- **Session 3 (cont.)** — Event log post-implementation gate passed.
  Developer first attributed "readings show it first" to the alarm being
  appended after the reading within a step; corrected (same tick — the
  threshold is the reason). Developer then read off a worked table that
  the event log says nothing about CNC-04 at tick 450 and that about
  0.40 health remains at the first alarm. Taught the Scenario
  abstraction; gate question asked.
