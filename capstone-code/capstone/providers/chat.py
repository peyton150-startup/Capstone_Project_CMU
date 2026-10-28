# One request to any provider's chat endpoint, one validated answer back.
# Responsibility: send a prompt, refuse any reply that is not the expected type.
"""The client behind the model policy, for every provider in scope.

    clients = clients_for_jobs()                    # one client per question
    answer = clients["decide"].ask(system, prompt, Decision)

Every provider offers a chat endpoint in the same OpenAI-style shape, so
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
only the time left, and each model an equal share of it so the fallback is
still asked; a caller can shorten that for one question, never lengthen it. A service that was reached but did not answer in time is
reported as timed out, not as unreachable.
"""

import json
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from capstone.contracts import Contract
from capstone.settings import Settings, critic_models, fallback_models, get_settings

# (url, headers, body, timeout in seconds) -> response body
Transport = Callable[[str, dict[str, str], bytes, float], bytes]
Answer = TypeVar("Answer", bound=BaseModel)
Result = TypeVar("Result")

USER_AGENT = "capstone-agent/0.1"

_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class ModelError(RuntimeError):
    """A model service could not be reached, refused, or is not configured.

    `transient` is True when asking again later might work: the service was
    unreachable, timed out, was overloaded (HTTP 429) or failed (HTTP 5xx).
    A rejected key or a bad request fails the same way every time.

    `out_of_time` is True when no answer came because the time the caller
    allowed ran out (less than a retry pause was left), not the question's
    own limit: the caller's clock, not the service, is why.
    """

    def __init__(
        self, message: str, *, transient: bool = False, out_of_time: bool = False
    ):
        super().__init__(message)
        self.transient = transient
        self.out_of_time = out_of_time


# The start of every invalid reply's outcome; the reason follows after ": ".
INVALID_REPLY = "invalid reply"


def invalid_outcome(error: ValueError) -> str:
    """ "invalid reply: <why>", short and without the reply's content.

    Why is one of: the reply was cut off at the output-token limit, it was not
    JSON, or it was JSON of the wrong shape (the first field at fault and what
    was wrong with it). The reply itself never goes into the record.
    """
    # Variables:
    #   error: The reason a reply was refused.
    #   problems: Each field the reply got wrong, if it was JSON of the wrong shape.
    #   first: The first problem, which is the one reported.
    #   where: The field at fault.
    #   more: A note of how many further problems there were.
    #   why: The short reason, without the reply's content.
    if isinstance(error, ValidationError):
        problems = error.errors(include_input=False, include_url=False)
        if any(p["type"] == "json_invalid" for p in problems):
            why = "not valid JSON"
        else:
            first = problems[0]
            where = ".".join(str(part) for part in first["loc"]) or "the answer"
            more = f" (and {len(problems) - 1} more)" if len(problems) > 1 else ""
            why = f"wrong shape: {where}: {first['msg']}{more}"
    else:
        why = str(error)
        for prefix in ("the model reply was ", "the model reply ", "the model "):
            why = why.removeprefix(prefix)
    return f"{INVALID_REPLY}: {why[:160]}"


def is_model_outcome(outcome: str) -> bool:
    """The model's own doing (an answer, or an invalid reply with or without
    its reason), as opposed to a service failure."""
    return outcome == "answered" or outcome.split(":", 1)[0] == INVALID_REPLY


