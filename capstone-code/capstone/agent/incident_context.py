"""Assemble a bounded, read-only view of the line before investigation planning."""

import json

from capstone.agent.loop import InvestigationDeps, gather
from capstone.agent.policy import CallTool
from capstone.agent.state import IncidentContext, InvestigationState
from capstone.contracts.evidence import Evidence
from capstone.contracts.tools import ToolRequest

WINDOW_TICKS = 60
MAX_CONTEXT_CALLS = 7

# The monitoring alarm carries words, not a sensor field. Only an unambiguous
# sensor name in those words justifies an automatic neighbor summary.
SENSOR_WORDS = (
    ("hydraulic pressure", "hydraulic_pressure"),
    ("following error", "following_error"),
    ("vibration", "vibration"),
    ("temperature", "temperature"),
    ("power", "power"),
    ("load", "load"),
)


def incident_sensor(state: InvestigationState) -> str | None:
    """Name the sensor explicit in the trigger, if exactly one is named."""
    # Variables:
    #   words: The trigger's observed description, never a fault label.
    #   named: Distinct sensors explicitly named; ambiguity means no automatic summary.
    words = state.anomaly.description.lower().replace("_", " ")
    named = {sensor for phrase, sensor in SENSOR_WORDS if phrase in words}
    return next(iter(named)) if len(named) == 1 else None


def context_call(
    state: InvestigationState,
    deps: InvestigationDeps,
    name: str,
    arguments: dict,
    purpose: str,
    *,
    limit: int,
) -> Evidence | None:
    """Gather one context answer while preserving half the research calls."""
    # Variables:
    #   limit: Maximum research calls including the initial time query that this
    #     packet may use, leaving the rest for the investigator.
    #   purpose: Why this reading was requested, retained in the decision trace.
    #   step: The read-only request sent through the normal provider boundary.
    if state.research_tool_calls >= limit or state.research_seconds(deps.clock()) <= 0:
        return None
    step = CallTool(
        information_needed=purpose,
        request=ToolRequest(name=name, arguments=arguments),
    )
    return gather(state, deps, "observe", step, interpret=False)


def assemble_incident_context(
    state: InvestigationState, deps: InvestigationDeps
) -> None:
    """Gather line context from existing tools without inferring any cause."""
    # Variables:
    #   trigger: The monitored symptom that started this investigation.
    #   from_tick: Start of the bounded historical window; its end is the
    #     trigger tick so later events cannot appear as pre-trigger evidence.
    #   as_of_tick: Time of the current machine snapshot, which may be later
    #     than the monitored trigger because monitoring scans in blocks.
    #   limit: Maximum total research calls allowed before planning, preserving
    #     at least half the configured research calls.
    #   found: Tool names mapped to original evidence IDs, without copying facts.
    #   summaries: Nearby machine IDs mapped to their sensor-summary evidence.
    #   unavailable: Queries not answered, including those skipped for budget.
    #   machine_ids: The observed line order, used only to find immediate neighbors.
    #   neighbor_ids: Trigger machine plus its immediate line neighbors.
    #   sensor: The one sensor explicit in the trigger; None avoids guessing.
    trigger = state.anomaly
    from_tick = max(0, trigger.tick - WINDOW_TICKS)
    as_of_tick = state.last_tick
    limit = state.research_tool_calls + min(
        MAX_CONTEXT_CALLS,
        max(0, state.budgets.max_tool_calls // 2 - state.research_tool_calls),
    )
    found: dict[str, str] = {}
    summaries: dict[str, str] = {}
    unavailable: list[str] = []
    machine_ids: tuple[str, ...] = ()
    neighbor_ids: tuple[str, ...] = ()

    machines = context_call(
        state,
        deps,
        "list_machines",
        {},
        "the observed status and job of every machine",
        limit=limit,
    )
    if machines is not None:
        as_of_tick = machines.observed_tick
        rows = json.loads(machines.content)
        if isinstance(rows, list) and all(
            isinstance(row, dict) and isinstance(row.get("machine_id"), str)
            for row in rows
        ):
            machine_ids = tuple(row["machine_id"] for row in rows)
            found["list_machines"] = machines.id
            if trigger.machine_id in machine_ids:
                position = machine_ids.index(trigger.machine_id)
                neighbor_ids = machine_ids[
                    max(0, position - 1) : min(len(machine_ids), position + 2)
                ]
        else:
            unavailable.append("list_machines: invalid answer")
    else:
        unavailable.append("list_machines: unavailable or budgeted out")

    for name, arguments, purpose in (
        ("get_settings", {}, "observed current settings for the whole line"),
        (
            "get_events",
            {"from_tick": from_tick, "to_tick": trigger.tick},
            "all recent line events through the trigger tick",
        ),
        (
            "get_inspections",
            {"from_tick": from_tick, "to_tick": trigger.tick},
            "recent inspection outcomes through the trigger tick",
        ),
    ):
        answer = context_call(state, deps, name, arguments, purpose, limit=limit)
        if answer is None:
            unavailable.append(f"{name}: unavailable or budgeted out")
        else:
            found[name] = answer.id

    sensor = incident_sensor(state)
    if sensor is None:
        unavailable.append("nearby sensor summaries: trigger names no single sensor")
    elif not neighbor_ids:
        unavailable.append(
            "nearby sensor summaries: trigger machine or line order unavailable"
        )
    else:
        for machine_id in neighbor_ids:
            answer = context_call(
                state,
                deps,
                "get_sensor_summary",
                {
                    "machine_id": machine_id,
                    "sensor": sensor,
                    "from_tick": from_tick,
                    "to_tick": trigger.tick,
                },
                f"{sensor} summary for {machine_id} near the trigger",
                limit=limit,
            )
            if answer is None:
                unavailable.append(
                    f"get_sensor_summary {machine_id}: unavailable or budgeted out"
                )
            else:
                summaries[machine_id] = answer.id

    state.incident_context = IncidentContext(
        trigger_tick=trigger.tick,
        as_of_tick=as_of_tick,
        from_tick=from_tick,
        machine_ids=machine_ids,
        neighbor_ids=neighbor_ids,
        evidence_by_tool=found,
        summary_evidence=summaries,
        unavailable=tuple(unavailable),
    )
