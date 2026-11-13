# Review an approved recorded CNC capture through the existing investigation graph.
# Responsibility: offer only supported replay tools and prohibit controller writes.
"""Offline, read-only agent review of a versioned real-machine capture.

There is no live CNC connection here. The caller supplies an authorized,
locally stored MTConnect JSONL capture and its independently checked channel
map. The graph investigates the operator's observation in TRIAGE mode;
it cannot propose, execute, or verify a physical intervention.

CLI usage from capstone-code/ (only with the shop's documented permission):
    uv run python -m capstone.recorded_investigation --capture /private/telemetry.jsonl \
        --channel-map /private/channel-map.json --probe /private/probe.xml \
        --machine VF2 --description "Review spindle load trend" \
        --out /private/review.json --approved-remote-model

The --approved-remote-model flag explicitly acknowledges that extracted shop
telemetry will be sent to the configured model provider. It does not grant
permission: obtain owner and IT/OT approval before using this command.
"""

import argparse
import copy
import math
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from time import monotonic

from capstone.agent.investigation import run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.agent.model_policy import ModelPolicy
from capstone.agent.policy import ReasoningPolicy
from capstone.agent.recorded_state import make_recorded_state
from capstone.agent.state import Budgets, InvestigationState
from capstone.contracts.investigations import run_id_for
from capstone.contracts.tools import ToolSpec
from capstone.ingestion.channel_map import ChannelMap, check_capture, read_capture
from capstone.ingestion.privacy import refusal
from capstone.ingestion.record import Line, TelemetryRecord
from capstone.providers.chat import clients_for_jobs, late_clients
from capstone.providers.factory import research_tools
from capstone.providers.replay import replay_provider
from capstone.settings import get_settings


def replay_tool_specs(
    lines: Sequence[Line],
    channel_map: ChannelMap,
    *,
    now: datetime,
    tick_seconds: int = 60,
) -> tuple[ToolSpec, ...]:
    """Offer only research capabilities that this recorded window can answer."""
    # Variables:
    #   visible: Recorded observations at or before the replay cutoff, never future data.
    #   machines: Available numeric sensor names by actual captured machine.
    #   factory: Whether a mapped ambient-temperature channel has a numeric value.
    #   execution: Devices with observed Execution events, needed for list_machines.
    #   kinds: The device-and-sensor facts included in tool descriptions and schemas.
    visible = [
        row
        for row in lines
        if isinstance(row, TelemetryRecord) and row.source_timestamp <= now
    ]
    machines: dict[str, set[str]] = {}
    factory = False
    execution = {
        row.device for row in visible if row.type == "Execution" and row.available
    }
    for entry in channel_map.entries:
        if entry.tool_sensor is None:
            continue
        measured = any(
            row.data_item_id == entry.data_item_id
            and row.device in (entry.device, entry.device_uuid)
            and row.available
            and row.number() is not None
            and math.isfinite(row.number())
            for row in visible
        )
        if not measured:
            continue
        if entry.tool_sensor == "air_temperature":
            factory = True
        else:
            machines.setdefault(entry.device, set()).add(entry.tool_sensor)

    kinds = ", ".join(
        f"{device}: {', '.join(sorted(sensors))}"
        for device, sensors in sorted(machines.items())
    )
    end = max(
        (row.source_timestamp for row in lines if isinstance(row, TelemetryRecord)),
        default=now,
    )
    specs: list[ToolSpec] = []
    for spec in research_tools():
        name = spec.name
        if name == "get_time":
            detail = (
                f"Recorded machine time. One replay tick is {tick_seconds} seconds."
            )
        elif name == "list_machines":
            if not machines or not all(device in execution for device in machines):
                continue
            detail = "Machine status from observed Execution values only."
        elif name in {"get_readings", "get_sensor_trend", "get_sensor_summary"}:
            if not machines and not (factory and name == "get_sensor_summary"):
                continue
            detail = (
                "Recorded observations only, never simulated machine values. "
                f"Available machine/sensor pairs: {kinds or 'none'}. "
                f"Ambient sensor: {'air_temperature' if factory else 'unavailable'}. "
                f"One tick is {tick_seconds} seconds; units are from the probe. "
                "Unknown or unsupported pairs are refused; no values are inferred."
            )
        elif name == "get_factory_readings":
            if not factory:
                continue
            detail = "Recorded air_temperature only; units from the probe."
        elif name == "wait":
            if now >= end:
                continue
            detail = "Advance the recorded cutoff, never a real controller."
        else:
            # No jobs, settings, simulated line screening, maintenance records,
            # inspections, events or shop-floor interventions in this capture.
            continue
        schema = copy.deepcopy(spec.arguments)
        if name in {"get_readings", "get_sensor_trend", "get_sensor_summary"}:
            options = sorted(
                {sensor for sensors in machines.values() for sensor in sensors}
            )
            if name == "get_sensor_summary" and factory:
                options.append("air_temperature")
            if "sensor" in schema.get("properties", {}):
                schema["properties"]["sensor"]["enum"] = sorted(set(options))
        specs.append(
            spec.model_copy(update={"description": detail, "arguments": schema})
        )
    return tuple(specs)


