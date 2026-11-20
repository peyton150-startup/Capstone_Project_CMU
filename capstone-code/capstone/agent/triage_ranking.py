"""The two-candidate ranking a triage conclusion may give, and its checks.

After deterministic triage compiles its candidates (TC1, TC2, ...: cause
families on a machine, never physical parts and never diagnoses), the
conclusion model may name the two it finds most plausible, each with its own
uncalibrated confidence, or abstain. Nothing here asks a model or changes a
run: this module freezes what the model will be shown (`RankingSnapshot`),
defines the answer's shape (`CandidateRanking`) and checks an answer against
the snapshot (`check_ranking`), returning one fixed reason code.

Why a frozen snapshot: TC numbers are given out by position when the
candidates are compiled, so a recompiled list can give "TC2" a different
explanation. An answer is only read against the exact list the model saw, and
a changed list (a different fingerprint) rejects the answer as stale instead
of reinterpreting it.
"""

import json
from hashlib import sha256
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from capstone.agent.triage_hypothesize import (
    TRIAGE_HYPOTHESIS_RULE_VERSION,
    CandidateFamily,
)
from capstone.contracts import Contract

if TYPE_CHECKING:
    from capstone.agent.state import InvestigationState

# Advance deliberately when the snapshot or answer shape changes.
TRIAGE_RANKING_CONTRACT_VERSION = "1.0"

# How many candidates a ranking names. Two, as the developer asked
# (2026-11-20): the most plausible and the runner-up.
RANKED_PICKS = 2

# Longest rationale kept per pick: a short reason, not an essay.
MAX_RATIONALE_CHARS = 300

# Every outcome of checking one answer. "ranking_accepted" and
# "ranking_abstained" are the two successes; the rest name exactly what was
# wrong, so a failed run says more than "invalid reply".
RankingReason = Literal[
    "ranking_accepted",
    "ranking_abstained",
    "candidate_list_empty",
    "candidate_count_insufficient",
    "candidate_snapshot_stale",
    "schema_invalid",
    "selection_count_invalid",
    "duplicate_candidate_id",
    "unknown_candidate_id",
    "score_invalid",
    "evidence_reference_invalid",
    "check_reference_invalid",
]

# Why a model may decline to rank.
AbstainReason = Literal["evidence_insufficient", "candidates_indistinguishable"]


# --- the snapshot: exactly what the model is shown --------------------------------


class SnapshotCandidate(Contract):
    """One candidate as the model saw it."""

    id: str = Field(pattern=r"^TC[1-9][0-9]*$")
    family: CandidateFamily
    explanation: str = Field(min_length=1)
    machine_id: str | None = None
    observation_evidence_ids: tuple[str, ...] = ()
    discriminating_requirement_ids: tuple[str, ...] = ()
    missing_requirement_ids: tuple[str, ...] = ()
    unavailable_requirement_ids: tuple[str, ...] = ()


def snapshot_fingerprint(body: dict) -> str:
    """A 20-character hash of a snapshot's content, from canonical JSON."""
    # Variables:
    #   body: Every snapshot field except the fingerprint itself.
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()[:20]


