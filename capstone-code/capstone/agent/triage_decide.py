"""Read-only, model-free Decide controller for opt-in fixed-plan triage.

This controller collects observations; it never asserts that the diagnosis is
correct. Hypothesize and Conclude retain their existing model-backed roles.
"""

import json
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
from capstone.agent.triage_trace import emit_triage_event
from capstone.contracts.tools import ToolRequest
from capstone.providers.factory import TOOL_ARGUMENTS

if TYPE_CHECKING:
    from capstone.agent.loop import InvestigationDeps

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


def permitted_triage_read(
    requirement: ReadRequirement, deps: "InvestigationDeps", state: InvestigationState
) -> bool:
    """Check catalog, channel, argument and cutoff before a provider call."""
    # Variables:
    #   cutoff: The source horizon captured before any controller reads.
    #   names: Authorized read-only operations for this particular provider.
    cutoff = state.triage_observation_cutoff_tick
    names = {spec.name for spec in deps.triage_tool_specs}
    if requirement.tool not in READ_ONLY or requirement.tool not in names:
        return False
    if cutoff is None or (
        requirement.to_tick is not None and requirement.to_tick > cutoff
    ):
        return False
    if (
        requirement.machine_id is not None
        and requirement.machine_id not in known_machines(state)
    ):
        return False
    if (
        requirement.sensor is not None
        and requirement.sensor
        not in deps.triage_channels.get(requirement.machine_id or "factory", ())
    ):
        return False
    try:
        TOOL_ARGUMENTS[requirement.tool].model_validate(
            request_for(requirement).arguments
        )
    except (KeyError, ValueError):
        return False
    return True


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
    cutoff = state.triage_observation_cutoff_tick
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
        try:
            found.append((evidence.id, json.loads(evidence.content)))
        except ValueError:
            continue
    return found


