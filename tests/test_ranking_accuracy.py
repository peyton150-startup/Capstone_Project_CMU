"""Scoring two-candidate triage rankings against the known cases' truth.

Unit checks use hand-built snapshots and verdicts. The last check runs every
known case through deterministic triage with a scripted conclusion and asks
whether a true cause is among the compiled candidates at all.
"""

from typing import get_args

import pytest

from capstone.agent.triage_hypothesize import CandidateFamily
from capstone.agent.triage_ranking import (
    AbstainedAnswer,
    RankedAnswer,
    RankedPick,
    RankingSnapshot,
    RankingVerdict,
    check_ranking,
    snapshot_fingerprint,
)
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.evaluation.ranking_accuracy import (
    FAMILY_FAULTS,
    MISSING,
    CaseRankingScore,
    aggregate,
    candidate_names,
    score_case,
    score_record,
)
from capstone.evaluation.scoring import Cause
from capstone.faults import FAULT_KINDS

BEARING = Cause(fault="bearing_degradation", machine_id="CNC-02")


def snapshot(*families, machine="CNC-02"):
    """A valid snapshot whose candidates TC1.. have these families, on one machine."""
    # Variables:
    #   body: The snapshot's content, hashed into its fingerprint.
    body = {
        "contract_version": "1.0",
        "rule_version": "1.2",
        "source_cutoff_tick": 100,
        "candidates": [
            {
                "id": f"TC{n}",
                "family": family,
                "explanation": f"{family} may explain it",
                "machine_id": machine,
                "observation_evidence_ids": [],
                "discriminating_requirement_ids": ["Q1:trigger"],
                "missing_requirement_ids": [],
                "unavailable_requirement_ids": [],
            }
            for n, family in enumerate(families, start=1)
        ],
        "evidence_ids": ["E1", "E2"],
    }
    return RankingSnapshot.model_validate(
        {**body, "fingerprint": snapshot_fingerprint(body)}
    )


def pick(candidate_id, confidence):
    """One pick citing evidence E1, which every test snapshot offers."""
    return RankedPick(
        candidate_id=candidate_id,
        confidence=confidence,
        rationale="because",
        evidence_ids=("E1",),
    )


def ranked(snap, first, second, confidences=(0.7, 0.4)):
    """check_ranking's verdict on a two-pick answer."""
    # Variables:
    #   first, second: The TC ids picked, in the order given; check_ranking
    #     keeps that order (prompt version 3), whatever the confidences.
    answer = RankedAnswer(
        picks=(pick(first, confidences[0]), pick(second, confidences[1]))
    )
    return check_ranking(snap, answer, current_fingerprint=snap.fingerprint)


ALARM = ("machine_condition", "operating_load", "sensor_or_transient", "setting_shift")


# --- the mapping ---------------------------------------------------------------


def test_every_candidate_family_is_mapped():
    assert set(FAMILY_FAULTS) == set(get_args(CandidateFamily))


def test_mapped_faults_are_real_fault_kinds():
    for rule in FAMILY_FAULTS.values():
        assert rule.faults <= set(FAULT_KINDS)
        assert rule.why


def test_every_known_fault_is_named_by_some_family():
    named = set().union(*(rule.faults for rule in FAMILY_FAULTS.values()))
    standard = {case.fault for case in KNOWN_CASES if case.fault is not None}
    assert standard <= named


def test_a_machine_family_needs_the_faulty_machine():
    on_cnc2 = snapshot("machine_condition").candidates[0]
    on_cnc5 = snapshot("machine_condition", machine="CNC-05").candidates[0]
    no_machine = snapshot("machine_condition", machine=None).candidates[0]
    assert candidate_names(on_cnc2, BEARING)
    assert not candidate_names(on_cnc5, BEARING)
    assert not candidate_names(no_machine, BEARING)


def test_a_setting_shift_without_a_machine_still_counts():
    setting = Cause(fault="wrong_setting", machine_id="CNC-03")
    unnamed = snapshot("setting_shift", machine=None).candidates[0]
    wrong = snapshot("setting_shift", machine="CNC-01").candidates[0]
    assert candidate_names(unnamed, setting)
    assert not candidate_names(wrong, setting)


