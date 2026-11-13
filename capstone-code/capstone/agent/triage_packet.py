# The triage evidence packet: what Observe actually established, item by item.
# Responsibility: qualify observable evidence and name what is missing; never infer a cause.
"""A bounded, source-linked evidence packet for rapid triage (Block 2, Observe).

Built in Python by `investigation.observe` only when the investigation is a
triage (`mode == "triage"`) and `triage_packet_enabled` is set (TRIAGE_PACKET,
off by default). A deep run never builds one.

The packet does not decide anything. It records, for later Python stages:

- the incident cutoff (the trigger tick) and the tick the factory reported
  when the packet was built, so later data is never mistaken for trigger-time
  data;
- the expected-machine roster from `list_machines` and each machine's status,
  compared with the machines the line screening returned;
- one item per screened sensor, per relevant sensor window and per missing
  piece, each with its physical root (`machine:sensor`) so two views of one
  channel are never counted as two sources;
- a source type on every item: a live sensor window, a derived screening
  score, a status row, or text (records, manual, memory). Text is never a
  measurement: its items carry no values;
- a ledger of the packet's calls: mandatory or optional, and observed, failed,
  repeated or skipped, and whether the answer qualified.

Missing data stays missing with a reason. Nothing here turns "no data" into
"normal". It makes no model call and reads no hidden truth: only tool answers
already in the state, or gathered here through the normal `gather` path.
"""

import json

from capstone.agent.evidence_packet import (
    CallRole,
    CutoffRelation,
    EvidencePacket,
    PacketCall,
    PacketItem,
    SourceType,
)
from capstone.agent.incident_context import SENSOR_WORDS
from capstone.agent.loop import InvestigationDeps, gather
from capstone.agent.policy import CallTool
from capstone.agent.state import InvestigationState
from capstone.agent.untrusted import looks_like_instruction
from capstone.contracts.evidence import Evidence
from capstone.contracts.tools import ToolRequest

# The window before the trigger that the alarmed sensor is summarized over.
WINDOW_TICKS = 60
# Fewest samples a sensor window needs to count as a qualified observation.
# A packet policy for "enough to look at", never a health threshold.
MIN_WINDOW_SAMPLES = 10
# The screening's published window rule, as its tool description states it.
# The compact screening does not report each window's ticks or count.
SCREENING_WINDOW_RULE = (
    "latest running readings up to the observation tick (at most 60, at least 20)"
)

# Tools whose answers are sensor readings.
LIVE_SENSOR_TOOLS = frozenset(
    {"get_readings", "get_sensor_trend", "get_factory_readings", "get_sensor_summary"}
)
STATUS_TOOLS = frozenset({"get_time", "list_machines", "get_settings"})
SCREENING_TOOL = "get_line_screening"


def trigger_sensor(description: str) -> str | None:
    """The one sensor the trigger's words name, or None when none or several."""
    # Variables:
    #   words: The observed description, lowercased; never a fault label.
    #   named: Distinct sensors named; more than one means no guess.
    words = description.lower().replace("_", " ")
    named = {sensor for phrase, sensor in SENSOR_WORDS if phrase in words}
    return next(iter(named)) if len(named) == 1 else None


def source_type_of(tool: str | None, origin: str) -> SourceType:
    """The source type of a tool answer, from its tool and provenance origin.

    Memory and manual origins win over the tool name. An unknown tool counts
    as text, so it can never pass as a measurement.
    """
    # Variables:
    #   origin: The provenance label the loop wrote: observable, memory or manual.
    if origin == "memory":
        return "memory"
    if origin == "manual":
        return "manual"
    if tool in LIVE_SENSOR_TOOLS:
        return "live_sensor"
    if tool == SCREENING_TOOL:
        return "derived_screening"
    if tool in STATUS_TOOLS:
        return "status"
    return "record_text"


