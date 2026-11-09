"""The human reviewer is shown the evidence behind a proposal, not just its reason."""

from capstone.agent.artifacts import ProposalRecord, ReviewPacket
from capstone.episode import review_text
from tests.test_agent_action import Factory, investigate


def reviewed():
    """Run the scripted wear investigation and keep what the reviewer was handed."""
    factory, seen = Factory(), []

    def human(proposal):
        seen.append(proposal)
        factory.desk.approve(proposal.proposal_id)

    state = investigate(factory, human)
    return state, seen


def test_the_reviewer_gets_a_packet_that_is_still_a_proposal():
    _, seen = reviewed()
    (packet,) = seen
    assert isinstance(packet, ReviewPacket)
    assert isinstance(packet, ProposalRecord)  # older reviewers keep working
    assert packet.action == "replace_bearing" and packet.machine_id == "CNC-02"


def test_the_packet_carries_the_belief_prediction_and_cited_evidence():
    state, seen = reviewed()
    (packet,) = seen
    assert packet.diagnosis == "wear on CNC-02"
    assert packet.confidence == 0.95
    assert packet.predicted_effect == state.predicted_effect
    assert [line.split(" ")[0] for line in packet.evidence] == ["E3", "E4"]
    assert packet.evidence[0].startswith("E3 get_sensor_summary: ")


def test_the_packet_does_not_change_what_the_run_records():
    state, _ = reviewed()
    # The record keeps a plain ProposalRecord; the packet is display only.
    assert type(state.proposed_action) is ProposalRecord
    assert state.proposed_action.status == "approved"


def test_evidence_is_cut_short_for_the_reviewer():
    _, seen = reviewed()
    assert all(len(line) < 260 for line in seen[0].evidence)


def test_console_text_shows_the_extra_fields():
    packet = ReviewPacket(
        proposal_id=1,
        machine_id="CNC-02",
        action="replace_bearing",
        reason="vibration climbing",
        status="pending",
        diagnosis="bearing wear",
        confidence=0.93,
        predicted_effect="vibration falls",
        evidence=("E3 get_readings: [1.2, 1.4]",),
        critic_view="agrees: favours H1. fits the trend",
    )
    text = review_text(packet)
    for part in (
        "replace_bearing on CNC-02",
        "Diagnosis (confidence 0.93): bearing wear",
        "Expected afterwards: vibration falls",
        "Critic agrees: favours H1",
        "E3 get_readings: [1.2, 1.4]",
    ):
        assert part in text


def test_console_text_still_works_for_a_plain_proposal():
    plain = ProposalRecord(
        proposal_id=2,
        machine_id="CNC-01",
        action="reset_setting",
        reason="r",
        status="pending",
    )
    assert review_text(plain).splitlines() == [
        "Proposal 2: reset_setting on CNC-01",
        "  Reason: r",
    ]
