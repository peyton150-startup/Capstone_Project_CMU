"""The critic's question, with fake clients and no network."""

import pytest

from capstone.agent.artifacts import CritiqueResult, Objection
from capstone.agent.critic import (
    CRITIC_BLIND_SYSTEM,
    CRITIC_SYSTEM,
    MANUAL_NOTE,
    MANUAL_PER_HYPOTHESIS,
    PRUNED_NOTE,
    SHOWN_HYPOTHESES,
    Critic,
    blind_labels,
    blind_order,
    critique_view,
    shown_hypotheses,
    verdict_mismatch,
)
from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis
from capstone.faults import FAULT_KINDS
from capstone.providers.chat import Attempt, ModelError
from capstone.providers.factory import research_tools
from tests.helpers import INVESTIGATION, RUN, new_state

HIDDEN_WORDS = (
    "bearing_degradation",
    "bad_material_batch",
    "wrong_setting",
    "false_alarm",
    "ground truth",
)


def hypothesis(id, confidence, claim="a claim"):
    return Hypothesis(
        id=id,
        claim=f"{id}: {claim}",
        confidence=confidence,
        supporting_evidence_ids=("E1",),
        contradicting_evidence_ids=("E2",),
    )


def state_with_hypotheses():
    state = new_state()
    state.evidence = [
        Evidence(
            id=f"E{n}",
            source_id="simulator:get_readings",
            source_type="tool_result",
            content='{"mean": 3.1}',
            observed_tick=10,
        )
        for n in (1, 2)
    ]
    state.hypotheses = [
        hypothesis("H1", 0.5),
        hypothesis("H2", 0.7),
        hypothesis("H3", 0.7),
    ]
    return state


def result(**changes):
    values = dict(
        favoured="H2",
        why="It fits the readings.",
        discriminating_check="get_readings on the other machine",
        objections=(
            Objection(kind="missing_evidence", text="no trend", evidence_ids=("E1",)),
        ),
        verdict="object",
        favoured_confidence=0.6,
        supports_action=False,
    )
    return CritiqueResult(**(values | changes))


class FakeClient:
    """Answers with a prepared result, or raises; keeps what it was asked."""

    answered_by = "fake-model"

    def __init__(self, reply):
        self.reply = reply
        self.asked = []
        self.attempts = []

    def ask(self, system, prompt, answer_type, *, max_seconds=None):
        self.asked.append((system, prompt, answer_type, max_seconds))
        if isinstance(self.reply, Exception):
            self.attempts = [Attempt(model="fake-model", outcome="timed out")]
            raise self.reply
        self.attempts = [Attempt(model="fake-model", outcome="answered")]
        return self.reply


def critic_with(reply):
    client = FakeClient(reply)
    return Critic(client, research_tools()), client


def test_shown_hypotheses_are_all_of_them_by_confidence_ties_keep_order():
    state = state_with_hypotheses()
    assert [h.id for h in shown_hypotheses(state)] == ["H2", "H3", "H1"]
    state.hypotheses = [hypothesis("H1", 0.4)]
    assert [h.id for h in shown_hypotheses(state)] == ["H1"]
    state.hypotheses = []
    assert shown_hypotheses(state) == []


def test_at_most_five_hypotheses_are_shown():
    state = state_with_hypotheses()
    state.hypotheses = [hypothesis(f"H{n}", 0.9 - n / 10) for n in range(1, 8)]
    assert SHOWN_HYPOTHESES == 5
    assert [h.id for h in shown_hypotheses(state)] == ["H1", "H2", "H3", "H4", "H5"]


def test_view_shows_every_hypothesis_evidence_and_tools_only():
    state = state_with_hypotheses()
    view = critique_view(state, research_tools())
    assert "H1" in view and "H2" in view and "H3" in view
    assert "E1" in view and "E2" in view
    assert "get_readings" in view
    for word in HIDDEN_WORDS:
        assert word not in view
    assert str(RUN) not in view and str(INVESTIGATION) not in view


