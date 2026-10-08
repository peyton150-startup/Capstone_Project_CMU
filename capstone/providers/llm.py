"""Provider-neutral structured research interface; no network model is installed."""

from typing import Protocol

from capstone.contracts.investigations import Investigation


class LLMProvider(Protocol):
    """An implementation consumes/returns explicit artifacts, never hidden thought."""

    def investigate(self, investigation: Investigation) -> Investigation: ...
