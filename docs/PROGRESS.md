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
| 10c | Ambient temperature drift (shared by all machines) | yes | yes    | yes         | yes               | `state.py` (`ambient_temperature`), `scenarios.py` (`AmbientTemperature`), `sensors.py` — COMPLETE |
| 10c2 | Loading door opening: a short ambient disturbance plus an event | yes | yes | yes       | yes               | `state.py` (`door_open`, `door_cooling`, `air_temperature`), `scenarios.py` (`LoadingDoor`), `simulator.py`, `events.py` — COMPLETE |
| 10c3 | Factory thermometer: a sensor for air temperature, not attached to a machine, readable by the agent | yes | yes | yes     | yes               | `sensors.py` (`FactoryThermometer`), `simulator.py`, `tools/observation.py` (`get_factory_readings`) — COMPLETE |
| 10d | Temperature warm-up / cool-down lag | yes        | yes              | yes         | yes               | `thermal.py` (new), `state.py` (`temperature`), `sensors.py`, `simulator.py` — COMPLETE |
| 10e | Standard line builder: `build_line(seed, machines=3..8)` sets up named machines, all sensors, thermometer, alarm, ambient, door, production line, thermal lag | n/a (§2.2 wiring) | n/a | yes | | `capstone/simulator/line.py`; built early at developer's request; wiring only, no gate required — COMPLETE |
| 11a | Letting time pass: a `wait(ticks)` tool, separate from the read-only tools | yes |  |           |                   | gate question asked, awaiting answer |
| 11b | Maintenance action: replace a bearing (downtime, health restored, the fault ends) | |    |             |                   | after 11a |
| 11c | Approval: the agent proposes an action, a human approves, then it is applied | |        |             |                   | after 11b |
| 12a | Assembly line: jobs with one identity move machine to machine in order; a machine's load comes from its job | yes | yes | yes      | yes               | COMPLETE. `state.py` (`Job`), `scenarios.py` (`ProductionLine`), `simulator.py`; awaiting post-implementation re-explain (re-asked in a new form). Idle-time issue resolved: working time is now each machine's own `ticks_per_job`. Replaces the `Workload` stand-in and the per-machine `job_number` |
| 12b | Job events and a job-history tool for the agent | yes  | yes              | yes         |                   | `simulator.py` (`_record_job_events`), `events.py` (`job_id`), `state.py` (`line`), `tools/observation.py` (`get_job_history`, `job_id` in `list_machines`) — COMPLETE (understood post: yes) |
| 12b2 | A worn machine works more slowly, so its jobs take extra ticks; natural variation of ±2 ticks on the standard line | yes | yes       | yes         |                   | `scenarios.py` (`working_speed`, `time_variation`), `state.py` (`job_work`, `job_done`), `line.py` — COMPLETE (understood post: yes) |
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
- **Session 3 (cont.)** — Ambient gate passed in the developer's own
  words (it stays in the factory state and others read it from there
  without storing it; CNC-02 cooling less than its neighbours may have a
  wear issue, because heat from wear offsets the cooling of the
  factory). Implemented `FactoryState.ambient_temperature`,
  `AmbientTemperature` (daily cycle, warmest ~4 pm, plus slow seeded
  drift), and `TemperatureSensor` measuring from the air; 10 tests, 158
  total. Developer asked for a loading-door scenario with an event; added
  as row 10c2. Debt: `warmest_tick` assumes a 6 am start with one-minute
  ticks; `Sensor.read` takes ambient as a keyword — a second shared fact
  would want a small environment object; no thermometer for the agent.
- **Session 3 (cont.)** — Ambient re-explain passed (developer: look at
  load, see what the building temperature is, then vibration should tell
  the story of the wear). Claude filled in that the agent has no
  thermometer, so "the building temperature" has to be read off the
  other machines. Taught the loading door (10c2); gate question asked.