def test_view_marks_the_agent_s_leading_explanation_once():
    view = critique_view(state_with_hypotheses(), research_tools())
    assert "H2 (confidence 0.70, the agent's leading explanation)" in view
    assert view.count("the agent's leading explanation") == 1


def test_system_prompt_names_no_fault():
    for kind in FAULT_KINDS:
        assert kind not in CRITIC_SYSTEM


def test_schema_fields_are_all_described():
    for name, field in CritiqueResult.model_fields.items():
        assert field.description, name


def test_review_returns_and_records_a_critic_call():
    critic, client = critic_with(result())
    answer = critic.review(state_with_hypotheses(), max_seconds=12.5)
    assert answer.favoured == "H2"
    call = critic.calls[-1]
    assert (call.job, call.agent, call.outcome) == ("critique", "critic", "answered")
    assert call.answered_by == "fake-model"
    assert client.asked[0][3] == 12.5


def test_review_accepts_none_as_favoured():
    critic, _ = critic_with(result(favoured="none"))
    assert critic.review(state_with_hypotheses(), max_seconds=5).favoured == "none"


def test_review_refuses_unknown_favoured():
    critic, _ = critic_with(result(favoured="H9"))
    with pytest.raises(ValueError):
        critic.review(state_with_hypotheses(), max_seconds=5)
    assert critic.calls[-1].outcome == "invalid_reply"
    assert critic.calls[-1].attempts[-1].outcome.startswith("invalid reply")


def test_review_accepts_a_hypothesis_below_the_leading_two():
    # H1 has the lowest confidence of three; it is shown, so it may be favoured.
    critic, _ = critic_with(result(favoured="H1"))
    assert critic.review(state_with_hypotheses(), max_seconds=5).favoured == "H1"
    assert critic.calls[-1].outcome == "answered"


def test_review_refuses_a_hypothesis_it_was_not_shown():
    # Seven hypotheses: H7 is past the five shown, so it cannot be favoured.
    state = state_with_hypotheses()
    state.hypotheses = [hypothesis(f"H{n}", 0.9 - n / 10) for n in range(1, 8)]
    critic, _ = critic_with(result(favoured="H7"))
    with pytest.raises(ValueError):
        critic.review(state, max_seconds=5)
    assert critic.calls[-1].outcome == "invalid_reply"


def test_review_refuses_ungathered_evidence():
    bad = Objection(kind="contradiction", text="see it", evidence_ids=("E99",))
    critic, _ = critic_with(result(objections=(bad,)))
    with pytest.raises(ValueError):
        critic.review(state_with_hypotheses(), max_seconds=5)
    assert critic.calls[-1].outcome == "invalid_reply"


def test_review_lets_model_error_up():
    critic, _ = critic_with(ModelError("no model answered"))
    with pytest.raises(ModelError):
        critic.review(state_with_hypotheses(), max_seconds=5)
    assert critic.calls[-1].outcome == "no_answer"
    assert critic.calls[-1].answered_by is None


def test_review_does_not_change_the_state():
    state = state_with_hypotheses()
    before = state.model_dump()
    critic, _ = critic_with(result())
    critic.review(state, max_seconds=5)
    assert state.model_dump() == before


# --- Option B: code searches the manual for every hypothesis shown -----------


class FakeManual:
    """A manual search that answers from a table of claim words, and keeps asks."""

    def __init__(self, table=None, *, fail=False):
        self.table = table or {}
        self.fail = fail
        self.asked = []

    def search(self, text, *, limit):
        self.asked.append((text, limit))
        if self.fail:
            raise RuntimeError("index down")
        for words, ids in self.table.items():
            if words in text:
                return tuple(section(i) for i in ids)[:limit]
        return ()


def section(section_id):
    from capstone.manual.sections import ManualSection

    return ManualSection(
        section_id=section_id,
        title=f"Title {section_id}",
        text=f"Guidance {section_id}.",
        document_id="SIM-CNC-001",
        revision="1.1",
    )


