"""TRIAGE_MODEL: one model asked first for every triage question.

Unset, nothing changes. Set, every job in a triage asks it (then the shared
FALLBACK_MODEL chain), ahead of LATE_MODEL; a deep run keeps its own models.
Its thinking is off by default and the switch goes to NVIDIA only. No test
touches the network or a real key.
"""

import json

import pytest

from capstone.agent.model_policy import Judgement, ModelPolicy
from capstone.progress import run_header
from capstone.providers.chat import (
    JOBS,
    late_clients,
    late_key,
    triage_clients,
    triage_key,
)
from capstone.providers.factory import research_tools
from capstone.settings import Settings
from tests.helpers import new_state

KEY = "test-key-not-real"
SUPER = "nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b"
LIGHTNING = "nvidia/nvidia/nemotron-3.5-lightning-30b-a3b"
COHERE = "cohere/command-a-03-2025"
MISTRAL = "mistral/ministral-14b-2512"
CLEARED = (
    "NVIDIA_API_KEY",
    "COHERE_API_KEY",
    "MISTRAL_API_KEY",
    "DEFAULT_MODEL",
    "FALLBACK_MODEL",
    "LATE_MODEL",
    "LATE_CONCLUDE",
    "TRIAGE_MODEL",
    "TRIAGE_MODEL_THINKING",
    "DECIDE_REASONING_EFFORT",
    "PROVIDER_SAMPLING",
    "MODEL_SAMPLING",
)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for name in CLEARED:
        monkeypatch.delenv(name, raising=False)
    for name in ("NVIDIA_API_KEY", "COHERE_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(name, KEY)


def settings(**values):
    return Settings(
        _env_file=None, DEFAULT_MODEL=SUPER, FALLBACK_MODEL=COHERE, **values
    )


def models(client):
    return [c.model for c in client.clients]


class Marker:
    """A stand-in client that only says which route it is."""

    def __init__(self, name):
        self.name = name


def policy(*, triage=True, late=False):
    clients = {job: Marker(job) for job in JOBS}
    if triage:
        clients.update({triage_key(job): Marker(f"{job}@triage") for job in JOBS})
    if late:
        clients[late_key("decide")] = Marker("decide@late")
    return ModelPolicy(clients, research_tools())


def test_the_setting_is_off_by_default():
    s = settings()
    assert s.triage_model is None
    assert s.triage_model_thinking is False
    assert triage_clients(s) == {}


def test_a_blank_setting_counts_as_unset():
    assert settings(TRIAGE_MODEL="  ").triage_model is None


def test_every_job_gets_a_triage_client_asking_the_triage_model_first():
    clients = triage_clients(settings(TRIAGE_MODEL=LIGHTNING))
    assert set(clients) == {triage_key(job) for job in JOBS}
    for client in clients.values():
        assert models(client) == [
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "command-a-03-2025",
        ]


def test_thinking_is_off_by_default_and_sent_to_nvidia_only():
    client = triage_clients(settings(TRIAGE_MODEL=LIGHTNING))[triage_key("decide")]
    lightning, cohere = client.clients
    assert lightning.thinking_fields == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert lightning.reasoning_effort is None
    assert cohere.thinking_fields is None


def test_thinking_can_be_switched_on():
    client = triage_clients(
        settings(TRIAGE_MODEL=LIGHTNING, TRIAGE_MODEL_THINKING="on")
    )[triage_key("conclude")]
    assert client.clients[0].thinking_fields == {
        "chat_template_kwargs": {"enable_thinking": True}
    }


def test_a_non_nvidia_triage_model_is_sent_no_thinking_switch():
    client = triage_clients(settings(TRIAGE_MODEL=MISTRAL))[triage_key("plan")]
    assert client.clients[0].thinking_fields is None


def test_the_request_body_turns_thinking_off():
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

    client = triage_clients(settings(TRIAGE_MODEL=LIGHTNING), transport=transport)[
        triage_key("decide")
    ]
    client.ask("system", "prompt", Judgement)
    assert sent[0]["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert sent[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "reasoning_effort" not in sent[0]


@pytest.mark.parametrize("job", JOBS)
def test_in_a_triage_every_job_asks_the_triage_client(job):
    state = new_state()
    state.mode = "triage"
    assert policy().client_for(job, state).name == f"{job}@triage"


@pytest.mark.parametrize("job", JOBS)
def test_a_deep_run_keeps_each_jobs_own_client(job):
    state = new_state()
    state.mode = "deep"
    assert policy().client_for(job, state).name == job


def test_the_triage_model_wins_over_the_late_model_in_a_triage():
    state = new_state()
    state.mode = "triage"
    state.seconds_for_question = 5.0
    assert policy(late=True).client_for("decide", state).name == "decide@triage"


def test_without_triage_clients_a_triage_keeps_its_old_routes():
    state = new_state()
    state.mode = "triage"
    state.seconds_for_question = 5.0
    assert (
        policy(triage=False, late=True).client_for("decide", state).name
        == "decide@late"
    )
    assert policy(triage=False).client_for("plan", state).name == "plan"


def test_late_clients_are_unchanged_by_the_triage_model():
    s = settings(TRIAGE_MODEL=LIGHTNING, LATE_MODEL=MISTRAL)
    assert set(late_clients(s)) == {late_key("decide")}


def test_the_run_header_names_the_triage_model_only_when_set():
    assert not any(
        "triage model" in line for line in run_header(settings(), manual=None)
    )
    lines = run_header(settings(TRIAGE_MODEL=LIGHTNING), manual=None)
    assert (
        f"RUN: triage model {LIGHTNING} (every triage question; thinking off)" in lines
    )
