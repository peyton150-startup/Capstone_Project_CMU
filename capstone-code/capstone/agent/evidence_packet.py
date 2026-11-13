# The typed contracts of the triage evidence packet.
# Responsibility: name what an item, a call and a packet hold; build nothing.
"""Contracts for the triage evidence packet (see `agent.triage_packet`).

Kept apart from the builder so `agent.state` can hold a packet without
importing the loop.
"""

from collections import Counter
from typing import Literal

from pydantic import Field

from capstone.contracts import Contract

# The most unscored items a TRIAGE COVERAGE section names; the rest are counted.
MAX_COVERAGE_MISSING = 8

SourceType = Literal[
    "live_sensor",  # readings or a summary of readings from one sensor
    "derived_screening",  # a score computed from readings against a reference
    "status",  # a status, setting or clock row: observed, not a measurement window
    "record_text",  # events, inspections, maintenance: what someone wrote or logged
    "manual",  # OEM guidance for the model of machine, never this machine now
    "memory",  # a past investigation's belief
]
ItemStatus = Literal["qualified", "missing", "context"]
CutoffRelation = Literal["before_cutoff", "after_cutoff", "unknown"]
CallRole = Literal["mandatory", "optional"]
CallOutcome = Literal[
    "observed", "failed", "repeated", "skipped_budget", "skipped_unavailable"
]


class PacketItem(Contract):
    """One observed, missing or text item, with where it came from."""

    machine_id: str | None = None
    sensor: str | None = None
    # "machine:sensor" for a physical channel; None for text and status rows.
    physical_root: str | None = None
    source_type: SourceType
    status: ItemStatus
    evidence_id: str | None = None
    missing_reason: str | None = None
    window_from_tick: int | None = None
    window_to_tick: int | None = None
    window_rule: str | None = None
    sample_count: int | None = Field(default=None, ge=0)
    observed_tick: int | None = Field(default=None, ge=0)
    cutoff: CutoffRelation = "unknown"
    # Screening only: [robust, plain] scores and the warm-up stage, as given.
    scores: tuple[float, float] | None = None
    warmup_stage: str | None = None
    # Text only: wording that reads like an instruction to a model.
    instruction_like: bool = False


class PacketCall(Contract):
    """One call the packet made or chose not to make."""

    tool: str
    role: CallRole
    outcome: CallOutcome
    qualified: bool = False
    evidence_id: str | None = None
    reason: str | None = None


class EvidencePacket(Contract):
    """What Observe established for a triage, and what it could not."""

    machine_id: str | None
    trigger_tick: int = Field(ge=0)
    observation_tick: int | None = Field(default=None, ge=0)
    sensor: str | None = None
    roster: tuple[str, ...] = ()
    roster_verified: bool = False
    machine_status: dict[str, str] = Field(default_factory=dict)
    screened_machines: tuple[str, ...] = ()
    absent_from_screening: tuple[str, ...] = ()
    unexpected_in_screening: tuple[str, ...] = ()
    screening_reference: str | None = None
    items: tuple[PacketItem, ...] = ()
    calls: tuple[PacketCall, ...] = ()

    @property
    def qualified_roots(self) -> tuple[str, ...]:
        """Distinct physical channels with at least one qualified item."""
        # Variables:
        #   roots: Physical roots in first-seen order; a screening score and a
        #     summary of the same channel add one root, not two.
        roots: dict[str, None] = {}
        for item in self.items:
            if item.status == "qualified" and item.physical_root is not None:
                roots.setdefault(item.physical_root, None)
        return tuple(roots)

    def counts(self) -> dict[str, int]:
        """Identifier-keyed counts for logging and records; no evidence text."""
        # Variables:
        #   outcomes: How many calls ended each way.
        #   statuses: How many items were qualified, missing or text context.
        #   sources: How many items came from each source type.
        #   by_source: Items per (status, source type), such as missing_live_sensor:
        #     what was qualified or missing from each kind of source.
        outcomes = Counter(call.outcome for call in self.calls)
        statuses = Counter(item.status for item in self.items)
        sources = Counter(item.source_type for item in self.items)
        by_source = Counter((item.status, item.source_type) for item in self.items)
        counts = {
            "calls_mandatory": sum(c.role == "mandatory" for c in self.calls),
            "calls_optional": sum(c.role == "optional" for c in self.calls),
            "calls_qualified": sum(c.qualified for c in self.calls),
            "qualified_roots": len(self.qualified_roots),
            "absent_from_screening": len(self.absent_from_screening),
        }
        counts.update({f"calls_{k}": v for k, v in sorted(outcomes.items())})
        counts.update({f"items_{k}": v for k, v in sorted(statuses.items())})
        counts.update({f"source_{k}": v for k, v in sorted(sources.items())})
        counts.update(
            {
                f"{status}_{source}": n
                for (status, source), n in sorted(by_source.items())
            }
        )
        return counts


