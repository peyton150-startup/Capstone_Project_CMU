import json

from capstone.agent.episode import run_episode
from capstone.agent.memory import InvestigationMemory
from capstone.agent.models import ScriptedModel, Turn
from tests.test_agent import bearing_script, call, machine_in


def test_a_finished_investigation_is_saved_with_its_story_and_the_technicians_finding(tmp_path):
    memory = InvestigationMemory(tmp_path / "memory.jsonl")
    run_episode(2, ScriptedModel(bearing_script()), fault="bearing_degradation", memory=memory)
    (entry,) = memory.records
    assert entry["anomaly"].startswith("tick") and "alarm" in entry["anomaly"]
    assert entry["conclusion"]["fault"] == "bearing_degradation"
    assert entry["actions"] == [f"replace_bearing {entry['conclusion']['machine_id']}"]
    assert entry["outcome"][-1].startswith("bearing replacement finished: old bearing")
    assert entry["hypotheses"][0]["hypothesis"] == "bearing_degradation"
    assert [c["name"] for c in entry["evidence"]] == ["get_sensor_trend", "propose_action", "get_proposals", "wait"]


def test_memory_never_holds_the_score_or_the_ground_truth(tmp_path):
    memory = InvestigationMemory(tmp_path / "memory.jsonl")
    run_episode(2, ScriptedModel(bearing_script()), fault="bearing_degradation", memory=memory)
    text = (tmp_path / "memory.jsonl").read_text()
    for secret in ("fault_correct", "true_fault", "resolved", "bearing_health", "start_tick"):
        assert secret not in text


def test_records_survive_a_restart_and_similar_cases_come_first(tmp_path):
    path = tmp_path / "memory.jsonl"
    memory = InvestigationMemory(path)
    run_episode(2, ScriptedModel(bearing_script()), fault="bearing_degradation", memory=memory)
    false_alarm = [lambda m: Turn(tool_calls=[call("submit_diagnosis", fault="false_alarm",
                                                   machine_id=machine_in(m.prompt), batch_id=None,
                                                   summary="single spike")], stop_reason="tool_use")]
    run_episode(0, ScriptedModel(false_alarm), fault="false_alarm", memory=memory)

    reloaded = InvestigationMemory(path)
    assert [r["id"] for r in reloaded.records] == [1, 2]
    hits = reloaded.search("vibration alarm, old bearing worn")
    assert hits[0]["investigation"] == 1
    assert reloaded.search("single spike")[0]["conclusion"]["fault"] == "false_alarm"
    assert reloaded.search("zebra") == []


def test_the_agent_can_search_memory_during_a_later_investigation(tmp_path):
    memory = InvestigationMemory(tmp_path / "memory.jsonl")
    run_episode(2, ScriptedModel(bearing_script()), fault="bearing_degradation", memory=memory)
    model = ScriptedModel([
        Turn(tool_calls=[call("search_incident_history", query="vibration alarm bearing")], stop_reason="tool_use"),
        lambda m: Turn(tool_calls=[call("submit_diagnosis", fault="false_alarm", machine_id=machine_in(m.prompt),
                                        batch_id=None, summary="x")], stop_reason="tool_use"),
    ])
    run_episode(0, model, fault="false_alarm", memory=memory)
    found = model.last_result(0) if len(model.results) == 1 else json.loads(model.results[0][0].content)
    assert found[0]["conclusion"]["fault"] == "bearing_degradation"
    assert "search_incident_history" in {spec["name"] for spec in model.tools}
