"""Tree-of-thought search improvements: reachability, retention, ranking, rotation,
reinstatement, adaptive branching and the second rating pass. Offline only:
fake clocks, scripted policies and fake models; no network and no keys."""

import pytest

from capstone.agent.artifacts import TerminationReason
from capstone.agent.loop import InvestigationDeps, held_for_hypotheses
from capstone.agent.tree_of_thought import (
    INDEPENDENT,
    UNTESTED,
    Candidate,
    Rating,
    Thought,
    TreeOfThoughtPolicy,
    TreeOptions,
    rank_candidates,
    retain,
)
from capstone.contracts.evidence import Evidence
from capstone.contracts.provenance import ProvenanceReference
from capstone.experiment import Case, run_experiment
from capstone.providers.chat import JOBS
from capstone.providers.factory import research_tools
from capstone.tree_reach import group_of, reach_of, summarize
from tests.helpers import ask, new_state
from tests.test_agent_investigation import fresh_state, investigate, stages, wear_policy
from tests.test_model_policy import FakeModel, scripted_models
from tests.test_tree_of_thought import as_tree


@pytest.fixture(autouse=True)
def two_questions_per_step(monkeypatch):
    """Scripted replies give separate interpret and decide answers."""
    monkeypatch.setenv("STEP_QUESTIONS", "2")


# --- reachability: the hypothesis reserve -------------------------------------


def slow_factory(now, seconds=40.0):
    """A factory where every call takes `seconds` on the fake clock."""

    def respond(request):
        now[0] += seconds
        return {"ok": True}

    return respond


def long_research():
    """Research that would go on until the time is up: six distinct look-ups."""
    return wear_policy(
        decisions={
            "investigate": [
                ask("get_sensor_summary", question_id="Q1", machine_id="CNC-02"),
                *[ask("get_events", from_tick=t, to_tick=t + 1) for t in range(5)],
            ],
            "test": [ask("get_readings", hypothesis_id="H1", machine_id="CNC-02")],
        }
    )


def run_long(reserve):
    now = [0.0]
    return investigate(
        long_research(),
        respond=slow_factory(now),
        clock=lambda: now[0],
        state=fresh_state(timeout_seconds=300.0, followup_seconds=60.0),
        hypothesis_seconds=reserve,
    )[0]


def test_without_a_reserve_long_research_skips_the_hypotheses():
    """The behaviour the audit found: research used every second, so the run
    went straight to the conclusion and never formed explanations."""
    state = run_long(0.0)
    assert "hypothesize" not in stages(state)
    assert state.hypothesis_reserve_used is None


def test_the_reserve_lets_the_hypothesize_question_be_asked():
    state = run_long(100.0)
    assert stages(state)[:5] == [
        "observe",
        "plan",
        "investigate",
        "hypothesize",
        "test",
    ]
    assert state.hypothesis_reserve_used is True
    # Research stopped early (three look-ups, not five), so the reserve was there.
    looked = [d for d in state.decisions if d.phase == "investigate" and d.tool]
    assert len(looked) == 3
    assert state.hypotheses  # the test stage ran on the explanation it formed


def test_a_reserve_that_was_not_needed_is_recorded_as_unused():
    state, _ = investigate(wear_policy(), hypothesis_seconds=50.0)
    assert state.hypothesis_reserve_used is False
    assert "hypothesize" in stages(state)


def test_the_reserve_is_held_only_before_the_hypothesize_question():
    deps = InvestigationDeps(
        provider=None, policy=wear_policy(), hypothesis_seconds=30.0
    )
    state = new_state()
    for stage, held in [
        ("plan", 30.0),
        ("investigate", 30.0),
        ("hypothesize", 0.0),
        ("test", 0.0),
        ("verify", 0.0),
    ]:
        state.stage = stage
        assert held_for_hypotheses(state, deps) == held


def test_a_negative_reserve_is_refused():
    with pytest.raises(ValueError):
        InvestigationDeps(provider=None, policy=wear_policy(), hypothesis_seconds=-1)


