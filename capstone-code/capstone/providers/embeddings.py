# Text embeddings for memory search, from NVIDIA's hosted retrieval model.
# Responsibility: turn texts into vectors; refuse any reply that is not one vector per text.
"""Embedders for the semantic memory index.

    passage, query = embedders_for(settings)        # None for "local"
    vectors = passage(["spindle bearing wore out after vibration rose"])

A retrieval model embeds a stored text and a search differently, so there
are two embedders: `passage` for memories written to the index and `query`
for what the agent searches with. Both must come from the same model as the
index they are used with (see `capstone.memory.semantic`).

Sending goes through the chat client's `post_json`, so a failure raises the
same `ModelError` with a short reason and never the key. Tests pass a fake
`Transport` and never touch the network.
"""

import json
from collections.abc import Sequence
from typing import Literal

from capstone.providers.chat import (
    ModelError,
    Transport,
    post_json,
    urllib_transport,
)
from capstone.settings import Settings, get_settings

NVIDIA_EMBEDDINGS_URL = "https://integrate.api.nvidia.com/v1/embeddings"
# Chroma's bundled all-MiniLM-L6-v2, the index's model before NVIDIA's.
LOCAL = "local"

InputType = Literal["passage", "query"]


class NvidiaEmbedder:
    """One role (passage or query) of one NVIDIA embedding model."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        input_type: InputType,
        transport: Transport = urllib_transport,
        timeout: float = 15.0,
    ):
        # Variables:
        #   input_type: passage for stored memories or query for a search; the model
        #     treats them differently.
        self._api_key = api_key
        self.model = model
        self.input_type = input_type
        self._transport = transport
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"NvidiaEmbedder(model={self.model!r}, input_type={self.input_type!r})"

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, in order. ValueError if the reply is not that."""
        # Variables:
        #   texts: What to embed, in order.
        #   body: The request, asking for float vectors and cutting overlong texts at
        #     the end.
        #   raw: The service's reply bytes.
        #   items: The reply's entries put back into the order of the texts.
        #   vectors: One list of numbers per text.
        if not texts:
            return []
        body = {
            "model": self.model,
            "input": list(texts),
            "input_type": self.input_type,
            "encoding_format": "float",
            # A memory longer than the model takes is cut at the end, not refused.
            "truncate": "END",
        }
        raw = post_json(
            self._transport, NVIDIA_EMBEDDINGS_URL, self._api_key, body, self.timeout
        )
        try:
            items = sorted(json.loads(raw)["data"], key=lambda item: item["index"])
            vectors = [[float(x) for x in item["embedding"]] for item in items]
        except (ValueError, LookupError, TypeError) as error:
            raise ValueError("the embedding service sent a malformed reply") from error
        if len(vectors) != len(texts):
            raise ValueError(
                f"the embedding service sent {len(vectors)} vectors for "
                f"{len(texts)} texts"
            )
        return vectors


def embedders_for(
    settings: Settings | None = None, *, transport: Transport = urllib_transport
) -> tuple[NvidiaEmbedder, NvidiaEmbedder] | None:
    """(passage, query) embedders for EMBEDDING_MODEL, or None for "local".

    ModelError names a missing key or an unsupported provider.
    """
    # Variables:
    #   reference: The configured model, written nvidia/model or local.
    #   provider: The part before the slash.
    #   model: The part after it.
    #   key: The NVIDIA key from settings.
    settings = settings or get_settings()
    reference = settings.embedding_model
    if reference == LOCAL:
        return None
    provider, _, model = reference.partition("/")
    if provider != "nvidia" or not model:
        raise ModelError(
            f"unknown embedding model {reference!r}: use nvidia/<model> or {LOCAL!r}"
        )
    if settings.nvidia_api_key is None:
        raise ModelError("set NVIDIA_API_KEY in the local .env or environment")
    key = settings.nvidia_api_key.get_secret_value()
    return tuple(
        NvidiaEmbedder(
            key,
            model,
            input_type=role,
            transport=transport,
            timeout=settings.model_request_seconds,
        )
        for role in ("passage", "query")
    )
