"""Conclude asks for the two-candidate ranking behind TRIAGE_RANKING (part 2).

No live model: a scripted policy (or the real ModelPolicy over a fake client)
answers, on KA-06 under deterministic triage.
"""

import pytest
from pydantic import ValidationError

from capstone.agent import investigation
from capstone.agent.model_policy import (
    JOBS,
    ModelPolicy,
    RankedConcludeAnswer,
    RankingCorrection,
    answer_types_for,
    conclusion_context,
)
from capstone.agent.triage_hypothesize import candidate_role
from capstone.agent.triage_ranking import (
    RankingAnswer,
    RankingSnapshot,
    RejectionDetail,
    correction_text,
    rankable_ids,
    ranking_schema,
)
from capstone.experiment import ranking_record
from capstone.providers.chat import ModelError
from tests.test_triage_graph_invariants import ConcludeOnly
from tests.test_triage_question_gaps import run_known_case


def causes(snapshot: RankingSnapshot):
    """The snapshot's cause candidates, in snapshot order: the rankable ones."""
    return [c for c in snapshot.candidates if candidate_role(c.family) == "cause"]


def good(snapshot: RankingSnapshot):
    """A valid ranking of the first two cause candidates, the second first."""
    first, second = causes(snapshot)[:2]
    return {
        "kind": "ranked",
        "picks": [
            {
                "candidate_id": c.id,
                "confidence": confidence,
                "rationale": "fits the evidence",
                "evidence_ids": list(c.observation_evidence_ids[:1])
                or [snapshot.evidence_ids[0]],
            }
            for c, confidence in ((second, 0.6), (first, 0.3))
        ],
    }


def unknown(snapshot):
    answer = good(snapshot)
    answer["picks"][1]["candidate_id"] = "TC99"
    return answer


class Ranker(ConcludeOnly):
    """Answers the conclusion with a scripted ranking, and scripted corrections."""

    def __init__(self, first, corrections=()):
        super().__init__()
        self.first = first
        self.corrections = list(corrections)
        self.reranks = []
        self.details = []
        self.last_ranking = None

    def conclude(self, state):
        snap = state.triage_ranking_snapshot
        self.last_ranking = (
            self.first(snap) if callable(self.first) and snap else self.first
        )
        if callable(self.last_ranking):
            self.last_ranking = None
        return super().conclude(state)

    def rerank(self, state, reason, detail=None):
        self.reranks.append(reason)
        self.details.append(detail)
        nxt = self.corrections.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt(state.triage_ranking_snapshot)


def run(monkeypatch, policy, ranking="on"):
    monkeypatch.setenv("TRIAGE_RANKING", ranking)
    monkeypatch.setattr(
        "tests.test_triage_question_gaps.ConcludeOnly", lambda: policy, raising=True
    )
    return run_known_case("KA-06-setting", monkeypatch)


def test_with_the_flag_off_nothing_about_ranking_runs(monkeypatch):
    policy = Ranker(good)
    state = run(monkeypatch, policy, ranking="off")
    assert state.triage_ranking_enabled is False
    assert state.triage_ranking is None and state.triage_ranking_snapshot is None
    assert policy.reranks == []
    assert ranking_record(state) == {"ranking": None}


def test_a_valid_first_ranking_is_accepted_and_leaves_the_conclusion_alone(
    monkeypatch,
):
    policy = Ranker(good)
    state = run(monkeypatch, policy)
    verdict = state.triage_ranking
    assert verdict.status == "accepted"
    assert state.triage_ranking_attempts == ("ranking_accepted",)
    assert state.triage_ranking_requests == 1 and policy.reranks == []
    snap = state.triage_ranking_snapshot
    assert [p.candidate_id for p in verdict.picks] == [
        causes(snap)[1].id,
        causes(snap)[0].id,
    ]
    # The ranking never changes the conclusion or what may be done.
    assert state.conclusion.recommendation == "escalate"
    assert state.proposed_action is None
    record = ranking_record(state)
    assert record["ranking_status"] == "accepted"
    assert record["ranking_picks"][0][1] == causes(snap)[1].family
    assert record["ranking_picks"][0][2] == causes(snap)[1].machine_id
    assert record["ranking_picks"][0][3] == 0.6
    assert record["ranking_order_conflict"] is False
    # `good` cites each candidate's own related evidence where it has some.
    assert record["ranking_unrelated_citations"] == tuple(
        0 if snap.candidates[i].observation_evidence_ids else 1 for i in (1, 0)
    )


