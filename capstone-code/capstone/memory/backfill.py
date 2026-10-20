# Copies every stored memory from the SQL store into the ChromaDB index.
# Responsibility: rebuild the derived index; never write to the SQL store.
"""Backfill the semantic index: `python -m capstone.memory.backfill`.

Reads DATABASE_URL, CHROMA_PATH, CHROMA_COLLECTION and EMBEDDING_MODEL from
the environment or `.env`. Upserts are keyed by memory ID, so rerunning is
safe. After changing EMBEDDING_MODEL, run with `--rebuild`: the old vectors
come from another model and cannot be searched with the new one, so the
collection is emptied and every memory is embedded again.
"""

import argparse

from capstone.memory.contracts import EpisodicMemory
from capstone.memory.service import MemoryIndex

BATCH_SIZE = 100


def backfill(memories: tuple[EpisodicMemory, ...], index: MemoryIndex) -> int:
    for start in range(0, len(memories), BATCH_SIZE):
        index.upsert(memories[start : start + BATCH_SIZE])
    return len(memories)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m capstone.memory.backfill")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="empty the index first (needed after EMBEDDING_MODEL changes)",
    )
    args = parser.parse_args(argv)

    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    from capstone.memory.repository import SQLMemoryRepository
    from capstone.memory.semantic import open_configured_index
    from capstone.settings import get_settings

    settings = get_settings()
    if settings.database_url is None:
        raise SystemExit("Set DATABASE_URL in the local .env or environment.")
    url = make_url(settings.database_url.get_secret_value())
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(url)
    try:
        memories = SQLMemoryRepository(engine).all_memories()
    finally:
        engine.dispose()
    index = open_configured_index(settings, rebuild=args.rebuild)
    count = backfill(memories, index)
    print(
        f"Indexed {count} memories into '{settings.chroma_collection}' "
        f"with {settings.embedding_model}."
    )


if __name__ == "__main__":
    main()
