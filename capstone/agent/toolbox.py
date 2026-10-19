"""What the agent can call, described for the model and dispatched to the real tools.

Built only from `ObservationTools`, `ActionTools` and the agent's own
notebook: the simulator, the approval desk and the ground truth are not
reachable from here. Every call is counted, because evaluation scores
how many it took.
"""

import json
from dataclasses import dataclass, field
from typing import Callable

from pydantic import ValidationError

from capstone.agent.models import ToolCall, ToolResult
from capstone.tools.actions import ACTIONS, ActionTools
from capstone.tools.diagnosis import FAULT_KINDS, Diagnosis
from capstone.tools.observation import ObservationTools

MAX_ROWS = 300  # longer answers are refused; the agent narrows the range or uses get_sensor_trend

SENSORS = ["vibration", "temperature", "load"]


def _schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TICK = {"type": "integer", "description": "Simulation tick (one tick is one minute)."}
MACHINE = {"type": "string", "description": "Machine id, e.g. CNC-02."}

TOOL_SPECS: list[dict] = [
    {
        "name": "get_time",
        "description": "The current tick and clock time.",
        "input_schema": _schema({}, []),
    },
    {
        "name": "list_machines",
        "description": "Every machine on the line in order, its status (running / idle / down) and current job.",
        "input_schema": _schema({}, []),
    },
    {
        "name": "get_settings",
        "description": "Each machine's current spindle speed in rpm. Standard speeds differ by machine and are not shown.",
        "input_schema": _schema({}, []),
    },
    {
        "name": "get_readings",
        "description": f"Raw readings from one machine sensor ({', '.join(SENSORS)}) in a tick range. "
        f"At most {MAX_ROWS} rows; for long ranges use get_sensor_trend.",
        "input_schema": _schema(
            {
                "machine_id": MACHINE,
                "sensor": {"type": "string", "enum": SENSORS},
                "from_tick": TICK,
                "to_tick": TICK,
            },
            ["machine_id", "sensor", "from_tick", "to_tick"],
        ),
    },
    {
        "name": "get_sensor_trend",
        "description": "One machine sensor summarised per block of ticks (mean, min, max, count). "
        "Idle readings are included, which pulls means down while a machine waits.",
        "input_schema": _schema(
            {
                "machine_id": MACHINE,
                "sensor": {"type": "string", "enum": SENSORS},
                "from_tick": TICK,
                "to_tick": TICK,
                "bucket_ticks": {
                    "type": "integer",
                    "description": "Ticks per block, default 60.",
                },
            },
            ["machine_id", "sensor", "from_tick", "to_tick"],
        ),
    },
    {
        "name": "get_factory_readings",
        "description": f"The factory air thermometer (sensor 'air_temperature', °F) in a tick range. At most {MAX_ROWS} rows.",
        "input_schema": _schema(
            {
                "sensor": {"type": "string", "enum": ["air_temperature"]},
                "from_tick": TICK,
                "to_tick": TICK,
            },
            ["sensor", "from_tick", "to_tick"],
        ),
    },
    {
        "name": "get_events",
        "description": "Event log in a tick range: alarms, machine stops, job started/finished/blocked, inspections, "
        f"material batches, loading door, maintenance. Optionally one machine only. At most {MAX_ROWS} rows.",
        "input_schema": _schema(
            {"from_tick": TICK, "to_tick": TICK, "machine_id": MACHINE},
            ["from_tick", "to_tick"],
        ),
    },
    {
        "name": "get_job_history",
        "description": "Everything the event log says about one job, across machines.",
        "input_schema": _schema({"job_id": {"type": "integer"}}, ["job_id"]),
    },
    {
        "name": "get_inspections",
        "description": "Pass/fail inspection results (with material batch) for jobs that left the line in a tick range.",
        "input_schema": _schema(
            {"from_tick": TICK, "to_tick": TICK}, ["from_tick", "to_tick"]
        ),
    },
    {
        "name": "wait",
        "description": "Let the factory run for some ticks (1-480). The only way time passes; looking is free.",
        "input_schema": _schema(
            {"ticks": {"type": "integer", "minimum": 1, "maximum": 480}}, ["ticks"]
        ),
    },
    {
        "name": "propose_action",
        "description": "Ask a human to approve a change to the factory. replace_bearing stops the machine about "
        "45 ticks (135 if it has broken down); reset_setting stops it 10 ticks and puts its speed back to standard. "
        "Nothing happens until a human decides; check with get_proposals.",
        "input_schema": _schema(
            {
                "machine_id": MACHINE,
                "action": {"type": "string", "enum": list(ACTIONS)},
                "reason": {
                    "type": "string",
                    "description": "Why, and what you expect to see afterwards.",
                },
            },
            ["machine_id", "action", "reason"],
        ),
    },
    {
        "name": "get_proposals",
        "description": "Every proposal so far and whether it was approved or rejected.",
        "input_schema": _schema({}, []),
    },
    {
        "name": "update_hypotheses",
        "description": "Record your current hypothesis table. Replaces the previous table. Call it whenever "
        "evidence changes your view.",
        "input_schema": _schema(
            {
                "hypotheses": {
                    "type": "array",
                    "items": _schema(
                        {
                            "hypothesis": {"type": "string"},
                            "supporting": {"type": "string"},
                            "contradicting": {"type": "string"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        ["hypothesis", "supporting", "contradicting", "confidence"],
                    ),
                }
            },
            ["hypotheses"],
        ),
    },
    {
        "name": "submit_diagnosis",
        "description": "End the investigation with your conclusion. 'false_alarm' means nothing needs fixing. "
        "Name the machine, or the material batch for bad_material_batch.",
        "input_schema": _schema(
            {
                "fault": {"type": "string", "enum": list(FAULT_KINDS)},
                "machine_id": {"type": ["string", "null"]},
                "batch_id": {"type": ["integer", "null"]},
                "summary": {
                    "type": "string",
                    "description": "Evidence, action taken, and what verification showed.",
                },
            },
            ["fault", "machine_id", "batch_id", "summary"],
        ),
    },
]


@dataclass
class Notebook:
    """The agent's own working state: its hypothesis tables, its evidence trail and its answer."""

    hypotheses: list[dict] = field(default_factory=list)
    history: list[list[dict]] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    diagnosis: Diagnosis | None = None


class Toolbox:
    """Turns a model's tool call into a call on the real tools, and the answer into JSON text."""

    def __init__(
        self,
        look: ObservationTools,
        act: ActionTools,
        *,
        extra: dict[str, tuple[dict, Callable]] | None = None,
    ):
        self.notebook = Notebook()
        self.tool_calls = 0
        self._handlers: dict[str, Callable] = {
            "get_time": look.get_time,
            "list_machines": look.list_machines,
            "get_settings": look.get_settings,
            "get_readings": look.get_readings,
            "get_sensor_trend": look.get_sensor_trend,
            "get_factory_readings": look.get_factory_readings,
            "get_events": look.get_events,
            "get_job_history": look.get_job_history,
            "get_inspections": look.get_inspections,
            "wait": act.wait,
            "propose_action": act.propose_action,
            "get_proposals": act.get_proposals,
            "update_hypotheses": self._update_hypotheses,
            "submit_diagnosis": self._submit_diagnosis,
        }
        self.specs = list(TOOL_SPECS)
        for name, (spec, handler) in (extra or {}).items():
            self.specs.append(spec)
            self._handlers[name] = handler

    def run(self, call: ToolCall) -> ToolResult:
        self.tool_calls += 1
        self.notebook.calls.append({"name": call.name, "input": call.input})
        handler = self._handlers.get(call.name)
        if handler is None:
            return ToolResult(
                call.id,
                json.dumps({"error": f"no tool named {call.name}"}),
                is_error=True,
            )
        try:
            answer = handler(**call.input)
        except (ValueError, TypeError, ValidationError) as error:
            return ToolResult(call.id, json.dumps({"error": str(error)}), is_error=True)
        if isinstance(answer, list) and len(answer) > MAX_ROWS:
            message = f"{len(answer)} rows is more than {MAX_ROWS}; narrow the range or use get_sensor_trend"
            return ToolResult(call.id, json.dumps({"error": message}), is_error=True)
        return ToolResult(call.id, json.dumps(answer, ensure_ascii=False))

    def _update_hypotheses(self, hypotheses: list[dict]) -> dict:
        self.notebook.hypotheses = hypotheses
        self.notebook.history.append(hypotheses)
        return {"recorded": len(hypotheses)}

    def _submit_diagnosis(
        self,
        fault: str,
        machine_id: str | None = None,
        batch_id: int | None = None,
        summary: str = "",
    ) -> dict:
        self.notebook.diagnosis = Diagnosis(
            fault=fault, machine_id=machine_id, batch_id=batch_id, summary=summary
        )
        return {"received": True}
