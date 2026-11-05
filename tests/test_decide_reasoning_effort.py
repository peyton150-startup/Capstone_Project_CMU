"""DECIDE_REASONING_EFFORT: low reasoning on the decide question only, NVIDIA only.

No test touches the network or a real key.
"""

import json
import urllib.error

import pytest
from pydantic import ValidationError

from capstone.agent.policy import Lesson
from capstone.progress import run_header
from capstone.providers.chat import JOBS, clients_for_jobs
from capstone.settings import Settings

KEY = "test-key-not-real"
NVIDIA = "nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b"
COHERE = "cohere/command-a-03-2025"
CLEARED = (
    "NVIDIA_API_KEY",
    "COHERE_API_KEY",
    "DEFAULT_MODEL",
    "PLAN_MODEL",
    "DECIDE_MODEL",
    "INTERPRET_MODEL",
    "HYPOTHESIZE_MODEL",
    "CONCLUDE_MODEL",
    "JUDGE_MODEL",
    "LESSON_MODEL",
    "FALLBACK_MODEL",
    "DECIDE_REASONING_EFFORT",
    "PROVIDER_SAMPLING",
    "MODEL_SAMPLING",
)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for name in CLEARED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    monkeypatch.setenv("COHERE_API_KEY", KEY)


class FakeTransport:
    """Records each request body and answers with the prepared replies in turn."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.bodies = []

    def __call__(self, url, headers, body, timeout):
        self.bodies.append(json.loads(body))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def chat(content):
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode()


def answer():
    return chat('{"text": "x"}')


def settings(**values):
    return Settings(
        _env_file=None, DEFAULT_MODEL=NVIDIA, FALLBACK_MODEL=COHERE, **values
    )


def body_for(job, configured):
    """The request body one question for `job` sends to its first model."""
    transport = FakeTransport(answer())
    clients_for_jobs(configured, transport=transport)[job].ask("s", "p", Lesson)
    [body] = transport.bodies
    return body


def test_unset_sends_no_reasoning_field_for_any_job():
    configured = settings()
    assert configured.decide_reasoning_effort is None
    for job in JOBS:
        assert "reasoning_effort" not in body_for(job, configured)


def test_low_reaches_the_decide_question_and_no_other():
    configured = settings(DECIDE_REASONING_EFFORT="low")
    assert body_for("decide", configured)["reasoning_effort"] == "low"
    for job in JOBS:
        if job != "decide":
            assert "reasoning_effort" not in body_for(job, configured)


def test_the_fallback_model_is_not_sent_the_field():
    # NVIDIA refuses the key, so Cohere answers the same decide question.
    configured = settings(DECIDE_REASONING_EFFORT="low")
    refused = urllib.error.HTTPError("https://example.test", 401, "error", {}, None)
    transport = FakeTransport(refused, answer())
    decide = clients_for_jobs(configured, transport=transport)["decide"]
    assert decide.ask("s", "p", Lesson) == Lesson(text="x")
    nvidia_body, cohere_body = transport.bodies
    assert nvidia_body["reasoning_effort"] == "low"
    assert "reasoning_effort" not in cohere_body
    # Everything else about Cohere's request is as before.
    assert cohere_body["temperature"] == 0.3


def test_a_non_nvidia_decide_model_is_never_sent_it():
    configured = settings(DECIDE_REASONING_EFFORT="medium", DECIDE_MODEL=COHERE)
    assert "reasoning_effort" not in body_for("decide", configured)


def test_only_the_documented_levels_are_accepted():
    with pytest.raises(ValidationError):
        settings(DECIDE_REASONING_EFFORT="none")


class HeaderSettings:
    """Just the fields run_header reads."""

    critic = False
    critic_blind = False
    critic_followup = False
    manual_step = False
    embedding_model = "e"

    def __init__(self, effort=None):
        self.decide_reasoning_effort = effort


def test_the_run_header_names_the_effort_only_when_set():
    assert len(run_header(HeaderSettings(), manual=None)) == 2
    lines = run_header(HeaderSettings("low"), manual=None)
    assert lines[2] == "RUN: decide reasoning effort low (NVIDIA models only)"
