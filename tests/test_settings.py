"""Settings checks use temporary files and fake credentials, never Neon."""

import os

import pytest

from capstone.settings import Settings, get_settings


def test_environment_takes_precedence_over_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('DATABASE_URL="postgresql://file:password@localhost/db"\n')
    monkeypatch.setenv("DATABASE_URL", "postgresql://env:password@localhost/db")
    settings = Settings(_env_file=env_file)
    assert (
        settings.database_url.get_secret_value()
        == "postgresql://env:password@localhost/db"
    )


def test_dotenv_does_not_mutate_environment(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'DATABASE_URL="postgresql://file:password@localhost/db"\nUNRELATED_KEY=ignored\n'
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=env_file)
    assert (
        settings.database_url.get_secret_value()
        == "postgresql://file:password@localhost/db"
    )
    assert "DATABASE_URL" not in os.environ


def test_database_configuration_is_optional(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert Settings(_env_file=None).database_url is None


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_configuration_is_treated_as_missing(monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", value)
    assert Settings(_env_file=None).database_url is None


def test_secret_is_masked_in_representations(monkeypatch):
    secret = "postgresql://test:private-password@localhost/db"
    monkeypatch.setenv("DATABASE_URL", secret)
    settings = Settings(_env_file=None)
    assert secret not in repr(settings)
    assert "private-password" not in settings.model_dump_json()
    assert settings.database_url.get_secret_value() == secret


def test_get_settings_reads_current_environment_without_stale_cache(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://first:password@localhost/db")
    first = get_settings()
    monkeypatch.setenv("DATABASE_URL", "postgresql://second:password@localhost/db")
    second = get_settings()
    assert (
        first.database_url.get_secret_value()
        == "postgresql://first:password@localhost/db"
    )
    assert (
        second.database_url.get_secret_value()
        == "postgresql://second:password@localhost/db"
    )