def test_a_rejected_ranking_gets_one_correction_with_its_reason(monkeypatch):
    policy = Ranker(unknown, corrections=[good])
    state = run(monkeypatch, policy)
    assert policy.reranks == ["unknown_candidate_id"]
    assert state.triage_ranking.status == "accepted"
    assert state.triage_ranking_attempts == ("unknown_candidate_id", "ranking_accepted")
    assert state.triage_ranking_requests == 2


def test_the_correction_is_told_the_wrong_ids_and_the_record_keeps_them(monkeypatch):
    policy = Ranker(unknown, corrections=[good])
    state = run(monkeypatch, policy)
    first = causes(state.triage_ranking_snapshot)[1].id
    detail = policy.details[0]
    assert (detail.field, detail.offending_ids) == ("candidate_id", ("TC99",))
    assert state.triage_ranking_details == (detail, None)
    record = ranking_record(state)
    assert record["ranking_prompt_version"] == "6"
    assert record["ranking_rejections"] == (
        {
            "attempt": 1,
            "reason": "unknown_candidate_id",
            "field": "candidate_id",
            "offending_ids": ["TC99"],
            "named_ids": [first, "TC99"],
        },
    )
    # Every key the record writes is a TriageRecord field.
    from capstone.experiment import TriageRecord

    assert set(record) <= set(TriageRecord.model_fields)


def test_a_missing_ranking_is_asked_for_once_more(monkeypatch):
    policy = Ranker(None, corrections=[good])
    state = run(monkeypatch, policy)
    assert policy.reranks == ["ranking_missing"]
    assert state.triage_ranking.status == "accepted"


def test_only_one_correction_is_asked_then_the_ranking_is_rejected(monkeypatch):
    policy = Ranker(unknown, corrections=[unknown, good])
    state = run(monkeypatch, policy)
    assert policy.reranks == ["unknown_candidate_id"]
    assert state.triage_ranking.status == "rejected"
    assert state.triage_ranking.picks == ()
    assert state.triage_ranking_requests == 2
    assert ranking_record(state)["ranking_picks"] == ()


@pytest.mark.parametrize(
    ("error", "status", "reason"),
    [
        (ModelError("down"), "unavailable", "provider_unavailable"),
        (ValueError("bad"), "rejected", "schema_invalid"),
    ],
)
def test_a_failed_correction_is_named(monkeypatch, error, status, reason):
    policy = Ranker(unknown, corrections=[error])
    state = run(monkeypatch, policy)
    assert (state.triage_ranking.status, state.triage_ranking.reason) == (
        status,
        reason,
    )


def test_a_correction_whose_reply_breaks_the_shape_is_named_precisely(monkeypatch):
    def three(snapshot):
        RankingAnswer.model_validate({"ranking": {"kind": "ranked", "picks": []}})

    policy = Ranker(unknown, corrections=[three])
    state = run(monkeypatch, policy)
    assert state.triage_ranking.reason == "selection_count_invalid"


def test_a_ranking_about_a_changed_candidate_list_is_stale_and_not_corrected(
    monkeypatch,
):
    real = investigation.ranking_snapshot
    calls = []

    def moving(state):
        snap = real(state)
        calls.append(snap)
        if len(calls) == 1:
            return snap
        body = snap.model_dump(mode="json", exclude={"fingerprint"})
        body["candidates"] = list(reversed(body["candidates"]))
        from capstone.agent.triage_ranking import snapshot_fingerprint

        return RankingSnapshot.model_validate(
            {**body, "fingerprint": snapshot_fingerprint(body)}
        )

    monkeypatch.setattr(investigation, "ranking_snapshot", moving)
    policy = Ranker(good, corrections=[good])
    state = run(monkeypatch, policy)
    assert state.triage_ranking.reason == "candidate_snapshot_stale"
    assert policy.reranks == []
    assert state.triage_ranking_requests == 1


# --- the real ModelPolicy over a fake client --------------------------------------


class FakeClient:
    """Returns prepared JSON for each answer type, and keeps what it was shown."""

    def __init__(self, replies):
        self.replies = replies
        self.prompts = []

    def ask(self, system, prompt, answer_type, *, max_seconds=None):
        self.prompts.append((answer_type, prompt))
        # Keyed by class name: the policy builds its ranking types per snapshot.
        replies = {getattr(k, "__name__", k): v for k, v in self.replies.items()}
        return answer_type.model_validate(replies[answer_type.__name__])


