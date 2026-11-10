# Controller-agnostic checklist and evidence gate for one approved shop machine.
# Responsibility: fail closed on missing consent, undocumented fields and bad captures.
"""Offline preflight for a read-only, one-machine manufacturer visit.

    uv run python -m capstone.ingestion.pilot_preflight template --out ../pilot-data/plan.json
    uv run python -m capstone.ingestion.pilot_preflight check --plan ../pilot-data/plan.json --stage discovery
    uv run python -m capstone.ingestion.pilot_preflight check --plan ../pilot-data/plan.json --stage capture \
        --probe ../pilot-data/probe.xml --map ../pilot-data/channel-map.json \
        --capture ../pilot-data/telemetry.jsonl --events ../pilot-data/events.csv

The plan is a PRIVATE checklist, not a legal agreement, a permission grant,
a network scanner, or evidence that the shop consented. A human must verify
the original authorization. No controller type or live network is assumed.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from capstone.ingestion.channel_map import ChannelMap, check_capture, read_capture
from capstone.ingestion.privacy import refusal
from capstone.ingestion.record import Line, TelemetryRecord
from capstone.ingestion.visit_log import TechnicianEvent, check_visit, load_event_log

Stage = Literal["discovery", "capture", "week"]


class PilotPlan(BaseModel):
    """Human-filled, private inventory; blank fields mean NOT confirmed."""

    model_config = ConfigDict(extra="forbid")

    site_name: str | None = None
    visit_date: str | None = None
    shop_contact: str | None = None
    machine_id: str | None = None
    manufacturer: str | None = None
    controller_model: str | None = None
    controller_software: str | None = None
    read_only_method: str | None = None
    manager_approver: str | None = None
    it_ot_approver: str | None = None
    written_approval_reference: str | None = None
    capture_authorized: bool = False
    approved_data_item_ids: list[str] = Field(default_factory=list)
    approved_poll_seconds: float | None = None
    private_storage_location: str | None = None
    retention_days: int | None = None
    stop_and_delete_procedure: str | None = None
    event_log_owner: str | None = None
    clocks_verified_by_human: bool = False
    normal_cycles_confirmed_by_technician: bool = False
    # A short connection test and a 7-day unattended pilot are separate scopes.
    seven_day_capture_authorized: bool = False
    named_collector_restart_contact: str | None = None
    disk_and_rotation_plan: str | None = None
    # Never treat a data collection approval as permission to send readings to an LLM.
    external_llm_transfer_authorized: bool = False


class PreflightReport(BaseModel):
    """What can and cannot yet be asserted from the private plan and files."""

    model_config = ConfigDict(frozen=True)
    stage: Stage
    ready: bool
    blocked: tuple[str, ...]
    warnings: tuple[str, ...]
    observations: int = 0
    mapped_channels: int = 0
    operator_events_matched: int = 0


def check_pilot(
    plan: PilotPlan,
    *,
    stage: Stage = "discovery",
    probe_xml: str | None = None,
    channel_map: ChannelMap | None = None,
    lines: Sequence[Line] | None = None,
    events: Sequence[TechnicianEvent] | None = None,
) -> PreflightReport:
    """Evaluate only provable readiness, never invent approval or machine facts."""
    # Variables:
    #   blocked: Missing required evidence/permission that prevents this stage.
    #   warnings: Work that cannot be proved from files (e.g. signed consent validity).
    #   mapped: Channels in the versioned map that correspond to this one machine.
    #   samples: Observations, excluding collector markers and UNAVAILABLE values.
    #   checks: Probe/map agreement and event-to-telemetry timestamp matching.
    blocked: list[str] = []
    warnings = [
        "Human review of original authorization, production impact and shop policy is mandatory.",
        "This offline report does not establish access permission or certify a controller safe.",
    ]
    for key, label in (
        ("site_name", "facility identity"),
        ("visit_date", "confirmed visit date"),
        ("shop_contact", "named shop contact"),
        ("machine_id", "exact target machine identifier"),
        ("manufacturer", "machine manufacturer"),
        ("controller_model", "controller model/generation"),
    ):
        if not getattr(plan, key):
            blocked.append(f"missing {label}")
    observations = 0
    mapped_channels = 0
    operator_events_matched = 0
    if stage in ("capture", "week"):
        for key, label in (
            ("read_only_method", "approved read-only interface or export method"),
            ("manager_approver", "named authorized manager approver"),
            ("it_ot_approver", "named IT/OT technical approver"),
            ("written_approval_reference", "private reference to written permission"),
            ("private_storage_location", "approved private data storage"),
            ("stop_and_delete_procedure", "documented stop/revocation and deletion steps"),
            ("event_log_owner", "operator/technician responsible for event notes"),
        ):
            if not getattr(plan, key):
                blocked.append(f"missing {label}")
        if not plan.capture_authorized:
            blocked.append("read-only collection has not been explicitly authorized")
        if not plan.approved_data_item_ids:
            blocked.append("no explicit per-channel data-field allowlist")
        if (
            plan.approved_poll_seconds is None
            or plan.approved_poll_seconds < 1
        ):
            blocked.append("no approved collection interval of at least one second")
        if plan.retention_days is None or plan.retention_days < 1:
            blocked.append("no approved positive retention period")
        if probe_xml is None or channel_map is None or lines is None or events is None:
            blocked.append("missing probe, channel map, capture or operator CSV")
        else:
            try:
                channel_map.verify_probe(probe_xml)
            except ValueError as error:
                blocked.append(f"probe/channel-map mismatch: {error}")
            checks = check_capture(channel_map, lines)
            if not checks.clean:
                blocked.append(
                    f"capture has {len(checks.unmapped)} unmapped channel(s) "
                    f"and {len(checks.mismatched)} type mismatch(es)"
                )
            allowed = set(plan.approved_data_item_ids)
            probe_ids = {entry.data_item_id for entry in channel_map.entries}
            unknown_permission = allowed - probe_ids
            if unknown_permission:
                blocked.append(
                    "approved fields not present in probe: "
                    + ", ".join(sorted(unknown_permission))
                )
            samples = [line for line in lines if isinstance(line, TelemetryRecord)]
            observations = len(samples)
            disallowed = {line.data_item_id for line in samples} - allowed
            if disallowed:
                blocked.append(
                    "capture includes fields not explicitly authorized: "
                    + ", ".join(sorted(disallowed))
                )
            mapped = [
                entry
                for entry in channel_map.entries
                if plan.machine_id in (entry.device, entry.device_uuid)
            ]
            mapped_channels = len(mapped)
            if not mapped:
                blocked.append("selected machine does not appear in the saved probe")
            names = {n for entry in mapped for n in (entry.device, entry.device_uuid)}
            other_machines = {line.device for line in samples if line.device not in names}
            if other_machines:
                blocked.append("recorded data includes a different machine: " + ", ".join(sorted(other_machines)))
            mapped_numeric = {
                (entry.device, entry.data_item_id)
                for entry in mapped
                if entry.tool_sensor is not None
            }
            observed_numeric = any(
                entry.data_item_id == line.data_item_id
                and line.device in (entry.device, entry.device_uuid)
                and line.number() is not None
                for entry in mapped
                for line in samples
                if entry.tool_sensor is not None and line.available
            )
            if not mapped_numeric or not observed_numeric:
                blocked.append("no useful, actually observed numeric mapped sensor")
            visit = check_visit(probe_xml, lines, events)
            operator_events_matched = len(visit.matches) - len(visit.unmatched)
            if not visit.ready:
                blocked.append(
                    "probe/capture/operator-log visit check failed "
                    f"({len(visit.unmatched)} unmatched events, {visit.observations} observations)"
                )
            if visit.gaps:
                warnings.append(
                    f"{visit.gaps} collection gap marker(s): review data coverage before analyzing trends"
                )
        if not plan.clocks_verified_by_human:
            blocked.append("controller and operator clock agreement not verified")
        if not plan.normal_cycles_confirmed_by_technician:
            blocked.append("normal cycles not confirmed by a technician")
        if not plan.external_llm_transfer_authorized:
            warnings.append("External model transfer is NOT authorized by this plan.")
    if stage == "week":
        if not plan.seven_day_capture_authorized:
            blocked.append("seven-day collection requires separate explicit authorization")
        if not plan.named_collector_restart_contact:
            blocked.append("no named contact to restart/stop the collector")
        if not plan.disk_and_rotation_plan:
            blocked.append("no approved disk-capacity, rotation and recovery plan")
        warnings.append(
            "This confirms paperwork and initial evidence, NOT seven days of observed uptime."
        )
    return PreflightReport(
        stage=stage,
        ready=not blocked,
        blocked=tuple(blocked),
        warnings=tuple(warnings),
        observations=observations,
        mapped_channels=mapped_channels,
        operator_events_matched=operator_events_matched,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Create a blank private plan or check its discovery/capture/week readiness."""
    # Variables:
    #   args: The requested operation and private input/output paths.
    #   plan: Explicit, human-filled facts; every omitted field remains unknown.
    #   report: Offline assessment; never proof of the signed approval itself.
    parser = argparse.ArgumentParser(prog="python -m capstone.ingestion.pilot_preflight")
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template", help="write a blank private plan")
    template.add_argument("--out", type=Path, required=True)
    check = commands.add_parser("check", help="audit a private plan and evidence")
    check.add_argument("--plan", type=Path, required=True)
    check.add_argument("--stage", choices=("discovery", "capture", "week"), default="discovery")
    for arg in ("probe", "map", "capture", "events", "out"):
        check.add_argument("--" + arg, type=Path)
    args = parser.parse_args(argv)
    if args.command == "template":
        if refusal(args.out, "--out"):
            parser.error("private plan must be outside a git checkout")
        if args.out.exists():
            parser.error("refusing to overwrite an existing private plan")
        args.out.write_text(PilotPlan().model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"wrote blank private plan to {args.out}")
        return 0
    if args.out and refusal(args.out, "--out"):
        parser.error("private report must be outside a git checkout")
    plan = PilotPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    probe_xml = args.probe.read_text(encoding="utf-8") if args.probe else None
    channel_map = (
        ChannelMap.model_validate_json(args.map.read_text(encoding="utf-8"))
        if args.map
        else None
    )
    lines = read_capture(args.capture) if args.capture else None
    events = load_event_log(args.events) if args.events else None
    report = check_pilot(
        plan,
        stage=args.stage,
        probe_xml=probe_xml,
        channel_map=channel_map,
        lines=lines,
        events=events,
    )
    result = json.dumps(report.model_dump(mode="json"), indent=2)
    if args.out:
        args.out.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)
    return 0 if report.ready else 1


if __name__ == "__main__":
    sys.exit(main())
