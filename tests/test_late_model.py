"""LATE_MODEL: opt-in late routing for decide and conclude.

Late means a question with less than LATE_MODEL_SECONDS left. Decide can
switch when LATE_MODEL is set; conclude switches only with LATE_CONCLUDE on.
The late model's thinking is off by default (NVIDIA only). No test touches
the network or a real key.
"""

import json

import pytest
from pydantic import ValidationError

from capstone.agent.artifacts import TerminationReason
from capstone.agent.model_policy import Judgement, ModelPolicy
from capstone.progress import run_header
from capstone.providers.chat import (
    JOBS,
    LATE_JOBS,
    late_clients,
    late_key,
    late_thinking_fields,
)
from capstone.providers.factory import research_tools
from capstone.settings import Settings
from tests.helpers import new_state

KEY = "test-key-not-real"
SUPER = "nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b"
LIGHTNING = "nvidia/nvidia/nemotron-3.5-lightning-30b-a3b"
COHERE = "cohere/command-a-03-2025"
CLEARED = (
    "NVIDIA_API_KEY",
    "COHERE_API_KEY",
    "DEFAULT_MODEL",
    "DECIDE_MODEL",
    "CONCLUDE_MODEL",
    "FALLBACK_MODEL",
    "DECIDE_REASONING_EFFORT",
    "LATE_MODEL",
    "LATE_CONCLUDE",
    "LATE_MODEL_SECONDS",
    "LATE_MODEL_REASONING_BUDGET",
    "LATE_MODEL_THINKING",
    "PROVIDER_SAMPLING",
    "MODEL_SAMPLING",
)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for name in CLEARED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    monkeypatch.setenv("COHERE_API_KEY", KEY)


def settings(**values):
    return Settings(
        _env_file=None, DEFAULT_MODEL=SUPER, FALLBACK_MODEL=COHERE, **values
    )


class FakeModel:
    """Answers each question with the prepared replies and records the asks."""

    attempts = ()

    def __init__(self, name, *replies):
        self.answered_by = name
        self.replies = list(replies)
        self.asked = 0

    def ask(self, system, prompt, answer_type, *, max_seconds=None):
        self.asked += 1
        return answer_type.model_validate_json(json.dumps(self.replies.pop(0)))


STOP = {
    "choice": "stop",
    "stop_reason": "evidence_sufficient",
    "information_needed": "x",
}
CONCLUDED = {
    "conclusion": {
        "diagnosis": "the cause remains uncertain",
        "confidence": 0.4,
        "recommendation": "escalate",
        "assessment": "unresolved",
    }
}


def policy(late=True, seconds=60.0, conclude_late=False):
    clients = {
        job: FakeModel("own", CONCLUDED if job == "conclude" else STOP) for job in JOBS
    }
    if late:
        clients |= {late_key(job): FakeModel("late", STOP) for job in LATE_JOBS}
    if conclude_late:
        clients[late_key("conclude")] = FakeModel("late", CONCLUDED)
    return ModelPolicy(clients, research_tools(), late_seconds=seconds)


def state(left=None, reason=None):
    s = new_state()
    s.seconds_for_question = left
    s.termination_reason = reason
    return s


def test_the_switch_is_off_by_default():
    configured = settings()
    assert configured.late_model is None
    assert configured.late_conclude is False
    assert configured.late_model_seconds == 60.0
    assert late_clients(configured) == {}


def test_the_threshold_must_be_positive():
    with pytest.raises(ValidationError):
        settings(LATE_MODEL_SECONDS=0)


def test_late_clients_ask_the_late_model_then_the_shared_fallback():
    clients = late_clients(settings(LATE_MODEL=LIGHTNING))
    assert set(clients) == {"decide@late"}
    for client in clients.values():
        assert [c.model for c in client.clients] == [
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "command-a-03-2025",
        ]


def test_late_conclusion_uses_the_same_model_fallback_and_thinking():
    clients = late_clients(settings(LATE_MODEL=LIGHTNING, LATE_CONCLUDE="on"))
    assert set(clients) == {"decide@late", "conclude@late"}
    for client in clients.values():
        assert [c.model for c in client.clients] == [
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "command-a-03-2025",
        ]
        assert client.clients[0].thinking_fields == {
            "chat_template_kwargs": {"enable_thinking": False}
        }
        assert client.clients[1].thinking_fields is None


def test_late_conclusion_requires_a_configured_late_model():
    with pytest.raises(ValueError, match="LATE_CONCLUDE requires LATE_MODEL"):
        late_clients(settings(LATE_CONCLUDE="on"))


def test_the_late_model_is_never_sent_the_decide_reasoning_effort():
    clients = late_clients(
        settings(LATE_MODEL=LIGHTNING, DECIDE_REASONING_EFFORT="low")
    )
    assert all(c.reasoning_effort is None for c in clients["decide@late"].clients)


@pytest.mark.parametrize(
    ("left", "late"), [(59.9, True), (10.0, True), (60.0, False), (None, False)]
)
def test_decide_switches_only_with_less_time_than_the_threshold(left, late):
    p = policy()
    chosen = p.client_for("decide", state(left=left))
    assert chosen is p.clients["decide@late" if late else "decide"]


