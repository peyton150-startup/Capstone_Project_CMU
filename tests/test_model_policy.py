"""The model-backed policy, with fake model clients and no network.

A fake client answers with JSON text, which is turned into the answer type
the same way the real client does it, so a reply that breaks the schema
fails here exactly as it would against a real model.
"""

import json
import re

import pytest

from capstone.agent.artifacts import AgentConclusion, ProposalRecord
from capstone.agent.model_policy import (
    MAX_EVIDENCE_CHARS,
    MAX_EVIDENCE_SECTION_CHARS,
    SYSTEM,
    ConcludeAnswer,
    Judgement,
    LessonAnswer,
    ModelPolicy,
    NextStep,
    PlanAnswer,
    render,
)
from capstone.agent.policy import CallTool, Interpretation, Stop
from capstone.agent.state import DecisionRecord, Question
from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.provenance import ProvenanceReference
from capstone.contracts.tools import ToolError, ToolRequest
from capstone.episode import run_episode
from capstone.providers.chat import JOBS, ChatClient, FallbackClient, ModelError
from capstone.providers.factory import research_tools
from capstone.providers.recall import RECALL_SPEC
from capstone.tools.diagnosis import FAULT_KINDS
from tests.helpers import new_state

ANSWER_TYPES = (PlanAnswer, NextStep, Interpretation, ConcludeAnswer, Judgement)


class FakeModel:
    """Answers each question from a queue of replies (JSON-able or callables
    of the prompt), and remembers what it was asked."""

    answered_by = "fake/model"
    attempts = ()

    def __init__(self, *replies):
        self.replies = list(replies)
        self.asked = []
        self.limits = []  # the max_seconds each question was given

    def ask(self, system, prompt, answer_type, *, max_seconds=None):
        self.asked.append((system, prompt, answer_type))
        self.limits.append(max_seconds)
        reply = self.replies.pop(0)
        if callable(reply):
            reply = reply(prompt)
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return answer_type.model_validate_json(text)


def policy(tools=None, **replies):
    clients = {job: FakeModel(*replies.get(job, ())) for job in JOBS}
    return ModelPolicy(clients, research_tools() if tools is None else tools)


def call(tool, question_id=None, **arguments):
    step = {
        "choice": "call_tool",
        "information_needed": f"what {tool} shows",
        "tool": tool,
        "arguments": arguments,
    }
    if question_id is not None:
        step["question_id"] = question_id
    return step


def stop(reason="evidence_sufficient"):
    return {"choice": "stop", "stop_reason": reason, "information_needed": "nothing"}


def state_with_evidence():
    state = new_state()
    state.last_tick = 914
    state.evidence = [
        Evidence(
            id="E1",
            source_id="simulator:get_sensor_summary",
            source_type="tool_result",
            content='{"mean": 3.1}',
            observed_tick=914,
        ),
        Evidence(
            id="E2",
            source_id="memory:recall_memories",
            source_type="tool_result",
            content='[{"lesson": "look at the trend"}]',
            observed_tick=914,
        ),
    ]
    state.provenance = [
        ProvenanceReference(
            evidence_id="E1",
            source_id="simulator:get_sensor_summary",
            source_type="tool_result",
            origin="observable",
            observed_tick=914,
        ),
        ProvenanceReference(
            evidence_id="E2",
            source_id="memory:recall_memories",
            source_type="tool_result",
            origin="memory",
            observed_tick=914,
        ),
    ]
    state.decisions = [
        DecisionRecord(
            sequence=1,
            phase="investigate",
            information_needed="vibration",
            tool="get_sensor_summary",
            arguments={"machine_id": "CNC-02", "from_tick": 614, "to_tick": 914},
            outcome="observed",
            evidence_ids=("E1",),
            confidence=0.0,
        ),
        DecisionRecord(
            sequence=2,
            phase="investigate",
            information_needed="raw vibration",
            tool="get_readings",
            arguments={"machine_id": "CNC-02", "from_tick": 0, "to_tick": 914},
            outcome="tool_error",
            confidence=0.0,
            error=ToolError(
                code="invalid_arguments", message="914 rows is more than 300"
            ),
        ),
    ]
    state.hypotheses = [
        Hypothesis(
            id="H1",
            claim="CNC-02 is wearing",
            confidence=0.6,
            supporting_evidence_ids=("E1",),
        )
    ]
    state.unanswered_questions = [
        Question(id="Q2", text="Is the rise gradual?", hypothesis_id="H1")
    ]
    return state


