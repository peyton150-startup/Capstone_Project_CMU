import json
import re
from types import SimpleNamespace

from capstone.agent.agent import SYSTEM_PROMPT, ResearchAgent
from capstone.agent.episode import run_episode
from capstone.agent.models import ClaudeModel, ScriptedModel, ToolCall, Turn
from capstone.agent.toolbox import MAX_ROWS, Toolbox
from capstone.simulator.generator import build_scenario
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools


def call(name: str, **kwargs) -> ToolCall:
    call.counter += 1
    return ToolCall(f"call_{call.counter}", name, kwargs)


call.counter = 0


def machine_in(prompt: str) -> str:
    return re.search(r"CNC-\d\d", prompt).group(0)


def bearing_script() -> list:
    """A competent investigator for a bearing fault, written out by hand."""
    return [
        lambda m: Turn(
            tool_calls=[
                call(
                    "get_sensor_trend",
                    machine_id=machine_in(m.prompt),
                    sensor="vibration",
                    from_tick=0,
                    to_tick=2000,
                    bucket_ticks=200,
                )
            ],
            stop_reason="tool_use",
        ),
        lambda m: Turn(
            tool_calls=[
                call(
                    "update_hypotheses",
                    hypotheses=[
                        {
                            "hypothesis": "bearing_degradation",
                            "supporting": "vibration creeping up",
                            "contradicting": "none",
                            "confidence": 0.7,
                        },
                        {
                            "hypothesis": "false_alarm",
                            "supporting": "single alarm",
                            "contradicting": "steady rise",
                            "confidence": 0.2,
                        },
                    ],
                )
            ],
            stop_reason="tool_use",
        ),
        lambda m: Turn(
            tool_calls=[
                call(
                    "propose_action",
                    machine_id=machine_in(m.prompt),
                    action="replace_bearing",
                    reason="vibration rising for hundreds of ticks; expect it to fall",
                )
            ],
            stop_reason="tool_use",
        ),
        lambda m: Turn(
            tool_calls=[call("get_proposals"), call("wait", ticks=60)],
            stop_reason="tool_use",
        ),
        lambda m: Turn(
            tool_calls=[
                call(
                    "submit_diagnosis",
                    fault="bearing_degradation",
                    machine_id=machine_in(m.prompt),
                    batch_id=None,
                    summary="bearing replaced; vibration back to normal",
                )
            ],
            stop_reason="tool_use",
        ),
    ]


def test_a_scripted_investigation_of_a_bearing_fault_scores_full_marks():
    model = ScriptedModel(bearing_script())
    result = run_episode(2, model, fault="bearing_degradation")
    s = result.score
    assert (s.fault_correct, s.target_correct, s.action_correct, s.resolved) == (
        True,
        True,
        True,
        True,
    )
    assert s.tool_calls == 6 and s.ticks_elapsed == 60
    assert result.hypotheses[0][0]["hypothesis"] == "bearing_degradation"
    assert (
        model.last_result(0)[0]["status"] == "approved"
    )  # the human approved between turns


def test_doing_nothing_and_naming_a_false_alarm_scores_full_marks():
    model = ScriptedModel(
        [
            lambda m: Turn(
                tool_calls=[
                    call(
                        "submit_diagnosis",
                        fault="false_alarm",
                        machine_id=machine_in(m.prompt),
                        batch_id=None,
                        summary="one spike, nothing else moved",
                    )
                ],
                stop_reason="tool_use",
            ),
        ]
    )
    s = run_episode(0, model, fault="false_alarm").score
    assert (
        s.fault_correct
        and s.target_correct
        and s.action_correct
        and s.resolved
        and s.actions_taken == []
    )


def test_a_rejecting_human_keeps_the_factory_unchanged():
    model = ScriptedModel(bearing_script())
    result = run_episode(
        2, model, fault="bearing_degradation", approver=lambda p: (False, "not now")
    )
    assert (
        result.score.actions_taken == []
        and not result.score.resolved
        and not result.score.action_correct
    )


def test_running_out_of_turns_leaves_no_diagnosis():
    model = ScriptedModel(
        [Turn(tool_calls=[call("get_time")], stop_reason="tool_use")] * 10
    )
    result = run_episode(0, model, fault="false_alarm", max_turns=3)
    assert result.score.diagnosed_fault is None and not result.score.fault_correct


def test_a_reply_without_tools_is_nudged_to_continue():
    model = ScriptedModel([Turn(text="Thinking aloud."), Turn(text="still")])
    run_episode(0, model, fault="false_alarm", max_turns=3)
    assert model.notes and "submit_diagnosis" in model.notes[0]


def toolbox(ticks: int = 900) -> tuple[Toolbox, ApprovalDesk]:
    sim = build_scenario(2, fault="bearing_degradation")
    desk = ApprovalDesk(sim)
    look, act = ObservationTools(sim), ActionTools(sim, desk)
    act.wait(min(ticks, 480))
    if ticks > 480:
        act.wait(ticks - 480)
    return Toolbox(look, act), desk