def cutoff_relation(last_tick: int | None, trigger_tick: int) -> CutoffRelation:
    """Whether data ending at `last_tick` lies wholly before the incident cutoff."""
    # Variables:
    #   last_tick: The tick of the data's last sample; None means it is not known.
    #   trigger_tick: The incident cutoff: the tick the alarm was raised.
    if last_tick is None:
        return "unknown"
    return "before_cutoff" if last_tick <= trigger_tick else "after_cutoff"


def text_item(state: InvestigationState, evidence: Evidence) -> PacketItem | None:
    """A context item for text evidence (records, manual, memory), or None.

    Text keeps its source label and evidence id for audit but carries no value,
    window or score: a note that says "normal" is not a normal reading.
    Wording that reads like an instruction is flagged, which is one signal and
    no proof that unflagged text is trustworthy.
    """
    # Variables:
    #   reference: The provenance the loop wrote when the evidence arrived.
    #   tool: The tool named in the evidence's source id ("source:tool").
    #   kind: The item's source type; anything but text returns None.
    reference = next(
        (p for p in state.provenance if p.evidence_id == evidence.id), None
    )
    tool = evidence.source_id.rsplit(":", 1)[-1]
    kind = source_type_of(tool, reference.origin if reference else "observable")
    if kind not in ("record_text", "manual", "memory"):
        return None
    return PacketItem(
        source_type=kind,
        status="context",
        evidence_id=evidence.id,
        observed_tick=evidence.observed_tick,
        cutoff="unknown",
        instruction_like=looks_like_instruction(evidence.content),
    )


def last_outcome(state: InvestigationState) -> str | None:
    """The outcome of the most recent decision record, if any."""
    # Variables:
    #   state.decisions: The loop's step records; `gather` appends one per call
    #     that did not become evidence, so the newest tells how it failed.
    return state.decisions[-1].outcome if state.decisions else None


def ledger_entry(
    state: InvestigationState,
    tool: str,
    role: CallRole,
    evidence: Evidence | None,
) -> PacketCall:
    """How one gathered call ended, read from the record `gather` left."""
    # Variables:
    #   outcome: "repeated_call" when gather skipped a repeat, else a failure.
    if evidence is not None:
        return PacketCall(
            tool=tool, role=role, outcome="observed", evidence_id=evidence.id
        )
    outcome = last_outcome(state)
    if outcome == "repeated_call":
        return PacketCall(
            tool=tool, role=role, outcome="repeated", reason="repeated_call"
        )
    return PacketCall(
        tool=tool, role=role, outcome="failed", reason=outcome or "tool_failed"
    )


def screening_items(
    machines: dict, observation_tick: int | None, trigger_tick: int
) -> list[PacketItem]:
    """One item per screened sensor, or per machine when the whole machine has a reason."""
    # Variables:
    #   cutoff: Screening windows end at or before the observation tick; when that
    #     is past the trigger, the window may hold later readings, so it is unknown.
    #   row: One machine's screening: sensor -> scores or reason, or one reason.
    #   entry: One sensor's [robust, plain] or [robust, plain, stage], or a reason.
    cutoff: CutoffRelation = (
        "before_cutoff"
        if observation_tick is not None and observation_tick <= trigger_tick
        else "unknown"
    )
    items = []
    for machine_id, row in machines.items():
        if not isinstance(row, dict) or not row:
            items.append(
                PacketItem(
                    machine_id=machine_id,
                    source_type="derived_screening",
                    status="missing",
                    missing_reason=row if isinstance(row, str) and row else "no_score",
                    window_rule=SCREENING_WINDOW_RULE,
                    cutoff=cutoff,
                )
            )
            continue
        for sensor, entry in row.items():
            root = f"{machine_id}:{sensor}"
            if isinstance(entry, list) and len(entry) >= 2:
                items.append(
                    PacketItem(
                        machine_id=machine_id,
                        sensor=sensor,
                        physical_root=root,
                        source_type="derived_screening",
                        status="qualified",
                        window_rule=SCREENING_WINDOW_RULE,
                        observed_tick=observation_tick,
                        cutoff=cutoff,
                        scores=(float(entry[0]), float(entry[1])),
                        warmup_stage=str(entry[2]) if len(entry) > 2 else None,
                    )
                )
            else:
                items.append(
                    PacketItem(
                        machine_id=machine_id,
                        sensor=sensor,
                        physical_root=root,
                        source_type="derived_screening",
                        status="missing",
                        missing_reason=entry if isinstance(entry, str) else "no_score",
                        window_rule=SCREENING_WINDOW_RULE,
                        cutoff=cutoff,
                    )
                )
    return items