# --- what a model is shown ------------------------------------------------------


def test_the_view_shows_anomaly_questions_evidence_and_beliefs_with_their_ids():
    text = render(state_with_evidence())
    assert "ANOMALY (alarm on CNC-02, tick 10): High vibration" in text
    assert "NOW: tick 914" in text
    assert "- Q2: Is the rise gradual? [tests H1]" in text
    assert (
        '- E1 get_sensor_summary {"from_tick":614,"machine_id":"CNC-02",'
        '"to_tick":914} at tick 914: {"mean": 3.1}' in text
    )
    assert "- H1 (confidence 0.60): CNC-02 is wearing Supported by: E1." in text


def test_a_memory_is_shown_as_a_past_belief_not_a_look_now():
    text = render(state_with_evidence())
    [line] = [line for line in text.splitlines() if line.startswith("- E2")]
    assert "FROM MEMORY" in line and "not a look at the factory now" in line


def test_a_failed_call_is_shown_with_what_to_correct():
    text = render(state_with_evidence())
    assert "RECENT FAILED CALLS" in text
    assert "invalid_arguments: 914 rows is more than 300" in text


def test_the_view_holds_no_bookkeeping():
    text = render(state_with_evidence())
    for word in ("sequence", "iteration_count", "seen_calls", "unproductive"):
        assert word not in text


def test_long_evidence_is_cut_with_a_note_saying_how_to_ask_for_less():
    state = state_with_evidence()
    state.evidence[0] = state.evidence[0].model_copy(
        update={"content": "x" * (MAX_EVIDENCE_CHARS + 500)}
    )
    text = render(state)
    assert "x" * (MAX_EVIDENCE_CHARS + 1) not in text
    assert "500 more characters not shown" in text


def many_large_pieces(count=20, cited=("E3", "E7")):
    """A state with `count` pieces of evidence of 2,000 characters each."""
    state = state_with_evidence()
    state.evidence = [
        Evidence(
            id=f"E{n}",
            source_id="simulator:get_readings",
            source_type="tool_result",
            content=str(n % 10) * MAX_EVIDENCE_CHARS,
            observed_tick=900 + n,
        )
        for n in range(1, count + 1)
    ]
    state.provenance = []
    state.hypotheses = [
        Hypothesis(
            id="H1",
            claim="CNC-02 is wearing",
            confidence=0.6,
            supporting_evidence_ids=cited,
        )
    ]
    return state


def evidence_part(text):
    """The evidence section of a prompt, header to the line before HYPOTHESES."""
    return text[text.index("EVIDENCE (") : text.index("\n\nHYPOTHESES:")]


def evidence_line(text, evidence_id):
    [line] = [x for x in text.splitlines() if x.startswith(f"- {evidence_id} ")]
    return line


def test_many_large_pieces_of_evidence_stay_within_the_section_limit():
    text = render(many_large_pieces())
    assert len(evidence_part(text)) <= MAX_EVIDENCE_SECTION_CHARS
    assert 20 * MAX_EVIDENCE_CHARS > 3 * MAX_EVIDENCE_SECTION_CHARS  # it had to cut


def test_the_newest_and_the_cited_evidence_are_shown_whole():
    text = render(many_large_pieces())
    for evidence_id, digit in (("E20", "0"), ("E3", "3"), ("E7", "7")):
        assert evidence_line(text, evidence_id).endswith(digit * MAX_EVIDENCE_CHARS)
    # The oldest uncited piece is listed by its call alone.
    assert evidence_line(text, "E1").endswith("[2000 characters, not shown here]")


def test_every_id_is_listed_once_in_order_and_none_is_invented():
    text = render(many_large_pieces())
    listed = re.findall(r"^- (E\d+) ", evidence_part(text), flags=re.MULTILINE)
    assert listed == [f"E{n}" for n in range(1, 21)]
    assert set(re.findall(r"\bE\d+\b", text)) <= set(listed)


def test_the_note_names_what_was_shortened_and_how_to_see_more():
    text = render(many_large_pieces())
    [note] = [x for x in text.splitlines() if x.startswith("(Listed by ID")]
    assert "E1, E2," in note and "E20" not in note and "E3," not in note
    assert "refused as a repeat" in note and "narrower question" in note


