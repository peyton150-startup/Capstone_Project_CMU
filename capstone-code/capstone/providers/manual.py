# Adds one tool, search_manual, in front of the other providers.
# Responsibility: answer manual searches, labelled as manual; pass the rest on.
"""The agent's way to read the machine manual: one tool through the usual boundary.

    provider = ManualProvider(inner_provider, KeywordManualSearch(load_manual()))

`search_manual(text, limit)` returns the best-matching numbered sections of
the manual (SIM-CNC-001), each with its number, title and text, under the
source "manual". The loop labels that evidence `manual`, so every prompt
marks it as general guidance for the machine model, not a look at the
factory now, and the memory gate refuses a lesson that cites only the
manual. The answer is stamped with the factory's current tick only so it
fits the result envelope. Every other tool goes to `inner` unchanged, so
this wraps the factory provider, or recall in front of it.

Searches are bounded the way recall's are (`providers/recall.py`): the
manual does not change during an investigation, so the same search again
(same words after `normalize`, same limit) is refused, and at most
`max_searches` are answered. A refusal is an invalid request: the loop
counts it as a failed call and shows its message in the next prompt.

The manual holds no hidden truth (`capstone.manual.sections` refuses a
section that names a fault, a seed or a case), and it is read-only: nothing
the agent does changes it.
"""

from typing import Protocol
from uuid import UUID

from pydantic import Field, JsonValue

from capstone.contracts.provenance import MANUAL_SOURCE
from capstone.contracts.tools import ToolError, ToolRequest, ToolResult, ToolSpec
from capstone.manual.sections import DOCUMENT_ID, ManualSection
from capstone.memory.policy import normalize
from capstone.providers.factory import FactoryProvider, NoArguments

MANUAL_TOOL = "search_manual"
MAX_SEARCHES = 3

REPEATED_SEARCH = (
    "This manual search was already made in this investigation and the manual "
    "has not changed. Try other words, for another symptom or cause, or look at "
    "the factory with its own tools."
)
SEARCHES_SPENT = (
    "No manual searches are left in this investigation. Carry on with the "
    "factory's own tools."
)


class ManualArguments(NoArguments):
    text: str = Field(min_length=1)
    limit: int = Field(default=3, ge=1, le=5)


MANUAL_SPEC = ToolSpec(
    name=MANUAL_TOOL,
    description=(
        f"Search the maintenance manual for this machine model ({DOCUMENT_ID}) by "
        "words, e.g. a symptom or a suspected cause. Returns numbered sections "
        "(cite them as §2.7): what a symptom can mean, possible causes, and the "
        "checks that tell them apart. The manual describes the machine type, not "
        "what is happening now: confirm what it suggests with the factory's own "
        f"data. At most {MAX_SEARCHES} searches per investigation; the same "
        "search twice is refused."
    ),
    arguments=ManualArguments.model_json_schema(),
)


class ManualSearch(Protocol):
    def search(self, text: str, *, limit: int) -> tuple[ManualSection, ...]: ...


def section_answer(section: ManualSection) -> dict:
    """One section as the agent receives it."""
    return {
        "section": f"§{section.section_id}",
        "title": section.title,
        "text": section.text,
        "document": f"{section.document_id} rev {section.revision}",
    }


class ManualProvider:
    """The inner provider's tools, plus `search_manual` answered from the manual."""

    def __init__(
        self,
        inner: FactoryProvider,
        manual: ManualSearch,
        *,
        max_searches: int = MAX_SEARCHES,
    ):
        # Variables:
        #   inner: The factory provider that answers every other tool.
        #   manual: The search over the manual's sections.
        #   max_searches: How many manual searches one investigation may make.
        #   searched: Searches already answered, as (normalized words, limit).
        if max_searches < 1:
            raise ValueError("max_searches must be at least one")
        self._inner = inner
        self._manual = manual
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
        # Variables:
        #   error: Why the search was refused or failed, or None.
        #   data: The sections returned, or None.
        #   arguments: The checked search text and limit.
        #   key: The search as normalized words plus limit, used to spot a repeat.
        #   found: The matching manual sections.
        #   clock: The factory's time, so the answer is stamped like any other.
        if request.name != MANUAL_TOOL:
            return self._inner.call(
                request, run_id=run_id, investigation_id=investigation_id
            )
        error, data = None, None
        try:
            arguments = ManualArguments.model_validate(request.arguments)
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
                    found = self._manual.search(arguments.text, limit=arguments.limit)
                    data = [section_answer(s) for s in found]
                    self.searched.append(key)
                except Exception:
                    # Index errors may name paths or services; never return them.
                    error = ToolError(
                        code="provider_error", message="Manual search failed."
                    )
        clock = self._inner.call(
            ToolRequest(name="get_time", arguments={}),
            run_id=run_id,
            investigation_id=investigation_id,
        )
        return ToolResult[JsonValue](
            success=error is None,
            tool=MANUAL_TOOL,
            source=MANUAL_SOURCE,
            tick=clock.tick,
            timestamp=clock.timestamp,
            run_id=run_id,
            investigation_id=investigation_id,
            data=data,
            error=error,
        )
