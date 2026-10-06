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
| 9b | Observation boundary (read-only tools) | yes | yes         | yes         | yes               | `capstone/tools/observation.py` — COMPLETE |
| 10 | TemperatureSensor (second evidence source) | yes | n/a (§2.2) | yes         | yes               | `capstone/simulator/sensors.py`, in °F at developer's request — COMPLETE |
| 10a | Operating load: `load` in MachineState, sensors respond, LoadSensor | yes | yes  | yes         | yes               | `state.py`, `sensors.py` — COMPLETE |
| 10a2 | Load–wear coupling: heavy load wears the bearing faster; worn bearing nudges the load reading up | yes | yes | yes   | yes               | `scenarios.py`, `sensors.py` — COMPLETE |
| 10b | Workload variation over time (what changes `load`) | yes | yes       | yes         | yes               | `scenarios.py` (`Workload`) — COMPLETE; stands in for jobs until row 12 |
| 10b2 | "Job started" event when a machine's work changes | yes | yes      | yes         | yes               | `state.py` (`job_number`), `scenarios.py`, `simulator.py` — COMPLETE |
| 10c | Ambient temperature drift (shared by all machines) | yes |        |             |                   | gate question re-asked in a new form, awaiting the developer's own answer. Design: `AmbientTemperature`, daily cycle + slow seeded drift |
| 10d | Temperature warm-up / cool-down lag |            |                  |             |                   | agreed with developer |
| 10e | Standard line builder: one function that sets up machines, all sensors, alarms and workload, so every run has varying load | | | |             | proposed after developer asked that load vary in every scenario |
| 11 | Maintenance action + advancing time through the tools | |      |             |                   | proposed next: closes action → change → verification |
| 12a | Assembly line: jobs with one identity move machine to machine in order; a machine's load comes from its job | |  |             |                   | NEXT after 10c, at developer's request. Replaces the `Workload` stand-in and the per-machine `job_number` |
| 12b | Job events and a job-history tool for the agent |      |                  |             |                   | follows 12a |
| 12c | Quality inspections / defect rate         |      |                  |             |                   | follows 12b; needed for the material-batch scenario |

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
- **Session 3 (cont.)** — Observation tools gate passed (developer chose
  the build-from-scratch version on a hunch; after the worked example,
  explained that a newly added machine field leaves that list untouched,
  whereas copy-everything would pass it through because it had not been
  accounted for). Implemented `ObservationTools` with `get_time`,
  `list_machines`, `get_readings`, `get_events`; 10 tests, 103 total,
  including a full-run leak test. Debt: `_sim` is private by convention
  only — real enforcement comes when the agent is given just these four
  functions; an unknown sensor name returns an empty list rather than an
  error; each call scans the whole log; nothing lets the agent advance
  time yet.
- **Session 3 (cont.)** — Observation tools post-implementation gate
  passed (developer: the agent can list machines and get CNC-04's
  readings; it cannot get bearing health or the degradation rate; the
  observation is built, not copied). Claude corrected: the tools object
  does hold the simulator — the protection is that only named fields are
  passed out and the agent is handed only the tools. Developer asked,
  unprompted, whether the agent can find the stop and backtrack through
  the reading log: yes, that is the intended investigation path. Rows
  1-9 complete. Proposed rows 10-12 from MVP_SCOPE.md; developer has not
  yet agreed the order.
- **Session 3 (cont.)** — TemperatureSensor built as a pattern repeat
  (CLAUDE.md §2.2), in Fahrenheit at the developer's request: 115 °F
  healthy, +45 °F per unit of wear (straight line), 72 °F when not
  running, noise 1 °F. Developer correctly said BearingDegradation needs
  no change, but expected `Simulator.step()` and `ObservationTools` to
  need changes — they do not (only `sensors.py` changed); explained, to
  be re-checked in the post-implementation question. 6 tests, 109 total.
  Debt: no warm-up or cool-down lag.
- **Session 3 (cont.)** — Developer noticed that temperature is too
  clean a signal (only bearing wear moves it) and asked how to make the
  agent's job harder while staying realistic. Agreed to add, before the
  maintenance action: operating load, room temperature drift, and
  warm-up/cool-down lag (rows 10a-10d). Taught 10a; gate question asked.
  Row 10's re-explain questions were not answered and are still owed.
- **Session 3 (cont.)** — TemperatureSensor re-explain passed on the
  architecture question (developer: sensors are one kind of object the
  other modules already account for, so a new one is just another entry
  in the list, not a new component). The cross-checking question was
  not answered separately; it is superseded by the load gate's first
  question, which tests the same idea with load in the picture.
- **Session 3 (cont.)** — Load gate passed (developer: worry about the
  machine at normal load, because temperature should not be that high
  for a routine job; separate per-sensor ideas of load would duplicate
  it, and if they drifted apart there would be no way to tell which was
  right or reconcile them). Implemented `MachineState.load` (0-1,
  default 0.5), load terms in `VibrationSensor` (+1.5 mm/s per unit) and
  `TemperatureSensor` (+30 °F per unit), and `LoadSensor` (%); 10 tests,
  119 total. One older test in `test_state.py` copied the machine minus
  `condition` and so picked up `load` automatically — the copy-and-
  remove behaviour from the tools gate, seen for real; expectation
  updated. `ObservationTools` needed no change and does not expose
  `load`. Debt: nothing changes load yet (row 10b); bearing wear does
  not raise load; load does not speed up wear.
