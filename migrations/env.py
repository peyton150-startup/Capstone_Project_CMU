"""Alembic entry point. Only an explicit Alembic command loads configuration."""

from alembic import context
from alembic.util import CommandError
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

from capstone.memory.schema import metadata
from capstone.settings import get_settings

# Only durable memory is an ORM schema; simulator state remains independent.
target_metadata = metadata


def database_url() -> URL:
    """Read a secret URL lazily and preserve connection options for Psycopg."""
    settings = get_settings()
    if settings.database_url is None:
        raise CommandError(
            "Set DATABASE_URL in the local .env or environment."
        ) from None
    try:
        url = make_url(settings.database_url.get_secret_value())
        if url.drivername in {"postgres", "postgresql", "postgresql+psycopg"}:
            url = url.set(drivername="postgresql+psycopg")
        # Validate dialect availability without opening a connection.
        url.get_dialect()
        return url
    except (SQLAlchemyError, ValueError):
        raise CommandError("DATABASE_URL is invalid or unsupported.") from None


def run_migrations_offline() -> None:
    """Render SQL without an engine or connection; do not apply it."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Use a short-lived connection only when an online command is requested."""
    url = database_url()
    # Configuring a dialect from a URL does not create an engine or connect.
    # RevisionContext also covers programmatic commands with cmd_opts=None.
    context.configure(url=url, target_metadata=target_metadata)
    revision = context.get_context().opts.get("revision_context")
    autogenerate = getattr(context.config.cmd_opts, "autogenerate", False)
    if revision is not None:
        autogenerate = autogenerate or revision.command_args.get("autogenerate", False)
    if autogenerate and not target_metadata.tables:
        raise CommandError(
            "Define the persistence schema before using --autogenerate. "
            "Empty metadata could propose dropping existing tables."
        ) from None
    connect_args = (
        {"connect_timeout": 10} if url.get_backend_name() == "postgresql" else {}
    )
    engine = None
    try:
        engine = create_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    except SQLAlchemyError:
        # Driver messages can contain credentials; don't expose chained exceptions.
        raise CommandError(
            "Migration database operation failed; check DATABASE_URL."
        ) from None
    finally:
        if engine is not None:
            engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
