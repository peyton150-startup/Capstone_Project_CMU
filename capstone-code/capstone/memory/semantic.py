# Keeps a ChromaDB similarity index of accepted lessons beside the SQL store.
# Responsibility: embed and look up memory IDs; the SQL store stays authoritative.
"""Semantic index of episodic memories. Requires the optional `semantic` extra.

The index stores only a searchable document, an embedding, and the metadata
`memory_id`, `outcome`, and `timestamp`. Search returns memory IDs; callers
hydrate full records from the SQL repository, so a stale or partial index can
never introduce a memory that the authoritative store does not contain.

Vectors from different embedding models cannot be compared: each model
places texts on its own map. So a collection records the model that built
it (`embedding_model` in its metadata; a collection without one was built
by the local model) and refuses to open with any other. Changing the model
means rebuilding the index from SQL: `python -m capstone.memory.backfill
--rebuild`.
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


LOCAL_MODEL = "local"  # Chroma's bundled all-MiniLM-L6-v2


class IndexModelMismatch(ValueError):
    """The index was built by a different embedding model than the one configured."""


class ChromaMemoryIndex:
    """Wraps one Chroma collection.

    `embed` turns stored memories into vectors and `embed_query` turns a
    search into one; a retrieval model treats the two differently. Without
    `embed_query`, `embed` does both.
    """

    def __init__(
        self, collection, embed: Embedder, embed_query: Embedder | None = None
    ):
        # Variables:
        #   collection: The Chroma collection that holds the vectors.
        #   embed: Turns stored memories into vectors.
        #   embed_query: Turns a search into a vector; falls back to embed if no
        #     separate one is given.
        self.collection = collection
        self.embed = embed
        self.embed_query = embed_query or embed

    def upsert(self, memories: Iterable[EpisodicMemory]) -> int:
        # Variables:
        #   documents: The searchable text of each memory, which is what gets embedded.
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
        # Variables:
        #   result: Chroma's nearest matches; only their metadata is asked for.
        if self.collection.count() == 0:
            return ()
        result = self.collection.query(
            query_embeddings=[list(self.embed_query([text])[0])],
            n_results=k,
            include=["metadatas"],
        )
        return tuple(UUID(meta["memory_id"]) for meta in result["metadatas"][0])


def default_embedder() -> Embedder:
    """Chroma's bundled local model (all-MiniLM-L6-v2, ONNX); no remote API."""
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    return DefaultEmbeddingFunction()


def open_collection(
    path: Path | str,
    collection_name: str,
    *,
    model: str = LOCAL_MODEL,
    rebuild: bool = False,
    rebuild_hint: str = "python -m capstone.memory.backfill --rebuild",
):
    """Open (or create) a persistent Chroma collection built by `model`.

    Raises IndexModelMismatch if the collection was built by another model,
    and anything Chroma raises if it is unavailable. `rebuild` deletes the
    collection first, so it starts empty under `model`. Shared by the memory
    index and the machine manual's index (`capstone.manual.index`).
    """
    # Variables:
    #   model: The embedding model the collection must have been built with.
    #   rebuild: If True, delete the collection first so it starts empty.
    #   client: The on-disk Chroma database.
    #   built_by: The model recorded when the collection was made; a collection without
    #     one was built locally.
    import chromadb
    from chromadb.errors import NotFoundError

    client = chromadb.PersistentClient(path=str(path))
    if rebuild:
        try:
            client.delete_collection(collection_name)
        except NotFoundError:
            pass
    try:
        collection = client.get_collection(collection_name, embedding_function=None)
    except NotFoundError:
        collection = client.create_collection(
            collection_name,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"embedding_model": model},
        )
    built_by = (collection.metadata or {}).get("embedding_model", LOCAL_MODEL)
    if built_by != model:
        raise IndexModelMismatch(
            f"the index '{collection_name}' was built by {built_by}, not "
            f"{model}; rebuild it: {rebuild_hint}"
        )
    return collection


def open_chroma_index(
    path: Path | str,
    collection_name: str,
    *,
    embed: Embedder | None = None,
    embed_query: Embedder | None = None,
    model: str = LOCAL_MODEL,
    rebuild: bool = False,
) -> ChromaMemoryIndex:
    """Open (or create) the memory index's collection built by `model`
    (see `open_collection`)."""
    collection = open_collection(path, collection_name, model=model, rebuild=rebuild)
    return ChromaMemoryIndex(collection, embed or default_embedder(), embed_query)


def open_configured_index(settings, *, rebuild: bool = False) -> ChromaMemoryIndex:
    """The index at CHROMA_PATH / CHROMA_COLLECTION, embedded by EMBEDDING_MODEL."""
    from capstone.providers.embeddings import embedders_for

    embedders = embedders_for(settings)
    passage, query = embedders if embedders is not None else (None, None)
    return open_chroma_index(
        settings.chroma_path,
        settings.chroma_collection,
        embed=passage,
        embed_query=query,
        model=settings.embedding_model,
        rebuild=rebuild,
    )
