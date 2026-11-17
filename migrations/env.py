"""Alembic entry point. Only an explicit Alembic command loads configuration."""

from alembic import context
from alembic.util import CommandError
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

from capstone.api.run_models import RunBase
from capstone.memory.schema import metadata
from capstone.settings import get_settings

# The hosted simulator journal is private and independent of memory. Its
# models must be visible to PostgreSQL autogenerate; the old journal stays
# intentionally unmanaged by these models.
target_metadata = metadata
LEGACY_JOURNAL = {"runs", "run_events", "run_reviews", "run_artifacts"}


def include_object(obj, name, type_, reflected, compare_to):
    """Do not propose dropping PR289's intentionally retained journal."""
    # Variables:
    #   reflected: This object exists in the database, rather than models.
    #   compare_to: Matching model object, absent for an old journal table.
    if (
        type_ == "table"
        and reflected
        and compare_to is None
        and getattr(obj, "schema", None) == "capstone_private"
        and name in LEGACY_JOURNAL
    ):
        return False
    return True


def migration_metadata(url: URL):
    """Include hosted run models only for PostgreSQL migrations."""
    # Variables:
    #   url: Migration target; SQLite remains the memory-only local test path.
    if url.get_backend_name() == "postgresql":
        return [metadata, RunBase.metadata]
    return metadata


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
    # Variables:
    #   url: Target dialect determines whether hosted run models are included.
    url = database_url()
    context.configure(
        url=url,
        target_metadata=migration_metadata(url),
        include_object=include_object,
        include_schemas=url.get_backend_name() == "postgresql",
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Use a short-lived connection only when an online command is requested."""
    # Variables:
    #   selected_metadata: Memory and, for PostgreSQL, hosted run definitions.
    #   autogenerate: Whether Alembic is comparing models to the live schema.
    url = database_url()
    # Configuring a dialect from a URL does not create an engine or connect.
    # RevisionContext also covers programmatic commands with cmd_opts=None.
    selected_metadata = migration_metadata(url)
    context.configure(
        url=url,
        target_metadata=selected_metadata,
        include_object=include_object,
        include_schemas=url.get_backend_name() == "postgresql",
    )
    revision = context.get_context().opts.get("revision_context")
    autogenerate = getattr(context.config.cmd_opts, "autogenerate", False)
    if revision is not None:
        autogenerate = autogenerate or revision.command_args.get("autogenerate", False)
    if autogenerate and not metadata.tables:
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
            context.configure(
                connection=connection,
                target_metadata=selected_metadata,
                include_object=include_object,
                include_schemas=url.get_backend_name() == "postgresql",
            )
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