def test_a_batch_family_ignores_the_machine():
    batch = Cause(fault="bad_material_batch", batch_id=2)
    candidate = snapshot("common_material_batch", machine=None).candidates[0]
    assert candidate_names(candidate, batch)


def test_an_evidence_family_names_no_fault():
    candidate = snapshot("operating_load").candidates[0]
    assert not any(candidate_names(candidate, Cause(fault=f)) for f in FAULT_KINDS)


# --- one case -----------------------------------------------------------------


def test_accepted_with_the_true_cause_first():
    snap = snapshot(*ALARM)
    score = score_case("KA-01", snap, ranked(snap, "TC1", "TC3"), [BEARING])
    assert score.status == "accepted" and score.valid and not score.abstained
    assert score.top1_correct and score.top2_correct
    assert score.true_cause_in_candidates
    assert score.top1_confidence == 0.7
    assert score.candidate_count == 4


def test_accepted_with_the_true_cause_second_is_top2_only():
    snap = snapshot(*ALARM)
    verdict = ranked(snap, "TC3", "TC1", confidences=(0.8, 0.5))
    score = score_case("KA-01", snap, verdict, [BEARING])
    assert not score.top1_correct and score.top2_correct


def test_accepted_but_wrong():
    snap = snapshot(*ALARM)
    score = score_case("KA-01", snap, ranked(snap, "TC2", "TC3"), [BEARING])
    assert score.valid
    assert not score.top1_correct and not score.top2_correct
    assert score.true_cause_in_candidates


def test_abstained_is_valid_and_never_correct():
    snap = snapshot(*ALARM)
    verdict = check_ranking(
        snap,
        AbstainedAnswer(reason="evidence_insufficient"),
        current_fingerprint=snap.fingerprint,
    )
    score = score_case("KA-01", snap, verdict, [BEARING])
    assert (score.status, score.valid, score.abstained) == ("abstained", True, True)
    assert not score.top1_correct and not score.top2_correct
    assert score.top1_confidence is None


def test_rejected_carries_its_reason():
    snap = snapshot(*ALARM)
    verdict = ranked(snap, "TC1", "TC9")
    score = score_case("KA-01", snap, verdict, [BEARING])
    assert (score.status, score.reason, score.valid) == (
        "rejected",
        "unknown_candidate_id",
        False,
    )
    assert not score.top2_correct


def test_missing_verdict():
    snap = snapshot(*ALARM)
    score = score_case("KA-01", snap, None, [BEARING])
    assert (score.status, score.reason, score.valid) == (MISSING, MISSING, False)
    assert score.true_cause_in_candidates


def test_true_cause_absent_from_the_candidates():
    snap = snapshot("operating_load", "sensor_or_transient", "setting_shift")
    score = score_case("KA-01", snap, ranked(snap, "TC1", "TC2"), [BEARING])
    assert not score.true_cause_in_candidates
    assert not score.top2_correct


def test_either_of_two_true_causes_counts():
    snap = snapshot(*ALARM, machine="CNC-07")
    causes = [
        Cause(fault="bearing_degradation", machine_id="CNC-07"),
        Cause(fault="wrong_setting", machine_id="CNC-07"),
    ]
    score = score_case("KA-09", snap, ranked(snap, "TC4", "TC3"), causes)
    assert score.top1_correct
    # Top-2 counts either cause; naming every cause is reported apart.
    assert (score.causes_named, score.true_cause_count) == (1, 2)
    both = score_case("KA-09", snap, ranked(snap, "TC4", "TC1"), causes)
    assert (both.causes_named, both.true_cause_count) == (2, 2)


def test_top1_is_the_models_first_pick_and_by_confidence_is_reported_apart():
    snap = snapshot(*ALARM)
    # The model put the wrong candidate first, with the lower confidence.
    verdict = ranked(snap, "TC3", "TC1", confidences=(0.4, 0.8))
    assert verdict.order_conflicts_confidence
    score = score_case("KA-01", snap, verdict, [BEARING])
    assert not score.top1_correct and score.top1_by_confidence_correct
    assert score.top1_confidence == 0.4


