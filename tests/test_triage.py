"""Rapid triage: a short, read-only first look before the deep investigation.

What these tests prove, with scripted policies and a fake clock (no model):
triage is off by default; a triage never proposes, executes or verifies,
whatever the model recommends; code, not the model, decides whether a deep
run follows; the deep run has its own investigation id and a reference to
the triage, and keeps human approval and verification; the triage's
deadline holds even when every answer is slow; and experiment records
report the triage's timing and outcome.
"""

import json

import pytest

from capstone.agent.artifacts import AgentConclusion
from capstone.agent.investigation import check_conclusion, needs_deep_run
from capstone.agent.loop import InvestigationDeps
from capstone.agent.state import TRIAGE_CONCLUDE_SECONDS, triage_budgets
from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.provenance import ProvenanceReference
from capstone.episode import run_episode
from capstone.experiment import (
    Case,
    format_triage,
    nearest_rank,
    report,
    run_experiment,
)
from capstone.providers.chat import ModelError
from tests.helpers import START, FakeCritic, FakeProvider, ScriptedPolicy, new_state
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
    # The triage's evidence packet wins over line context (2026-11-13), so the
    # triage builds its own packet and no line-context one.
    assert first.triage_packet is not None and first.incident_context is None
    assert deep.incident_context is not None
    # Its own packet, gathered in the deep run, not the triage's carried over.
    assert deep.incident_context is not first.incident_context
    packet = deep.incident_context
    cited = {*packet.evidence_by_tool.values(), *packet.summary_evidence.values()}
    assert cited and cited <= {e.id for e in deep.evidence}


# --- a triage no model answered ---------------------------------------------------


class NoConclusion:
    """A scripted policy whose conclusion no model answers, after `attempts` requests."""

    def __init__(self, inner, attempts):
        self.inner, self.attempts = inner, attempts

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def conclude(self, state, *args, **kwargs):
        raise ModelError(
            "no model service answered (m: out of time)",
            out_of_time=True,
            attempts=self.attempts,
        )


def test_a_triage_conclusion_no_model_answered_is_model_unavailable(monkeypatch):
    policy = ByMode(NoConclusion(wear_policy("intervene"), 2), wear_policy())
    result = run(policy, monkeypatch, then_deep=False, triage=True)
    assert result.triage.termination_reason == "model_unavailable"
    assert result.triage.conclusion.recommendation == "escalate"
    assert result.triage.deep_recommended is True


def test_a_triage_with_no_time_to_ask_any_model_is_still_a_timeout(monkeypatch):
    policy = ByMode(NoConclusion(wear_policy("intervene"), 0), wear_policy())
    result = run(policy, monkeypatch, then_deep=False, triage=True)
    assert result.triage.termination_reason == "timeout"


def test_a_deep_conclusion_no_model_answered_is_still_a_timeout(monkeypatch):
    monkeypatch.delenv("TRIAGE", raising=False)
    result = run(NoConclusion(wear_policy(), 2), monkeypatch)
    assert result.state.mode == "deep"
    assert result.state.termination_reason == "timeout"  # deep runs unchanged