def test_a_reserve_that_leaves_no_research_time_is_refused(monkeypatch):
    from capstone.episode import run_episode
    from tests.test_known_answers import stand_in

    monkeypatch.setenv("HYPOTHESIS_RESERVE_SECONDS", "800")
    with pytest.raises(ValueError, match="HYPOTHESIS_RESERVE_SECONDS"):
        run_episode(6, stand_in(), fault="bearing_degradation", clock=lambda: 0.0)


# --- reachability: the measurement over saved records ---------------------------


def test_the_report_puts_a_tree_run_in_the_tree_group():
    from tests.test_model_policy import scripted_models
    from tests.test_tree_of_thought import as_tree

    case = [Case("bearing-6", 6, "bearing_degradation")]
    [record] = run_experiment(case, lambda: as_tree(scripted_models()), name="tot")
    assert group_of(record) == "tree"
    reach = reach_of(record)
    assert reach.scenario_id == "bearing-6"
    # Time before the tree is counted only for jobs asked before hypothesize.
    assert "conclude" not in reach.seconds_by_job
    summary = summarize([reach])
    assert summary["runs"] == 1 and summary["groups"]["tree"]["runs"] == 1


def test_the_report_groups_a_run_that_ended_before_the_question_by_its_reason():
    from tests.test_model_policy import scripted_models

    case = [Case("bearing-6", 6, "bearing_degradation")]
    [record] = run_experiment(case, scripted_models, name="plain")
    record = record.model_copy(
        update={
            "thoughts": [],
            "model_calls": record.model_calls.model_copy(
                update={
                    "details": tuple(
                        c for c in record.model_calls.details if c.job != "hypothesize"
                    )
                }
            ),
            "score": record.score.model_copy(update={"termination_reason": "timeout"}),
        }
    )
    assert group_of(record) == "before_timeout"


def test_the_report_reads_the_archived_pairs_as_the_audit_counted_them():
    """The 2026-11-05 audit, repeated from the saved records alone."""
    from pathlib import Path

    from capstone.tree_reach import read_all

    archive = Path(__file__).parents[1] / "docs/benchmarks/2026-11-01-tot13-pairs"
    paths = sorted(archive.glob("*/master-tot13-*.records.jsonl"))
    if not paths:
        pytest.skip("archive not present")
    groups = summarize([reach_of(r) for r in read_all(paths)])["groups"]
    assert {name: g["runs"] for name, g in groups.items()} == {
        "tree": 33,
        "no_answer": 3,
        "before_model_unavailable": 9,
        "before_timeout": 7,
    }


def test_the_stop_reason_for_a_timeout_is_still_timeout():
    """The reserve changes where the run goes after research, not why research
    stopped: the record still says the research ran out of time."""
    state = run_long(100.0)
    stopped = [
        d
        for d in state.decisions
        if d.phase == "investigate" and d.outcome == "stopped"
    ]
    assert stopped[-1].termination_reason is TerminationReason.TIMEOUT


# --- P1: keep several evidence-backed causes ----------------------------------


def cand(id, *supporting, check=None):
    return Candidate(
        id=id,
        claim=f"explanation {id}",
        supporting_evidence_ids=supporting,
        discriminating_check=check,
    )


def rate(id, verdict="likely", confidence=0.6, question=None):
    return Rating(
        candidate_id=id, verdict=verdict, confidence=confidence, question=question
    )


def ranked(candidates, ratings, observed=("E1", "E2", "E3")):
    entries, _ = rank_candidates(candidates, ratings, set(observed), set(observed))
    return entries


def descending(candidates):
    return [rate(c.id, confidence=0.9 - 0.1 * n) for n, c in enumerate(candidates)]