- **Session 3 (cont.)** — Developer asked whether ambient temperature is
  a hidden field; explained the three kinds of state (secrets, plain
  facts, measured conditions) and that ambient is unmeasured by choice.
  Developer decided to add a factory thermometer (row 10c3, after the
  door). 10c2 gate still awaiting answer.
- **Session 3 (cont.)** — Loading door gate passed (developer: ambient
  first and the door second; leave the season out and make the door a
  set cooling; "the factory state would notice the door opened" —
  corrected: the state only holds the door, the simulator's `step()`
  notices). DESIGN CHANGE DURING IMPLEMENTATION, explained to the
  developer: the door does not subtract from `ambient_temperature`. It
  writes its own `door_cooling`, and `FactoryState.air_temperature` is
  ambient minus door cooling. Reason: subtracting each tick only works
  if the daily cycle resets the value first every tick; without it the
  air would fall forever. The two scenarios now write different values
  and their order does not matter. Implemented `LoadingDoor`, door
  events with `machine_id=None`; 13 tests, 171 total. Debt: one door,
  one fixed cooling; a machine-filtered `get_events` hides door events.
- **Session 3 (cont.)** — Loading door re-explain passed (developer:
  check the load, and check the event log to see whether the door had
  been opened). Claude added a third check: the other machines dipping
  at the same time. Taught the factory thermometer (10c3); gate question
  asked.
- **Session 3 (cont.)** — Thermometer gate passed after re-teaching.
  Developer first expected the agent to see the thermometer as soon as
  it wrote to the reading log; re-taught that the agent sees only what a
  tool returns, and the developer concluded a new tool is needed. On the
  worked case (118 °F, air 75 °F, normal load) the developer judged
  nothing wrong and said the agent must take the factory temperature and
  work out the heat the machine gives off; Claude supplied the figure
  (118 − 75 = 43). Implemented `FactoryThermometer`,
  `Simulator.add_factory_sensor`, `get_factory_readings` (fifth tool);
  10 tests, 181 total. Debt: `FactoryThermometer` is not a `Sensor`
  subclass (different inputs) — a shared base is due if a second
  factory-level sensor appears.
- **Session 3 (cont.)** — Thermometer re-explain passed (developer: the
  machine could just be under a heavy load, and the agent would use the
  load sensor). Fixed a table slip: row 10c's post-implementation column
  was blank although the notes recorded the pass. Taught the assembly
  line (12a): one job identity moving station to station, hand-off only
  when the next station is free, load taken from the job, a machine with
  no work or nowhere to send it is idle; gate question asked.
- **Session 3 (cont.)** — Assembly line gate passed (developer: idle
  neighbours of a broken machine are just not busy; load now comes from
  a job number that follows the line from machine 1 to the last one).
  Claude filled in what stops the agent blaming idle machines (status,
  the stop event, their flat history) and why a shared job helps (the
  same load appears on each machine in turn). Implemented `Job`,
  `MachineState.job` / `job_progress`, `FactoryState.completed_jobs`,
  `ProductionLine`; job events now read "job N started". REMOVED the
  stand-ins: `Workload`, `MachineState.job_number`, and their two test
  files (20 tests); 14 new tests, 175 total. Sample (seed 42): a wear
  fault on CNC-02 stops it at tick 721 and the line makes nothing more.
  OPEN ISSUE found in the sample run: with every job taking a different
  time, healthy machines are idle 17% / 24% / 34% of the time along the
  line. Debt: no buffers between machines; no job-finished events or
  job-history tool (12b); a DOWN machine keeps its last `load` value.
- **Session 3 (cont.)** — Developer pasted an outside review of 12a.
  Adopted: working time is a property of the machine
  (`MachineState.ticks_per_job`, default 60), not of the job; a job now
  carries only its id and load; no random variation in time for now.
  Kept: one job brings the same load to every machine. Measured result:
  a balanced line (60/60/60) is never idle once full; an uneven line
  (60/70/55) idles in a fixed pattern each 70-tick cycle — the machine
  before the slow one waits 10 ticks holding a finished job, the one
  after waits 15 ticks empty. 18 line tests, 179 total. Which times the
  standard line uses is left for the line builder (10e). The paste also
  answered the re-explain question; per CLAUDE.md §1.1 it was re-asked
  with a different example. Later options noted from the review: a few
  ticks of natural variation, several job types, per-machine load.
