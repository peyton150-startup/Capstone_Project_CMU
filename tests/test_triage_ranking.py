"""The two-candidate ranking contract, its frozen snapshot and its checks.

No model is asked: these tests build snapshots by hand or from a real triage
run with a scripted conclusion, then check hand-written answers.
"""

from typing import get_args

import pytest
from pydantic import ValidationError

from capstone.agent.triage_hypothesize import (
    FAMILY_ROLES,
    CandidateFamily,
    candidate_role,
)
from capstone.agent.triage_ranking import (
    NOT_AN_ID,
    RANKING_INSTRUCTIONS,
    AbstainedAnswer,
    RankedAnswer,
    RankedPick,
    RankingAnswer,
    RankingSnapshot,
    RankingVerdict,
    RejectionDetail,
    check_ranking,
    correction_text,
    id_shape,
    judge_reply,
    parse_reason,
    ranking_schema,
    ranking_snapshot,
    ranking_view,
    snapshot_fingerprint,
)


def snapshot(candidates=("machine_condition", "setting_shift", "sensor_or_transient")):
    """A snapshot of up to three candidates over evidence E1-E4."""
    body = {
        "contract_version": "1.0",
        "rule_version": "1.2",
        "source_cutoff_tick": 900,
        "candidates": [
            {
                "id": f"TC{n}",
                "family": family,
                "explanation": f"{family} explanation",
                "machine_id": "CNC-02",
                "observation_evidence_ids": [f"E{n}"],
                "discriminating_requirement_ids": [f"Q{n}:check"],
                "missing_requirement_ids": [],
                "unavailable_requirement_ids": [],
            }
            for n, family in enumerate(candidates, start=1)
        ],
        "evidence_ids": ["E1", "E2", "E3", "E4"],
    }
    return RankingSnapshot.model_validate(
        {**body, "fingerprint": snapshot_fingerprint(body)}
    )


def pick(cid, confidence, evidence=("E1",), **extra):
    return RankedPick(
        candidate_id=cid,
        confidence=confidence,
        rationale="because",
        evidence_ids=evidence,
        **extra,
    )


def ranked(*picks):
    return RankedAnswer(picks=picks)


def check(answer, snap=None, current=None):
    snap = snap or snapshot()
    return check_ranking(snap, answer, current_fingerprint=current or snap.fingerprint)


# --- the snapshot -----------------------------------------------------------------


def test_the_fingerprint_is_stable_and_follows_the_content():
    assert snapshot().fingerprint == snapshot().fingerprint
    reordered = snapshot(("setting_shift", "machine_condition", "sensor_or_transient"))
    assert reordered.fingerprint != snapshot().fingerprint


def test_a_snapshot_changed_without_validation_is_refused_when_revalidated():
    snap = snapshot()
    forged = snap.model_copy(update={"evidence_ids": ("E1", "E2", "E3", "E4", "E9")})
    with pytest.raises(ValidationError, match="fingerprint does not match"):
        RankingSnapshot.model_validate(forged.model_dump())


def test_a_snapshot_rejects_repeated_ids_and_unoffered_candidate_evidence():
    body = snapshot().model_dump(mode="json", exclude={"fingerprint"})
    body["candidates"][1]["id"] = "TC1"
    with pytest.raises(ValidationError, match="must not repeat"):
        RankingSnapshot.model_validate(
            {**body, "fingerprint": snapshot_fingerprint(body)}
        )
    body = snapshot().model_dump(mode="json", exclude={"fingerprint"})
    body["candidates"][0]["observation_evidence_ids"] = ["E7"]
    with pytest.raises(ValidationError, match="not in the snapshot"):
        RankingSnapshot.model_validate(
            {**body, "fingerprint": snapshot_fingerprint(body)}
        )


# --- accepted and abstained ----------------------------------------------------------


def test_two_valid_picks_are_accepted_in_the_models_own_order():
    verdict = check(ranked(pick("TC2", 0.7, ("E2", "E3")), pick("TC1", 0.2)))
    assert verdict.status == "accepted" and verdict.reason == "ranking_accepted"
    assert [p.candidate_id for p in verdict.picks] == ["TC2", "TC1"]
    assert verdict.order_conflicts_confidence is False
    assert verdict.snapshot_fingerprint == snapshot().fingerprint


def test_a_less_confident_first_pick_keeps_its_place_and_is_flagged():
    # The model was asked for the most plausible first; Python no longer
    # re-sorts by confidence, so top-1 is the model's own first choice.
    verdict = check(ranked(pick("TC1", 0.2), pick("TC2", 0.7, ("E2", "E3"))))
    assert [p.candidate_id for p in verdict.picks] == ["TC1", "TC2"]
    assert verdict.order_conflicts_confidence is True


