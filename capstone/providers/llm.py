# The interface a research model provider must follow.
# Responsibility: pass investigations in and out. It makes no model calls itself.
"""Provider-neutral structured research interface; no network model is installed."""

from typing import Protocol

from capstone.contracts.investigations import Investigation


class LLMProvider(Protocol):
    """An implementation consumes/returns explicit artifacts, never hidden thought."""

    def investigate(self, investigation: Investigation) -> Investigation: ...