- **Session 3 (cont.)** — Developer pasted an outside priority list.
  ORDER ADOPTED for the remaining rows: 12a (done, re-explain owed) →
  10d temperature lag → 12b job history and events → 11 maintenance
  action + advancing time → 12c quality, small pass/fail version →
  10e line builder → then stop adding simulator features. Standard line
  times taken as 60 / 70 / 55 ticks (CNC-02 the slowest step), to be set
  in 10e. Two items on the list already exist: sensor noise (vibration
  ±0.15 mm/s, temperature ±1 °F, load ±2 points, thermometer ±0.3 °F)
  and not exposing causes (status is only running / idle / down; tools
  return id and status). Gates are not skipped to meet a one-day target.
- **Session 3 (cont.)** — Assembly line re-explain passed on the second
  attempt. Developer first had the two kinds of waiting reversed (said
  CNC-01 waits empty and CNC-04 waits holding a job for a "CNC-05");
  re-taught with a tick-by-tick cycle and the two end-of-line facts. On
  a fresh line (80/50/50) the developer answered that CNC-02 is empty
  and waiting for CNC-01, and that CNC-01 is always going unless the
  line has no job for it — and said plainly that the first attempt had
  been a guess. Taught temperature lag (10d): the machine's real
  temperature becomes state, moved toward its settling point each tick
  by the simulator; the sensor only reads it. Gate question asked.
- **Session 3 (cont.)** — Temperature lag gate passed with one gap.
  Developer: the lag belongs in the machine state, because two sensors
  on one machine would otherwise give two different readings; a careless
  agent would conclude the machine is worn, and should check the
  thermometer and the loading door. GAP, filled by Claude and to be
  re-checked after implementation: the first thing to check is the
  machine's recent work (the heavy job just before). Implemented
  `thermal.py` (`settling_temperature`, `settle`, `warm_or_cool`),
  `MachineState.temperature`, `Simulator(thermal_lag_ticks=...)` with a
  default of 1 (no lag) so earlier exact results still hold;
  `TemperatureSensor` now only reads the stored temperature, and the
  ambient keyword added to `Sensor.read` in 10c is gone again. 12 tests,
  191 total. Sample on the 60/70/55 line with lag 20: CNC-04 swings
  between about 90 and 118 °F every cycle as it waits and works. Debt:
  one lag for all machines; lag defaults to off until the line builder
  sets it; heat constants are module constants, not per machine.
- **Session 3 (cont.)** — Temperature lag re-explain passed and the gap
  is closed (developer: check whether the machine had a much heavier
  load a tick or a few ticks before; if it is healthy the agent would
  expect to find something like an 80% load there). Taught job history
  (12b): "finished" events, a job id on job events, the current job in
  `list_machines`, and a `get_job_history` tool built from the event
  log; gate question asked.
- **Session 3 (cont.)** — 12b gate, first attempt: developer said a
  longer wait between "finished on CNC-01" and "started on CNC-02"
  points at the first machine; corrected (CNC-01 had already finished —
  the job waits because CNC-02 is still occupied). Second question not
  yet answered. Developer proposed that a worn machine take extra ticks
  per job; agreed as row 12b2. Claude noted its own example was not yet
  possible in the simulator: with fixed working times a wait is either
  the normal length or, after a breakdown, endless — 12b2 is what makes
  a lengthening wait real.
