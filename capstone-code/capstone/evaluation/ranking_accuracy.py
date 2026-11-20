# Scores the two-candidate triage ranking against the known cases' hidden truth.
# Responsibility: say, after a run, whether each ranking had the right form and named the true cause.
"""Ranking accuracy: whether a triage ranking named the true cause.

Deterministic triage compiles candidates TC1..TCn, each a cause *family* on a
machine (`capstone.agent.triage_hypothesize`), and the conclusion model may
rank two of them with its own uncalibrated confidences, or abstain
(`capstone.agent.triage_ranking`). This module judges those rankings after
the run, against the case's true causes (`capstone.evaluation.scoring.Cause`).

Three questions are kept apart, because they fail for different reasons:

- **Form:** was the answer valid (accepted or abstained) or rejected, and why?
- **Accuracy:** did the top pick, or either of the two picks, name a true
  cause? And was a true cause among the candidates at all? When it was not,
  a miss is the candidate list's fault, not the model's.
- **Calibration:** not measured. The mean confidence of right and wrong top
  picks is reported, but 13 cases is a functionality check, far too few to
  say whether a confidence of 0.7 means "right 7 times in 10".

Families are not faults, so `FAMILY_FAULTS` says, family by family, which
true faults a pick of that family counts as naming, and whether the
candidate's machine has to be the faulty one. A family that only points at
evidence (events, inspections, a coverage gap) names no fault.

Evaluator-side only. This module reads hidden truth; nothing in it may reach
a prompt, a tool answer, the ranking check or memory.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

from capstone.agent.triage_hypothesize import CandidateFamily
from capstone.agent.triage_ranking import (
    RankingSnapshot,
    RankingVerdict,
    SnapshotCandidate,
)
from capstone.evaluation.scoring import Cause

# How a family's candidate must relate to the faulty machine to count:
#   same_machine: the candidate names a machine and it is the faulty one.
#   if_named: a candidate naming a machine must name the faulty one; one
#     naming none (an inspection anomaly has no machine) still counts.
#   not_needed: the family is not about one machine (a material batch).
MachineRule = Literal["same_machine", "if_named", "not_needed"]

# The faults that wear a machine down until it is repaired.
DEGRADATION = frozenset({"bearing_degradation", "servo_drive_wear", "hydraulic_leak"})


@dataclass(frozen=True)
class FamilyFaults:
    """The true faults a pick of one candidate family counts as naming."""

    faults: frozenset[str]
    machine: MachineRule
    why: str


# Every candidate family, and what naming it would count as. Kept strict: a
# family counts only for the faults its own explanation names as a cause.
FAMILY_FAULTS: dict[str, FamilyFaults] = {
    "machine_condition": FamilyFaults(
        DEGRADATION,
        "same_machine",
        "'machine or process condition' on the alarmed machine: a wearing part",
    ),
    "process_condition": FamilyFaults(
        DEGRADATION,
        "same_machine",
        "a stop's sensor family is the only one offered for the machine's own "
        "condition, so it stands for a wearing part as machine_condition does",
    ),
    "sensor_or_transient": FamilyFaults(
        frozenset({"false_alarm"}),
        "same_machine",
        "a transient or measurement issue on the alarmed machine: a false alarm",
    ),
    "setting_shift": FamilyFaults(
        frozenset({"wrong_setting"}),
        "if_named",
        "a changed setting; from an inspection anomaly it names no machine",
    ),
    "service_context": FamilyFaults(
        frozenset({"wrong_setting"}),
        "same_machine",
        "'service or settings' on the stopped machine: a changed setting",
    ),
    "common_material_batch": FamilyFaults(
        frozenset({"bad_material_batch"}),
        "not_needed",
        "failed jobs sharing a material batch; the candidate names no batch",
    ),
    # Families that point at evidence or a symptom, not at a cause.
    "operating_load": FamilyFaults(
        frozenset(), "not_needed", "a symptom (load, temperature), not a cause"
    ),
    "related_quality": FamilyFaults(
        frozenset(), "not_needed", "an effect on inspections, not a cause"
    ),
    "stoppage_event": FamilyFaults(
        frozenset(), "not_needed", "recorded events, not a cause"
    ),
    "common_machine_path": FamilyFaults(
        frozenset(),
        "not_needed",
        "a shared machine says where, not what: no fault kind is named",
    ),
    "preceding_events": FamilyFaults(
        frozenset(), "not_needed", "recorded events, not a cause"
    ),
    "observed_event": FamilyFaults(
        frozenset(), "not_needed", "recorded events, not a cause"
    ),
    "quality_signal": FamilyFaults(
        frozenset(), "not_needed", "inspection evidence, not a cause"
    ),
    "cross_machine_review": FamilyFaults(
        frozenset(), "not_needed", "a comparison across machines, not a cause"
    ),
    "telemetry_coverage_gap": FamilyFaults(
        frozenset(), "not_needed", "missing observations, not a cause"
    ),
}

assert set(FAMILY_FAULTS) == set(get_args(CandidateFamily)), "map every family"

# Below this many cases, rates are a functionality check, not an estimate.
SMALL_SAMPLE_CASES = 30

CONFIDENCE_NOTE = (
    "Confidences are the model's own, uncalibrated and independent per pick; "
    "their means describe this run, not how often a confidence is right."
)

# A case with no verdict at all (the ranking was never asked or never stored).
MISSING = "missing"


def family_names(family: str, machine_id: str | None, cause: Cause) -> bool:
    """Whether a pick of this family on this machine counts as naming this cause."""
    # Variables:
    #   machine_id: The machine the picked candidate is about; None when it
    #     names none (an inspection anomaly).
    #   rule: What the family counts as naming, and its machine rule; None
    #     for a family no candidate can have (a record writes "" for a pick
    #     whose TC id was not in the snapshot), which names nothing.
    rule = FAMILY_FAULTS.get(family)
    if rule is None or cause.fault not in rule.faults:
        return False
    if rule.machine == "same_machine":
        return machine_id is not None and machine_id == cause.machine_id
    if rule.machine == "if_named":
        return machine_id is None or machine_id == cause.machine_id
    return True


def candidate_names(candidate: SnapshotCandidate, cause: Cause) -> bool:
    """Whether picking this snapshot candidate counts as naming this true cause."""
    return family_names(candidate.family, candidate.machine_id, cause)


def names_any(candidate: SnapshotCandidate, causes: Iterable[Cause]) -> bool:
    """Whether this candidate names at least one of the true causes."""
    # Variables:
    #   causes: Every true cause of the case; naming any one of them is enough,
    #     so either cause of the compound challenge counts.
    return any(candidate_names(candidate, cause) for cause in causes)


class CaseRankingScore(BaseModel):
    """How one case's ranking turned out against its true causes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str
    # accepted / abstained / rejected from the verdict; "unavailable" when
    # the run recorded that no ranking could be had; "missing" without one.
    status: Literal["accepted", "abstained", "rejected", "unavailable", "missing"]
    # The verdict's fixed reason code, or "missing".
    reason: str
    valid: bool
    abstained: bool
    # Only an accepted ranking can be right; False otherwise.
    top1_correct: bool
    top2_correct: bool
    # A true cause was among the candidates the model was shown. None when
    # the candidates are not known (an older run record without them).
    true_cause_in_candidates: bool | None
    candidate_count: int | None
    # The top pick's confidence; None unless accepted.
    top1_confidence: float | None