def manual_critic(manual):
    client = FakeClient(result())
    return Critic(client, research_tools(), manual=manual), client


def test_without_a_manual_nothing_changes():
    critic, client = critic_with(result())
    critic.review(state_with_hypotheses(), max_seconds=40)
    assert MANUAL_NOTE not in client.asked[0][1]
    assert critic.last_sections is None


def test_the_manual_is_searched_on_every_shown_hypothesis():
    manual = FakeManual({"H1": ("2.1", "2.9"), "H2": ("2.9", "2.7"), "H3": ()})
    critic, client = manual_critic(manual)
    state = state_with_hypotheses()
    critic.review(state, max_seconds=40)

    shown = shown_hypotheses(state)
    assert manual.asked == [(h.claim, MANUAL_PER_HYPOTHESIS) for h in shown]
    # Shown once each, in the order the hypotheses are shown (H2, H3, H1).
    assert critic.last_sections == ("§2.9", "§2.7", "§2.1")
    prompt = client.asked[0][1]
    assert MANUAL_NOTE in prompt
    assert prompt.count("§2.9 Title 2.9: Guidance 2.9.") == 1
    assert prompt.index(MANUAL_NOTE) > prompt.index("HYPOTHESES SHOWN TO YOU:")


def test_a_manual_that_finds_nothing_shows_no_section_but_says_it_was_offered():
    critic, client = manual_critic(FakeManual())
    critic.review(state_with_hypotheses(), max_seconds=40)
    assert critic.last_sections == ()
    assert MANUAL_NOTE not in client.asked[0][1]


def test_a_failed_search_leaves_the_critic_to_judge_without_it():
    critic, client = manual_critic(FakeManual(fail=True))
    assert critic.review(state_with_hypotheses(), max_seconds=40) == result()
    assert critic.last_sections == ()


def test_a_manual_section_cannot_be_cited_as_evidence():
    reply = result(
        objections=(
            Objection(
                kind="unsupported_claim", text="manual says", evidence_ids=("§2.9",)
            ),
        )
    )
    client = FakeClient(reply)
    critic = Critic(client, research_tools(), manual=FakeManual({"H": ("2.9",)}))
    with pytest.raises(ValueError, match="never gathered"):
        critic.review(state_with_hypotheses(), max_seconds=40)


def test_the_prompt_says_manual_sections_are_guidance_not_evidence():
    assert "Manual sections" in CRITIC_SYSTEM
    assert "never cite them as evidence" in CRITIC_SYSTEM
    assert not [w for w in HIDDEN_WORDS if w in CRITIC_SYSTEM]


def test_the_real_manual_shown_to_the_critic_names_no_hidden_truth():
    from capstone.manual.index import KeywordManualSearch
    from capstone.manual.sections import load_manual

    critic, client = manual_critic(KeywordManualSearch(load_manual()))
    state = state_with_hypotheses()
    state.hypotheses[0] = hypothesis("H1", 0.5, "failed inspections on one batch")
    critic.review(state, max_seconds=40)
    assert critic.last_sections
    prompt = client.asked[0][1].lower()
    assert not [w for w in HIDDEN_WORDS if w in prompt]


# --- the critic sees what tree-of-thought ruled out --------------------------


def with_pruned(state):
    from capstone.agent.state import PrunedCandidate

    state.pruned_candidates = [
        PrunedCandidate(
            id="C4",
            claim="a bad material batch",
            reason="rated impossible",
            status="contradicted",
            verdict="impossible",
            confidence=0.1,
            contradicting_evidence_ids=("E2",),
        )
    ]
    return state


def test_the_critic_is_shown_what_was_ruled_out():
    view = critique_view(with_pruned(state_with_hypotheses()), research_tools())
    assert PRUNED_NOTE in view
    assert (
        "- C4 (rated impossible, 0.10): a bad material batch "
        "Dropped (contradicted): rated impossible." in view
    )
    assert view.index(PRUNED_NOTE) > view.index("HYPOTHESES SHOWN TO YOU:")


