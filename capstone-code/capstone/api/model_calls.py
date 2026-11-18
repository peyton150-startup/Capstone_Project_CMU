"""Safe, versioned model-call projections for the managed simulator.

The source of truth is ModelPolicy.calls (ModelCall / Attempt). Never send
provider exception text, prompts, HTTP bodies, evidence or simulator truth to
browser clients. All externally visible values are revalidated on read.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
_IDENTIFIER = re.compile(r"[a-z][a-z_]{0,39}\Z")
_HASH = re.compile(r"[0-9a-f]{8,64}\Z")
_HTTP_STATUS = re.compile(r"\bHTTP (\d{3})\b")
MAX_ATTEMPTS = 64
MAX_CALLS = 200

AttemptOutcome = Literal[
    "answered", "invalid_reply", "timeout", "rate_limited", "unauthorized",
    "forbidden", "request_rejected", "provider_error", "unavailable",
    "budget_exhausted", "skipped", "other_error",
]


class SafeAttempt(BaseModel):
    """Only bounded operational request metadata; no provider text."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    attempt_index: int = Field(ge=1, le=MAX_ATTEMPTS)
    model: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
    outcome: AttemptOutcome
    seconds: float | None = Field(default=None, ge=0, le=3600)
    input_tokens: int | None = Field(default=None, ge=0, le=100_000_000)
    output_tokens: int | None = Field(default=None, ge=0, le=100_000_000)
    prompt_chars: int | None = Field(default=None, ge=0, le=100_000_000)
    prompt_version: str | None = Field(default=None, pattern=r"^[0-9a-f]{8,64}$")
    retry: bool = False
    fallback: bool = False


class SafeModelCall(BaseModel):
    """One model question with zero or more attempted requests."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1
    question_index: int = Field(ge=1, le=100_000)
    job: str = Field(pattern=r"^[a-z][a-z_]{0,39}$")
    agent: Literal["research_agent", "critic", "other"] = "research_agent"
    stage: str | None = Field(default=None, pattern=r"^[a-z][a-z_]{0,39}$")
    mode: Literal["triage", "deep"] | None = None
    outcome: Literal["answered", "invalid_reply", "no_answer"]
    answered_by: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$"
    )
    attempts: tuple[SafeAttempt, ...] = Field(max_length=MAX_ATTEMPTS)
    omitted_attempts: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    fallback_selected: bool = False
    fallback_succeeded: bool = False


class SafeModelConfiguration(BaseModel):
    """A bounded configuration result; never the missing key or error text."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    outcome: Literal["configured", "missing_credentials", "invalid_configuration"]


class SafeModelSummary(BaseModel):
    """Make incomplete telemetry explicit, rather than silently losing calls."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    questions_seen: int = Field(ge=0, le=100_000)
    questions_persisted: int = Field(ge=0, le=100_000)
    write_failures: int = Field(ge=0, le=100_000)
    complete: bool


def safe_model_name(value: object) -> str:
    """Never echo arbitrary strings from configuration or provider responses."""
    if isinstance(value, str) and _MODEL.fullmatch(value):
        if not value.lower().startswith(("sk-", "nvapi-", "bearer", "api_key")):
            return value
    return "redacted"


def safe_identifier(value: object) -> str:
    return value if isinstance(value, str) and _IDENTIFIER.fullmatch(value) else "other"


def safe_count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 100_000_000 else None


def safe_seconds(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
        if math.isfinite(result) and 0 <= result <= 3600:
            return round(result, 3)
    return None


def classify_outcome(value: object) -> AttemptOutcome:
    """Map a private error to a fixed category, never expose its message."""
    if value == "answered":
        return "answered"
    if not isinstance(value, str):
        return "other_error"
    if value.startswith("invalid reply"):
        return "invalid_reply"
    if value.startswith("skipped:"):
        return "skipped"
    if value.startswith("out of time") or "no time left" in value:
        return "budget_exhausted"
    if "timed out" in value:
        return "timeout"
    match = _HTTP_STATUS.search(value)
    if match:
        code = int(match.group(1))
        if code == 401:
            return "unauthorized"
        if code == 403:
            return "forbidden"
        if code == 429:
            return "rate_limited"
        if 400 <= code < 500:
            return "request_rejected"
        if 500 <= code <= 599:
            return "provider_error"
    if "could not be reached" in value or "unreachable" in value:
        return "unavailable"
    return "other_error"


def project_model_call(call: Any, question_index: int) -> dict[str, Any]:
    """Validate an explicitly selected subset of the ModelCall contract.

    Called only by the trusted worker. The response reader separately validates
    every persisted row, even if database content was altered outside this code.
    """
    raw_attempts = tuple(getattr(call, "attempts", ()) or ())
    attempts = []
    first_model = (
        safe_model_name(getattr(raw_attempts[0], "model", None))
        if raw_attempts else None
    )
    previous_model = None
    for number, source in enumerate(raw_attempts[:MAX_ATTEMPTS], start=1):
        model = safe_model_name(getattr(source, "model", None))
        retry = (
            previous_model == model
            and model != "redacted"
            and classify_outcome(getattr(source, "outcome", None)) != "skipped"
        )
        fallback = (
            first_model is not None
            and first_model != "redacted"
            and model != "redacted"
            and model != first_model
        )
        version = getattr(source, "prompt_version", None)
        attempts.append(
            SafeAttempt(
                attempt_index=number,
                model=model,
                outcome=classify_outcome(getattr(source, "outcome", None)),
                seconds=safe_seconds(getattr(source, "seconds", None)),
                input_tokens=safe_count(getattr(source, "input_tokens", None)),
                output_tokens=safe_count(getattr(source, "output_tokens", None)),
                prompt_chars=safe_count(getattr(source, "prompt_chars", None)),
                prompt_version=version
                if isinstance(version, str) and _HASH.fullmatch(version)
                else None,
                retry=retry,
                fallback=fallback,
            )
        )
        previous_model = model

    answered = getattr(call, "answered_by", None)
    answered_by = safe_model_name(answered) if answered is not None else None
    return SafeModelCall(
        question_index=question_index,
        job=safe_identifier(getattr(call, "job", None)),
        agent=(
            getattr(call, "agent", None)
            if getattr(call, "agent", None) in ("research_agent", "critic")
            else "other"
        ),
        stage=(
            safe_identifier(getattr(call, "stage", None))
            if getattr(call, "stage", None) is not None else None
        ),
        mode=getattr(call, "mode", None)
        if getattr(call, "mode", None) in ("triage", "deep") else None,
        outcome=getattr(call, "outcome"),
        answered_by=answered_by,
        attempts=tuple(attempts),
        omitted_attempts=max(0, len(raw_attempts) - MAX_ATTEMPTS),
        retry_count=sum(a.retry for a in attempts),
        fallback_selected=any(
            a.fallback and a.outcome != "skipped" for a in attempts
        ),
        fallback_succeeded=any(
            a.fallback and a.outcome == "answered" for a in attempts
        ),
    ).model_dump(mode="json")
