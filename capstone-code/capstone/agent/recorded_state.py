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
) -> InvestigationState:
    """Make a triage-only state for evidence review, never a repair workflow."""
    # Variables:
    #   run_id: Stable identifier for the same recorded review and its evidence.
    #   tick: The recorded cutoff on the replay provider's time axis.
    #   budgets: The operator's finite review budget or a short triage default.
    #   stage_context: Whether the policy uses the project's stage-specific views.
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
        stage_context=stage_context,
        state_action_bar=state_action_bar,
    )
