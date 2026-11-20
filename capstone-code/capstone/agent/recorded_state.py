# Construct read-only recorded-investigation state within the agent's boundary.
# Responsibility: own the runtime anomaly record without exposing it to other packages.
"""One approved capture becomes an agent investigation state, not simulator truth."""

from uuid import UUID

from capstone.agent.artifacts import DetectedAnomaly
from capstone.agent.state import Budgets, InvestigationState, triage_budgets
from capstone.contracts.investigations import investigation_id_for


def make_recorded_state(
    run_id: UUID,
    *,
    machine_id: str,
    description: str,
    tick: int,
    budgets: Budgets | None,
    stage_context: bool,
    state_action_bar: bool,
    triage_packet: bool = False,
    triage_packet_prompt: bool = False,
    triage_conclude_brief: bool = False,
    triage_conclude_cap: bool = False,
    triage_ranking: bool = False,
    triage_fixed_plan: bool = False,
) -> InvestigationState:
    """Make a triage-only state for evidence review, never a repair workflow."""
    # Variables:
    #   run_id: Stable identifier for the same recorded review and its evidence.
    #   tick: The recorded cutoff on the replay provider's time axis.
    #   budgets: The operator's finite review budget or a short triage default.
    #   stage_context: Whether the policy uses the project's stage-specific views.
    #   triage_packet: TRIAGE_PACKET; the packet then records the screening as
    #     missing (no verified healthy reference), never as normal.
    #   triage_packet_prompt: TRIAGE_PACKET_PROMPT; the prompts then show the
    #     packet's coverage, including that missing screening.
    #   triage_conclude_brief: TRIAGE_CONCLUDE_BRIEF; the conclusion question
    #     then shows what was tested, measured and missing.
    #   triage_conclude_cap: TRIAGE_CONCLUDE_CAP; the conclusion question then
    #     keeps to the triage's conclusion window.
    #   triage_ranking: TRIAGE_RANKING; the conclusion then also names two
    #     candidates, when any were compiled.
    return InvestigationState(
        run_id=run_id,
        investigation_id=investigation_id_for(run_id, 1),
        anomaly=DetectedAnomaly(
            tick=tick,
            machine_id=machine_id,
            kind="operator_review",
            description=description,
        ),
        budgets=budgets or triage_budgets(),
        mode="triage",
        line_context_enabled=False,
        triage_packet_enabled=triage_packet,
        triage_packet_prompt=triage_packet_prompt,
        triage_conclude_brief=triage_conclude_brief,
        triage_conclude_cap=triage_conclude_cap,
        triage_ranking_enabled=triage_ranking,
        triage_fixed_plan=triage_fixed_plan,
        stage_context=stage_context,
        state_action_bar=state_action_bar,
    )