def test_every_described_tool_has_a_handler_and_none_can_approve():
    box, _ = toolbox(10)
    names = {spec["name"] for spec in box.specs}
    assert names == set(box._handlers)
    assert not {"approve", "reject", "ground_truth"} & names
    assert all(spec["input_schema"]["type"] == "object" for spec in box.specs)


def test_errors_come_back_as_error_results_and_every_call_is_counted():
    box, _ = toolbox(10)
    bad = box.run(
        ToolCall(
            "1",
            "get_readings",
            {
                "machine_id": "CNC-99",
                "sensor": "vibration",
                "from_tick": 0,
                "to_tick": 5,
            },
        )
    )
    unknown = box.run(ToolCall("2", "ground_truth", {}))
    wrong_args = box.run(ToolCall("3", "wait", {"minutes": 5}))
    assert bad.is_error and unknown.is_error and wrong_args.is_error
    assert "unknown machine" in json.loads(bad.content)["error"]
    assert box.tool_calls == 3


def test_oversized_answers_are_refused_with_a_pointer_to_the_trend_tool():
    box, _ = toolbox()
    big = box.run(
        ToolCall(
            "1",
            "get_readings",
            {
                "machine_id": "CNC-01",
                "sensor": "vibration",
                "from_tick": 0,
                "to_tick": MAX_ROWS + 50,
            },
        )
    )
    assert big.is_error and "get_sensor_trend" in json.loads(big.content)["error"]
    trend = json.loads(
        box.run(
            ToolCall(
                "2",
                "get_sensor_trend",
                {
                    "machine_id": "CNC-01",
                    "sensor": "vibration",
                    "from_tick": 1,
                    "to_tick": 600,
                },
            )
        ).content
    )
    assert len(trend) == 10 and trend[0]["count"] == 60


def test_nothing_the_agent_can_call_reveals_the_hidden_truth():
    box, _ = toolbox()
    seen = []
    for spec in box.specs:
        if spec["name"] in (
            "wait",
            "propose_action",
            "submit_diagnosis",
            "update_hypotheses",
            "get_job_history",
        ):
            continue
        args = {"from_tick": 0, "to_tick": 250}
        props = spec["input_schema"]["properties"]
        args = {k: v for k, v in args.items() if k in props}
        if "machine_id" in props:
            args["machine_id"] = "CNC-01"
        if "sensor" in props:
            args["sensor"] = props["sensor"]["enum"][0]
        seen.append(box.run(ToolCall("x", spec["name"], args)).content)
    text = " ".join(seen)
    for secret in (
        "bearing_health",
        "defect_risk",
        "sensor_offset",
        "bearing_degradation",
        "ground",
    ):
        assert secret not in text


def test_the_system_prompt_names_the_four_causes_and_both_actions():
    for word in (
        "bearing_degradation",
        "wrong_setting",
        "bad_material_batch",
        "false_alarm",
        "replace_bearing",
        "reset_setting",
        "submit_diagnosis",
        "update_hypotheses",
    ):
        assert word in SYSTEM_PROMPT


class FakeClient:
    """Stands in for anthropic.Anthropic(): records requests, returns prepared responses."""

    def __init__(self, responses):
        self.requests = []
        self._responses = list(responses)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._responses.pop(0)


def block(**kwargs):
    return SimpleNamespace(**kwargs)


def test_the_claude_model_sends_tools_and_returns_tool_results_as_tool_result_blocks():
    first = SimpleNamespace(
        stop_reason="tool_use",
        content=[
            block(type="thinking", thinking=""),
            block(type="text", text="Looking at the time."),
            block(type="tool_use", id="tu_1", name="get_time", input={}),
        ],
    )
    second = SimpleNamespace(
        stop_reason="end_turn", content=[block(type="text", text="Done.")]
    )
    client = FakeClient([first, second])
    model = ClaudeModel(client=client)
    turn = model.start("system", [{"name": "get_time"}], "anomaly")
    assert (
        turn.tool_calls == [ToolCall("tu_1", "get_time", {})]
        and turn.text == "Looking at the time."
    )
    request = client.requests[0]
    assert request["model"] == "claude-opus-5-5" and request["thinking"] == {
        "type": "adaptive"
    }
    assert request["fallbacks"] == "default" and request["tools"] == [
        {"name": "get_time"}
    ]

    from capstone.agent.models import ToolResult

    model.continue_with([ToolResult("tu_1", '{"tick": 5}')])
    sent = client.requests[1]["messages"]
    assert sent[1] == {
        "role": "assistant",
        "content": first.content,
    }  # thinking passed back unchanged
    assert sent[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "tu_1",
        "content": '{"tick": 5}',
        "is_error": False,
    }


def test_the_agent_stops_on_a_refusal():
    model = ScriptedModel([Turn(stop_reason="refusal")])
    box, _ = toolbox(10)
    result = ResearchAgent(model, box, max_turns=5).investigate("x")
    assert not result.finished and model.results == []


def test_the_command_line_refuses_politely_without_a_key(monkeypatch, capsys):
    from capstone.agent.__main__ import main

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert main(["--seed", "1", "--no-memory"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
