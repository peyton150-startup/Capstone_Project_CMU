# Ungated build summary (rows 13c–17)

> **2026-10-19:** the older agent described in rows 16-17 below (`agent.py`,
> `toolbox.py`, `models.py`, `memory.py`, `episode.py`) has been retired. The
> runner is now `capstone/episode.py`; see `docs/PROGRESS.md` row R2.

Built in session 5 without comprehension gates, at the developer's direction
(CLAUDE.md §1, rule change of 2026-10-06). Every item here is marked
"Understood: no — developer to review" in `PROGRESS.md`. 380 tests pass.

## 13c — Setting reset action

| Where | Added | Meaning |
|---|---|---|
| `simulator/simulator.py` | `start_setting_reset(machine_id)` | Stops a machine for 10 ticks; when done its speed goes back to standard. Refused on a broken-down machine. |
| | `_machine_for_maintenance`, `_start_maintenance` | Shared start-up for both repair kinds: check the machine, set it DOWN, record "… started". |
| | `_finish_maintenance` (reworked), `_describe_old_setting` | On finishing, does the right thing for the kind of work and logs what the technician saw: "setting was off standard" / "already standard". |
| `simulator/state.py` | `MachineState.maintenance_kind` | Which repair is under way. |
| `tools/actions.py` | `"reset_setting"` in `ACTIONS` | The agent can now propose it; the desk carries it out on approval. |

## 13d — False alarm (fault 4)

| Where | Added | Meaning |
|---|---|---|
| `simulator/state.py` | `MachineCondition.vibration_sensor_offset` | Hidden: how much a faulty vibration sensor adds to its own reading. |
| `simulator/sensors.py` | `VibrationSensor` reads the offset | The glitch reaches the evidence through the sensor, never as a written reading. |
| `simulator/scenarios.py` | `FalseAlarm` | Turns the offset on for a few ticks, then off. Nothing else in the machine changes. Correct action: none. |

## 14 — Scenario generator

| Where | Added | Meaning |
|---|---|---|
| `simulator/generator.py` | `build_scenario(seed, machines=None, fault=None)` | A standard line plus one fault whose kind, place, start and strength all come from the seed (stream `generator`). `fault=` forces the kind. |
| | `FAULTS` | The four fault names. |

## 15 — Evaluation

| Where | Added | Meaning |
|---|---|---|
| `tools/diagnosis.py` | `Diagnosis`, `FAULT_KINDS` | The agent's final answer: cause, machine or batch, summary. Its belief, handed across the boundary. |
| `evaluation/scoring.py` | `evaluate(...) → Score` | Compares the answer and the APPROVED actions with the ground truth, and checks hidden state to see if the cause is really gone. |
| | `CORRECT_ACTION` | bearing → replace_bearing, setting → reset_setting, batch / false alarm → do nothing. |
| | `summarize`, `format_summary` | Totals over many runs ("18/20 root causes…"). |

## 16 — The research agent

| Where | Added | Meaning |
|---|---|---|
| `agent/models.py` | `Model` interface, `ScriptedModel`, `Turn`, `ToolCall`, `ToolResult` | The LLM behind one small interface. `ScriptedModel` replays fixed turns so tests need no key. The original Claude model class was removed on 2026-10-12: Anthropic is not a provider in this project. |
| `agent/toolbox.py` | `Toolbox`, `TOOL_SPECS`, `Notebook` | The 14 tools as the model sees them, dispatch to the real tools, call counting, error handling, the agent's hypothesis table and answer. |
| `agent/agent.py` | `ResearchAgent`, `SYSTEM_PROMPT` | The investigation loop and the instructions for the staged method. |
| `agent/monitor.py` | `wait_for_anomaly` | Runs the line until an alarm, a stop, or 3 rejects in 10 — using only agent tools. |
| `agent/episode.py` | `run_episode`, `approve_all`, `ask_on_console` | One full run: scenario → anomaly → agent → human decisions → score. |
| `agent/__main__.py` | removed 2026-10-12 | The command line only ran the Claude model, which is out of scope. |
| `tools/observation.py` | `get_sensor_trend` | Readings summarised per block of ticks, so long histories fit in the model's context. |

## 17 — Memory

| Where | Added | Meaning |
|---|---|---|
| `agent/memory.py` | `InvestigationMemory.record` | Saves one JSON line per investigation: anomaly, evidence, hypotheses, conclusion, actions, outcome. Never the score or truth. |
| | `InvestigationMemory.search` / `search_incident_history` tool | Finds past cases sharing words with a description. |

## Decisions taken without asking

- Generated lines use 10 jobs per batch (the standard line keeps 25), so a bad batch appears within a day.
- Generated wrong settings are 18–20% off standard; 12–15% often went unnoticed for 4,000 ticks.
- A broken-down machine cannot be "reset"; it needs a bearing replacement.
- The automated "human" in experiments approves everything, so the score shows whether the agent asked for the right thing.

## Not done

- No run of the real agent yet (no API key in the build session).
