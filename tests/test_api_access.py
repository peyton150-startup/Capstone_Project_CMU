"""Browser access roles: token generation, environment check, whoami, errors."""

from __future__ import annotations

import pytest

from capstone.api.access import (
    ROLE_VARIABLES,
    check_environment,
    env_block,
    generate_tokens,
    main,
    roles_for,
)
from capstone.api.config import UiConfig

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - API extra absent
    TestClient = None

VIEWER = "viewer-abcdefghijklmnopqrstuvwxyz"
OPERATOR = "operator-abcdefghijklmnopqrstuvwxyz"
REVIEWER = "reviewer-abcdefghijklmnopqrstuvwxyz"
EVALUATOR = "evaluator-abcdefghijklmnopqrstuvwxyz"


def run_config(tmp_path, **extra):
    return UiConfig(
        token=VIEWER,
        run_token=OPERATOR,
        review_token=REVIEWER,
        run_db=tmp_path / "runs.sqlite",
        runs_enabled=True,
        **extra,
    )


def test_generated_tokens_are_distinct_long_and_pass_the_api_rules(tmp_path):
    tokens = generate_tokens()
    assert set(tokens) == set(ROLE_VARIABLES.values())
    assert len(set(tokens.values())) == 4
    assert all(len(value) >= 24 for value in tokens.values())
    # The same values satisfy UiConfig's own startup validation.
    UiConfig(
        token=tokens["CAPSTONE_UI_TOKEN"],
        run_token=tokens["CAPSTONE_UI_RUN_TOKEN"],
        review_token=tokens["CAPSTONE_UI_REVIEW_TOKEN"],
        evaluator_token=tokens["CAPSTONE_UI_EVALUATOR_TOKEN"],
        evaluator=True,
        run_db=tmp_path / "runs.sqlite",
        runs_enabled=True,
    )
    block = env_block(tokens)
    assert "CAPSTONE_UI_SIM_RUNS=1" in block
    assert check_environment(dict(line.split("=", 1) for line in block.split())) == []


def test_check_names_problems_without_printing_values(capsys, monkeypatch):
    env = {
        "CAPSTONE_UI_SIM_RUNS": "1",
        "CAPSTONE_UI_TOKEN": VIEWER,
        "CAPSTONE_UI_RUN_TOKEN": VIEWER,
        "CAPSTONE_UI_EVALUATOR_TOKEN": "short",
    }
    problems = check_environment(env)
    assert "CAPSTONE_UI_REVIEW_TOKEN is not set" in problems
    assert any(
        "CAPSTONE_UI_RUN_TOKEN is the same as CAPSTONE_UI_TOKEN" in p for p in problems
    )
    assert any("CAPSTONE_UI_EVALUATOR_TOKEN is shorter" in p for p in problems)
    for name in ROLE_VARIABLES.values():
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert main(["check"]) == 1
    out = capsys.readouterr().out
    assert VIEWER not in out and "short" not in out.replace("shorter", "")


def test_check_warns_when_role_tokens_are_set_but_runs_are_off():
    problems = check_environment(
        {"CAPSTONE_UI_TOKEN": VIEWER, "CAPSTONE_UI_RUN_TOKEN": OPERATOR}
    )
    assert problems == ["CAPSTONE_UI_SIM_RUNS=1 is not set, so runs stay off"]


def test_roles_for_matches_only_the_exact_token(tmp_path):
    cfg = run_config(tmp_path)
    assert roles_for(OPERATOR, cfg) == ["operator"]
    assert roles_for(VIEWER, cfg) == ["viewer"]
    assert roles_for("", cfg) == []
    assert roles_for(OPERATOR + "x", cfg) == []


@pytest.mark.skipif(TestClient is None, reason="FastAPI optional dependency absent")
def test_whoami_and_named_role_errors(tmp_path):
    from capstone.api.app import create_app

    client = TestClient(create_app(run_config(tmp_path)))

    def who(token):
        return client.get(
            "/api/v1/access/whoami", headers={"Authorization": "Bearer " + token}
        ).json()

    assert who(OPERATOR) == {"open": False, "roles": ["operator"], "runs_enabled": True}
    assert who(REVIEWER)["roles"] == ["reviewer"]
    assert who("not-a-token")["roles"] == []
    # A viewer token cannot start a run, and the error says which token can.
    denied = client.post(
        "/api/v1/lab/runs",
        json={"seed": 3, "kind": "standard", "mode": "deep"},
        headers={"Authorization": "Bearer " + VIEWER, "Idempotency-Key": "k" * 20},
    )
    assert denied.status_code == 403
    assert "CAPSTONE_UI_RUN_TOKEN" in denied.json()["detail"]
    review = client.post(
        "/api/v1/simulator/reviews/00000000-0000-0000-0000-000000000000",
        json={"proposal_id": 1, "decision": "approve"},
        headers={"Authorization": "Bearer " + OPERATOR},
    )
    assert review.status_code == 403
    assert "CAPSTONE_UI_REVIEW_TOKEN" in review.json()["detail"]


@pytest.mark.skipif(TestClient is None, reason="FastAPI optional dependency absent")
def test_evaluator_endpoints_name_the_evaluator_token(tmp_path):
    from capstone.api.app import create_app

    cfg = run_config(tmp_path, evaluator=True, evaluator_token=EVALUATOR)
    client = TestClient(create_app(cfg))
    denied = client.get(
        "/api/v1/evaluations", headers={"Authorization": "Bearer " + OPERATOR}
    )
    assert denied.status_code == 403
    assert "CAPSTONE_UI_EVALUATOR_TOKEN" in denied.json()["detail"]
    allowed = client.get(
        "/api/v1/evaluations", headers={"Authorization": "Bearer " + EVALUATOR}
    )
    assert allowed.status_code == 200
