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
| 7 | Scenario abstraction          | yes    | yes              | yes         | yes               | `capstone/simulator/scenarios.py` — COMPLETE |
| 8 | BearingDegradation scenario   | yes    | yes              | yes         | yes               | `capstone/simulator/scenarios.py` — COMPLETE |
| 8b | Machine failure transition (goes DOWN) | yes | yes           | yes         | yes               | `simulator.py` (`_apply_consequences`) — COMPLETE |
| 9a | Ground truth record           | yes    | yes              | yes         | yes               | `capstone/simulator/ground_truth.py` — COMPLETE |
| 9b | Observation boundary (read-only tools) | yes |             |             |                   | gate question asked, awaiting answer. Actions are a later row |

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
- **Session 3 (cont.)** — Scenario gate passed after re-teaching
  (developer was unsure why a scenario may not write a fake reading;
  then correctly stated that a heavy-load scenario changes only the load
  for a few ticks and restores it, and that the sensor produces the
  5.0 mm/s reading). Implemented `Scenario` base, `add_scenario`, and
  the scenario loop in `_update_reality`; 7 tests, 63 total. The
  test-only `Simulator` subclass is gone (debt from row 5 cleared).
  `load` is NOT in `MachineState` yet — it belongs with the false-alarm
  scenario.
- **Session 3 (cont.)** — Scenario post-implementation gate passed
  (developer: scenarios run before the sensors, can change anything in
  FactoryState, cannot change an event's tick). Claude filled in: they
  run after the clock advances, and cannot touch the clock, reading log
  or event log at all. Taught BearingDegradation (wear only while
  RUNNING, linear health loss with seeded variation, failure transition
  deferred to its own increment); gate question asked.
- **Session 3 (cont.)** — BearingDegradation gate passed on the second
  attempt. First answer put the curve in the noise and a temperature
  function inside the scenario; re-taught with the worked wear-squared
  table and the one-job-per-component split. Developer then stated that
  the curve comes from the equation that squares wear, and that the
  scenario changes only bearing health, with vibration and temperature
  readings following from it. Implemented `BearingDegradation` (wear
  only while RUNNING, seeded variation, clamped at 0); 14 tests, 77
  total. Seed 42 sample run: start tick 100, rate 0.001, first alarm at
  tick 714. Debt: no failure transition; a wrong `machine_id` surfaces
  as a KeyError on the first active tick, not at construction.
- **Session 3 (cont.)** — BearingDegradation post-implementation gate
  passed (developer: health holds while idle because the machine is not
  running; vibration is high before, drops during idle, resumes after;
  the agent should read the machine's idle status). Claude corrected two
  points: after restart vibration returns to the same elevated level as
  before the pause, not to normal; and the dangerous wrong conclusion is
  "the problem went away", not "the machine is broken". Also confirmed
  on request that health never drops without a scenario (no normal wear;
  deliberate). Taught the failure transition; gate question asked.
- **Session 3 (cont.)** — Failure transition gate passed first time
  (developer: it does not belong in BearingDegradation, which should
  only change bearing health, and other causes of failure should not
  depend on it; the event says only that the machine stopped, because
  working out why is the agent's job). Implemented a consequences stage
  in `step()` between scenarios and sensors; 8 tests, 85 total. Seed 42
  sample run: fault starts tick 100, first alarm 714, machine stops 995.
  Debt: failure level is one number for all machines; only RUNNING
  machines fail; nothing can bring a DOWN machine back yet.
- **Session 3 (cont.)** — Failure transition post-implementation gate
  passed (developer raised unprompted that status is observable; then:
  event log first mentions CNC-04 at tick 714, and the reading log is
  what the agent needs to date the fault). Claude corrected: status
  would read "down", not "idle"; and the fault is not visible in the
  readings at tick 100 itself — it emerges from the noise around tick
  250-300 and the agent must extrapolate back. Split row 9 into 9a
  (ground truth) and 9b (tools). Taught 9a; gate question asked.
- **Session 3 (cont.)** — Ground truth gate passed after re-teaching
  part 1 (developer knew at once that tools reading the ground truth
  would hand the agent the answers; was unsure why `bearing_health` is
  not enough, then answered on the false-alarm case that the fact has to
  come from the ground truth). Claude corrected again that sensor
  readings are not in FactoryState. Implemented `GroundTruth` (frozen),
  abstract `Scenario.ground_truth()`, `Simulator.ground_truth()`;
  8 tests, 93 total. Debt: `Simulator.ground_truth()` is a public method
  on the same object the tools will wrap — 9b must make it unreachable;
  `fault` is free text; no end tick or cause field yet.
- **Session 3 (cont.)** — Ground truth post-implementation gate passed
  (developer: it comes from the scenarios, it is what will go wrong, and
  only evaluation may read it — no agent tools). Claude filled in why it
  does not change: it is built from settings fixed when the scenario is
  created. Taught the read-only observation tools (allow-list vs
  block-list); gate question asked.
