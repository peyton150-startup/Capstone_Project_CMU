"""Read-only, model-free Decide controller for opt-in fixed-plan triage.

This controller collects observations; it never asserts that the diagnosis is
correct. Hypothesize and Conclude retain their existing model-backed roles.
"""

import json
import re
from hashlib import sha256
from math import isfinite
from typing import TYPE_CHECKING

from capstone.agent.artifacts import TerminationReason
from capstone.agent.evidence_tests import RANK, judge
from capstone.agent.investigate_compiler import known_machines, targets
from capstone.agent.policy import CallTool
from capstone.agent.state import InvestigationState
from capstone.agent.triage_decide_contracts import (
    TriageReadDecision,
    TriageStopDecision,
    TriageStopReason,
)
from capstone.agent.triage_evidence_validation import (
    EvidenceQualification,
    validate_triage_result,
)
from capstone.agent.triage_plan import fixed_requirements
from capstone.agent.triage_requirements import (
    ReadRequirement,
    RequirementResult,
    TriageDecisionRecord,
)
from capstone.agent.triage_trace import emit_triage_event, requirement_reason_code
from capstone.contracts.tools import ToolRequest, ToolResult
from capstone.providers.factory import TOOL_ARGUMENTS

if TYPE_CHECKING:
    from capstone.agent.loop import InvestigationDeps

# The deterministic read-ordering policy's version. It is written into a
# selected read's reason and into saved traces, so a change to the weights is
# a new version, never a silent reordering of an old run.
READ_RANKING_POLICY = "read-ranking-v1"

READ_ONLY = frozenset(
    {
        "get_sensor_summary",
        "get_events",
        "get_maintenance_history",
        "get_settings",
        "get_inspections",
        "get_job_history",
    }
)
# Reads that measure a machine's signal, rather than query its records.
SENSOR_READS = frozenset({"get_sensor_summary", "get_readings", "get_sensor_trend"})
STOP_MAP = {
    "requirements_complete": TerminationReason.EVIDENCE_SUFFICIENT,
    "no_eligible_read": TerminationReason.NO_USEFUL_ACTION,
    "capability_unavailable": TerminationReason.NO_USEFUL_ACTION,
    "data_insufficient": TerminationReason.NO_USEFUL_ACTION,
    "retries_exhausted": TerminationReason.NO_USEFUL_ACTION,
    "max_tool_calls": TerminationReason.MAX_TOOL_CALLS,
    "max_iterations": TerminationReason.MAX_ITERATIONS,
    "timeout": TerminationReason.TIMEOUT,
}


def request_for(requirement: ReadRequirement) -> ToolRequest:
    """Build a canonical request from the stable requirement definition."""
    # Variables:
    #   arguments: Only the fields accepted by this read's argument model.
    arguments = {
        key: value
        for key, value in {
            "machine_id": requirement.machine_id
            if requirement.tool != "get_inspections"
            else None,
            "sensor": requirement.sensor,
            "job_id": requirement.job_id,
            "from_tick": requirement.from_tick,
            "to_tick": requirement.to_tick,
        }.items()
        if value is not None
    }
    return ToolRequest(name=requirement.tool, arguments=arguments)


def fingerprint(request: ToolRequest, cutoff_tick: int) -> str:
    """Identify an identical read at one authorized observation horizon."""
    # Variables:
    #   cutoff_tick: Fixed when triage begins; late replies cannot change it.
    return json.dumps([request.name, request.arguments, cutoff_tick], sort_keys=True)


def unpermitted_reason(
    requirement: ReadRequirement, deps: "InvestigationDeps", state: InvestigationState
) -> str | None:
    """Why this read is not authorized now, as a safe code, or None when it is."""
    # Variables:
    #   cutoff: The source horizon captured before any controller reads.
    #   names: Authorized read-only operations for this particular provider.
    cutoff = state.triage_observation_cutoff_tick
    names = {spec.name for spec in deps.triage_tool_specs}
    if requirement.tool not in READ_ONLY or requirement.tool not in names:
        return "unsupported_tool"
    if cutoff is None:
        return "observation_cutoff_unknown"
    if requirement.to_tick is not None and requirement.to_tick > cutoff:
        return "window_past_cutoff"
    if (
        requirement.machine_id is not None
        and requirement.machine_id not in known_machines(state)
    ):
        return "unknown_machine"
    if (
        requirement.sensor is not None
        and requirement.sensor
        not in deps.triage_channels.get(requirement.machine_id or "factory", ())
    ):
        return "channel_unavailable"
    try:
        TOOL_ARGUMENTS[requirement.tool].model_validate(
            request_for(requirement).arguments
        )
    except (KeyError, ValueError):
        return "invalid_arguments"
    return None


def permitted_triage_read(
    requirement: ReadRequirement, deps: "InvestigationDeps", state: InvestigationState
) -> bool:
    """Check catalog, channel, argument and cutoff before a provider call."""
    # Variables:
    #   requirement: The planned read; its tool, machine, sensor and window are
    #     each checked against this provider's catalog, channels and cutoff.
    return unpermitted_reason(requirement, deps, state) is None


def initialize_requirements(state: InvestigationState) -> None:
    """Freeze the source cutoff and add the fixed plan's collection contracts."""
    # Variables:
    #   packet_tick: Observe's recorded horizon when the packet is available.
    if state.triage_observation_cutoff_tick is None:
        packet_tick = (
            state.triage_packet.observation_tick
            if state.triage_packet is not None
            else None
        )
        state.triage_observation_cutoff_tick = (
            packet_tick
            if packet_tick is not None
            else state.last_tick
            if state.last_tick is not None
            else state.anomaly.tick
        )
    if state.fixed_plan_used and not state.triage_requirements:
        state.triage_requirements.update(
            fixed_requirements(state.anomaly, state.triage_observation_cutoff_tick)
        )


def add_test_requirements(state: InvestigationState) -> None:
    """Compile model-written Test questions into stable read requirements."""
    # Variables:
    #   candidate: A compiler-ranked read; its window is clamped to the fixed
    #     cutoff rather than the mutable last result tick.
    planned_questions = {r.question_id for r in state.triage_requirements.values()}
    cutoff = state.triage_observation_cutoff_tick
    if cutoff is None:
        return
    for question in state.unanswered_questions:
        if question.id in planned_questions:
            continue
        for target in targets(state, question, known_machines(state)):
            rid = f"{question.id}:{target.tool}:{target.machine_id}:{target.sensor}"
            if rid in state.triage_requirements:
                continue
            state.triage_requirements[rid] = ReadRequirement(
                requirement_id=rid,
                question_id=question.id,
                tool=target.tool,
                machine_id=target.machine_id,
                sensor=target.sensor,
                from_tick=target.from_tick,
                to_tick=min(target.to_tick, cutoff)
                if target.to_tick is not None
                else None,
                min_samples=2 if target.sensor else 0,
                min_span_ticks=1 if target.sensor else 0,
                qualification="measurement" if target.sensor else "record",
            )