def test_the_model_policy_shows_the_candidates_and_keeps_the_raw_ranking(
    monkeypatch,
):
    state = run(monkeypatch, Ranker(good))
    snap = state.triage_ranking_snapshot
    conclusion = state.conclusion.model_dump(mode="json")
    client = FakeClient(
        {
            RankedConcludeAnswer: {"conclusion": conclusion, "ranking": good(snap)},
            RankingCorrection: {"ranking": good(snap)},
        }
    )
    policy = ModelPolicy({job: client for job in JOBS}, ())
    policy.conclude(state)
    answer_type, prompt = client.prompts[-1]
    assert issubclass(answer_type, RankedConcludeAnswer)
    ranking = answer_type.model_json_schema()["properties"]["ranking"]
    assert ids_enum(ranking) == list(rankable_ids(snap))
    assert "CANDIDATE CAUSES TO RANK" in prompt and causes(snap)[0].id in prompt
    assert "must not invent a probability" not in prompt
    assert policy.last_ranking == good(snap)

    raw = policy.rerank(
        state,
        "unknown_candidate_id",
        detail=RejectionDetail(field="candidate_id", offending_ids=("TC99",)),
    )
    assert raw["kind"] == "ranked"
    correction = client.prompts[-1][1]
    assert "must name a candidate id from the list" in correction
    assert "Problem at candidate_id: TC99." in correction
    assert f"Valid candidate ids: {', '.join(rankable_ids(snap))}." in correction
    correction_type = client.prompts[-1][0]
    assert issubclass(correction_type, RankingCorrection)
    assert ids_enum(correction_type.model_json_schema()["properties"]["ranking"]) == (
        list(rankable_ids(snap))
    )
    # The correction sees what the conclusion saw, not only the candidates.
    assert correction.startswith(conclusion_context(state))
    assert "CANDIDATE CAUSES TO RANK" in correction
    assert policy.calls[-1].job == "ranking_correction"


def ids_enum(ranking_schema_json: dict) -> list[str]:
    """The candidate_id enum in a ranking schema's ranked branch."""
    branches = ranking_schema_json.get("anyOf", [])
    for branch in branches:
        picks = branch.get("properties", {}).get("picks")
        if picks is not None:
            return picks["items"]["properties"]["candidate_id"].get("enum", [])
        if "anyOf" in branch:
            found = ids_enum(branch)
            if found:
                return found
    return []


def test_the_schema_enum_lists_only_the_cause_ids(monkeypatch):
    state = run(monkeypatch, Ranker(good))
    snap = state.triage_ranking_snapshot
    causes_only = rankable_ids(snap)
    assert causes_only == tuple(c.id for c in causes(snap))
    assert ids_enum(ranking_schema(causes_only)) == list(causes_only)
    # Without ids the schema stays open, as before.
    assert ids_enum(ranking_schema()) == []
    conclude, correction = answer_types_for(snap)
    assert conclude.__name__ == "RankedConcludeAnswer"
    assert correction.__name__ == "RankingCorrection"
    # The correction reply is held raw: an unknown id still validates here
    # and is judged later by check_ranking.
    bad = {"kind": "ranked", "picks": [{"candidate_id": "TC99"}]}
    assert correction.model_validate({"ranking": bad}).ranking == bad


def test_only_candidate_id_failures_list_the_valid_ids():
    ids = ("TC2", "TC3")
    for reason in ("unknown_candidate_id", "context_candidate_picked"):
        assert "Valid candidate ids: TC2, TC3." in correction_text(reason, None, ids)
    assert "Valid candidate ids" not in correction_text("schema_invalid", None, ids)
    assert "Valid candidate ids" not in correction_text("unknown_candidate_id")


def test_without_a_snapshot_the_model_policy_asks_as_before(monkeypatch):
    state = run(monkeypatch, Ranker(good), ranking="off")
    conclusion = state.conclusion.model_dump(mode="json")
    from capstone.agent.model_policy import ConcludeAnswer

    client = FakeClient({ConcludeAnswer: {"conclusion": conclusion}})
    policy = ModelPolicy({job: client for job in JOBS}, ())
    policy.conclude(state)
    assert client.prompts[-1][0] is ConcludeAnswer
    assert policy.last_ranking is None
    with pytest.raises(ValueError, match="no ranking snapshot"):
        policy.rerank(state, "schema_invalid")


def test_the_ranked_answer_schema_shows_the_full_ranking_shape():
    schema = RankedConcludeAnswer.model_json_schema()
    ranking = schema["properties"]["ranking"]
    assert "anyOf" in ranking and "$ref" not in str(ranking)
    with pytest.raises(ValidationError):
        RankedConcludeAnswer.model_validate({"conclusion": {}, "ranking": None})
