"""Observe's own reads and the triage's research budget (TRIAGE_OBSERVE_CALLS).

In a triage the loop makes several reads itself before research starts: the
time, the packet's sensor window and roster, and the manual search. With
"shared" (the default) they count against TRIAGE_TOOL_CALLS, as before; with
"separate" they are moved off it once they are made, so research keeps all
its calls. The reads themselves are the same either way.
"""

import pytest

from capstone.agent.investigation import release_observe_calls
from capstone.agent.state import InvestigationState
from capstone.experiment import Case, run_experiment
from tests.test_episode import SEED, wear_policy
from tests.test_triage import ByMode, run, triage_then_deep


class FirstResearchLook:
    """A scripted policy that notes the research calls left, and the reads
    made so far, the first time it is asked anything in research."""

    def __init__(self, inner):
        self.inner = inner
        self.calls_left = None
        self.observe_reads = None

    def __getattr__(self, name):
        method = getattr(self.inner, name)
        if not callable(method):
            return method

        def call(state, *args, **kwargs):
            if self.calls_left is None and state.stage in ("plan", "investigate"):
                self.calls_left = state.remaining_tool_calls
                self.observe_reads = [
                    e.source_id
                    for e in state.evidence
                    if e.source_type == "tool_result"
                ]
            return method(state, *args, **kwargs)

        return call


def triage_look(monkeypatch, setting):
    # These tests inspect a scripted policy's first research question. Under
    # the new deterministic default no Decide model callback is expected;
    # select the model-backed comparison path explicitly.
    monkeypatch.setenv("TRIAGE_INVESTIGATE", "off")
    monkeypatch.setenv("TRIAGE_PLAN", "model")
    if setting is None:
        monkeypatch.delenv("TRIAGE_OBSERVE_CALLS", raising=False)
    else:
        monkeypatch.setenv("TRIAGE_OBSERVE_CALLS", setting)
    look = FirstResearchLook(wear_policy("intervene"))
    result = run(ByMode(look, wear_policy()), monkeypatch, triage=True)
    return look, result


# --- the counting itself ---------------------------------------------------------


def state(mode="triage", separate=True, calls=0, screening=0):
    s = InvestigationState.model_validate(
        {
            "run_id": "00000000-0000-0000-0000-000000000001",
            "investigation_id": "00000000-0000-0000-0000-000000000002",
            "anomaly": {
                "tick": 1,
                "machine_id": "CNC-02",
                "kind": "alarm",
                "description": "x",
            },
        }
    )
    s.mode = mode
    s.triage_observe_separate = separate
    s.tool_call_count = calls
    s.screening_tool_calls_used = screening
    return s


def test_separate_moves_the_reads_made_since_the_start_less_the_screening():
    s = state(calls=5, screening=1)
    release_observe_calls(s, (0, 0))
    assert s.observe_tool_calls_used == 4  # 5 reads, the screening paid already
    assert s.research_tool_calls == 0


@pytest.mark.parametrize(("mode", "separate"), [("triage", False), ("deep", True)])
def test_shared_or_a_deep_run_moves_nothing(mode, separate):
    s = state(mode=mode, separate=separate, calls=5, screening=1)
    release_observe_calls(s, (0, 0))
    assert s.observe_tool_calls_used == 0
    assert s.research_tool_calls == 4


# --- in a triage -----------------------------------------------------------------


def test_by_default_observe_still_spends_research_calls(monkeypatch):
    look, result = triage_look(monkeypatch, None)
    assert result.triage.triage_observe_separate is False
    assert result.triage.observe_tool_calls_used == 0
    assert look.calls_left < result.triage.budgets.max_tool_calls


def test_separate_leaves_research_every_call_after_the_same_reads(monkeypatch):
    shared, _ = triage_look(monkeypatch, "shared")
    separate, result = triage_look(monkeypatch, "separate")
    budget = result.triage.budgets.max_tool_calls
    assert separate.calls_left == budget  # research starts with all six
    assert shared.calls_left < budget
    # Observe made exactly the same reads; only who pays for them changed.
    assert separate.observe_reads == shared.observe_reads
    assert result.triage.observe_tool_calls_used == budget - shared.calls_left


def test_the_deep_run_after_a_separate_triage_pays_as_before(monkeypatch):
    _, result = triage_look(monkeypatch, "separate")
    assert result.state is not result.triage
    assert result.state.triage_observe_separate is False
    assert result.state.observe_tool_calls_used == 0


def test_the_triage_record_counts_the_reads_kept_off_research(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    monkeypatch.setenv("TRIAGE_OBSERVE_CALLS", "separate")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], triage_then_deep, name="obs", triage=True)
    assert record.triage.observe_tool_calls > 0
    assert record.triage.research_tool_calls <= 6


def test_an_unknown_observe_setting_is_refused(monkeypatch):
    from capstone.settings import Settings

    monkeypatch.setenv("TRIAGE_OBSERVE_CALLS", "free")
    with pytest.raises(ValueError):
        Settings()