def test_beliefs_questions_and_failed_calls_are_never_shortened():
    text = render(many_large_pieces())
    assert "- H1 (confidence 0.60): CNC-02 is wearing Supported by: E3, E7." in text
    assert "- Q2: Is the rise gradual? [tests H1]" in text
    assert "invalid_arguments: 914 rows is more than 300" in text


def test_the_limit_holds_even_when_everything_is_cited():
    state = many_large_pieces(cited=tuple(f"E{n}" for n in range(1, 21)))
    text = render(state)
    assert len(evidence_part(text)) <= MAX_EVIDENCE_SECTION_CHARS
    assert evidence_line(text, "E20").endswith("0" * MAX_EVIDENCE_CHARS)
    # Cited pieces that did not fit go newest first: E19 is whole, E1 is not.
    assert evidence_line(text, "E19").endswith("9" * MAX_EVIDENCE_CHARS)
    assert "not shown here" in evidence_line(text, "E1")


def test_a_small_prompt_is_shown_whole_with_no_note():
    text = render(state_with_evidence())
    assert "Listed by ID" not in text


def test_no_prompt_or_answer_schema_lists_the_possible_causes():
    """The model must find the cause in the evidence, not pick it from a list."""
    texts = [*SYSTEM.values()]
    texts += [json.dumps(t.model_json_schema()) for t in ANSWER_TYPES]
    texts += [
        json.dumps(spec.model_dump()) for spec in (*research_tools(), RECALL_SPEC)
    ]
    texts.append(render(state_with_evidence()))
    joined = " ".join(texts).lower()
    assert not [kind for kind in FAULT_KINDS if kind in joined]
    assert not [kind for kind in FAULT_KINDS if kind.replace("_", " ") in joined]


def test_the_client_puts_the_answer_schema_in_the_system_prompt():
    sent = []

    def transport(url, headers, body, timeout):
        sent.append(json.loads(body))
        reply = {"choices": [{"message": {"content": '{"questions": []}'}}]}
        return json.dumps(reply).encode()

    client = ChatClient("https://example.test", "k", "m", transport=transport)
    ModelPolicy({job: client for job in JOBS}, research_tools()).plan(new_state())
    system = sent[0]["messages"][0]["content"]
    assert system.startswith(SYSTEM["plan"])
    assert '"questions"' in system


# --- each question, and its answer -----------------------------------------------


def test_a_plan_is_a_list_of_questions():
    agent = policy(plan=[{"questions": [{"id": "Q1", "text": "When did it start?"}]}])
    assert agent.plan(new_state()) == (Question(id="Q1", text="When did it start?"),)


def test_a_decision_is_a_tool_call_or_a_stop():
    agent = policy(
        decide=[
            call("get_sensor_trend", machine_id="CNC-02", sensor="vibration"),
            stop(),
        ]
    )
    first = agent.decide(new_state(), "investigate")
    assert isinstance(first, CallTool) and first.request.name == "get_sensor_trend"
    assert isinstance(agent.decide(new_state(), "investigate"), Stop)


def test_the_decision_prompt_names_the_stage_and_the_tools_with_their_schemas():
    agent = policy(decide=[stop("no_useful_action")])
    agent.decide(new_state(), "test")
    _, prompt, _ = agent.clients["decide"].asked[0]
    assert "STAGE: test." in prompt
    assert "- get_sensor_trend: " in prompt and '"bucket_ticks"' in prompt
    for procedure in ("propose_action", "execute_action", "get_proposals"):
        assert f"- {procedure}:" not in prompt
    assert "recall_memories" not in prompt


def test_recall_is_offered_only_when_given():
    agent = policy(
        tools=(*research_tools(), RECALL_SPEC),
        decide=[call("recall_memories", text="vibration alarm")],
    )
    decision = agent.decide(new_state(), "investigate")
    assert decision.request.name == "recall_memories"
    assert "- recall_memories: " in agent.clients["decide"].asked[0][1]


@pytest.mark.parametrize("tool", ["propose_action", "execute_action", "approve"])
def test_a_call_to_a_tool_not_offered_is_refused_and_counted_against_the_model(
    tool,
):
    agent = policy(decide=[call(tool, proposal_id=1)])
    with pytest.raises(ValueError, match="not a tool offered here"):
        agent.decide(new_state(), "investigate")
    assert agent.calls[-1].outcome == "invalid_reply"