def test_retention_keeps_the_top_k_and_adds_a_second_cause_with_its_own_evidence():
    """Bearing wear (E1) and a wrong setting (E3) on one machine: the setting
    ranks fourth but cites evidence no kept candidate cites, so it stays."""
    candidates = [
        cand("C1", "E1"),
        cand("C2", "E1"),
        cand("C3", "E1", "E2"),
        cand("C4", "E3"),
        cand("C5", "E1"),
    ]
    kept, why = retain(
        ranked(candidates, descending(candidates)),
        3,
        {"E1", "E2", "E3"},
        extra=2,
        floor=0.5,
        calls_left=10,
    )
    assert [e.candidate.id for e in kept] == ["C1", "C2", "C3", "C4"]
    assert why == {"C4": INDEPENDENT}  # C5 only repeats kept evidence


def test_retention_keeps_an_untested_alternative_that_names_a_check():
    """KA-09's lost candidate: the fault may be on a machine nobody checked."""
    candidates = [
        cand("C1", "E1"),
        cand("C2", "E1"),
        cand("C3", "E1"),
        cand("C4", check="Read CNC-07 sensors over the alarm window"),
        cand("C5"),  # no evidence and no check: nothing to test it with
    ]
    _, why = retain(
        ranked(candidates, descending(candidates)),
        3,
        {"E1"},
        extra=2,
        floor=0.5,
        calls_left=10,
    )
    assert why == {"C4": UNTESTED}


def test_retention_never_keeps_a_weak_or_impossible_candidate():
    candidates = [cand("C1", "E1"), cand("C2", "E3"), cand("C3", "E2")]
    ratings = [
        rate("C1", confidence=0.9),
        rate("C2", confidence=0.4),  # below the floor
        rate("C3", "impossible", 0.8),  # unproven impossible: never an extra
    ]
    _, why = retain(
        ranked(candidates, ratings),
        1,
        {"E1", "E2", "E3"},
        extra=2,
        floor=0.5,
        calls_left=10,
    )
    assert why == {}


def test_retention_keeps_no_more_than_the_calls_left_can_test():
    candidates = [cand("C1", "E1"), cand("C2", "E2"), cand("C3", "E3")]
    ratings = [rate(c.id, confidence=0.8) for c in candidates]
    every = {"E1", "E2", "E3"}
    kept, why = retain(
        ranked(candidates, ratings), 1, every, extra=2, floor=0.5, calls_left=2
    )
    assert [e.candidate.id for e in kept] == ["C1", "C2"]
    assert why == {"C2": INDEPENDENT}
    kept, _ = retain(
        ranked(candidates, ratings), 1, every, extra=2, floor=0.5, calls_left=0
    )
    assert [e.candidate.id for e in kept] == ["C1"]  # the top-k is never cut


def test_a_manual_section_is_not_independent_evidence():
    candidates = [cand("C1", "E1"), cand("C2", "M1")]
    ratings = [rate("C1", confidence=0.9), rate("C2", confidence=0.8)]
    entries, _ = rank_candidates(candidates, ratings, {"E1", "M1"}, {"E1"})
    _, why = retain(entries, 1, {"E1"}, extra=2, floor=0.5, calls_left=10)
    assert why == {}


def tree_state(*ids, source="simulator:get_events"):
    state = new_state()
    for evidence_id in ids:
        state.evidence.append(
            Evidence(
                id=evidence_id,
                source_id=source,
                source_type="tool_result",
                content="[]",
                observed_tick=10,
            )
        )
        state.provenance.append(
            ProvenanceReference(
                evidence_id=evidence_id,
                source_id=source,
                source_type="tool_result",
                origin="observable",
            )
        )
    return state


def tree_policy(*hypothesize_replies, **options):
    clients = {job: FakeModel() for job in JOBS}
    clients["hypothesize"] = FakeModel(*hypothesize_replies)
    return TreeOfThoughtPolicy(
        clients, research_tools(), options=TreeOptions(**options)
    )