def score_case(
    scenario_id: str,
    snapshot: RankingSnapshot | None,
    verdict: RankingVerdict | None,
    causes: Sequence[Cause],
) -> CaseRankingScore:
    """Score one case's ranking verdict against its true causes."""
    # Variables:
    #   snapshot: The frozen candidates the model was shown; None when no
    #     ranking question was asked, so no candidate can cover the truth.
    #   verdict: What check_ranking made of the answer; None counts as missing.
    #   causes: The case's true causes (two in the compound challenge); a
    #     pick is right when it names any of them.
    #   candidates: The snapshot's candidates, empty without a snapshot.
    #   covered: Whether any candidate names a true cause, so a wrong ranking
    #     can be blamed on the model rather than on the candidate list.
    #   by_id: The snapshot's candidates by TC id, to look picks up.
    #   picks: The accepted picks' candidates, most plausible first (empty
    #     unless accepted).
    #   right: For each pick, whether it names a true cause.
    candidates = snapshot.candidates if snapshot is not None else ()
    covered = any(names_any(c, causes) for c in candidates)
    if verdict is None:
        return CaseRankingScore(
            scenario_id=scenario_id,
            status=MISSING,
            reason=MISSING,
            valid=False,
            abstained=False,
            top1_correct=False,
            top2_correct=False,
            true_cause_in_candidates=covered,
            candidate_count=len(candidates),
            top1_confidence=None,
        )
    if snapshot is not None and verdict.snapshot_fingerprint != snapshot.fingerprint:
        raise ValueError(f"{scenario_id}: the verdict answers a different snapshot")
    by_id = {c.id: c for c in candidates}
    picks = [by_id[p.candidate_id] for p in verdict.picks]
    right = [names_any(c, causes) for c in picks]
    return CaseRankingScore(
        scenario_id=scenario_id,
        status=verdict.status,
        reason=verdict.reason,
        valid=verdict.status != "rejected",
        abstained=verdict.status == "abstained",
        top1_correct=bool(right) and right[0],
        top2_correct=any(right),
        true_cause_in_candidates=covered,
        candidate_count=len(candidates),
        top1_confidence=verdict.picks[0].confidence if verdict.picks else None,
    )


