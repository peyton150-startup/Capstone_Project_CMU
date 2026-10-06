"""The language model behind the agent, behind one small interface.

The agent's loop talks to a `Model`: start a conversation, then hand back
tool results and get the next turn. `ClaudeModel` is the real one;
`ScriptedModel` replays a fixed list of turns so the loop can be tested
without a network or an API key.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Protocol

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str  # JSON text
    is_error: bool = False


@dataclass
class Turn:
    """One reply from the model: what it said and which tools it wants run."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"


class Model(Protocol):
    def start(self, system: str, tools: list[dict], prompt: str) -> Turn: ...

    def continue_with(self, results: list[ToolResult], note: str | None = None) -> Turn: ...


class ScriptedModel:
    """Plays back prepared turns in order. A turn may be a function of the results so far."""

    def __init__(self, turns: list):
        self._turns = list(turns)
        self.results: list[list[ToolResult]] = []
        self.prompt: str | None = None
        self.notes: list[str] = []

    def start(self, system: str, tools: list[dict], prompt: str) -> Turn:
        self.system, self.tools, self.prompt = system, tools, prompt
        return self._next()

    def continue_with(self, results: list[ToolResult], note: str | None = None) -> Turn:
        self.results.append(results)
        if note:
            self.notes.append(note)
        return self._next()

    def _next(self) -> Turn:
        if not self._turns:
            return Turn(text="(script finished)")
        turn = self._turns.pop(0)
        return turn(self) if callable(turn) else turn

    def last_result(self, index: int = 0) -> object:
        """The decoded content of a tool result from the latest batch, for scripts that react."""
        return json.loads(self.results[-1][index].content)


class ClaudeModel:
    """Claude through the Anthropic SDK, with a hand-written tool loop.

    Keeps the conversation itself and appends each response's content
    unchanged, so thinking blocks travel back exactly as they came.
    Needs ANTHROPIC_API_KEY (or another credential the SDK can find).
    """

    def __init__(self, model: str = DEFAULT_MODEL, *, effort: str = "high", max_tokens: int = 16000, client=None):
        if client is None:
            import anthropic  # only needed for the real model

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.messages: list[dict] = []

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def start(self, system: str, tools: list[dict], prompt: str) -> Turn:
        self._system, self._tools = system, tools
        self.messages = [{"role": "user", "content": prompt}]
        return self._ask()

    def continue_with(self, results: list[ToolResult], note: str | None = None) -> Turn:
        content: list[dict] = [
            {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content, "is_error": r.is_error}
            for r in results
        ]
        if note:
            content.append({"type": "text", "text": note})
        if content:
            self.messages.append({"role": "user", "content": content})
        return self._ask()

    def _ask(self) -> Turn:
        response = self._client.beta.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._system,
            tools=self._tools,
            messages=self.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        self.messages.append({"role": "assistant", "content": response.content})
        text = "\n".join(b.text for b in response.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"]
        return Turn(text=text, tool_calls=calls, stop_reason=response.stop_reason or "end_turn")
