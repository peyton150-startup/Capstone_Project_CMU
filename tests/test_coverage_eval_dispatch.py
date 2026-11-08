"""Cover the evaluator's planned requests without sending a model call."""

import json
from types import SimpleNamespace

import pytest

from evaltools import full_evaluation, run_packet, snap_request


@pytest.mark.parametrize(
    "family, identifier",
    [
        ("functions", "function:one"),
        ("tests", "tests/test_example.py::test_one"),
        ("tools", "get_readings"),
        ("runs", "archive"),
    ],
)
def test_request_cli_dispatches_each_family_offline(
    tmp_path, monkeypatch, capsys, family, identifier
):
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    entries = [
        ("FUNCTION_INVENTORY.json", "functions", "id", "function:one"),
        ("TEST_INVENTORY.json", "tests", "id", "tests/test_example.py::test_one"),
        ("TOOL_INVENTORY.json", "tools", "name", "get_readings"),
    ]
    for filename, key, id_field, value in entries:
        (inventory / filename).write_text(
            json.dumps({key: [{id_field: value}]}), encoding="utf-8"
        )
    monkeypatch.setattr(
        snap_request,
        "load_questions",
        lambda *args: ({"rubric_version": "synthetic"}, []),
    )
    monkeypatch.setattr(snap_request, "questions_for", lambda *args: [])
    events = []
    monkeypatch.setattr(
        snap_request,
        "function_state",
        lambda item, tests: (events.append("FN"), {"id": item["id"]})[1],
    )
    monkeypatch.setattr(
        snap_request,
        "test_state",
        lambda item, functions: (events.append("TS"), {"id": item["id"]})[1],
    )
    monkeypatch.setattr(
        snap_request,
        "tool_state",
        lambda item, functions, tests=None: (events.append("TL"), {"id": item["name"]})[1],
    )
    monkeypatch.setattr(
        snap_request,
        "item_requests",
        lambda items, questions, providers, **kwargs: (
            events.append(("items", [item[0] for item in items])),
            [{"body": {}, "tags": {}}],
        )[1],
    )
    monkeypatch.setattr(
        snap_request,
        "run_requests",
        lambda directory, questions, providers, **kwargs: (
            events.append(("runs", directory)),
            [{"body": {}, "tags": {}}],
        )[1],
    )
    monkeypatch.setattr(
        snap_request,
        "write_requests",
        lambda built, out, **kwargs: (
            events.append(("write", len(built), kwargs["send_them"])),
            {"failed": 0, "sent": 0, "already_answered": 0},
        )[1],
    )
    args = [
        "--out",
        str(tmp_path / "requests"),
        "--inventory",
        str(inventory),
        "--provider",
        "snap",
        "--model",
        "offline-override",
        "--send",
    ]
    option = {
        "functions": "--ids",
        "tests": "--ids",
        "tools": "--names",
        "runs": "--packets",
    }[family]
    assert snap_request.main([*args, family, option, identifier]) == 0
    assert events[-1] == ("write", 1, True)
    assert "1 request file(s)" in capsys.readouterr().out
    if family == "runs":
        assert any(event[0] == "runs" for event in events if isinstance(event, tuple))
    else:
        assert ("items", [identifier]) in events


def test_request_cli_returns_failure_when_a_mocked_send_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        snap_request,
        "load_questions",
        lambda *args: ({"rubric_version": "test"}, []),
    )
    monkeypatch.setattr(
        snap_request, "run_requests", lambda *args, **kwargs: [{"body": {}}]
    )
    monkeypatch.setattr(
        snap_request,
        "write_requests",
        lambda *args, **kwargs: {
            "failed": 1,
            "sent": 0,
            "already_answered": 0,
        },
    )
    assert (
        snap_request.main(
            [
                "--out",
                str(tmp_path / "requests"),
                "--provider",
                "snap",
                "--full-context",
                "--send",
                "runs",
                "--packets",
                str(tmp_path / "archive"),
            ]
        )
        == 1
    )


@pytest.mark.parametrize("failure", [True, False])
def test_plan_covers_archived_packets_and_refused_or_unfittable_comparisons(
    tmp_path, monkeypatch, failure
):
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    for filename, payload in [
        (
            "FUNCTION_INVENTORY.json",
            {
                "functions": [
                    {
                        "id": "module:function",
                        "snap_questions": ["FN-01"],
                        "verification_status": "TESTED",
                    }
                ]
            },
        ),
        ("TEST_INVENTORY.json", {"tests": [{"id": "test-case"}]}),
        ("TOOL_INVENTORY.json", {"tools": [{"name": "get_readings"}]}),
    ]:
        (inventory / filename).write_text(json.dumps(payload))
    for key in ("function_state", "test_state", "tool_state"):
        monkeypatch.setattr(snap_request, key, lambda *args, **kwargs: {})
    monkeypatch.setattr(snap_request, "item_requests", lambda *args, **kwargs: [])
    monkeypatch.setattr(snap_request, "run_requests", lambda *args, **kwargs: [])
    packet = SimpleNamespace(
        meta=SimpleNamespace(episode_key="offline/1"),
        model_dump_json=lambda indent: "{}",
    )

    def load_archive(path, *, refused):
        refused.append({"episode_key": "offline/refused", "reason": "bad audit"})
        return [packet]

    monkeypatch.setattr(run_packet, "build_archive", load_archive)
    monkeypatch.setattr(run_packet, "check_unique", lambda packets: None)
    monkeypatch.setattr(
        full_evaluation,
        "comparisons",
        lambda packets: [
            {
                "state": {"factors": "synthetic"},
                "item_id": "before-and-after",
                "forbidden": ["PRIVATE"],
            }
        ],
    )

    def build_request(*args, **kwargs):
        if failure:
            raise ValueError("state exceeds provider window")
        return [
            {
                "body": {"data": "PRIVATE"},
                "tags": {
                    "family": "BT",
                    "provider": "snap",
                    "item_id": "before-and-after",
                    "question_ids": ["BT-01"],
                },
            }
        ]

    monkeypatch.setattr(snap_request, "build_request", build_request)
    monkeypatch.setattr(
        run_packet,
        "leak_in",
        lambda data, forbidden: "PRIVATE" if "PRIVATE" in data else None,
    )
    out = tmp_path / "output"
    archive = tmp_path / "saved-episodes"
    result = full_evaluation.plan(
        inventory=inventory,
        archives=[archive],
        providers=[full_evaluation.PROVIDERS["snap"]],
        out=out,
        commit="abc123",
        families=("FN", "TS", "TL", "RUN", "BT"),
    )
    assert (out / "packets" / archive.name).exists()
    assert len(result["packets"]) == 1
    assert len(result["built"]) == 1
    request = result["built"][0]
    assert request["body"] is None
    assert "unfittable" in request["tags"]
    assert result["refused_packets"] == [
        {"episode_key": "offline/refused", "reason": "bad audit"}
    ]
    assert any(
        row["family"] == "RUN"
        and row["status"] == "refused"
        and row["item_id"] == "offline/refused"
        for row in result["rows"]
    )
