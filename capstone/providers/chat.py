# One request to any provider's chat endpoint, one validated answer back.
# Responsibility: send a prompt, refuse any reply that is not the expected type.
"""The client behind the model policy, for every provider in scope.

    clients = clients_for_jobs()                    # one client per question
    answer = clients["decide"].ask(system, prompt, Decision)

All six providers offer a chat endpoint in the same OpenAI-style shape, so
one client reaches them all: only the address, the key and the model name
differ (`PROVIDERS`). The client uses just the common part of that shape:
a system and a user message, temperature 0, a Bearer key, and the reply's
text. It asks for one JSON object matching the answer type's schema and
validates the reply against that type. Anything else raises `ValueError`
and is never repaired or guessed: the loop already treats a `ValueError`
from a policy as an invalid decision.

A failure to reach a service raises `ModelError`, which carries only a
short reason, never the key or the response body. Sending goes through a
`Transport` function, so tests pass a fake and never touch the network.

`FallbackClient` is what each job is given. It handles an outage, never a
bad reply: an unreachable or overloaded service is asked once more, then
the next model in its list (FALLBACK_MODEL) is asked. A reply that breaks
the answer type is the model's own mistake and goes straight to the loop.

One question has a time limit. A request waits at most `timeout` seconds
(15 by default), and `FallbackClient` gives the whole question, retries
and fallback included, `max_seconds` (20 by default), handing each request
only the time left; a caller can shorten that for one question, never
lengthen it. A service that was reached but did not answer in time is
reported as timed out, not as unreachable.
"""

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from capstone.contracts import Contract
from capstone.settings import Settings, get_settings

# (url, headers, body, timeout in seconds) -> response body
Transport = Callable[[str, dict[str, str], bytes, float], bytes]
Answer = TypeVar("Answer", bound=BaseModel)

_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class ModelError(RuntimeError):
    """A model service could not be reached, refused, or is not configured.

    `transient` is True when asking again later might work: the service was
    unreachable, timed out, was overloaded (HTTP 429) or failed (HTTP 5xx).
    A rejected key or a bad request fails the same way every time.
    """

    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class Attempt(Contract):
    """One model asked during one question, and what came of it.

    "answered" and "invalid reply" are the model's own doing: an invalid
    reply counts against its reasoning. Anything else is the reason it gave
    no answer (an outage, a timeout, a rejected key), which counts only
    against the service's uptime.
    """

    model: str
    outcome: str
    # How long the request took, on the client's clock. The pause before a
    # retry is not included: it is the client waiting, not the model.
    seconds: float | None = None


@dataclass(frozen=True)
class Provider:
    url: str  # may contain {account}
    key_setting: str  # the environment name of its key


PROVIDERS = {
    "nvidia": Provider(
        "https://integrate.api.nvidia.com/v1/chat/completions", "NVIDIA_API_KEY"
    ),
    "groq": Provider("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY"),
    "mistral": Provider(
        "https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY"
    ),
    "gemini": Provider(
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "GEMINI_API_KEY",
    ),
    "cohere": Provider(
        "https://api.cohere.ai/compatibility/v1/chat/completions", "COHERE_API_KEY"
    ),
    "cloudflare": Provider(
        "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions",
        "CLOUDFLARE_API_TOKEN",
    ),
}

# The seven policy questions, each of which can be given to its own model.
JOBS = (
    "plan",
    "decide",
    "interpret",
    "hypothesize",
    "conclude",
    "judge_verification",
    "write_lesson",
)
_JOB_SETTING = {
    "plan": "plan_model",
    "decide": "decide_model",
    "interpret": "interpret_model",
    "hypothesize": "hypothesize_model",
    "conclude": "conclude_model",
    "judge_verification": "judge_model",
    "write_lesson": "lesson_model",
}


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def reply_text(body: bytes) -> str:
    """The assistant's text in a chat-completions reply. ValueError if absent.

    A reply cut off at the output-token limit is refused as such: half a
    JSON object is not an answer, and saying why helps set the limit.
    """
    try:
        choice = json.loads(body)["choices"][0]
        content = choice["message"]["content"]
    except (ValueError, LookupError, TypeError) as error:
        raise ValueError("the model service sent a malformed reply") from error
    if isinstance(choice, dict) and choice.get("finish_reason") == "length":
        raise ValueError("the model reply was cut off at the output-token limit")
    if not isinstance(content, str):
        raise ValueError("the model reply has no text")
    return content


