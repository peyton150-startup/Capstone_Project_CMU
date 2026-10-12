from capstone.tools.actions import ActionTools, ApprovalDesk


def approve_and_run(desk: ApprovalDesk, act: ActionTools, proposal_id: int) -> dict:
    """The human says yes, then the approved work is started."""
    desk.approve(proposal_id)
    return act.execute_action(proposal_id)
