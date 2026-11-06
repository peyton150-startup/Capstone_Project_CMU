"""Rapid triage: a short, read-only first look before the deep investigation.

What these tests prove, with scripted policies and a fake clock (no model):
triage is off by default; a triage never proposes, executes or verifies,
whatever the model recommends; code, not the model, decides whether a deep
run follows; the deep run has its own investigation id and a reference to
the triage, and keeps human approval and verification; the triage's
deadline holds even when every answer is slow; and experiment records
report the triage's timing and outcome.
"""

import pytest

from capstone.agent.artifacts import AgentConclusion
from capstone.agent.investigation import needs_deep_run
from capstone.agent.state import TRIAGE_CONCLUDE_SECONDS, triage_budgets
from capstone.episode import run_episode
from capstone.experiment import (
    Case,
    format_triage,
    nearest_rank,
    report,
    run_experiment,
)
from tests.helpers import FakeCritic
from tests.test_episode import MACHINE, SEED, wear_policy


class ByMode:
    """One scripted policy for the triage and a fresh one for the deep run.

    A scripted policy plays its decisions back from queues, so one policy
    used for both runs would leave the deep run nothing to ask. Each method
    goes to the policy for the mode of the state it is asked about.
    """

    def __init__(self, triage, deep):
        self.triage, self.deep = triage, deep

    def __getattr__(self, name):
        # Variables:
        #   name: The policy method asked for; missing on either, missing here.
        getattr(self.triage, name), getattr(self.deep, name)

        def call(state, *args, **kwargs):
            # Variables:
            #   state: The investigation asked about; its mode picks the policy.
            mine = self.triage if state.mode == "triage" else self.deep
            return getattr(mine, name)(state, *args, **kwargs)

        return call


def triage_then_deep(triage_recommends="intervene"):
    return ByMode(wear_policy(triage_recommends), wear_policy())


def run(policy, monkeypatch, *, then_deep=True, clock=lambda: 0.0, **options):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "on" if then_deep else "off")
    return run_episode(
        SEED, policy, fault="bearing_degradation", clock=clock, **options
    )


# --- off unless asked for ---------------------------------------------------


def test_triage_is_off_by_default(monkeypatch):
    monkeypatch.delenv("TRIAGE", raising=False)
    result = run(wear_policy(), monkeypatch)
    assert result.triage is None and result.triage_seconds is None
    assert result.state.mode == "deep" and result.state.follows_triage is None
    assert result.state.deep_recommended is None


def test_the_triage_setting_turns_it_on(monkeypatch):
    monkeypatch.setenv("TRIAGE", "on")
    result = run(triage_then_deep(), monkeypatch)
    assert result.triage is not None and result.triage.mode == "triage"


# --- read-only, enforced by the graph ---------------------------------------


def test_a_triage_that_wants_a_fix_proposes_nothing(monkeypatch):
    result = run(
        triage_then_deep("intervene"), monkeypatch, then_deep=False, triage=True
    )
    first = result.triage
    assert result.state is first  # no deep run followed
    assert first.policy_recommendation == "intervene"  # what the model wanted
    assert first.proposed_action is None
    assert first.action_started_tick is None and first.verification is None
    assert not any(
        d.tool in ("propose_action", "execute_action") for d in first.decisions
    )
    assert result.score.actions_taken == []
    assert first.deep_recommended is True


def test_a_triage_never_verifies_even_when_nothing_needs_doing(monkeypatch):
    result = run(
        triage_then_deep("no_action"), monkeypatch, then_deep=False, triage=True
    )
    assert result.triage.verification is None
    assert not any(d.phase == "verify" for d in result.triage.decisions)


# --- the deep run that follows ----------------------------------------------


def test_a_deep_run_follows_with_its_own_id_and_keeps_approval_and_verification(
    monkeypatch,
):
    result = run(triage_then_deep("intervene"), monkeypatch, triage=True)
    first, deep = result.triage, result.state
    assert deep is not first and deep.mode == "deep"
    assert deep.run_id == first.run_id
    assert deep.investigation_id != first.investigation_id
    assert deep.follows_triage == first.investigation_id
    assert deep.proposed_action.status == "approved" and deep.action_carried_out
    assert deep.verification.outcome == "resolved"
    assert result.score.actions_taken == [f"replace_bearing {MACHINE}"]


def test_the_deep_run_is_not_shown_the_triage_conclusion(monkeypatch):
    policy = triage_then_deep("intervene")
    run(policy, monkeypatch, triage=True)
    first_look = policy.deep.seen_states[0]
    assert first_look.conclusion is None
    assert first_look.follows_triage is not None


def test_a_rejected_deep_proposal_is_still_a_human_decision(monkeypatch):
    from capstone.episode import reject_all

    result = run(triage_then_deep(), monkeypatch, triage=True, approver=reject_all)
    assert result.state.proposed_action.status == "rejected"
    assert result.score.actions_taken == []


