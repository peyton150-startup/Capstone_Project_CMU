# Offline, read-only investigations over previously collected machine telemetry.
# Responsibility: offer only captured capabilities to the existing Pydantic graph.
"""Investigate a recorded machine without a simulator or live machine access.

    uv run python -m capstone.replay_investigation \
        --capture ../pilot-data/telemetry.jsonl \
        --map ../pilot-data/channel-map.json \
        --probe ../pilot-data/probe.xml \
        --machine VF2 --symptom "Operator noticed a sustained load increase"

This is shadow research, not automated diagnosis or permission to intervene.
The controller is never contacted; probe, capture and map come from private
shop-approved files. Model calls need configured provider credentials. Nothing
changes a machine, and nothing is uploaded by this program except requests to
the configured LLM provider; review the shop's authorization and allowed data
fields before using any external provider with customer telemetry.
"""

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

from capstone.agent.artifacts import DetectedAnomaly
from capstone.agent.investigation import run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.agent.policy import ReasoningPolicy
from capstone.agent.state import InvestigationState, triage_budgets
from capstone.contracts.investigations import investigation_id_for, run_id_for
from capstone.contracts.tools import ToolSpec
from capstone.ingestion.channel_map import ChannelMap, read_capture
from capstone.ingestion.privacy import refusal
from capstone.ingestion.record import Line, TelemetryRecord
from capstone.providers.factory import tool_spec
from capstone.providers.replay import replay_provider

# A recorded investigation never offers simulated settings, jobs, repairs or
# 'wait': moving the replay cutoff forward would expose later measurements.
_RECORD_READS = (
    "get_time",
    "list_machines",
    "get_readings",
    "get_sensor_trend",
    "get_factory_readings",
    "get_sensor_summary",
)


def recorded_tool_specs(
    lines: Sequence[Line], channel_map: ChannelMap, *, cutoff: datetime | None = None
) -> tuple[ToolSpec, ...]:
    """Describe only numeric channels visible by the requested replay cutoff.

    Data-item assignments come from the human-reviewed SM-1 map. The source
    records, not the map alone, prove that a sensor reported a numeric value.
    """
    # Variables:
    #   entries: DataItem lookup keyed by device name/UUID and item id.
    #   signals: Real numeric readings available per machine and per tool sensor.
    #   execution: Machines with an observed Execution state, needed for list_machines.
    #   common: An explicit warning and tick mapping added to each tool description.
    #   names: Tools whose required data were actually recorded.
    entries = {
        (device, entry.data_item_id): entry
        for entry in channel_map.entries
        for device in (entry.device, entry.device_uuid)
    }
    signals: dict[str, dict[str, str]] = defaultdict(dict)
    execution: set[str] = set()
    for line in lines:
        if not isinstance(line, TelemetryRecord):
            continue
        if cutoff is not None and line.source_timestamp > cutoff:
            continue
        if line.type.lower() == "execution" and line.available:
            execution.add(line.device)
        entry = entries.get((line.device, line.data_item_id))
        if entry is None or entry.tool_sensor is None:
            continue
        if not line.available or line.number() is None:
            continue
        signals[entry.device][entry.tool_sensor] = entry.units or "unit not stated"
    machine = {
        device: values
        for device, values in signals.items()
        if any(sensor != "air_temperature" for sensor in values)
    }
    if not machine:
        raise ValueError(
            "no numeric machine sensors in the authorized, mapped capture "
            "at this cutoff; do not run a diagnosis"
        )
    factory = any("air_temperature" in values for values in signals.values())
    available = "; ".join(
        f"{device}: " + ", ".join(f"{sensor} ({unit})" for sensor, unit in sorted(values.items()))
        for device, values in sorted(machine.items())
    )
    common = (
        "READ-ONLY recorded telemetry, NOT the simulator. Tick 0 is the first "
        "recorded observation and 1 tick is 60 seconds of source time. "
        "The available machine readings are: "
        + available
        + ". Missing, stale or unrecorded signals are not evidence of normal operation. "
        "This capture has no confirmed root cause, maintenance record or safe action."
    )
    names = ["get_time"]
    # This tool refuses if any mapped machine lacks a known Execution state.
    if all(device in execution for device in machine):
        names.append("list_machines")
    names += ["get_readings", "get_sensor_trend"]
    if factory:
        names.append("get_factory_readings")
    names.append("get_sensor_summary")
    return tuple(
        tool_spec(name).model_copy(
            update={
                "description": (
                    f"{common} "
                    + {
                        "get_time": "Read the recorded cutoff time.",
                        "list_machines": "Read recorded machine Execution states; no job or fault inference.",
                        "get_readings": "Fetch time-stamped, mapped numeric machine values in a tick range.",
                        "get_sensor_trend": "Summarize recorded windows using time-weighted holds, never across gaps.",
                        "get_factory_readings": "Fetch the mapped factory air-temperature channel.",
                        "get_sensor_summary": "Summarize recorded values; absent data remains absent.",
                    }[name]
                )
            }
        )
        for name in names
    )