def test_confidences_need_not_add_to_one_and_ties_are_no_conflict():
    verdict = check(ranked(pick("TC3", 0.9), pick("TC1", 0.9)))
    assert verdict.status == "accepted"
    assert [p.candidate_id for p in verdict.picks] == ["TC3", "TC1"]
    assert verdict.order_conflicts_confidence is False


def test_only_an_accepted_verdict_may_flag_an_order_conflict():
    with pytest.raises(ValidationError, match="order to compare"):
        RankingVerdict(
            status="rejected",
            reason="unknown_candidate_id",
            snapshot_fingerprint="0" * 20,
            order_conflicts_confidence=True,
        )


def test_support_outside_the_candidates_related_evidence_is_recorded_not_rejected():
    # TC1's related evidence is E1; citing E3 for it is valid but unrelated.
    verdict = check(ranked(pick("TC1", 0.7, ("E1", "E3")), pick("TC2", 0.3, ("E2",))))
    assert verdict.status == "accepted"
    assert verdict.picks[0].unrelated_evidence_ids == ("E3",)
    assert verdict.picks[1].unrelated_evidence_ids == ()


def test_an_abstention_is_a_valid_outcome_without_picks():
    verdict = check(AbstainedAnswer(reason="evidence_insufficient"))
    assert verdict.status == "abstained" and verdict.reason == "ranking_abstained"
    assert verdict.picks == () and verdict.abstain_reason == "evidence_insufficient"


# --- rejected, each with its own reason -----------------------------------------------


def test_a_changed_candidate_list_rejects_the_answer_as_stale():
    later = snapshot(("setting_shift", "machine_condition", "sensor_or_transient"))
    verdict = check(
        ranked(pick("TC1", 0.7), pick("TC2", 0.2)), current=later.fingerprint
    )
    assert verdict.status == "rejected"
    assert verdict.reason == "candidate_snapshot_stale"
    assert verdict.picks == ()


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (ranked(pick("TC2", 0.7), pick("TC2", 0.3)), "duplicate_candidate_id"),
        (ranked(pick("TC2", 0.7), pick("TC9", 0.3)), "unknown_candidate_id"),
        (
            ranked(pick("TC2", 0.7), pick("TC1", 0.3, ("E9",))),
            "evidence_reference_invalid",
        ),
        (
            ranked(
                pick("TC2", 0.7), pick("TC1", 0.3, contradicting_evidence_ids=("E1",))
            ),
            "evidence_reference_repeated",
        ),
    ],
)
def test_each_fault_in_an_answer_has_its_own_reason(answer, reason):
    verdict = check(answer)
    assert verdict.status == "rejected" and verdict.reason == reason
    assert verdict.detail is not None


# --- missing checks come from Python, not the model (prompt version 2) -------------


def test_missing_checks_the_model_sends_are_ignored_and_filled_from_the_snapshot():
    body = snapshot().model_dump(mode="json", exclude={"fingerprint"})
    body["candidates"][0]["missing_requirement_ids"] = ["Q1:check"]
    snap = RankingSnapshot.model_validate(
        {**body, "fingerprint": snapshot_fingerprint(body)}
    )
    raw = {
        "kind": "ranked",
        "picks": [
            {
                "candidate_id": "TC1",
                "confidence": 0.7,
                "rationale": "r",
                "evidence_ids": ["E1"],
                # Not asked for, and not an id the candidate lists: no harm.
                "missing_checks": ["check the spindle", "Q9:made_up"],
            },
            {
                "candidate_id": "TC2",
                "confidence": 0.3,
                "rationale": "r",
                "evidence_ids": ["E2"],
            },
        ],
    }
    verdict = judge_reply(snap, raw, current_fingerprint=snap.fingerprint)
    assert verdict.status == "accepted"
    assert verdict.picks[0].missing_checks == ("Q1:check",)
    assert verdict.picks[1].missing_checks == ()


def test_the_schema_the_model_sees_no_longer_asks_for_missing_checks():
    ranked_schema = next(
        s for s in ranking_schema()["anyOf"] if "picks" in s.get("properties", {})
    )
    assert (
        "missing_checks"
        not in ranked_schema["properties"]["picks"]["items"]["properties"]
    )
    assert "Do not list missing checks" in RANKING_INSTRUCTIONS


# --- a rejection keeps where it broke and the wrong ids, never prose ---------------


def test_an_unknown_candidate_is_recorded_with_its_id_and_the_ids_named():
    verdict = check(ranked(pick("TC2", 0.7), pick("TC9", 0.3)))
    assert verdict.detail == RejectionDetail(
        field="candidate_id", offending_ids=("TC9",), named_ids=("TC2", "TC9")
    )
    assert correction_text(verdict.reason, verdict.detail).endswith(
        "Problem at candidate_id: TC9."
    )


