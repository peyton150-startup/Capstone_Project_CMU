"""Safe, typed read-only lifecycle projection for full investigations.

Uses fields already owned by Pydantic Graph InvestigationState. No model calls,
tool reads, prompts, raw telemetry, private review notes or simulator answer keys.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DeepStage = Literal[
    "observe",
    "manual",
    "plan",
    "investigate",
    "hypothesize",
    "test",
    "critique",
    "recheck",
    "conclude",
    "decide",
    "propose",
    "execute",
    "verify",
]

CriticOutcome = Literal["answered", "invalid_reply", "no_answer"]
RecheckOutcome = Literal[
    "observed",
    "no_evidence",
    "policy_stopped",
    "invalid_decision",
    "out_of_time",
    "skipped",
    "already_answered",
]
ProposalStatus = Literal["pending", "approved", "rejected", "not_submitted"]
VerificationOutcome = Literal[
    "resolved", "not_resolved", "inconclusive", "not_performed"
]


class SafeDeepSignals(BaseModel):
    """Explicitly allowed deep-loop milestones; no free-text model outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    critic_outcome: CriticOutcome | None = None
    recheck_outcome: RecheckOutcome | None = None
    critic_tool_calls: int = Field(default=0, ge=0)
    pruned_candidates: int = Field(default=0, ge=0)
    hypothesis_revisions: int = Field(default=0, ge=0)
    conclusion_assessment: Literal["supported", "unresolved"] | None = None
    conclusion_recommendation: Literal["intervene", "no_action", "escalate"] | None = None
    conclusion_evidence_count: int = Field(default=0, ge=0)
    proposal_status: ProposalStatus | None = None
    action_started: bool = False
    action_finished: bool = False
    verification_outcome: VerificationOutcome | None = None
    verification_observed: bool = False
    verification_tick: int | None = Field(default=None, ge=0)


class SafeDeepCheckpoint(BaseModel):
    """One observed stage transition, not a guessed or planned step."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    sequence: int = Field(ge=1)
    stage: DeepStage
    iteration_count: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    hypothesis_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)
    observed_tick: int | None = Field(default=None, ge=0)


def _allowed(value: Any, options: tuple[str, ...]) -> str | None:
    """An unknown enum is absent, not free-form text that leaks to the browser."""
    return value if isinstance(value, str) and value in options else None


def safe_deep_signals(state: Any) -> SafeDeepSignals:
    """Read only bounded statuses/counts from a Pydantic Graph deep state."""
    if state.mode != "deep":
        raise ValueError("Deep lifecycle requires a deep investigation")

    critique = getattr(state, "critique", None)
    recheck = getattr(state, "recheck", None)
    conclusion = getattr(state, "conclusion", None)
    proposed = getattr(state, "proposed_action", None)
    check = getattr(state, "verification", None)

    outcome = _allowed(
        getattr(check, "outcome", None),
        ("resolved", "not_resolved", "inconclusive", "not_performed"),
    )
    checked_tick = getattr(check, "checked_tick", None)
    if type(checked_tick) is not int or checked_tick < 0:
        checked_tick = None

    return SafeDeepSignals(
        critic_outcome=_allowed(
            getattr(critique, "outcome", None),
            ("answered", "invalid_reply", "no_answer"),
        ),
        recheck_outcome=_allowed(
            getattr(recheck, "outcome", None),
            (
                "observed",
                "no_evidence",
                "policy_stopped",
                "invalid_decision",
                "out_of_time",
                "skipped",
                "already_answered",
            ),
        ),
        critic_tool_calls=getattr(state, "critic_tool_calls_used", 0),
        pruned_candidates=len(getattr(state, "pruned_candidates", ())),
        hypothesis_revisions=getattr(state, "hypothesis_revisions", 0),
        conclusion_assessment=_allowed(
            getattr(conclusion, "assessment", None), ("supported", "unresolved")
        ),
        conclusion_recommendation=_allowed(
            getattr(conclusion, "recommendation", None),
            ("intervene", "no_action", "escalate"),
        ),
        conclusion_evidence_count=len(getattr(conclusion, "evidence_ids", ())),
        proposal_status=_allowed(
            getattr(proposed, "status", None),
            ("pending", "approved", "rejected", "not_submitted"),
        ),
        action_started=getattr(state, "action_started_tick", None) is not None,
        action_finished=getattr(state, "action_finish_tick", None) is not None,
        verification_outcome=outcome,
        verification_observed=checked_tick is not None
        and outcome not in (None, "not_performed"),
        verification_tick=checked_tick,
    )


def checkpoint_from_stage(sequence: int, stage: dict[str, Any]) -> SafeDeepCheckpoint:
    """Revalidate the persisted Pydantic snapshot before adding a milestone."""
    if stage.get("mode") != "deep":
        raise ValueError("Stage transition is not from the deep investigation")
    return SafeDeepCheckpoint(
        sequence=sequence,
        stage=stage["stage"],
        iteration_count=stage["iteration_count"],
        tool_calls=stage["tool_calls"],
        evidence_count=stage["evidence_count"],
        hypothesis_count=stage["hypothesis_count"],
        decision_count=stage["decision_count"],
        observed_tick=stage.get("last_observed_tick"),
    )
