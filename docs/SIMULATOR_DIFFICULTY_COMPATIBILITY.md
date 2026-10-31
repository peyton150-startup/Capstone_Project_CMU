# Simulator difficulty compatibility verification

Checked 2026-10-18 against this checkout; limits re-audited 2026-10-31 (see the ✅ IMPLEMENTED note below). The developer authorized harder
simulator behavior only if it requires no investigation-side code changes.
This check adds tests, not new production behavior.

| Capability | Verified evidence | Limit |
|---|---|---|
| Compound faults | Existing `BearingDegradation` and `WrongSetting` run together; the provider returns readings, settings, events and proposals. | No solver runtime is present to test reasoning or completion behavior. |
| Similar symptoms from different causes | A worn bearing and an excessive speed setting produce identical noise-free vibration samples. | Other observations can distinguish them; this is intentional ambiguity in one sensor. |
| Drift, transient anomalies and missing samples | Synthetic sample fixtures pass through existing reading and summary tools; gaps stay gaps, empty summaries have null statistics, endpoint rates use elapsed ticks. | Tests verify representation, not implemented causal drift/dropout/transient models. |
| Partial improvement after intervention | A human-approved bearing replacement reduces vibration while the simultaneous speed fault leaves it above baseline. Existing tools show the residual evidence. | Only bearing replacement is currently allowed; no setting-reset action is implemented. |
| Delayed historical maintenance records | Appending an earlier-tick record after a later event is rejected by `EventLog.record()`. | `EventObservation` has one tick, not separate occurrence/publication times. A publication-time event with the occurrence time in its message could preserve the shape, but that convention and consumer behavior have not been verified. |

The compatibility tests are in `tests/test_difficulty_tool_compatibility.py`.
They exercise the actual provider, simulator, scenarios, sensors, approval desk,
and action tools. Synthetic observation fixtures are explicitly identified.
Existing provider tests separately verify all read-tool shapes and deny hidden
truth/approval tools; sensor-summary tests cover sparse and empty histories.

`CompletedInvestigation` has one `proposed_action` and one conclusion whose
diagnosis is free text. Several diagnoses could be written into that string,
but structured reporting of multiple causes/interventions is not established
by the current contract. `LLMProvider` is a protocol, not an executable solver.
Consequently, tool-shape compatibility is demonstrated for the cases above;
zero changes to an actual investigation runtime cannot be certified here.

Initial verification decision: do not introduce the full requested difficulty bundle under the
strict zero-investigation-change condition. Preserve the existing interfaces;
resolve delayed-record semantics and test the actual solver before claiming
end-to-end compatibility. No new LLM is necessary for these simulator features.

## Implemented after the developer excluded delayed records

The developer then authorized all the difficulty additions except delayed
maintenance records. Delayed information is excluded, not a pending feature.
The initial table above describes the verification snapshot before this build.

- `state.py`: `SensorEffect` stores a hidden instrument offset or signal loss.
  `MachineState.sensor_effects` keeps contributions by scenario name, separate
  from bearing health. None of these fields crosses the tool boundary.
- `disturbances.py`: `SensorDrift`, `TransientAnomaly`, and `SensorDropout`
  change instrument state only. `_SensorDisturbance.apply()` owns a window from
  `start_tick` inclusive to `start_tick + duration` exclusive and removes only
  its own contribution when it ends. Drift adds `per_tick` on the first active
  tick and grows each subsequent tick; its configured window ending represents
  calibration recovery, independent of a bearing repair. The transient is
  constant during its window. Dropout supplies no fabricated zero samples.
- `sensors.py`: `Sensor.read()` adds matching instrument biases to its physical
  measurement. `Sensor.available()` checks signal loss. Offsets are in the
  sensor's own units; callers should choose physically useful magnitudes.
- `simulator.py`: `Simulator.step()` still samples instrument noise every tick,
  but only transmitted readings enter history or trigger alarms. Physical
  production, maintenance, thermal and failure logic remain independent.