- **Session 3 (cont.)** — 12b gate passed. Developer DECIDED, against
  Claude's expected answer, that job history should say "blocked by
  CNC-02", because it happens in real life; accepted — the factory's own
  systems could see it, and it does not say why the next machine is
  slow. On the timing question the developer first thought the line had
  skipped a CNC-03 (the line is CNC-01, CNC-02, CNC-04 — naming gap to
  fix in the line builder: use CNC-01/02/03), then read off that CNC-02
  took 88 ticks on the job; Claude added that 88 against a normal 70
  points at CNC-02. Implemented started / finished / "blocked by <next>"
  job events with a `job_id`, `FactoryState.line`, the current job in
  `list_machines`, and `get_job_history` (sixth tool); 11 tests, 202
  total. Debt: no "starved" note for an empty waiting machine;
  `get_job_history` scans the whole log.
- **Session 3 (cont.)** — Developer asked for machines renamed in order,
  more machines, and a line of 3 to 8 machines chosen per run. Built the
  line builder (row 10e) now, as wiring under CLAUDE.md §2.2:
  `build_line(seed, machines=3)` gives CNC-01 upward, working times
  60/70/55/65/60/68/58/62 by position (second machine slowest), three
  sensors per machine, thermometer, vibration alarm at 4.5, ambient
  cycle timed from the clock (peak 4 pm whatever the start time),
  loading door, production line, thermal lag 20. Faults are added by the
  caller afterwards so they run after the line. 19 tests, 221 total.
  SCOPE CHANGE at developer's direction: `docs/MVP_SCOPE.md` and
  `CLAUDE.md` now say 3-8 machines (was 3-5). Older tests keep their own
  small hand-built factories and the old names (CNC-04 etc.). Row 12b's
  re-explain is still owed.
- **Session 3 (cont.)** — Job history re-explain passed (developer:
  CNC-02 worked on job 5 from tick 341 to 410; the job spent 10 ticks
  waiting; a slower CNC-02 would enlarge "the first number", its own
  working time). Claude added that the wait on CNC-01 grows as well,
  because CNC-02 frees up later. Taught 12b2 (a worn machine makes less
  than one tick of progress per tick); gate question asked.
- **Session 3 (cont.)** — Developer asked that the seed decide the
  number of machines. Done in `build_line`: with no size given, a
  dedicated stream (`line.size`) draws 3-8; passing `machines=` still
  fixes it. Over seeds 0-599 the sizes come out roughly evenly (85-108
  each); seed 42 gives 8 machines. 222 tests. Idea noted for evaluation
  time, not built: let the seed also choose the fault, the machine and
  the start tick. Row 12b2 gate still awaiting answer.
- **Session 3 (cont.)** — 12b2 gate passed (developer: CNC-02 is the
  worn one, and both neighbours wait the extra 10 ticks — CNC-01 because
  it cannot send its job on yet, CNC-03 because it cannot receive one
  yet; a rising working time is open information, not a leak). Developer
  added a requirement: no single field should make the fault easy to
  find at once. Acted on it: with working times exact, even one extra
  tick was a perfect giveaway, so the standard line now varies each
  job's time at each machine by ±2 ticks (`time_variation`, seeded, off
  by default elsewhere). This reverses the earlier "postpone natural
  variation" decision, for that reason. Implemented `working_speed`
  (1 − 0.4 × wear²) applied to job progress; 13 tests, 235 total.
  Sample: a wearing CNC-02 takes 71, 71, 72, 73, 74, 76, 78, 80, 84, 93
  ticks per job as health falls to 0.1, with no vibration alarm before
  the slowdown is visible; a machine at health 0.3 completes 15 jobs
  where a healthy line completes 19. Debt: only bearing wear slows a
  machine, so slowness still has one cause until the configuration
  scenario exists.
- **Session 3 (cont.)** — 12b2 re-explain passed (developer: one slow
  job proves nothing because jobs vary — the agent needs to be more
  patient and look at other readings such as vibration and load). Claude
  added: and at the trend over many jobs. Split row 11 into 11a (wait),
  11b (replace bearing), 11c (approval). Taught 11a; gate question
  asked.
