# The typed application settings, read from the environment and .env.
# Responsibility: load and check configuration when asked, and hide secret values.
"""Typed configuration, loaded on demand without changing process state.

Models are named "provider/model", for example
"nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b" or "groq/<model>". Every
policy question uses DEFAULT_MODEL unless its own setting names another,
so any model can do any job.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The developer's choice for the agent (2026-10-20); listed by NVIDIA's hosted
# API that day. The earlier default was nemotron-3.5-lightning-30b-a3b.
DEFAULT_MODEL = "nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b"

# The developer's choice for memory search (2026-10-20): 2,048 numbers per text.
DEFAULT_EMBEDDING_MODEL = "nvidia/nvidia/nemotron-3-embed-1b"


# The repository's top folder (the one holding pyproject.toml and .env):
# this file is capstone-code/capstone/settings.py, two folders below it.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _optional(alias: str):
    """An optional setting read from the environment name `alias`."""
    return Field(default=None, validation_alias=alias)


class Settings(BaseSettings):
    """Only implemented integrations have settings; credentials are optional."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr | None = _optional("DATABASE_URL")

    # Free-text memory recall: "semantic" (ChromaDB, falls back to keyword when
    # Chroma is unavailable), "keyword" (SQL store only), or "none" (disabled).
    memory_retrieval_mode: Literal["semantic", "keyword", "none"] = Field(
        default="semantic", validation_alias="MEMORY_RETRIEVAL_MODE"
    )
    chroma_path: Path = Field(
        default=REPO_ROOT / ".chroma",
        validation_alias="CHROMA_PATH",
    )
    chroma_collection: str = Field(
        default="episodic_memories", min_length=3, validation_alias="CHROMA_COLLECTION"
    )
    # The model that turns memories and searches into vectors: "provider/model"
    # (NVIDIA only for now) or "local" for Chroma's bundled all-MiniLM-L6-v2.
    # Changing it means rebuilding the index: `python -m capstone.memory.backfill
    # --rebuild`.
    embedding_model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL, validation_alias="EMBEDDING_MODEL"
    )

    # One key per model provider in scope.
    nvidia_api_key: SecretStr | None = _optional("NVIDIA_API_KEY")
    groq_api_key: SecretStr | None = _optional("GROQ_API_KEY")
    mistral_api_key: SecretStr | None = _optional("MISTRAL_API_KEY")
    gemini_api_key: SecretStr | None = _optional("GEMINI_API_KEY")
    cohere_api_key: SecretStr | None = _optional("COHERE_API_KEY")
    cloudflare_api_token: SecretStr | None = _optional("CLOUDFLARE_API_TOKEN")
    cloudflare_account_id: str | None = _optional("CLOUDFLARE_ACCOUNT_ID")
    # Two model routers (added 2026-10-21): they pass a model name on.
    requesty_api_key: SecretStr | None = _optional("REQUESTY_API_KEY")
    xkiro_api_key: SecretStr | None = _optional("XKIRO_API_KEY")

    # Which model answers which policy question. None: use default_model.
    default_model: str = Field(default=DEFAULT_MODEL, validation_alias="DEFAULT_MODEL")
    plan_model: str | None = _optional("PLAN_MODEL")
    decide_model: str | None = _optional("DECIDE_MODEL")
    interpret_model: str | None = _optional("INTERPRET_MODEL")
    hypothesize_model: str | None = _optional("HYPOTHESIZE_MODEL")
    conclude_model: str | None = _optional("CONCLUDE_MODEL")
    judge_model: str | None = _optional("JUDGE_MODEL")
    lesson_model: str | None = _optional("LESSON_MODEL")
    # Asked when a job's own model cannot be reached. None: no fallback.
    fallback_model: str | None = _optional("FALLBACK_MODEL")

    # Limits on every model question (MVP_SCOPE.md section 3). The loop's own
    # limits (iterations, tool calls, time per investigation) are in Budgets.
    # The most tokens one reply may use, thinking included. Measured live on
    # 2026-10-20: the thinking models used 450-1,050 reasoning tokens on the
    # 120b model and up to 6,950 on nemotron lightning before the answer, so
    # the earlier 2,048 could cut a reply off before its JSON began. On
    # 2026-10-21, with 120 s waits, 3 of the 120b model's replies were cut off
    # at 8,192 (recorded since PR #43), so the limit is now 16,384.
    model_max_output_tokens: int = Field(
        default=16384, ge=1, validation_alias="MODEL_MAX_OUTPUT_TOKENS"
    )
    # How long one request may wait, and one question in all (retries and the
    # fallback model included). Measured live on 2026-10-20: the default model
    # answered one small question in 6, 10, 6 and 40 s and once not in 120 s,
    # and a planning question took 37 s, so the earlier 15 s / 20 s ended most
    # runs as "model unavailable". A request past 45 s is usually stuck in the
    # provider's queue: asking again or the fallback is quicker than waiting.
    model_request_seconds: float = Field(
        default=45.0, gt=0, validation_alias="MODEL_REQUEST_SECONDS"
    )
    model_question_seconds: float = Field(
        default=90.0, gt=0, validation_alias="MODEL_QUESTION_SECONDS"
    )
    # How many more times an unreachable model is asked before moving on.
    # Measured live on 2026-10-20: NVIDIA's hosted API answered HTTP 500 in
    # 0.3 s several times an episode, and one retry 2 s later often failed
    # too; three retries with doubling pauses (2, 4, 8 s) cost 14 s at most.
    model_retries: int = Field(default=3, ge=0, validation_alias="MODEL_RETRIES")

    @field_validator(
        "database_url",
        "nvidia_api_key",
        "groq_api_key",
        "mistral_api_key",
        "gemini_api_key",
        "cohere_api_key",
        "cloudflare_api_token",
        "cloudflare_account_id",
        "requesty_api_key",
        "xkiro_api_key",
        "plan_model",
        "decide_model",
        "interpret_model",
        "hypothesize_model",
        "conclude_model",
        "judge_model",
        "lesson_model",
        "fallback_model",
        mode="before",
    )
    @classmethod
    def blank_is_missing(cls, value: object) -> object:
        """Treat blank strings as unconfigured; keep other secrets masked."""
        if isinstance(value, str):
            return value.strip() or None
        return value


def get_settings() -> Settings:
    """Read current configuration when requested, without import-time loading."""
    return Settings()