def test_unoffered_and_repeated_evidence_are_told_apart():
    unseen = check(ranked(pick("TC2", 0.7), pick("TC1", 0.3, ("E9",))))
    assert unseen.reason == "evidence_reference_invalid"
    assert (unseen.detail.field, unseen.detail.offending_ids) == (
        "TC1.evidence",
        ("E9",),
    )
    both = check(
        ranked(pick("TC2", 0.7), pick("TC1", 0.3, contradicting_evidence_ids=("E1",)))
    )
    assert both.reason == "evidence_reference_repeated"
    assert both.detail.offending_ids == ("E1",)
    assert "never both for and against" in correction_text(both.reason, both.detail)
    # An answer with both faults is named for the unoffered id first.
    mixed = check(
        ranked(
            pick("TC2", 0.7),
            pick("TC1", 0.3, ("E9",), contradicting_evidence_ids=("E9",)),
        )
    )
    assert mixed.reason == "evidence_reference_invalid"


def test_prose_in_an_id_field_is_never_kept():
    verdict = check(
        ranked(pick("TC2", 0.7), pick("TC1", 0.3, ("the spindle bearing is worn",)))
    )
    (shape,) = verdict.detail.offending_ids
    assert shape.startswith(NOT_AN_ID) and "inner space" in shape
    assert "spindle" not in str(verdict.model_dump())


@pytest.mark.parametrize(
    ("value", "shape"),
    [
        ("TC 1", "<not an id: len 4, inner space, starts TC>"),
        ("TC1 ", "<not an id: len 4, edge space, starts TC>"),
        ("#TC1", "<not an id: len 4, punct #>"),
        ("TC1,TC2", "<not an id: len 7, starts TC, punct ,>"),
        ("E5)", "<not an id: len 3, starts E, punct )>"),
        ("TC\u00b71", "<not an id: len 4, starts TC, non-ascii>"),
        (3, "<not an id: int>"),
    ],
)
def test_a_value_that_is_not_an_id_is_kept_only_as_its_shape(value, shape):
    assert id_shape(value) == shape


def test_a_short_malformed_candidate_id_reaches_the_unknown_check_with_its_shape():
    # Under the 12-character limit, so not a shape error: the six
    # "<not an id>" rejections of 2026-11-21 were values like this.
    verdict = check(ranked(pick("TC 1", 0.7), pick("TC 2", 0.3, ("E2",))))
    assert verdict.reason == "unknown_candidate_id"
    assert (
        verdict.detail.offending_ids
        == ("<not an id: len 4, inner space, starts TC>",) * 2
    )


def test_a_shape_error_is_recorded_with_its_field_path():
    snap = snapshot()
    verdict = judge_reply(
        snap,
        {"kind": "ranked", "picks": [{"candidate_id": "TC1"}] * 2},
        current_fingerprint=snap.fingerprint,
    )
    assert verdict.reason == "score_invalid"
    assert verdict.detail.field == "ranking.ranked.picks.0.confidence"


def test_only_a_rejected_verdict_may_carry_a_detail():
    with pytest.raises(ValidationError, match="rejection detail"):
        RankingVerdict(
            status="abstained",
            reason="ranking_abstained",
            snapshot_fingerprint="0" * 20,
            abstain_reason="evidence_insufficient",
            detail=RejectionDetail(field="x"),
        )


# --- causes are ranked; context is shown apart (prompt version 4) ------------------


def test_every_family_is_a_cause_or_context():
    assert set(FAMILY_ROLES) == set(get_args(CandidateFamily))
    assert candidate_role("common_machine_path") == "context"
    assert candidate_role("common_material_batch") == "cause"


def test_picking_a_context_candidate_is_its_own_rejection():
    snap = snapshot(("common_machine_path", "common_material_batch", "setting_shift"))
    verdict = check(ranked(pick("TC1", 0.7), pick("TC2", 0.4, ("E2",))), snap)
    assert verdict.reason == "context_candidate_picked"
    assert verdict.detail == RejectionDetail(
        field="candidate_id", offending_ids=("TC1",), named_ids=("TC1", "TC2")
    )
    assert "context candidates are evidence" in correction_text(
        verdict.reason, verdict.detail
    )
    causes_only = check(ranked(pick("TC2", 0.7, ("E2",)), pick("TC3", 0.4)), snap)
    assert causes_only.status == "accepted"


def test_fewer_than_two_causes_cannot_be_ranked_whatever_the_context():
    snap = snapshot(("common_machine_path", "preceding_events", "setting_shift"))
    verdict = check(ranked(pick("TC3", 0.7), pick("TC1", 0.4)), snap)
    assert verdict.reason == "candidate_count_insufficient"
    abstained = check(AbstainedAnswer(reason="evidence_insufficient"), snap)
    assert abstained.status == "abstained"