def run_recorded_investigation(
    lines: Sequence[Line],
    channel_map: ChannelMap,
    policy: ReasoningPolicy,
    *,
    machine_id: str,
    symptom: str,
    cutoff: datetime | None = None,
    timeout_seconds: float = 90.0,
) -> InvestigationState:
    """Run the existing investigation graph on an offline, read-only capture.

    The graph uses triage mode deliberately: it can investigate, hypothesize
    and conclude, but cannot propose, execute or verify a machine change.
    """
    # Variables:
    #   machine_id: The operator-confirmed machine, never guessed from sensor names.
    #   symptom: The operator's report, not a manufactured controller alarm.
    #   provider: Existing FactoryProvider contract backed by recorded JSONL.
    #   now: The replay cutoff; no tool can return a later observation.
    #   state: The graph's investigation state, with all intervention stages blocked.
    #   deps: Real provider and policy, but no simulator line-screening or critic.
    if not machine_id.strip() or not symptom.strip():
        raise ValueError("a confirmed machine and an operator symptom are required")
    provider = replay_provider(lines, channel_map, now=cutoff)
    now = provider._observations.now
    recorded_tool_specs(lines, channel_map, cutoff=now)
    mapped = {
        entry.device
        for entry in channel_map.entries
        if entry.tool_sensor not in (None, "air_temperature")
        and any(
            isinstance(row, TelemetryRecord)
            and row.device in (entry.device, entry.device_uuid)
            and row.data_item_id == entry.data_item_id
            and row.source_timestamp <= now
            and row.available
            and row.number() is not None
            for row in lines
        )
    }
    if machine_id not in mapped:
        raise ValueError(
            f"{machine_id!r} has no visible mapped numeric readings at this cutoff"
        )
    # Even a scripted policy may use the provider's complete contract: its
    # physical action methods still refuse; triage never reaches those stages.
    run_id = run_id_for(f"recorded/{uuid4().hex}")
    state = InvestigationState(
        run_id=run_id,
        investigation_id=investigation_id_for(run_id, 1),
        anomaly=DetectedAnomaly(
            tick=provider._observations.tick_of(now),
            machine_id=machine_id,
            kind="operator_observation",
            description=symptom,
        ),
        mode="triage",
        budgets=triage_budgets(seconds=timeout_seconds),
        line_context_enabled=False,
    )
    deps = InvestigationDeps(
        provider=provider,
        policy=policy,
        clock=monotonic,
        screening_available=False,
        step_questions=2,
        decide_calls=1,
    )
    run_investigation(state, deps)
    return state


def main(argv: Sequence[str] | None = None) -> int:
    """Run an opt-in model investigation of private, recorded data."""
    # Variables:
    #   args: Private capture, map, optional hash-verification probe and symptom.
    #   lines: Recorded machine observations; never sent to a repository.
    #   tools: Capabilities exposed to the LLM, limited to the capture's fields.
    #   policy: The existing model policy using the project's configured models.
    #   state: Final read-only report; no intervention is attempted.
    parser = argparse.ArgumentParser(prog="python -m capstone.replay_investigation")
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True, help="saved /probe, to verify the map")
    parser.add_argument("--machine", required=True, help="operator-confirmed controller device name")
    parser.add_argument("--symptom", required=True, help="operator-observed issue, not a diagnosis")
    parser.add_argument("--cutoff", help="ISO 8601 date with timezone; default last observation")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--out", type=Path, help="private output JSON, outside the repository")
    args = parser.parse_args(argv)
    if args.out and refusal(args.out, "--out"):
        parser.error("private investigation reports must stay outside the git checkout")
    channel_map = ChannelMap.model_validate_json(args.map.read_text(encoding="utf-8"))
    channel_map.verify_probe(args.probe.read_text(encoding="utf-8"))
    lines = read_capture(args.capture)
    cutoff = None
    if args.cutoff:
        cutoff = datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            parser.error("--cutoff needs a timezone")
    tools = recorded_tool_specs(lines, channel_map, cutoff=cutoff)
    # Models see only supported observation tools. These calls can transfer
    # private telemetry to an external provider: operator authorization is required.
    from capstone.agent.model_policy import ModelPolicy
    from capstone.providers.chat import clients_for_jobs, late_clients
    from capstone.settings import get_settings

    policy = ModelPolicy(
        {**clients_for_jobs(), **late_clients()},
        tools,
        late_seconds=get_settings().late_model_seconds,
    )
    state = run_recorded_investigation(
        lines,
        channel_map,
        policy,
        machine_id=args.machine,
        symptom=args.symptom,
        cutoff=cutoff,
        timeout_seconds=args.timeout_seconds,
    )
    report = {
        "source": "replay",
        "read_only": True,
        "run_id": str(state.run_id),
        "machine_id": args.machine,
        "conclusion": state.conclusion.model_dump(mode="json") if state.conclusion else None,
        "termination_reason": state.termination_reason,
        "tool_calls": state.tool_call_count,
        "failed_tool_calls": state.failed_tool_calls,
        "screening_tool_calls": state.screening_tool_calls_used,
    }
    output = json.dumps(report, indent=2, default=str)
    if args.out:
        args.out.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
