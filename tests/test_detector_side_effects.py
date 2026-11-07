"""Testing the detector: the line screening does its job and changes nothing else.

The normal tests (`test_line_screening.py`) check the screening itself. These
check what is around it. Most compare a run with the screening against the
same run with only the screening's own call skipped (`without_screening`), so
any difference is the screening's doing. Everything runs offline on the 13
known cases, with scripted policies and a fixed clock: no model is called.
"""

import json

import pytest

from capstone.agent import investigation
from capstone.agent.artifacts import AgentConclusion
from capstone.agent.model_policy import evidence_section
from capstone.agent.monitor import detect_anomaly
from capstone.episode import build_world, run_episode
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.helpers import ScriptedPolicy, ask

SCREENING = "get_line_screening"
REAL_GATHER = investigation.gather
# The cases monitoring raises on a named machine: the ones a blackout can hit.
ALARMED = [
    c
    for c in KNOWN_CASES
    if c.scenario_id
    not in {"KA-03-batch", "KA-04-batch", "KA-05-setting", "KA-06-setting"}
]
HIDDEN_WORDS = ("bearing", "health", "degradation", "fault", "scenario", "truth")
# What the screening shows at each case's alarm, under the rule used to check
# it offline (both scores at least 3): the machines it singles out, and the
# ones it cannot score yet. Wear and leak faults are found on their own
# machine; batch, setting and false-alarm cases single out nothing.
AT_THE_ALARM = {
    "KA-01-bearing": ({"CNC-02"}, set()),
    "KA-02-bearing": ({"CNC-05"}, set()),
    "KA-03-batch": (set(), set()),
    "KA-04-batch": (set(), set()),
    "KA-05-setting": (set(), set()),
    "KA-06-setting": (set(), set()),
    "KA-07-false-alarm": (set(), set()),
    "KA-08-false-alarm": (set(), {"CNC-07", "CNC-08"}),
    # Tick 71: most of the line has not cut long enough to be scored.
    "KA-09-challenge": (set(), {"CNC-03", "CNC-04", "CNC-05", "CNC-06", "CNC-07"}),
    "KA-10-servo": ({"CNC-04"}, set()),
    "KA-11-servo": ({"CNC-02"}, set()),
    "KA-12-hydraulic": ({"CNC-05"}, set()),
    "KA-13-hydraulic": ({"CNC-02"}, set()),
}


def skip_screening(state, deps, phase, step, **options):
    """`gather`, except the loop's own screening call is never made."""
    # Variables:
    #   step: The call the investigation module is about to make; only a
    #     screening is dropped, without counting a call, so the run looks as
    #     if the screening had never been added. Used only with policies that
    #     never ask for the screening themselves.
    if step.request.name == SCREENING:
        return None
    return REAL_GATHER(state, deps, phase, step, **options)


def episode(case, make_policy, *, screening=True, **options):
    """One known case, run offline on a fixed clock; `screening=False` skips
    only the screening's call, so the two runs differ by it alone."""
    # Variables:
    #   make_policy: Builds a fresh policy, so the two runs never share one.
    #   screening: False swaps in `skip_screening` for this run only.
    #   options: Passed to run_episode as they are (hazards, triage).
    with pytest.MonkeyPatch.context() as patch:
        if not screening:
            patch.setattr(investigation, "gather", skip_screening)
        return run_episode(
            case.seed,
            make_policy(),
            kind=case.kind,
            fault=case.fault,
            clock=lambda: 0.0,
            **options,
        )


def look_once(state):
    """One look at what monitoring named, from working memory only."""
    a = state.anomaly
    window = {"from_tick": max(0, a.tick - 300), "to_tick": a.tick}
    if a.machine_id is not None:
        return ask(
            "get_sensor_trend", machine_id=a.machine_id, sensor="vibration", **window
        )
    return ask("get_inspections", **window)


def undetermined(state):
    return (
        AgentConclusion(
            diagnosis="undetermined", confidence=0.2, recommendation="escalate"
        ),
        None,
    )


def stand_in():
    """Looks once and admits it cannot tell; cites no evidence id, so the
    screening shifting the numbering cannot change what it does."""
    return ScriptedPolicy({"investigate": [look_once]}, conclude=undetermined)


def busy():
    """Many looks with large answers, so the prompt's evidence section fills up."""
    # Variables:
    #   looks: The nine calls, built from the anomaly once it is known: raw
    #     readings on four sensors (each cut in the prompt) plus five lists.
    #   queued: Whether the calls have been put in the queue, so it is filled
    #     once and the run then stops when the queue is empty.
    #   scripted: The ScriptedPolicy's own decide, which plays the queue back.

    def looks(state):
        a = state.anomaly
        machine = a.machine_id or "CNC-01"
        window = {"from_tick": max(0, a.tick - 299), "to_tick": a.tick}
        return [
            ask("get_readings", machine_id=machine, sensor=sensor, **window)
            for sensor in ("vibration", "temperature", "load", "power")
        ] + [
            ask("get_events", **window),
            ask("get_inspections", **window),
            ask("get_maintenance_history"),
            ask("list_machines"),
            ask("get_settings"),
        ]

    policy = ScriptedPolicy({"investigate": []}, conclude=undetermined)
    scripted = policy.decide
    queued = False

    def decide(state, phase):
        nonlocal queued
        if phase == "investigate" and not queued:
            policy.decisions["investigate"] = looks(state)
            queued = True
        return scripted(state, phase)

    policy.decide = decide
    return policy


