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

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
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


class SamplingOptions(BaseModel):
    """Sampling fields that a provider or exact model can override."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    temperature: float = Field(default=0.0, ge=0, le=2, allow_inf_nan=False)
    # An explicit null removes top_p from the request, using the service default.
    top_p: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)


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
    # The machine manual's own collection, beside memory but never inside it
    # (`capstone.manual.index`): a manual section is fixed reference, a memory
    # is a past run's belief.
    manual_collection: str = Field(
        default="cnc_machine_manual_v1",
        min_length=3,
        validation_alias="MANUAL_COLLECTION",
    )
    # The manual step: with a manual offered (the default; `--no-manual` turns
    # it off), search it once on the anomaly before the agent plans, so the
    # guidance is there from the start. The `search_manual` tool stays. On by
    # default (developer, 2026-10-29); MANUAL_STEP=off turns only the step off.
    manual_step: bool = Field(default=True, validation_alias="MANUAL_STEP")
    line_context: bool = Field(default=False, validation_alias="LINE_CONTEXT")
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
    # A third router (2026-10-21): 100,000 free tokens a day, support agent only.
    llm7_api_key: SecretStr | None = _optional("LLM7_API_KEY")
    # Kilo Code's gateway (2026-10-21): a support agent or a fallback.
    kilo_code_api_key: SecretStr | None = _optional("KILO_CODE_API_KEY")
    # TypeSafe's System One API (2026-10-23): typed judgments (yes/no
    # probabilities, choices), not text. Used only by the evaluator's
    # auto-labeller, never by the agent.
    typesafe_api_key: SecretStr | None = _optional("TYPESAFE_API_KEY")
    typesafe_model: str = Field(
        default="jev-latest", min_length=1, validation_alias="TYPESAFE_MODEL"
    )

    # Which model answers which policy question. None: use default_model.
    default_model: str = Field(default=DEFAULT_MODEL, validation_alias="DEFAULT_MODEL")
    # JSON maps in .env: provider name or full provider/model reference to the
    # fields to override. Exact model fields take precedence over provider fields.
    provider_sampling: dict[str, SamplingOptions] = Field(
        default_factory=dict, validation_alias="PROVIDER_SAMPLING"
    )
    model_sampling: dict[str, SamplingOptions] = Field(
        default_factory=dict, validation_alias="MODEL_SAMPLING"
    )
    plan_model: str | None = _optional("PLAN_MODEL")
    decide_model: str | None = _optional("DECIDE_MODEL")
    interpret_model: str | None = _optional("INTERPRET_MODEL")
    hypothesize_model: str | None = _optional("HYPOTHESIZE_MODEL")
    conclude_model: str | None = _optional("CONCLUDE_MODEL")
    judge_model: str | None = _optional("JUDGE_MODEL")
    lesson_model: str | None = _optional("LESSON_MODEL")
    # P5: the model for the tree's second rating pass (TOT_REVALUE), ideally a
    # faster one; unset, the pass uses the hypothesize model.
    value_model: str | None = _optional("VALUE_MODEL")
    # Prompt visibility only: the confidence threshold is always enforced.
    state_action_bar: bool = Field(default=True, validation_alias="STATE_ACTION_BAR")
    # Questions per tool result. 1 (the default since 2026-10-30, developer's
    # decision) combines the interpretation with the next decision, using
    # DECIDE_MODEL (or DEFAULT_MODEL), about half the model questions; the
    # 2026-10-30 master runs asked 23-35 per case with 2 and timed out on every
    # batch and setting case. STEP_QUESTIONS=2 asks them separately.
    step_questions: int = Field(
        default=1, ge=1, le=2, validation_alias="STEP_QUESTIONS"
    )
    # The most tool calls one decide answer may list (developer, 2026-11-05).
    # 1, the default, is one call per answer, and the model's prompt and
    # answer schema stay exactly as before. Above 1 the model may list several
    # reads; the loop runs them in order, cuts the list at the first wait (time
    # only moves on its own), and then asks one question about all the new
    # evidence: fewer model questions per case. Each call still counts against
    # the tool-call budget.
    decide_calls: int = Field(default=1, ge=1, le=5, validation_alias="DECIDE_CALLS")
    # Stage views (developer, 2026-11-08): judge_verification is shown evidence
    # set out by when its data was taken relative to the work, with
    # same-signal before/after numbers and the gaps; write_lesson is shown the
    # conclusion, calls made and the factual brief instead of raw evidence.
    # Off by default, so every question sees the shared view and runs stay
    # comparable with the baseline.
    stage_context: bool = Field(default=False, validation_alias="STAGE_CONTEXT")
    # How hard NVIDIA's thinking models reason on the decide question only
    # (choosing the next tool; with STEP_QUESTIONS=1 it also interprets the
    # last result). Sent as "reasoning_effort", which NVIDIA documents for
    # Nemotron 3.5 Super: "low" and "medium" pick a shorter reasoning mode,
    # "high" is full reasoning. None (the default) sends nothing, so requests
    # stay as before and runs stay comparable. Other providers and every other
    # question are never sent it (developer, 2026-11-05).
    decide_reasoning_effort: Literal["low", "medium", "high"] | None = _optional(
        "DECIDE_REASONING_EFFORT"
    )
    # The late-run model (developer, 2026-11-09). Super 120B thinks at length,
    # and in the runs of 2026-10-31 to 2026-11-09 it timed out on 93 of 552
    # decide questions, mostly near the end of research. With LATE_MODEL set,
    # a decide question with less than LATE_MODEL_SECONDS left goes to it
    # instead (Super, given half of that time, answered in 30 s only 55% of
    # the time). LATE_CONCLUDE independently opts the conclusion into the
    # same model and threshold. None (the default) switches nothing.
    late_model: str | None = _optional("LATE_MODEL")
    late_model_seconds: float = Field(
        default=60.0, gt=0, validation_alias="LATE_MODEL_SECONDS"
    )
    # Off by default; when on, a late conclude question also uses LATE_MODEL.
    # Its own CONCLUDE_MODEL still handles an early conclusion.
    late_conclude: bool = Field(default=False, validation_alias="LATE_CONCLUDE")
    # The late model's thinking (developer, 2026-11-09: turn it off or lower
    # it). Off by default: NVIDIA is sent chat_template_kwargs.enable_thinking
    # false. On, LATE_MODEL_REASONING_BUDGET caps the thinking tokens
    # (`reasoning_budget`); unset leaves the cap to NVIDIA. Sent to NVIDIA
    # models only, never to the fallback, and only on routed late questions.
    late_model_thinking: bool = Field(
        default=False, validation_alias="LATE_MODEL_THINKING"
    )
    late_model_reasoning_budget: int | None = Field(
        default=None, ge=1, validation_alias="LATE_MODEL_REASONING_BUDGET"
    )
    # Asked when a job's own model cannot be reached. None: no fallback.
    # Several models, separated by commas, are tried in order: the second
    # when the first is out too (for example its daily quota is spent).
    fallback_model: str | None = _optional("FALLBACK_MODEL")

    # The critic (review only): a second model that judges the two leading
    # hypotheses before the conclusion and changes nothing in the run. Off by
    # default so runs stay comparable with the baseline. Its models are its
    # own primary list and CRITIC_FALLBACK_MODEL chain: the investigator's
    # FALLBACK_MODEL is never added. Comma-separated primary lists still work.
    critic: bool = Field(default=False, validation_alias="CRITIC")
    critic_model: str | None = _optional("CRITIC_MODEL")
    critic_fallback_model: str | None = _optional("CRITIC_FALLBACK_MODEL")
    # The critic's own time window, on top of the investigation's time.
    # Live check 2026-10-28: good answers took 4-10 s and the 30 s timeouts
    # never answered; 40 s gives each of two models about 20 s.
    critic_seconds: float = Field(default=40.0, gt=0, validation_alias="CRITIC_SECONDS")
    # The critic follow-up: when the critic objects, or agrees with a leading
    # hypothesis still below the action bar, the agent makes one more reading
    # where the critic pointed. Off by default, so the review-only critic stays
    # the baseline. Needs CRITIC on; without it there is nothing to follow up.
    critic_followup: bool = Field(default=False, validation_alias="CRITIC_FOLLOWUP")
    # The blind critic: shown the hypotheses shuffled, under neutral labels,
    # with no confidence and no "leading" mark, so it cannot anchor on the
    # agent's choice; code then sets its verdict from its pick. Off by default,
    # so the anchored critic stays the comparison. Needs CRITIC on.
    critic_blind: bool = Field(default=False, validation_alias="CRITIC_BLIND")
    # The follow-up's own window: one question, one call and one reading, on
    # top of the investigation's time. Live questions took 4-113 s on
    # 2026-10-27, so 90 s fits about two ordinary answers.
    critic_followup_seconds: float = Field(
        default=90.0, gt=0, validation_alias="CRITIC_FOLLOWUP_SECONDS"
    )

    # Tree-of-thought and hypothesis options (TOT_CRITIC_EVALUATION_FUTURE_WORK.md).
    # All off by default, so runs stay comparable with the archived ToT pairs.
    # The hypothesis reserve: research before the hypothesize question stops
    # this many seconds early, so a run that researches until its time is up
    # still forms explanations. 0 keeps no reserve. A tree question pair took
    # roughly 30-120 s live, so 120 is a reasonable trial value.
    hypothesis_reserve_seconds: float = Field(
        default=0.0, ge=0, validation_alias="HYPOTHESIS_RESERVE_SECONDS"
    )
    # P1, with --tree-of-thought only: top_k keeps the best three candidates;
    # evidence also keeps up to two more that cite factory evidence no kept one
    # cites, or that name a check for somewhere nobody has looked yet.
    tot_retain: Literal["top_k", "evidence"] = Field(
        default="top_k", validation_alias="TOT_RETAIN"
    )
    # P4: confidence ranks candidates by the model's confidence; evidence by
    # a transparent rubric first (verdict, factory evidence families for less
    # against, gaps), then confidence.
    tot_rank: Literal["confidence", "evidence"] = Field(
        default="confidence", validation_alias="TOT_RANK"
    )
    # P4: list the candidates to the rating question in an order rotated per
    # run, so `python -m capstone.tree_reach --positions` can measure position bias.
    tot_rotate: bool = Field(default=False, validation_alias="TOT_ROTATE")
    # P2: right after pruning, ask the critic (one extra critic question, in
    # its own window) whether one dropped candidate deserves a check; if so it
    # becomes the least believed hypothesis. Needs CRITIC on and a tree run.
    tot_reinstate: bool = Field(default=False, validation_alias="TOT_REINSTATE")
    # P3: decide from the agent's current beliefs whether to branch. A clear
    # case (one explanation at 0.8+, 0.3 ahead, two factory readings behind it)
    # gets the ordinary one-question step; an ambiguous one keeps one more.
    tot_adaptive: bool = Field(default=False, validation_alias="TOT_ADAPTIVE")
    # P5: after the test stage, rate the kept explanations once more against
    # the new evidence (one more question, skipped when no research time is
    # left); only a factory contradiction removes one.
    tot_revalue: bool = Field(default=False, validation_alias="TOT_REVALUE")
    # Rapid triage (MVP_SCOPE.md, "Split rapid triage from deep
    # investigation"): a short, read-only first look before the deep run.
    # Off by default (developer, 2026-11-05), so runs stay comparable with the
    # baseline. The time and call limits are starting points, not a measured
    # response-time target. TRIAGE_THEN_DEEP=off stops after the triage, to
    # measure it alone.
    triage: bool = Field(default=False, validation_alias="TRIAGE")
    triage_seconds: float = Field(default=90.0, gt=0, validation_alias="TRIAGE_SECONDS")
    triage_tool_calls: int = Field(
        default=6, ge=1, validation_alias="TRIAGE_TOOL_CALLS"
    )
    triage_then_deep: bool = Field(default=True, validation_alias="TRIAGE_THEN_DEEP")

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
    # The confidence a recommendation to intervene needs before the loop
    # accepts it (`InvestigationDeps.min_action_confidence`). 0.9 since the
    # loop was built; the value is the developer's decision (MAX-HIGH
    # change 3), to be set from measured runs, not a single one.
    min_action_confidence: float = Field(
        default=0.9, ge=0.0, le=1.0, validation_alias="MIN_ACTION_CONFIDENCE"
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
        "llm7_api_key",
        "kilo_code_api_key",
        "typesafe_api_key",
        "plan_model",
        "decide_model",
        "interpret_model",
        "hypothesize_model",
        "conclude_model",
        "judge_model",
        "lesson_model",
        "value_model",
        "late_model",
        "fallback_model",
        "critic_model",
        "critic_fallback_model",
        mode="before",
    )
    @classmethod
    def blank_is_missing(cls, value: object) -> object:
        """Treat blank strings as unconfigured; keep other secrets masked."""
        if isinstance(value, str):
            return value.strip() or None
        return value


def fallback_models(settings: Settings) -> tuple[str, ...]:
    """The fallback chain from FALLBACK_MODEL, in order; empty when none is set."""
    # Variables:
    #   settings: The project settings.
    #   chain: The models in the order they are tried, each once.
    #   reference: One model written as provider/model.
    if not settings.fallback_model:
        return ()
    chain: list[str] = []
    for reference in settings.fallback_model.split(","):
        reference = reference.strip()
        if reference and reference not in chain:
            chain.append(reference)
    return tuple(chain)


def critic_models(settings: Settings) -> tuple[str, ...]:
    """The critic's primary list then its own fallbacks, each model once."""
    # Variables:
    #   settings: The project settings.
    #   chain: The models in the order they are tried, each once.
    #   reference: One model written as provider/model.
    #   configured: The primary list followed by the critic-only backup list.
    if not settings.critic_model:
        return ()
    chain: list[str] = []
    for configured in (settings.critic_model, settings.critic_fallback_model):
        for reference in (configured or "").split(","):
            reference = reference.strip()
            if reference and reference not in chain:
                chain.append(reference)
    return tuple(chain)


def get_settings() -> Settings:
    """Read current configuration when requested, without import-time loading."""
    return Settings()