- **Session 3 (cont.)** — Developer brought outside feedback that the
  two load simplifications are unrealistic (a worn bearing does raise
  motor load a little; heavy load does shorten bearing life, steeply).
  Agreed to model both as row 10a2. Taught it (wear rate scales with
  load cubed; friction term lives in `LoadSensor`, not in `load`); gate
  question asked. Row 10a's re-explain question is still owed.
- **Session 3 (cont.)** — Load re-explain passed (developer: the two
  explanations are higher load or a degraded bearing). The deciding
  reading was not named this time; the developer had used the load
  sensor to decide the two-machine case in the pre-implementation gate,
  so Claude filled it in. Row 10a2 gate question still awaiting answer.
- **Session 3 (cont.)** — Load–wear coupling gate passed (developer
  chose the sensor-side friction term because it does not change load
  for everyone, only the reading; asked how load then speeds up wear —
  explained it lives in `BearingDegradation`, which reads `load` and
  still writes only health; developer then said the heavier-loaded
  machine fails first). Claude filled in the two failure modes of the
  other option (double counting, runaway loop). Implemented wear scaled
  by (load / 0.5) ** 3 and `LoadSensor` friction of 8 × wear²; 9 tests,
  128 total. Sample: same fault from tick 100, machine at 80% load stops
  at tick 319, machine at 30% load is still at health 0.81 at tick 1000.
  Debt: the cube is steep and uncapped; friction does not depend on load.
- **Session 3 (cont.)** — Load–wear coupling re-explain passed on the
  second attempt. Developer first said the load gets heavier as the
  machine wears; corrected (the reading rises, `load` does not).
  Developer then stated that the actual load is 80 and the difference is
  the wear, and confirmed unprompted that friction is not tracked as its
  own value and need not be. Taught workload variation (10b); gate
  question asked.
- **Session 3 (cont.)** — Developer's direction on 10b: load must vary
  on every machine in every run, not only in one scenario; block-based
  load is acceptable as a starter, with load driven by what the machine
  is actually making to follow (row 12). Note: MVP_SCOPE.md says one
  product type; whether to vary by product or by job size is undecided.
  Added proposed row 10e (standard line builder). 10b gate questions
  still awaiting answers.
- **Session 3 (cont.)** — Workload gate passed (developer: a jump means
  another product is on the machine — too big and sudden to be wear,
  which is gradual; workload should run first, otherwise degradation
  runs and then the product is switched for that tick). Implemented
  `Workload` (blocks of 30-90 ticks, load 0.3-0.8, own stream per
  machine); scenarios may now declare no ground truth; 9 tests, 137
  total. Debt: run order (workload before degradation) is a convention
  to be enforced by the line builder (10e); load changes instantly; the
  agent sees load only via the load sensor, with no job record to
  explain a change (row 12).
- **Session 3 (cont.)** — Workload re-explain passed with gaps filled by
  Claude. Developer: the agent looks at the load, and also the vibration;
  confirmed by asking that two scenarios can run at once. Claude
  corrected that vibration rises with load too, so the second check is
  the shape of the change (step vs. creep), and explained why a changing
  workload hides a slow fault (job steps are larger than the drift, so
  the agent must compare periods of similar load). Developer proposed
  recording load changes in the event log; agreed as row 10b2, taught,
  gate question asked.
- **Session 3 (cont.)** — Job-event gate passed on the second attempt.
  Developer first thought "machine stopped" was written by a reading
  threshold and rightly objected that a threshold cannot work for load;
  re-taught the two event routes (alarm on a reading vs. the simulator
  noticing a state change). Developer then stated that the simulator
  reads the job number, finds it different, and adds the entry to the
  event log. Implemented `MachineState.job_number`, `Workload` raising
  it, and `Simulator._record_new_jobs`; 9 tests, 146 total. The
  copy-minus-condition test in `test_state.py` broke a second time on
  the new field and was rewritten to check only what it means to check.
  Debt: the event carries no job identity or description (row 12).
- **Session 3 (cont.)** — Developer proposed tracking one job number
  through the machines (a job travelling down the line). Agreed as the
  design for row 12, not built now. Open items: (1) developer's go-ahead
  on the fix so a machine that is not running starts no new jobs — found
  in the 10b2 sample run, where a DOWN machine logged nine more jobs;
  (2) row 10b2 re-explain.
- **Session 3 (cont.)** — Job-event re-explain passed (developer: with a
  job event it is just a new job; with none it could be wear and should
  be investigated). Developer approved the fix: `Workload` now starts no
  new job on a machine that is not running and resumes when it runs
  again; 2 tests, 148 total. Taught room temperature drift (10c); gate
  question asked.
- **Session 3 (cont.)** — Developer asked for the machines to form an
  assembly line with a job moving through them (e.g. job 117: CNC-01 →
  CNC-02 → CNC-04). Agreed and moved up: row 12 split into 12a-12c, with
  12a next after 10c. Rows 10d (thermal lag), 10e (line builder) and 11
  (maintenance action) follow the line work; 10e will likely fold into
  12a. Row 10c gate question still awaiting answer.
- **Session 3 (cont.)** — Developer pasted an outside review of row 10c.
  Adopted from it: name the scenario `AmbientTemperature` (not
  `RoomTemperature`); make the daily cycle vary a little from day to day
  with a slow seeded drift rather than a perfect repeating curve. Noted
  for later, not now: HVAC cycling, door openings, temperature zones.
  The paste also contained answers to both gate questions; per CLAUDE.md
  §1.1 these do not count as the developer's own explanation, so the
  gate was re-asked with a different example.