def test_a_record_is_scored_in_its_stored_order_with_by_confidence_alongside():
    record = {
        "scenario_id": "KA-01",
        "score": {"causes": [BEARING.model_dump(mode="json")]},
        "triage": {
            "ranking": True,
            "ranking_status": "accepted",
            "ranking_reason": "ranking_accepted",
            "ranking_picks": [
                ["TC3", "sensor_or_transient", "CNC-02", 0.4],
                ["TC1", "machine_condition", "CNC-02", 0.8],
            ],
        },
    }
    score = score_record(record)
    assert not score.top1_correct and score.top1_by_confidence_correct
    assert score.top2_correct and score.causes_named == 1


def test_a_verdict_for_another_snapshot_is_refused():
    snap = snapshot(*ALARM)
    other = snapshot(*ALARM, machine="CNC-05")
    with pytest.raises(ValueError, match="different snapshot"):
        score_case("KA-01", other, ranked(snap, "TC1", "TC2"), [BEARING])


def test_no_snapshot_means_no_coverage():
    score = score_case("KA-01", None, None, [BEARING])
    assert not score.true_cause_in_candidates and score.candidate_count == 0


# --- many cases ----------------------------------------------------------------


def case(status="accepted", reason="ranking_accepted", top1=False, top2=False,
         covered=True, confidence=0.5, by_confidence=None, named=None,
         causes=1):  # fmt: skip
    """A hand-made case score; validity and abstention follow from `status`."""
    # Variables:
    #   covered: Whether a true cause was among the case's candidates.
    #   confidence: The top pick's confidence, kept only when accepted.
    #   by_confidence: Top-1 by confidence; the same as top1 unless given.
    #   named, causes: True causes the picks name, of how many; by default
    #     one when top-2 is right.
    return CaseRankingScore(
        top1_by_confidence_correct=top1 if by_confidence is None else by_confidence,
        causes_named=int(top2) if named is None else named,
        true_cause_count=causes,
        scenario_id="KA",
        status=status,
        reason=reason,
        valid=status in ("accepted", "abstained"),
        abstained=status == "abstained",
        top1_correct=top1,
        top2_correct=top2,
        true_cause_in_candidates=covered,
        candidate_count=4,
        top1_confidence=confidence if status == "accepted" else None,
    )


def test_aggregate_rates_and_confidences():
    scores = [
        case(top1=True, top2=True, confidence=0.8),
        case(top2=True, confidence=0.6),
        case(covered=False, confidence=0.4),
        case(status="abstained", reason="ranking_abstained"),
        case(status="rejected", reason="unknown_candidate_id"),
        case(status=MISSING, reason=MISSING, covered=False),
    ]
    result = aggregate(scores)
    assert (result.cases, result.accepted, result.abstained) == (6, 3, 1)
    assert result.validity_rate == pytest.approx(4 / 6)
    assert result.abstention_rate == pytest.approx(1 / 6)
    assert result.invalid_rate == pytest.approx(2 / 6)
    assert result.invalid_by_reason == {MISSING: 1, "unknown_candidate_id": 1}
    assert result.top1_accuracy_accepted == pytest.approx(1 / 3)
    assert result.top2_accuracy_accepted == pytest.approx(2 / 3)
    assert result.top1_accuracy_all == pytest.approx(1 / 6)
    assert result.top2_accuracy_all == pytest.approx(2 / 6)
    assert result.coverage_known == 6
    assert result.candidate_coverage_rate == pytest.approx(4 / 6)
    assert result.top2_accuracy_covered == pytest.approx(1.0)
    assert result.mean_confidence_top1_correct == pytest.approx(0.8)
    assert result.mean_confidence_top1_incorrect == pytest.approx(0.5)
    assert result.small_sample and "not an accuracy estimate" in result.warning
    assert "uncalibrated" in result.confidence_note


def test_aggregate_reports_top1_by_confidence_and_compound_coverage():
    scores = [
        case(top1=True, top2=True, by_confidence=False),
        case(top2=True, by_confidence=True),
        case(top1=True, top2=True, named=1, causes=2),
        case(top1=True, top2=True, named=2, causes=2),
    ]
    result = aggregate(scores)
    assert result.top1_accuracy_accepted == pytest.approx(3 / 4)
    assert result.top1_by_confidence_accuracy_accepted == pytest.approx(3 / 4)
    assert result.top1_rules_disagree == 2
    assert result.compound_accepted == 2
    assert result.all_causes_named_rate == pytest.approx(1 / 2)
    assert "not complete-diagnosis accuracy" in result.accuracy_note