def matching_evidence(
    state: InvestigationState, requirement: ReadRequirement
) -> list[tuple[str, object]]:
    """Find observable results of this source, including earlier Observe reads."""
    # Variables:
    #   decision: The request associated with a saved evidence item.
    #   cutoff: A response after the fixed horizon cannot qualify this run.
    #   covering: Whether only reads whose window covers the requirement's own
    #     window count: true for the reads that compare jobs over a lookback,
    #     where a shorter read of the same tool would miss jobs.
    cutoff = state.triage_observation_cutoff_tick
    covering = requirement.from_tick is not None and (
        requirement.qualification == "cycle_time_shift"
        or bool(requirement.failed_job_ids)
    )
    observed = {p.evidence_id for p in state.provenance if p.origin == "observable"}
    found: list[tuple[str, object]] = []
    for evidence in state.evidence:
        if (
            evidence.id not in observed
            or cutoff is None
            or evidence.observed_tick > cutoff
        ):
            continue
        decision = next(
            (d for d in state.decisions if evidence.id in d.evidence_ids), None
        )
        if decision is None or decision.tool != requirement.tool:
            continue
        args = decision.arguments
        if (
            requirement.machine_id is not None
            and requirement.tool != "get_inspections"
            and args.get("machine_id") != requirement.machine_id
        ):
            continue
        if requirement.sensor is not None and args.get("sensor") != requirement.sensor:
            continue
        if requirement.job_id is not None and args.get("job_id") != requirement.job_id:
            continue
        if covering and not (
            type(args.get("from_tick")) is int
            and type(args.get("to_tick")) is int
            and args["from_tick"] <= requirement.from_tick
            and args["to_tick"] >= requirement.to_tick
        ):
            continue
        try:
            data = json.loads(evidence.content)
            # Observe evidence predates the deterministic admission hook.
            # Requalify it before allowing it to satisfy a requirement.
            source = evidence.source_id.rsplit(":", 1)[0]
            replayed = ToolResult(
                success=True,
                tool=decision.tool,
                source=source,
                tick=evidence.observed_tick,
                timestamp=evidence.observed_at,
                data=data,
            )
            request = ToolRequest(name=decision.tool, arguments=dict(args))
            if not validate_triage_result(
                replayed,
                request,
                cutoff,
                allowed_sources=state.triage_allowed_sources,
            ).accepted:
                continue
            found.append((evidence.id, data))
        except (ValueError, TypeError, KeyError):
            continue
    return found


# A station's job time must move by at least this fraction at one point to be
# reported as a shift, with at least this many finished jobs either side.
# Chosen defaults: a wrong setting in the simulator moves job times by roughly
# 10-25% at once, while a station's own jobs vary by a few percent.
SHIFT_FRACTION = 0.10
SHIFT_MIN_JOBS = 2
JOB_EVENT = re.compile(r"^job (?P<job>\d+) (?P<stage>started|finished)$")


