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
import re
import string
from hashlib import sha256
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from capstone.agent.triage_hypothesize import (
    TRIAGE_HYPOTHESIS_RULE_VERSION,
    CandidateFamily,
    candidate_role,
)
from capstone.contracts import Contract

if TYPE_CHECKING:
    from capstone.agent.state import InvestigationState

# Advance deliberately when the snapshot or answer shape changes.
TRIAGE_RANKING_CONTRACT_VERSION = "1.0"

# Advance when what the model is asked changes, so runs can be compared.
# "2": the model no longer writes missing checks (Python fills them from the
# snapshot), and a correction is shown the conclusion's own context.
# "3": the picks keep the model's own order (no longer re-sorted by
# confidence); an evidence id given both for and against a pick has its own
# reason and correction sentence.
# "4": only cause candidates may be ranked; context candidates (a shared
# machine path, recorded events, load as a symptom) are listed apart as
# context, and naming one is its own rejection. Manual excerpts are said
# to be uncitable.
# "5": each candidate line starts with its bare id in brackets ("[TC1]"),
# the answer schema lists the cause ids as the only allowed candidate_id
# values (an enum: NVIDIA's strict JSON decoding cut "TC1_machine_condition"
# to its 12-character limit, "TC1_machine_"), and a correction is told the
# valid ids.
RANKING_PROMPT_VERSION = "5"

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
    # A pick named a context candidate (from prompt version 4).
    "context_candidate_picked",
    "score_invalid",
    # A cited evidence id the snapshot does not offer.
    "evidence_reference_invalid",
    # One evidence id cited twice for a pick (for and against, or repeated).
    # Before prompt version 3 this was folded into evidence_reference_invalid.
    "evidence_reference_repeated",
    # No longer produced (prompt version 2 stopped asking the model for
    # missing checks); kept so records from earlier runs still load.
    "check_reference_invalid",
    # No ranking to check: the reply left it out, or no reply came.
    "ranking_missing",
    "provider_unavailable",
    "conclusion_deadline_exceeded",
]

# Failures that end without an answer to check: the verdict is "unavailable".
UNAVAILABLE_REASONS = frozenset(
    {"provider_unavailable", "conclusion_deadline_exceeded"}
)

# What each failure is told in the one correction request: a fixed sentence,
# never the model's own text or any evidence content.
CORRECTION_TEXT: dict[str, str] = {
    "candidate_list_empty": "There are no candidates to rank; abstain.",
    "candidate_count_insufficient": (
        "Fewer than two candidate causes exist; abstain instead of ranking."
    ),
    "schema_invalid": "The ranking did not match the required JSON shape.",
    "selection_count_invalid": "A ranking must name exactly two candidates.",
    "duplicate_candidate_id": "The two picks must name two different candidates.",
    "unknown_candidate_id": "Every pick must name a candidate id from the list.",
    "context_candidate_picked": (
        "Pick only from the candidate causes; context candidates are evidence "
        "about where to look, not causes."
    ),
    "score_invalid": "Each confidence must be a number from 0 to 1.",
    "evidence_reference_invalid": (
        "Cite only evidence ids from the list of evidence ids you may cite."
    ),
    "evidence_reference_repeated": (
        "Cite each evidence id at most once per pick: never both for and against it."
    ),
    "ranking_missing": "The answer had no ranking.",
}

# The one shape an id in a rejection detail may have; anything else (prose,
# a long string) is recorded only as a shape summary starting NOT_AN_ID
# ("<not an id: len 4, inner space, starts TC>"), so no model text is kept.
ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:\-]{1,40}$")
NOT_AN_ID = "<not an id"
# Punctuation an id may contain, so it is not reported in a shape summary.
ID_PUNCTUATION = frozenset("_.:-")
# Most distinct punctuation marks one shape summary lists.
MAX_SHAPE_MARKS = 6
# Rejections about which candidate was named: their correction also lists
# the valid ids.
ID_REASONS = frozenset(
    {"unknown_candidate_id", "context_candidate_picked", "duplicate_candidate_id"}
)
# Most offending or named ids one detail keeps.
MAX_DETAIL_IDS = 4

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