def test_aggregate_without_accepted_rankings_has_no_accuracy_over_accepted():
    result = aggregate([case(status="abstained", reason="ranking_abstained")])
    assert result.top1_accuracy_accepted is None
    assert result.mean_confidence_top1_correct is None
    assert result.top1_accuracy_all == 0


def test_aggregate_of_nothing():
    result = aggregate([])
    assert result.cases == 0 and result.validity_rate is None


def test_a_large_sample_has_no_warning():
    result = aggregate([case()] * 30)
    assert not result.small_sample and result.warning is None


def test_rejected_verdicts_are_not_counted_valid():
    verdict = RankingVerdict(
        status="rejected", reason="schema_invalid", snapshot_fingerprint="0" * 20
    )
    score = score_case("KA", None, verdict, [BEARING])
    assert not score.valid


# --- run records ----------------------------------------------------------------


def record(status="accepted", picks=None, reason=None, ranking=True, causes=None,
           families=None):  # fmt: skip
    """One records.jsonl line as json.loads gives it, ranking fields as part 2 writes them."""
    # Variables:
    #   picks: (candidate id, family, machine id or None, confidence) lists,
    #     most plausible first, as JSON turns the recorded tuples into lists.
    #   ranking: The record's `triage.ranking`: True when a ranking was asked,
    #     None in older records and when none was asked.
    #   families: The families of `triage.deterministic_candidates` (TC1..),
    #     all on CNC-02; None leaves the field out, as in an older record.
    if picks is None:
        picks = [["TC1", "machine_condition", "CNC-02", 0.7],
                 ["TC3", "sensor_or_transient", "CNC-02", 0.3]]  # fmt: skip
    triage = {
        "seconds": 40.0,
        "ranking": ranking,
        "ranking_status": status,
        "ranking_reason": reason or f"ranking_{status}",
        "ranking_attempts": [reason or f"ranking_{status}"],
        "ranking_requests": 1,
        "ranking_fingerprint": "0" * 20,
        "ranking_picks": picks if status == "accepted" else [],
    }
    if families is not None:
        triage["deterministic_candidates"] = [
            snapshot(*families).candidates[n].model_dump(mode="json")
            | {"status": "unconfirmed", "open_question_ids": []}
            for n in range(len(families))
        ]
    return {
        "scenario_id": "KA-01-bearing",
        "score": {"causes": causes or [BEARING.model_dump()]},
        "triage": triage,
    }


def test_record_accepted_right_first():
    score = score_record(record())
    assert (score.status, score.reason, score.valid) == (
        "accepted",
        "ranking_accepted",
        True,
    )
    assert score.top1_correct and score.top2_correct
    assert score.top1_confidence == 0.7
    assert score.true_cause_in_candidates is None and score.candidate_count is None


def test_record_accepted_right_second():
    picks = [["TC3", "sensor_or_transient", "CNC-02", 0.6],
             ["TC1", "machine_condition", "CNC-02", 0.5]]  # fmt: skip
    score = score_record(record(picks=picks))
    assert not score.top1_correct and score.top2_correct


def test_record_pick_on_the_wrong_machine_is_wrong():
    picks = [["TC1", "machine_condition", "CNC-05", 0.7],
             ["TC2", "setting_shift", None, 0.2]]  # fmt: skip
    score = score_record(record(picks=picks))
    assert not score.top2_correct


def test_record_abstained_rejected_and_unavailable():
    abstained = score_record(record("abstained", reason="ranking_abstained"))
    assert abstained.valid and abstained.abstained and not abstained.top2_correct
    rejected = score_record(record("rejected", reason="unknown_candidate_id"))
    assert (rejected.status, rejected.reason, rejected.valid) == (
        "rejected",
        "unknown_candidate_id",
        False,
    )
    unavailable = score_record(record("unavailable", reason="candidate_list_empty"))
    assert (unavailable.status, unavailable.valid) == ("unavailable", False)


