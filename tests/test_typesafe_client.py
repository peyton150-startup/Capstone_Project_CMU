"""The TypeSafe client sends typed questions and reads typed answers, with no key shown."""

import json
import urllib.error

import pytest

from capstone.providers.chat import ModelError
from capstone.providers.typesafe import (
    TYPESAFE_URL,
    Choice,
    ChoiceAnswer,
    JudgmentClient,
    Noul,
    NoulAnswer,
    judgment_client,
)
from capstone.settings import Settings

QUESTIONS = {
    "is_bearing": Noul(instructions="Is it a bearing?", true="yes", false="no"),
    "machine": Choice(
        instructions="Which machine?", options={"CNC-01": None, "none": "no machine"}
    ),
}

REPLY = {
    "model": "jev-2026-09-10",
    "answers": {
        "is_bearing": {"type": "noul", "noul": 0.91},
        "machine": {
            "type": "choice",
            "choice": "CNC-01",
            "confidence": 0.8,
            "probabilities": {"CNC-01": 0.9, "none": 0.1},
        },
    },
    "usage": {"input_tokens": 120, "output_tokens": 4},
}


class Recorder:
    def __init__(self, reply):
        self.reply = reply
        self.sent = []

    def __call__(self, url, headers, body, timeout):
        self.sent.append((url, headers, json.loads(body), timeout))
        if isinstance(self.reply, Exception):
            raise self.reply
        return json.dumps(self.reply).encode()


def test_one_request_holds_the_state_and_every_question():
    transport = Recorder(REPLY)
    client = JudgmentClient("secret-key", "jev-latest", transport=transport, timeout=7)
    client.ask({"conclusion": "worn bearing on CNC-01"}, QUESTIONS)

    ((url, headers, body, timeout),) = transport.sent
    assert url == TYPESAFE_URL
    assert headers["Authorization"] == "Bearer secret-key"
    assert timeout == 7
    assert body == {
        "model": "jev-latest",
        "state": {"conclusion": "worn bearing on CNC-01"},
        "questions": {
            "is_bearing": {
                "type": "noul",
                "instructions": "Is it a bearing?",
                "criteria": {"true": "yes", "false": "no"},
            },
            "machine": {
                "type": "choice",
                "instructions": "Which machine?",
                "criteria": {"CNC-01": None, "none": "no machine"},
            },
        },
    }


def test_a_noul_without_criteria_sends_none():
    assert Noul(instructions="Is it?").request() == {
        "type": "noul",
        "instructions": "Is it?",
    }


def test_answers_are_typed_and_name_the_model_that_answered():
    client = JudgmentClient("k", transport=Recorder(REPLY))
    judgments = client.ask("text", QUESTIONS)
    assert judgments.model == "jev-2026-09-10"
    assert judgments.input_tokens == 120
    assert judgments.answers["is_bearing"] == NoulAnswer(type="noul", noul=0.91)
    machine = judgments.answers["machine"]
    assert isinstance(machine, ChoiceAnswer) and machine.choice == "CNC-01"


@pytest.mark.parametrize(
    "broken",
    [
        {"model": "m"},  # no answers
        {
            "model": "m",
            "answers": {"is_bearing": {"type": "noul", "noul": 0.5}},
        },  # one missing
        {
            **REPLY,
            "answers": {
                **REPLY["answers"],
                "is_bearing": {"type": "noul", "noul": 1.5},
            },
        },
        {
            **REPLY,
            "answers": {
                **REPLY["answers"],
                "machine": {**REPLY["answers"]["machine"], "choice": "CNC-99"},
            },
        },
        # A choice answer where a noul was asked.
        {
            **REPLY,
            "answers": {**REPLY["answers"], "is_bearing": REPLY["answers"]["machine"]},
        },
    ],
)
def test_a_reply_that_is_not_the_answers_asked_for_is_refused(broken):
    client = JudgmentClient("k", transport=Recorder(broken))
    with pytest.raises(ValueError):
        client.ask("text", QUESTIONS)


def test_service_failures_are_model_errors_without_the_key():
    error = urllib.error.HTTPError(TYPESAFE_URL, 503, "busy", {}, None)
    client = JudgmentClient("secret-key", transport=Recorder(error))
    with pytest.raises(ModelError) as raised:
        client.ask("text", QUESTIONS)
    assert raised.value.transient
    assert "secret-key" not in str(raised.value)
    assert "secret-key" not in repr(client)


def test_no_questions_is_refused_before_any_request():
    transport = Recorder(REPLY)
    with pytest.raises(ValueError):
        JudgmentClient("k", transport=transport).ask("text", {})
    assert transport.sent == []


def test_the_configured_client_needs_the_key():
    with pytest.raises(ModelError, match="TYPESAFE_API_KEY"):
        judgment_client(Settings(_env_file=None, TYPESAFE_API_KEY=""))
    client = judgment_client(
        Settings(_env_file=None, TYPESAFE_API_KEY="k", TYPESAFE_MODEL="jev-preview")
    )
    assert client.model == "jev-preview"