def test_the_triage_line_counts_triages_no_model_answered(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment(
        [case],
        lambda: ByMode(NoConclusion(wear_policy("intervene"), 1), wear_policy()),
        name="unserved",
        triage=True,
    )
    assert record.triage.termination_reason == "model_unavailable"
    assert record.score.model_unavailable  # left out of every total
    assert "(0 timed out, 1 no model answered)" in format_triage([record])


# --- the check before a triage run ------------------------------------------------


def test_a_triage_run_does_not_start_when_no_model_answers_the_check(
    monkeypatch, tmp_path
):
    import capstone.experiment as experiment

    asked = []
    monkeypatch.setattr(experiment, "preflight_models", lambda: asked.append(1))
    monkeypatch.setattr(
        experiment,
        "run_experiment",
        lambda *a, **k: pytest.fail("the run must not start"),
    )
    monkeypatch.setattr(experiment, "model_policy_factory", lambda *a, **k: None)
    out = tmp_path / "records.jsonl"
    code = experiment.main(
        ["run", "--name", "x", "--known", "--out", str(out), "--triage"]
        + ["--quiet", "--no-manual", "--no-audit"]
    )
    assert code == 1 and asked == [1] and not out.exists()


def test_a_deep_only_run_skips_the_check(monkeypatch, tmp_path):
    import capstone.experiment as experiment

    monkeypatch.delenv("TRIAGE", raising=False)
    monkeypatch.setattr(
        experiment,
        "preflight_models",
        lambda: pytest.fail("a deep-only run asks no model before it starts"),
    )
    monkeypatch.setattr(experiment, "run_experiment", lambda *a, **k: [])
    monkeypatch.setattr(experiment, "model_policy_factory", lambda *a, **k: None)
    out = tmp_path / "records.jsonl"
    assert (
        experiment.main(
            ["run", "--name", "x", "--known", "--out", str(out), "--quiet"]
            + ["--no-manual", "--no-audit"]
        )
        == 0
    )


# --- a triage may not clear an alarm it never checked (TRI-02/TRI-33) -------
#
# A0 run 2, KA-09 (2026-11-12): the alarm was on CNC-03 at tick 80, the true
# faults were on CNC-07, the screening had scored almost no machine yet, and
# the triage formed no explanation; it still answered "supported, no action"
# and the case closed without a deep run. These tests hold that answer open.


def clearance_state(*, hypotheses=True, screening="full"):
    """A triage about CNC-02 with one observation and, optionally, a screening.

    `screening` is "full" (every machine scored), "alarmed_unscored" (the
    alarmed machine's sensors have no score yet), "machine_unscored" (another
    machine has no score at all) or None (no screening was gathered).
    """
    # Variables:
    #   machines: The screening's per-machine rows, as get_line_screening
    #     returns them: [robust, plain] scores or a reason there is none.
    state = new_state()
    state.mode = "triage"
    add_evidence(state, "E1", "simulator:get_time", {"tick": 10})
    if screening is not None:
        machines = {
            "CNC-01": {"vibration": [0.1, 0.2]},
            "CNC-02": {"vibration": [0.3, 0.2], "temperature": [0.1, 0.0, "steady"]},
        }
        if screening == "alarmed_unscored":
            machines["CNC-02"] = {"vibration": "not_running_yet"}
        if screening == "machine_unscored":
            machines["CNC-01"] = "not_running_yet"
        add_evidence(
            state,
            "E2",
            "simulator:get_line_screening",
            {"machines": machines, "reference": "healthy line"},
        )
    if hypotheses:
        state.hypotheses = [
            Hypothesis(id="H1", claim="a transient spike", confidence=0.9)
        ]
    return state


def add_evidence(state, evidence_id, source_id, content):
    state.evidence.append(
        Evidence(
            id=evidence_id,
            source_id=source_id,
            source_type="tool_result",
            content=json.dumps(content),
            observed_tick=10,
            observed_at=START,
        )
    )
    state.provenance.append(
        ProvenanceReference(
            evidence_id=evidence_id,
            source_id=source_id,
            source_type="tool_result",
            origin="observable",
            observed_tick=10,
        )
    )


def clear(state, *, screening_available=True, **changes):
    """Run the final check on a supported "nothing needs doing" answer."""
    values = {
        "diagnosis": "a transient spike that has passed",
        "confidence": 0.85,
        "recommendation": "no_action",
        "assessment": "supported",
        "hypothesis_id": "H1" if state.hypotheses else None,
        "evidence_ids": ("E1",),
    }
    values.update(changes)
    deps = InvestigationDeps(
        provider=FakeProvider(),
        policy=ScriptedPolicy(),
        screening_available=screening_available,
    )
    checked, _ = check_conclusion(state, deps, AgentConclusion(**values), None)
    return checked


def gap_kinds(state):
    return [g.kind for g in state.conclusion_trace.gaps]


def test_a_triage_with_no_explanation_cannot_clear_the_alarm():
    state = clearance_state(hypotheses=False)
    checked = clear(state)
    assert checked.assessment == "unresolved"
    assert checked.recommendation == "escalate"
    assert needs_deep_run(checked) is True
    assert gap_kinds(state) == ["triage_no_hypothesis"]


def test_a_triage_cannot_clear_an_alarmed_machine_the_screening_did_not_score():
    state = clearance_state(screening="alarmed_unscored")
    checked = clear(state)
    assert checked.recommendation == "escalate" and needs_deep_run(checked)
    assert gap_kinds(state) == ["triage_screening_gap"]
    assert "CNC-02" in checked.unresolved_questions[0]


def test_a_triage_cannot_clear_while_another_machine_is_unscored():
    state = clearance_state(screening="machine_unscored")
    checked = clear(state)
    assert gap_kinds(state) == ["triage_screening_gap"]
    assert "CNC-01" in checked.unresolved_questions[0]


def test_a_triage_whose_screening_never_arrived_cannot_clear():
    state = clearance_state(screening=None)
    checked = clear(state)
    assert gap_kinds(state) == ["triage_screening_gap"]
    assert needs_deep_run(checked)


def test_both_reasons_are_kept_when_both_hold():
    state = clearance_state(hypotheses=False, screening=None)
    clear(state)
    assert gap_kinds(state) == ["triage_no_hypothesis", "triage_screening_gap"]


def test_a_triage_with_an_explanation_and_a_full_screening_may_still_clear():
    state = clearance_state()
    checked = clear(state)
    assert checked.assessment == "supported"
    assert checked.recommendation == "no_action"
    assert needs_deep_run(checked) is False


def test_a_recorded_machine_without_screening_needs_only_an_explanation():
    state = clearance_state(screening=None)
    checked = clear(state, screening_available=False)
    assert checked.recommendation == "no_action" and not needs_deep_run(checked)


@pytest.mark.parametrize("recommendation", ["escalate", "intervene"])
def test_answers_that_clear_nothing_get_no_clearance_gaps(recommendation):
    state = clearance_state(hypotheses=False, screening=None)
    clear(state, recommendation=recommendation)
    assert gap_kinds(state) == []


def test_a_deep_run_is_not_held_to_the_triage_clearance_rule():
    state = clearance_state(hypotheses=False, screening=None)
    state.mode = "deep"
    checked = clear(state)
    assert checked.assessment == "supported" and checked.recommendation == "no_action"
    assert gap_kinds(state) == []