def answer_json(text: str) -> str:
    """The JSON object in a reply: thinking and a code fence removed, nothing else."""
    text = _THINKING.sub("", text).strip()
    fenced = _FENCE.match(text)
    return fenced.group(1) if fenced else text


class ChatClient:
    def __init__(
        self,
        url: str,
        api_key: str,
        model: str,
        *,
        transport: Transport = urllib_transport,
        timeout: float = 15.0,
        max_output_tokens: int | None = None,
    ):
        if max_output_tokens is not None and max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1")
        self.url = url
        self._api_key = api_key
        self.model = model
        self._transport = transport
        self.timeout = timeout
        # The most tokens one reply may use, thinking included. None: the
        # provider's own limit.
        self.max_output_tokens = max_output_tokens

    def __repr__(self) -> str:
        return f"ChatClient(url={self.url!r}, model={self.model!r})"

    def ask(
        self,
        system: str,
        prompt: str,
        answer_type: type[Answer],
        *,
        timeout: float | None = None,
        max_seconds: float | None = None,
    ) -> Answer:
        """One question, one answer of `answer_type`. ValueError if the reply is not one.

        `timeout` can shorten this request's wait below the client's own,
        never lengthen it. `max_seconds`, the policy's limit on a whole
        question, does the same: here the question is this one request.
        """
        limit = min(x for x in (self.timeout, timeout, max_seconds) if x is not None)
        schema = json.dumps(answer_type.model_json_schema())
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": f"{system}\n\nReply with exactly one JSON object "
                    f"and nothing else. It must match this JSON schema:\n{schema}",
                },
                {"role": "user", "content": prompt},
            ],
        }
        if self.max_output_tokens is not None:
            body["max_tokens"] = self.max_output_tokens
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            raw = self._transport(self.url, headers, json.dumps(body).encode(), limit)
        except urllib.error.HTTPError as error:
            raise ModelError(
                f"the model service answered HTTP {error.code}",
                transient=error.code == 429 or error.code >= 500,
            ) from None
        except TimeoutError:
            # Reached, but no answer in time: a slow model, not a missing one.
            raise ModelError("the model service timed out", transient=True) from None
        except (urllib.error.URLError, OSError):
            raise ModelError(
                "the model service could not be reached", transient=True
            ) from None
        return answer_type.model_validate_json(answer_json(reply_text(raw)))