def test_no_deep_run_when_the_triage_supports_that_nothing_is_needed(monkeypatch):
    calm = wear_policy("no_action")
    original = calm._conclude

    def supported(state):
        # Variables:
        #   concluded: The scripted conclusion, marked supported.
        concluded, request = original(state)
        return concluded.model_copy(update={"assessment": "supported"}), request

    calm._conclude = supported
    result = run(ByMode(calm, wear_policy()), monkeypatch, triage=True)
    assert result.triage.deep_recommended is False
    assert result.state is result.triage


def test_triage_then_deep_off_stops_after_the_triage(monkeypatch):
    result = run(triage_then_deep(), monkeypatch, then_deep=False, triage=True)
    assert result.triage.deep_recommended is True
    assert result.state is result.triage


def test_the_triage_runs_without_the_critic(monkeypatch):
    critic = FakeCritic()
    result = run(triage_then_deep(), monkeypatch, triage=True, critic=critic)
    assert result.triage.critique is None
    assert result.state.critique is not None  # the deep run keeps it
    assert len(critic.reviewed) == 1


# --- the deadline ------------------------------------------------------------


def test_a_slow_triage_stops_at_its_deadline_and_asks_for_a_deep_run(monkeypatch):
    monkeypatch.setenv("TRIAGE_SECONDS", "30")
    now = [0.0]

    def slow():
        # Every reading of the clock is 15 seconds after the last.
        now[0] += 15.0
        return now[0]

    result = run(
        triage_then_deep(), monkeypatch, then_deep=False, triage=True, clock=slow
    )
    first = result.triage
    assert first.termination_reason == "timeout"
    assert first.conclusion.recommendation == "escalate"
    assert first.deep_recommended is True
    assert first.proposed_action is None


# --- the rule, and the limits -------------------------------------------------


@pytest.mark.parametrize(
    ("recommendation", "assessment", "deep"),
    [
        ("no_action", "supported", False),
        ("no_action", "unresolved", True),
        ("no_action", None, True),
        ("intervene", "supported", True),
        ("escalate", "supported", True),
        ("escalate", "unresolved", True),
    ],
)
def test_only_a_supported_no_action_closes_the_case(recommendation, assessment, deep):
    concluded = AgentConclusion(
        diagnosis="x",
        confidence=0.9,
        recommendation=recommendation,
        assessment=assessment,
    )
    assert needs_deep_run(concluded) is deep


def test_triage_budgets_keep_nothing_for_a_fix_and_time_for_the_conclusion():
    limits = triage_budgets(90.0, 6)
    assert limits.timeout_seconds == 90.0 and limits.max_tool_calls == 6
    assert limits.followup_tool_calls == 0 and limits.critic_tool_calls == 0
    assert limits.followup_seconds == TRIAGE_CONCLUDE_SECONDS
    assert triage_budgets(8.0).followup_seconds == 2.0  # a quarter when short


# --- what the experimenter sees ------------------------------------------------


def test_an_experiment_records_and_reports_the_triage(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "on")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], triage_then_deep, name="triaged", triage=True)
    assert record.triage is not None
    assert record.triage.policy_recommendation == "intervene"
    assert record.triage.deep_recommended and record.triage.deep_ran
    assert record.triage.seconds >= 0 and record.triage.tool_calls > 0
    assert record.recommendation == "intervene"  # the deep run's answer
    line = format_triage([record])
    assert line.startswith("triage: 1 run(s), p50 ")
    assert "deep run asked for 1, ran 1" in line
    assert line in report([record], {})


def test_an_experiment_without_triage_has_no_triage_line(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.delenv("TRIAGE", raising=False)
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], wear_policy, name="plain")
    assert record.triage is None and format_triage([record]) is None


def test_nearest_rank_percentiles():
    values = [float(n) for n in range(1, 11)]
    assert nearest_rank(values, 0.5) == 5.0
    assert nearest_rank(values, 0.95) == 10.0
    assert nearest_rank([7.0], 0.95) == 7.0


def test_with_line_context_the_deep_run_gathers_its_own_packet(monkeypatch):
    """From PR 186's walkthrough: the deep state was built without the flag,
    so with TRIAGE=on and LINE_CONTEXT=on only the triage got a packet."""
    monkeypatch.setenv("LINE_CONTEXT", "on")
    result = run(triage_then_deep("intervene"), monkeypatch, triage=True)
    first, deep = result.triage, result.state
    assert first.line_context_enabled and deep.line_context_enabled
    assert first.incident_context is not None
    assert deep.incident_context is not None
    # Its own packet, gathered in the deep run, not the triage's carried over.
    assert deep.incident_context is not first.incident_context
    packet = deep.incident_context
    cited = {*packet.evidence_by_tool.values(), *packet.summary_evidence.values()}
    assert cited and cited <= {e.id for e in deep.evidence}
