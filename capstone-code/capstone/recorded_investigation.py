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

With --baseline (technician-approved calibrated baselines, see
`capstone.ingestion.haas_screen`), the capture is screened first and the
investigation starts only if the calibrated detector flags a signal; the
trigger then names the machine and writes the observation, so --machine and
--description are not needed:
    uv run python -m capstone.recorded_investigation --capture ...         --channel-map ... --probe ... --baseline /private/baselines.json         --authorized-item-id S1load --screen-out /private/screen.json         --out /private/review.json --approved-remote-model

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
from capstone.ingestion.haas_screen import load_baselines, screen_capture
from capstone.ingestion.privacy import refusal
from capstone.ingestion.record import Line, TelemetryRecord
from capstone.providers.chat import clients_for_jobs, late_clients, triage_clients
from capstone.providers.factory import research_tools
from capstone.providers.replay import replay_provider
from capstone.settings import get_settings


def replay_tool_specs(
    lines: Sequence[Line],
    channel_map: ChannelMap,
    *,
    now: datetime,
    tick_seconds: int = 60,
    approved_event_item_ids: frozenset[str] = frozenset(),
) -> tuple[ToolSpec, ...]:
    """Offer only research capabilities that this recorded window can answer."""
    # Variables:
    #   visible: Recorded observations at or before the replay cutoff, never future data.
    #   machines: Available numeric sensor names by actual captured machine.
    #   factory: Whether a mapped ambient-temperature channel has a numeric value.
    #   execution: Devices with observed Execution events, needed for list_machines.
    #   kinds: The device-and-sensor facts included in tool descriptions and schemas.
    #   event_capable: True only when a person approved event data items and at
    #     least one of them was recorded before the cutoff; only then is
    #     get_events offered to the model.
    visible = [
        row
        for row in lines
        if isinstance(row, TelemetryRecord) and row.source_timestamp <= now
    ]
    machines: dict[str, set[str]] = {}
    factory = False
    event_capable = bool(approved_event_item_ids) and any(
        row.data_item_id in approved_event_item_ids
        and row.category in ("EVENT", "CONDITION")
        for row in visible
    )
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
        elif name == "get_events":
            if not event_capable:
                continue
            detail = (
                "Approved, recorded MTConnect status and condition events only; "
                "unknown/partial coverage is refused rather than returned empty."
            )
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
    approved_event_item_ids: frozenset[str] = frozenset(),
    budgets: Budgets | None = None,
    clock: Callable[[], float] = monotonic,
) -> InvestigationState:
    """Run the same Pydantic graph on a recording, always in read-only triage."""
    # Variables:
    #   provider: The real-data FactoryProvider; all action methods refuse changes.
    #   look: Its recorded observations, which own the replay cutoff and time axis.
    #   state: A fresh TRIAGE investigation, so no proposal or execution stage runs.
    #     It takes the triage settings, including TRIAGE_CONCLUDE_CAP, which
    #     holds its conclusion question to the conclusion window.
    #   deps: Graph dependencies with no live controller or simulator truth.
    #   approved_event_item_ids: EVENT/CONDITION data items a person approved;
    #     passed to both the provider and the tool list, so they always agree.
    if not description.strip():
        raise ValueError("a nonempty operator observation is required")
    provider = replay_provider(
        lines,
        channel_map,
        tick_seconds=tick_seconds,
        now=now,
        approved_event_item_ids=approved_event_item_ids,
    )
    look = provider._observations
    available = replay_tool_specs(
        lines,
        channel_map,
        now=look.now,
        tick_seconds=tick_seconds,
        approved_event_item_ids=approved_event_item_ids,
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
    profile = settings.effective_triage
    run_id = run_id_for(f"replay/{machine_id}/{look.now.isoformat()}/{description}")
    state = make_recorded_state(
        run_id,
        machine_id=machine_id,
        description=description,
        tick=look.tick_of(look.now),
        budgets=budgets,
        stage_context=settings.stage_context,
        state_action_bar=settings.state_action_bar,
        triage_packet=profile.packet,
        triage_packet_prompt=profile.packet_prompt,
        triage_conclude_brief=settings.triage_conclude_brief,
        triage_conclude_cap=settings.triage_conclude_cap,
        triage_ranking=settings.triage_ranking,
        triage_fixed_plan=profile.plan == "fixed",
    )
    state.triage_run_mode = profile.run_mode
    state.triage_observe_separate = profile.observe_calls == "separate"
    # Preserve the recording's prior zero-reserve behavior in custom mode.
    # Deterministic mode likewise needs no model Hypothesize time reserve.
    state.triage_hypothesis_seconds = 0.0
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
        triage_run_mode=profile.run_mode,
        triage_investigate=profile.investigate,
        triage_allowed_sources=("replay",),
        triage_hypothesize=profile.hypothesize,
        triage_tool_specs=tuple(spec for spec in available if spec.name != "wait"),
        triage_channels={
            machine_id: tuple(
                sorted(
                    {
                        entry.tool_sensor
                        for entry in channel_map.entries
                        if entry.device == machine_id
                        and entry.tool_sensor not in (None, "air_temperature")
                        and any(
                            isinstance(row, TelemetryRecord)
                            and row.source_timestamp <= look.now
                            and row.data_item_id == entry.data_item_id
                            and row.device in (entry.device, entry.device_uuid)
                            and row.available
                            and row.number() is not None
                            and math.isfinite(row.number())
                            for row in lines
                        )
                    }
                )
            )
        },
        triage_evidence_tests=profile.evidence_tests,
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
    #   approved_events: The --approved-event-id values; empty keeps get_events off.
    #   report: With --baseline, the calibrated detector's verdict at the cutoff;
    #     its trigger, if any, decides whether the investigation runs and on
    #     which machine, and writes the observation it starts from.
    #   machine, description: The investigation's machine and observation: from
    #     --machine/--description, or from the detector's trigger.
    #   outputs: Every file this run writes (--out, and --screen-out with a
    #     baseline); each is privacy-checked, must be new and is never a source.
    parser = argparse.ArgumentParser(prog="python -m capstone.recorded_investigation")
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--channel-map", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--machine", help="required unless --baseline is given")
    parser.add_argument(
        "--approved-event-id",
        action="append",
        default=[],
        help="explicitly authorized MTConnect EVENT/CONDITION data-item ID (repeatable)",
    )
    parser.add_argument("--description", help="required unless --baseline is given")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="JSON list of technician-approved calibrated signal baselines; "
        "screen first and investigate only a flagged signal",
    )
    parser.add_argument(
        "--authorized-item-id",
        action="append",
        default=[],
        help="MTConnect SAMPLE data-item ID approved for detector analysis (repeatable)",
    )
    parser.add_argument(
        "--window-seconds",
        type=float,
        help="score only samples this many seconds before the cutoff",
    )
    parser.add_argument(
        "--screen-out",
        type=Path,
        help="private path for the detector report; required with --baseline",
    )
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
    if args.baseline is None:
        if not args.machine or not args.description:
            parser.error("--machine and --description are required without --baseline")
        if args.authorized_item_id or args.screen_out or args.window_seconds:
            parser.error(
                "--authorized-item-id, --screen-out and --window-seconds "
                "need --baseline"
            )
    else:
        if args.machine or args.description:
            parser.error("with --baseline the detector's trigger names the machine")
        if args.screen_out is None:
            parser.error("--baseline requires --screen-out")
        if not args.authorized_item_id:
            parser.error("--baseline requires at least one --authorized-item-id")
    outputs = [("--out", args.out)]
    if args.screen_out is not None:
        outputs.append(("--screen-out", args.screen_out))
        if args.screen_out == args.out:
            parser.error("--screen-out and --out must be different files")
    sources = (args.capture, args.channel_map, args.probe, args.baseline)
    for flag, path in outputs:
        problem = refusal(path, flag)
        if problem:
            parser.error(problem)
        if path.exists():
            parser.error(f"{flag} already exists; choose a fresh private path")
        if path in sources:
            parser.error(f"{flag} cannot overwrite a source file")
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
        approved_events = frozenset(args.approved_event_id)
        machine, description = args.machine, args.description
        if args.baseline is not None:
            report = screen_capture(
                captured,
                channel_map,
                load_baselines(args.baseline, channel_map),
                authorized_item_ids=frozenset(args.authorized_item_id),
                cutoff=cutoff,
                window_seconds=args.window_seconds,
            )
            with args.screen_out.open("x", encoding="utf-8") as output:
                output.write(report.model_dump_json(indent=2) + "\n")
            if report.trigger is None:
                print(
                    "calibrated detector flagged no signal; no investigation "
                    f"started, no model called. Report: {args.screen_out}"
                )
                return 0
            machine = report.trigger.machine_id
            description = report.trigger.description()
        tool_specs = replay_tool_specs(
            captured,
            channel_map,
            now=cutoff,
            approved_event_item_ids=approved_events,
        )
        if len(tool_specs) <= 1:
            raise ValueError("no supported observation tools in this capture")
        from capstone.agent.model_policy import ModelPolicy

        settings = get_settings()
        policy = ModelPolicy(
            {**clients_for_jobs(), **late_clients(), **triage_clients()},
            tool_specs,
            late_seconds=settings.late_model_seconds,
        )
        state = run_recorded_investigation(
            captured,
            channel_map,
            policy,
            machine_id=machine,
            description=description,
            now=cutoff,
            approved_event_item_ids=approved_events,
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
