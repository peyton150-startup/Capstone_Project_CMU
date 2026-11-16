"""Deterministic, unscored candidate and test packets for opt-in triage.

A candidate is a possibility worth checking, NOT a diagnosed cause. The
compiler consumes only the fixed plan and qualified observable evidence;
it never reads simulator fault labels or assigns probabilities.
"""

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from capstone.contracts import Contract

if TYPE_CHECKING:
    from capstone.agent.state import InvestigationState


class TriageCandidate(Contract):
    """A source-linked possibility, without fabricated model confidence."""

    id: str = Field(pattern=r"^TC[1-9][0-9]*$")
    family: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    machine_id: str | None = None
    status: Literal["unconfirmed"] = "unconfirmed"
    # These are observations relevant to a check, never causal support claims.
    observation_evidence_ids: tuple[str, ...] = ()
    discriminating_requirement_ids: tuple[str, ...] = ()
    missing_requirement_ids: tuple[str, ...] = ()


class TriageHypothesisTrace(Contract):
    """A bounded, replayable record of the fixed candidate compiler."""

    stage: Literal["hypothesize", "test"]
    action: Literal["compiled", "refreshed", "no_candidates"]
    candidate_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    qualified_sources: int = Field(default=0, ge=0)
    missing_sources: int = Field(default=0, ge=0)


# Families are potential explanations, not labels extracted from ground truth.
# A listed requirement tells the controller what could discriminate between
# possibilities, not what cause was proved by a successful tool response.
ALARM_RULES = (
    ("machine_condition", "Machine or process condition may explain the alarm",
     ("Q1:trigger", "Q3:events", "Q3:service")),
    ("operating_load", "Related load or temperature behavior may be relevant",
     ("Q1:trigger", "Q5:vibration", "Q5:temperature", "Q5:load")),
    ("sensor_or_transient", "A transient or measurement issue remains possible",
     ("Q1:trigger",)),
)

STATUS_RULES = (
    ("stoppage_event", "Recorded events may help explain the machine stop",
     ("Q1:events",)),
    ("process_condition", "Sensor behavior may be associated with the stop",
     ("Q2:vibration", "Q2:temperature", "Q2:load")),
    ("service_context", "Service or settings may be relevant but not proven",
     ("Q4:service",)),
)

INSPECTION_RULES = (
    ("common_machine_path", "Failed jobs may share a visited machine",
     ("Q1:failed_jobs",)),
    ("common_material_batch", "Failed jobs may share a material batch",
     ("Q2:inspections",)),
    ("preceding_events", "Recorded events may precede the failed parts",
     ("Q5:events",)),
)

GENERIC_RULES = (
    ("observed_event", "The anomaly may be connected to recorded events",
     ("Q2:events",)),
    ("quality_signal", "Inspection evidence may narrow the possibilities",
     ("Q3:inspections",)),
)


def rule_specs(state: "InvestigationState") -> tuple[
    tuple[str, str, tuple[str, ...]], ...
]:
    """Select explicit case families from the observable anomaly category."""
    # Variables:
    #   alarm: Parsed alarm text; it is not a root-cause label.
    # Keep the fixed-plan import inside the function: triage_plan imports
    # InvestigationState, while state imports the candidate contract above.
    from capstone.agent.triage_plan import ALARM

    alarm = (
        ALARM.match(state.anomaly.description)
        if state.anomaly.kind == "alarm"
        else None
    )
    if alarm is not None and state.anomaly.machine_id is not None:
        if alarm["sensor"] == "vibration":
            return ALARM_RULES
        return (
            ALARM_RULES[0],
            ("related_quality", "Inspection evidence may show a related effect",
             ("Q5:inspections",)),
            ALARM_RULES[2],
        )
    if state.anomaly.kind == "status":
        return STATUS_RULES
    if state.anomaly.kind == "inspection_failures":
        return INSPECTION_RULES
    return GENERIC_RULES


def compile_candidates(
    state: "InvestigationState",
) -> tuple[tuple[TriageCandidate, ...], tuple[str, ...]]:
    """Compile possibilities and test requirements without a model or side effects."""
    # Variables:
    #   available: The fixed plan's typed requirements, never simulated truth.
    #   observed: Factory-observable evidence ids; a recollection cannot qualify.
    #   target_ids: Existing requirements associated with a possible explanation.
    #   needed: Requirements whose source is not yet qualified.
    #   tests: Ordered union of checks to run in Test, stable for replay.
    available = state.triage_requirements
    observed = {
        provenance.evidence_id
        for provenance in state.provenance
        if provenance.origin == "observable"
    }
    candidates: list[TriageCandidate] = []
    tests: list[str] = []
    for family, explanation, parts in rule_specs(state):
        target_ids = [rid for rid in parts if rid in available]
        if family == "common_machine_path":
            target_ids.extend(sorted(
                rid for rid in available if rid.startswith("Q1:job:")
            ))
        if not target_ids:
            continue
        seen_ids: list[str] = []
        needed: list[str] = []
        for rid in target_ids:
            result = state.triage_requirement_results.get(rid)
            if result is not None and result.status == "satisfied":
                seen_ids.extend(eid for eid in result.evidence_ids if eid in observed)
            else:
                needed.append(rid)
            # A setting snapshot cannot prove a change; never schedule an
            # inherently non-verifiable historical claim as a discriminating test.
            if available[rid].qualification != "setting_change" and rid not in tests:
                tests.append(rid)
        candidates.append(
            TriageCandidate(
                id=f"TC{len(candidates) + 1}",
                family=family,
                explanation=explanation,
                machine_id=state.anomaly.machine_id,
                observation_evidence_ids=tuple(dict.fromkeys(seen_ids)),
                discriminating_requirement_ids=tuple(target_ids),
                missing_requirement_ids=tuple(needed),
            )
        )
    return tuple(candidates), tuple(tests)


def update_candidate_packet(state: "InvestigationState", *, stage: Literal[
    "hypothesize", "test"
]) -> None:
    """Store a reproducible packet and its reference-only trace."""
    # Variables:
    #   candidates: Refreshed sources and gaps, not model beliefs.
    #   test_ids: Canonical, qualified-source read targets for the Test scheduler.
    #   trace: Stable ids and counters suitable for private run records.
    candidates, test_ids = compile_candidates(state)
    state.triage_candidates = list(candidates)
    state.triage_test_requirement_ids = test_ids
    trace = TriageHypothesisTrace(
        stage=stage,
        action=("compiled" if stage == "hypothesize" else "refreshed")
        if candidates else "no_candidates",
        candidate_ids=tuple(candidate.id for candidate in candidates),
        requirement_ids=test_ids,
        qualified_sources=sum(
            len(candidate.observation_evidence_ids) for candidate in candidates
        ),
        missing_sources=sum(
            len(candidate.missing_requirement_ids) for candidate in candidates
        ),
    )
    state.triage_hypothesis_trace.append(trace)
