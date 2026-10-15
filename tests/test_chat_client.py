"""The generic chat client and the job table, with a fake transport.

No test touches the network or a real key.
"""

import json
import urllib.error

import pytest

from capstone.agent.policy import Lesson
from capstone.providers.chat import (
    JOBS,
    PROVIDERS,
    ChatClient,
    ModelError,
    client_for,
    clients_for_jobs,
)
from capstone.settings import DEFAULT_MODEL, Settings

KEY = "test-key-not-real"
ALL_KEYS = (
    "NVIDIA_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "GEMINI_API_KEY",
    "COHERE_API_KEY",
    "CLOUDFLARE_API_TOKEN",
)
JOB_SETTINGS = (
    "DEFAULT_MODEL",
    "PLAN_MODEL",
    "DECIDE_MODEL",
    "INTERPRET_MODEL",
    "HYPOTHESIZE_MODEL",
    "CONCLUDE_MODEL",
    "JUDGE_MODEL",
    "LESSON_MODEL",
    "CLOUDFLARE_ACCOUNT_ID",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in (*ALL_KEYS, *JOB_SETTINGS):
        monkeypatch.delenv(name, raising=False)


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


def client(*replies, url="https://example.test/v1/chat/completions", model="m"):
    transport = FakeTransport(*replies)
    return ChatClient(url, KEY, model, transport=transport), transport


def settings(**values):
    return Settings(_env_file=None, **values)


# --- the request ---------------------------------------------------------------


def test_one_request_carries_the_model_the_prompt_and_the_answer_shape():
    ask, transport = client(chat('{"text": "Look at vibration first."}'))
    ask.ask("You investigate a factory.", "What next?", Lesson)
    [(url, headers, body, timeout)] = transport.requests
    assert url == "https://example.test/v1/chat/completions"
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert headers["Content-Type"] == "application/json"
    assert body["model"] == "m"
    assert body["temperature"] == 0
    system, user = body["messages"]
    assert system["role"] == "system"
    assert system["content"].startswith("You investigate a factory.")
    assert json.dumps(Lesson.model_json_schema()) in system["content"]
    assert user == {"role": "user", "content": "What next?"}
    assert timeout > 0


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
    error = urllib.error.HTTPError(
        "https://example.test", 401, "Unauthorized", {}, None
    )
    ask, _ = client(error)
    with pytest.raises(ModelError) as raised:
        ask.ask("s", "p", Lesson)
    assert "401" in str(raised.value)
    assert KEY not in str(raised.value)


@pytest.mark.parametrize(
    "error", [urllib.error.URLError("connection refused"), TimeoutError("timed out")]
)
def test_an_unreachable_service_is_a_model_error(error):
    ask, _ = client(error)
    with pytest.raises(ModelError):
        ask.ask("s", "p", Lesson)


def test_the_key_never_appears_in_the_client_representation():
    ask, _ = client()
    assert KEY not in repr(ask)


# --- the provider table ---------------------------------------------------------


def test_the_six_providers_in_scope_and_no_others():
    assert set(PROVIDERS) == {
        "nvidia",
        "groq",
        "mistral",
        "gemini",
        "cohere",
        "cloudflare",
    }
    for provider in PROVIDERS.values():
        assert provider.url.startswith("https://")
        assert provider.url.endswith("/chat/completions")


@pytest.mark.parametrize(
    "provider,key_setting,expected_url",
    [
        (
            "nvidia",
            "NVIDIA_API_KEY",
            "https://integrate.api.nvidia.com/v1/chat/completions",
        ),
        ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions"),
        ("mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions"),
        (
            "gemini",
            "GEMINI_API_KEY",
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        ),
        (
            "cohere",
            "COHERE_API_KEY",
            "https://api.cohere.ai/compatibility/v1/chat/completions",
        ),
    ],
)
def test_each_provider_gets_its_own_address_and_key(
    monkeypatch, provider, key_setting, expected_url
):
    monkeypatch.setenv(key_setting, KEY)
    transport = FakeTransport(chat('{"text": "x"}'))
    ask = client_for(f"{provider}/some-model", settings(), transport=transport)
    ask.ask("s", "p", Lesson)
    url, headers, body, _ = transport.requests[0]
    assert url == expected_url
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert body["model"] == "some-model"


def test_cloudflare_needs_the_account_id(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", KEY)
    with pytest.raises(ModelError, match="CLOUDFLARE_ACCOUNT_ID"):
        client_for("cloudflare/@cf/some/model", settings())
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "abc123")
    transport = FakeTransport(chat('{"text": "x"}'))
    client_for("cloudflare/@cf/some/model", settings(), transport=transport).ask(
        "s", "p", Lesson
    )
    url, _, body, _ = transport.requests[0]
    assert url == (
        "https://api.cloudflare.com/client/v4/accounts/abc123/ai/v1/chat/completions"
    )
    assert body["model"] == "@cf/some/model"


def test_the_model_id_keeps_everything_after_the_provider(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    ask = client_for("nvidia/nvidia/nemotron-x", settings())
    assert ask.model == "nvidia/nemotron-x"


@pytest.mark.parametrize(
    "reference", ["openai/gpt-x", "anthropic/claude-x", "nvidia", "nvidia/", ""]
)
def test_an_unknown_provider_or_bad_reference_is_refused(monkeypatch, reference):
    for name in ALL_KEYS:
        monkeypatch.setenv(name, KEY)
    with pytest.raises(ModelError):
        client_for(reference, settings())


def test_a_missing_key_names_the_setting_not_the_value():
    with pytest.raises(ModelError, match="GROQ_API_KEY"):
        client_for("groq/some-model", settings())


# --- the job table ----------------------------------------------------------------


def test_the_jobs_are_the_seven_policy_questions():
    assert JOBS == (
        "plan",
        "decide",
        "interpret",
        "hypothesize",
        "conclude",
        "judge_verification",
        "write_lesson",
    )


def test_every_job_uses_the_default_model_unless_named(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    clients = clients_for_jobs(settings())
    assert set(clients) == set(JOBS)
    expected = DEFAULT_MODEL.split("/", 1)[1]
    assert {c.model for c in clients.values()} == {expected}


def test_any_job_can_be_given_to_any_provider(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    monkeypatch.setenv("MISTRAL_API_KEY", KEY)
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    monkeypatch.setenv("JUDGE_MODEL", "mistral/judge-model")
    monkeypatch.setenv("DECIDE_MODEL", "groq/decide-model")
    clients = clients_for_jobs(settings())
    assert clients["judge_verification"].model == "judge-model"
    assert clients["judge_verification"].url.startswith("https://api.mistral.ai/")
    assert clients["decide"].model == "decide-model"
    assert clients["plan"].model == DEFAULT_MODEL.split("/", 1)[1]


def test_only_providers_in_use_need_a_key(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)  # every other key is missing
    assert len(clients_for_jobs(settings())) == len(JOBS)
    monkeypatch.setenv("LESSON_MODEL", "cohere/command-x")
    with pytest.raises(ModelError, match="COHERE_API_KEY"):
        clients_for_jobs(settings())


def test_keys_are_masked_in_settings(monkeypatch):
    for name in ALL_KEYS:
        monkeypatch.setenv(name, f"{name}-{KEY}")
    loaded = settings()
    for name in ALL_KEYS:
        assert f"{name}-{KEY}" not in repr(loaded)
        assert f"{name}-{KEY}" not in loaded.model_dump_json()


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_key_is_treated_as_missing(monkeypatch, value):
    monkeypatch.setenv("GROQ_API_KEY", value)
    assert settings().groq_api_key is None
