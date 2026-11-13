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
        outcomes = Counter(call.outcome for call in self.calls)
        statuses = Counter(item.status for item in self.items)
        sources = Counter(item.source_type for item in self.items)
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
        return counts
