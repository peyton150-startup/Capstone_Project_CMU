# A client for TypeSafe's System One API: typed judgments, not text.
# Responsibility: send one batch of questions about one state, return typed answers.
"""TypeSafe's System One models (Jev) answer questions with numbers, not prose.

One request holds one `state` (the text or JSON the questions are about) and
any number of named questions, answered in parallel without seeing each
other. Two question types are used here:

- a **noul** is a yes/no question; its answer is the probability of yes;
- a **choice** picks one option from a named set; its answer is the option,
  a probability for every option, and a confidence (how peaked they are).

The model never sees the question names, only the instructions and criteria.
The service is described at https://docs.typesafe.ai/api.md. Used only by the
evaluator (`capstone.evaluation.auto_label`), never by the agent.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from capstone.providers.chat import ModelError, Transport, post_json, urllib_transport
from capstone.settings import Settings

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"


class Noul(BaseModel):
    """A yes/no question. `true` and `false` say where the boundary lies."""

    model_config = ConfigDict(frozen=True)

    instructions: str = Field(min_length=1)
    true: str | None = None
    false: str | None = None

    def request(self) -> dict:
        body: dict = {"type": "noul", "instructions": self.instructions}
        if self.true is not None or self.false is not None:
            body["criteria"] = {"true": self.true, "false": self.false}
        return body


class Choice(BaseModel):
    """One option from `options` (name -> description, or None if plain)."""

    model_config = ConfigDict(frozen=True)

    instructions: str = Field(min_length=1)
    options: dict[str, str | None] = Field(min_length=1, max_length=255)

    def request(self) -> dict:
        return {
            "type": "choice",
            "instructions": self.instructions,
            "criteria": dict(self.options),
        }


Question = Noul | Choice


class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float = Field(ge=0, le=1)  # the probability the answer is yes


class ChoiceAnswer(BaseModel):
    type: Literal["choice"]
    choice: str
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float]


class Judgments(BaseModel):
    """The answers to one request, by question name, and who gave them."""

    model_config = ConfigDict(frozen=True)

    model: str  # the model that answered, which may differ from the alias asked
    answers: dict[str, NoulAnswer | ChoiceAnswer]
    input_tokens: int = 0


def read_judgments(body: bytes, asked: dict[str, Question]) -> Judgments:
    """The typed answers in a reply. ValueError if any asked one is missing or wrong."""
    # Variables:
    #   asked: The questions that were put, by name; each must come back answered.
    #   reply: The service's reply decoded.
    #   judgments: The answers in typed form.
    #   answer: The answer to one question, or None if missing.
    #   wanted: The answer type that question requires.
    try:
        reply = json.loads(body)
        judgments = Judgments(
            model=reply["model"],
            answers=reply["answers"],
            input_tokens=reply.get("usage", {}).get("input_tokens", 0),
        )
    except (ValueError, LookupError, TypeError, ValidationError) as error:
        raise ValueError("the judgment service sent a malformed reply") from error
    for name, question in asked.items():
        answer = judgments.answers.get(name)
        wanted = NoulAnswer if isinstance(question, Noul) else ChoiceAnswer
        if not isinstance(answer, wanted):
            raise ValueError(f"the judgment service did not answer {name!r}")
        if isinstance(answer, ChoiceAnswer) and answer.choice not in question.options:
            raise ValueError(
                f"the judgment service chose an unknown option for {name!r}"
            )
    return judgments


class JudgmentClient:
    """Asks one System One model. The key is held here and never shown."""

    def __init__(
        self,
        api_key: str,
        model: str = "jev-latest",
        *,
        transport: Transport = urllib_transport,
        timeout: float = 45.0,
        url: str = TYPESAFE_URL,
    ):
        # Variables:
        #   api_key: The key; kept private and left out of repr.
        #   model: Which System One model to ask.
        #   transport: How requests are sent; replaced in tests.
        #   timeout: The longest one request may take.
        #   url: The service address.
        self._api_key = api_key
        self.model = model
        self._transport = transport
        self.timeout = timeout
        self.url = url

    def __repr__(self) -> str:
        return f"JudgmentClient(model={self.model!r})"

    def ask(self, state: str | dict, questions: dict[str, Question]) -> Judgments:
        """All `questions` about `state`, in one request.

        ModelError if the service cannot answer (as for chat models);
        ValueError if its reply is not the typed answers asked for.
        """
        # Variables:
        #   state: What the questions are about, as text or a dictionary.
        #   questions: Named questions, all answered in one request.
        #   body: The request sent to the service.
        #   reply: The service's reply bytes.
        if not questions:
            raise ValueError("ask at least one question")
        body = {
            "model": self.model,
            "state": state,
            "questions": {name: q.request() for name, q in questions.items()},
        }
        reply = post_json(self._transport, self.url, self._api_key, body, self.timeout)
        return read_judgments(reply, questions)


def judgment_client(settings: Settings, **kwargs) -> JudgmentClient:
    """The configured client. ModelError if TYPESAFE_API_KEY is not set."""
    if settings.typesafe_api_key is None:
        raise ModelError("TYPESAFE_API_KEY is not set")
    return JudgmentClient(
        settings.typesafe_api_key.get_secret_value(),
        settings.typesafe_model,
        timeout=settings.model_request_seconds,
        **kwargs,
    )
