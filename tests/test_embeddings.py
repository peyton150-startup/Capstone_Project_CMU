"""The NVIDIA embedder for memory search. Every request goes to a fake transport."""

import json
import urllib.error

import pytest

from capstone.providers.chat import ModelError
from capstone.providers.embeddings import (
    LOCAL,
    NVIDIA_EMBEDDINGS_URL,
    NvidiaEmbedder,
    embedders_for,
)
from capstone.settings import DEFAULT_EMBEDDING_MODEL, Settings

KEY = "test-key-not-real"


class FakeTransport:
    """Records each request and answers with a prepared reply body or error."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, url, headers, body, timeout):
        self.requests.append((url, headers, json.loads(body), timeout))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def vectors(*rows, shuffled=False):
    """A reply body in the embeddings shape, one item per row."""
    items = [{"index": i, "embedding": list(row)} for i, row in enumerate(rows)]
    return json.dumps({"data": items[::-1] if shuffled else items}).encode()


def embedder(*replies, input_type="passage"):
    transport = FakeTransport(*replies)
    return NvidiaEmbedder(
        KEY, "nvidia/nemotron-3-embed-1b", input_type=input_type, transport=transport
    ), transport


def test_texts_go_to_nvidia_with_the_role_and_come_back_in_order():
    embed, transport = embedder(vectors([1, 0], [0, 1], shuffled=True))
    assert embed(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    [(url, headers, body, _)] = transport.requests
    assert url == NVIDIA_EMBEDDINGS_URL
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert body["model"] == "nvidia/nemotron-3-embed-1b"
    assert body["input"] == ["first", "second"]
    assert body["input_type"] == "passage"


def test_a_search_is_embedded_as_a_query():
    embed, transport = embedder(vectors([1, 0]), input_type="query")
    embed(["rising vibration"])
    assert transport.requests[0][2]["input_type"] == "query"


def test_no_texts_make_no_request():
    embed, transport = embedder()
    assert embed([]) == [] and transport.requests == []


def test_a_reply_with_the_wrong_number_of_vectors_is_refused():
    embed, _ = embedder(vectors([1, 0]))
    with pytest.raises(ValueError, match="1 vectors for 2 texts"):
        embed(["a", "b"])


def test_a_malformed_reply_is_refused():
    embed, _ = embedder(b'{"data": [{"no": "vector"}]}')
    with pytest.raises(ValueError, match="malformed"):
        embed(["a"])


def test_a_rejected_key_fails_once_and_never_shows_the_key():
    error = urllib.error.HTTPError(NVIDIA_EMBEDDINGS_URL, 401, "no", {}, None)
    embed, _ = embedder(error)
    with pytest.raises(ModelError) as raised:
        embed(["a"])
    assert raised.value.transient is False
    assert KEY not in str(raised.value) and KEY not in repr(embed)


def test_a_slow_service_is_reported_as_timed_out():
    embed, _ = embedder(TimeoutError("timed out"))
    with pytest.raises(ModelError, match="timed out") as raised:
        embed(["a"])
    assert raised.value.transient is True


def settings(**values):
    return Settings(_env_file=None, **values)


def test_the_default_is_nvidias_nemotron_embedder():
    assert settings().embedding_model == DEFAULT_EMBEDDING_MODEL
    assert DEFAULT_EMBEDDING_MODEL == "nvidia/nvidia/nemotron-3-embed-1b"


def test_the_setting_gives_a_passage_and_a_query_embedder_of_one_model():
    passage, query = embedders_for(settings(NVIDIA_API_KEY=KEY))
    assert (passage.input_type, query.input_type) == ("passage", "query")
    assert passage.model == query.model == "nvidia/nemotron-3-embed-1b"


def test_local_means_chromas_own_model():
    assert embedders_for(settings(EMBEDDING_MODEL=LOCAL)) is None


def test_a_missing_key_or_another_provider_is_named():
    with pytest.raises(ModelError, match="NVIDIA_API_KEY"):
        embedders_for(settings())
    with pytest.raises(ModelError, match="unknown embedding model"):
        embedders_for(settings(EMBEDDING_MODEL="groq/some-model", NVIDIA_API_KEY=KEY))
