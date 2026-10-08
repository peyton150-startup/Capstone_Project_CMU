"""Read-only database connectivity probe. No schema or persistence logic."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from capstone.settings import get_settings


def check_database_connection() -> bool:
    """Load local configuration and check SELECT 1, closing all connections."""
    settings = get_settings()
    if settings.database_url is None:
        raise ValueError("Set DATABASE_URL in the local .env or environment.")

    url = make_url(settings.database_url.get_secret_value())
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
