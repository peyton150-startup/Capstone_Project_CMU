"""Bounded factual summaries and numeric checks over observable tool results."""

import json
from collections import defaultdict
from math import isclose

from capstone.agent.state import InvestigationState
from capstone.contracts.hypotheses import NumericClaim

MAX_BRIEF_CHARS = 8000


def section(title: str, rows: list[str], limit: int) -> list[str]:
    """Keep room for every kind of evidence rather than letting one section dominate."""
    # Variables:
    #   limit: This section's share of the prompt, including a truncation warning.
    #   kept, used: Whole lines accepted so far and their character cost.
    kept, used = [title], len(title)
    for row in rows:
        if used + len(row) + 1 > limit - 70:
            kept.append("[Section shortened; omitted detail is unknown, not normal.]")
            break
        kept.append(row)
        used += len(row) + 1
    return kept


def observations(state: InvestigationState):
    """Parse observations only; manual and memory cannot become factory facts."""
    # Variables:
    #   origins: Provenance assigned by the loop, never by the policy's beliefs.
    #   calls: The original tool and arguments, including context omitted from rows.
    #   rows: Complete parsed tool data, before prompt shortening.
    origins = {p.evidence_id: p.origin for p in state.provenance}
    calls = {
        eid: (d.tool, d.arguments)
        for d in state.decisions
        for eid in d.evidence_ids
        if d.tool is not None
    }
    for evidence in state.evidence:
        if origins.get(evidence.id) != "observable":
            continue
        try:
            data = json.loads(evidence.content)
        except (ValueError, TypeError):
            continue
        rows = data if isinstance(data, list) else [data]
        tool, arguments = calls.get(
            evidence.id, (evidence.source_id.split(":")[-1], {})
        )
        yield evidence, tool, [r for r in rows if isinstance(r, dict)], arguments


def measurement_groups(rows: list[dict], arguments: dict):
    """Keep measurements separate by machine, sensor and unit; deduplicate exact samples."""
    # Variables:
    #   arguments: Supplies machine/sensor context only when a row omits it.
    #   groups: Unique (tick, value) samples for each machine/sensor/unit combination.
    groups = defaultdict(dict)
    for row in rows:
        value, tick = row.get("value"), row.get("tick")
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(tick, int)
        ):
            key = (
                row.get("machine_id", arguments.get("machine_id")),
                row.get("sensor", arguments.get("sensor")),
                row.get("unit"),
            )
            if key[1] is not None:
                groups[key][(tick, value)] = value
    return groups


def statistics(samples: dict) -> dict:
    """Compute arithmetic in data-tick order, not retrieval order."""
    # Variables:
    #   ordered: Sample identities sorted by data tick; no simulator state is read.
    #   values: Values in that order, used for extrema, average and endpoint delta.
    ordered = sorted(samples)
    values = [samples[key] for key in ordered]
    return {
        "sample_count": len(values),
        "minimum": min(values),
        "maximum": max(values),
        "mean": sum(values) / len(values),
        "delta": values[-1] - values[0],
        "from_tick": ordered[0][0],
        "to_tick": ordered[-1][0],
    }


def verify_numeric_claims(
    state: InvestigationState, claims: tuple[NumericClaim, ...]
) -> tuple[str, ...]:
    """Reject checkably wrong values; unavailable facts stay unverified, not false."""
    # Variables:
    #   results: Observable tool data keyed by evidence ID; excludes manual/memory.
    #   candidates: Matching signals/windows; ambiguity cannot establish a false claim.
    #   selected: Actual measurements inside the claim's stated data window.
    #   unverified: Claims lacking enough data or units; these are not causal verdicts.
    results = {e.id: (rows, args) for e, _, rows, args in observations(state)}
    known = {e.id for e in state.evidence}
    unverified = []
    for claim in claims:
        if claim.evidence_id not in known:
            raise ValueError("numeric claim cites evidence that was not gathered")
        rows, arguments = results.get(claim.evidence_id, ([], {}))
        candidates = []
        for (machine, sensor, unit), samples in measurement_groups(
            rows, arguments
        ).items():
            if machine != claim.machine_id or sensor != claim.sensor:
                continue
            selected = {
                key: value
                for key, value in samples.items()
                if (claim.from_tick is None or key[0] >= claim.from_tick)
                and (claim.to_tick is None or key[0] <= claim.to_tick)
            }
            if selected:
                candidates.append((unit, statistics(selected)))
        for row in rows:
            if (
                row.get("machine_id") == claim.machine_id
                and row.get("sensor") == claim.sensor
            ):
                if (
                    claim.from_tick in (None, row.get("from_tick"))
                    and claim.to_tick in (None, row.get("to_tick"))
                    and isinstance(row.get(claim.metric), (int, float))
                ):
                    candidates.append((row.get("unit"), row))
        if len(candidates) != 1:
            unverified.append(f"{claim.evidence_id}: unverified")
            continue
        unit, values = candidates[0]
        if claim.metric != "sample_count" and (unit is None or claim.unit is None):
            unverified.append(f"{claim.evidence_id}: unverified")
            continue
        if claim.unit != unit and claim.metric != "sample_count":
            raise ValueError("numeric claim unit disagrees with observed unit")
        if not isclose(claim.value, values[claim.metric], rel_tol=1e-6, abs_tol=0.001):
            raise ValueError("numeric claim disagrees with observed arithmetic")
    return tuple(unverified)


