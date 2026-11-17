"""Immutable, per-run triage settings resolved before a managed Graph run.

Only allowed stage controls appear here. The resolver never mutates process
environment, model provider credentials, simulator truth, or deep settings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from capstone.settings import Settings, TriageExecutionProfile

RunMode = Literal["custom", "deterministic"]
Plan = Literal["fixed", "model"]
Investigate = Literal["deterministic", "advisory", "on", "off"]
Hypothesize = Literal["deterministic", "model"]
ObserveCalls = Literal["shared", "separate"]


class TriageRunOptions(BaseModel):
    """Optional requested overrides; absent fields inherit server defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    run_mode: RunMode | None = None
    plan: Plan | None = None
    investigate: Investigate | None = None
    hypothesize: Hypothesize | None = None
    evidence_tests: bool | None = None
    packet: bool | None = None
    packet_prompt: bool | None = None
    observe_calls: ObserveCalls | None = None
    then_deep: bool | None = None
    conclude_brief: bool | None = None
    conclude_cap: bool | None = None
    seconds: float | None = Field(default=None, ge=5, le=900, allow_inf_nan=False)
    tool_calls: int | None = Field(default=None, ge=1, le=30)
    hypothesis_seconds: float | None = Field(
        default=None, ge=0, le=300, allow_inf_nan=False
    )


class EffectiveTriageRun(BaseModel):
    """Validated, frozen values injected into one triage execution only."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    run_mode: RunMode
    plan: Plan
    investigate: Investigate
    hypothesize: Hypothesize
    evidence_tests: bool
    packet: bool
    packet_prompt: bool
    observe_calls: ObserveCalls
    then_deep: bool
    conclude_brief: bool
    conclude_cap: bool
    seconds: float = Field(ge=5, le=900, allow_inf_nan=False)
    tool_calls: int = Field(ge=1, le=30)
    hypothesis_seconds: float = Field(ge=0, le=300, allow_inf_nan=False)

    @model_validator(mode="after")
    def guarded_profile(self):
        if self.investigate == "deterministic" and self.plan != "fixed":
            raise ValueError("deterministic Investigate requires fixed Plan")
        if self.hypothesize == "deterministic" and (
            self.plan != "fixed"
            or self.investigate != "deterministic"
            or not self.evidence_tests
        ):
            raise ValueError(
                "deterministic Hypothesize requires fixed Plan, "
                "deterministic Investigate and evidence tests"
            )
        if self.packet_prompt and not self.packet:
            raise ValueError("packet prompt requires evidence packet")
        if self.run_mode == "deterministic" and (
            self.plan != "fixed"
            or self.investigate != "deterministic"
            or self.hypothesize != "deterministic"
            or not self.evidence_tests
            or not self.packet
            or not self.packet_prompt
            or self.observe_calls != "separate"
            or self.hypothesis_seconds != 0
        ):
            raise ValueError(
                "deterministic run override must control all triage stages"
            )
        if self.seconds <= self.hypothesis_seconds:
            raise ValueError("hypothesis reserve must leave triage research time")
        return self

    @property
    def profile(self) -> TriageExecutionProfile:
        """Adapter to existing Pydantic Graph state/dependency profile."""
        return TriageExecutionProfile(
            run_mode=self.run_mode,
            plan=self.plan,
            investigate=self.investigate,
            hypothesize=self.hypothesize,
            evidence_tests=self.evidence_tests,
            packet=self.packet,
            packet_prompt=self.packet_prompt,
            observe_calls=self.observe_calls,
            hypothesis_seconds=self.hypothesis_seconds,
            critic=False,
            critic_followup=False,
            critic_reinstate=False,
        )

    def stage_modes(self) -> dict[str, str]:
        """Safe semantic summary, not guesses about actual provider success."""
        return {
            "observe": "deterministic",
            "manual": "authorized retrieval when selected",
            "plan": "deterministic" if self.plan == "fixed" else "model",
            "investigate": (
                "deterministic" if self.investigate == "deterministic"
                else "model or assisted"
            ),
            "decide_interpret": (
                "deterministic" if self.investigate == "deterministic"
                else "model or assisted"
            ),
            "hypothesize": (
                "deterministic" if self.hypothesize == "deterministic" else "model"
            ),
            "test": (
                "deterministic" if self.investigate == "deterministic"
                else "model or assisted"
            ),
            "critic_recheck": "off",
            "conclude": "model",
            "triage_actions": "read-only",
            "deep_escalation": "conditional" if self.then_deep else "off",
        }


def resolve_triage_run(
    settings: Settings,
    requested: TriageRunOptions | None = None,
) -> EffectiveTriageRun:
    """One source of truth for preview, admission and Graph runtime.

    A deterministic profile overrides stage fields, but does not override
    explicit budgets or model-backed Conclude options. Custom selections
    obey the same guarded-stage preconditions as the legacy Settings model.
    """
    options = requested or TriageRunOptions()

    def get(name: str, fallback):
        chosen = getattr(options, name)
        return fallback if chosen is None else chosen

    run_mode = get("run_mode", settings.triage_run_mode)
    if run_mode == "deterministic":
        plan, investigate, hypothesize = "fixed", "deterministic", "deterministic"
        evidence_tests, packet, packet_prompt = True, True, True
        observe_calls, hypothesis_seconds = "separate", 0.0
    else:
        plan = get("plan", settings.triage_plan)
        investigate = get("investigate", settings.triage_investigate)
        hypothesize = get("hypothesize", settings.triage_hypothesize)
        evidence_tests = get("evidence_tests", settings.triage_evidence_tests)
        packet = get("packet", settings.triage_packet)
        packet_prompt = get("packet_prompt", settings.triage_packet_prompt)
        observe_calls = get("observe_calls", settings.triage_observe_calls)
        hypothesis_seconds = get(
            "hypothesis_seconds", settings.triage_hypothesis_seconds
        )
    return EffectiveTriageRun(
        run_mode=run_mode,
        plan=plan,
        investigate=investigate,
        hypothesize=hypothesize,
        evidence_tests=evidence_tests,
        packet=packet,
        packet_prompt=packet_prompt,
        observe_calls=observe_calls,
        then_deep=get("then_deep", settings.triage_then_deep),
        conclude_brief=get("conclude_brief", settings.triage_conclude_brief),
        conclude_cap=get("conclude_cap", settings.triage_conclude_cap),
        seconds=get("seconds", settings.triage_seconds),
        tool_calls=get("tool_calls", settings.triage_tool_calls),
        hypothesis_seconds=hypothesis_seconds,
    )


def overridden_fields(
    requested: TriageRunOptions | None, effective: EffectiveTriageRun
) -> tuple[str, ...]:
    """Only overridden *explicit* fields, never raw secrets or free text."""
    if requested is None:
        return ()
    fields = requested.model_dump(exclude_none=True)
    return tuple(
        name for name, value in fields.items()
        if getattr(effective, name) != value
    )
