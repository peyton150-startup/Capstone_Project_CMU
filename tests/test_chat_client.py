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
    USER_AGENT,
    ChatClient,
    FallbackClient,
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
    "FALLBACK_MODEL",
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
    # Not urllib's own "Python-urllib/3.x", which Groq refuses with HTTP 403.
    assert headers["User-Agent"] == USER_AGENT
    assert not headers["User-Agent"].startswith("Python-urllib")
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


# --- an outage is retried, then handed to the fallback model ---------------------

UNREACHABLE = urllib.error.URLError("connection refused")


def http_error(code):
    return urllib.error.HTTPError("https://example.test", code, "error", {}, None)


def fallback(*clients, retries=1):
    waits = []
    return FallbackClient(clients, retries=retries, sleep=waits.append), waits


@pytest.mark.parametrize(
    ("error", "transient"),
    [
        (UNREACHABLE, True),
        (TimeoutError("timed out"), True),
        (http_error(429), True),
        (http_error(503), True),
        (http_error(401), False),
        (http_error(400), False),
    ],
)
def test_only_an_outage_is_marked_worth_retrying(error, transient):
    ask, _ = client(error)
    with pytest.raises(ModelError) as raised:
        ask.ask("s", "p", Lesson)
    assert raised.value.transient is transient


def test_an_outage_is_retried_once_on_the_same_model():
    primary, transport = client(UNREACHABLE, chat('{"text": "advice"}'), model="a")
    ask, waits = fallback(primary)
    assert ask.ask("s", "p", Lesson) == Lesson(text="advice")
    assert len(transport.requests) == 2
    assert len(waits) == 1  # it paused once before trying again
    assert ask.answered_by == "a"


def test_a_refused_reply_is_not_retried_or_handed_on():
    primary, first = client(chat("not json"), model="a")
    backup, second = client(chat('{"text": "advice"}'), model="b")
    ask, _ = fallback(primary, backup)
    with pytest.raises(ValueError):
        ask.ask("s", "p", Lesson)
    assert len(first.requests) == 1
    assert second.requests == []
    assert ask.answered_by is None


def test_after_the_retry_fails_the_fallback_model_answers():
    primary, first = client(UNREACHABLE, http_error(503), model="a")
    backup, second = client(chat('{"text": "advice"}'), model="b")
    ask, _ = fallback(primary, backup)
    assert ask.ask("s", "p", Lesson) == Lesson(text="advice")
    assert len(first.requests) == 2
    assert len(second.requests) == 1
    assert ask.answered_by == "b"


def test_a_rejected_key_skips_the_retry_and_goes_to_the_fallback():
    primary, first = client(http_error(401), model="a")
    backup, _ = client(chat('{"text": "advice"}'), model="b")
    ask, waits = fallback(primary, backup)
    assert ask.ask("s", "p", Lesson) == Lesson(text="advice")
    assert len(first.requests) == 1
    assert waits == []


def test_when_no_model_answers_the_error_names_each_failure_but_no_key():
    primary, _ = client(UNREACHABLE, UNREACHABLE, model="a")
    backup, _ = client(http_error(401), model="b")
    ask, _ = fallback(primary, backup)
    with pytest.raises(ModelError) as raised:
        ask.ask("s", "p", Lesson)
    message = str(raised.value)
    assert "a: the model service could not be reached" in message
    assert "b: the model service answered HTTP 401" in message
    assert KEY not in message
    assert raised.value.transient is False


# --- which models were tried, and why each gave no answer ----------------------------


def test_every_model_tried_is_recorded_even_when_a_later_one_answers():
    primary, _ = client(TimeoutError("slow"), TimeoutError("slow"), model="groq")
    backup, _ = client(chat('{"text": "advice"}'), model="mistral")
    ask, _ = fallback(primary, backup)
    ask.ask("s", "p", Lesson)
    assert [(a.model, a.outcome) for a in ask.attempts] == [
        ("groq", "the model service timed out"),
        ("groq", "the model service timed out"),
        ("mistral", "answered"),
    ]