def test_a_reply_that_breaks_the_answer_type_is_refused():
    agent = policy(
        decide=[
            '{"choice": "stop", "stop_reason": "i am done", "information_needed": "x"}'
        ]
    )
    with pytest.raises(ValueError):
        agent.decide(new_state(), "investigate")
    assert agent.calls[-1].outcome == "invalid_reply"


def test_interpreting_is_told_which_call_was_just_made():
    agent = policy(interpret=[{"hypotheses": None}])
    step = CallTool(
        information_needed="whether vibration rose gradually",
        request=ToolRequest(name="get_sensor_trend", arguments={"to_tick": 914}),
        hypothesis_id="H1",
    )
    state = state_with_evidence()
    assert agent.interpret(state, step, state.evidence[0]) == Interpretation()
    prompt = agent.clients["interpret"].asked[0][1]
    assert 'JUST ASKED: get_sensor_trend {"to_tick":914}' in prompt
    assert "testing H1" in prompt and "Its answer is E1 above." in prompt


def test_a_conclusion_comes_with_an_action_or_none():
    concluded = {
        "diagnosis": "CNC-02 is wearing",
        "confidence": 0.9,
        "recommendation": "no_action",
    }
    agent = policy(conclude=[{"conclusion": concluded}])
    conclusion, action = agent.conclude(state_with_evidence())
    assert conclusion == AgentConclusion(**concluded) and action is None
    assert "replace_bearing" in SYSTEM["conclude"]  # the actions, not the causes


def test_a_judgement_keeps_the_prediction_recorded_before_the_action():
    state = state_with_evidence()
    state.predicted_effect = "vibration falls"
    agent = policy(judge_verification=[{"outcome": "resolved", "evidence_ids": ["E1"]}])
    check = agent.judge_verification(state)
    assert (check.outcome, check.prediction, check.evidence_ids) == (
        "resolved",
        "vibration falls",
        ("E1",),
    )


@pytest.mark.parametrize("lesson", [None, "", "   "])
def test_no_lesson_is_none(lesson):
    agent = policy(write_lesson=[{"lesson": lesson}])
    assert agent.write_lesson(new_state()) is None


def test_the_policy_never_changes_the_state_it_is_shown():
    state = state_with_evidence()
    before = state.model_dump()
    agent = policy(
        plan=[{"questions": []}],
        hypothesize=[{"hypotheses": None}],
        write_lesson=[LessonAnswer(lesson="x").model_dump()],
    )
    agent.plan(state)
    agent.hypothesize(state)
    agent.write_lesson(state)
    assert state.model_dump() == before


def test_every_job_needs_a_client():
    with pytest.raises(ValueError, match="no model client for decide"):
        ModelPolicy({job: FakeModel() for job in JOBS if job != "decide"}, ())


# --- the record of each model question -------------------------------------------


def test_each_question_records_the_models_tried_and_why_each_failed():
    from tests.test_chat_client import UNREACHABLE, chat, client

    groq, _ = client(UNREACHABLE, UNREACHABLE, model="groq")
    mistral, _ = client(chat('{"questions": []}'), model="mistral")
    fallback = FallbackClient([groq, mistral], sleep=lambda s: None)
    clients = {job: FakeModel() for job in JOBS} | {"plan": fallback}
    agent = ModelPolicy(clients, ())
    agent.plan(new_state())
    [made] = agent.calls
    assert (made.job, made.outcome, made.answered_by) == ("plan", "answered", "mistral")
    assert [(a.model, a.outcome) for a in made.attempts] == [
        ("groq", "the model service could not be reached"),
        ("groq", "the model service could not be reached"),
        ("mistral", "answered"),
    ]


# --- a whole episode through the model policy -------------------------------------


def number(pattern, prompt):
    return int(re.search(pattern, prompt).group(1))


def latest_evidence(prompt):
    return max(int(n) for n in re.findall(r"^- E(\d+) ", prompt, re.MULTILINE))


def verify_look(prompt):
    since = number(r"finished at tick (\d+)", prompt)
    now = number(r"NOW: tick (\d+)", prompt)
    return call(
        "get_sensor_summary",
        machine_id="CNC-02",
        sensor="vibration",
        from_tick=since + 1,
        to_tick=now,
    )


