"""The language model behind the agent, behind one small interface.

The agent's loop talks to a `Model`: start a conversation, then hand back
tool results and get the next turn. `ScriptedModel` replays a fixed list
of turns so the loop can be tested without a network or an API key. No
real model is wired to this older interface.
"""

import json
from dataclasses import dataclass, field
from typing import Protocol


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

    def continue_with(
        self, results: list[ToolResult], note: str | None = None
    ) -> Turn: ...


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