class PickFields(Contract):
    """What a pick says: the candidate, the model's belief, its reasons."""

    candidate_id: str = Field(min_length=1, max_length=12)
    # The model's belief that this candidate explains the anomaly: 0 to 1,
    # uncalibrated, and independent of the other pick (the two need not add
    # to 1; causes can coexist). Strict: true/false and "0.5" are refused.
    confidence: float = Field(ge=0, le=1, strict=True)
    rationale: str = Field(min_length=1, max_length=MAX_RATIONALE_CHARS)
    # Observable evidence for the pick, and any against it.
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    contradicting_evidence_ids: tuple[str, ...] = ()


class RankedPick(PickFields):
    """One named candidate as the model answers it.

    The model is not asked which checks are still missing: Python already
    knows (the snapshot's `missing_requirement_ids`) and fills them in on
    acceptance. A reply that still sends `missing_checks` out of habit is
    not punished; the field is dropped unread.
    """

    @model_validator(mode="before")
    @classmethod
    def drop_missing_checks(cls, data):
        """Ignore a `missing_checks` the model was not asked for."""
        # Variables:
        #   data: The raw pick before validation; a copy without the field.
        if isinstance(data, dict) and "missing_checks" in data:
            data = {k: v for k, v in data.items() if k != "missing_checks"}
        return data


class AcceptedPick(PickFields):
    """An accepted pick, with what Python knows about its candidate."""

    # The candidate's own checks still unanswered when the snapshot froze:
    # copied from the snapshot, never written by the model.
    missing_checks: tuple[str, ...] = ()
    # Supporting evidence ids that are offered but are not among this
    # candidate's own related evidence. A diagnostic, not a rejection: a
    # related reading is not proof of support, nor an unrelated one of none.
    unrelated_evidence_ids: tuple[str, ...] = ()


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


def shape_detail(error: ValidationError) -> "RejectionDetail":
    """Where an answer broke the ranking shape: the first error's field path."""
    # Variables:
    #   where: The first error's location, list positions included, as a path.
    where = ".".join(str(part) for part in error.errors()[0]["loc"]) or "ranking"
    return RejectionDetail(field=where[:80])


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


def id_shape(value: object) -> str:
    """A value that is not id-shaped, described by its shape, never its text.

    For example "<not an id: len 4, inner space, starts TC>" for "TC 1". It
    says what kind of mistake the model made without storing model prose.
    """
    # Variables:
    #   marks: What the summary says: length, where any whitespace is,
    #     whether it starts like a TC or E id, and the punctuation used.
    #   stripped: The value without leading and trailing whitespace, to tell
    #     a stray edge space from a space inside.
    #   punct: The distinct ASCII punctuation an id may not contain.
    if not isinstance(value, str):
        return f"{NOT_AN_ID}: {type(value).__name__}>"
    stripped = value.strip()
    marks = [f"len {len(value)}"]
    if stripped != value:
        marks.append("edge space")
    if any(c.isspace() for c in stripped):
        marks.append("inner space")
    if stripped[:2].upper() == "TC":
        marks.append("starts TC")
    elif stripped[:1].upper() == "E" and stripped[1:2].isdigit():
        marks.append("starts E")
    punct = sorted(
        {c for c in value if c in string.punctuation and c not in ID_PUNCTUATION}
    )
    if punct:
        marks.append("punct " + "".join(punct[:MAX_SHAPE_MARKS]))
    if any(ord(c) > 127 for c in value):
        marks.append("non-ascii")
    return f"{NOT_AN_ID}: {', '.join(marks)}>"


def safe_ids(values) -> tuple[str, ...]:
    """Up to MAX_DETAIL_IDS values kept as ids; anything else as its shape."""
    # Variables:
    #   values: Strings the answer gave (candidate or evidence ids, or not).
    return tuple(
        v if isinstance(v, str) and ID_PATTERN.match(v) else id_shape(v)
        for v in list(values)[:MAX_DETAIL_IDS]
    )