def judge(prompt):
    return {
        "outcome": "resolved",
        "evidence_ids": ["E2", f"E{latest_evidence(prompt)}"],
    }


def believe(confidence, *evidence_ids):
    return {
        "hypotheses": [
            {
                "id": "H1",
                "claim": "the alarmed machine is wearing",
                "confidence": confidence,
                "supporting_evidence_ids": list(evidence_ids),
            }
        ]
    }


def scripted_models():
    """Replies a model might give on seed 6, worked out from the prompt alone."""
    return policy(
        plan=[{"questions": [{"id": "Q1", "text": "How has vibration changed?"}]}],
        decide=[
            lambda p: call(
                "get_sensor_summary",
                question_id="Q1",
                machine_id="CNC-02",
                sensor="vibration",
                from_tick=number(r"tick (\d+)\):", p) - 300,
                to_tick=number(r"tick (\d+)\):", p),
            ),
            stop(),
            lambda p: call(
                "get_sensor_trend",
                machine_id="CNC-02",
                sensor="vibration",
                from_tick=number(r"NOW: tick (\d+)", p) - 600,
                to_tick=number(r"NOW: tick (\d+)", p),
                bucket_ticks=100,
            ),
            call("wait", ticks=300),
            verify_look,
            stop(),
        ],
        interpret=[
            {"hypotheses": None},
            believe(0.95, "E2", "E3"),
            {"hypotheses": None},
            {"hypotheses": None},
        ],
        hypothesize=[believe(0.6, "E2")],
        conclude=[
            {
                "conclusion": {
                    "diagnosis": "the spindle bearing on CNC-02 is wearing",
                    "confidence": 0.95,
                    "recommendation": "intervene",
                    "hypothesis_id": "H1",
                    "evidence_ids": ["E2", "E3"],
                },
                "action": {
                    "machine_id": "CNC-02",
                    "action": "replace_bearing",
                    "reason": "vibration climbed in every block",
                    "prediction": "vibration on CNC-02 falls back",
                },
            }
        ],
        judge_verification=[judge],
    )


def test_a_whole_episode_runs_on_model_replies_alone():
    agent = scripted_models()
    result = run_episode(6, agent, fault="bearing_degradation", clock=lambda: 0.0)
    state = result.state
    assert state.proposed_action == ProposalRecord(
        proposal_id=1,
        machine_id="CNC-02",
        action="replace_bearing",
        reason="vibration climbed in every block",
        status="approved",
    )
    assert state.verification.outcome == "resolved"
    assert result.score.action_correct and result.score.resolved
    assert [c.job for c in agent.calls] == [
        "plan",
        "decide",
        "interpret",
        "decide",
        "hypothesize",
        "decide",
        "interpret",
        "conclude",
        "decide",
        "interpret",
        "decide",
        "interpret",
        "decide",
        "judge_verification",
    ]
    assert all(c.outcome == "answered" for c in agent.calls)
    # The check looked at data from after the work, which the view had shown.
    check_prompt = agent.clients["judge_verification"].asked[0][1]
    assert f"finished at tick {state.action_finish_tick}" in check_prompt


class Slow:
    """Wraps a model client so that every answer takes `seconds` on `clock`."""

    def __init__(self, client, clock, seconds):
        self.client, self.clock, self.seconds = client, clock, seconds
        self.answered_by, self.attempts = client.answered_by, client.attempts
        self.asked = client.asked

    def ask(self, system, prompt, answer_type, *, max_seconds=None):
        self.clock[0] += self.seconds
        return self.client.ask(system, prompt, answer_type, max_seconds=max_seconds)


def slow_episode(seconds_per_answer, **budgets):
    from capstone.agent.state import Budgets

    clock = [0.0]
    agent = scripted_models()
    agent.clients = {
        job: Slow(client, clock, seconds_per_answer)
        for job, client in agent.clients.items()
    }
    return run_episode(
        6,
        agent,
        fault="bearing_degradation",
        clock=lambda: clock[0],
        budgets=Budgets(**budgets),
    )


def test_the_default_budget_fits_a_whole_episode_at_eight_seconds_an_answer():
    result = slow_episode(8.0)
    assert result.state.termination_reason != "timeout"
    assert result.state.verification.outcome == "resolved"
    assert result.score.resolved


