# The typed application settings, read from the environment and .env.
# Responsibility: load and check configuration when asked, and hide secret values.
"""Typed configuration, loaded on demand without changing process state."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Free-text memory recall: "semantic" (ChromaDB, falls back to keyword when
    # Chroma is unavailable), "keyword" (SQL store only), or "none" (disabled).
    memory_retrieval_mode: Literal["semantic", "keyword", "none"] = Field(
        default="semantic", validation_alias="MEMORY_RETRIEVAL_MODE"
    )
    chroma_path: Path = Field(
        default=Path(__file__).resolve().parents[1] / ".chroma",
        validation_alias="CHROMA_PATH",
    )
    chroma_collection: str = Field(
        default="episodic_memories", min_length=3, validation_alias="CHROMA_COLLECTION"
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        """Treat blank strings as unconfigured; keep other secrets masked."""
        if isinstance(value, str):
            return value.strip() or None
        return value


def get_settings() -> Settings:
    """Read current configuration when requested, without import-time loading."""
    return Settings()
