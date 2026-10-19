# Adds one tool, recall_memories, in front of the factory provider.
# Responsibility: answer recall from memory, labelled as memory; pass the rest on.
"""The agent's only way to read memory: one tool through the usual boundary.

    provider = RecallingProvider(factory_provider, memory_service)

`recall_memories(text, limit)` is answered from `MemoryService.search`
with source "memory", so the loop labels the evidence `memory`, not
`observable`. The answer is stamped with the factory's current tick only
so it fits the result envelope; it says nothing about the factory now.
Every other tool goes to the factory unchanged.

This lives outside `capstone.agent`: whoever runs an investigation decides
whether the agent gets recall at all, and the loop never imports memory.
"""

from typing import Protocol
from uuid import UUID

from pydantic import Field, JsonValue

from capstone.contracts.provenance import MEMORY_SOURCE
from capstone.contracts.tools import ToolError, ToolRequest, ToolResult, ToolSpec
from capstone.memory.contracts import RecalledMemory
from capstone.providers.factory import FactoryProvider, NoArguments

RECALL_TOOL = "recall_memories"


class RecallArguments(NoArguments):
    text: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=10)


# How a model is shown the recall tool, when it is offered at all.
RECALL_SPEC = ToolSpec(
    name=RECALL_TOOL,
    description=(
        "Search lessons kept from earlier investigations by words, e.g. the "
        "symptom. An answer is a past investigation's belief, not a look at "
        "the factory now: it can suggest where to look, never prove anything."
    ),
    arguments=RecallArguments.model_json_schema(),
)


class MemorySearch(Protocol):
    def search(self, text: str, *, limit: int) -> tuple[RecalledMemory, ...]: ...


class RecallingProvider:
    """The factory's tools, plus `recall_memories` answered from memory."""

    def __init__(self, factory: FactoryProvider, memory: MemorySearch):
        self._factory = factory
        self._memory = memory

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
            try:
                found = self._memory.search(arguments.text, limit=arguments.limit)
                data = [view.model_dump(mode="json") for view in found]
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