def summary_item(
    machine_id: str, sensor: str, data: object, evidence: Evidence, trigger_tick: int
) -> PacketItem:
    """A live-sensor item from a get_sensor_summary answer, qualified or not."""
    # Variables:
    #   count: Samples in the window; fewer than MIN_WINDOW_SAMPLES is not enough.
    #   last: The last sample's tick, compared with the incident cutoff.
    #   relation: Whether the window's last sample is before the incident cutoff.
    #   reason: Why the window does not qualify, or None when it does.
    data = data if isinstance(data, dict) else {}
    count = data.get("sample_count")
    count = count if isinstance(count, int) and count >= 0 else None
    last = data.get("last_tick") if isinstance(data.get("last_tick"), int) else None
    relation = cutoff_relation(last, trigger_tick)
    if count is None:
        reason = "malformed_summary"
    elif count == 0:
        reason = "no_samples_in_window"
    elif count < MIN_WINDOW_SAMPLES:
        reason = "too_few_samples"
    elif relation == "after_cutoff":
        reason = "window_past_cutoff"
    else:
        reason = None
    return PacketItem(
        machine_id=machine_id,
        sensor=sensor,
        physical_root=f"{machine_id}:{sensor}",
        source_type="live_sensor",
        status="qualified" if reason is None else "missing",
        evidence_id=evidence.id,
        missing_reason=reason,
        window_from_tick=data.get("from_tick")
        if isinstance(data.get("from_tick"), int)
        else None,
        window_to_tick=data.get("to_tick")
        if isinstance(data.get("to_tick"), int)
        else None,
        sample_count=count,
        observed_tick=evidence.observed_tick,
        cutoff=relation,
    )


def optional_call(
    state: InvestigationState,
    deps: InvestigationDeps,
    name: str,
    arguments: dict,
    purpose: str,
    limit: int,
) -> tuple[PacketCall, Evidence | None]:
    """Make one optional read if the packet's share of research allows it."""
    # Variables:
    #   limit: The research call count the packet may reach, get_time included;
    #     the rest of the six-call default stays for investigation.
    #   evidence: The answer as evidence, or None when skipped, repeated or failed.
    if state.research_tool_calls >= limit or state.research_seconds(deps.clock()) <= 0:
        return PacketCall(
            tool=name, role="optional", outcome="skipped_budget", reason="budgeted_out"
        ), None
    step = CallTool(
        information_needed=purpose, request=ToolRequest(name=name, arguments=arguments)
    )
    evidence = gather(state, deps, "observe", step, interpret=False)
    return ledger_entry(state, name, "optional", evidence), evidence