FOUR = {
    "candidates": [
        {"id": "C1", "claim": "bearing wear", "supporting_evidence_ids": ["E1"]},
        {"id": "C2", "claim": "a loose sensor", "supporting_evidence_ids": ["E1"]},
        {"id": "C3", "claim": "a passing glitch", "supporting_evidence_ids": ["E1"]},
        {"id": "C4", "claim": "a wrong setting", "supporting_evidence_ids": ["E2"]},
    ]
}
FOUR_RATED = {
    "ratings": [
        {"candidate_id": f"C{n}", "verdict": "likely", "confidence": c, "question": q}
        for n, c, q in [
            (1, 0.8, "Did vibration climb?"),
            (2, 0.7, None),
            (3, 0.6, None),
            (4, 0.55, "Is the speed setting off?"),
        ]
    ]
}


def test_the_tree_with_retention_makes_the_extra_cause_a_hypothesis():
    agent = tree_policy(FOUR, FOUR_RATED, retain="evidence")
    answer = agent.hypothesize(tree_state("E1", "E2"))
    assert [h.claim for h in answer.hypotheses] == [
        "bearing wear",
        "a loose sensor",
        "a passing glitch",
        "a wrong setting",
    ]
    assert [q.hypothesis_id for q in answer.new_questions] == ["H1", "H4"]
    [thought] = agent.thoughts
    assert thought.retained == {"C4": INDEPENDENT}
    assert "C4" not in thought.dropped
    assert answer.pruned == ()  # nothing was dropped


def test_top_k_retention_is_the_depth_one_tree_unchanged():
    agent = tree_policy(FOUR, FOUR_RATED)
    answer = agent.hypothesize(tree_state("E1", "E2"))
    assert len(answer.hypotheses) == 3
    [thought] = agent.thoughts
    assert thought.retained == {}
    assert thought.dropped == {"C4": "ranked below the best 3"}


def test_older_trees_read_without_retained():
    old = {"candidates": [], "ratings": [], "kept": [], "dropped": {}}
    assert Thought.model_validate(old).retained == {}


def fake_clients(monkeypatch):
    import capstone.providers.chat as chat

    monkeypatch.setattr(
        chat, "clients_for_jobs", lambda: {j: FakeModel() for j in chat.JOBS}
    )


def test_the_retain_setting_reaches_the_tree(monkeypatch):
    from capstone.experiment import model_policy_factory

    fake_clients(monkeypatch)
    monkeypatch.setenv("TOT_RETAIN", "evidence")
    assert model_policy_factory(False, tree_of_thought=True)().options.retain == (
        "evidence"
    )
    monkeypatch.delenv("TOT_RETAIN")
    made = model_policy_factory(False, tree_of_thought=True)()
    assert made.options == TreeOptions()


def test_a_tree_record_keeps_its_options():
    case = [Case("bearing-6", 6, "bearing_degradation")]
    [record] = run_experiment(case, lambda: as_tree(scripted_models()), name="tot")
    assert record.tree_options == TreeOptions()
    [plain] = run_experiment(case, scripted_models, name="plain")
    assert plain.tree_options is None


# --- P4: order rotation, the position check and the evidence rubric -------------


def test_rotation_starts_the_listing_at_the_offset_and_wraps_round():
    from capstone.agent.tree_of_thought import rotated

    candidates = [cand(f"C{n}") for n in range(1, 5)]
    assert [c.id for c in rotated(candidates, 1)] == ["C2", "C3", "C4", "C1"]
    assert [c.id for c in rotated(candidates, 6)] == ["C3", "C4", "C1", "C2"]
    assert rotated([], 3) == []


def test_a_rotated_tree_lists_the_candidates_in_its_shown_order():
    agent = tree_policy(FOUR, FOUR_RATED, rotate=True)
    state = tree_state("E1", "E2")
    agent.hypothesize(state)
    [thought] = agent.thoughts
    offset = state.investigation_id.int % 4
    expected = [f"C{(offset + n) % 4 + 1}" for n in range(4)]
    assert list(thought.shown_order) == expected
    [_, (_, prompt, _)] = agent.clients["hypothesize"].asked
    listed = [
        line.split(":")[0][2:] for line in prompt.splitlines() if line[:3] == "- C"
    ]
    assert listed == expected
    # Rotation changes only the listing: the same ratings keep the same ones.
    assert thought.kept == ("C1", "C2", "C3")


