"""Migration scaffold checks: no network access or database mutations."""

from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

import capstone.settings as settings_module
from capstone.settings import Settings

alembic_config = pytest.importorskip("alembic.config")
command = pytest.importorskip("alembic.command")
script = pytest.importorskip("alembic.script")
context = pytest.importorskip("alembic.context")
util = pytest.importorskip("alembic.util")
sqlalchemy = pytest.importorskip("sqlalchemy")
sqlalchemy_exc = pytest.importorskip("sqlalchemy.exc")
mako_template = pytest.importorskip("mako.template")

ROOT = Path(__file__).resolve().parents[1]


def configuration():
    return alembic_config.Config(str(ROOT / "alembic.ini"), output_buffer=StringIO())


def use_database_url(monkeypatch, value):
    settings = Settings(_env_file=None, DATABASE_URL=value)
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)


def test_scaffold_has_no_revisions_and_works_outside_repository(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    directory = script.ScriptDirectory.from_config(configuration())
    assert directory.get_heads() == []
    assert list(directory.walk_revisions()) == []
    assert Path(directory.env_py_location).is_file()


def test_revision_template_produces_valid_empty_upgrade_and_downgrade():
    source = mako_template.Template(filename=str(ROOT / "migrations/script.py.mako"))
    rendered = source.render(
        message="test migration",
        up_revision="abc123",
        down_revision=None,
        branch_labels=None,
        depends_on=None,
        create_date="2026-10-08",
        imports="",
        upgrades="",
        downgrades="",
        comma=util.format_as_comma,
    )
    namespace = {}
    exec(compile(rendered, "test_revision.py", "exec"), namespace)
    assert namespace["revision"] == "abc123"
    assert namespace["down_revision"] is None
    assert namespace["upgrade"]() is None
    assert namespace["downgrade"]() is None


def test_offline_upgrade_uses_settings_and_never_creates_an_engine(monkeypatch):
    use_database_url(monkeypatch, "sqlite:///:memory:")

    def unexpected_engine(*args, **kwargs):
        pytest.fail("Offline migrations must not create an engine")

    monkeypatch.setattr(sqlalchemy, "create_engine", unexpected_engine)
    config = configuration()
    command.upgrade(config, "head", sql=True)
    assert "CREATE TABLE" not in config.output_buffer.getvalue()
    assert config.get_main_option("sqlalchemy.url") is None


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_postgresql_offline_url_uses_psycopg_and_preserves_ssl(monkeypatch, scheme):
    secret = "synthetic%25password"
    use_database_url(
        monkeypatch,
        f"{scheme}://user:{secret}@example.invalid/db?sslmode=require",
    )
    captured = {}
    configure = context.configure

    def record_configuration(**kwargs):
        captured.update(kwargs)
        return configure(**kwargs)

    monkeypatch.setattr(context, "configure", record_configuration)
    config = configuration()
    command.upgrade(config, "head", sql=True)
    assert captured["url"].drivername == "postgresql+psycopg"
    assert captured["url"].query["sslmode"] == "require"
    assert captured["url"].password == "synthetic%password"
    assert len(captured["target_metadata"].tables) == 0
    assert secret not in config.output_buffer.getvalue()


@pytest.mark.parametrize(
    "value",
    [
        None,
        "invalid://user:synthetic-secret@host",
        "postgresql://user:synthetic-secret@host:notaport/db",
    ],
)
def test_unconfigured_or_invalid_url_has_safe_error(monkeypatch, value):
    use_database_url(monkeypatch, value)
    with pytest.raises(util.CommandError) as error:
        command.upgrade(configuration(), "head", sql=True)
    assert "DATABASE_URL" in str(error.value)
    assert "synthetic-secret" not in str(error.value)
    assert error.value.__suppress_context__


def test_online_connection_error_is_safe_and_engine_is_disposed(monkeypatch):
    use_database_url(monkeypatch, "sqlite:///:memory:")
    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    disposed = []
    dispose = engine.dispose

    def failed_connect():
        raise sqlalchemy_exc.SQLAlchemyError("synthetic-secret")

    def record_disposal():
        disposed.append(True)
        dispose()

    monkeypatch.setattr(engine, "connect", failed_connect)
    monkeypatch.setattr(engine, "dispose", record_disposal)
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *args, **kwargs: engine)
    with pytest.raises(util.CommandError) as error:
        command.current(configuration())
    assert "DATABASE_URL" in str(error.value)
    assert "synthetic-secret" not in str(error.value)
    assert error.value.__suppress_context__
    assert disposed == [True]


@pytest.mark.parametrize("cli_options", [None, SimpleNamespace(autogenerate=True)])
def test_autogeneration_without_schema_is_refused_before_engine_creation(
    monkeypatch, cli_options
):
    use_database_url(monkeypatch, "sqlite:///:memory:")

    def unexpected_engine(*args, **kwargs):
        pytest.fail("Empty schema must not be compared with a live database")

    monkeypatch.setattr(sqlalchemy, "create_engine", unexpected_engine)
    config = configuration()
    config.cmd_opts = cli_options
    with pytest.raises(util.CommandError, match="schema"):
        command.revision(config, message="unsafe comparison", autogenerate=True)
    assert script.ScriptDirectory.from_config(config).get_heads() == []
