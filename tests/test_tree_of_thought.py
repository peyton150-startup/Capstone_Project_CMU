"""The opt-in tree-of-thought hypothesize step, with fake models and no network."""

import pytest

from capstone.agent.model_policy import ModelPolicy
from capstone.agent.tree_of_thought import (
    GENERATE,
    VALUE,
    Candidate,
    Candidates,
    Rating,
    Ratings,
    TreeOfThoughtPolicy,
    prune,
)
from capstone.contracts.evidence import Evidence
from capstone.contracts.provenance import ProvenanceReference
from capstone.experiment import Case, run_experiment
from capstone.providers.chat import JOBS
from capstone.providers.factory import research_tools
from tests.helpers import new_state
from tests.test_model_policy import FakeModel, scripted_models


def candidate(id, *supporting):
    return Candidate(
        id=id, claim=f"explanation {id}", supporting_evidence_ids=supporting
    )


def rating(id, verdict="likely", confidence=0.5, *against):
    return Rating(
        candidate_id=id,
        verdict=verdict,
        confidence=confidence,
        contradicting_evidence_ids=against,
    )


# --- pruning, in code -----------------------------------------------------------


def test_pruning_keeps_the_best_rated_and_says_why_the_rest_went():
    candidates = [
        candidate("C1", "E1"),
        candidate("C2", "E1"),
        candidate("C3", "E9"),  # cites evidence never gathered
        candidate("C4"),  # never rated
        candidate("C5", "E1"),
        candidate("C6"),
    ]
    ratings = [
        rating("C1", confidence=0.4),
        rating("C2", "impossible", 0.9, "E1"),
        rating("C3", "sure", 0.99),
        rating("C5", "sure", 0.8),
        rating("C6", confidence=0.4),  # ties C1; C1 came first
        rating("C7", "sure", 1.0),  # no such candidate: ignored
    ]
    kept, dropped = prune(candidates, ratings, {"E1"}, breadth=2)
    assert [c.id for c, _ in kept] == ["C5", "C1"]
    assert dropped == {
        "C2": "rated impossible",
        "C3": "cites evidence that was not gathered",
        "C4": "not rated",
        "C6": "ranked below the best 2",
    }


def test_pruning_is_deterministic_and_counts_a_candidates_first_rating():
    candidates = [candidate("C1"), candidate("C1"), candidate("C2")]
    ratings = [
        rating("C1", confidence=0.2),
        rating("C1", confidence=0.9),
        rating("C2", confidence=0.5),
    ]
    first = prune(candidates, ratings, set(), breadth=3)
    assert first == prune(candidates, ratings, set(), breadth=3)
    kept, dropped = first
    assert [(c.id, r.confidence) for c, r in kept] == [("C2", 0.5), ("C1", 0.2)]
    assert dropped == {"C1": "a repeated candidate id"}


def test_impossible_drops_a_candidate_only_with_a_cited_contradiction():
    """The model's verdict alone does not rule a cause out: it must point at
    gathered evidence against it, in the rating or in the candidate itself."""
    against_itself = Candidate(
        id="C4", claim="explanation C4", contradicting_evidence_ids=("E1",)
    )
    candidates = [candidate("C1"), candidate("C2"), candidate("C3"), against_itself]
    ratings = [
        rating("C1", "impossible", 0.3, "E1"),  # cited and gathered: dropped
        rating("C2", "impossible", 0.2),  # nothing cited: ranked like the rest
        rating("C3", "impossible", 0.1, "E9"),  # cites only ungathered: same
        rating("C4", "impossible", 0.4),  # the candidate cites E1 itself
    ]
    kept, dropped = prune(candidates, ratings, {"E1"}, breadth=3)
    assert [c.id for c, _ in kept] == ["C2", "C3"]
    assert dropped == {"C1": "rated impossible", "C4": "rated impossible"}