class RejectionDetail(Contract):
    """Why one answer was rejected, in ids only: enough to debug, no prose.

    `field` names where the answer broke; `offending_ids` are the values
    there that were wrong; `named_ids` are the candidate ids the answer
    named. Every value passed `safe_ids`, so model prose is never kept.
    """

    field: str = Field(min_length=1, max_length=80)
    offending_ids: tuple[str, ...] = ()
    named_ids: tuple[str, ...] = ()


class RankingVerdict(Contract):
    """What the checks made of one answer; only an accepted verdict has picks."""

    # "unavailable": no answer could be checked (no reply, or no time left).
    status: Literal["accepted", "abstained", "rejected", "unavailable"]
    reason: RankingReason
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{20}$")
    # In the model's own order: it was asked for the most plausible first.
    # (Before prompt version 3 they were re-sorted by confidence.)
    picks: tuple[AcceptedPick, ...] = ()
    # Whether the model's second pick has the higher confidence: its order
    # and its confidences disagree. Only an accepted verdict can say True.
    order_conflicts_confidence: bool = False
    abstain_reason: AbstainReason | None = None
    # Only on a rejected answer that was read: where it broke and the ids.
    detail: RejectionDetail | None = None

    @model_validator(mode="after")
    def picks_match_status(self):
        """Two picks exactly when accepted; a reason that fits the status."""
        # Variables:
        #   expected: The one success reason each non-rejected status must carry.
        expected = {"accepted": "ranking_accepted", "abstained": "ranking_abstained"}
        if self.status in expected and self.reason != expected[self.status]:
            raise ValueError("reason does not match status")
        if self.status == "rejected" and (
            self.reason in expected.values() or self.reason in UNAVAILABLE_REASONS
        ):
            raise ValueError("a rejected verdict needs a checked failure reason")
        if (self.status == "unavailable") != (self.reason in UNAVAILABLE_REASONS):
            raise ValueError("unavailable exactly when no answer could be checked")
        if (len(self.picks) == RANKED_PICKS) != (self.status == "accepted"):
            raise ValueError("only an accepted verdict carries its two picks")
        if (self.abstain_reason is not None) != (self.status == "abstained"):
            raise ValueError("only an abstention carries an abstain reason")
        if self.detail is not None and self.status != "rejected":
            raise ValueError("only a rejected verdict carries a rejection detail")
        if self.order_conflicts_confidence and self.status != "accepted":
            raise ValueError("only an accepted verdict has an order to compare")
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
    #   named: The candidate ids the answer named, kept (as ids only) in any
    #     rejection detail so a failure can be read back later.
    #   picks: The answer's picks in the model's own order (most plausible
    #     first, as asked), each given its candidate's still-missing checks
    #     and the cited support outside the candidate's related evidence,
    #     both from the snapshot (the model is not asked for either).
    #   unseen / repeated: A pick's cited ids the snapshot does not offer, and
    #     those it cites twice; each its own rejection reason.
    #   causes: The ids of the snapshot's candidates whose family names a
    #     possible cause (rankable_ids); only these may be ranked, so fewer
    #     than two cannot be ranked.
    #   context_ids: Picks that named a context candidate (where to look or
    #     what else was seen), which is not an answer to what caused it.
    def rejected(
        reason: RankingReason, detail: RejectionDetail | None = None
    ) -> RankingVerdict:
        return RankingVerdict(
            status="rejected",
            reason=reason,
            snapshot_fingerprint=fingerprint,
            detail=detail,
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
        return rejected(parse_reason(error), shape_detail(error))
    if isinstance(answer, AbstainedAnswer):
        return RankingVerdict(
            status="abstained",
            reason="ranking_abstained",
            snapshot_fingerprint=fingerprint,
            abstain_reason=answer.reason,
        )
    if not snapshot.candidates:
        return rejected("candidate_list_empty")
    causes = rankable_ids(snapshot)
    if len(causes) < RANKED_PICKS:
        return rejected("candidate_count_insufficient")
    ids = [pick.candidate_id for pick in answer.picks]
    named = safe_ids(ids)
    if len(set(ids)) != len(ids):
        return rejected(
            "duplicate_candidate_id",
            RejectionDetail(field="candidate_id", offending_ids=named, named_ids=named),
        )
    known = {c.id: (position, c) for position, c in enumerate(snapshot.candidates)}
    unknown_ids = [cid for cid in ids if cid not in known]
    if unknown_ids:
        return rejected(
            "unknown_candidate_id",
            RejectionDetail(
                field="candidate_id",
                offending_ids=safe_ids(unknown_ids),
                named_ids=named,
            ),
        )
    context_ids = [
        cid for cid in ids if candidate_role(known[cid][1].family) == "context"
    ]
    if context_ids:
        return rejected(
            "context_candidate_picked",
            RejectionDetail(
                field="candidate_id",
                offending_ids=safe_ids(context_ids),
                named_ids=named,
            ),
        )
    offered = set(snapshot.evidence_ids)
    for pick in answer.picks:
        cited = (*pick.evidence_ids, *pick.contradicting_evidence_ids)
        unseen = [e for e in dict.fromkeys(cited) if e not in offered]
        repeated = [e for e in dict.fromkeys(cited) if cited.count(e) > 1]
        for reason, ids in (
            ("evidence_reference_invalid", unseen),
            ("evidence_reference_repeated", repeated),
        ):
            if ids:
                return rejected(
                    reason,
                    RejectionDetail(
                        field=f"{pick.candidate_id}.evidence",
                        offending_ids=safe_ids(ids),
                        named_ids=named,
                    ),
                )
    picks = tuple(
        AcceptedPick(
            **pick.model_dump(),
            missing_checks=known[pick.candidate_id][1].missing_requirement_ids,
            unrelated_evidence_ids=tuple(
                e
                for e in pick.evidence_ids
                if e not in known[pick.candidate_id][1].observation_evidence_ids
            ),
        )
        for pick in answer.picks
    )
    return RankingVerdict(
        status="accepted",
        reason="ranking_accepted",
        snapshot_fingerprint=fingerprint,
        picks=picks,
        order_conflicts_confidence=picks[1].confidence > picks[0].confidence,
    )


def unavailable(snapshot: RankingSnapshot, reason: RankingReason) -> RankingVerdict:
    """The verdict when no answer could be checked: no reply, or no time left."""
    return RankingVerdict(
        status="unavailable", reason=reason, snapshot_fingerprint=snapshot.fingerprint
    )


def judge_reply(
    snapshot: RankingSnapshot, raw: object, *, current_fingerprint: str
) -> RankingVerdict:
    """Check a ranking as it came in a reply: raw JSON, possibly missing or malformed."""
    # Variables:
    #   raw: The reply's "ranking" value exactly as parsed from JSON, never
    #     trusted: None when the reply left it out.
    #   parsed: The value validated into a ranked or abstained answer.
    if raw is None:
        return RankingVerdict(
            status="rejected",
            reason="ranking_missing",
            snapshot_fingerprint=snapshot.fingerprint,
        )
    try:
        parsed = RankingAnswer.model_validate({"ranking": raw}).ranking
    except ValidationError as error:
        return RankingVerdict(
            status="rejected",
            reason=parse_reason(error),
            snapshot_fingerprint=snapshot.fingerprint,
            detail=shape_detail(error),
        )
    return check_ranking(snapshot, parsed, current_fingerprint=current_fingerprint)


def rankable_ids(snapshot: RankingSnapshot) -> tuple[str, ...]:
    """The ids a ranking may name: the cause candidates', in snapshot order."""
    return tuple(
        c.id for c in snapshot.candidates if candidate_role(c.family) == "cause"
    )


def correction_text(
    reason: str,
    detail: RejectionDetail | None = None,
    valid_ids: tuple[str, ...] = (),
) -> str:
    """What a correction is told: the fixed sentence, then the offending ids."""
    # Variables:
    #   reason: The rejection code, turned into its fixed CORRECTION_TEXT.
    #   detail: Where the rejected answer broke and which ids were wrong;
    #     ids only, so echoing them back never repeats model prose.
    #   valid_ids: The ids a pick may name, listed after a candidate-id
    #     failure so the correction is told what a right answer looks like.
    text = CORRECTION_TEXT.get(reason, "It did not match the contract.")
    if detail is not None:
        text += f" Problem at {detail.field}"
        if detail.offending_ids:
            text += f": {', '.join(detail.offending_ids)}"
        text += "."
    if valid_ids and reason in ID_REASONS:
        text += f" Valid candidate ids: {', '.join(valid_ids)}."
    return text


def candidate_line(c: SnapshotCandidate) -> str:
    """One snapshot candidate as a prompt line."""
    return (
        f"- [{c.id}] {c.family}"
        + (f" on {c.machine_id}" if c.machine_id else "")
        + f": {c.explanation}; related evidence "
        f"{', '.join(c.observation_evidence_ids) or 'none'}; checks "
        f"{', '.join(c.discriminating_requirement_ids) or 'none'}; still "
        f"missing {', '.join(c.missing_requirement_ids) or 'none'}."
    )


def ranking_view(snapshot: RankingSnapshot) -> list[str]:
    """The snapshot as prompt lines: causes to rank, context, citable evidence."""
    # Variables:
    #   causes / context: The snapshot's candidates split by their family's
    #     role, each kept in snapshot order; only causes may be ranked.
    #   lines: The cause lines, then the context lines (if any), then the
    #     evidence ids a pick may cite.
    causes = [c for c in snapshot.candidates if c.id in rankable_ids(snapshot)]
    context = [c for c in snapshot.candidates if candidate_role(c.family) == "context"]
    lines = ["CANDIDATE CAUSES TO RANK (unscored; fixed rules, not diagnoses):"]
    lines.extend(candidate_line(c) for c in causes)
    if not causes:
        lines.append("- none")
    if context:
        lines.append(
            "CONTEXT (where to look or what else was seen; use it as evidence, "
            "never rank it as a cause):"
        )
        lines.extend(candidate_line(c) for c in context)
    lines.append(
        "Evidence ids you may cite: "
        + (", ".join(snapshot.evidence_ids) or "none")
        + " (factory observations only; manual excerpts and memories are not "
        "citable)."
    )
    return lines


RANKING_INSTRUCTIONS = (
    'Also fill "ranking": either kind "ranked" naming exactly two different '
    "candidate cause ids (never a context id), each exactly the bracketed "
    'id with nothing added (for example "TC2"), most plausible first, each '
    "with your own "
    "confidence from 0 to 1 (independent: the two need not add to 1, and they "
    "are beliefs, not measured probabilities), a short rationale, the evidence "
    "ids that support it (at least one) and any against it, copied exactly "
    'from the list; or kind "abstained" when the evidence cannot support two '
    "defensible causes. Do not list missing checks: they are filled in from "
    "the candidate list. Never invent a candidate or an evidence id. "
    "The ranking never changes what may be done to a machine."
)


def ranking_schema(candidate_ids: tuple[str, ...] = ()) -> dict:
    """The ranking's JSON schema with every reference written out in place.

    The conclusion reply carries the ranking as a loosely typed field (so a
    bad ranking never costs the conclusion), but the model must still be
    shown the full shape: this is that shape, self-contained, with `anyOf`
    for the two kinds.
    """
    # Variables:
    #   candidate_ids: When given, the only values a pick's candidate_id may
    #     take (an enum). A service that enforces the schema while decoding
    #     (NVIDIA) then cannot produce any other id; the reply is still
    #     judged by check_ranking as before.
    #   full: The union's schema with its shared definitions under "$defs".
    #   defs: Those definitions, by name, substituted wherever referenced.
    full = TypeAdapter(CandidateRanking).json_schema()
    defs = full.pop("$defs", {})

    def inline(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(defs[node["$ref"].rsplit("/", 1)[-1]])
            node = {k: inline(v) for k, v in node.items() if k != "discriminator"}
            if "oneOf" in node:
                node["anyOf"] = node.pop("oneOf")
            return node
        if isinstance(node, list):
            return [inline(item) for item in node]
        return node

    schema = inline(full)
    if candidate_ids:
        for kind in schema["anyOf"]:
            picks = kind.get("properties", {}).get("picks")
            if picks is not None:
                picks["items"]["properties"]["candidate_id"]["enum"] = list(
                    candidate_ids
                )
    return schema
