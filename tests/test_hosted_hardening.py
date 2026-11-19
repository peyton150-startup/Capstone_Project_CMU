"""Hosted hardening from the overnight merge audit (PR #314): no database needed.

- hosted mode refuses a missing or short build commit (web and worker);
- a malformed TRIAGE_* value is the same 503 on every settings endpoint;
- a pydantic ValidationError during model setup is a model_setup failure.
"""

import logging

import pytest

from capstone.api.run_repository import (
    SOURCE_REVISION_VARIABLES,
    hosted_revision,
)
from capstone.api.runs import InvalidRunEnvironment


@pytest.fixture
def no_revision(monkeypatch):
    for name in SOURCE_REVISION_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_hosted_mode_needs_the_full_build_commit(no_revision):
    with pytest.raises(InvalidRunEnvironment):
        hosted_revision()  # nothing set: web and worker would both say None
    no_revision.setenv("NF_DEPLOYMENT_SHA", "abc1234")
    with pytest.raises(InvalidRunEnvironment):
        hosted_revision()  # short: never equals the other host's full SHA
    no_revision.setenv("NF_DEPLOYMENT_SHA", "a" * 40)
    assert hosted_revision() == "a" * 40


def test_hosted_runner_refuses_readiness_and_submission_without_a_commit(
    no_revision,
):
    from capstone.api.hosted_runs import HostedSimulatorRuns
    from capstone.api.runs import RunRequest

    class Repository:
        def ready(self):
            return True

        def submit(self, *args, **kwargs):
            pytest.fail("a run without a build commit must not be stored")

    runner = HostedSimulatorRuns.__new__(HostedSimulatorRuns)
    runner.repository = Repository()
    with pytest.raises(InvalidRunEnvironment):
        runner.ready()
    with pytest.raises(InvalidRunEnvironment):
        runner.submit(RunRequest(seed=1), "hardening-key-000001")
    no_revision.setenv("RENDER_GIT_COMMIT", "c" * 40)
    assert runner.ready()


def test_ready_endpoint_names_a_missing_commit(no_revision):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import capstone.api.hosted_runs as hosted
    from capstone.api.app import create_app
    from capstone.api.config import UiConfig

    class SchemaReady(hosted.HostedSimulatorRuns):
        def __init__(self, url):
            self.repository = type("R", (), {"ready": lambda self: True})()

        def close(self):
            pass

    no_revision.setattr(hosted, "HostedSimulatorRuns", SchemaReady)
    client = TestClient(
        create_app(
            UiConfig(
                run_backend="hosted",
                run_database_url="postgresql://dummy/capstone_test",
                runs_enabled=True,
                token="v" * 24,
                run_token="o" * 24,
                review_token="r" * 24,
            )
        )
    )
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "Hosted build commit missing"
    no_revision.setenv("RENDER_GIT_COMMIT", "d" * 40)
    assert client.get("/api/v1/ready").status_code == 200


def test_worker_refuses_to_start_without_a_commit(no_revision, caplog):
    import json

    from capstone.worker.runner import main

    no_revision.setenv("CAPSTONE_WORKER_ENABLED", "1")
    no_revision.setenv(
        "CAPSTONE_UI_RUN_DATABASE_URL", "postgresql://dummy/capstone_test"
    )
    with caplog.at_level(logging.INFO, logger="capstone.worker"):
        with pytest.raises(InvalidRunEnvironment):
            main()
    logged = json.loads(caplog.records[-1].message)
    assert logged == {
        "event": "worker_stopped",
        "failure_code": "invalid_configuration",
        "service": "agent_worker",
    }


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/v1/settings/effective"),
        ("get", "/api/v1/lab/runs/configuration"),
        ("post", "/api/v1/lab/runs/preview"),
        ("post", "/api/v1/lab/runs"),
    ],
)
def test_a_bad_triage_setting_is_one_named_server_fault(
    tmp_path, monkeypatch, method, path
):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from capstone.api.app import create_app
    from tests.test_web_runs import KEY, OPERATOR, auth, config

    monkeypatch.setenv("TRIAGE_PLAN", "not-a-plan")
    client = TestClient(create_app(config(tmp_path)))
    headers = {**auth(OPERATOR), "Idempotency-Key": KEY}
    if method == "get":
        response = client.get(path, headers=headers)
    else:
        response = client.post(path, headers=headers, json={"seed": 1})
    assert response.status_code == 503
    assert response.json()["detail"] == "Server run configuration is invalid"
    assert "not-a-plan" not in response.text


def test_a_validation_error_during_model_setup_is_model_setup():
    from pydantic import BaseModel, ValidationError

    from capstone.worker.runner import classify_failure

    class Model(BaseModel):
        name: int

    with pytest.raises(ValidationError) as raised:
        Model(name="not a number")
    assert classify_failure(raised.value, "model_setup") == "model_setup"
    # Outside model setup it is still a contract failure, as before.
    assert classify_failure(raised.value, "episode") == "contract"
    assert classify_failure(ValueError("x"), "model_setup") == "contract"
