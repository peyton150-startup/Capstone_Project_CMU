"""The critic's question, with fake clients and no network."""

import pytest

from capstone.agent.artifacts import CritiqueResult, Objection
from capstone.agent.critic import CRITIC_SYSTEM, Critic, critique_view, top_two
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


def test_top_two_by_confidence_ties_keep_order():
    state = state_with_hypotheses()
    assert [h.id for h in top_two(state)] == ["H2", "H3"]
    state.hypotheses = [hypothesis("H1", 0.4)]
    assert [h.id for h in top_two(state)] == ["H1"]
    state.hypotheses = []
    assert top_two(state) == []


def test_view_shows_two_hypotheses_evidence_and_tools_only():
    state = state_with_hypotheses()
    view = critique_view(state, research_tools())
    assert "H2" in view and "H3" in view
    assert "H1" not in view
    assert "E1" in view and "E2" in view
    assert "get_readings" in view
    for word in HIDDEN_WORDS:
        assert word not in view
    assert str(RUN) not in view and str(INVESTIGATION) not in view


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


def test_review_refuses_a_hypothesis_it_was_not_shown():
    # H1 exists in the state but is not among the two leading ones.
    critic, _ = critic_with(result(favoured="H1"))
    with pytest.raises(ValueError):
        critic.review(state_with_hypotheses(), max_seconds=5)
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