# The ranking fields a run record's `triage` carries (TriageRecord, part 2).
RECORD_STATUSES = ("accepted", "abstained", "rejected", "unavailable")


def score_record(record: dict, *, covered: bool | None = None) -> CaseRankingScore:
    """Score one experiment record's triage ranking against its true causes.

    Reads the record as written to `*.records.jsonl`: true causes from
    `score.causes`, the ranking from `triage.ranking_status`,
    `triage.ranking_reason` and `triage.ranking_picks` (each pick is
    candidate id, family, machine id or None, confidence; most plausible
    first; empty unless accepted). Coverage comes from the record's
    `triage.deterministic_candidates` (the candidates as triage ended), or
    from `covered` when given; without either it is unknown (None).
    """
    # Variables:
    #   record: One parsed line of a run's records file.
    #   covered: Whether a true cause was among this case's candidates, when
    #     known from elsewhere; it overrides the recorded candidates.
    #   triage: The record's triage summary; None in a record without triage.
    #   causes: The case's true causes, rebuilt from the record's score.
    #   candidates: The recorded (family, machine) of each final candidate;
    #     None in records without them.
    #   status: The recorded ranking outcome; None when no ranking was asked
    #     or the record predates rankings, which scores as missing.
    #   picks: The accepted (family, machine, confidence) picks, best first.
    #   right: For each pick, whether it names a true cause.
    triage = record.get("triage") or {}
    causes = [Cause.model_validate(c) for c in record["score"]["causes"]]
    candidates = (
        [(c["family"], c.get("machine_id")) for c in triage["deterministic_candidates"]]
        if triage.get("deterministic_candidates") is not None
        else None
    )
    if covered is None and candidates is not None:
        covered = any(
            family_names(family, machine_id, cause)
            for family, machine_id in candidates
            for cause in causes
        )
    status = triage.get("ranking_status") if triage.get("ranking") else None
    if status not in RECORD_STATUSES:
        status = None
    picks = [
        (family, machine_id, confidence)
        for _id, family, machine_id, confidence in (
            triage.get("ranking_picks") or () if status == "accepted" else ()
        )
    ]
    right = [
        any(family_names(family, machine_id, cause) for cause in causes)
        for family, machine_id, _ in picks
    ]
    return CaseRankingScore(
        scenario_id=record["scenario_id"],
        status=status or MISSING,
        reason=(triage.get("ranking_reason") or status) if status else MISSING,
        valid=status in ("accepted", "abstained"),
        abstained=status == "abstained",
        top1_correct=bool(right) and right[0],
        top2_correct=any(right),
        true_cause_in_candidates=covered,
        candidate_count=None if candidates is None else len(candidates),
        top1_confidence=picks[0][2] if picks else None,
    )


