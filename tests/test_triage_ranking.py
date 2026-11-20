"""The two-candidate ranking contract, its frozen snapshot and its checks.

No model is asked: these tests build snapshots by hand or from a real triage
run with a scripted conclusion, then check hand-written answers.
"""

import pytest
from pydantic import ValidationError

from capstone.agent.triage_ranking import (
    AbstainedAnswer,
    RankedAnswer,
    RankedPick,
    RankingAnswer,
    RankingSnapshot,
    RankingVerdict,
    check_ranking,
    parse_reason,
    ranking_snapshot,
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


def test_two_valid_picks_are_accepted_most_plausible_first():
    verdict = check(ranked(pick("TC1", 0.2), pick("TC2", 0.7, ("E2", "E3"))))
    assert verdict.status == "accepted" and verdict.reason == "ranking_accepted"
    assert [p.candidate_id for p in verdict.picks] == ["TC2", "TC1"]
    assert verdict.snapshot_fingerprint == snapshot().fingerprint


def test_confidences_need_not_add_to_one_and_ties_keep_snapshot_order():
    verdict = check(ranked(pick("TC3", 0.9), pick("TC1", 0.9)))
    assert verdict.status == "accepted"
    assert [p.candidate_id for p in verdict.picks] == ["TC1", "TC3"]


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
            "evidence_reference_invalid",
        ),
        (
            ranked(pick("TC2", 0.7), pick("TC1", 0.3, missing_checks=("Q2:check",))),
            "check_reference_invalid",
        ),
    ],
)
def test_each_fault_in_an_answer_has_its_own_reason(answer, reason):
    verdict = check(answer)
    assert verdict.status == "rejected" and verdict.reason == reason


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