- `challenge.py`: `build_challenge(seed, machines=None, start=...)` calls the
  existing line builder and adds five scenarios. Its separate RNG stream picks
  three distinct machines and an onset between ticks 40 and 80. Bearing wear
  and excessive speed share a target; a second machine has an eight-tick
  vibration spike beginning ten ticks later. A third has a 180-tick temperature
  drift and twenty missing temperature samples starting sixty ticks after onset.
  Repairs clear bearing wear but do not correct the speed or instrument faults.

No investigation-facing modules, tool names, arguments, or response contracts
were changed. Existing compatibility tests prove overlapping causes and partial
repair through real tools. New disturbance tests prove causal isolation, exact
windows, composability, alarm suppression, recovery and noise-stream alignment.
Challenge tests prove same-seed replay, different-seed variation, sparse histories,
line sizes, and hidden state exclusion. `build_line()` remains the ordinary
factory; callers opt into the challenge explicitly. No new dependencies or LLM.

> **✅ IMPLEMENTED since this section was written (audit 2026-10-31, `main` at
> `af3b7bf`).** The limits in the paragraph below no longer hold, except the
> last two rows of this list:
>
> - **Solver runtime and evaluator: ✅ IMPLEMENTED.** The full agent loop
>   (`agent/investigation.py`), `evals.py` and `evaluation/scoring.py` exist.
> - **Challenge scoring: ✅ IMPLEMENTED.** The challenge is known-answer case
>   `KA-09-challenge` (`evaluation/known_answers.py`), scored with partial
>   credit per cause (`COMPOUND`, `causes_resolved`).
> - **Setting reset: ✅ IMPLEMENTED.** `ActionTools` / `ApprovalDesk.carry_out`
>   also support `reset_setting`, `replace_servo_drive` and `repair_hydraulics`
>   besides `replace_bearing`.
> - **Sensor calibration action: ❌ NOT BUILT.** Instrument drift still cannot
>   be repaired.
> - **Several interventions per investigation: ❌ NOT BUILT.**
>   `CompletedInvestigation` still has one `proposed_action` and a free-text
>   diagnosis, so the challenge's bearing and speed faults on one machine
>   cannot both be fixed in one investigation.

Original text (written 2026-10-18):

The challenge is an investigation exercise, not a new fully scored benchmark.
There is still no connected solver runtime or general simulator evaluator in
this checkout. Setting reset and sensor calibration actions are not available;
the only current intervention is bearing replacement. Complete repair of all
challenge faults is therefore not an expected outcome yet. Completion-report
and evaluation integration remain separate work.

## Kanika feedback: realistic next steps

| Suggestion | Realistic now? | Current state / next step |
|---|---|---|
| Noisy and missing sensor data | Yes | Existing seeded noise plus implemented drift/dropout. |
| Equipment failures | Yes | Existing bearing degradation, breakdown and approved bearing repair. |
| Several faults / plausible alternative causes | Yes | Compound challenge, speed/load/wear overlap, and instrument bias; no extra reasoning agent. |
| Harmless anomalies with real faults | Yes | Implemented temporary instrument spike alongside persistent faults. |
| Partial improvement after intervention | Yes | Bearing repair leaves independent speed/instrument causes intact; tested via tools. |
| Different factory settings | Yes, within existing simulator capabilities | Seed, 3–8 machines, cycle times, workload variation, thermal lag and alarm threshold are configurable through `build_line()`. A configuration matrix is feasible; new factory layouts/processes need more modeling. |
| One production problem and fewer agents/tools | Yes | Keep one investigation agent and current allowlist; do not add specialists for this feedback. Runtime still needs integration. |
| Root-cause/action/verification evaluation | Feasible next increment | General simulator scoring, episode runner and solver integration remain absent here; current evaluation code covers memory records. Define multi-fault and partial-resolution scoring before claiming measured agent performance. |
| Cooling-system failure as a third overheating cause | Feasible later, not implemented | Needs a hidden cooling state and causal thermal model, then diagnosis/repair/scoring tests. Load and instrument-bias explanations already fit current physics/interfaces. |
| Delayed information / maintenance records | Excluded by developer | Do not implement or add to the work queue. |

Kanika's feedback supports strengthening simulation and evaluation; it does not
require a second model, a new framework, or specialized agents. Prioritize the
complete single-agent investigation/approval/verification/evaluation path before
adding new physical subsystems or a broad configuration benchmark.