def test_the_view_lists_causes_to_rank_then_context_then_citable_evidence():
    snap = snapshot(("common_machine_path", "common_material_batch", "setting_shift"))
    lines = ranking_view(snap)
    assert lines[0].startswith("CANDIDATE CAUSES TO RANK")
    assert [line[:7] for line in lines[1:3]] == ["- [TC2]", "- [TC3]"]
    assert lines[3].startswith("CONTEXT") and "never rank it" in lines[3]
    assert lines[4].startswith("- [TC1] common_machine_path")
    assert "manual excerpts and memories are not citable" in lines[5]
    assert "never a context id" in RANKING_INSTRUCTIONS


def test_too_few_candidates_cannot_be_ranked_but_can_be_abstained_on():
    one = snapshot(("machine_condition",))
    assert check(ranked(pick("TC1", 0.7), pick("TC2", 0.2)), one).reason == (
        "candidate_count_insufficient"
    )
    empty = snapshot(())
    assert check(ranked(pick("TC1", 0.7), pick("TC2", 0.2)), empty).reason == (
        "candidate_list_empty"
    )
    assert check(AbstainedAnswer(reason="evidence_insufficient"), empty).status == (
        "abstained"
    )


def test_an_answer_forged_past_validation_is_rejected_not_trusted():
    good = ranked(pick("TC1", 0.7), pick("TC2", 0.2))
    forged = good.model_copy(update={"picks": (pick("TC1", 0.7),)})
    assert check(forged).reason == "selection_count_invalid"
    bad_score = pick("TC2", 0.2).model_copy(update={"confidence": 1.5})
    assert check(ranked(pick("TC1", 0.7), bad_score)).reason == "score_invalid"


# --- parsing a model's raw reply ----------------------------------------------------


def raw(picks):
    return {"ranking": {"kind": "ranked", "picks": picks}}


def raw_pick(cid="TC1", confidence=0.5):
    return {
        "candidate_id": cid,
        "confidence": confidence,
        "rationale": "r",
        "evidence_ids": ["E1"],
    }


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        (
            raw([raw_pick(), raw_pick("TC2"), raw_pick("TC3")]),
            "selection_count_invalid",
        ),
        (raw([raw_pick()]), "selection_count_invalid"),
        (raw([raw_pick(), raw_pick("TC2", True)]), "score_invalid"),
        (raw([raw_pick(), raw_pick("TC2", "0.5")]), "score_invalid"),
        (raw([raw_pick(), raw_pick("TC2", 1.2)]), "score_invalid"),
        ({"ranking": {"kind": "guess"}}, "schema_invalid"),
        (raw([raw_pick(), {**raw_pick("TC2"), "secret": 1}]), "schema_invalid"),
    ],
)
def test_a_reply_that_breaks_the_shape_is_named_precisely(reply, reason):
    with pytest.raises(ValidationError) as error:
        RankingAnswer.model_validate(reply)
    assert parse_reason(error.value) == reason


def test_nan_and_infinity_are_refused_in_a_json_reply():
    reply = '{"ranking": {"kind": "ranked", "picks": [%s, %s]}}'
    good = '{"candidate_id": "TC1", "confidence": 0.5, "rationale": "r", "evidence_ids": ["E1"]}'
    for value in ("NaN", "Infinity"):
        bad = good.replace("0.5", value).replace("TC1", "TC2")
        with pytest.raises(ValidationError) as error:
            RankingAnswer.model_validate_json(reply % (good, bad))
        assert parse_reason(error.value) == "score_invalid"


def test_a_verdict_cannot_claim_acceptance_without_two_picks():
    with pytest.raises(ValidationError):
        RankingVerdict(
            status="accepted",
            reason="ranking_accepted",
            snapshot_fingerprint=snapshot().fingerprint,
        )
    with pytest.raises(ValidationError):
        RankingVerdict(
            status="rejected",
            reason="ranking_accepted",
            snapshot_fingerprint=snapshot().fingerprint,
        )


# --- a snapshot from a real triage run ---------------------------------------------


def test_a_snapshot_of_a_real_run_offers_only_observable_evidence(monkeypatch):
    """KA-06 under deterministic triage (scripted conclusion, no model)."""
    from tests.test_triage_question_gaps import run_known_case

    state = run_known_case("KA-06-setting", monkeypatch)
    snap = ranking_snapshot(state)
    assert [c.id for c in snap.candidates] == [c.id for c in state.triage_candidates]
    assert "setting_shift" in {c.family for c in snap.candidates}
    observable = {p.evidence_id for p in state.provenance if p.origin == "observable"}
    assert set(snap.evidence_ids) <= observable
    assert snap.source_cutoff_tick == state.triage_observation_cutoff_tick
    # Rebuilding from the same state gives the same fingerprint.
    assert ranking_snapshot(state).fingerprint == snap.fingerprint
