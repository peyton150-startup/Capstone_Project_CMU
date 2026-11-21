"""The ranking's lifecycle events, terminal lines and experiment summary (part 3).

No live model: KA-06 under deterministic triage with a scripted ranking.
"""

from types import SimpleNamespace

from capstone.experiment import format_ranking
from capstone.progress import ranking_lines
from tests.test_triage_ranking_conclude import Ranker, good, run, unknown


def ranking_events(state):
    return [
        e for e in state.triage_trace_events if e.event.startswith("triage.ranking")
    ]


def test_an_accepted_ranking_leaves_request_judgement_and_completion(monkeypatch):
    state = run(monkeypatch, Ranker(good))
    events = ranking_events(state)
    assert [e.event for e in events] == [
        "triage.ranking_requested",
        "triage.ranking_judged",
        "triage.ranking_completed",
    ]
    snap = state.triage_ranking_snapshot
    assert all(e.request_hash == snap.fingerprint for e in events)
    assert all(e.phase == "conclude" for e in events)
    assert events[0].candidate_count == len(snap.candidates)
    assert events[0].reason_code == "ranking_requested" and events[0].status is None
    assert (events[-1].status, events[-1].reason_code) == (
        "accepted",
        "ranking_accepted",
    )
    # Events are ordered after everything the triage recorded before them.
    sequences = [e.sequence for e in state.triage_trace_events]
    assert sequences == sorted(sequences)


def test_a_correction_is_recorded_as_its_own_attempt(monkeypatch):
    state = run(monkeypatch, Ranker(unknown, corrections=[good]))
    events = ranking_events(state)
    assert [(e.event, e.attempt, e.reason_code) for e in events] == [
        ("triage.ranking_requested", 1, "ranking_requested"),
        ("triage.ranking_judged", 1, "unknown_candidate_id"),
        ("triage.ranking_correction_requested", 2, "unknown_candidate_id"),
        ("triage.ranking_judged", 2, "ranking_accepted"),
        ("triage.ranking_completed", 2, "ranking_accepted"),
    ]
    assert events[3].duration_ms is not None and events[3].duration_ms >= 0


def test_ranking_events_carry_no_model_text_or_confidence(monkeypatch):
    state = run(monkeypatch, Ranker(good))
    dumped = str([e.model_dump() for e in ranking_events(state)])
    assert "fits the evidence" not in dumped
    assert "0.6" not in dumped and "0.3" not in dumped


def test_with_the_flag_off_there_are_no_ranking_events_or_lines(monkeypatch):
    state = run(monkeypatch, Ranker(good), ranking="off")
    assert ranking_events(state) == []
    assert ranking_lines(state) == []


def test_the_terminal_shows_the_verdict_attempts_and_picks(monkeypatch):
    state = run(monkeypatch, Ranker(unknown, corrections=[good]))
    lines = ranking_lines(state)
    snap = state.triage_ranking_snapshot
    assert lines[0].startswith("TRIAGE RANKING accepted (ranking_accepted)")
    assert "unknown_candidate_id -> ranking_accepted" in lines[0]
    assert snap.fingerprint in lines[0]
    first = snap.candidates[1]
    assert lines[1].startswith(f"  1. {first.id} {first.family} belief 0.60")
    assert "uncalibrated" in lines[1]
    # The rejected first attempt is shown with where it broke, ids only.
    assert lines[3] == (
        f"  attempt 1 unknown_candidate_id at candidate_id: TC99 "
        f"(named {snap.candidates[0].id}, TC99)"
    )
    assert len(lines) == 4


def test_a_rejected_ranking_prints_no_picks(monkeypatch):
    state = run(monkeypatch, Ranker(unknown, corrections=[unknown]))
    lines = ranking_lines(state)
    assert lines[0].startswith("TRIAGE RANKING rejected (unknown_candidate_id)")
    # No picks; only the two rejected attempts, each with its wrong id.
    assert [line.split(" at ")[0] for line in lines[1:]] == [
        "  attempt 1 unknown_candidate_id",
        "  attempt 2 unknown_candidate_id",
    ]


def record(status, reason, requests=1):
    return SimpleNamespace(
        triage=SimpleNamespace(
            ranking=True,
            ranking_status=status,
            ranking_reason=reason,
            ranking_requests=requests,
        )
    )


def test_the_experiment_summary_counts_outcomes_and_corrections():
    records = [
        record("accepted", "ranking_accepted"),
        record("accepted", "ranking_accepted", requests=2),
        record("rejected", "unknown_candidate_id", requests=2),
        record("abstained", "ranking_abstained"),
        record("unavailable", "conclusion_deadline_exceeded"),
        SimpleNamespace(triage=None),
    ]
    line = format_ranking(records)
    assert line.startswith(
        "ranking: 5 asked; 2 accepted, 1 abstained, 1 rejected, 1 unavailable; "
        "2 corrected (1 saved)"
    )
    assert "ranking_accepted 2" in line


def test_the_experiment_summary_is_absent_without_rankings():
    assert format_ranking([SimpleNamespace(triage=None)]) is None