def build_triage_packet(
    state: InvestigationState,
    deps: InvestigationDeps,
    time_evidence: Evidence | None,
    screening_evidence: Evidence | None,
) -> EvidencePacket:
    """Qualify Observe's evidence for a triage and gather up to two optional reads.

    The mandatory core was gathered by `observe` already: the time and, on the
    simulator, the line screening. This adds, within half the research calls
    (get_time included): the alarmed sensor's window up to the trigger, then
    the expected-machine roster. Each is skipped with a reason if it does not fit.
    """
    # Variables:
    #   trigger: The anomaly that started the triage: machine, cutoff tick, words.
    #   limit: The research call count the packet may reach (half the budget).
    #   calls: The ledger of every call, in order, mandatory first.
    #   items: Qualified, missing and text items, in order of discovery.
    #   sensor: The one sensor the trigger names; None means no window is guessed.
    #   machines: The screening's machine -> row map, or None without one.
    #   roster: Machine ids from list_machines, in line order; the expected set.
    #   observation_tick: The tick get_time reported, the packet's "as of" time,
    #     usually later than the trigger because monitoring scans in blocks.
    #   reference: The screening's named baseline source, kept as identity only.
    #   status: Each roster machine's reported status (running, idle, down).
    #   absent: Roster machines the screening did not return: unknown, never normal.
    #   covered: Evidence ids the ledger already accounts for, so only other
    #     evidence (text from earlier) is added as context items.
    trigger = state.anomaly
    observation_tick = time_evidence.observed_tick if time_evidence else state.last_tick
    limit = state.budgets.max_tool_calls // 2
    calls: list[PacketCall] = [
        ledger_entry_for_mandatory(state, "get_time", time_evidence)
    ]
    if time_evidence is not None:
        calls[0] = calls[0].model_copy(update={"qualified": True})
    items: list[PacketItem] = []
    machines: dict | None = None
    reference: str | None = None

    if not deps.screening_available:
        calls.append(
            PacketCall(
                tool=SCREENING_TOOL,
                role="mandatory",
                outcome="skipped_unavailable",
                reason="no_verified_healthy_reference",
            )
        )
        items.append(
            PacketItem(
                machine_id=trigger.machine_id,
                source_type="derived_screening",
                status="missing",
                missing_reason="no_verified_healthy_reference",
            )
        )
    else:
        entry = ledger_entry_for_mandatory(state, SCREENING_TOOL, screening_evidence)
        if screening_evidence is not None:
            try:
                data = json.loads(screening_evidence.content)
            except ValueError:
                data = None
            if isinstance(data, dict) and isinstance(data.get("machines"), dict):
                machines = data["machines"]
                reference = (
                    data.get("reference")
                    if isinstance(data.get("reference"), str)
                    else None
                )
                entry = entry.model_copy(update={"qualified": True})
            else:
                entry = entry.model_copy(update={"reason": "malformed_screening"})
        calls.append(entry)
        if machines is None:
            items.append(
                PacketItem(
                    machine_id=trigger.machine_id,
                    source_type="derived_screening",
                    status="missing",
                    missing_reason="screening_unavailable",
                )
            )
        else:
            items += [
                item.model_copy(update={"evidence_id": screening_evidence.id})
                for item in screening_items(machines, observation_tick, trigger.tick)
            ]

    sensor = trigger_sensor(trigger.description)
    if trigger.machine_id is None:
        calls.append(
            PacketCall(
                tool="get_sensor_summary",
                role="optional",
                outcome="skipped_unavailable",
                reason="no_trigger_machine",
            )
        )
    elif sensor is None:
        calls.append(
            PacketCall(
                tool="get_sensor_summary",
                role="optional",
                outcome="skipped_unavailable",
                reason="trigger_names_no_single_sensor",
            )
        )
        items.append(
            PacketItem(
                machine_id=trigger.machine_id,
                source_type="live_sensor",
                status="missing",
                missing_reason="trigger_names_no_single_sensor",
            )
        )
    else:
        call, evidence = optional_call(
            state,
            deps,
            "get_sensor_summary",
            {
                "machine_id": trigger.machine_id,
                "sensor": sensor,
                "from_tick": max(0, trigger.tick - WINDOW_TICKS),
                "to_tick": trigger.tick,
            },
            f"{sensor} on {trigger.machine_id} in the window up to the trigger",
            limit,
        )
        if evidence is not None:
            item = summary_item(
                trigger.machine_id,
                sensor,
                json.loads(evidence.content),
                evidence,
                trigger.tick,
            )
            call = call.model_copy(update={"qualified": item.status == "qualified"})
        else:
            item = PacketItem(
                machine_id=trigger.machine_id,
                sensor=sensor,
                physical_root=f"{trigger.machine_id}:{sensor}",
                source_type="live_sensor",
                status="missing",
                missing_reason=call.reason,
            )
        calls.append(call)
        items.append(item)

    roster: tuple[str, ...] = ()
    status: dict[str, str] = {}
    call, evidence = optional_call(
        state,
        deps,
        "list_machines",
        {},
        "the expected machines on the line and each one's status",
        limit,
    )
    if evidence is not None:
        rows = json.loads(evidence.content)
        if (
            isinstance(rows, list)
            and rows
            and all(
                isinstance(r, dict) and isinstance(r.get("machine_id"), str)
                for r in rows
            )
        ):
            roster = tuple(r["machine_id"] for r in rows)
            status = {
                r["machine_id"]: r["status"]
                for r in rows
                if isinstance(r.get("status"), str)
            }
            call = call.model_copy(update={"qualified": True})
        else:
            call = call.model_copy(update={"reason": "malformed_roster"})
    calls.append(call)

    screened = tuple(machines) if machines is not None else ()
    absent: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    if roster and machines is not None:
        absent = tuple(m for m in roster if m not in machines)
        unexpected = tuple(m for m in screened if m not in roster)
        items += [
            PacketItem(
                machine_id=machine_id,
                source_type="derived_screening",
                status="missing",
                missing_reason="absent_from_screening",
            )
            for machine_id in absent
        ]

    covered = {c.evidence_id for c in calls if c.evidence_id}
    for evidence in state.evidence:
        if evidence.id in covered:
            continue
        item = text_item(state, evidence)
        if item is not None:
            items.append(item)

    return EvidencePacket(
        machine_id=trigger.machine_id,
        trigger_tick=trigger.tick,
        observation_tick=observation_tick,
        sensor=sensor,
        roster=roster,
        roster_verified=bool(roster),
        machine_status=status,
        screened_machines=screened,
        absent_from_screening=absent,
        unexpected_in_screening=unexpected,
        screening_reference=reference,
        items=tuple(items),
        calls=tuple(calls),
    )