def test_an_invalid_reply_is_recorded_against_the_model_that_sent_it():
    """Groq times out twice, then Mistral answers with an invalid reply: the
    timeouts are uptime, the invalid reply is Mistral's reasoning."""
    primary, _ = client(TimeoutError("slow"), TimeoutError("slow"), model="groq")
    backup, _ = client(chat("not json"), model="mistral")
    ask, _ = fallback(primary, backup)
    with pytest.raises(ValueError):
        ask.ask("s", "p", Lesson)
    assert [(a.model, a.outcome) for a in ask.attempts] == [
        ("groq", "the model service timed out"),
        ("groq", "the model service timed out"),
        ("mistral", "invalid reply"),
    ]
    assert ask.answered_by is None


def test_each_question_starts_a_fresh_record():
    primary, _ = client(UNREACHABLE, chat('{"text": "a"}'), chat('{"text": "b"}'))
    ask, _ = fallback(primary)
    ask.ask("s", "p", Lesson)
    ask.ask("s", "p", Lesson)
    assert [a.outcome for a in ask.attempts] == ["answered"]


# --- one question has a time limit -------------------------------------------------


class Clock:
    """Virtual seconds: a pause takes its length, a request the time it is given."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def silent(clock, model):
    """A client whose service never answers: every request runs out of time."""
    given = []

    def transport(url, headers, body, timeout):
        given.append(timeout)
        clock.now += timeout
        raise TimeoutError("timed out")

    return ChatClient("https://example.test", KEY, model, transport=transport), given


def test_a_service_that_answers_too_late_is_reported_as_timed_out():
    ask, _ = client(TimeoutError("timed out"))
    with pytest.raises(ModelError, match="the model service timed out") as raised:
        ask.ask("s", "p", Lesson)
    assert raised.value.transient is True


def test_one_question_gets_twenty_seconds_retries_and_fallback_included():
    clock = Clock()
    primary, first = silent(clock, "a")
    backup, second = silent(clock, "b")
    ask = FallbackClient([primary, backup], sleep=clock.sleep, clock=clock)
    with pytest.raises(ModelError) as raised:
        ask.ask("s", "p", Lesson)
    assert clock.now == 20.0  # it used to take 244: 60 s per request, four requests
    # Each model gets half: a's retry would eat b's time, so b is asked instead.
    assert first == [10.0]
    assert second == [10.0]
    assert "b: not asked again, no time left" in str(raised.value)


def test_a_slow_first_model_leaves_the_fallback_its_share_of_the_question():
    clock = Clock()
    primary, first = silent(clock, "a")
    primary.timeout = 60.0  # a request may wait 60 s, the question 90 s
    backup, _ = client(chat('{"text": "ok"}'), model="b")
    ask = FallbackClient(
        [primary, backup], sleep=clock.sleep, clock=clock, max_seconds=90.0
    )
    assert ask.ask("s", "p", Lesson).text == "ok"
    assert first == [45.0]  # not 60 + a retry, which left the fallback nothing
    assert ask.answered_by == "b"
    assert [a.outcome for a in ask.attempts] == [
        "the model service timed out",
        "answered",
    ]


def test_a_caller_can_shorten_a_question_but_never_lengthen_it():
    clock = Clock()
    primary, given = silent(clock, "a")
    ask = FallbackClient([primary], sleep=clock.sleep, clock=clock)
    with pytest.raises(ModelError):
        ask.ask("s", "p", Lesson, max_seconds=7.0)
    assert clock.now == 7.0 and given == [7.0]  # the investigation's 7 s, not 20

    clock.now, given[:] = 0.0, []
    with pytest.raises(ModelError):
        ask.ask("s", "p", Lesson, max_seconds=600.0)
    assert clock.now == 20.0  # its own 20 s still hold


def test_a_question_with_no_time_left_asks_no_model():
    clock = Clock()
    primary, given = silent(clock, "a")
    ask = FallbackClient([primary], sleep=clock.sleep, clock=clock)
    with pytest.raises(ModelError, match="not asked, no time left"):
        ask.ask("s", "p", Lesson, max_seconds=0.0)
    assert given == [] and ask.attempts == ()


def test_one_request_is_held_to_the_question_limit_too():
    ask, transport = client(chat('{"text": "advice"}'))
    ask.ask("s", "p", Lesson, max_seconds=4.0)
    [(_, _, _, timeout)] = transport.requests
    assert timeout == 4.0


def test_each_attempt_records_how_long_the_model_took_but_not_the_pause():
    clock = Clock()
    primary, _ = silent(clock, "a")

    def answers_in_three_seconds(url, headers, body, timeout):
        clock.now += 3.0
        return chat('{"text": "advice"}')

    backup = ChatClient(
        "https://example.test", KEY, "b", transport=answers_in_three_seconds
    )
    ask = FallbackClient(
        [primary, backup], retries=0, sleep=clock.sleep, clock=clock, max_seconds=60
    )
    ask.ask("s", "p", Lesson)
    assert [(a.model, a.outcome, a.seconds) for a in ask.attempts] == [
        ("a", "the model service timed out", 15.0),
        ("b", "answered", 3.0),
    ]


def test_a_request_never_waits_longer_than_its_client_allows():
    ask, transport = client(chat('{"text": "advice"}'))
    ask.ask("s", "p", Lesson, timeout=600)
    [(_, _, _, timeout)] = transport.requests
    assert timeout == ask.timeout == 15.0


def test_a_job_falls_back_to_the_fallback_model_when_one_is_set(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    assert [c.model for c in clients_for_jobs(settings())["decide"].clients] == [
        DEFAULT_MODEL.split("/", 1)[1]
    ]
    monkeypatch.setenv("FALLBACK_MODEL", "groq/backup-model")
    monkeypatch.setenv("PLAN_MODEL", "groq/backup-model")
    clients = clients_for_jobs(settings())
    assert [c.model for c in clients["decide"].clients] == [
        DEFAULT_MODEL.split("/", 1)[1],
        "backup-model",
    ]
    # A job whose own model is the fallback is not asked twice.
    assert [c.model for c in clients["plan"].clients] == ["backup-model"]


# --- limits on every model question (MVP_SCOPE.md section 3) -------------------


def test_the_output_token_limit_is_sent_with_each_request():
    transport = FakeTransport(chat('{"text": "Look first."}'))
    limited = ChatClient(
        "https://x.test", KEY, "m", transport=transport, max_output_tokens=300
    )
    limited.ask("s", "p", Lesson)
    assert transport.requests[0][2]["max_tokens"] == 300
    ask, transport = client(chat('{"text": "Look first."}'))
    ask.ask("s", "p", Lesson)
    assert "max_tokens" not in transport.requests[0][2]


def test_a_reply_cut_off_at_the_limit_is_refused_and_says_so():
    body = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": '{"text": "Lo'},
                }
            ]
        }
    ).encode()
    ask, _ = client(body)
    with pytest.raises(ValueError, match="output-token limit"):
        ask.ask("s", "p", Lesson)


def test_the_limits_come_from_settings(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    configured = settings(
        MODEL_MAX_OUTPUT_TOKENS="512",
        MODEL_REQUEST_SECONDS="9",
        MODEL_QUESTION_SECONDS="30",
        MODEL_RETRIES="3",
    )
    client_ = client_for(DEFAULT_MODEL, configured)
    assert (client_.max_output_tokens, client_.timeout) == (512, 9.0)
    job = clients_for_jobs(configured)["decide"]
    assert (job.retries, job.max_seconds) == (3, 30.0)
    defaults = settings()
    assert defaults.model_max_output_tokens == 8192
    assert (defaults.model_request_seconds, defaults.model_question_seconds) == (
        45.0,
        90.0,
    )
    assert defaults.model_retries == 1
    with pytest.raises(ValueError):
        settings(MODEL_MAX_OUTPUT_TOKENS="0")
