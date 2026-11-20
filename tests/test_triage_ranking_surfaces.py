"""The ranking in the triage report, the safe API projection and storage (part 4).

No live model: KA-06 under deterministic triage with a scripted ranking.
"""

import json

from capstone.agent.triage_report import TriageReport
from capstone.api.runs import SafeExecutedTriage, safe_executed_triage
from tests.test_triage_ranking_conclude import Ranker, good, run, unknown


def test_the_report_carries_the_accepted_ranking_with_what_each_id_meant(
    monkeypatch,
):
    state = run(monkeypatch, Ranker(good))
    ranking = state.triage_report.ranking
    snap = state.triage_ranking_snapshot
    assert ranking.status == "accepted" and ranking.requests == 1
    assert ranking.snapshot_fingerprint == snap.fingerprint
    assert ranking.candidate_count == len(snap.candidates)
    first = snap.candidates[1]
    assert (ranking.picks[0].candidate_id, ranking.picks[0].family) == (
        first.id,
        first.family,
    )
    assert ranking.picks[0].explanation == first.explanation
    assert ranking.picks[0].confidence == 0.6
    # The ranking never changes the report's own judgement.
    assert state.triage_report.recommendation == "escalate"


def test_a_rejected_ranking_is_reported_without_picks(monkeypatch):
    state = run(monkeypatch, Ranker(unknown, corrections=[unknown]))
    ranking = state.triage_report.ranking
    assert (ranking.status, ranking.reason, ranking.picks) == (
        "rejected",
        "unknown_candidate_id",
        (),
    )
    assert ranking.attempts == ("unknown_candidate_id", "unknown_candidate_id")


def test_without_the_flag_the_report_has_no_ranking(monkeypatch):
    state = run(monkeypatch, Ranker(good), ranking="off")
    assert state.triage_report.ranking is None


def test_the_report_survives_storage_and_old_reports_still_load(monkeypatch):
    state = run(monkeypatch, Ranker(good))
    stored = json.loads(json.dumps(state.triage_report.model_dump(mode="json")))
    assert TriageReport.model_validate(stored) == state.triage_report
    stored.pop("ranking")
    assert TriageReport.model_validate(stored).ranking is None


def test_the_api_projects_only_the_rankings_codes(monkeypatch):
    state = run(monkeypatch, Ranker(unknown, corrections=[good]))
    projected = safe_executed_triage(state)
    assert projected["ranking_enabled"] is True
    assert projected["ranking_status"] == "accepted"
    assert projected["ranking_reason"] == "ranking_accepted"
    assert projected["ranking_requests"] == 2
    text = json.dumps(projected)
    assert "fits the evidence" not in text and "TC" not in text


def test_the_api_projection_is_off_without_the_flag_and_old_payloads_load(
    monkeypatch,
):
    state = run(monkeypatch, Ranker(good), ranking="off")
    projected = safe_executed_triage(state)
    assert projected["ranking_enabled"] is False
    assert projected["ranking_status"] is None
    old = {k: v for k, v in projected.items() if not k.startswith("ranking_")}
    assert SafeExecutedTriage.model_validate(old).ranking_enabled is False
