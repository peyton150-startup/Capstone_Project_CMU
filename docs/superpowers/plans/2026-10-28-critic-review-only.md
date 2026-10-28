# Critic, Review Only: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a critic stage, between `test` and `conclude`, that asks a second model to judge the two leading hypotheses and records its verdict without changing the run.

**Architecture:** A `Critic` class (`agent/critic.py`) asks one typed question through its own `FallbackClient` chain and keeps its own `ModelCall` records tagged `agent="critic"`. A new graph stage, `critique`, calls it with its own time window, pauses the investigation's deadline for the time it used, and writes a `CritiqueRecord` on the state. It does nothing when no critic is configured. The episode builds the critic from settings, and the experiment and EV1 records carry its record and calls.

**Tech Stack:** Python 3.11, Pydantic v2, pydantic_graph, pytest, the project's own `providers/chat.py` client.

**Spec:** `docs/superpowers/specs/2026-10-28-critic-review-only-design.md` (PR #104).

## Global Constraints

- The critic changes nothing in the run: not the hypotheses, the confidence, the conclusion, the recommendation or the proposal.
- The critic never sees hidden truth, the scenario, a run key or a score. It gets no tools: only their names and descriptions, as text.
- Its output is a belief, never evidence, and is never written to memory.
- `CRITIC` (`on`/`off`, default `off`); `CRITIC_MODEL` (comma-separated chain, no default); `CRITIC_SECONDS` (default `40`, must be > 0).
- The critic's chain is `CRITIC_MODEL` only: the shared `FALLBACK_MODEL` chain is **not** appended.
- A critic `ModelError` never ends the run.
- The investigation's deadline moves back by exactly the seconds the critic used.
- No Anthropic or OpenAI model, SDK or key name anywhere. Tests need no key: fake clients only.
- Every new test file is added to a group in `.github/test_groups.py`.
- The prompt names no project fault kind and no fault signature (the rule kept for `TOOL_DESCRIPTIONS`).

## Review Focus

1. **A reply citing an evidence id that was never gathered:** refused as `invalid_reply`, the critique recorded with no result, and the run goes on. (Task 2)
2. **`favoured` names a hypothesis the critic was not shown:** refused the same way. (Task 2)
3. **`CRITIC=on` with no `CRITIC_MODEL`:** fails before the first case runs, with a message naming `CRITIC_MODEL`, not as an outage in every case. (Task 1)
4. **Only one hypothesis, or a confidence tie:** with one, the critic is shown that one. With a tie, the first in the list wins, the same rule as `leading_hypothesis`. (Task 2)
5. **Critique starts after the deadline has already passed:** the critic still runs in its own window, and the time left stays 0, not negative. (Task 3)

---

### Task 1: Settings and the critic's client

**Files:**
- Modify: `capstone-code/capstone/settings.py` (beside `fallback_model`, and `fallback_models`)
- Modify: `capstone-code/capstone/providers/chat.py` (after `clients_for_jobs`)
- Test: `tests/test_settings.py`, `tests/test_chat_client.py`

**Interfaces:**
- Produces: `Settings.critic: bool` (alias `CRITIC`, default `False`); `Settings.critic_model: str | None` (alias `CRITIC_MODEL`, blank means unset, like the other `_optional` fields); `Settings.critic_seconds: float` (alias `CRITIC_SECONDS`, default `40.0`, `gt=0`); `critic_models(settings) -> tuple[str, ...]` (split on commas, trimmed, no repeats, like `fallback_models`); `critic_client(settings=None, *, transport=urllib_transport) -> FallbackClient` (one `client_for` per model in `critic_models`, `retries=settings.model_retries`, `max_seconds=settings.critic_seconds`; raises `ModelError("set CRITIC_MODEL ...")` when the chain is empty).

- [ ] **Step 1: Write the failing tests**

`test_settings.py`:
- `test_critic_settings_default_off`: `Settings()` gives `critic is False`, `critic_model is None`, `critic_seconds == 40.0`.
- `test_critic_on_and_chain`: with env `CRITIC=on` and `CRITIC_MODEL="mistral/ministral-14b-2512, cohere/command-a-03-2025, mistral/ministral-14b-2512"`, the result has `critic is True` and `critic_models(s) == ("mistral/ministral-14b-2512", "cohere/command-a-03-2025")`.
- `test_critic_seconds_must_be_positive`: `CRITIC_SECONDS=0` raises `ValidationError`.

`test_chat_client.py`:
- `test_critic_client_uses_only_its_chain`: settings with the two-model `CRITIC_MODEL` and `FALLBACK_MODEL="cloudflare/x"`. `[c.model for c in critic_client(s, transport=fake).clients] == ["ministral-14b-2512", "command-a-03-2025"]`, and `max_seconds == 40.0`.
- `test_critic_client_needs_a_model`: `CRITIC_MODEL` unset gives `pytest.raises(ModelError, match="CRITIC_MODEL")`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_settings.py tests/test_chat_client.py -k critic -q`
Expected: FAIL (`critic` attribute and `critic_client` do not exist).

- [ ] **Step 3: Add the three fields, `critic_models`, and `critic_client`**

`critic_model` joins the `blank_is_missing` validator list. `critic_client` reuses `client_for` per reference, so per-provider caps (Cohere 8,192) still apply.

- [ ] **Step 4: Run them and see them pass**

Run: `uv run pytest tests/test_settings.py tests/test_chat_client.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add capstone-code/capstone/settings.py capstone-code/capstone/providers/chat.py tests/test_settings.py tests/test_chat_client.py
git commit -m "feature: critic settings and its own model chain"
```

### Task 2: The critique contract and the critic's question

**Files:**
- Modify: `capstone-code/capstone/agent/artifacts.py` (new contracts, beside `VerificationCheck`)
- Create: `capstone-code/capstone/agent/critic.py`
- Test: `tests/test_critic.py` (new; add `"critic"` to the `"Model policy"` group in `.github/test_groups.py`)

**Interfaces:**
- Consumes: `Client` protocol and `ModelCall` from `agent/model_policy.py`; `evidence_section`, `tool_list` from the same module; `invalid_outcome` from `providers/chat.py`.
- Produces, in `agent/artifacts.py`:
  - `Objection(Contract)`: `kind: Literal["contradiction", "unsupported_claim", "missing_evidence", "alternative", "overconfidence"]`, `text: str` (min length 1), `evidence_ids: tuple[str, ...] = ()`.
  - `CritiqueResult(Contract)`: `favoured: str` (a shown hypothesis id, or `"none"`), `why: str`, `discriminating_check: str`, `objections: tuple[Objection, ...] = ()`, `verdict: Literal["object", "no_objection"]`, `favoured_confidence: float` (0 to 1), `supports_action: bool`. Every field gets a `Field(description=...)` stating its exact meaning (the client sends the schema with the question). `favoured`'s description must say: better supported than the other, not proven beyond doubt; `none` only if the evidence supports neither.
  - `CritiqueRecord(Contract)`: `outcome: Literal["answered", "invalid_reply", "no_answer"]`, `result: CritiqueResult | None = None`, `shown_hypotheses: tuple[str, ...]`, `seconds: float` (≥ 0).
- Produces, in `agent/critic.py`:
  - `top_two(state) -> list[Hypothesis]`: by confidence, highest first, ties kept in list order, at most 2.
  - `critique_view(state, tools: Sequence[ToolSpec]) -> str`: the anomaly line, `evidence_section(state)`, the shown hypotheses (id, confidence, claim, supporting and contradicting ids, the format `render` uses), and `TOOLS THE AGENT CAN CALL (you cannot call them):` followed by `tool_list(tools)`. Nothing else from the state.
  - `CRITIC_SYSTEM: str`: the numbered procedure from the spec (1 read each hypothesis and what it cites; 2 list evidence for and against each; 3 pick the better-supported one; 4 name one call from the tool list that would separate them, with its arguments; 5 list objections, citing ids; 6 give the verdict). Cite only ids shown. Plus one neutral worked example, a short made-up case about something other than this factory's faults.
  - `class Critic`: `__init__(self, client: Client, tools: Sequence[ToolSpec])`, attribute `calls: list[ModelCall]`, method `review(self, state: InvestigationState, *, max_seconds: float) -> CritiqueResult`. It asks `client.ask(CRITIC_SYSTEM, critique_view(state, tools), CritiqueResult, max_seconds=max_seconds)` and appends a `ModelCall(job="critique", agent="critic", ...)` whatever happens (as `ModelPolicy._ask` does). After a reply it raises `ValueError` and marks the call `invalid_reply` (the same marking as `ModelPolicy._refuse`) if `favoured` is neither a shown id nor `"none"`, or any cited id (objections) is not in `state.evidence`.

- [ ] **Step 1: Write the failing tests** (`tests/test_critic.py`, with a fake client that returns a fixed `CritiqueResult` or raises)

- `test_top_two_by_confidence_ties_keep_order`: hypotheses H1 0.5, H2 0.7, H3 0.7 give `["H2", "H3"]`; a single hypothesis gives `["H1"]`.
- `test_view_shows_two_hypotheses_evidence_and_tools_only`: the view contains `H2` and `H3` and not `H1`, contains every evidence id, contains `get_readings`, and contains none of `bearing_degradation`, `bad_material_batch`, `wrong_setting`, `false_alarm`, `ground truth`, the run id or the investigation id.
- `test_system_prompt_names_no_fault`: `CRITIC_SYSTEM` contains none of the fault kinds in `capstone.faults.FAULT_KINDS`.
- `test_review_returns_and_records_a_critic_call`: an answered review returns the result, and `critic.calls[-1]` has `job == "critique"`, `agent == "critic"`, `outcome == "answered"`; the fake was given `max_seconds`.
- `test_review_refuses_unknown_favoured`: `favoured="H9"` raises `ValueError`, and the call is recorded `invalid_reply`.
- `test_review_refuses_ungathered_evidence`: an objection citing `"E99"` raises `ValueError`, and the call is recorded `invalid_reply`.
- `test_review_lets_model_error_up`: a fake raising `ModelError` makes `review` raise `ModelError`, and the call is recorded `no_answer`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_critic.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Add the contracts, `top_two`, `critique_view`, `CRITIC_SYSTEM` and `Critic`**

- [ ] **Step 4: Run them, and the group check**

Run: `uv run pytest tests/test_critic.py tests/test_model_policy.py -q && uv run python .github/test_groups.py check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add capstone-code/capstone/agent/artifacts.py capstone-code/capstone/agent/critic.py tests/test_critic.py .github/test_groups.py
git commit -m "feature: the critic's typed question and its records"
```

### Task 3: The critique stage in the graph

**Files:**
- Modify: `capstone-code/capstone/agent/loop.py` (`InvestigationDeps`)
- Modify: `capstone-code/capstone/agent/state.py` (`InvestigationState`)
- Modify: `capstone-code/capstone/agent/investigation.py` (new `critique` stage; `build_graph`)
- Test: `tests/test_agent_investigation.py`

**Interfaces:**
- Consumes: `Critic`, `CritiqueRecord`, `top_two` (Task 2).
- Produces: `InvestigationDeps.critic: Critic | None = None`, `InvestigationDeps.critic_seconds: float = 40.0`; `InvestigationState.critique: CritiqueRecord | None = None`; `critique(state, deps) -> None` in `investigation.py`. The graph edge `test → conclude` becomes `test → critique → conclude`, and `critique` is wrapped by `staged` like every other stage.

Behaviour of `critique`: if `deps.critic is None` or `state.hypotheses` is empty, return without writing anything. Otherwise time the call with `deps.clock`, and call `deps.critic.review(state.model_copy(deep=True), max_seconds=deps.critic_seconds)`. Answered gives `outcome="answered"`; `ModelError` gives `"no_answer"`; `POLICY_ERRORS` gives `"invalid_reply"`; neither error goes further. Then write `state.critique` with the shown ids and the seconds used. If `state.started_at` is set, add the seconds used to it, so `remaining_seconds` is unchanged across the stage.

- [ ] **Step 1: Write the failing tests** (use the existing scripted policy and provider fixtures in this file, and a fake critic object with `review` and `calls`)

- `test_no_critic_changes_nothing`: the same scripted run with `critic=None` gives `state.critique is None`, and the same conclusion and decisions as before this change.
- `test_critic_answer_is_recorded_and_changes_nothing`: with a fake critic answering `verdict="object"`, `state.critique.outcome == "answered"`, `state.critique.result.verdict == "object"`, and `state.conclusion` and `state.proposed_action` equal the `critic=None` run's.
- `test_critic_outage_does_not_end_the_run`: a fake critic raising `ModelError` gives `state.critique.outcome == "no_answer"`, `state.conclusion` is set by the policy (not `UNDETERMINED`), and `state.termination_reason != TerminationReason.MODEL_UNAVAILABLE`.
- `test_invalid_critique_does_not_end_the_run`: a fake raising `ValueError` gives `outcome == "invalid_reply"`, and the run goes on to conclude.
- `test_critic_time_does_not_shorten_the_investigation`: an injected clock moves 30 s during `review`. `state.remaining_seconds(clock())` just after the stage equals the value just before it, and `state.critique.seconds == 30`.
- `test_critic_after_deadline_still_runs`: started so that no time is left; the critic is still asked, and `remaining_seconds` stays `0.0`.
- `test_critic_skipped_without_hypotheses`: a run that goes `investigate → conclude` (nothing to explain) never calls `review`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_agent_investigation.py -k critic -q`
Expected: FAIL.

- [ ] **Step 3: Add the fields, the stage and the edge**

- [ ] **Step 4: Run the reasoning-loop and verification groups**

Run: `uv run pytest tests/test_agent_investigation.py tests/test_agent_loop.py tests/test_agent_verification.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add capstone-code/capstone/agent/loop.py capstone-code/capstone/agent/state.py capstone-code/capstone/agent/investigation.py tests/test_agent_investigation.py
git commit -m "feature: the critique stage, review only, in its own time"
```

### Task 4: Episode wiring, experiment records and the live view

**Files:**
- Modify: `capstone-code/capstone/episode.py` (`run_episode`, `EpisodeResult`)
- Modify: `capstone-code/capstone/experiment.py` (`run_experiment`, `ExperimentRecord`, `record_of`)
- Modify: `capstone-code/capstone/progress.py` (`ProgressView.__call__`)
- Test: `tests/test_episode.py`, `tests/test_experiment.py`, `tests/test_progress_view.py`

**Interfaces:**
- Consumes: `critic_client`, `Settings.critic`, `Settings.critic_seconds` (Task 1); `Critic` (Task 2); `InvestigationDeps.critic`, `InvestigationState.critique` (Task 3).
- Produces: `run_episode(..., critic: Critic | None = None)`. When `critic` is None and `settings.critic` is true, it builds `Critic(critic_client(settings), getattr(policy, "tools", research_tools()))` **before** the factory is built, so a missing `CRITIC_MODEL` fails before the case runs. It passes `critic` and `settings.critic_seconds` into `InvestigationDeps`. `EpisodeResult.critic_calls: tuple[ModelCall, ...] = ()`. `ExperimentRecord.critique: CritiqueRecord | None = None` (older files still read). `run_experiment` summarizes `policy.calls + result.critic_calls`, so the critic's questions appear in `model_calls` and in `agent_steps` with `agent="critic"`. `ProgressView` prints one line when `state.critique` first appears: `CRITIC (<outcome>): favoured <id>, <verdict>, check: <shortened discriminating_check>`.

- [ ] **Step 1: Write the failing tests**

- `test_episode.py::test_critic_off_by_default_keeps_results`: `run_episode` with a scripted policy and default settings gives `result.critic_calls == ()` and `result.state.critique is None`.
- `test_episode.py::test_critic_on_without_model_fails_before_running`: settings with `critic=True` and no `critic_model` give `pytest.raises(ModelError, match="CRITIC_MODEL")`, and no factory step was taken (the fake clock was never read).
- `test_episode.py::test_passed_critic_is_used`: passing a fake critic gives `result.state.critique.outcome == "answered"` and `result.critic_calls == tuple(fake.calls)`.
- `test_experiment.py::test_critic_questions_counted_and_tagged`: a record from a run with a fake critic has `agent_steps` containing a step with `agent == "critic"`, `kind == "model_question"`, `phase == "critique"`, and `record.critique` equal to the state's.
- `test_experiment.py::test_old_records_without_critique_still_read`: a stored record JSON without `critique` validates, with `critique is None`.
- `test_progress_view.py::test_critic_line_printed_once`: showing the same state with a critique twice prints the `CRITIC (` line once.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_episode.py tests/test_experiment.py tests/test_progress_view.py -k critic -q`
Expected: FAIL.

- [ ] **Step 3: Wire the episode, the records and the view**

- [ ] **Step 4: Run those files**

Run: `uv run pytest tests/test_episode.py tests/test_experiment.py tests/test_progress_view.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add capstone-code/capstone/episode.py capstone-code/capstone/experiment.py capstone-code/capstone/progress.py tests/test_episode.py tests/test_experiment.py tests/test_progress_view.py
git commit -m "feature: critic wired into episodes, records and the live view"
```

### Task 5: The EV1 report: the critic's verdict and pick per case

**Files:**
- Modify: `capstone-code/capstone/evals.py` (`EvalCase`, `report_of`, `automatic_labels`)
- Test: `tests/test_evals.py`

**Interfaces:**
- Consumes: `ExperimentRecord.critique` (Task 4); `propose` from `evaluation/auto_label.py`; `apply_label`.
- Produces: `EvalCase.critic_outcome: str | None`, `critic_verdict: str | None`, `critic_favoured: str | None` (all default `None`); `critic_pick_correct: bool | None = None`. `report_of(..., critic_labels: dict[str, Label] | None = None)`: when a record's run key has a critic label, `critic_pick_correct = apply_label(record.score, label.diagnosis).fully_right`. `automatic_labels` also returns critic labels: for each record whose critique was answered with `favoured != "none"`, `propose(run_key, <claim text of the favoured hypothesis>, client)`. The claim text comes from a new record field, `ExperimentRecord.critic_favoured_claim: str | None` (set in `record_of` from the state's hypothesis with that id). A proposal that `needs_review` is left out, so the pick stays unjudged.

- [ ] **Step 1: Write the failing tests**

- `test_report_shows_critic_fields`: a record with an answered critique gives a case with `critic_outcome == "answered"`, `critic_verdict == "object"` and `critic_favoured == "H1"`.
- `test_critic_pick_scored_from_its_label`: a critic label naming the true fault gives `critic_pick_correct is True`; naming another fault gives `False`; no label gives `None`.
- `test_records_without_critic_report_none`: an old record gives all four critic fields `None`, and the existing accuracy fields are unchanged.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_evals.py -k critic -q`
Expected: FAIL.

- [ ] **Step 3: Add the fields and the critic labels**

- [ ] **Step 4: Run the experiments group**

Run: `uv run pytest tests/test_evals.py tests/test_experiment.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add capstone-code/capstone/evals.py capstone-code/capstone/experiment.py tests/test_evals.py
git commit -m "feature: EV1 report carries the critic's verdict and scored pick"
```

### Task 6: Prompt check on made-up cases, docs, and the full check

**Files:**
- Modify: `docs/PROGRESS.md` (new row `C1`, critic review only, and a session note)
- Modify: `README.md` "Research basis" only if a paper shaped a change (AGENTS.md section 11 step 9)

- [ ] **Step 1: Live prompt check (one live run at a time, the developer's keys)**

Run the critic, through `Critic.review` and the configured chain, on 3 or 4 made-up states of different kinds (not known-answer or held-out seeds). Record per state: valid reply, seconds, `favoured`, and whether the check names a listed tool. Put the table in the PR description, marked live.

- [ ] **Step 2: Full local suite and lint** (the change touches the loop and records, so AGENTS.md section 11 asks for the full suite)

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run python .github/test_groups.py check`
Expected: all pass.

- [ ] **Step 3: `PROGRESS.md` row and note**

Row `C1`: taught yes, pre-check passed (2026-10-28), implemented yes, post "walkthrough owed". The note lists files, functions and tests, and that `.env.example` needs `CRITIC`, `CRITIC_MODEL`, `CRITIC_SECONDS` added by the developer if the session cannot edit it.

- [ ] **Step 4: Commit, push, open the PR** with the AGENTS.md section 11 description, then the pre-merge walkthrough before merging.