def run_recorded_investigation(
    lines: Sequence[Line],
    channel_map: ChannelMap,
    policy: ReasoningPolicy,
    *,
    machine_id: str,
    description: str,
    now: datetime | None = None,
    tick_seconds: int = 60,
    budgets: Budgets | None = None,
    clock: Callable[[], float] = monotonic,
) -> InvestigationState:
    """Run the same Pydantic graph on a recording, always in read-only triage."""
    # Variables:
    #   provider: The real-data FactoryProvider; all action methods refuse changes.
    #   look: Its recorded observations, which own the replay cutoff and time axis.
    #   state: A fresh TRIAGE investigation, so no proposal or execution stage runs.
    #   deps: Graph dependencies with no live controller or simulator truth.
    if not description.strip():
        raise ValueError("a nonempty operator observation is required")
    provider = replay_provider(lines, channel_map, tick_seconds=tick_seconds, now=now)
    look = provider._observations
    available = replay_tool_specs(
        lines, channel_map, now=look.now, tick_seconds=tick_seconds
    )
    listed = " ".join(tool.description for tool in available)
    if not any(
        entry.device == machine_id
        and entry.tool_sensor not in (None, "air_temperature")
        for entry in channel_map.entries
    ):
        raise ValueError("machine has no manually mapped observation channels")
    if machine_id not in listed:
        raise ValueError("machine has no captured numeric channels at this cutoff")
    if isinstance(policy, ModelPolicy):
        if {tool.name for tool in policy.tools} - {tool.name for tool in available}:
            raise ValueError("model policy exposes tools this capture cannot answer")

    settings = get_settings()
    run_id = run_id_for(f"replay/{machine_id}/{look.now.isoformat()}/{description}")
    state = make_recorded_state(
        run_id,
        machine_id=machine_id,
        description=description,
        tick=look.tick_of(look.now),
        budgets=budgets,
        stage_context=settings.stage_context,
        state_action_bar=settings.state_action_bar,
        triage_packet=settings.triage_packet,
    )
    step_questions = (
        settings.step_questions
        if callable(getattr(policy, "interpret_and_decide", None))
        else 2
    )
    decide_calls = (
        settings.decide_calls
        if step_questions == 2
        or callable(getattr(policy, "interpret_and_decide_many", None))
        else 1
    )
    deps = InvestigationDeps(
        provider=provider,
        policy=policy,
        clock=clock,
        screening_available=False,
        step_questions=step_questions,
        decide_calls=decide_calls,
        min_action_confidence=settings.min_action_confidence,
        state_action_bar=settings.state_action_bar,
    )
    return run_investigation(state, deps)


def main(argv: Sequence[str] | None = None) -> int:
    """Review an approved private capture and write an audit outside git."""
    # Variables:
    #   args: Explicitly named source files, machine, cutoff and consent flag.
    #   channel_map: Technician-mapped probe channels; verified against the probe.
    #   captured: Checked stored records; the tool never contacts an MTConnect agent.
    #   tool_specs: Only the recorded capabilities the remote model can request.
    #   state: The graph's typed conclusion and evidence, written to a private path.
    parser = argparse.ArgumentParser(prog="python -m capstone.recorded_investigation")
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--channel-map", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument(
        "--at", help="ISO source timestamp with UTC offset; default last"
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--approved-remote-model",
        action="store_true",
        help="explicitly acknowledge shop consent to share selected telemetry with LLM",
    )
    args = parser.parse_args(argv)
    if not args.approved_remote_model:
        parser.error(
            "remote model use requires documented shop authorization and "
            "--approved-remote-model"
        )
    problem = refusal(args.out, "--out")
    if problem:
        parser.error(problem)
    if args.out.exists():
        parser.error("review output already exists; choose a fresh private path")
    if args.out in (args.capture, args.channel_map, args.probe):
        parser.error("review output cannot overwrite a source file")
    try:
        channel_map = ChannelMap.model_validate_json(
            args.channel_map.read_text(encoding="utf-8")
        )
        channel_map.verify_probe(args.probe.read_text(encoding="utf-8"))
        captured = read_capture(args.capture)
        checked = check_capture(channel_map, captured)
        if checked.unmapped or checked.mismatched:
            raise ValueError(
                "capture disagrees with probe channel map; verify it before model use"
            )
        at = datetime.fromisoformat(args.at) if args.at else None
        if at is not None and at.utcoffset() is None:
            raise ValueError("--at requires a UTC offset")
        cutoff = at or max(
            row.source_timestamp for row in captured if isinstance(row, TelemetryRecord)
        )
        tool_specs = replay_tool_specs(captured, channel_map, now=cutoff)
        if len(tool_specs) <= 1:
            raise ValueError("no supported observation tools in this capture")
        from capstone.agent.model_policy import ModelPolicy

        settings = get_settings()
        policy = ModelPolicy(
            {**clients_for_jobs(), **late_clients()},
            tool_specs,
            late_seconds=settings.late_model_seconds,
        )
        state = run_recorded_investigation(
            captured,
            channel_map,
            policy,
            machine_id=args.machine,
            description=args.description,
            now=cutoff,
        )
        with args.out.open("x", encoding="utf-8") as output:
            output.write(state.model_dump_json(indent=2) + "\n")
    except (OSError, ValueError, StopIteration) as error:
        print(f"recorded review refused: {error}", file=sys.stderr)
        return 2
    print(
        f"read-only replay review saved privately: {args.out}; "
        f"recommendation={state.conclusion.recommendation if state.conclusion else 'unresolved'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
