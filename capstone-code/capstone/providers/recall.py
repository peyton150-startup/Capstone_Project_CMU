# Adds one tool, recall_memories, in front of the factory provider.
# Responsibility: answer recall from memory, labelled as memory; pass the rest on.
"""The agent's only way to read memory: one tool through the usual boundary.

    provider = RecallingProvider(factory_provider, memory_service)

`recall_memories(text, limit)` is answered from `MemoryService.search`
with source "memory", so the loop labels the evidence `memory`, not
`observable`. The answer is stamped with the factory's current tick only
so it fits the result envelope; it says nothing about the factory now.
Every other tool goes to the factory unchanged.

Searches are bounded (Future Work 1, "agent-directed RAG and repeat
retrieval"). One provider serves one investigation, and in that time the
store does not change: lessons are promoted only after a run ends. So:

- the same search again (same words after `normalize`, same limit) is
  refused, whatever the tick: it can only return what is already known.
  The refusal says to revise the wording, try other symptoms or another
  hypothesis, or look at the factory instead;
- at most `max_searches` searches are answered (default 3, the Future Work
  1 default); later ones are refused with a message that says what to do
  instead: carry on with the factory's own tools and say what memory left
  unknown.

A refused search is an invalid request, like wrong arguments: the loop
counts it as a failed call and shows its message in the next prompt, so
the agent can correct course. Both limits sit here, not in the loop, which
never imports memory.

This lives outside `capstone.agent`: whoever runs an investigation decides
whether the agent gets recall at all, and the loop never imports memory.
"""

from typing import Protocol
from uuid import UUID

from pydantic import Field, JsonValue

from capstone.contracts.provenance import MEMORY_SOURCE
from capstone.contracts.tools import ToolError, ToolRequest, ToolResult, ToolSpec
from capstone.memory.contracts import RecalledMemory
from capstone.memory.policy import normalize
from capstone.providers.factory import FactoryProvider, NoArguments

RECALL_TOOL = "recall_memories"
# Future Work 1's default: at most three retrieval calls, the first included.
MAX_SEARCHES = 3

REPEATED_SEARCH = (
    "This search was already made in this investigation and memory has not "
    "changed since. Revise the wording, try other symptoms or another "
    "hypothesis, or look at the factory with its own tools."
)
SEARCHES_SPENT = (
    "No memory searches are left in this investigation. Carry on with the "
    "factory's own tools and say what memory left unknown."
)


class RecallArguments(NoArguments):
    text: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=10)


# How a model is shown the recall tool, when it is offered at all.
RECALL_SPEC = ToolSpec(
    name=RECALL_TOOL,
    description=(
        "Search lessons kept from earlier investigations by words, e.g. the "
        "symptom. An answer is a past investigation's belief, not a look at "
        "the factory now: it can suggest where to look, never prove anything. "
        f"At most {MAX_SEARCHES} searches per investigation; the same search "
        "twice is refused. If an answer does not help, search again with "
        "different words, or carry on without memory."
    ),
    arguments=RecallArguments.model_json_schema(),
)


class MemorySearch(Protocol):
    def search(self, text: str, *, limit: int) -> tuple[RecalledMemory, ...]: ...


class RecallingProvider:
    """The factory's tools, plus `recall_memories` answered from memory."""

    def __init__(
        self,
        factory: FactoryProvider,
        memory: MemorySearch,
        *,
        max_searches: int = MAX_SEARCHES,
    ):
        if max_searches < 1:
            raise ValueError("max_searches must be at least one")
        self._factory = factory
        self._memory = memory
        self.max_searches = max_searches
        # Each answered search, as (normalized words, limit), oldest first.
        self.searched: list[tuple[str, int]] = []

    def call(
        self,
        request: ToolRequest,
        *,
        run_id: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> ToolResult[JsonValue]:
        if request.name != RECALL_TOOL:
            return self._factory.call(
                request, run_id=run_id, investigation_id=investigation_id
            )
        error, data = None, None
        try:
            arguments = RecallArguments.model_validate(request.arguments)
        except ValueError:
            error = ToolError(
                code="invalid_arguments", message="Tool arguments are invalid."
            )
        else:
            key = (normalize(arguments.text), arguments.limit)
            if key in self.searched:
                error = ToolError(code="invalid_arguments", message=REPEATED_SEARCH)
            elif len(self.searched) >= self.max_searches:
                error = ToolError(code="invalid_arguments", message=SEARCHES_SPENT)
            else:
                try:
                    found = self._memory.search(arguments.text, limit=arguments.limit)
                    data = [view.model_dump(mode="json") for view in found]
                    self.searched.append(key)
                except Exception:
                    # Store errors may contain connection details; never return them.
                    error = ToolError(code="provider_error", message="Recall failed.")
        clock = self._factory.call(
            ToolRequest(name="get_time", arguments={}),
            run_id=run_id,
            investigation_id=investigation_id,
        )
        return ToolResult[JsonValue](
            success=error is None,
            tool=RECALL_TOOL,
            source=MEMORY_SOURCE,
            tick=clock.tick,
            timestamp=clock.timestamp,
            run_id=run_id,
            investigation_id=investigation_id,
            data=data,
            error=error,
        )