def ledger_entry_for_mandatory(
    state: InvestigationState, tool: str, evidence: Evidence | None
) -> PacketCall:
    """The ledger entry for a mandatory call `observe` already made."""
    # Variables:
    #   outcome: The record of the call, found by tool name, newest first, so a
    #     later optional call cannot be mistaken for it.
    if evidence is not None:
        return PacketCall(
            tool=tool, role="mandatory", outcome="observed", evidence_id=evidence.id
        )
    outcome = next(
        (d.outcome for d in reversed(state.decisions) if d.tool == tool), None
    )
    if outcome == "repeated_call":
        return PacketCall(
            tool=tool, role="mandatory", outcome="repeated", reason=outcome
        )
    return PacketCall(
        tool=tool, role="mandatory", outcome="failed", reason=outcome or "tool_failed"
    )


def log_packet(
    state: InvestigationState, deps: InvestigationDeps, packet: EvidencePacket
) -> None:
    """Emit opt-in structured events for the packet: identifiers and counts only."""
    # Variables:
    #   logger: The run's opt-in EventLogger; None logs nothing.
    #   run_id, investigation_id: Correlation ids, as text.
    logger = deps.event_logger
    if logger is None:
        return
    run_id, investigation_id = str(state.run_id), str(state.investigation_id)
    for call in packet.calls:
        logger.log_event(
            f"triage_packet_call_{call.outcome}",
            run_id=run_id,
            investigation_id=investigation_id,
            tick=packet.observation_tick,
            tool=call.tool,
            success=call.qualified,
        )
    logger.log_event(
        "triage_packet_built",
        run_id=run_id,
        investigation_id=investigation_id,
        tick=packet.observation_tick,
        counts=packet.counts(),
    )
