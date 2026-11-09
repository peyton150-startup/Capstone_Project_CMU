"""LATE_MODEL: decide and conclude go to another model late in a run.

Late means a decide question with less than LATE_MODEL_SECONDS left, or the
conclusion after research stopped because its time ran out. Every other
question keeps its own model. No test touches the network or a real key.
"""

import json

import pytest
from pydantic import ValidationError

from capstone.agent.artifacts import TerminationReason
from capstone.agent.model_policy import ModelPolicy
from capstone.progress import run_header
from capstone.providers.chat import JOBS, LATE_JOBS, late_clients, late_key
from capstone.providers.factory import research_tools
from capstone.settings import Settings
from tests.helpers import new_state

KEY = "test-key-not-real"
SUPER = "nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b"
INSTRUCT = "nvidia/nvidia/llama-3.1-nemotron-70b-instruct"
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
    "LATE_MODEL_SECONDS",
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


def policy(late=True, seconds=60.0):
    clients = {job: FakeModel("own", STOP) for job in JOBS}
    if late:
        clients |= {late_key(job): FakeModel("late", STOP) for job in LATE_JOBS}
    return ModelPolicy(clients, research_tools(), late_seconds=seconds)


def state(left=None, reason=None):
    s = new_state()
    s.seconds_for_question = left
    s.termination_reason = reason
    return s


def test_the_switch_is_off_by_default():
    configured = settings()
    assert configured.late_model is None
    assert configured.late_model_seconds == 60.0
    assert late_clients(configured) == {}


def test_the_threshold_must_be_positive():
    with pytest.raises(ValidationError):
        settings(LATE_MODEL_SECONDS=0)


def test_late_clients_ask_the_late_model_then_the_shared_fallback():
    clients = late_clients(settings(LATE_MODEL=INSTRUCT))
    assert set(clients) == {"decide@late", "conclude@late"}
    for client in clients.values():
        assert [c.model for c in client.clients] == [
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "command-a-03-2025",
        ]


def test_the_late_model_is_never_sent_the_decide_reasoning_effort():
    clients = late_clients(settings(LATE_MODEL=INSTRUCT, DECIDE_REASONING_EFFORT="low"))
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


@pytest.mark.parametrize(
    ("reason", "late"),
    [
        (TerminationReason.TIMEOUT, True),
        (TerminationReason.EVIDENCE_SUFFICIENT, False),
        (TerminationReason.MAX_TOOL_CALLS, False),
        (None, False),
    ],
)
def test_conclude_switches_only_after_research_ran_out_of_time(reason, late):
    p = policy()
    chosen = p.client_for("conclude", state(left=500.0, reason=reason))
    assert chosen is p.clients["conclude@late" if late else "conclude"]


def test_conclude_ignores_the_time_left():
    p = policy()
    assert p.client_for("conclude", state(left=5.0)) is p.clients["conclude"]


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


def test_the_run_header_names_the_late_model_only_when_set():
    assert not any("late-run" in line for line in run_header(settings(), manual=None))
    lines = run_header(settings(LATE_MODEL=INSTRUCT), manual=None)
    assert any(
        "late-run model nvidia/nvidia/llama-3.1-nemotron-70b-instruct" in line
        and "under 60 s" in line
        for line in lines
    )