def test_an_unrotated_tree_records_the_generated_order():
    agent = tree_policy(FOUR, FOUR_RATED)
    agent.hypothesize(tree_state("E1", "E2"))
    assert agent.thoughts[0].shown_order == ("C1", "C2", "C3", "C4")


def test_older_trees_read_without_a_shown_order():
    old = {"candidates": [], "ratings": [], "kept": [], "dropped": {}}
    assert Thought.model_validate(old).shown_order == ()


def test_the_position_check_pairs_each_listing_place_with_its_rating():
    from capstone.tree_reach import position_effect

    agent = tree_policy(FOUR, FOUR_RATED, rotate=True)
    state = tree_state("E1", "E2")
    agent.hypothesize(state)
    case = [Case("bearing-6", 6, "bearing_degradation")]
    [record] = run_experiment(case, lambda: as_tree(scripted_models()), name="tot")
    record = record.model_copy(update={"thoughts": agent.thoughts})
    effect = position_effect([record])
    assert effect["trees"] == 1
    first = agent.thoughts[0].shown_order[0]
    confidence = {r.candidate_id: r.confidence for r in agent.thoughts[0].ratings}
    assert effect["by_position"][1]["mean_confidence"] == confidence[first]
    assert effect["rotated_trees"] == (agent.thoughts[0].shown_order[0] != "C1")


def test_the_evidence_rubric_ranks_independent_support_above_confidence():
    """Two views of one sensor are one family; events and inspections are two."""
    state = tree_state("E1", "E2", source="simulator:get_readings")
    state = tree_state_more(state, "E3", "simulator:get_sensor_summary")
    state = tree_state_more(state, "E4", "simulator:get_events")
    state = tree_state_more(state, "E5", "simulator:get_inspections")
    generated = {
        "candidates": [
            {"id": "C1", "claim": "a", "supporting_evidence_ids": ["E1", "E2", "E3"]},
            {"id": "C2", "claim": "b", "supporting_evidence_ids": ["E4", "E5"]},
        ]
    }
    rated = {
        "ratings": [
            {"candidate_id": "C1", "verdict": "likely", "confidence": 0.9},
            {"candidate_id": "C2", "verdict": "likely", "confidence": 0.6},
        ]
    }
    by_evidence = tree_policy(generated, rated, rank="evidence", breadth=1)
    assert by_evidence.hypothesize(state).hypotheses[0].claim == "b"
    by_confidence = tree_policy(generated, rated, breadth=1)
    assert by_confidence.hypothesize(state).hypotheses[0].claim == "a"


def tree_state_more(state, evidence_id, source):
    state.evidence.append(
        Evidence(
            id=evidence_id,
            source_id=source,
            source_type="tool_result",
            content="[]",
            observed_tick=10,
        )
    )
    state.provenance.append(
        ProvenanceReference(
            evidence_id=evidence_id,
            source_id=source,
            source_type="tool_result",
            origin="observable",
        )
    )
    return state


def test_the_rubric_puts_a_settled_verdict_first_and_counts_contradictions():
    from capstone.agent.tree_of_thought import Ranked, evidence_strength

    families = {"E1": "get_events", "E2": "get_inspections"}
    sure = Ranked(order=0, candidate=cand("C1", "E1"), rating=rate("C1", "sure", 0.5))
    contradicted = Ranked(
        order=1,
        candidate=Candidate(
            id="C2",
            claim="x",
            supporting_evidence_ids=("E1", "E2"),
            contradicting_evidence_ids=("E2",),
        ),
        rating=rate("C2", "likely", 0.9),
    )
    assert evidence_strength(sure, families, {"E1", "E2"}) == (2, 1, 0)
    assert evidence_strength(contradicted, families, {"E1", "E2"}) == (1, 1, 0)
    unproven = Ranked(
        order=2,
        candidate=cand("C3", "E1"),
        rating=rate("C3", "impossible"),
        unproven=True,
    )
    assert evidence_strength(unproven, families, {"E1"})[0] == 0