def test_the_old_sixty_second_budget_did_not():
    """At 8 s an answer, 60 s ran out after two tool calls, with nothing found."""
    result = slow_episode(8.0, timeout_seconds=60.0, followup_seconds=20.0)
    state = result.state
    assert state.termination_reason == "timeout"
    assert state.conclusion.diagnosis == "undetermined"
    assert state.proposed_action is None and not result.score.resolved


class StallsOnce(Slow):
    """Like Slow, but its `nth` question gets no answer: it waits the whole
    limit it was given (or, with `waits=False`, fails at once)."""

    def __init__(self, client, clock, seconds, nth, *, waits=True):
        super().__init__(client, clock, seconds)
        self.nth, self.waits, self.count = nth, waits, 0

    def ask(self, system, prompt, answer_type, *, max_seconds=None):
        self.count += 1
        if self.count != self.nth:
            return super().ask(system, prompt, answer_type, max_seconds=max_seconds)
        self.client.limits.append(max_seconds)
        self.client.replies.pop(0)  # the reply this question would have had
        if self.waits:
            self.clock[0] += max_seconds
        raise ModelError("no model service answered (a: the model service timed out)")


def stalled_episode(job, nth, *, waits=True, **budgets):
    """Seed 6 at 8 s an answer, with the `nth` question of `job` stalling."""
    from capstone.agent.state import Budgets

    clock = [0.0]
    agent = scripted_models()
    agent.clients = {
        name: StallsOnce(client, clock, 8.0, nth if name == job else 0, waits=waits)
        for name, client in agent.clients.items()
    }
    result = run_episode(
        6,
        agent,
        fault="bearing_degradation",
        clock=lambda: clock[0],
        budgets=Budgets(**budgets),
    )
    return result, agent, clock[0]


def test_a_question_may_use_only_the_research_time_left():
    # Research ends 110 - 60 = 50 s in. Five answers take 40 s, so the
    # test stage's decide may wait 10 s, not its own 20.
    result, agent, _ = stalled_episode(
        "decide", 3, timeout_seconds=110, followup_seconds=60
    )
    state = result.state
    assert agent.clients["decide"].client.limits[2] == 10.0
    stop = next(d for d in state.decisions if d.phase == "test")
    assert (stop.outcome, stop.termination_reason) == ("stopped", "timeout")
    # Research ended on time, with the follow-up time whole: the conclusion
    # was asked with the 60 s kept for it, and the run reports the timeout.
    assert agent.clients["conclude"].client.limits == [60.0]
    assert state.termination_reason == "timeout"
    assert state.conclusion is not None


def test_a_cut_off_interpretation_keeps_the_evidence_and_the_run_goes_on():
    # Research ends 115 - 60 = 55 s in; the test stage's interpret starts at
    # 48 s and may wait 7. The fix and the check still fit in the 60 s kept.
    result, agent, _ = stalled_episode(
        "interpret", 2, timeout_seconds=115, followup_seconds=60
    )
    state = result.state
    assert agent.clients["interpret"].client.limits[1] == 7.0
    assert "E3" in {e.id for e in state.evidence}
    assert state.interpretation_failures == 0  # the clock's doing, not the model's
    assert state.termination_reason == "timeout"
    assert state.proposed_action.status == "approved"
    assert state.verification.outcome == "resolved"


class GivesUpNearTheDeadline(StallsOnce):
    """Its `nth` question waits until 1.5 s before the deadline it was given,
    then gives up as the real client does: less left than a retry pause."""

    def ask(self, system, prompt, answer_type, *, max_seconds=None):
        self.count += 1
        if self.count != self.nth:
            return Slow.ask(self, system, prompt, answer_type, max_seconds=max_seconds)
        self.client.replies.pop(0)
        self.clock[0] += max_seconds - 1.5
        raise ModelError(
            "no model service answered (a: no time left)", out_of_time=True
        )


def test_giving_up_just_before_the_deadline_is_a_timeout_not_an_outage():
    """Seen live on 2026-10-20: research ran out mid-question with 1-2 s left."""
    from capstone.agent.state import Budgets

    clock = [0.0]
    agent = scripted_models()
    agent.clients = {
        name: GivesUpNearTheDeadline(client, clock, 8.0, 3 if name == "decide" else 0)
        for name, client in agent.clients.items()
    }
    result = run_episode(
        6,
        agent,
        fault="bearing_degradation",
        clock=lambda: clock[0],
        budgets=Budgets(timeout_seconds=110, followup_seconds=60),
    )
    assert result.state.termination_reason == "timeout"
    assert result.state.conclusion is not None