class RankingSnapshot(Contract):
    """The candidates and evidence one ranking question offers, frozen.

    The fingerprint is checked on every validation, so a copy whose content
    was changed without validation (`model_copy(update=...)`) is caught the
    next time it crosses a boundary and is revalidated.
    """

    contract_version: Literal["1.0"] = TRIAGE_RANKING_CONTRACT_VERSION
    rule_version: str = Field(min_length=1)
    source_cutoff_tick: int | None = Field(default=None, ge=0)
    candidates: tuple[SnapshotCandidate, ...] = ()
    # The factory evidence a pick may cite: observable, at or before the cutoff.
    evidence_ids: tuple[str, ...] = ()
    fingerprint: str = Field(pattern=r"^[0-9a-f]{20}$")

    @model_validator(mode="after")
    def consistent(self):
        """Unique ids, candidate evidence offered, and a fingerprint that matches."""
        # Variables:
        #   ids: The candidates' ids, which must not repeat.
        #   offered: The evidence ids a pick may cite.
        ids = [candidate.id for candidate in self.candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("snapshot candidate ids must not repeat")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("snapshot evidence ids must not repeat")
        offered = set(self.evidence_ids)
        for candidate in self.candidates:
            if not set(candidate.observation_evidence_ids) <= offered:
                raise ValueError("candidate evidence is not in the snapshot")
        if self.fingerprint != snapshot_fingerprint(
            self.model_dump(mode="json", exclude={"fingerprint"})
        ):
            raise ValueError("snapshot fingerprint does not match its content")
        return self


def ranking_snapshot(state: "InvestigationState") -> RankingSnapshot:
    """Freeze the current candidates and citable evidence for one ranking question."""
    # Variables:
    #   cutoff: The evidence horizon fixed when triage began; later evidence
    #     cannot be cited.
    #   observable: Evidence ids whose provenance is the factory itself.
    #   evidence_ids: Factory-observable evidence at or before the cutoff, in
    #     the order it was gathered; manual text and memories are left out.
    #   body: The snapshot's content, hashed into its fingerprint.
    cutoff = state.triage_observation_cutoff_tick
    observable = {p.evidence_id for p in state.provenance if p.origin == "observable"}
    evidence_ids = tuple(
        dict.fromkeys(
            e.id
            for e in state.evidence
            if e.id in observable and (cutoff is None or e.observed_tick <= cutoff)
        )
    )
    body = {
        "contract_version": TRIAGE_RANKING_CONTRACT_VERSION,
        "rule_version": TRIAGE_HYPOTHESIS_RULE_VERSION,
        "source_cutoff_tick": cutoff,
        "candidates": [
            SnapshotCandidate(
                id=c.id,
                family=c.family,
                explanation=c.explanation,
                machine_id=c.machine_id,
                observation_evidence_ids=tuple(
                    e for e in c.observation_evidence_ids if e in evidence_ids
                ),
                discriminating_requirement_ids=c.discriminating_requirement_ids,
                missing_requirement_ids=c.missing_requirement_ids,
                unavailable_requirement_ids=c.unavailable_requirement_ids,
            ).model_dump(mode="json")
            for c in state.triage_candidates
        ],
        "evidence_ids": list(evidence_ids),
    }
    return RankingSnapshot.model_validate(
        {**body, "fingerprint": snapshot_fingerprint(body)}
    )


# --- the answer the model gives ------------------------------------------------------


class RankedPick(Contract):
    """One named candidate, with the model's own confidence in it."""

    candidate_id: str = Field(min_length=1, max_length=12)
    # The model's belief that this candidate explains the anomaly: 0 to 1,
    # uncalibrated, and independent of the other pick (the two need not add
    # to 1; causes can coexist). Strict: true/false and "0.5" are refused.
    confidence: float = Field(ge=0, le=1, strict=True)
    rationale: str = Field(min_length=1, max_length=MAX_RATIONALE_CHARS)
    # Observable evidence for the pick, and any against it.
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    contradicting_evidence_ids: tuple[str, ...] = ()
    # The candidate's own checks that would still separate it from the other.
    missing_checks: tuple[str, ...] = ()


class RankedAnswer(Contract):
    """Exactly two candidates, most plausible first."""

    kind: Literal["ranked"] = "ranked"
    picks: tuple[RankedPick, ...] = Field(
        min_length=RANKED_PICKS, max_length=RANKED_PICKS
    )


class AbstainedAnswer(Contract):
    """No ranking: the evidence cannot support two defensible picks."""

    kind: Literal["abstained"] = "abstained"
    reason: AbstainReason
    missing_checks: tuple[str, ...] = ()


CandidateRanking = Annotated[
    RankedAnswer | AbstainedAnswer, Field(discriminator="kind")
]


class RankingAnswer(Contract):
    """The ranking field as a model is asked for it."""

    ranking: CandidateRanking


def parse_reason(error: ValidationError) -> RankingReason:
    """Name what was wrong with an answer that did not fit the ranking shape."""
    # Variables:
    #   first: The first validation error; its location says which field broke.
    #   where: That location's field names, without list positions.
    first = error.errors()[0]
    where = [str(part) for part in first["loc"] if not isinstance(part, int)]
    if "confidence" in where:
        return "score_invalid"
    if where and where[-1] == "picks" and first["type"] in ("too_short", "too_long"):
        return "selection_count_invalid"
    return "schema_invalid"


# --- the check ------------------------------------------------------------------------


class RankingVerdict(Contract):
    """What the checks made of one answer; only an accepted verdict has picks."""

    status: Literal["accepted", "abstained", "rejected"]
    reason: RankingReason
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{20}$")
    # Most plausible first: by the model's confidence, ties in snapshot order.
    picks: tuple[RankedPick, ...] = ()
    abstain_reason: AbstainReason | None = None

    @model_validator(mode="after")
    def picks_match_status(self):
        """Two picks exactly when accepted; a reason that fits the status."""
        # Variables:
        #   expected: The one success reason each non-rejected status must carry.
        expected = {"accepted": "ranking_accepted", "abstained": "ranking_abstained"}
        if self.status in expected and self.reason != expected[self.status]:
            raise ValueError("reason does not match status")
        if self.status == "rejected" and self.reason in expected.values():
            raise ValueError("a rejected verdict needs a failure reason")
        if (len(self.picks) == RANKED_PICKS) != (self.status == "accepted"):
            raise ValueError("only an accepted verdict carries its two picks")
        if (self.abstain_reason is not None) != (self.status == "abstained"):
            raise ValueError("only an abstention carries an abstain reason")
        return self


def check_ranking(
    snapshot: RankingSnapshot,
    answer: RankedAnswer | AbstainedAnswer,
    *,
    current_fingerprint: str,
) -> RankingVerdict:
    """Accept, record an abstention, or reject an answer, with one fixed reason.

    Python never picks or repairs: an answer with any fault is rejected
    whole, and the caller decides whether to ask once more.
    """

    # Variables:
    #   current_fingerprint: The fingerprint of the candidates as they stand
    #     when the answer arrives; a difference means the list changed since
    #     the model saw it, so its TC ids may mean something else now.
    #   known: The snapshot's candidates by id, with their position for ties.
    #   offered: The evidence ids a pick may cite.
    #   fingerprint: The snapshot's own fingerprint, recorded on every verdict
    #     so a verdict can be joined to the question it answers.
    #   answer: Re-validated before use, since a copy may have skipped validation.
    #   picks: The answer's picks, most plausible first.
    def rejected(reason: RankingReason) -> RankingVerdict:
        return RankingVerdict(
            status="rejected", reason=reason, snapshot_fingerprint=fingerprint
        )

    fingerprint = snapshot.fingerprint
    try:
        # Both may have been copied without validation (`model_copy`):
        # revalidate before anything is trusted.
        snapshot = RankingSnapshot.model_validate(snapshot.model_dump())
    except ValidationError:
        return rejected("candidate_snapshot_stale")
    if current_fingerprint != snapshot.fingerprint:
        return rejected("candidate_snapshot_stale")
    try:
        answer = RankingAnswer.model_validate({"ranking": answer.model_dump()}).ranking
    except ValidationError as error:
        return rejected(parse_reason(error))
    if isinstance(answer, AbstainedAnswer):
        return RankingVerdict(
            status="abstained",
            reason="ranking_abstained",
            snapshot_fingerprint=fingerprint,
            abstain_reason=answer.reason,
        )
    if not snapshot.candidates:
        return rejected("candidate_list_empty")
    if len(snapshot.candidates) < RANKED_PICKS:
        return rejected("candidate_count_insufficient")
    ids = [pick.candidate_id for pick in answer.picks]
    if len(set(ids)) != len(ids):
        return rejected("duplicate_candidate_id")
    known = {c.id: (position, c) for position, c in enumerate(snapshot.candidates)}
    if any(cid not in known for cid in ids):
        return rejected("unknown_candidate_id")
    offered = set(snapshot.evidence_ids)
    for pick in answer.picks:
        cited = (*pick.evidence_ids, *pick.contradicting_evidence_ids)
        if not set(cited) <= offered or len(set(cited)) != len(cited):
            return rejected("evidence_reference_invalid")
        candidate = known[pick.candidate_id][1]
        if not set(pick.missing_checks) <= set(
            candidate.discriminating_requirement_ids
        ):
            return rejected("check_reference_invalid")
    picks = tuple(
        sorted(
            answer.picks,
            key=lambda pick: (-pick.confidence, known[pick.candidate_id][0]),
        )
    )
    return RankingVerdict(
        status="accepted",
        reason="ranking_accepted",
        snapshot_fingerprint=fingerprint,
        picks=picks,
    )