def screening_rows(state):
    """The screening's answer in this investigation's evidence."""
    (evidence,) = [e for e in state.evidence if e.source_id.endswith(SCREENING)]
    return json.loads(evidence.content)


def shown_whole(state) -> dict[str, bool]:
    """For each piece of evidence, by what produced it, whether the prompt
    shows it whole (True) or only as a one-line stand-in (False)."""
    # Variables:
    #   lines: The evidence section exactly as the model policy writes it.
    #   key: The tool, tick and answer behind a piece of evidence, so runs
    #     with and without the screening compare the same evidence even though
    #     its id (E2, E3...) differs between them.
    lines = evidence_section(state)
    whole = {}
    for evidence in state.evidence:
        (line,) = [x for x in lines if x.startswith(f"- {evidence.id} ")]
        key = (evidence.source_id, evidence.observed_tick, evidence.content)
        whole[key] = "characters, not shown here" not in line
    return whole


@pytest.fixture(scope="module")
def paired():
    """Every known case run by the stand-in, with and without the screening."""
    return {
        case.scenario_id: (
            episode(case, stand_in),
            episode(case, stand_in, screening=False),
        )
        for case in KNOWN_CASES
    }


# --- 1. The factory and monitoring are untouched ---------------------------


@pytest.mark.parametrize("case", KNOWN_CASES, ids=lambda c: c.scenario_id)
def test_asking_for_the_screening_changes_nothing_in_the_factory(case):
    """Called again and again mid-run, the screening leaves every later
    reading, event and alarm exactly as a run that never called it."""

    def run(calls: bool):
        sim = build_world(case.seed, kind=case.kind, fault=case.fault)
        look = ObservationTools(sim)
        for tick in range(600):
            if calls and tick % 50 == 0:
                look.get_line_screening()
            sim.step()
        anomaly = detect_anomaly(look, ActionTools(sim, ApprovalDesk(sim)))
        return sim.readings, look.get_events(0, sim.clock.tick), anomaly

    assert run(calls=True) == run(calls=False)


def test_monitoring_sees_the_same_alarm_with_or_without_the_screening(paired):
    for scenario_id, (screened, plain) in paired.items():
        assert screened.state.anomaly == plain.state.anomaly, scenario_id


def test_a_whole_episode_repeats_screening_included():
    case = KNOWN_CASES[0]
    first, second = episode(case, stand_in), episode(case, stand_in)
    assert first.state.evidence == second.state.evidence
    assert first.score == second.score


# --- 2. Budgets and stop reasons -------------------------------------------


def test_research_keeps_its_whole_budget_in_every_known_case(paired):
    for scenario_id, (screened, plain) in paired.items():
        a, b = screened.state, plain.state
        assert a.screening_tool_calls_used == 1 and b.screening_tool_calls_used == 0
        assert a.tool_call_count == b.tool_call_count + 1, scenario_id
        same = (
            "research_tool_calls",
            "remaining_tool_calls",
            "followup_tool_calls_used",
            "critic_tool_calls_used",
            "remaining_iterations",
            "termination_reason",
            "repeated_calls",
            "failed_tool_calls",
            "unproductive_steps",
        )
        assert {k: getattr(a, k) for k in same} == {k: getattr(b, k) for k in same}, (
            scenario_id
        )


def test_triage_counts_the_screening_on_its_own_allowance_too():
    case = KNOWN_CASES[0]
    screened = episode(case, stand_in, triage=True)
    plain = episode(case, stand_in, screening=False, triage=True)
    assert screened.triage is not None and plain.triage is not None
    assert screened.triage.screening_tool_calls_used == 1
    assert screened.triage.research_tool_calls == plain.triage.research_tool_calls
    assert screened.triage.deep_recommended == plain.triage.deep_recommended


def test_asking_again_is_a_repeat_now_and_research_later():
    """The agent may call the screening itself, like any tool: the same
    question at the same tick is refused as a repeat; later it is a research call."""
    policy = ScriptedPolicy(
        {"investigate": [ask(SCREENING), ask("wait", ticks=5), ask(SCREENING)]},
        conclude=undetermined,
    )
    state = run_episode(6, policy, fault="bearing_degradation", clock=lambda: 0.0).state
    screenings = [e for e in state.evidence if e.source_id.endswith(SCREENING)]
    assert len(screenings) == 2  # the loop's, then the later one; not the repeat
    assert state.repeated_calls == 1
    assert state.screening_tool_calls_used == 1  # only the loop's own call is free
    # The loop's get_time (research before #201 too), the wait, the later screening.
    assert state.research_tool_calls == 3