def test_nothing_ruled_out_shows_no_such_section():
    assert PRUNED_NOTE not in critique_view(state_with_hypotheses(), research_tools())


def test_the_critic_cannot_favour_a_ruled_out_candidate():
    critic, _ = critic_with(result(favoured="C4"))
    with pytest.raises(ValueError, match="not a hypothesis shown"):
        critic.review(with_pruned(state_with_hypotheses()), max_seconds=40)


def test_the_prompt_says_ruled_out_candidates_are_not_hypotheses():
    assert "ruled out are not hypotheses" in CRITIC_SYSTEM
    assert "kind alternative" in CRITIC_SYSTEM


# --- the verdict must agree with the critic's own pick -----------------------


@pytest.mark.parametrize(
    "changes, mismatch",
    [
        # Live 2026-10-30: object, favouring the leader, minor gaps only.
        (
            {"favoured": "H1", "verdict": "object"},
            "object while favouring the leading H1, with no contradiction or "
            "alternative raised",
        ),
        # Live 2026-10-30: no_objection while preferring another hypothesis.
        (
            {"favoured": "H2", "verdict": "no_objection"},
            "no_objection while favouring H2, not the leading H1",
        ),
        ({"favoured": "H1", "verdict": "no_objection"}, None),
        ({"favoured": "H2", "verdict": "object"}, None),
        ({"favoured": "none", "verdict": "no_objection"}, None),
        (
            {
                "favoured": "H1",
                "verdict": "object",
                "objections": (
                    Objection(
                        kind="alternative", text="H2 fits too", evidence_ids=("E1",)
                    ),
                ),
            },
            None,
        ),
    ],
)
def test_a_verdict_that_disagrees_with_the_pick_is_named(changes, mismatch):
    assert verdict_mismatch(result(**changes), "H1") == mismatch


def test_no_leader_no_mismatch():
    assert verdict_mismatch(result(verdict="no_objection"), None) is None


def test_the_prompt_ties_the_verdict_to_the_pick():
    assert "make it agree with your pick" in CRITIC_SYSTEM
    # The worked example favours the leading H1 and so no longer objects.
    example = CRITIC_SYSTEM.split("Worked example", 1)[1]
    assert "verdict: no_objection" in example
    assert "verdict: object;" not in example


# --- the blind critic (CRITIC_BLIND) -----------------------------------------


def blind_critic(reply):
    client = FakeClient(reply)
    return Critic(client, research_tools(), blind=True), client


def label_of(state, hypothesis_id):
    """The neutral label a hypothesis is shown under in the blind view."""
    return blind_labels(blind_order(state))[hypothesis_id]


def test_blind_view_hides_the_ranking_and_the_ids():
    """No confidence, no leading mark and no real id: nothing to anchor on."""
    state = state_with_hypotheses()
    view = critique_view(state, research_tools(), blind=True)
    assert "confidence" not in view and "leading" not in view
    for hid in ("H1", "H2", "H3"):
        assert hid not in view  # the claims say "H1: ...", relabelled too
    assert "X1" in view and "X2" in view and "X3" in view
    assert "E1" in view and "E2" in view and "get_readings" in view


def test_blind_order_repeats_on_replay_and_shows_the_same_hypotheses():
    state = state_with_hypotheses()
    first = [h.id for h in blind_order(state)]
    assert first == [h.id for h in blind_order(state.model_copy(deep=True))]
    assert sorted(first) == sorted(h.id for h in shown_hypotheses(state))


