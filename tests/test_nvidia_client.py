"""The NVIDIA client, with a fake transport. No test touches the network or a real key."""

import json
import urllib.error

import pytest

from capstone.agent.policy import Lesson
from capstone.providers.nvidia import (
    DEFAULT_MODEL,
    NVIDIA_URL,
    ModelError,
    NvidiaClient,
)
from capstone.settings import Settings

KEY = "nvapi-test-not-a-real-key"


class FakeTransport:
    """Records each request and answers with a prepared reply body."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, url, headers, body, timeout):
        self.requests.append((url, headers, json.loads(body), timeout))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def chat(content):
    """A reply body in the chat-completions shape, carrying `content`."""
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode()


def client(*replies, **options):
    transport = FakeTransport(*replies)
    return NvidiaClient(KEY, transport=transport, **options), transport


# --- the request ---------------------------------------------------------------


def test_one_request_carries_the_model_the_prompt_and_the_answer_shape():
    ask, transport = client(chat('{"text": "Look at vibration first."}'))
    ask.ask("You investigate a factory.", "What next?", Lesson)
    [(url, headers, body, timeout)] = transport.requests
    assert url == NVIDIA_URL
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert headers["Content-Type"] == "application/json"
    assert body["model"] == DEFAULT_MODEL
    assert body["temperature"] == 0
    system, user = body["messages"]
    assert system["role"] == "system"
    assert system["content"].startswith("You investigate a factory.")
    assert json.dumps(Lesson.model_json_schema()) in system["content"]
    assert user == {"role": "user", "content": "What next?"}
    assert timeout > 0


def test_the_model_name_can_be_chosen():
    ask, transport = client(chat('{"text": "x"}'), model="nvidia/other-model")
    ask.ask("s", "p", Lesson)
    assert transport.requests[0][2]["model"] == "nvidia/other-model"


# --- the answer ----------------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        '{"text": "Look at vibration first."}',
        '```json\n{"text": "Look at vibration first."}\n```',
        '<think>The user wants advice.</think>\n{"text": "Look at vibration first."}',
        '  \n{"text": "Look at vibration first."}\n',
    ],
)
def test_a_valid_reply_becomes_the_typed_answer(content):
    ask, _ = client(chat(content))
    assert ask.ask("s", "p", Lesson) == Lesson(text="Look at vibration first.")


@pytest.mark.parametrize(
    "content",
    [
        "Look at vibration first.",  # not JSON
        '{"text": ""}',  # breaks the type's rules
        '{"text": "x", "category": "bearing"}',  # a field the type does not have
        '[{"text": "x"}]',  # not one object
    ],
)
def test_an_invalid_reply_is_refused_not_repaired(content):
    ask, _ = client(chat(content))
    with pytest.raises(ValueError):
        ask.ask("s", "p", Lesson)


@pytest.mark.parametrize(
    "body", [b"not json", b'{"choices": []}', b'{"choices": [{"message": {}}]}']
)
def test_a_malformed_service_reply_is_refused(body):
    ask, _ = client(body)
    with pytest.raises(ValueError):
        ask.ask("s", "p", Lesson)


# --- failures say nothing secret ------------------------------------------------


def test_an_http_error_reports_only_its_status():
    error = urllib.error.HTTPError(NVIDIA_URL, 401, "Unauthorized", {}, None)
    ask, _ = client(error)
    with pytest.raises(ModelError) as raised:
        ask.ask("s", "p", Lesson)
    assert "401" in str(raised.value)
    assert KEY not in str(raised.value)


def test_an_unreachable_service_is_a_model_error():
    ask, _ = client(urllib.error.URLError("connection refused"))
    with pytest.raises(ModelError):
        ask.ask("s", "p", Lesson)


def test_a_timeout_is_a_model_error():
    ask, _ = client(TimeoutError("timed out"))
    with pytest.raises(ModelError):
        ask.ask("s", "p", Lesson)


def test_the_key_never_appears_in_the_client_representation():
    ask, _ = client()
    assert KEY not in repr(ask)


# --- settings --------------------------------------------------------------------


def test_from_settings_needs_a_key_and_names_it(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(ModelError, match="NVIDIA_API_KEY"):
        NvidiaClient.from_settings(Settings(_env_file=None))


def test_from_settings_uses_the_key_and_model(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    monkeypatch.setenv("NVIDIA_MODEL", "nvidia/other-model")
    transport = FakeTransport(chat('{"text": "x"}'))
    ask = NvidiaClient.from_settings(Settings(_env_file=None), transport=transport)
    ask.ask("s", "p", Lesson)
    url, headers, body, _ = transport.requests[0]
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert body["model"] == "nvidia/other-model"


def test_the_model_setting_defaults_and_the_key_is_masked(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.nvidia_model == DEFAULT_MODEL
    assert KEY not in repr(settings)
    assert KEY not in settings.model_dump_json()


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_key_is_treated_as_missing(monkeypatch, value):
    monkeypatch.setenv("NVIDIA_API_KEY", value)
    assert Settings(_env_file=None).nvidia_api_key is None
