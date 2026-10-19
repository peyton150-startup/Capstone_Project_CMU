# Keeps a ChromaDB similarity index of accepted lessons beside the SQL store.
# Responsibility: embed and look up memory IDs; the SQL store stays authoritative.
"""Semantic index of episodic memories. Requires the optional `semantic` extra.

The index stores only a searchable document, an embedding, and the metadata
`memory_id`, `outcome`, and `timestamp`. Search returns memory IDs; callers
hydrate full records from the SQL repository, so a stale or partial index can
never introduce a memory that the authoritative store does not contain.
"""

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from uuid import UUID

from capstone.memory.contracts import EpisodicMemory

Embedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]


def memory_document(memory: EpisodicMemory) -> str:
    """The text that represents a memory for both embedding and keyword search."""
    return "\n".join(
        (
            memory.category,
            "; ".join(memory.symptoms),
            memory.diagnosis,
            memory.lesson,
        )
    )


def memory_metadata(memory: EpisodicMemory) -> dict[str, str | int]:
    # `timestamp` is the simulation tick of the source investigation; the
    # contract records no wall-clock time and the project forbids reading one.
    return {
        "memory_id": str(memory.memory_id),
        "outcome": memory.outcome,
        "timestamp": memory.source_tick,
    }


class ChromaMemoryIndex:
    """Wraps one Chroma collection; embeddings are computed by `embed`."""

    def __init__(self, collection, embed: Embedder):
        self.collection = collection
        self.embed = embed

    def upsert(self, memories: Iterable[EpisodicMemory]) -> int:
        memories = tuple(memories)
        if not memories:
            return 0
        documents = [memory_document(memory) for memory in memories]
        self.collection.upsert(
            ids=[str(memory.memory_id) for memory in memories],
            documents=documents,
            embeddings=[list(vector) for vector in self.embed(documents)],
            metadatas=[memory_metadata(memory) for memory in memories],
        )
        return len(memories)

    def search(self, text: str, k: int) -> tuple[UUID, ...]:
        """Nearest memory IDs across the whole collection, closest first."""
        if self.collection.count() == 0:
            return ()
        result = self.collection.query(
            query_embeddings=[list(self.embed([text])[0])],
            n_results=k,
            include=["metadatas"],
        )
        return tuple(UUID(meta["memory_id"]) for meta in result["metadatas"][0])


def default_embedder() -> Embedder:
    """Chroma's bundled local model (all-MiniLM-L6-v2, ONNX); no remote API."""
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    return DefaultEmbeddingFunction()


def open_chroma_index(
    path: Path | str, collection_name: str, *, embed: Embedder | None = None
) -> ChromaMemoryIndex:
    """Open (or create) a persistent collection. Raises if Chroma is unavailable."""
    import chromadb

    client = chromadb.PersistentClient(path=str(path))
    collection = client.get_or_create_collection(
        collection_name,
        embedding_function=None,
        configuration={"hnsw": {"space": "cosine"}},
    )
    return ChromaMemoryIndex(collection, embed or default_embedder())