def qualify(
    state: InvestigationState, requirement: ReadRequirement
) -> RequirementResult:
    """Judge matching observations without treating a tool success as completion."""
    # Variables:
    #   matches: Observable evidence from the requested source at the cutoff.
    #   data: Parsed tool answer; shape and finite values must be checked.
    #   first, last: Actual first and last observed sample ticks around the alarm.
    #   best: Strongest predicate verdict based on sufficiently spread samples.
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
    if requirement.qualification == "record":
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
        failures = [
            row
            for _, data in matches
            if isinstance(data, list)
            for row in data
            if isinstance(row, dict) and row.get("result") == "failed"
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
            len(jobs) >= 2 and len(identified) == len(failures) and len(failures) >= 2
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
        return RequirementResult(
            status="satisfied" if complete else "insufficient",
            evidence_ids=ids,
            reason=(
                "all observed failed jobs share batch " + str(next(iter(distinct)))
                if len(distinct) == 1
                else "observed failed jobs have different batch identifiers"
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
    #   job_ids: Every dated failed job in the observed inspection window.
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


def evaluate_triage_requirements(state: InvestigationState) -> None:
    """Reconcile all requirements, attach shared evidence, and close only complete questions."""
    # Variables:
    #   by_question: Required parts of each question, evaluated independently.
    #   movement: Q5's three source requirements, not proof of correlation.
    #   all_qualified: Whether each source passes independently.
    expand_job_requirements(state)
    by_question: dict[str, list[str]] = {}
    for rid, requirement in state.triage_requirements.items():
        result = qualify(state, requirement)
        state.triage_requirement_results[rid] = result
        by_question.setdefault(requirement.question_id, []).append(rid)
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


def choose_next_triage_read(
    state: InvestigationState, deps: "InvestigationDeps", phase: str
) -> TriageReadDecision | TriageStopDecision:
    """Select one unmet authorized read, or explain why collection stops."""
    # Variables:
    #   pending: Requirements still missing qualified evidence.
    #   grouped: One request may answer several requirements with one call.
    #   attempts: Count for the exact request at this stable cutoff.
    cutoff = state.triage_observation_cutoff_tick
    assert cutoff is not None
    pending = [
        r
        for r in state.triage_requirements.values()
        if state.triage_requirement_results[r.requirement_id].status != "satisfied"
    ]
    if not pending and not state.unanswered_questions:
        return TriageStopDecision(reason="requirements_complete")
    grouped: dict[str, tuple[ToolRequest, list[str]]] = {}
    unavailable = False
    exhausted = False
    insufficient = False
    for requirement in pending:
        if not permitted_triage_read(requirement, deps, state):
            unavailable = True
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
        request, ids = next(iter(grouped.values()))
        first = state.triage_requirements[ids[0]]
        return TriageReadDecision(
            step=CallTool(
                information_needed=f"deterministic triage {first.question_id}",
                request=request,
                question_id=first.question_id,
            ),
            requirement_ids=tuple(ids),
            reason="unmet qualified requirement",
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
    """Record the triage-specific reason and its legacy loop equivalent."""
    from capstone.agent.loop import record

    state.triage_deterministic_stops += 1
    state.triage_decide_trace.append(
        TriageDecisionRecord(
            phase=phase,
            iteration=state.iteration_count,
            kind="stop",
            reason=decision.reason,
            requirement_ids=decision.unresolved_requirement_ids,
        )
    )
    # Keep the reason and all outstanding dependencies even for budget stops.
    unresolved = tuple(
        sorted(
            rid
            for rid, result in state.triage_requirement_results.items()
            if result.status != "satisfied"
        )
    )
    emit_triage_event(
        state,
        deps,
        event="triage.stopped",
        phase=phase,
        reason_code=decision.reason,
        status="stopped",
        requirement_ids=unresolved,
    )
    mapped = STOP_MAP[decision.reason]
    record(
        state,
        phase,
        "stopped",
        information_needed=decision.reason,
        termination_reason=mapped,
    )
    return mapped


def run_deterministic_triage_loop(
    state: InvestigationState, deps: "InvestigationDeps", phase: str
) -> TerminationReason:
    """Collect only prevalidated evidence, with reproducible decision diagnostics."""
    from capstone.agent.loop import gather, held_for_hypotheses, notify

    if not deps.triage_tool_specs:
        raise ValueError("deterministic triage requires an authorized tool catalog")
    if not state.fixed_plan_used:
        raise ValueError("deterministic triage requires a fixed plan")
    if state.started_at is None:
        state.started_at = deps.clock()
    state.step_questions = deps.step_questions
    state.decide_calls = deps.decide_calls
    initialize_requirements(state)

    def finish(decision: TriageStopDecision) -> TerminationReason:
        return stop(state, phase, decision, deps)

    def reconcile() -> None:
        """Emit only changed requirement results; no noisy repeated state dumps."""
        # Variables:
        #   previous: Last qualification outcome per requirement.
        #   result: Most recent typed evaluation of that requirement.
        previous = {
            rid: (r.status, r.evidence_ids, r.reason)
            for rid, r in state.triage_requirement_results.items()
        }
        evaluate_triage_requirements(state)
        for rid, result in sorted(state.triage_requirement_results.items()):
            before = previous.get(rid)
            after = (result.status, result.evidence_ids, result.reason)
            if before != after:
                emit_triage_event(
                    state,
                    deps,
                    event="triage.requirement_evaluated",
                    phase=phase,
                    reason_code=result.status,
                    status=result.status,
                    requirement_ids=(rid,),
                    evidence_ids=result.evidence_ids,
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
            add_test_requirements(state)
            reconcile()
        if not state.unanswered_questions:
            return finish(TriageStopDecision(reason="requirements_complete"))
        if state.remaining_iterations <= 0:
            return finish(TriageStopDecision(reason="max_iterations"))
        if state.remaining_tool_calls <= 0:
            return finish(TriageStopDecision(reason="max_tool_calls"))
        decision = choose_next_triage_read(state, deps, phase)
        if isinstance(decision, TriageStopDecision):
            return finish(decision)
        state.iteration_count += 1
        cutoff = state.triage_observation_cutoff_tick
        assert cutoff is not None
        request = decision.step.request
        key = fingerprint(request, cutoff)
        attempts = state.triage_read_attempts.get(key, 0)
        state.triage_read_attempts[key] = attempts + 1
        emit_triage_event(
            state,
            deps,
            event="triage.read_selected",
            phase=phase,
            reason_code="selected",
            status="pending",
            tool=request.name,
            requirement_ids=decision.requirement_ids,
        )
        started = deps.clock()
        qualification: EvidenceQualification | None = None

        def precommit(result) -> str | None:
            """Return a safe reason code; no invalid evidence is ever appended."""
            nonlocal qualification
            try:
                qualification = validate_triage_result(result, request, cutoff)
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
                    "request_hash": sha256(key.encode("utf-8")).hexdigest()[:20],
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
            )
            if not qualification.accepted:
                outcome = "invalid_result"
        else:
            if outcome == "tool_error":
                error = state.decisions[-1].error
                outcome = error.code if error is not None else "untrusted_response"
            elif outcome == "malformed_result" and deps.last_provider_exception:
                outcome = "untrusted_response"
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