def test_the_threshold_comes_from_the_setting():
    p = policy(seconds=30.0)
    assert p.client_for("decide", state(left=45.0)) is p.clients["decide"]
    assert p.client_for("decide", state(left=29.0)) is p.clients["decide@late"]


def test_the_conclusion_never_switches_even_after_a_timeout():
    p = policy()
    late_state = state(left=5.0, reason=TerminationReason.TIMEOUT)
    assert p.client_for("conclude", late_state) is p.clients["conclude"]


@pytest.mark.parametrize(
    ("left", "late"), [(59.9, True), (5.0, True), (60.0, False), (None, False)]
)
def test_conclusion_switches_only_when_enabled_and_under_threshold(left, late):
    p = policy(conclude_late=True)
    chosen = p.client_for("conclude", state(left=left))
    assert chosen is p.clients["conclude@late" if late else "conclude"]


@pytest.mark.parametrize("job", [j for j in JOBS if j not in LATE_JOBS])
def test_every_other_question_keeps_its_own_model(job):
    p = policy()
    late_state = state(left=1.0, reason=TerminationReason.TIMEOUT)
    assert p.client_for(job, late_state) is p.clients[job]


def test_without_late_clients_nothing_switches():
    p = policy(late=False)
    late_state = state(left=1.0, reason=TerminationReason.TIMEOUT)
    for job in JOBS:
        assert p.client_for(job, late_state) is p.clients[job]


def test_a_late_decide_is_asked_and_recorded_as_the_late_model():
    p = policy()
    p.decide(state(left=20.0), "investigate")
    assert p.clients["decide@late"].asked == 1
    assert p.clients["decide"].asked == 0
    assert p.calls[-1].answered_by == "late"


def test_an_early_decide_still_asks_its_own_model():
    p = policy()
    p.decide(state(left=200.0), "investigate")
    assert p.clients["decide"].asked == 1
    assert p.clients["decide@late"].asked == 0


def test_late_conclusion_is_asked_and_recorded_as_the_late_model():
    p = policy(conclude_late=True)
    conclusion, action = p.conclude(state(left=20.0))
    assert conclusion.diagnosis == "the cause remains uncertain"
    assert action is None
    assert p.clients["conclude@late"].asked == 1
    assert p.clients["conclude"].asked == 0
    assert p.calls[-1].job == "conclude"
    assert p.calls[-1].answered_by == "late"


def test_the_run_header_names_the_late_model_only_when_set():
    assert not any("late-run" in line for line in run_header(settings(), manual=None))
    lines = run_header(settings(LATE_MODEL=LIGHTNING), manual=None)
    assert any(
        "late-run model nvidia/nvidia/nemotron-3.5-lightning-30b-a3b" in line
        and "under 60 s" in line
        and "thinking off" in line
        for line in lines
    )
    budget = settings(
        LATE_MODEL=LIGHTNING,
        LATE_MODEL_THINKING="true",
        LATE_MODEL_REASONING_BUDGET=512,
    )
    assert any(
        "thinking on, budget 512 tokens" in line
        for line in run_header(budget, manual=None)
    )
    lines = run_header(settings(LATE_MODEL=LIGHTNING, LATE_CONCLUDE="on"), manual=None)
    assert any("late conclude" in line and "under 60 s" in line for line in lines)


def test_thinking_is_off_by_default_and_sent_to_nvidia_only():
    late = late_clients(settings(LATE_MODEL=LIGHTNING))["decide@late"]
    lightning, cohere = late.clients
    assert lightning.thinking_fields == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert cohere.thinking_fields is None


def test_thinking_on_with_a_budget():
    configured = settings(
        LATE_MODEL=LIGHTNING,
        LATE_MODEL_THINKING="true",
        LATE_MODEL_REASONING_BUDGET=512,
    )
    assert late_thinking_fields(configured) == {
        "chat_template_kwargs": {"enable_thinking": True},
        "reasoning_budget": 512,
    }
    assert late_thinking_fields(settings(LATE_MODEL_THINKING="true")) == {
        "chat_template_kwargs": {"enable_thinking": True}
    }


def test_the_budget_must_be_positive():
    with pytest.raises(ValidationError):
        settings(LATE_MODEL_REASONING_BUDGET=0)


def test_the_request_body_carries_the_thinking_switch():
    sent = []

    def transport(url, headers, body, timeout):
        sent.append(json.loads(body))
        reply = {"outcome": "resolved", "evidence_ids": ["E1"]}
        return json.dumps(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": json.dumps(reply)}}
                ]
            }
        ).encode()

    late = late_clients(settings(LATE_MODEL=LIGHTNING), transport=transport)
    late["decide@late"].ask("system", "prompt", Judgement)
    assert sent[0]["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert sent[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "reasoning_budget" not in sent[0]


def test_the_own_decide_client_is_never_sent_the_thinking_switch():
    from capstone.providers.chat import clients_for_jobs

    own = clients_for_jobs(settings(LATE_MODEL=LIGHTNING))["decide"]
    assert all(c.thinking_fields is None for c in own.clients)