def test_the_rank_and_rotate_settings_reach_the_tree(monkeypatch):
    from capstone.experiment import model_policy_factory

    fake_clients(monkeypatch)
    monkeypatch.setenv("TOT_RANK", "evidence")
    monkeypatch.setenv("TOT_ROTATE", "true")
    options = model_policy_factory(False, tree_of_thought=True)().options
    assert (options.rank, options.rotate) == ("evidence", True)


# --- P2: the critic may bring back one dropped candidate ------------------------

from capstone.agent.critic import (  # noqa: E402
    REINSTATE_SYSTEM,
    Critic,
    Reinstatement,
    reinstate_view,
)
from capstone.agent.investigation import reinstated_confidence  # noqa: E402
from capstone.agent.policy import PrunedInterpretation  # noqa: E402
from capstone.agent.state import PrunedCandidate  # noqa: E402
from capstone.contracts.hypotheses import Hypothesis  # noqa: E402
from capstone.providers.chat import ModelError  # noqa: E402
from tests.helpers import critique_result  # noqa: E402

CNC07 = PrunedCandidate(
    id="C5",
    claim="the real fault is on CNC-07, which nobody has checked",
    reason="ranked below the best 3",
    status="deferred",
    verdict="likely",
    confidence=0.7,
)
RULED_OUT = PrunedCandidate(
    id="C4",
    claim="a passing glitch",
    reason="rated impossible",
    status="contradicted",
    verdict="impossible",
    confidence=0.8,
    contradicting_evidence_ids=("E2",),
)


def with_pruned(*pruned):
    state = tree_state("E1", "E2")
    state.hypotheses = [
        Hypothesis(id="H1", claim="CNC-03 wear", confidence=0.8),
        Hypothesis(id="H2", claim="CNC-03 sensor fault", confidence=0.6),
    ]
    state.pruned_candidates = list(pruned)
    return state


def test_the_reinstatement_view_shows_kept_and_dropped_but_no_truth():
    view = reinstate_view(with_pruned(CNC07, RULED_OUT), research_tools())
    assert "KEPT EXPLANATIONS:" in view and "DROPPED BEFORE TESTING:" in view
    assert "- C5 (rated likely, 0.70): the real fault is on CNC-07" in view
    assert "Dropped (contradicted): rated impossible" in view
    for hidden in ("ground_truth", "bearing_health", "true_fault"):
        assert hidden not in view


def critic_with(*replies):
    return Critic(FakeModel(*replies), research_tools())


def test_the_critic_names_a_dropped_candidate_and_its_question_is_recorded():
    critic = critic_with(
        {"candidate_id": "C5", "why": "nobody looked at CNC-07", "check": "read CNC-07"}
    )
    answer = critic.reconsider(with_pruned(CNC07), max_seconds=30)
    assert answer == Reinstatement(
        candidate_id="C5", why="nobody looked at CNC-07", check="read CNC-07"
    )
    [(system, _, kind)] = critic.client.asked
    assert system == REINSTATE_SYSTEM and kind is Reinstatement
    assert [(c.job, c.agent, c.outcome) for c in critic.calls] == [
        ("reinstate", "critic", "answered")
    ]


@pytest.mark.parametrize(
    "reply",
    [
        {"candidate_id": "C9", "why": "x"},  # not a dropped candidate
        {"candidate_id": "C5", "why": "x", "evidence_ids": ["E7"]},  # never gathered
        {"candidate_id": "H1", "why": "x"},  # a kept hypothesis, not a dropped one
    ],
    ids=["unknown id", "ungathered evidence", "kept hypothesis"],
)
def test_a_reinstatement_naming_what_was_not_offered_is_refused(reply):
    critic = critic_with(reply)
    with pytest.raises(ValueError):
        critic.reconsider(with_pruned(CNC07), max_seconds=30)
    assert critic.calls[-1].outcome == "invalid_reply"