def test_blind_order_does_not_always_put_the_leader_first():
    """Across different investigations the leader lands in different places."""
    # Variables:
    #   places: Where the leader (H1, most believed) lands, over many anomalies.
    places = set()
    for tick in range(40):
        state = state_with_hypotheses()
        state.hypotheses = [
            hypothesis("H1", 0.9),
            hypothesis("H2", 0.5),
            hypothesis("H3", 0.3),
        ]
        state.anomaly = state.anomaly.model_copy(update={"tick": tick})
        places.add([h.id for h in blind_order(state)].index("H1"))
    assert places == {0, 1, 2}


def test_blind_order_draws_nothing_from_the_simulator():
    """The shuffle has its own seed: building it twice from a world moves no
    simulator stream, so the factory plays out the same."""
    from capstone.episode import build_world

    def readings_after(shuffle: bool):
        sim = build_world(6, fault="bearing_degradation")
        if shuffle:
            blind_order(state_with_hypotheses())
        for _ in range(50):
            sim.step()
        return sim.state.model_dump()

    assert readings_after(True) == readings_after(False)


def test_blind_review_uses_the_blind_prompt():
    state = state_with_hypotheses()
    critic, client = blind_critic(result(favoured=label_of(state, "H2")))
    critic.review(state, max_seconds=5)
    system, prompt, _, _ = client.asked[0]
    assert system == CRITIC_BLIND_SYSTEM
    assert "leading" not in prompt


@pytest.mark.parametrize(
    "pick, verdict",
    [("H2", "no_objection"), ("H1", "object"), ("H3", "object")],
)
def test_blind_pick_is_mapped_back_and_code_sets_the_verdict(pick, verdict):
    """H2 leads (0.70, first in list order); the critic was not told that."""
    state = state_with_hypotheses()
    label = label_of(state, pick)
    reply = result(
        favoured=label,
        why=f"{label} fits E1.",
        discriminating_check=f"get_readings to tell {label} apart",
        objections=(
            Objection(kind="alternative", text=f"{label} fits", evidence_ids=("E1",)),
        ),
        verdict="no_objection",  # what the blind prompt asks for; code replaces it
    )
    critic, _ = blind_critic(reply)
    answer = critic.review(state, max_seconds=5)
    assert answer.favoured == pick and answer.verdict == verdict
    assert pick in answer.why and pick in answer.discriminating_check
    assert answer.objections[0].text == f"{pick} fits"
    assert critic.last_order == tuple(h.id for h in blind_order(state))


def test_blind_none_is_an_objection():
    critic, _ = blind_critic(result(favoured="none", verdict="no_objection"))
    answer = critic.review(state_with_hypotheses(), max_seconds=5)
    assert (answer.favoured, answer.verdict) == ("none", "object")


def test_blind_review_refuses_a_label_it_was_not_shown():
    critic, _ = blind_critic(result(favoured="X9"))
    with pytest.raises(ValueError, match="X9"):
        critic.review(state_with_hypotheses(), max_seconds=5)
    assert critic.calls[-1].outcome == "invalid_reply"


def test_blind_review_refuses_a_real_id_it_was_never_shown():
    """Found in the pre-merge walkthrough: a blind critic that writes "H1"
    names an id hidden from it; that is a guess, not a pick, so it is refused
    even though H1 is one of the agent's shown hypotheses."""
    critic, _ = blind_critic(result(favoured="H1"))
    with pytest.raises(ValueError, match="not a label shown"):
        critic.review(state_with_hypotheses(), max_seconds=5)
    assert critic.calls[-1].outcome == "invalid_reply"


def test_anchored_critic_is_unchanged_by_default():
    critic, client = critic_with(result())
    critic.review(state_with_hypotheses(), max_seconds=5)
    assert client.asked[0][0] == CRITIC_SYSTEM
    assert critic.blind is False and critic.last_order is None


def test_blind_prompt_names_no_fault_and_asks_for_labels():
    for kind in FAULT_KINDS:
        assert kind not in CRITIC_BLIND_SYSTEM
    assert "not told which" in CRITIC_BLIND_SYSTEM
    assert "leading explanation" not in CRITIC_BLIND_SYSTEM