def coverage_lines(packet: EvidencePacket) -> list[str]:
    """The packet's coverage as a short prompt section (TRIAGE_PACKET_PROMPT).

    Says what was observed and what was not, each with its evidence ID or
    reason, so the model knows what is missing even when old evidence is shown
    only as a stub. Built from identifiers, counts and reasons only: no scores,
    no record text, and no word about what is wrong.
    """
    # Variables:
    #   screening: The screening's ledger entry; its evidence ID and outcome.
    #   unscored: Screening items with no score, as where (reason).
    #   window: The alarmed sensor's window item, qualified or missing.
    #   skipped: Calls that were not answered: failed, repeated or skipped.
    #   roster: How the screening compares with the roster, or that the roster
    #     was not read.
    #   down: Roster machines whose reported status is not "running".
    screening = next((c for c in packet.calls if c.tool == "get_line_screening"), None)
    unscored = [
        f"{i.physical_root or i.machine_id or '?'} ({i.missing_reason})"
        for i in packet.items
        if i.source_type == "derived_screening"
        and i.status == "missing"
        and i.missing_reason != "absent_from_screening"
    ]
    window = next(
        (
            i
            for i in packet.items
            if i.source_type == "live_sensor" and i.machine_id == packet.machine_id
        ),
        None,
    )
    skipped = [
        f"{c.tool} ({c.outcome}{': ' + c.reason if c.reason else ''})"
        for c in packet.calls
        if c.outcome != "observed"
    ]
    as_of = packet.observation_tick
    lines = [
        "TRIAGE COVERAGE (what was and was not observed; not a diagnosis):",
        f"Trigger tick {packet.trigger_tick}; observed as of tick "
        f"{as_of if as_of is not None else 'unknown'}.",
    ]
    if screening is not None and screening.qualified:
        reference = (
            f", reference {packet.screening_reference}"
            if packet.screening_reference
            else ""
        )
        lines.append(
            f"Line screening {screening.evidence_id}{reference}: "
            f"{len(packet.screened_machines)} machine(s) returned."
        )
    else:
        reason = screening.reason if screening and screening.reason else "unavailable"
        lines.append(f"Line screening: none usable ({reason}).")
    if packet.roster_verified:
        roster = f"Roster: {len(packet.roster)} machine(s)"
        if packet.absent_from_screening:
            roster += "; absent from screening: " + ", ".join(
                packet.absent_from_screening
            )
        if packet.unexpected_in_screening:
            roster += "; screened but not on the roster: " + ", ".join(
                packet.unexpected_in_screening
            )
        down = [f"{m} {s}" for m, s in packet.machine_status.items() if s != "running"]
        if down:
            roster += "; not running: " + ", ".join(down)
        lines.append(roster + ".")
    else:
        lines.append("Roster: not read, so screening coverage is not verified.")
    shown = unscored[:MAX_COVERAGE_MISSING]
    more = len(unscored) - len(shown)
    lines.append(
        "Not scored by the screening: "
        + (", ".join(shown) if shown else "none")
        + (f" (+{more} more)" if more > 0 else "")
        + "."
    )
    if window is None:
        lines.append("Alarmed sensor window: not read.")
    elif window.status == "qualified":
        lines.append(
            f"Alarmed sensor window: {window.physical_root} ticks "
            f"{window.window_from_tick}-{window.window_to_tick}, "
            f"{window.sample_count} samples ({window.evidence_id})."
        )
    else:
        where = window.physical_root or window.machine_id or "?"
        lines.append(
            f"Alarmed sensor window: {where} missing ({window.missing_reason})."
        )
    if skipped:
        lines.append("Not answered: " + ", ".join(skipped) + ".")
    lines.append("A machine or sensor not observed here is not known to be healthy.")
    return lines
