# One request to NVIDIA's model service, one validated answer back.
# Responsibility: send a prompt, refuse any reply that is not the expected type.
"""The client behind the model policy.

    client = NvidiaClient.from_settings()
    answer = client.ask(system, prompt, Stop)    # a `Stop`, or ValueError

`ask` sends one chat request (temperature 0) to NVIDIA's OpenAI-style
endpoint using only the standard library, and asks for one JSON object
matching the answer type's schema. The reply is validated against that
type. Anything else raises `ValueError` and is never repaired or guessed:
the loop already treats a `ValueError` from a policy as an invalid decision.

A failure to reach the service raises `ModelError`, which carries only a
short reason, never the key or the response body. Sending goes through a
`Transport` function, so tests pass a fake and never touch the network.
"""

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from capstone.settings import NVIDIA_DEFAULT_MODEL as DEFAULT_MODEL
from capstone.settings import Settings, get_settings

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# (url, headers, body, timeout in seconds) -> response body
Transport = Callable[[str, dict[str, str], bytes, float], bytes]
Answer = TypeVar("Answer", bound=BaseModel)

_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class ModelError(RuntimeError):
    """The model service could not be reached or refused the request."""


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def reply_text(body: bytes) -> str:
    """The assistant's text in a chat-completions reply. ValueError if absent."""
    try:
        content = json.loads(body)["choices"][0]["message"]["content"]
    except (ValueError, LookupError, TypeError) as error:
        raise ValueError("the model service sent a malformed reply") from error
    if not isinstance(content, str):
        raise ValueError("the model reply has no text")
    return content


def answer_json(text: str) -> str:
    """The JSON object in a reply: thinking and a code fence removed, nothing else."""
    text = _THINKING.sub("", text).strip()
    fenced = _FENCE.match(text)
    return fenced.group(1) if fenced else text


class NvidiaClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        transport: Transport = urllib_transport,
        timeout: float = 60.0,
    ):
        self._api_key = api_key
        self.model = model
        self._transport = transport
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"NvidiaClient(model={self.model!r})"

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        transport: Transport = urllib_transport,
    ) -> "NvidiaClient":
        settings = settings or get_settings()
        if settings.nvidia_api_key is None:
            raise ModelError("set NVIDIA_API_KEY in the local .env or environment")
        return cls(
            settings.nvidia_api_key.get_secret_value(),
            model=settings.nvidia_model,
            transport=transport,
        )

    def ask(self, system: str, prompt: str, answer_type: type[Answer]) -> Answer:
        """One question, one answer of `answer_type`. ValueError if the reply is not one."""
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
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            raw = self._transport(
                NVIDIA_URL, headers, json.dumps(body).encode(), self.timeout
            )
        except urllib.error.HTTPError as error:
            raise ModelError(f"the model service answered HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ModelError("the model service could not be reached") from None
        return answer_type.model_validate_json(answer_json(reply_text(raw)))
