"""Read-only database connectivity probe. No schema or persistence logic."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def check_database_connection() -> bool:
    """Load local configuration and check SELECT 1, closing all connections."""
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("Set DATABASE_URL in the local .env or environment.")

    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg"}:
        url = url.set(drivername="postgresql+psycopg")
        connect_args = {"connect_timeout": 10}
    else:
        connect_args = {}

    engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()
