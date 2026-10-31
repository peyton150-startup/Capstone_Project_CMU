# Ungated build summary

Every component built without the comprehension gate first (AGENTS.md §1:
the rule change of 2026-10-06, and later builds the developer asked for with
"build first, teach after"), with where it stands now. The status comes from
the "Understood (post)" column of `docs/PROGRESS.md`, which stays the record;
this page is the index. Updated 2026-10-31.

- **Taught since**: the developer has explained it back (walkthrough or
  re-teach); nothing is owed.
- **Partly**: a walkthrough happened, but a question is still open or the
  mark was left for the developer.
- **Owed**: not yet taught.

## Status of every ungated build

| Row | What was built | Status now |
|---|---|---|
| 13c | Setting reset action (`start_setting_reset`, `reset_setting`) | Taught since (after one re-teach) |
| 13d | False alarm, fault 4 (`FalseAlarm`, `vibration_sensor_offset`) | Taught since (after one hint) |
| 14 | Seeded scenario generator (`build_scenario`, `FAULTS`) | Taught since |
| 15 | Evaluation (`evaluate`, `Score`, `Diagnosis`) | Taught since |
| 16 | The first research agent | Retired 2026-10-19 (row R2); only `monitor.py` and `get_sensor_trend` remain |
| 17 | The first memory | Retired 2026-10-19; replaced by `capstone/memory/` (rows A6a-A7b, taught) |
| R1 | Review fixes: loop budgets, tool errors, repair check, trend tool | Taught since |
| R2 | Row cap, unjudged diagnosis, old agent retired, episode runner | Taught since (after one re-teach) |
| R3 | MVP gap fixes: semantic recall, score fields, harness, hand labels, known-answer suite | Taught since |
| R4a | Scoring-integrity tests | Taught since (after one re-teach) |
| R4b | Evidence-vs-reasoning miss label | Taught since |
| R4c | Rule-based diagnostic baseline | Taught since (after one re-teach) |
| R4d | Unreliable tools on a fixed schedule (hazards) | Taught since (after one re-teach) |
| R4e | Evidence-completeness stop | Taught since |
| L1 | Live runs finish: User-Agent, fallback time share, stage deadline | Taught since |
| E6 | The compound challenge in experiments (KA-09) | Taught since |
| L2 | Benchmark under real limits; retries back off | Taught since |
| L2b | Prompts show the time left | Taught since |
| L3 | Requesty and xKiro providers | Taught since |
| L4 | Why a reply was invalid is recorded | Taught since |
| L5 | NVIDIA structured output | Taught since |
| L6 | LLM7 and Kilo Code providers | Taught since |
| C2 | Course Module 2 gap note (docs) | Taught since |
| C4 | Opt-in tree-of-thought hypothesize step | Taught since |
| FD | Experiment failure diagnostics | Taught since |
| C3a | Memory comparison command | Taught since |
| C3b | Bounded memory search | Taught since |
| C3c | Memory comparison made fair (PR #74) | Taught since (walkthrough 2026-10-26) |
| LV | Live progress view (PR #81) | Taught since (walkthrough 2026-10-26) |
| L8 | Chain of fallback models; Cohere output cap | Partly: walkthrough 2026-10-28, Q3 in part, mark left for the developer |
| L9 | Progress view on by default in `experiment run` | Partly: walkthrough 2026-10-28, Q2 half right, mark left for the developer |
| A10 | Policy recommendation and why an action was lowered, recorded | Partly: walkthrough 2026-10-28, corrected, mark left for the developer |
| A11 | Conclude prompt states the bar; `MIN_ACTION_CONFIDENCE` | Partly: taught with A13 on 2026-10-28, mark left for the developer |
| A13 | `STATE_ACTION_BAR`: show or hide the threshold | Partly: walkthrough 2026-10-28, Q3 corrected, mark left for the developer |
| A14 | Prompt: one discriminating check before stopping | Partly: walkthrough 2026-10-28, Q2 mostly right, mark left for the developer |
| A15 | Prompt: consult the manual before a repair | Partly: walkthrough 2026-10-28, mark left for the developer |
| EV1 | Full-episode evaluation harness and master baseline | Partly: two walkthroughs 2026-10-28; a re-check of Q3 is owed |
| M2 | Critic option B: manual sections searched per hypothesis | Owed |
| M1b | The manual step before planning (`MANUAL_STEP`) | Owed |
| — | Terminal progress colours (2026-10-30, display only) | Owed (display only, no behaviour) |
| — | Cohere JSON-object output (PR #145, 2026-10-31) | Owed |
| — | Per-model sampling and independent critic fallback (PR #146, 2026-10-31) | Owed |
| EV2 | Known cases KA-10 to KA-13 (servo drive, hydraulic leak); manual rev 1.3; scoring fix for both faults | Owed |

Rows built through the gate (A1-A9b, E1-E5, L7, G1, M1, T1, F1-F5, C1, C1b,
C2r, D1, D2 and the simulator rows 1-13b) are not listed. C1, C1b, C2r, D1
and D2 still have a closing question or a mark outstanding; see `PROGRESS.md`.

## What the owed builds added

### M2 — Critic option B (2026-10-29)

| Where | Added | Meaning |
|---|---|---|
| `agent/critic.py` | `manual_sections`, `MANUAL_PER_HYPOTHESIS`, `MANUAL_NOTE`, `Critic(manual=...)`, `Critic.last_sections` | With a manual offered, code (not the model) searches it once per hypothesis the critic is shown, and puts the sections into the critic's prompt as guidance. |
| `agent/artifacts.py` | `CritiqueRecord.manual_sections` | Which sections the critic was shown, kept in the record. |

### M1b — The manual step (2026-10-29)

| Where | Added | Meaning |
|---|---|---|
| `agent/investigation.py` | `manual_query`, `consult_manual`, `MANUAL_STEP_LIMIT`, edge `observe -> manual -> plan` | Opt-in (`MANUAL_STEP`): search the manual once on the anomaly before the agent plans. The `search_manual` tool stays available. |
| `evaluation/manual.py` | `ManualSearchRecord.automatic` | Tells the automatic search apart from the agent's own. |

### Cohere JSON output (PR #145) and model sampling (PR #146), 2026-10-31

| Where | Added | Meaning |
|---|---|---|
| `providers/chat.py` | JSON-object mode for Cohere | Cohere is asked for a JSON object, which stopped its HTTP 422 "no valid response" on tree-of-thought questions. The schema instruction and Pydantic check stay. |
| `settings.py` | `SamplingOptions`, `PROVIDER_SAMPLING`, `MODEL_SAMPLING`, `CRITIC_FALLBACK_MODEL` | Temperature and top_p per provider and per model, and the critic's own backup models. |
| `providers/chat.py` | `MODEL_SAMPLING_DEFAULTS`, sampling in `client_for` and `ChatClient` | Exact-model defaults (e.g. Nemotron 1.0/0.95, Command A 0.3/0.75), overridden field by field. |

### EV2 — Faults that need a repair join the known cases (2026-10-31)

| Where | Added | Meaning |
|---|---|---|
| `evaluation/known_answers.py` | KA-10/KA-11 (servo drive wear), KA-12/KA-13 (hydraulic leak); `BASELINE_CASES` | Four cases where "leave it alone" is always wrong. `BASELINE_CASES` is the four default faults only, since the rule baseline has no rules for the new two. |
| `evals/scenarios.json` | The four new cases | The master config lists every known case. |
| `evals.py` | `Scenario.valid_factory` accepts every `FAULT_KINDS` fault | A config case may force the servo or hydraulic fault, which the generator never draws by itself. |
| `evaluation/scoring.py` | `_resolved` checks `axis_replaced_tick` and `hydraulics_repaired_tick` | **Bug fix.** Both faults used to fall through to the false-alarm check, so they always counted as "resolved" even when nothing was repaired. Now only their repair after the fault began counts, the same rule the scenarios use to stop the wear. An unknown fault raises an error instead of falling through. |
| `manual/sim-cnc-001.md` | Rev 1.3: §2.14 servo drive, §2.15 hydraulic clamping; §1.2 and §2.13 updated | How each fault shows, how to tell it from the others, that it never recovers by itself, and its one repair. |
| `manual/sections.py` | `_LEAKS` refuses `servo_drive_wear` and `hydraulic_leak` | The manual cannot name the internal fault names. |

## The original session-5 builds (rows 13c-17)

> **2026-10-19:** the older agent described in rows 16-17 below (`agent.py`,
> `toolbox.py`, `models.py`, `memory.py`, `episode.py`) has been retired. The
> runner is now `capstone/episode.py`; see `docs/PROGRESS.md` row R2.

Built in session 5 without comprehension gates. 13c, 13d, 14 and 15 have
since been taught (see the table above).

### 13c — Setting reset action

| Where | Added | Meaning |
|---|---|---|
| `simulator/simulator.py` | `start_setting_reset(machine_id)` | Stops a machine for 10 ticks; when done its speed goes back to standard. Refused on a broken-down machine. |
| | `_machine_for_maintenance`, `_start_maintenance` | Shared start-up for every repair kind: check the machine, set it DOWN, record "… started". |
| | `_finish_maintenance` (reworked), `_describe_old_setting` | On finishing, does the right thing for the kind of work and logs what the technician saw: "setting was off standard" / "already standard". |
| `simulator/state.py` | `MachineState.maintenance_kind` | Which repair is under way. |
| `tools/actions.py` | `"reset_setting"` in `ACTIONS` | The agent can now propose it; the desk carries it out on approval. |

### 13d — False alarm (fault 4)

| Where | Added | Meaning |
|---|---|---|
| `simulator/state.py` | `MachineCondition.vibration_sensor_offset` | Hidden: how much a faulty vibration sensor adds to its own reading. |
| `simulator/sensors.py` | `VibrationSensor` reads the offset | The glitch reaches the evidence through the sensor, never as a written reading. |
| `simulator/scenarios.py` | `FalseAlarm` | Turns the offset on for a few ticks, then off. Nothing else in the machine changes. Correct action: none. |

### 14 — Scenario generator

| Where | Added | Meaning |
|---|---|---|
| `simulator/generator.py` | `build_scenario(seed, machines=None, fault=None)` | A standard line plus one fault whose kind, place, start and strength all come from the seed (stream `generator`). `fault=` forces the kind. |
| | `FAULTS` | The four fault names a seed draws by itself (the servo and hydraulic faults, added later, are only ever forced). |

### 15 — Evaluation

| Where | Added | Meaning |
|---|---|---|
| `tools/diagnosis.py` | `Diagnosis`, `FAULT_KINDS` | The agent's final answer: cause, machine or batch, summary. Its belief, handed across the boundary. |
| `evaluation/scoring.py` | `evaluate(...) → Score` | Compares the answer and the APPROVED actions with the ground truth, and checks hidden state to see if the cause is really gone. |
| | `CORRECT_ACTION` | bearing → replace_bearing, setting → reset_setting, servo → replace_servo_drive, hydraulic → repair_hydraulics, batch / false alarm → do nothing. |
| | `summarize`, `format_summary` | Totals over many runs ("18/20 root causes…"). |

### 16 — The research agent (retired)

| Where | Added | Meaning |
|---|---|---|
| `agent/models.py` | `Model` interface, `ScriptedModel`, `Turn`, `ToolCall`, `ToolResult` | The LLM behind one small interface. Retired. |
| `agent/toolbox.py` | `Toolbox`, `TOOL_SPECS`, `Notebook` | The tools as the model saw them. Retired. |
| `agent/agent.py` | `ResearchAgent`, `SYSTEM_PROMPT` | The first investigation loop. Retired; replaced by `agent/loop.py` and `agent/investigation.py`. |
| `agent/monitor.py` | `wait_for_anomaly` (now `detect_anomaly`) | Runs the line until an alarm, a stop, or 3 rejects in 10, using only agent tools. Still in use. |
| `tools/observation.py` | `get_sensor_trend` | Readings summarised per block of ticks. Still in use. |

### 17 — Memory (retired)

| Where | Added | Meaning |
|---|---|---|
| `agent/memory.py` | `InvestigationMemory`, `search_incident_history` | One JSON line per investigation and a word search. Retired; replaced by `capstone/memory/`. |

### Decisions taken without asking (session 5)

- Generated lines use 10 jobs per batch (the standard line keeps 25), so a bad batch appears within a day.
- Generated wrong settings are 18–20% off standard; 12–15% often went unnoticed for 4,000 ticks.
- A broken-down machine cannot be "reset"; it needs a bearing replacement.
- The automated "human" in experiments approves everything, so the score shows whether the agent asked for the right thing.