def job_durations(rows: list) -> dict[str, list[tuple[int, int]]]:
    """Each station's finished jobs as (start tick, ticks worked), in start order.

    Built from job "started" and "finished" events. A job still running at
    the read's end, or started before its window, has no pair and is left out.
    """
    # Variables:
    #   started: The tick each (station, job) started, waiting for its finish.
    #   durations: Each station's finished jobs, the result.
    started: dict[tuple[str, int], int] = {}
    durations: dict[str, list[tuple[int, int]]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") != "job":
            continue
        machine, tick = row.get("machine_id"), row.get("tick")
        found = JOB_EVENT.match(str(row.get("message", "")))
        if found is None or not isinstance(machine, str) or type(tick) is not int:
            continue
        key = (machine, int(found["job"]))
        if found["stage"] == "started":
            started[key] = tick
        elif key in started:
            begin = started.pop(key)
            durations.setdefault(machine, []).append((begin, tick - begin))
    for jobs in durations.values():
        jobs.sort()
    return durations


def largest_shift(jobs: list[tuple[int, int]]) -> tuple[float, int, float, float]:
    """The one split of a station's job times where their mean moves the most.

    Returns (relative change, tick of the first job after the split, mean
    before, mean after). A step change, as a changed setting makes, gives one
    large split; steady wear spreads its change over every split.
    """
    # Variables:
    #   times: The ticks worked per job, in start order.
    #   best: The largest relative change found so far, with its split.
    times = [worked for _, worked in jobs]
    best = (0.0, jobs[0][0], 0.0, 0.0)
    for split in range(SHIFT_MIN_JOBS, len(times) - SHIFT_MIN_JOBS + 1):
        before = sum(times[:split]) / split
        after = sum(times[split:]) / (len(times) - split)
        if before <= 0:
            continue
        change = (after - before) / before
        if abs(change) > abs(best[0]):
            best = (change, jobs[split][0], before, after)
    return best


def cycle_time_result(rows: list, ids: tuple[str, ...]) -> RequirementResult:
    """Whether any station's job times shifted at one point (manual §2.7).

    The settings record shows only current speeds, and each station's normal
    speed is on its own setup sheet, so a changed setting is found from its
    effect: one station's job times move at one point and stay there. This
    reports which stations moved and by how much; it is evidence, not a
    diagnosis (a worn bearing also lengthens jobs, gradually).
    """
    # Variables:
    #   durations: Each station's finished jobs over the read's window.
    #   comparable: Stations with enough jobs either side of some split.
    #   shifted: Stations whose largest one-point change reaches SHIFT_FRACTION.
    durations = job_durations(rows)
    comparable = {
        machine: largest_shift(jobs)
        for machine, jobs in sorted(durations.items())
        if len(jobs) >= 2 * SHIFT_MIN_JOBS
    }
    if not comparable:
        return RequirementResult(
            status="insufficient",
            evidence_ids=ids,
            reason="too few finished jobs to compare job times",
        )
    shifted = [
        f"{machine} {before:.1f} to {after:.1f} ticks per job "
        f"({change:+.0%}) around tick {tick}, {len(durations[machine])} jobs"
        for machine, (change, tick, before, after) in comparable.items()
        if abs(change) >= SHIFT_FRACTION
    ]
    return RequirementResult(
        status="satisfied",
        evidence_ids=ids,
        reason=(
            "largest change in mean job time at one point: " + "; ".join(shifted)
            if shifted
            else f"no station's mean job time changed by {SHIFT_FRACTION:.0%} or "
            f"more at any one point ({', '.join(comparable)} compared)"
        ),
    )


def job_time_baseline_result(
    baseline: list, failed: dict[int, list], ids: tuple[str, ...]
) -> RequirementResult:
    """Each station's time on the failed jobs against its time on the first job.

    A changed setting makes one station work every later job at a different
    pace; a bad batch fails parts without changing any station's pace. The
    first job is the reference because it ran before most changes could have
    been made; a change made before it reached a station leaves no difference.
    """
    # Variables:
    #   reference: Each station's ticks worked on the first job.
    #   paced: Each failed job's ticks worked per station.
    #   changed: Stations where every failed job differs from the first job by
    #     SHIFT_FRACTION or more, in the same direction.
    reference = {
        machine: jobs[0][1]
        for machine, jobs in job_durations(baseline).items()
        if jobs and jobs[0][1] > 0
    }
    paced = {
        job: {machine: jobs[0][1] for machine, jobs in job_durations(rows).items()}
        for job, rows in sorted(failed.items())
    }
    paced = {job: times for job, times in paced.items() if times}
    if not reference or len(paced) < 2:
        return RequirementResult(
            status="insufficient",
            evidence_ids=ids,
            reason="too few finished jobs to compare job times",
        )
    changed = []
    for machine, base in sorted(reference.items()):
        times = [times[machine] for times in paced.values() if machine in times]
        if len(times) < 2:
            continue
        changes = [(t - base) / base for t in times]
        if all(c >= SHIFT_FRACTION for c in changes) or all(
            c <= -SHIFT_FRACTION for c in changes
        ):
            mean = sum(changes) / len(changes)
            changed.append(
                f"{machine} {base} ticks on the first job, "
                f"{', '.join(str(t) for t in times)} on failed jobs "
                f"{', '.join(str(j) for j in paced)} ({mean:+.0%})"
            )
    return RequirementResult(
        status="satisfied",
        evidence_ids=ids,
        reason=(
            "a station worked every failed job at a different pace than the first "
            "job: " + "; ".join(changed)
            if changed
            else "no station worked every failed job at a pace "
            f"{SHIFT_FRACTION:.0%} or more different from the first job "
            f"({', '.join(sorted(reference))} compared)"
        ),
    )


def batch_failure_rates(matches: list[tuple[str, object]]) -> str:
    """Each batch's failed and inspected job counts, as a reason suffix.

    A bad batch fails often while other batches pass; a shared batch with a
    similar rate elsewhere, or with no other batch inspected, separates little.
    """
    # Variables:
    #   results: Each inspected job's batch and whether it failed, once per job.
    results: dict[int, tuple[object, bool]] = {}
    for _, data in matches:
        if not isinstance(data, list):
            continue
        for row in data:
            if (
                isinstance(row, dict)
                and type(row.get("job_id")) is int
                and type(row.get("batch_id")) in (int, str)
                and row.get("result") in ("passed", "failed")
            ):
                results[row["job_id"]] = (row["batch_id"], row["result"] == "failed")
    if not results:
        return ""
    counts: dict[object, list[int]] = {}
    for batch, failed in results.values():
        tally = counts.setdefault(batch, [0, 0])
        tally[0] += int(failed)
        tally[1] += 1
    parts = [
        f"batch {batch}: {failed} of {seen} failed"
        for batch, (failed, seen) in sorted(counts.items(), key=lambda b: str(b[0]))
    ]
    note = "" if len(counts) > 1 else "; no other batch inspected in the read"
    return " (inspected jobs: " + "; ".join(parts) + note + ")"


def qualify(
    state: InvestigationState, requirement: ReadRequirement
) -> RequirementResult:
    """Judge matching observations without treating a tool success as completion."""
    # Variables:
    #   matches: Observable evidence from the requested source at the cutoff.
    #   data: Parsed tool answer; shape and finite values must be checked.
    #   first, last: Actual first and last observed sample ticks around the alarm.
    #   best: Strongest predicate verdict based on sufficiently spread samples.
    #   failed: For the job-1 baseline, each failed job's history rows, read by
    #     the job-path requirements the inspection read added.
    #   named: The failed jobs the anomaly named; when set, only they are
    #     compared, and every one must be in the read.
    #   rates: Each batch's failed and inspected counts, added to a batch
    #     reason so a shared batch is weighed against the other batches.
    matches = matching_evidence(state, requirement)
    if not matches:
        return RequirementResult()
    ids = tuple(eid for eid, _ in matches)
    if requirement.qualification == "setting_change":
        return RequirementResult(
            status="insufficient",
            evidence_ids=ids,
            reason="current settings snapshot does not establish a historical change",
        )
    if requirement.qualification == "job_time_baseline":
        failed = {
            other.job_id: [
                row
                for _, data in matching_evidence(state, other)
                if isinstance(data, list)
                for row in data
            ]
            for other in state.triage_requirements.values()
            if other.qualification == "job_path"
            and other.job_id is not None
            and other.job_id != requirement.job_id
        }
        return job_time_baseline_result(
            [row for _, data in matches if isinstance(data, list) for row in data],
            failed,
            ids,
        )
    if requirement.qualification == "cycle_time_shift":
        return cycle_time_result(
            [row for _, data in matches if isinstance(data, list) for row in data],
            ids,
        )
    if requirement.qualification == "record":
        # Empty history is a valid read, not proof of historical coverage.
        if any(isinstance(data, list) and not data for _, data in matches):
            return RequirementResult(
                status="insufficient",
                evidence_ids=ids,
                reason="empty record response cannot establish complete history",
            )
        if any(isinstance(data, (list, dict)) for _, data in matches):
            return RequirementResult(
                status="satisfied", evidence_ids=ids, reason="record source checked"
            )
        return RequirementResult(
            status="insufficient",
            evidence_ids=ids,
            reason="record answer has no usable structure",
        )
    if requirement.qualification in {"inspection_batch", "inspection_jobs"}:
        # A valid observation must account for every observed failed row;
        # missing job/batch identifiers cannot silently disappear from a
        # comparison just because two other rows happen to be complete.
        # When the anomaly named its failed jobs, compare exactly those: an
        # older, unrelated failure in the lookback must not join the set, and
        # a named job the read missed leaves the comparison incomplete.
        named = set(requirement.failed_job_ids)
        failures = [
            row
            for _, data in matches
            if isinstance(data, list)
            for row in data
            if isinstance(row, dict)
            and row.get("result") == "failed"
            and (not named or row.get("job_id") in named)
        ]
        identified = [
            row
            for row in failures
            if type(row.get("job_id")) is int
            and row["job_id"] > 0
            and type(row.get("tick")) is int
            and row["tick"] >= 0
        ]
        jobs = {row["job_id"] for row in identified}
        comparable = (
            len(jobs) >= 2
            and len(identified) == len(failures)
            and len(failures) >= 2
            and named <= jobs
        )
        if requirement.qualification == "inspection_jobs":
            return RequirementResult(
                status="satisfied" if comparable else "insufficient",
                evidence_ids=ids,
                reason="all failed jobs have dated identifiers for path checks"
                if comparable
                else "failed jobs are missing dated identifiers or a second job",
            )
        batches = [
            row.get("batch_id")
            for row in identified
            if type(row.get("batch_id")) in (int, str) and row["batch_id"] != ""
        ]
        complete = comparable and len(batches) == len(identified)
        distinct = set(batches)
        # Sharing a batch alone says little when batches are large: every
        # failed job of a wrong-setting case shares one too. So each batch's
        # failure rate over every inspected job in the read goes with it.
        rates = batch_failure_rates(matches) if named else ""
        return RequirementResult(
            status="satisfied" if complete else "insufficient",
            evidence_ids=ids,
            reason=(
                "all observed failed jobs share batch "
                + str(next(iter(distinct)))
                + rates
                if len(distinct) == 1
                else "observed failed jobs have different batch identifiers" + rates
            )
            if complete
            else "failed jobs lack comparable batch identifiers",
        )
    if requirement.qualification == "job_path":
        rows = [
            row
            for _, data in matches
            if isinstance(data, list)
            for row in data
            if isinstance(row, dict)
            and row.get("job_id") == requirement.job_id
            and isinstance(row.get("machine_id"), str)
            and bool(row["machine_id"])
            and type(row.get("tick")) is int
            and row["tick"] >= 0
        ]
        return RequirementResult(
            status="satisfied" if rows else "insufficient",
            evidence_ids=ids,
            reason="dated machine history matches the requested job"
            if rows
            else "job history does not identify the requested job's machine path",
        )
    if requirement.qualification == "inspection_machine":
        rows = [
            row
            for _, data in matches
            if isinstance(data, list)
            for row in data
            if isinstance(row, dict)
            and row.get("machine_id") == requirement.machine_id
            and type(row.get("tick")) is int
        ]
        return RequirementResult(
            status="satisfied" if rows else "insufficient",
            evidence_ids=ids,
            reason="inspections linked to machine and time"
            if rows
            else "inspections do not link affected machine and time",
        )
    if requirement.qualification == "inspection_recent":
        rows = [
            row
            for _, data in matches
            if isinstance(data, list)
            for row in data
            if isinstance(row, dict)
            and type(row.get("tick")) is int
            and row.get("result") is not None
        ]
        return RequirementResult(
            status="satisfied" if rows else "insufficient",
            evidence_ids=ids,
            reason="recent inspection results checked"
            if rows
            else "no dated inspection results",
        )
    predicate = state.question_predicates.get(requirement.question_id)
    if predicate is not None and requirement.requirement_id.endswith(":trigger"):
        best = None
        for eid, data in matches:
            # Requested windows and sample counts do not prove the measured
            # samples actually span the triggering alarm.
            if not isinstance(data, dict):
                continue
            first, last = data.get("first_tick"), data.get("last_tick")
            if (
                type(first) is not int
                or type(last) is not int
                or first > state.anomaly.tick
                or last < state.anomaly.tick
                or last - first < requirement.min_span_ticks
                or first < predicate.from_tick
                or last > predicate.to_tick
            ):
                continue
            evidence = next(e for e in state.evidence if e.id == eid)
            result = judge(predicate, evidence, data)
            if result.verdict in ("true", "false"):
                return RequirementResult(
                    status="satisfied",
                    evidence_ids=(eid,),
                    valid_samples=result.sample_count or 0,
                    reason=result.reason,
                )
            if best is None or RANK[result.verdict] >= RANK[best.verdict]:
                best = result
        return RequirementResult(
            status=best.verdict if best is not None else "insufficient",
            evidence_ids=ids,
            valid_samples=(best.sample_count or 0) if best is not None else 0,
            reason=best.reason
            if best is not None
            else "observed samples do not span the alarm and minimum sustain interval",
        )
    for eid, data in matches:
        if not isinstance(data, dict):
            continue
        count = data.get("sample_count")
        first, last = data.get("first_tick"), data.get("last_tick")
        mean = data.get("mean")
        delta = data.get("delta")
        if (
            type(count) is int
            and count >= requirement.min_samples
            and type(first) is int
            and type(last) is int
            and last - first >= requirement.min_span_ticks
            and first >= (requirement.from_tick or 0)
            and last <= (requirement.to_tick or last)
            and type(mean) in (int, float)
            and isfinite(mean)
            and (
                requirement.qualification != "movement"
                or (type(delta) in (int, float) and isfinite(delta))
            )
        ):
            return RequirementResult(
                status="satisfied",
                evidence_ids=(eid,),
                valid_samples=count,
                reason="qualified measurement covers the required interval",
            )
    return RequirementResult(
        status="insufficient",
        evidence_ids=ids,
        reason="measurement lacks qualified samples or span",
    )


def expand_job_requirements(state: InvestigationState) -> None:
    """Require the path of every failed job found in an inspection read."""
    # Variables:
    #   parent: The inspection requirement whose question needs job paths.
    #   job_ids: Every dated failed job in the observed inspection window, or
    #     only the ones the anomaly named when it named them.
    parents = [
        requirement
        for requirement in state.triage_requirements.values()
        if requirement.qualification == "inspection_jobs"
    ]
    for parent in parents:
        job_ids = {
            row["job_id"]
            for _, data in matching_evidence(state, parent)
            if isinstance(data, list)
            for row in data
            if isinstance(row, dict)
            and row.get("result") == "failed"
            and type(row.get("job_id")) is int
            and row["job_id"] > 0
            and type(row.get("tick")) is int
            and (not parent.failed_job_ids or row["job_id"] in parent.failed_job_ids)
        }
        for job_id in sorted(job_ids):
            rid = f"{parent.question_id}:job:{job_id}"
            if rid not in state.triage_requirements:
                state.triage_requirements[rid] = ReadRequirement(
                    requirement_id=rid,
                    question_id=parent.question_id,
                    tool="get_job_history",
                    job_id=job_id,
                    qualification="job_path",
                )


def reconcile_question_comparison(
    state: InvestigationState, question_id: str, ids: list[str]
) -> None:
    """Check cross-source comparisons before closing a multi-part question."""
    # Variables:
    #   paths: Independently qualified histories for the failed jobs.
    #   common: Machine ids present in the history of every failed job.
    #   spans: Actual first/last observation ticks of three sensor summaries.
    #   directions: Signed endpoint movement; not a correlation estimate.
    if question_id == "Q1" and "Q1:failed_jobs" in ids:
        paths = [
            requirement
            for requirement in state.triage_requirements.values()
            if requirement.question_id == question_id
            and requirement.qualification == "job_path"
        ]
        if len(paths) >= 2 and all(
            state.triage_requirement_results[path.requirement_id].status == "satisfied"
            for path in paths
        ):
            machine_sets = []
            for path in paths:
                machines = {
                    row["machine_id"]
                    for _, data in matching_evidence(state, path)
                    if isinstance(data, list)
                    for row in data
                    if isinstance(row, dict)
                    and row.get("job_id") == path.job_id
                    and isinstance(row.get("machine_id"), str)
                    and bool(row["machine_id"])
                    and type(row.get("tick")) is int
                }
                machine_sets.append(machines)
            common = set.intersection(*machine_sets)
            original = state.triage_requirement_results["Q1:failed_jobs"]
            state.triage_requirement_results["Q1:failed_jobs"] = original.model_copy(
                update={
                    "reason": (
                        "all failed jobs visited common machine(s): "
                        + ", ".join(sorted(common))
                        if common
                        else "no machine appears in every failed job history"
                    )
                }
            )

    movement = ("Q5:vibration", "Q5:temperature", "Q5:load")
    if question_id != "Q5" or not set(movement).issubset(ids):
        return
    if not all(
        state.triage_requirement_results[rid].status == "satisfied" for rid in movement
    ):
        return
    by_id = {e.id: e for e in state.evidence}
    summaries = [
        json.loads(by_id[state.triage_requirement_results[rid].evidence_ids[0]].content)
        for rid in movement
    ]
    spans = {(data["first_tick"], data["last_tick"]) for data in summaries}
    counts = {data["sample_count"] for data in summaries}
    directions = [data["delta"] for data in summaries]
    comparable = (
        len(spans) == 1
        and len(counts) == 1
        and all(type(delta) in (int, float) and delta != 0 for delta in directions)
    )
    same_direction = comparable and (
        all(delta > 0 for delta in directions) or all(delta < 0 for delta in directions)
    )
    if comparable:
        reason = (
            "three aligned summaries have matching endpoint directions; "
            "this is not a time-series correlation or causal finding"
            if same_direction
            else "aligned summary endpoint directions differ; "
            "this does not establish causal independence"
        )
    else:
        reason = (
            "summaries lack matching observation endpoints, equal sample counts, "
            "or nonzero changes; movement cannot be compared"
        )
    for rid in movement:
        result = state.triage_requirement_results[rid]
        state.triage_requirement_results[rid] = result.model_copy(
            update={
                "status": "satisfied" if comparable else "partial",
                "reason": reason,
            }
        )


def reconciled_result(
    previous: RequirementResult | None,
    fresh: RequirementResult,
    *,
    capability: str | None = None,
    checked: bool = False,
) -> RequirementResult:
    """One authoritative status: qualified evidence first, then capability.

    A requirement the provider cannot serve must not read as "pending", but a
    remembered verdict can go stale: the catalog, channels or cutoff may
    change between cycles. So when authorization can be checked (`checked`),
    the capability verdict is recomputed from it, not carried over. Evidence
    that already qualified is never invalidated by a later capability change.
    """
    # Variables:
    #   previous: The result recorded before this evaluation, if any.
    #   fresh: What the current evidence qualifies to, recomputed from scratch.
    #   capability: The current blocking reason code, or None if the read is
    #     authorized now; ignored unless `checked`.
    #   checked: Whether this cycle could evaluate authorization at all. When
    #     it could not (no deps), a recorded capability verdict is kept.
    if fresh.status == "satisfied":
        # Qualified evidence wins: a capability change is not retroactive.
        return fresh
    if not checked:
        if (
            previous is not None
            and previous.status in ("unavailable", "unsupported")
            and not fresh.evidence_ids
        ):
            return previous
        return fresh
    if capability is None:
        return fresh
    status = (
        "unsupported"
        if capability in ("unsupported_tool", "invalid_arguments")
        else "unavailable"
    )
    detail = f"read not authorized: {capability}"
    if fresh.evidence_ids:
        # Keep both facts: what was collected, and why more cannot be.
        detail += f"; collected evidence is {fresh.status}: {fresh.reason}"
    return RequirementResult(
        status=status,
        evidence_ids=fresh.evidence_ids,
        valid_samples=fresh.valid_samples,
        reason=detail,
    )


def missing_cutoff_stop(state: InvestigationState) -> TriageStopDecision:
    """The typed fail-closed stop when the source horizon is unexpectedly unset."""
    # Variables:
    #   state.triage_requirements: Every requirement is left unresolved, since
    #     no read can be authorized without a cutoff.
    return TriageStopDecision(
        reason="data_insufficient",
        unresolved_requirement_ids=tuple(sorted(state.triage_requirements)),
    )


def unresolved_required(state: InvestigationState) -> tuple[str, ...]:
    """Required requirements whose result is not satisfied, in plan order."""
    # Variables:
    #   result: The last recorded verdict, or the pending default if never read.
    return tuple(
        rid
        for rid, requirement in state.triage_requirements.items()
        if requirement.required
        and state.triage_requirement_results.get(rid, RequirementResult()).status
        != "satisfied"
    )


def evaluate_triage_requirements(
    state: InvestigationState, deps: "InvestigationDeps | None" = None
) -> None:
    """Reconcile all requirements, attach shared evidence, and close only complete questions.

    When `deps` is given (the deterministic controller), each requirement's
    capability status is recomputed from the current catalog, channels and
    cutoff, so it can never go stale.
    """
    # Variables:
    #   by_question: Required parts of each question, evaluated independently.
    #   movement: Q5's three source requirements, not proof of correlation.
    #   all_qualified: Whether each source passes independently.
    #   previous: The recorded results, for the no-deps case only.
    #   capability: Why this read is not authorized now, or None if it is;
    #     only the deterministic controller can check it, hence `deps`.
    expand_job_requirements(state)
    previous = dict(state.triage_requirement_results)
    by_question: dict[str, list[str]] = {}
    for rid, requirement in state.triage_requirements.items():
        capability = (
            unpermitted_reason(requirement, deps, state) if deps is not None else None
        )
        result = reconciled_result(
            previous.get(rid),
            qualify(state, requirement),
            capability=capability,
            checked=deps is not None,
        )
        state.triage_requirement_results[rid] = result
        by_question.setdefault(requirement.question_id, []).append(rid)
    # Anomalies are a diagnostic of the CURRENT state, recomputed each cycle:
    # a resolved inconsistency must disappear, and identical state must give
    # identical entries, so this can never accumulate or block forever.
    found: list[str] = []
    for question_id, ids in by_question.items():
        reconcile_question_comparison(state, question_id, ids)
        evidence_ids = list(
            dict.fromkeys(
                eid
                for rid in ids
                for eid in state.triage_requirement_results[rid].evidence_ids
            )
        )
        state.triage_question_evidence[question_id] = evidence_ids
        movement = {"Q5:vibration", "Q5:temperature", "Q5:load"}
        all_qualified = all(
            state.triage_requirement_results[rid].status == "satisfied" for rid in ids
        )
        if question_id == "Q5" and movement.issubset(ids):
            # Even matching summary endpoints and signed deltas cannot
            # demonstrate that sensors covaried at the same observation times.
            state.triage_question_gaps[question_id] = (
                "aggregate summaries cannot prove time-aligned vibration, "
                "temperature and load co-movement"
                if all_qualified
                else "vibration, temperature and load evidence is incomplete or noncomparable"
            )
            continue
        if all_qualified:
            state.triage_question_gaps.pop(question_id, None)
            state.answers[question_id] = evidence_ids
            state.unanswered_questions = [
                q for q in state.unanswered_questions if q.id != question_id
            ]
        elif question_id in state.answers:
            # `answers` is an evidence map, not a closure record: gather()
            # appends evidence for a question it then holds open (an unsettled
            # predicate). So this is only an inconsistency when the question is
            # no longer open -- answered, yet its requirements unsatisfied.
            # Not reachable otherwise through the current lifecycle: job paths
            # expand inside the same reconciliation, before closure, and
            # identical reads are deduplicated.
            still_open = any(q.id == question_id for q in state.unanswered_questions)
            if not still_open:
                unmet = sorted(
                    rid
                    for rid in ids
                    if state.triage_requirement_results[rid].status != "satisfied"
                )
                found.append(
                    f"{question_id}: answered but {', '.join(unmet)} unsatisfied"
                )
    state.triage_bookkeeping_anomalies = sorted(found)


def read_priority(
    requirement_ids: tuple[str, ...],
    *,
    state: InvestigationState,
    direct: bool,
    order_position: int | None = None,
) -> tuple[int, int, int, int, int, int]:
    """A reproducible sort key for one grouped read; smaller is read first.

    It is an ordinal preference over evidence, never a probability or a
    claim that the read explains anything.
    """
    # Variables:
    #   requirement_ids: Every requirement this one request answers, so a
    #     grouped read is judged by all of them, not just the first.
    #   order_position: The read's place in the candidate-derived Test order,
    #     when there is one; it always wins, since Hypothesize already ranked
    #     those reads against the explanations.
    #   shared: How many requirements the read settles at once.
    #   discriminating: Whether any compiled candidate names any of these
    #     requirements as separating its possibilities. It is 0 during
    #     Investigate, where candidates do not exist yet, so a test there
    #     only measures shared coverage.
    #   direct: Whether the read measures a machine rather than its records.
    #   question_number: The first question's number, so Q1 leads on a tie.
    #   ordered: 0 when an explicit Test order exists, else 1; it is the
    #     first key, so ranking never overrides that order.
    shared = len(requirement_ids)
    named = {
        rid
        for candidate in state.triage_candidates
        for rid in candidate.discriminating_requirement_ids
    }
    discriminating = any(rid in named for rid in requirement_ids)
    suffix = state.triage_requirements[requirement_ids[0]].question_id.removeprefix("Q")
    question_number = int(suffix) if suffix.isdigit() else 99
    return (
        0 if order_position is not None else 1,
        order_position if order_position is not None else 0,
        -shared,
        -int(discriminating),
        -int(direct),
        question_number,
    )


def choose_next_triage_read(
    state: InvestigationState, deps: "InvestigationDeps", phase: str
) -> TriageReadDecision | TriageStopDecision:
    """Select one unmet authorized read, or explain why collection stops."""
    # Variables:
    #   pending: Requirements still missing qualified evidence.
    #   grouped: One request may answer several requirements with one call.
    #   attempts: Count for the exact request at this stable cutoff.
    #   order: Typed candidate-driven Test priority, rebuilt as observed
    #     inspections reveal job-path requirements.
    #   ranked: Grouped requests best first, by `read_priority` and then by
    #     their key, so identical inputs always pick the same read.
    cutoff = state.triage_observation_cutoff_tick
    if cutoff is None:
        # Normally unreachable (the trusted-clock check runs first), but a
        # replay or corrupted state must fail closed with a typed stop, not an
        # assert that `python -O` would strip.
        return missing_cutoff_stop(state)
    pending = [
        r
        for r in state.triage_requirements.values()
        if state.triage_requirement_results[r.requirement_id].status != "satisfied"
    ]
    if deps.triage_hypothesize == "deterministic":
        if phase == "investigate":
            # Collect one source for the event before compiling possibilities.
            # Keep other sources for actual hypothesis-driven Test.
            anchors = [
                r
                for r in pending
                if r.question_id == "Q1" and r.qualification != "job_path"
            ]
            if not anchors:
                anchors = [r for r in pending if r.requirement_id == "Q2:events"]
            pending = anchors
        elif phase == "test":
            # New failed jobs can be discovered during Test, after Hypothesize
            # compiled its initial packet. Refresh from typed requirements,
            # but do not add another stage-level trace for each read.
            from capstone.agent.triage_hypothesize import update_candidate_packet

            update_candidate_packet(state, stage="test", deps=deps, record_trace=False)
            order = {
                rid: position
                for position, rid in enumerate(state.triage_test_requirement_ids)
            }
            pending = [r for r in pending if r.requirement_id in order]
            # Preserve stable candidate priority, not arbitrary lexicographic
            # requirement IDs or an LLM-supplied test order.
            pending.sort(key=lambda r: (order[r.requirement_id], r.requirement_id))
            if not pending:
                unsupported = tuple(
                    sorted(
                        {
                            rid
                            for candidate in state.triage_candidates
                            for rid in candidate.unavailable_requirement_ids
                        }
                    )
                )
                if unsupported:
                    return TriageStopDecision(
                        reason="capability_unavailable",
                        unresolved_requirement_ids=unsupported,
                    )
    if not pending and not state.unanswered_questions:
        # `pending` is phase-filtered: an empty list here proves nothing about
        # the whole ledger. Completion is judged globally.
        outstanding = unresolved_required(state)
        if outstanding:
            return TriageStopDecision(
                reason="data_insufficient", unresolved_requirement_ids=outstanding
            )
        return TriageStopDecision(reason="requirements_complete")
    grouped: dict[str, tuple[ToolRequest, list[str]]] = {}
    unavailable = False
    exhausted = False
    insufficient = False
    for requirement in pending:
        reason = unpermitted_reason(requirement, deps, state)
        if reason is not None:
            unavailable = True
            # Keep the requirement in the plan and in the record: what the
            # investigation needed but could not obtain must stay visible.
            # A requirement that already has evidence keeps its own verdict.
            current = state.triage_requirement_results.get(requirement.requirement_id)
            if current is None or (
                current.status == "pending" and not current.evidence_ids
            ):
                state.triage_requirement_results[requirement.requirement_id] = (
                    RequirementResult(
                        status=(
                            "unsupported"
                            if reason in {"unsupported_tool", "invalid_arguments"}
                            else "unavailable"
                        ),
                        reason=f"read not authorized: {reason}",
                    )
                )
            continue
        request = request_for(requirement)
        key = fingerprint(request, cutoff)
        attempts = state.triage_read_attempts.get(key, 0)
        previous = next(
            (
                t
                for t in reversed(state.triage_decide_trace)
                if t.kind == "read"
                and t.tool == request.name
                and t.arguments == request.arguments
            ),
            None,
        )
        if attempts:
            if previous is None or previous.outcome not in (
                "provider_error",
                "untrusted_response",
            ):
                insufficient = True
                continue
            if attempts >= 2:
                exhausted = True
                continue
        if key not in grouped:
            grouped[key] = (request, [])
        grouped[key][1].append(requirement.requirement_id)
    if grouped:
        test_order = {
            rid: position
            for position, rid in enumerate(state.triage_test_requirement_ids)
        }
        ranked = sorted(
            grouped.items(),
            key=lambda entry: (
                read_priority(
                    tuple(entry[1][1]),
                    state=state,
                    direct=entry[1][0].name in SENSOR_READS,
                    order_position=min(
                        (test_order[rid] for rid in entry[1][1] if rid in test_order),
                        default=None,
                    ),
                ),
                entry[0],
            ),
        )
        _, (request, ids) = ranked[0]
        first = state.triage_requirements[ids[0]]
        return TriageReadDecision(
            step=CallTool(
                information_needed=f"deterministic triage {first.question_id}",
                request=request,
                question_id=first.question_id,
            ),
            requirement_ids=tuple(ids),
            reason=f"unmet qualified requirement ({READ_RANKING_POLICY})",
            candidate_count=len(grouped),
        )
    reason: TriageStopReason = (
        "retries_exhausted"
        if exhausted
        else "capability_unavailable"
        if unavailable
        else "data_insufficient"
        if insufficient
        else "no_eligible_read"
    )
    return TriageStopDecision(
        reason=reason,
        unresolved_requirement_ids=tuple(r.requirement_id for r in pending),
    )


def stop(
    state: InvestigationState,
    phase: str,
    decision: TriageStopDecision,
    deps: "InvestigationDeps",
) -> TerminationReason:
    """Record the triage-specific reason and its legacy loop equivalent.

    One authoritative completion rule at the boundary every stop crosses: a
    `requirements_complete` decision is converted to `data_insufficient`,
    keeping its unresolved ids, when a required requirement is unresolved.
    This is an explicit recorded transition, not an assertion, so it holds
    under optimized execution and never interrupts the Graph.
    """
    # Variables:
    #   effective: The stop actually recorded; the converted one on violation.
    #   outstanding: Required requirements still not satisfied, sorted.
    from capstone.agent.loop import record

    effective = decision
    converted = False
    if decision.reason == "requirements_complete":
        # A phase-filtered empty list, or an empty question list, never
        # proves sufficiency on its own. Neither does a satisfied
        # requirement ledger: a mandatory question may still be open, or
        # a composite one may have a gap its parts cannot settle.
        outstanding = unresolved_required(state)
        open_questions = tuple(q.id for q in state.unanswered_questions)
        gapped = tuple(sorted(state.triage_question_gaps))
        if (
            outstanding
            or open_questions
            or gapped
            or state.triage_bookkeeping_anomalies
        ):
            converted = True
            effective = TriageStopDecision(
                reason="data_insufficient",
                unresolved_requirement_ids=tuple(
                    sorted(set(outstanding) | set(decision.unresolved_requirement_ids))
                ),
            )
    if converted:
        # Observable on purpose: an invalid completion attempt is a controller
        # bug worth finding in a saved run, not something to swallow.
        emit_triage_event(
            state,
            deps,
            event="triage.completion_converted",
            phase=phase,
            reason_code="data_insufficient",
            status="stopped",
            requirement_ids=effective.unresolved_requirement_ids,
            question_ids=tuple(q.id for q in state.unanswered_questions),
        )
    state.triage_deterministic_stops += 1
    state.triage_decide_trace.append(
        TriageDecisionRecord(
            phase=phase,
            iteration=state.iteration_count,
            kind="stop",
            reason=effective.reason,
            requirement_ids=effective.unresolved_requirement_ids,
        )
    )
    # Keep the reason and all outstanding dependencies even for budget stops.
    unresolved = tuple(
        sorted(
            set(effective.unresolved_requirement_ids)
            | {
                rid
                for rid in state.triage_requirements
                if rid not in state.triage_requirement_results
                or state.triage_requirement_results[rid].status != "satisfied"
            }
        )
    )
    emit_triage_event(
        state,
        deps,
        event="triage.stopped",
        phase=phase,
        reason_code=effective.reason,
        status="stopped",
        requirement_ids=unresolved,
        question_ids=tuple(q.id for q in state.unanswered_questions),
        iteration=state.iteration_count,
        remaining_tool_calls=state.remaining_tool_calls,
    )
    mapped = STOP_MAP[effective.reason]
    record(
        state,
        phase,
        "stopped",
        information_needed=effective.reason,
        termination_reason=mapped,
    )
    return mapped


def run_deterministic_triage_loop(
    state: InvestigationState, deps: "InvestigationDeps", phase: str
) -> TerminationReason:
    """Collect only prevalidated evidence, with reproducible decision diagnostics."""
    from capstone.agent.loop import gather, held_for_hypotheses, notify

    # Guard direct/replayed entry as well as the Pydantic Graph routing edge:
    # reject an invalid phase or deep state before any read or state mutation.
    if state.mode != "triage" or phase not in ("investigate", "test"):
        raise ValueError("deterministic triage requires triage Investigate/Test")
    if not deps.triage_tool_specs:
        raise ValueError("deterministic triage requires an authorized tool catalog")
    if not deps.triage_allowed_sources or any(
        not isinstance(source, str) or not source.strip()
        for source in deps.triage_allowed_sources
    ):
        raise ValueError("deterministic triage requires authorized provider sources")
    if not state.fixed_plan_used:
        raise ValueError("deterministic triage requires a fixed plan")
    if state.started_at is None:
        state.started_at = deps.clock()
    state.step_questions = deps.step_questions
    state.decide_calls = deps.decide_calls
    state.triage_allowed_sources = deps.triage_allowed_sources
    initialize_requirements(state)
    if not any(e.event == "triage.started" for e in state.triage_trace_events):
        config_input = json.dumps(
            {
                "controller": deps.triage_investigate,
                "step_questions": deps.step_questions,
                "decide_calls": deps.decide_calls,
                "fixed_plan": state.fixed_plan_used,
                "cutoff": state.triage_observation_cutoff_tick,
                "authorized_sources": sorted(deps.triage_allowed_sources),
                "catalog": sorted(spec.name for spec in deps.triage_tool_specs),
                "channels": {
                    machine: sorted(channels)
                    for machine, channels in sorted(deps.triage_channels.items())
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        emit_triage_event(
            state,
            deps,
            event="triage.started",
            phase=phase,
            reason_code="started",
            status="active",
            config_fingerprint=sha256(config_input.encode("utf-8")).hexdigest()[:20],
            iteration=state.iteration_count,
            remaining_tool_calls=state.remaining_tool_calls,
        )
    emit_triage_event(
        state,
        deps,
        event="requirements.compiled",
        phase=phase,
        reason_code="compiled",
        status="active",
        requirement_ids=tuple(sorted(state.triage_requirements)),
        question_ids=tuple(
            sorted({r.question_id for r in state.triage_requirements.values()})
        ),
        iteration=state.iteration_count,
        remaining_tool_calls=state.remaining_tool_calls,
    )

    def finish(decision: TriageStopDecision) -> TerminationReason:
        return stop(state, phase, decision, deps)

    # The monitor's previous tick is not a verified Observe clock.
    # A missing verdict is not authorization: only the admitted get_time
    # result can establish the source horizon. This also protects replay
    # and direct loop entry points that bypass the Observe stage.
    if state.triage_clock_verified is not True:
        return finish(
            TriageStopDecision(
                reason="data_insufficient",
                unresolved_requirement_ids=tuple(sorted(state.triage_requirements)),
            )
        )

    def reconcile() -> None:
        """Emit only changed requirement results; no noisy repeated state dumps."""
        # Variables:
        #   previous: Last qualification outcome per requirement.
        #   result: Most recent typed evaluation of that requirement.
        previous = {
            rid: (r.status, r.evidence_ids, r.reason)
            for rid, r in state.triage_requirement_results.items()
        }
        before_open = {q.id for q in state.unanswered_questions}
        before_gaps = dict(state.triage_question_gaps)
        before_evidence = {
            qid: tuple(ids) for qid, ids in state.triage_question_evidence.items()
        }
        evaluate_triage_requirements(state, deps)
        for rid, result in sorted(state.triage_requirement_results.items()):
            before = previous.get(rid)
            after = (result.status, result.evidence_ids, result.reason)
            if before != after:
                emit_triage_event(
                    state,
                    deps,
                    event="triage.requirement_evaluated",
                    phase=phase,
                    reason_code=requirement_reason_code(result.status, result.reason),
                    status=result.status,
                    requirement_ids=(rid,),
                    evidence_ids=result.evidence_ids,
                )
        after_open = {q.id for q in state.unanswered_questions}
        for qid in sorted({r.question_id for r in state.triage_requirements.values()}):
            evidence_ids = tuple(state.triage_question_evidence.get(qid, ()))
            if (
                (qid in before_open) != (qid in after_open)
                or before_gaps.get(qid) != state.triage_question_gaps.get(qid)
                or before_evidence.get(qid, ()) != evidence_ids
            ):
                unresolved = qid in after_open
                emit_triage_event(
                    state,
                    deps,
                    event="question.evaluated",
                    phase=phase,
                    reason_code="unresolved" if unresolved else "closed",
                    status="unresolved" if unresolved else "satisfied",
                    question_ids=(qid,),
                    evidence_ids=evidence_ids,
                )

    while True:
        notify(state, deps)
        now = deps.clock()
        if state.remaining_seconds(now) <= 0 or (
            state.research_seconds(now) - held_for_hypotheses(state, deps) <= 0
        ):
            return finish(TriageStopDecision(reason="timeout"))
        reconcile()
        if phase == "test":
            # Typed candidate requirements only: never compile model-written
            # test questions in the deterministic hypothesis arm.
            if deps.triage_hypothesize != "deterministic":
                add_test_requirements(state)
            reconcile()
        if not state.unanswered_questions and not unresolved_required(state):
            return finish(TriageStopDecision(reason="requirements_complete"))
        if state.remaining_iterations <= 0:
            return finish(TriageStopDecision(reason="max_iterations"))
        if state.remaining_tool_calls <= 0:
            return finish(TriageStopDecision(reason="max_tool_calls"))
        decision = choose_next_triage_read(state, deps, phase)
        if isinstance(decision, TriageStopDecision):
            # An empty question list is never completion on its own: if a
            # required requirement is still unresolved, the stop keeps it on
            # the record, whatever reason the selector gave.
            outstanding = unresolved_required(state)
            if outstanding and not state.unanswered_questions:
                return finish(
                    TriageStopDecision(
                        reason=decision.reason,
                        unresolved_requirement_ids=tuple(
                            sorted(
                                set(outstanding)
                                | set(decision.unresolved_requirement_ids)
                            )
                        ),
                    )
                )
            return finish(decision)
        if deps.triage_hypothesize == "deterministic":
            from capstone.agent.triage_hypothesize import log_hypothesis_event

            log_hypothesis_event(
                state,
                deps,
                "triage.read.selected",
                tool=decision.step.request.name,
                counts={
                    "requirements": len(decision.requirement_ids),
                    "remaining_calls": state.remaining_tool_calls,
                },
            )
        state.iteration_count += 1
        cutoff = state.triage_observation_cutoff_tick
        if cutoff is None:
            return finish(missing_cutoff_stop(state))
        request = decision.step.request
        key = fingerprint(request, cutoff)
        attempts = state.triage_read_attempts.get(key, 0)
        state.triage_read_attempts[key] = attempts + 1
        request_hash = sha256(key.encode("utf-8")).hexdigest()[:20]
        emit_triage_event(
            state,
            deps,
            event="decide.selected",
            phase=phase,
            reason_code="selected",
            status="pending",
            tool=request.name,
            requirement_ids=decision.requirement_ids,
            request_hash=request_hash,
            attempt=attempts + 1,
            iteration=state.iteration_count,
            candidate_count=decision.candidate_count,
            remaining_tool_calls=state.remaining_tool_calls,
        )
        emit_triage_event(
            state,
            deps,
            event="triage.read_selected",
            phase=phase,
            reason_code="selected",
            status="pending",
            tool=request.name,
            requirement_ids=decision.requirement_ids,
            request_hash=request_hash,
            attempt=attempts + 1,
            iteration=state.iteration_count,
        )
        # Emit a pending selection while the provider is still running.
        # The watcher receives a copy and cannot mutate the deterministic choice;
        # its bounded journal queue must not block or affect tool execution.
        notify(state, deps)
        started = deps.clock()
        trusted_before_read = state.last_tick
        qualification: EvidenceQualification | None = None

        def precommit(result) -> str | None:
            """Return a safe reason code; no invalid evidence is ever appended."""
            nonlocal qualification
            try:
                qualification = validate_triage_result(
                    result,
                    request,
                    cutoff,
                    min_result_tick=trusted_before_read,
                    allowed_sources=deps.triage_allowed_sources,
                )
            except Exception:
                # An internal validator error is itself a rejected observation.
                qualification = EvidenceQualification(
                    accepted=False,
                    reason_code="validator_error",
                    observed_tick=result.tick,
                )
            return None if qualification.accepted else qualification.reason_code

        evidence = gather(
            state,
            deps,
            phase,
            decision.step,
            interpret=False,
            defer_question_bookkeeping=True,
            retry_failed=attempts > 0,
            validate_result=precommit,
        )
        duration_ms = max(0.0, (deps.clock() - started) * 1000.0)
        outcome = state.decisions[-1].outcome
        if qualification is not None:
            checked = qualification.model_copy(
                update={
                    "evidence_id": evidence.id if evidence is not None else None,
                    "request_hash": request_hash,
                }
            )
            state.triage_evidence_checks.append(checked)
            emit_triage_event(
                state,
                deps,
                event=(
                    "triage.evidence_accepted"
                    if checked.accepted
                    else "triage.evidence_rejected"
                ),
                phase=phase,
                reason_code=checked.reason_code,
                status="accepted" if checked.accepted else "rejected",
                tool=request.name,
                requirement_ids=decision.requirement_ids,
                evidence_ids=(evidence.id,) if evidence is not None else (),
                duration_ms=duration_ms,
                request_hash=request_hash,
                attempt=attempts + 1,
                iteration=state.iteration_count,
            )
            if not qualification.accepted:
                outcome = "invalid_result"
        else:
            if outcome == "tool_error":
                error = state.decisions[-1].error
                outcome = error.code if error is not None else "untrusted_response"
            elif outcome == "malformed_result" and deps.last_provider_exception:
                outcome = "untrusted_response"
            failure_code = (
                outcome
                if outcome
                in {
                    "invalid_result",
                    "invalid_arguments",
                    "unknown_tool",
                    "provider_error",
                    "untrusted_response",
                    "malformed_result",
                    "repeated_call",
                }
                else "malformed_result"
            )
            state.triage_evidence_checks.append(
                EvidenceQualification(
                    accepted=False,
                    reason_code=failure_code,
                    request_hash=request_hash,
                )
            )
            emit_triage_event(
                state,
                deps,
                event="triage.read_failed",
                phase=phase,
                reason_code=(
                    outcome
                    if outcome
                    in {
                        "invalid_result",
                        "invalid_arguments",
                        "unknown_tool",
                        "provider_error",
                        "untrusted_response",
                        "malformed_result",
                        "repeated_call",
                    }
                    else "read_failed"
                ),
                status="failed",
                tool=request.name,
                requirement_ids=decision.requirement_ids,
                duration_ms=duration_ms,
                request_hash=request_hash,
                attempt=attempts + 1,
                iteration=state.iteration_count,
            )
        checked = state.triage_evidence_checks[-1]
        emit_triage_event(
            state,
            deps,
            event="evidence.validated",
            phase=phase,
            reason_code=checked.reason_code,
            status="accepted" if checked.accepted else "rejected",
            tool=request.name,
            requirement_ids=decision.requirement_ids,
            evidence_ids=(evidence.id,) if evidence is not None else (),
            request_hash=request_hash,
            attempt=attempts + 1,
            duration_ms=deps.triage_last_admission_ms,
        )
        emit_triage_event(
            state,
            deps,
            event="tool.completed",
            phase=phase,
            reason_code="observed" if evidence is not None else checked.reason_code,
            status="accepted" if evidence is not None else "failed",
            tool=request.name,
            requirement_ids=decision.requirement_ids,
            evidence_ids=(evidence.id,) if evidence is not None else (),
            request_hash=request_hash,
            attempt=attempts + 1,
            iteration=state.iteration_count,
            duration_ms=deps.triage_last_provider_ms,
            remaining_tool_calls=state.remaining_tool_calls,
        )
        state.triage_deterministic_reads += 1
        state.triage_decide_trace.append(
            TriageDecisionRecord(
                phase=phase,
                iteration=state.iteration_count,
                kind="read",
                reason=decision.reason,
                tool=request.name,
                arguments=request.arguments,
                requirement_ids=decision.requirement_ids,
                evidence_ids=(evidence.id,) if evidence is not None else (),
                outcome=outcome,
            )
        )
        if deps.triage_hypothesize == "deterministic":
            # No raw result, provider exception, or free-text reason leaves
            # the typed state through the operational logging channel.
            from capstone.agent.triage_hypothesize import log_hypothesis_event

            log_hypothesis_event(
                state,
                deps,
                "triage.read.result",
                tool=decision.step.request.name,
                success=evidence is not None,
                counts={
                    "attempt": attempts + 1,
                    "qualified_response": int(evidence is not None),
                    "failed_response": int(evidence is None),
                },
            )