def test_record_without_a_ranking_is_missing():
    for line in (record(ranking=None), {**record(), "triage": None}):
        score = score_record(line)
        assert (score.status, score.reason, score.valid) == (MISSING, MISSING, False)


def test_record_coverage_can_be_supplied():
    assert score_record(record(), covered=False).true_cause_in_candidates is False


def test_record_coverage_comes_from_the_recorded_candidates():
    covered = score_record(record(families=ALARM))
    assert covered.true_cause_in_candidates is True and covered.candidate_count == 4
    gap = score_record(record(families=("operating_load", "setting_shift")))
    assert gap.true_cause_in_candidates is False


def test_record_candidates_fit_the_real_triage_record():
    from capstone.experiment import TriageRecord

    triage = record(families=ALARM)["triage"]
    parsed = TriageRecord.model_validate(
        {
            "conclusion": None,
            "confidence": None,
            "recommendation": None,
            "deep_recommended": False,
            "deep_ran": False,
            **triage,
        }
    )
    again = parsed.model_dump(mode="json")
    line = {"scenario_id": "KA-01", "score": {"causes": [BEARING.model_dump()]},
            "triage": again}  # fmt: skip
    score = score_record(line)
    assert score.top1_correct and score.true_cause_in_candidates


def test_a_pick_with_no_recorded_family_names_nothing():
    picks = [["TC9", "", None, 0.9], ["TC1", "machine_condition", "CNC-02", 0.1]]
    score = score_record(record(picks=picks))
    assert not score.top1_correct and score.top2_correct


def test_aggregate_counts_coverage_only_where_known():
    scores = [score_record(record()), score_record(record(), covered=True),
              score_record(record(), covered=False)]  # fmt: skip
    result = aggregate(scores)
    assert result.coverage_known == 2
    assert result.candidate_coverage_rate == pytest.approx(0.5)
    assert result.top2_accuracy_covered == pytest.approx(1.0)


# --- the real simulator ----------------------------------------------------------

# Known cases whose compiled candidates hold no family naming a true cause,
# with the reason. Found by the check below (2026-11-20).
COVERAGE_GAPS: dict[str, str] = {
    "KA-09-challenge": (
        "the first alarm is the false-alarm distractor on CNC-03, so every "
        "candidate is on CNC-03, while both true causes (bearing wear and a "
        "wrong setting) are on CNC-07; cross_machine_review names no fault"
    ),
}


def run_case(scenario_id, monkeypatch):
    """One known case through deterministic triage with a scripted conclusion."""
    # Variables:
    #   known: The case's seed, kind and forced fault from KNOWN_CASES.
    from capstone.episode import run_episode
    from tests.test_triage_graph_invariants import ConcludeOnly

    for key, value in {
        "TRIAGE_RUN_MODE": "deterministic",
        "TRIAGE": "on",
        "TRIAGE_THEN_DEEP": "off",
        "CRITIC": "off",
    }.items():
        monkeypatch.setenv(key, value)
    known = next(c for c in KNOWN_CASES if c.scenario_id == scenario_id)
    return run_episode(
        known.seed, ConcludeOnly(), kind=known.kind, fault=known.fault, triage=True
    )


@pytest.mark.parametrize("scenario_id", [c.scenario_id for c in KNOWN_CASES])
def test_known_case_candidates_cover_the_true_cause(scenario_id, monkeypatch):
    """Every known case's candidates name a true cause, or it is a listed gap."""
    # Variables:
    #   state: The triage's own state (a deep run may follow it).
    #   snap: The candidates a ranking question would show the model.
    #   score: Scored with no verdict; only its coverage is read here.
    from capstone.agent.triage_ranking import ranking_snapshot

    result = run_case(scenario_id, monkeypatch)
    state = result.triage or result.state
    snap = ranking_snapshot(state)
    score = score_case(scenario_id, snap, None, result.score.causes)
    if scenario_id in COVERAGE_GAPS:
        assert not score.true_cause_in_candidates, "gap closed: drop it from the list"
    else:
        families = [c.family for c in snap.candidates]
        assert score.true_cause_in_candidates, (families, result.score.causes)