def test_a_reinstated_candidate_never_starts_above_the_kept_ones():
    assert reinstated_confidence(CNC07, floor=0.6) == 0.6  # rated 0.7, floor 0.6
    assert reinstated_confidence(CNC07, floor=0.9) == 0.7
    # Factory evidence was against it: at most 0.5 until a check says otherwise.
    assert reinstated_confidence(RULED_OUT, floor=0.9) == pytest.approx(0.2)
    unrated = CNC07.model_copy(update={"verdict": None, "confidence": None})
    assert reinstated_confidence(unrated, floor=0.9) == 0.5


class StubCritic:
    """Answers the reinstatement question and the later critique."""

    def __init__(self, reinstatement):
        self.reinstatement = reinstatement
        self.calls = []
        self.reconsidered = []

    def reconsider(self, state, *, max_seconds):
        self.reconsidered.append(max_seconds)
        if isinstance(self.reinstatement, Exception):
            raise self.reinstatement
        return self.reinstatement

    def review(self, state, *, max_seconds):
        return critique_result()


def pruning_policy():
    """The worked example, with a hypothesize step that also dropped C5."""
    return wear_policy(
        hypothesize=lambda state: PrunedInterpretation(
            hypotheses=(
                Hypothesis(
                    id="H1",
                    claim="CNC-02 is wearing",
                    confidence=0.6,
                    supporting_evidence_ids=("E2",),
                ),
            ),
            pruned=(CNC07,),
        )
    )


def test_a_reinstated_candidate_becomes_a_hypothesis_with_its_check():
    critic = StubCritic(
        Reinstatement(candidate_id="C5", why="unchecked", check="read CNC-07")
    )
    seen = []
    state, _ = investigate(
        pruning_policy(), critic=critic, critic_reinstate=True, watch=seen.append
    )
    # The scripted test reading later rewrites the beliefs, so look at the
    # states the run went through: the test stage started with H2 in them.
    assert any(
        s.stage == "test" and CNC07.claim in [h.claim for h in s.hypotheses]
        for s in seen
    )
    record = state.reinstatement
    assert (record.outcome, record.candidate_id, record.hypothesis_id) == (
        "reinstated",
        "C5",
        "H2",
    )
    assert record.offered == ("C5",)
    assert record.confidence == 0.6  # no higher than H1 when it was reinstated
    assert "C5" not in [p.id for p in state.pruned_candidates]
    assert critic.reconsidered  # asked in the critic's own window
    # Its check went to the test stage as an open question tied to H2.
    open_r1 = [q for q in state.unanswered_questions if q.id == "R1"]
    assert "R1" in state.answers or [q.hypothesis_id for q in open_r1] == ["H2"]


def test_a_declined_or_failed_reinstatement_changes_nothing():
    for reply, outcome in [
        (Reinstatement(candidate_id="none", why="all fit"), "declined"),
        (ModelError("down"), "no_answer"),
        (ValueError("bad"), "invalid_reply"),
    ]:
        state, _ = investigate(
            pruning_policy(), critic=StubCritic(reply), critic_reinstate=True
        )
        assert state.reinstatement.outcome == outcome
        assert [p.id for p in state.pruned_candidates] == ["C5"]
        assert state.conclusion is not None  # the run went on


def test_reinstatement_is_off_by_default_and_needs_something_pruned():
    critic = StubCritic(Reinstatement(candidate_id="C5"))
    state, _ = investigate(pruning_policy(), critic=critic)
    assert state.reinstatement is None and critic.reconsidered == []
    state, _ = investigate(wear_policy(), critic=critic, critic_reinstate=True)
    assert state.reinstatement is None  # the ordinary step prunes nothing


def test_the_reinstate_setting_reaches_the_run(monkeypatch):
    from capstone.episode import run_episode

    monkeypatch.setenv("TOT_REINSTATE", "true")
    critic = StubCritic(Reinstatement(candidate_id="none"))
    result = run_episode(
        6,
        as_tree(scripted_models()),
        fault="bearing_degradation",
        clock=lambda: 0.0,
        critic=critic,
    )
    assert result.state.reinstatement.outcome == "declined"
    assert critic.reconsidered