class RankingAccuracy(BaseModel):
    """Rankings over a set of cases: form, accuracy and (uncalibrated) confidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: int
    accepted: int
    abstained: int
    # Rejected verdicts and missing ones, by reason code ("missing" included).
    invalid_by_reason: dict[str, int]
    validity_rate: float | None
    abstention_rate: float | None
    invalid_rate: float | None
    # Over accepted rankings only, then over every case (abstained, rejected
    # and missing count as not right).
    top1_accuracy_accepted: float | None
    top2_accuracy_accepted: float | None
    top1_accuracy_all: float | None
    top2_accuracy_all: float | None
    # Cases where a true cause was among the candidates at all (over the
    # cases whose coverage is known), and top-2 accuracy over accepted
    # rankings of covered cases only.
    coverage_known: int
    candidate_coverage_rate: float | None
    top2_accuracy_covered: float | None
    # Mean top-pick confidence when the top pick was right, and when wrong.
    mean_confidence_top1_correct: float | None
    mean_confidence_top1_incorrect: float | None
    confidence_note: str = CONFIDENCE_NOTE
    small_sample: bool
    warning: str | None


def _rate(hits: int, total: int) -> float | None:
    """hits / total, or None when there is nothing to divide by."""
    return hits / total if total else None


def _mean(values: Sequence[float]) -> float | None:
    """The mean, or None for no values."""
    return sum(values) / len(values) if values else None


def aggregate(scores: Sequence[CaseRankingScore]) -> RankingAccuracy:
    """Summarise per-case ranking scores into the reported metrics."""
    # Variables:
    #   accepted: The cases whose ranking passed every check; the only ones
    #     whose picks can be right or wrong.
    #   known: Cases whose coverage is known; run records alone do not say.
    #   covered_accepted: Accepted cases whose candidates included a true
    #     cause, so a miss there is the model's, not the candidate list's.
    #   invalid: Reason codes of rejected and missing verdicts, counted.
    #   n: How many cases; the denominator of every "all cases" rate.
    #   small: Fewer than SMALL_SAMPLE_CASES cases, so the warning is set.
    n = len(scores)
    accepted = [s for s in scores if s.status == "accepted"]
    known = [s for s in scores if s.true_cause_in_candidates is not None]
    covered_accepted = [s for s in accepted if s.true_cause_in_candidates is True]
    invalid = Counter(s.reason for s in scores if not s.valid)
    small = n < SMALL_SAMPLE_CASES
    return RankingAccuracy(
        cases=n,
        accepted=len(accepted),
        abstained=sum(s.abstained for s in scores),
        invalid_by_reason=dict(sorted(invalid.items())),
        validity_rate=_rate(sum(s.valid for s in scores), n),
        abstention_rate=_rate(sum(s.abstained for s in scores), n),
        invalid_rate=_rate(sum(not s.valid for s in scores), n),
        top1_accuracy_accepted=_rate(
            sum(s.top1_correct for s in accepted), len(accepted)
        ),
        top2_accuracy_accepted=_rate(
            sum(s.top2_correct for s in accepted), len(accepted)
        ),
        top1_accuracy_all=_rate(sum(s.top1_correct for s in scores), n),
        top2_accuracy_all=_rate(sum(s.top2_correct for s in scores), n),
        coverage_known=len(known),
        candidate_coverage_rate=_rate(
            sum(bool(s.true_cause_in_candidates) for s in known), len(known)
        ),
        top2_accuracy_covered=_rate(
            sum(s.top2_correct for s in covered_accepted), len(covered_accepted)
        ),
        mean_confidence_top1_correct=_mean(
            [s.top1_confidence for s in accepted if s.top1_correct]
        ),
        mean_confidence_top1_incorrect=_mean(
            [s.top1_confidence for s in accepted if not s.top1_correct]
        ),
        small_sample=small,
        warning=(
            f"{n} cases: a functionality check, not an accuracy estimate or a "
            "calibration measurement."
            if small
            else None
        ),
    )