def test_an_uncited_impossible_ranked_out_says_so():
    candidates = [candidate("C1"), candidate("C2")]
    ratings = [rating("C1", confidence=0.6), rating("C2", "impossible", 0.1)]
    kept, dropped = prune(candidates, ratings, set(), breadth=1)
    assert [c.id for c, _ in kept] == ["C1"]
    assert dropped == {
        "C2": "rated impossible with no factory evidence against it; ranked below the best 1"
    }


def test_the_rating_prompt_asks_for_the_contradicting_evidence():
    assert "contradicting_evidence_ids" in VALUE


# --- the hypothesize step -----------------------------------------------------------


def tree(*hypothesize_replies, **options):
    clients = {job: FakeModel() for job in JOBS}
    clients["hypothesize"] = FakeModel(*hypothesize_replies)
    return TreeOfThoughtPolicy(clients, research_tools(), **options)


def with_evidence():
    state = new_state()
    for number in (1, 2):
        state.evidence.append(
            Evidence(
                id=f"E{number}",
                source_id="simulator:get_events",
                source_type="tool_result",
                content="[]",
                observed_tick=10,
            )
        )
        # Answered by the factory, as the loop labels it.
        state.provenance.append(
            ProvenanceReference(
                evidence_id=f"E{number}",
                source_id="simulator:get_events",
                source_type="tool_result",
                origin="observable",
            )
        )
    return state


GENERATED = {
    "candidates": [
        {
            "id": "C1",
            "claim": "bearing wear on CNC-02",
            "supporting_evidence_ids": ["E1"],
        },
        {
            "id": "C2",
            "claim": "a passing glitch, nothing to fix",
            "contradicting_evidence_ids": ["E2"],
        },
        {"id": "C3", "claim": "a wrong speed setting on CNC-02"},
        {"id": "C4", "claim": "a bad batch", "supporting_evidence_ids": ["E7"]},
    ]
}
RATED = {
    "ratings": [
        {
            "candidate_id": "C1",
            "verdict": "likely",
            "confidence": 0.7,
            "question": "Did vibration climb slowly over hours?",
        },
        {
            "candidate_id": "C2",
            "verdict": "likely",
            "confidence": 0.2,
            "question": "Has vibration fallen back since?",
        },
        {
            "candidate_id": "C3",
            "verdict": "impossible",
            "confidence": 0.1,
            "contradicting_evidence_ids": ["E1"],
        },
        {"candidate_id": "C4", "verdict": "sure", "confidence": 0.9},
    ]
}


def test_hypotheses_are_the_pruned_candidates_with_their_valued_confidence():
    agent = tree(GENERATED, RATED, breadth=2)
    state = with_evidence()
    before = state.model_copy(deep=True)
    answer = agent.hypothesize(state)
    assert state == before  # the policy never changes state
    assert [(h.id, h.claim, h.confidence) for h in answer.hypotheses] == [
        ("H1", "bearing wear on CNC-02", 0.7),
        ("H2", "a passing glitch, nothing to fix", 0.2),
    ]
    assert answer.hypotheses[0].supporting_evidence_ids == ("E1",)
    assert answer.hypotheses[1].contradicting_evidence_ids == ("E2",)
    assert [(q.id, q.hypothesis_id) for q in answer.new_questions] == [
        ("T1", "H1"),
        ("T2", "H2"),
    ]
    [thought] = agent.thoughts
    assert thought.kept == ("C1", "C2")
    assert thought.dropped == {
        "C3": "rated impossible",
        "C4": "cites evidence that was not gathered",
    }


def test_two_hypothesize_questions_each_with_its_own_prompt():
    agent = tree(GENERATED, RATED)
    agent.hypothesize(with_evidence())
    (gen_system, gen_prompt, gen_type), (val_system, val_prompt, val_type) = (
        agent.clients["hypothesize"].asked
    )
    assert gen_system == GENERATE.format(count=5) and gen_type is Candidates
    assert val_system == VALUE and val_type is Ratings
    assert "CANDIDATES:" not in gen_prompt
    assert "- C1: bearing wear on CNC-02 Supported by: E1." in val_prompt
    assert [(c.job, c.outcome) for c in agent.calls] == [
        ("hypothesize", "answered"),
        ("hypothesize", "answered"),
    ]


