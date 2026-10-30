"""Settings checks use temporary files and fake credentials, never Neon."""

import os

import pytest

from capstone.settings import Settings, critic_models, get_settings


@pytest.mark.parametrize("value", ["1", "2"])
def test_step_questions_can_be_selected_in_the_environment(monkeypatch, value):
    monkeypatch.setenv("STEP_QUESTIONS", value)
    assert Settings(_env_file=None).step_questions == int(value)


@pytest.mark.parametrize("value", ["0", "3", "1.5", "true"])
def test_step_questions_rejects_unsupported_modes(monkeypatch, value):
    monkeypatch.setenv("STEP_QUESTIONS", value)
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_step_questions_defaults_to_one(monkeypatch):
    """One question per step since 2026-10-30; STEP_QUESTIONS=2 asks two."""
    monkeypatch.delenv("STEP_QUESTIONS", raising=False)
    assert Settings(_env_file=None).step_questions == 1


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


def test_env_and_index_live_at_the_repository_root():
    # The package moved into capstone-code/ (PR #23); .env stayed at the top.
    from capstone.settings import REPO_ROOT

    assert (REPO_ROOT / "pyproject.toml").is_file()
    assert Settings.model_config["env_file"] == REPO_ROOT / ".env"
    assert Settings.model_fields["chroma_path"].default == REPO_ROOT / ".chroma"


@pytest.mark.parametrize("value, expected", [("true", True), ("false", False)])
def test_state_action_bar_is_an_environment_switch(monkeypatch, value, expected):
    monkeypatch.setenv("STATE_ACTION_BAR", value)
    assert Settings(_env_file=None).state_action_bar is expected


def test_state_action_bar_defaults_to_visible(monkeypatch):
    monkeypatch.delenv("STATE_ACTION_BAR", raising=False)
    assert Settings(_env_file=None).state_action_bar is True


CRITIC_CHAIN = (
    "mistral/ministral-14b-2512, cohere/command-a-03-2025, mistral/ministral-14b-2512"
)


def test_critic_settings_default_off(monkeypatch):
    for name in ("CRITIC", "CRITIC_MODEL", "CRITIC_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert s.critic is False
    assert s.critic_model is None
    assert s.critic_seconds == 40.0


def test_critic_on_and_chain(monkeypatch):
    monkeypatch.setenv("CRITIC", "on")
    monkeypatch.setenv("CRITIC_MODEL", CRITIC_CHAIN)
    s = Settings(_env_file=None)
    assert s.critic is True
    assert critic_models(s) == (
        "mistral/ministral-14b-2512",
        "cohere/command-a-03-2025",
    )


def test_blank_critic_model_is_unset(monkeypatch):
    monkeypatch.setenv("CRITIC_MODEL", "  ")
    s = Settings(_env_file=None)
    assert s.critic_model is None
    assert critic_models(s) == ()


def test_critic_seconds_must_be_positive(monkeypatch):
    monkeypatch.setenv("CRITIC_SECONDS", "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
