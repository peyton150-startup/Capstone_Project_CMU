"""The provider benchmark, with fake models and no network."""

import json
import urllib.error

import pytest

from capstone import benchmark
from capstone.agent.model_policy import ModelCall, ModelPolicy
from capstone.benchmark import (
    EpisodeRecord,
    format_table,
    percentile,
    run_model,
    single_model_clients,
    summarize,
)
from capstone.providers.chat import JOBS, Attempt, ChatClient, FallbackClient
from capstone.providers.factory import research_tools
from tests.test_model_policy import scripted_models


def made(job, outcome, *attempts):
    return ModelCall(
        job=job,
        outcome=outcome,
        attempts=tuple(Attempt(model="m", outcome=o, seconds=s) for o, s in attempts),
    )


def record(*calls, reason="diagnosis_supported", resolved=True):
    return EpisodeRecord(
        model="m",
        fault="bearing_degradation",
        seed=0,
        termination_reason=reason,
        diagnosis="worn",
        action_correct=resolved,
        resolved=resolved,
        calls=calls,
    )


# --- the numbers in one row --------------------------------------------------------


def test_a_row_counts_answers_invalid_replies_and_outages_apart():
    report = summarize(
        "m",
        [
            record(
                made("plan", "answered", ("answered", 1.0)),
                made("decide", "invalid_reply", ("invalid reply", 2.0)),
                made(
                    "decide",
                    "answered",
                    ("the model service timed out", 15.0),
                    ("answered", 3.0),
                ),
            ),
            record(
                made("plan", "no_answer", ("the model service answered HTTP 503", 0.2)),
                reason="model_unavailable",
                resolved=False,
            ),
        ],
    )
    assert (report.episodes, report.questions, report.answered) == (2, 4, 2)
    assert (report.invalid_replies, report.invalid_by_job) == (1, {"decide": 1})
    assert report.outages == 2
    # Times are the model's own answers, valid or not; outages are left out.
    assert (report.median_seconds, report.p95_seconds) == (2.0, 3.0)
    assert report.questions_per_episode == 2.0
    assert (report.model_unavailable, report.timeouts) == (1, 0)
    assert (report.action_correct, report.resolved) == (1, 1)


def test_the_slowest_five_percent_is_the_nearest_rank():
    assert percentile([], 0.95) is None
    assert percentile([3.0], 0.95) == 3.0
    assert percentile([float(n) for n in range(1, 21)], 0.95) == 19.0
    assert percentile([float(n) for n in range(1, 101)], 0.95) == 95.0


def test_the_table_has_one_row_per_model():
    report = summarize("groq/x", [record(made("plan", "answered", ("answered", 1.5)))])
    table = format_table([report])
    assert table.splitlines()[-1] == (
        "| groq/x | 1 | 1/1 | 0 | 0 | 1.5 | 1.5 | 1.0 | 0 | 0 | 1/1 | 1/1 |"
    )


# --- one model alone ----------------------------------------------------------------


def test_every_job_gets_the_one_model_with_nothing_behind_it(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    clients = single_model_clients("groq/some-model", transport=lambda *a: b"")
    assert set(clients) == set(JOBS)
    assert all(
        [c.model for c in client.clients] == ["some-model"]
        for client in clients.values()
    )


def test_episodes_are_run_and_recorded_for_each_fault_and_seed():
    records = run_model(
        "scripted",
        scripted_models,
        faults=["bearing_degradation"],
        seeds=[6],
        clock=lambda: 0.0,
    )
    [only] = records
    assert (only.fault, only.seed, only.resolved, only.action_correct) == (
        "bearing_degradation",
        6,
        True,
        True,
    )
    assert only.diagnosis == "the spindle bearing on CNC-02 is wearing"
    assert len(only.calls) == 14 and all(c.outcome == "answered" for c in only.calls)


def unreachable_clients():
    def transport(url, headers, body, timeout):
        raise urllib.error.URLError("no network in tests")

    client = ChatClient("https://example.test", "k", "down/model", transport=transport)
    return {job: FallbackClient([client], sleep=lambda s: None) for job in JOBS}


def test_a_model_that_never_answers_ends_each_episode_as_unavailable():
    records = run_model(
        "down/model",
        lambda: ModelPolicy(unreachable_clients(), research_tools()),
        faults=["false_alarm"],
        seeds=[0, 2],
        clock=lambda: 0.0,
    )
    report = summarize("down/model", records)
    assert report.model_unavailable == 2 and report.answered == 0
    assert report.outages == 4  # each episode's first question: asked, then retried
    assert report.median_seconds is None


def test_the_command_writes_the_table_and_the_raw_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(
        benchmark, "single_model_clients", lambda model: unreachable_clients()
    )
    assert (
        benchmark.main(
            [
                "down/model",
                "--faults",
                "false_alarm",
                "--seeds",
                "0",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    table = (tmp_path / "results.md").read_text(encoding="utf-8")
    assert "| down/model | 1 | 0/1 |" in table
    [line] = (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    saved = json.loads(line)
    assert saved["termination_reason"] == "model_unavailable"
    assert saved["calls"][0]["attempts"][0]["outcome"].startswith("the model service")


@pytest.mark.parametrize("bad", ["nobody/model", "groq"])
def test_an_unknown_model_is_refused_before_anything_runs(bad):
    from capstone.providers.chat import ModelError

    with pytest.raises(ModelError):
        single_model_clients(bad)
