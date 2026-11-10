# A controller-agnostic evidence gate for the first approved manufacturing visit.
# Responsibility: report what the shop visit actually proves, without assumptions.
"""Prepare and evaluate a private, read-only CNC pilot evidence packet.

The evaluator never contacts the shop, its controller, or a model provider.
Only the MTConnect capture path has automated validation today. An unknown
controller or a non-MTConnect offline export remains an explicit open task.
Operator and approval confirmations are self-reported; software cannot validate
a signature or prove that a recording caused zero production impact.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from capstone.ingestion.channel_map import ChannelMap, check_capture, read_capture
from capstone.ingestion.privacy import refusal
from capstone.ingestion.record import Line, TelemetryRecord
from capstone.ingestion.visit_log import (
    TechnicianEvent,
    check_visit,
    load_event_log,
)


class PilotManifest(BaseModel):
    """Private, human-supplied inventory and authorization for exactly one machine."""

    model_config = ConfigDict(extra="forbid")
    facility: str = "Prestige Manufacturing"
    machine_label: str | None = None
    manufacturer: str | None = None
    machine_model: str | None = None
    controller: str | None = None
    controller_revision: str | None = None
    access_method: Literal[
        "unknown", "mtconnect", "approved_offline_export", "other"
    ] = "unknown"
    owner_approved: bool = False
    it_ot_approved: bool = False
    authorization_reference: str | None = None
    approved_channels: list[str] = Field(default_factory=list)
    approved_poll_seconds: float | None = Field(default=None, gt=0)
    data_storage_location: str | None = None
    retention_days: int | None = Field(default=None, ge=1)
    revocation_contact: str | None = None
    clock_alignment_confirmed: bool = False
    normal_cycles_confirmed: int = Field(default=0, ge=0)
    no_production_impact_confirmed: bool = False
    collection_gaps_reviewed: bool = False
    continued_collection_approved: bool = False
    continued_collection_until: str | None = None
    restrictions: str | None = None


class PilotAcceptance(BaseModel):
    """A conservative evidence status; never a certificate of site approval."""

    model_config = ConfigDict(frozen=True)
    status: Literal["blocked", "pending_capture", "capture_verified"]
    blockers: list[str]
    observations: int = 0
    mapped_channels_with_values: int = 0
    event_entries_covered: int = 0
    gap_markers: int = 0
    note: str = (
        "Reported permissions and operating conditions require human "
        "verification; software does not certify approval or machine safety."
    )


def assess_pilot(
    manifest: PilotManifest,
    *,
    probe: str | None = None,
    mapping: ChannelMap | None = None,
    capture: Sequence[Line] | None = None,
    events: Sequence[TechnicianEvent] | None = None,
) -> PilotAcceptance:
    """Check site prerequisites and evidence; never infer an unknown controller."""
    # Variables:
    #   blockers: Missing approvals, configuration or files that prevent acceptance.
    #   visit: SM-4 evidence check aligning operator events to collection timestamps.
    #   channel_check: SM-1 comparison of recorded fields against the saved probe.
    #   uses: Mapped data items with at least one genuinely available observation.
    blockers: list[str] = []
    if not manifest.machine_label or not manifest.manufacturer:
        blockers.append("identify the particular machine and manufacturer")
    if not manifest.machine_model or not manifest.controller:
        blockers.append("record machine model and controller before choosing an adapter")
    if manifest.access_method == "unknown":
        blockers.append("controller access method is unknown; no protocol may be assumed")
    elif manifest.access_method != "mtconnect":
        blockers.append(
            "this access method needs its own validated, approved capture adapter; "
            "MTConnect evidence checks do not apply"
        )
    if not (manifest.owner_approved and manifest.it_ot_approved):
        blockers.append("obtain both owner/manager and IT/OT read-only approvals")
    if not manifest.authorization_reference:
        blockers.append("record where written pilot permission is held privately")
    if not manifest.approved_channels:
        blockers.append("approve a field list and data-use boundary")
    if manifest.access_method == "mtconnect" and manifest.approved_poll_seconds is None:
        blockers.append("approve controller-safe poll rate with IT/OT")
    if not manifest.data_storage_location or not manifest.retention_days:
        blockers.append("agree on local storage and retention/deletion policy")
    if not manifest.revocation_contact:
        blockers.append("name the shop contact who can stop collection immediately")
    if not manifest.no_production_impact_confirmed:
        blockers.append("confirm the approved test caused no observed production impact")
    if not manifest.clock_alignment_confirmed:
        blockers.append("compare controller/source clock against operator event times")
    if manifest.normal_cycles_confirmed < 3:
        blockers.append("have the technician confirm at least three normal cycles")
    if not manifest.continued_collection_approved:
        blockers.append("obtain explicit permission before leaving a collector running")
    if manifest.continued_collection_approved and not manifest.continued_collection_until:
        blockers.append("record when authorization to continue collection expires")

    observations = 0
    mapped = 0
    covered = 0
    gaps = 0
    complete = (
        probe is not None
        and mapping is not None
        and capture is not None
        and events is not None
    )
    if manifest.access_method == "mtconnect" and complete:
        try:
            mapping.verify_probe(probe)
        except ValueError:
            blockers.append("channel map does not match the saved controller probe")
        channel_check = check_capture(mapping, capture)
        if not channel_check.clean:
            blockers.append("captured data is unmapped or disagrees with the probe")
        uses = [row for row in channel_check.uses if row.available > 0]
        mapped = len(uses)
        observations = sum(
            isinstance(row, TelemetryRecord) for row in capture
        )
        if not uses:
            blockers.append("no mapped channels supplied usable observations")
        visit = check_visit(probe, capture, events)
        gaps = visit.gaps
        covered = sum(match.placement == "covered" for match in visit.matches)
        if not visit.ready:
            blockers.append("probe, observations and matching technician events incomplete")
        if gaps and not manifest.collection_gaps_reviewed:
            blockers.append("review and explain data gaps before declaring acceptance")
    else:
        blockers.append(
            "approved, replayable probe/map/capture/technician-event evidence not yet verified"
        )
    if blockers:
        status = "blocked" if (
            not manifest.owner_approved
            or not manifest.it_ot_approved
            or manifest.access_method == "unknown"
        ) else "pending_capture"
    else:
        status = "capture_verified"
    return PilotAcceptance(
        status=status,
        blockers=blockers,
        observations=observations,
        mapped_channels_with_values=mapped,
        event_entries_covered=covered,
        gap_markers=gaps,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Write a private manifest template or an evidence-based acceptance report."""
    # Variables:
    #   args: Commands and private paths chosen by the user.
    #   manifest: Site-specific observations and approvals, not a generated guess.
    #   report: Explicit blockers or verified capture counts, never an invented pass.
    parser = argparse.ArgumentParser(prog="python -m capstone.ingestion.pilot_acceptance")
    actions = parser.add_subparsers(dest="command", required=True)
    template = actions.add_parser("template")
    template.add_argument("--out", required=True, type=Path)
    check = actions.add_parser("check")
    check.add_argument("--manifest", required=True, type=Path)
    check.add_argument("--probe", type=Path)
    check.add_argument("--map", type=Path)
    check.add_argument("--capture", type=Path)
    check.add_argument("--events", type=Path)
    check.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    problem = refusal(args.out, "--out")
    if problem:
        parser.error(problem)
    if args.out.exists():
        parser.error("refusing to overwrite an existing private pilot artifact")
    if args.command == "template":
        args.out.write_text(PilotManifest().model_dump_json(indent=2) + "\n")
        print(f"saved a private, unapproved pilot template: {args.out}")
        return 0
    if args.out in (args.manifest, args.probe, args.map, args.capture, args.events):
        parser.error("report may not replace any input artifact")
    try:
        manifest = PilotManifest.model_validate_json(
            args.manifest.read_text(encoding="utf-8")
        )
        report = assess_pilot(
            manifest,
            probe=args.probe.read_text(encoding="utf-8") if args.probe else None,
            mapping=ChannelMap.model_validate_json(
                args.map.read_text(encoding="utf-8")
            ) if args.map else None,
            capture=read_capture(args.capture) if args.capture else None,
            events=load_event_log(args.events) if args.events else None,
        )
        args.out.write_text(report.model_dump_json(indent=2) + "\n")
    except (OSError, ValueError) as error:
        print(f"pilot evidence could not be checked: {error}", file=sys.stderr)
        return 2
    print(f"{report.status}: {len(report.blockers)} open acceptance items")
    for reason in report.blockers:
        print(f"  - {reason}")
    return 0 if report.status == "capture_verified" else 1


if __name__ == "__main__":
    sys.exit(main())