def test_no_candidates_means_no_hypotheses_and_no_rating_question():
    agent = tree({"candidates": []})
    answer = agent.hypothesize(with_evidence())
    assert answer.hypotheses is None and answer.new_questions == ()
    assert len(agent.calls) == 1


def test_everything_pruned_leaves_the_hypotheses_alone():
    agent = tree(GENERATED, {"ratings": []})
    answer = agent.hypothesize(with_evidence())
    assert answer.hypotheses is None
    assert set(agent.thoughts[0].dropped.values()) == {
        "not rated",
        "cites evidence that was not gathered",
    }


def test_a_bad_rating_reply_is_an_invalid_reply_not_a_repair():
    bad = {"ratings": [{"candidate_id": "C1", "verdict": "maybe", "confidence": 0.5}]}
    agent = tree(GENERATED, bad)
    with pytest.raises(ValueError):
        agent.hypothesize(with_evidence())
    assert [c.outcome for c in agent.calls] == ["answered", "invalid_reply"]


def test_breadth_must_fit_the_candidates():
    with pytest.raises(ValueError):
        tree(breadth=0)
    with pytest.raises(ValueError):
        tree(candidates=2, breadth=3)


def test_the_ordinary_policy_is_unchanged_by_default():
    from capstone.agent.model_policy import SYSTEM

    clients = {job: FakeModel() for job in JOBS}
    clients["hypothesize"] = FakeModel({"hypotheses": None})
    agent = ModelPolicy(clients, research_tools())
    agent.hypothesize(with_evidence())
    [(system, _, _)] = clients["hypothesize"].asked
    assert system == SYSTEM["hypothesize"]


# --- compared with the ordinary step, through the experiment harness ----------------


def as_tree(agent: ModelPolicy) -> TreeOfThoughtPolicy:
    """The scripted seed-6 models, with the hypothesize step answered as a tree."""
    clients = dict(agent.clients)
    clients["hypothesize"] = FakeModel(
        {
            "candidates": [
                {
                    "id": "C1",
                    "claim": "the alarmed machine is wearing",
                    "supporting_evidence_ids": ["E2"],
                },
                {"id": "C2", "claim": "a one-off vibration glitch"},
            ]
        },
        {
            "ratings": [
                {"candidate_id": "C1", "verdict": "likely", "confidence": 0.6},
                {
                    "candidate_id": "C2",
                    "verdict": "impossible",
                    "confidence": 0.05,
                    "contradicting_evidence_ids": ["E2"],
                },
            ]
        },
    )
    return TreeOfThoughtPolicy(clients, agent.tools)


def test_both_steps_run_the_same_case_and_the_tree_costs_one_more_question():
    """Scripted, not live: the same replies except the hypothesize step."""
    case = [Case("bearing-6", 6, "bearing_degradation")]
    [plain] = run_experiment(case, scripted_models, name="plain")
    built = []

    def make_tree():
        built.append(as_tree(scripted_models()))
        return built[-1]

    [tot] = run_experiment(case, make_tree, name="tot")
    for record in (plain, tot):
        assert record.score.action_correct and record.score.resolved
        assert record.verification == "resolved"
    assert tot.conclusion == plain.conclusion
    assert tot.model_calls.questions == plain.model_calls.questions + 1
    [thought] = built[0].thoughts
    assert thought.kept == ("C1",) and thought.dropped == {"C2": "rated impossible"}
    assert plain.thoughts is None
    assert tot.thoughts == [thought]