class FallbackClient:
    """One job's models in order. An outage moves on; a bad reply does not.

    Each model is asked, and asked `retries` more times after a transient
    failure. A failure that will not change (a rejected key) moves straight
    to the next model. A reply that breaks the answer type raises
    `ValueError` at once: retrying or switching models would hide which
    model got it wrong. When no model answers, one `ModelError` names each
    failure.

    The whole question gets `max_seconds`: each request is given only the
    time left, and once none is left no further model is asked.
    """

    def __init__(
        self,
        clients: Sequence[ChatClient],
        *,
        retries: int = 1,
        retry_delay: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        max_seconds: float = 20.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not clients:
            raise ValueError("a job needs at least one model")
        self.clients = tuple(clients)
        self.retries = retries
        self.retry_delay = retry_delay
        self._sleep = sleep
        self.max_seconds = max_seconds
        self._clock = clock
        # The model that gave the latest answer, so a record can name it.
        self.answered_by: str | None = None
        # Every model asked in the latest question, in order, and its outcome.
        self.attempts: tuple[Attempt, ...] = ()

    @property
    def model(self) -> str:
        """The model asked first."""
        return self.clients[0].model

    @property
    def url(self) -> str:
        return self.clients[0].url

    def __repr__(self) -> str:
        return f"FallbackClient({[c.model for c in self.clients]!r})"

    def ask(
        self,
        system: str,
        prompt: str,
        answer_type: type[Answer],
        *,
        max_seconds: float | None = None,
    ) -> Answer:
        """One question within its time. `max_seconds` can only shorten it."""
        self.answered_by = None
        attempts: list[Attempt] = []
        failures = []
        limit = (
            self.max_seconds
            if max_seconds is None
            else min(max_seconds, self.max_seconds)
        )
        deadline = self._clock() + limit
        try:
            for client in self.clients:
                for attempt in range(1 + self.retries):
                    pause = self.retry_delay if attempt else 0.0
                    left = deadline - self._clock() - pause
                    if left <= 0:
                        failures.append(f"{client.model}: not asked, no time left")
                        raise no_answer(failures)
                    if pause:
                        self._sleep(pause)
                    started = self._clock()

                    def tried(outcome: str) -> Attempt:
                        return Attempt(
                            model=client.model,
                            outcome=outcome,
                            seconds=round(self._clock() - started, 3),
                        )

                    try:
                        answer = client.ask(system, prompt, answer_type, timeout=left)
                    except ModelError as error:
                        failures.append(f"{client.model}: {error}")
                        attempts.append(tried(str(error)))
                        if not error.transient:
                            break
                        continue
                    except ValueError:
                        attempts.append(tried("invalid reply"))
                        raise
                    attempts.append(tried("answered"))
                    self.answered_by = client.model
                    return answer
            raise no_answer(failures)
        finally:
            self.attempts = tuple(attempts)


def no_answer(failures: list[str]) -> ModelError:
    """The error for a question no model answered, naming each failure."""
    return ModelError("no model service answered (" + "; ".join(failures) + ")")


def client_for(
    reference: str,
    settings: Settings | None = None,
    *,
    transport: Transport = urllib_transport,
) -> ChatClient:
    """A client for "provider/model". ModelError names any missing setting."""
    settings = settings or get_settings()
    name, _, model = reference.partition("/")
    if name not in PROVIDERS or not model:
        raise ModelError(
            f"unknown model {reference!r}: use provider/model with a provider "
            f"from {sorted(PROVIDERS)}"
        )
    provider = PROVIDERS[name]
    key = getattr(settings, provider.key_setting.lower())
    if key is None:
        raise ModelError(f"set {provider.key_setting} in the local .env or environment")
    url = provider.url
    if "{account}" in url:
        if settings.cloudflare_account_id is None:
            raise ModelError(
                "set CLOUDFLARE_ACCOUNT_ID in the local .env or environment"
            )
        url = url.format(account=settings.cloudflare_account_id)
    return ChatClient(
        url,
        key.get_secret_value(),
        model,
        transport=transport,
        timeout=settings.model_request_seconds,
        max_output_tokens=settings.model_max_output_tokens,
    )


def clients_for_jobs(
    settings: Settings | None = None, *, transport: Transport = urllib_transport
) -> dict[str, FallbackClient]:
    """One client per policy question, from the job table in settings.

    Each job asks its own model, then FALLBACK_MODEL if one is set.
    """
    settings = settings or get_settings()
    clients = {}
    for job in JOBS:
        references = [getattr(settings, _JOB_SETTING[job]) or settings.default_model]
        if settings.fallback_model and settings.fallback_model not in references:
            references.append(settings.fallback_model)
        clients[job] = FallbackClient(
            [client_for(r, settings, transport=transport) for r in references],
            retries=settings.model_retries,
            max_seconds=settings.model_question_seconds,
        )
    return clients