class Attempt(Contract):
    """One model asked during one question, and what came of it.

    "answered" and "invalid reply: <why>" are the model's own doing: an
    invalid reply counts against its reasoning (`is_model_outcome`). Records
    from before 2026-10-21 say just "invalid reply". Anything else is the
    reason it gave no answer (an outage, a timeout, a rejected key), which
    counts only against the service's uptime.
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
    # Ask the service itself to keep the reply to the answer type's JSON
    # schema (the standard `response_format` of type "json_schema"). Only
    # where it was checked live: NVIDIA's hosted API on 2026-10-21. The reply
    # is still validated against the type, as for every provider.
    structured_output: bool = False
    # The most output tokens the service accepts in one request, if it has
    # a limit below the project's MODEL_MAX_OUTPUT_TOKENS. A larger request
    # is refused outright (HTTP 400), so it is lowered to this instead.
    max_output_tokens: int | None = None


PROVIDERS = {
    "nvidia": Provider(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        "NVIDIA_API_KEY",
        structured_output=True,
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
        "https://api.cohere.ai/compatibility/v1/chat/completions",
        "COHERE_API_KEY",
        # Command A refused 16,384 on 2026-10-26: "max tokens must be less than
        # or equal to 8192, the maximum output length for this model".
        max_output_tokens=8192,
    ),
    "cloudflare": Provider(
        "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions",
        "CLOUDFLARE_API_TOKEN",
    ),
    # Two routers, added by the developer on 2026-10-21 for comparing larger
    # models. Each passes the model name on, so a reference names the model
    # the router lists: "requesty/nvidia/nemotron-3-ultra-550b-a55b",
    # "xkiro/qwen/qwen3.8-max:free". Both also list Anthropic and OpenAI
    # models, which stay out of this project (AGENTS.md section 9).
    "requesty": Provider(
        "https://router.requesty.ai/v1/chat/completions", "REQUESTY_API_KEY"
    ),
    "xkiro": Provider("https://api.xkiro.com/v1/chat/completions", "XKIRO_API_KEY"),
    # A third router (added 2026-10-21). Its free allowance is 100,000 tokens
    # a day, less than one investigation, so it is for a support agent only.
    "llm7": Provider("https://api.llm7.io/v1/chat/completions", "LLM7_API_KEY"),
    # Kilo Code's gateway (added 2026-10-21): free models marked ":free", e.g.
    # "kilo/minimax/minimax-m3.1-flash:free"; its free models may train on
    # prompts (ours are simulator data only).
    "kilo": Provider(
        "https://api.kilo.ai/api/gateway/chat/completions", "KILO_CODE_API_KEY"
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


def run_with_deadline(work: Callable[[], Result], seconds: float) -> Result:
    """`work()`'s result, or TimeoutError once `seconds` have passed.

    `work` runs in a background (daemon) thread and the caller waits at most
    `seconds`. On time it gets the result, or the exception `work` raised. Past
    the deadline the caller gets TimeoutError and moves on; the thread is left
    to end by itself, and whatever it later returns is never read.
    """
    # Variables:
    #   work: The slow call to run, such as one network request.
    #   seconds: The most the caller will wait for it.
    #   outcome: A queue that carries the result, or the error, back from the background
    #     thread.
    outcome: queue.SimpleQueue = queue.SimpleQueue()

    def run() -> None:
        try:
            outcome.put((True, work()))
        except BaseException as error:  # handed to the caller below
            outcome.put((False, error))

    threading.Thread(target=run, daemon=True, name="deadline").start()
    try:
        finished, value = outcome.get(timeout=seconds)
    except queue.Empty:
        raise TimeoutError(f"no complete reply within {seconds:g} s") from None
    if finished:
        return value
    raise value


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float):
    """POST `body` and return the whole reply within `timeout` seconds in all.

    urllib's own timeout limits each wait on the socket, and every piece of
    data that arrives starts it again, so a reply that trickles in can take
    far longer (one request ran 146 s against 45 s on 2026-10-21). The
    deadline makes `timeout` cover the whole request: connecting, sending,
    waiting and reading.
    """
    # Variables:
    #   timeout: The limit for the whole request, from connecting to the last byte read.
    #   request: The POST, built once and sent inside the deadline.
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")

    def send() -> bytes:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    return run_with_deadline(send, timeout)


def post_json(
    transport: Transport, url: str, api_key: str, body: dict, timeout: float
) -> bytes:
    """Send one JSON request with a Bearer key. ModelError on any failure to answer.

    The error carries only a short reason, never the key or the response body.
    """
    # Variables:
    #   transport: The function that really sends the request; tests replace it so
    #     nothing touches the network.
    #   api_key: Sent as a Bearer token and never included in an error.
    #   headers: The request headers, including a User-Agent that Groq's front end
    #     accepts.
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Without it urllib sends "Python-urllib/3.x", which Groq's front end
        # refuses with HTTP 403 (Cloudflare error 1010) on every request.
        "User-Agent": USER_AGENT,
    }
    try:
        return transport(url, headers, json.dumps(body).encode(), timeout)
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


def reply_text(body: bytes) -> str:
    """The assistant's text in a chat-completions reply. ValueError if absent.

    A reply cut off at the output-token limit is refused as such: half a
    JSON object is not an answer, and saying why helps set the limit.
    """
    # Variables:
    #   choice: The first answer option in the service's reply.
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
    # Variables:
    #   fenced: The match inside a code fence, if the model wrapped its JSON in one.
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
        structured_output: bool = False,
    ):
        # Variables:
        #   url: The chat-completions address of the provider.
        #   api_key: The provider's key; kept private and left out of repr.
        #   model: The model name sent in each request.
        #   transport: How requests are sent; replaced in tests.
        #   timeout: The longest one request may take.
        #   max_output_tokens: The most tokens one reply may use, or None for the
        #     provider's own limit.
        #   structured_output: If True, also send the answer type's schema so the
        #     service must follow it.
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
        # Send the answer type's schema as `response_format` too, so the
        # service cannot reply in another shape (see Provider).
        self.structured_output = structured_output

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
        # Variables:
        #   timeout: A shorter wait for this request only; it can shorten the client's
        #     limit, never lengthen it.
        #   max_seconds: The policy's limit for the whole question, which here is this
        #     one request.
        #   limit: The shortest of the allowed waits, which is what is used.
        #   schema: The answer type's JSON schema as text, shown to the model in the
        #     system prompt.
        #   body: The request sent to the service; temperature 0 keeps answers as
        #     repeatable as the service allows.
        #   raw: The service's reply bytes, before the text and JSON are pulled out and
        #     checked.
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
        if self.structured_output:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": answer_type.__name__,
                    "schema": answer_type.model_json_schema(),
                    "strict": True,
                },
            }
        raw = post_json(self._transport, self.url, self._api_key, body, limit)
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
    time left, and once none is left no further model is asked. Each model,
    retries included, gets an equal share of the time left with the models
    still to ask: a model that keeps timing out moves on to the fallback
    while there is time to ask it.
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
        # Variables:
        #   clients: The models for one job, in the order they are tried.
        #   retries: How many more times to ask a model after a temporary failure.
        #   retry_delay: Seconds paused before the first retry; each later pause
        #     doubles.
        #   sleep: How to pause; replaced in tests so they do not wait.
        #   max_seconds: The time the whole question may take, retries and fallbacks
        #     included.
        #   clock: Seconds that only move forward; replaced in tests.
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
        # Variables:
        #   attempts: Every model asked for this question and what came of each, kept
        #     for the record.
        #   failures: A short reason for each model that gave no answer.
        #   limit: The time this question has: the caller's, or the client's own if that
        #     is shorter.
        #   deadline: The clock reading when the question must be over.
        #   caller_bound: True if it is the caller's time that is running out, not this
        #     client's own limit.
        #   share: An equal slice of the time left for this model and the ones still to
        #     ask.
        #   own_deadline: When this model's slice ends.
        #   pause: How long to wait before this retry.
        #   left: The time this attempt may take after the pause.
        #   started: The clock reading when the attempt began, to time it.
        self.answered_by = None
        attempts: list[Attempt] = []
        failures = []
        limit = (
            self.max_seconds
            if max_seconds is None
            else min(max_seconds, self.max_seconds)
        )
        deadline = self._clock() + limit
        # The caller's time is what runs out, not this question's own limit.
        caller_bound = max_seconds is not None and max_seconds <= self.max_seconds

        def given_up() -> ModelError:
            # Variables:
            #   spent: True if no time is left for another try.
            spent = deadline - self._clock() <= self.retry_delay
            return no_answer(failures, out_of_time=caller_bound and spent)

        try:
            for index, client in enumerate(self.clients):
                # This model and its retries get an equal share of the time
                # left with the models still to ask, so a slow model cannot
                # use up the fallback's time. The last model gets all of it.
                share = (deadline - self._clock()) / (len(self.clients) - index)
                own_deadline = self._clock() + share
                for attempt in range(1 + self.retries):
                    # The pause doubles each retry (2, 4, 8 s by default):
                    # the HTTP 500s seen live cleared within seconds. When
                    # the longer pause no longer fits, the shortest is used.
                    pause = self.retry_delay * 2 ** (attempt - 1) if attempt else 0.0
                    if attempt and own_deadline - self._clock() - pause <= 0:
                        pause = self.retry_delay
                    left = own_deadline - self._clock() - pause
                    if left <= 0:
                        if deadline - self._clock() - pause > 0:
                            break  # its share is spent; the next model is asked
                        again = " again" if attempt else ""
                        failures.append(
                            f"{client.model}: not asked{again}, no time left"
                        )
                        raise given_up()
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
                    except ValueError as error:
                        attempts.append(tried(invalid_outcome(error)))
                        raise
                    attempts.append(tried("answered"))
                    self.answered_by = client.model
                    return answer
            raise given_up()
        finally:
            self.attempts = tuple(attempts)


def no_answer(failures: list[str], *, out_of_time: bool = False) -> ModelError:
    """The error for a question no model answered, naming each failure."""
    # Variables:
    #   failures: A reason from each model that did not answer.
    #   out_of_time: True if the clock ran out, not the services.
    return ModelError(
        "no model service answered (" + "; ".join(failures) + ")",
        out_of_time=out_of_time,
    )


def client_for(
    reference: str,
    settings: Settings | None = None,
    *,
    transport: Transport = urllib_transport,
) -> ChatClient:
    """A client for "provider/model". ModelError names any missing setting."""
    # Variables:
    #   reference: A model written as provider/model, e.g. nvidia/model-name.
    #   name: The provider part of the reference.
    #   model: The model part of the reference.
    #   provider: The provider's address, key setting and limits.
    #   key: The secret for that provider from settings; None means it is not set.
    #   url: The provider's address, with the Cloudflare account filled in if needed.
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
        max_output_tokens=_capped(
            settings.model_max_output_tokens, provider.max_output_tokens
        ),
        structured_output=provider.structured_output,
    )


def _capped(wanted: int | None, limit: int | None) -> int | None:
    """The output tokens to ask for: the project's setting, never above the provider's limit."""
    # Variables:
    #   wanted: The project's setting for the most output tokens.
    #   limit: The most the provider accepts, if it has a limit.
    if wanted is None or limit is None:
        return wanted
    return min(wanted, limit)


def clients_for_jobs(
    settings: Settings | None = None, *, transport: Transport = urllib_transport
) -> dict[str, FallbackClient]:
    """One client per policy question, from the job table in settings.

    Each job asks its own model, then each model of FALLBACK_MODEL in order
    (a comma-separated chain), skipping any it already has.
    """
    # Variables:
    #   references: The models for one job: its own, then the shared fallbacks not
    #     already listed.
    settings = settings or get_settings()
    clients = {}
    for job in JOBS:
        references = [getattr(settings, _JOB_SETTING[job]) or settings.default_model]
        for reference in fallback_models(settings):
            if reference not in references:
                references.append(reference)
        clients[job] = FallbackClient(
            [client_for(r, settings, transport=transport) for r in references],
            retries=settings.model_retries,
            max_seconds=settings.model_question_seconds,
        )
    return clients


def critic_client(
    settings: Settings | None = None, *, transport: Transport = urllib_transport
) -> FallbackClient:
    """The critic's client: only the models of CRITIC_MODEL, in its own window.

    The shared FALLBACK_MODEL chain is not added: it leads back to the
    investigator's models, and a critic answered by them is not a second look.
    """
    # Variables:
    #   transport: Sends the HTTP request; replaced by a fake in tests.
    #   references: The critic's models from CRITIC_MODEL, in the order they are
    #     tried; never the shared fallback models.
    settings = settings or get_settings()
    references = critic_models(settings)
    if not references:
        raise ModelError("set CRITIC_MODEL in the local .env or environment")
    return FallbackClient(
        [client_for(r, settings, transport=transport) for r in references],
        retries=settings.model_retries,
        max_seconds=settings.critic_seconds,
    )