def test_saved_tree_survives_the_results_file(tmp_path):
    """The tree is written with the record and read back unchanged."""
    from capstone.experiment import append_records, read_records

    case = [Case("bearing-6", 6, "bearing_degradation")]
    [tot] = run_experiment(case, lambda: as_tree(scripted_models()), name="tot")
    path = tmp_path / "tot.jsonl"
    append_records(path, [tot])
    [back] = read_records(path)
    assert back.thoughts == tot.thoughts
    assert back.thoughts[0].dropped == {"C2": "rated impossible"}


def test_the_experiment_flag_builds_the_tree_policy(monkeypatch):
    import capstone.providers.chat as chat
    from capstone.experiment import model_policy_factory

    fakes = {job: FakeModel() for job in JOBS}
    monkeypatch.setattr(chat, "clients_for_jobs", lambda: fakes)
    assert type(model_policy_factory(False)()) is ModelPolicy
    made = model_policy_factory(False, tree_of_thought=True)()
    assert isinstance(made, TreeOfThoughtPolicy)


# --- only factory evidence rules a candidate out; pruned branches are kept ----


def test_impossible_needs_factory_evidence_not_the_manual():
    """With the manual on by default, every run has manual sections before
    hypothesize. A rating that cites only one cannot rule a cause out."""
    candidates = [candidate("C1"), candidate("C2"), candidate("C3")]
    ratings = [
        rating("C1", "impossible", 0.3, "M1"),  # only a manual section: kept
        rating("C2", "impossible", 0.2, "E1"),  # a factory reading: dropped
        rating("C3", confidence=0.5),
    ]
    kept, dropped = prune(candidates, ratings, {"E1", "M1"}, 3, observed_ids={"E1"})
    assert [c.id for c, _ in kept] == ["C3", "C1"]
    assert dropped == {"C2": "rated impossible"}
    # Without the observed set, every gathered id counts, as before.
    _, before = prune(candidates, ratings, {"E1", "M1"}, 3)
    assert before == {"C1": "rated impossible", "C2": "rated impossible"}


def test_hypothesize_hands_back_what_it_ruled_out():
    from capstone.agent.policy import PrunedInterpretation

    agent = tree(GENERATED, RATED, breadth=2)
    answer = agent.hypothesize(with_evidence())
    assert isinstance(answer, PrunedInterpretation)
    # C4 cited evidence never gathered, so the critic could not check it.
    [c3] = answer.pruned
    assert (c3.id, c3.reason, c3.verdict, c3.confidence) == (
        "C3",
        "rated impossible",
        "impossible",
        0.1,
    )
    assert c3.claim == "a wrong speed setting on CNC-02"


def test_the_model_s_reply_type_has_no_pruned_field():
    """Only code builds the pruned list; no model reply can carry one."""
    from capstone.agent.policy import Interpretation

    assert "pruned" not in Interpretation.model_json_schema()["properties"]


def test_the_loop_keeps_the_pruned_branches_in_the_state():
    from capstone.agent.loop import apply_interpretation
    from capstone.agent.policy import Interpretation

    agent = tree(GENERATED, RATED, breadth=2)
    state = with_evidence()
    apply_interpretation(state, agent.hypothesize(state))
    assert [p.id for p in state.pruned_candidates] == ["C3"]
    apply_interpretation(state, Interpretation())  # an ordinary reading adds none
    assert [p.id for p in state.pruned_candidates] == ["C3"]


def test_a_tree_run_writes_its_pruned_branches_to_the_audit_log(tmp_path):
    from capstone.agent.completion import AuditLog
    from capstone.episode import run_episode

    log = AuditLog(tmp_path / "audit.jsonl")
    result = run_episode(
        6,
        as_tree(scripted_models()),
        fault="bearing_degradation",
        clock=lambda: 0.0,
        log=log,
    )
    [record] = log.read()
    assert [p.id for p in record.pruned_candidates] == ["C2"]
    assert record.pruned_candidates == tuple(result.state.pruned_candidates)
    # The shared record, which memory learns from, holds only the beliefs.
    assert "C2" not in [h.id for h in record.completed.hypotheses]