def evidence_brief(state: InvestigationState) -> str:
    """Show coverage, time windows and observed routes; never infer a root cause."""
    # Variables:
    #   machines, sensors: Observed operating states and signals seen, never health labels.
    #   facts: Arithmetic/settings with original IDs and retrieval/data times.
    #   events, inspections: Observed job visits and pass/fail records; gaps stay unknown.
    #   seen, duplicates: Exact measurement identities already included in another view.
    #   coverage, routes: Bounded display rows, not assertions of complete factory coverage.
    machines, sensors, facts, events, inspections = {}, defaultdict(set), [], [], []
    seen, duplicates = set(), 0
    for evidence, tool, rows, arguments in observations(state):
        for row in rows:
            machine = row.get("machine_id", arguments.get("machine_id"))
            if tool == "list_machines" and machine:
                machines[machine] = (row.get("status", "unknown"), evidence.id)
            if row.get("sensor") and machine:
                sensors[machine].add(str(row["sensor"]))
            if (
                row.get("job_id") is not None
                and row.get("kind")
                and row.get("tick") is not None
            ):
                events.append(
                    (row["job_id"], row["tick"], str(machine), row["kind"], evidence.id)
                )
            if row.get("result") in ("passed", "failed"):
                inspections.append(
                    f"job {row.get('job_id')} batch {row.get('batch_id')} "
                    f"{row['result']} at tick {row.get('tick')} [{evidence.id}]"
                )
            if "sample_count" in row and "sensor" in row:
                fields = {
                    key: row[key]
                    for key in (
                        "machine_id",
                        "sensor",
                        "from_tick",
                        "to_tick",
                        "sample_count",
                        "unit",
                        "first_tick",
                        "last_tick",
                        "start_value",
                        "end_value",
                        "minimum",
                        "maximum",
                        "mean",
                        "delta",
                        "rate_of_change",
                    )
                    if key in row
                }
                facts.append(
                    f"[{evidence.id}] retrieved tick {evidence.observed_tick}: "
                    + json.dumps(fields, sort_keys=True)
                )
            if "speed_rpm" in row and machine:
                facts.append(
                    f"[{evidence.id}] {machine} speed setting={row['speed_rpm']} rpm; retrieved tick {evidence.observed_tick}; no standard speed inferred"
                )
            if tool == "get_sensor_trend" and "count" in row:
                facts.append(
                    f"[{evidence.id}] {machine} {arguments.get('sensor', 'sensor unknown')} "
                    f"ticks {row.get('from_tick')}..{row.get('to_tick')}: "
                    f"min={row.get('min')}; max={row.get('max')}; mean={row.get('mean')}; "
                    f"sample_count={row['count']}; unit not supplied"
                )
        for key, samples in measurement_groups(rows, arguments).items():
            machine, sensor, unit = key
            if machine:
                sensors[machine].add(str(sensor))
            stats = statistics(samples)
            facts.append(
                f"[{evidence.id}] {machine} {sensor}: ticks {stats['from_tick']}..{stats['to_tick']}; "
                f"sample_count={stats['sample_count']}; min={stats['minimum']:g}; "
                f"max={stats['maximum']:g}; mean={stats['mean']:g}; delta={stats['delta']:g} "
                f"{unit}; retrieved tick {evidence.observed_tick}"
            )
            for tick, value in samples:
                identity = (*key, tick, value)
                duplicates += identity in seen
                seen.add(identity)
    coverage = []
    for machine in sorted(machines.keys() | sensors.keys()):
        status, eid = machines.get(machine, ("operating state unknown", "unknown"))
        checked = (
            ", ".join(sorted(sensors[machine]))
            if sensors[machine]
            else "sensors not checked"
        )
        coverage.append(f"- {machine}: {status}; {checked} [{eid}]")
    routes = [
        f"job {job}: tick {tick} {machine} {kind} [{eid}]"
        for job, tick, machine, kind, eid in sorted(set(events))
    ]
    lines = ["FACTUAL BRIEF (observations only; unknown is not normal):"]
    lines += section("MACHINE COVERAGE:", coverage, 1800)
    lines += section(
        "JOB ROUTES (observed events only; missing visits remain unknown):",
        routes,
        1600,
    )
    lines += section("INSPECTIONS:", list(dict.fromkeys(inspections)), 1100)
    lines += section(
        "MEASUREMENTS (data ticks differ from retrieval tick):", facts, 2800
    )
    lines += [
        f"{duplicates} repeated measurement(s); overlapping views are not independent support.",
        "Missing sensors, time windows and inspections are untested, not normal.",
    ]
    text = "\n".join(lines)
    if len(text) > MAX_BRIEF_CHARS:
        return (
            text[: MAX_BRIEF_CHARS - 80]
            + "\n[Brief shortened; missing detail remains unknown. Request a narrower window.]"
        )
    return text
