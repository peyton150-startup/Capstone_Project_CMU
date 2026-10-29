"""The critic's question, with fake clients and no network."""

import pytest

from capstone.agent.artifacts import CritiqueResult, Objection
from capstone.agent.critic import (
    CRITIC_SYSTEM,
    MANUAL_NOTE,
    MANUAL_PER_HYPOTHESIS,
    SHOWN_HYPOTHESES,
    Critic,
    critique_view,
    shown_hypotheses,
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