def test_a_failed_screening_does_not_stop_the_investigation(monkeypatch):
    """If the screening breaks (say its "before" file is missing), the run
    carries on and research keeps its budget. Pinned as it is today: the
    failure counts as a failed tool call, though the agent never asked for it."""
    from capstone.tools import observation

    def broken(self):
        raise FileNotFoundError("healthy_reference.json")

    case = KNOWN_CASES[0]
    plain = episode(case, stand_in, screening=False)
    monkeypatch.setattr(observation.ObservationTools, "get_line_screening", broken)
    failed = episode(case, stand_in)
    assert not [e for e in failed.state.evidence if e.source_id.endswith(SCREENING)]
    assert failed.state.failed_tool_calls == plain.state.failed_tool_calls + 1
    assert failed.state.research_tool_calls == plain.state.research_tool_calls
    assert failed.state.termination_reason == plain.state.termination_reason
    assert failed.score.model_dump(exclude={"tool_calls"}) == plain.score.model_dump(
        exclude={"tool_calls"}
    )


# --- 3. Hazards ------------------------------------------------------------


@pytest.mark.parametrize("case", ALARMED, ids=lambda c: c.scenario_id)
def test_the_standard_hazards_land_on_the_same_calls(case):
    screened = episode(case, stand_in, hazards=True)
    plain = episode(case, stand_in, screening=False, hazards=True)
    assert screened.hazards == plain.hazards
    assert not [f for f in screened.hazards.fired if SCREENING in f]


@pytest.mark.parametrize("case", ALARMED, ids=lambda c: c.scenario_id)
def test_a_blackout_hides_the_machine_in_the_screening_and_counts_the_same(case):
    screened = episode(case, stand_in, hazards="blackout")
    plain = episode(case, stand_in, screening=False, hazards="blackout")
    assert screened.hazards == plain.hazards  # blocked calls, recovery: unchanged
    machine = screened.state.anomaly.machine_id
    assert screening_rows(screened.state)["machines"][machine] == "feed_unavailable"


# --- 4. What the model sees ------------------------------------------------


def test_the_screening_is_shown_whole_in_every_prompt_of_a_short_run(paired):
    for scenario_id, (screened, _) in paired.items():
        state = screened.state
        assert all(shown_whole(state).values()), scenario_id


def test_the_screening_pushes_no_other_evidence_out_of_the_prompt():
    """In a run with many large answers, the evidence shown whole is the same
    with and without the screening, apart from the screening itself."""
    case = KNOWN_CASES[0]
    screened, plain = episode(case, busy), episode(case, busy, screening=False)
    with_screening = {
        key: whole
        for key, whole in shown_whole(screened.state).items()
        if not key[0].endswith(SCREENING)
    }
    assert with_screening == shown_whole(plain.state)


def test_in_a_long_run_the_screening_is_what_gets_shortened():
    """Pinned as it is today, for the developer to decide on: once the
    evidence section is full, the screening (early, and cited by nothing) is
    the piece cut to a one-line stand-in, so late prompts no longer show it."""
    state = episode(KNOWN_CASES[0], busy).state
    whole = shown_whole(state)
    assert not all(whole.values())  # the section really is full
    (screening,) = [v for k, v in whole.items() if k[0].endswith(SCREENING)]
    assert screening is False


# --- 5. Scoring is unaffected ----------------------------------------------


def test_the_score_is_the_same_apart_from_one_more_tool_call(paired):
    for scenario_id, (screened, plain) in paired.items():
        assert screened.score.tool_calls == plain.score.tool_calls + 1, scenario_id
        assert screened.score.model_dump(
            exclude={"tool_calls"}
        ) == plain.score.model_dump(exclude={"tool_calls"}), scenario_id


# --- 6. The detector's own results -----------------------------------------


@pytest.mark.parametrize("case", KNOWN_CASES, ids=lambda c: c.scenario_id)
def test_at_the_alarm_the_screening_singles_out_only_the_faulty_machine(case):
    sim = build_world(case.seed, kind=case.kind, fault=case.fault)
    look = ObservationTools(sim)
    detect_anomaly(look, ActionTools(sim, ApprovalDesk(sim)))
    machines = look.get_line_screening()["machines"]
    far = {
        machine
        for machine, sensors in machines.items()
        if isinstance(sensors, dict)
        for scores in sensors.values()
        if isinstance(scores, list) and abs(scores[0]) >= 3 and abs(scores[1]) >= 3
    }
    unscored = {
        machine for machine, entry in machines.items() if isinstance(entry, str)
    }
    assert (far, unscored) == AT_THE_ALARM[case.scenario_id]
    # Nothing it singles out is a healthy machine.
    assert far <= {t.machine_id for t in sim.ground_truth()}


@pytest.mark.parametrize("case", KNOWN_CASES, ids=lambda c: c.scenario_id)
def test_no_hidden_truth_in_any_known_case(case):
    sim = build_world(case.seed, kind=case.kind, fault=case.fault)
    look = ObservationTools(sim)
    detect_anomaly(look, ActionTools(sim, ApprovalDesk(sim)))
    answer = look.get_line_screening()
    text = json.dumps(answer).lower()
    assert not [word for word in HIDDEN_WORDS if word in text]
    listed = [m["machine_id"] for m in look.list_machines()]
    assert list(answer["machines"]) == listed
