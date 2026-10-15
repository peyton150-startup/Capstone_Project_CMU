# The typed application settings, read from the environment and .env.
# Responsibility: load and check configuration when asked, and hide secret values.
"""Typed configuration, loaded on demand without changing process state."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The model NVIDIA's catalogue listed when this was written (see docs/PROGRESS.md).
NVIDIA_DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"


class Settings(BaseSettings):
    """Only implemented integrations have settings; credentials are optional."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr | None = Field(
        default=None, validation_alias="DATABASE_URL"
    )
    nvidia_api_key: SecretStr | None = Field(
        default=None, validation_alias="NVIDIA_API_KEY"
    )
    nvidia_model: str = Field(
        default=NVIDIA_DEFAULT_MODEL, validation_alias="NVIDIA_MODEL"
    )

    @field_validator("database_url", "nvidia_api_key", mode="before")
    @classmethod
    def normalize_secret(cls, value: object) -> object:
        """Treat blank strings as unconfigured; keep other secrets masked."""
        if isinstance(value, str):
            return value.strip() or None
        return value


def get_settings() -> Settings:
    """Read current configuration when requested, without import-time loading."""
    return Settings()