def test_a_failure_with_time_left_is_still_an_outage():
    result, _, _ = stalled_episode("decide", 3, waits=False)
    assert result.state.termination_reason == "model_unavailable"


def test_a_question_outside_a_running_investigation_has_only_its_own_limit():
    # The lesson is written from the finished state, after the deadline:
    # the loop sets no limit there, so the client's own limit applies.
    agent = policy(write_lesson=[{"lesson": "check vibration first"}])
    agent.write_lesson(new_state())
    assert agent.clients["write_lesson"].limits == [None]


# --- the decide answer is one flat object, never a union to nest -------------


def test_the_reply_seen_live_that_nested_the_call_under_its_name_is_refused():
    nested = {
        "decision": {
            "CallTool": {
                "information_needed": "vibration on CNC-02",
                "request": {"name": "get_sensor_trend", "arguments": {}},
            }
        }
    }
    agent = policy(decide=[nested])
    with pytest.raises(ValueError):
        agent.decide(new_state(), "investigate")
    assert agent.calls[-1].outcome == "invalid_reply"


def test_a_flat_call_becomes_the_loops_own_call_with_its_ids():
    reply = call("get_sensor_trend", question_id="Q1", machine_id="CNC-02")
    reply["hypothesis_id"] = "H2"
    decision = policy(decide=[reply]).decide(new_state(), "test")
    assert decision == CallTool(
        information_needed="what get_sensor_trend shows",
        request=ToolRequest(
            name="get_sensor_trend", arguments={"machine_id": "CNC-02"}
        ),
        question_id="Q1",
        hypothesis_id="H2",
    )


@pytest.mark.parametrize(
    "reply, problem",
    [
        ({"choice": "call_tool", "information_needed": "x"}, "must name a tool"),
        (
            {**call("get_events"), "stop_reason": "evidence_sufficient"},
            "gives no stop_reason",
        ),
        ({"choice": "stop", "information_needed": "x"}, "must give a stop_reason"),
        ({**stop(), "tool": "get_events"}, "names no tool"),
        ({**stop(), "question_id": "Q1"}, "names no tool"),
    ],
)
def test_each_choice_keeps_to_its_own_fields(reply, problem):
    agent = policy(decide=[reply])
    with pytest.raises(ValueError, match=problem):
        agent.decide(new_state(), "investigate")
    assert agent.calls[-1].outcome == "invalid_reply"


def test_the_schema_the_model_sees_has_no_named_alternatives_to_nest():
    schema = NextStep.model_json_schema()
    assert "CallTool" not in json.dumps(schema) and "Stop" not in schema.get(
        "$defs", {}
    )
    assert schema["properties"]["choice"]["enum"] == ["call_tool", "stop"]
    assert "anyOf" not in json.dumps(schema["properties"]["choice"])


# --- the budget, as the model is shown it -------------------------------------------


def budget_line(state):
    return next(line for line in render(state).splitlines() if "BUDGET LEFT" in line)


def test_the_budget_line_shows_the_stages_seconds_only_when_known():
    state = new_state()
    assert "seconds" not in budget_line(state)
    state.seconds_for_question = 47.9
    assert budget_line(state).endswith(", about 47 seconds for this stage")


def test_a_low_budget_note_appears_only_when_research_calls_are_nearly_spent():
    from capstone.agent.model_policy import LOW_BUDGET_NOTE, LOW_CALLS

    state = new_state(max_tool_calls=5)
    assert LOW_BUDGET_NOTE not in render(state)
    state.tool_call_count = 5 - LOW_CALLS
    assert LOW_BUDGET_NOTE in render(state)
    state.conclusion = AgentConclusion(
        diagnosis="undetermined", confidence=0.0, recommendation="escalate"
    )
    assert LOW_BUDGET_NOTE not in render(state)  # research is over


def test_every_job_is_told_to_spend_the_budget_well_not_to_hurry():
    for job, system in SYSTEM.items():
        assert "BUDGET LEFT" in system, job
        assert "Being thorough matters more than being fast" in system, job
    assert "remaining budget is better saved" in SYSTEM["decide"]
