# Full investigation: safe live lifecycle for the industrial console

**Scope:** Read-only, deep investigation progress for the existing React + FastAPI
managed-run UI. This is deliberately stacked **#293 -> #294 -> this PR**.
No role Access redesign, triage algorithm change, model provider switch,
CNC controls, hosted worker extraction, or deployment migration.

## Why a separate PR

- #293 established final result and separate triage/deep completed audits.
- #294 added generic typed Graph state progress, safe triage measurements,
  persistent snapshots, and terminal/reconnect hardening.
- This change adds **deep-only lifecycle detail** and a **durable observed
  transition ledger** without copying the earlier features.

## Existing PydanticAI/Pydantic Graph contracts

The project already uses `pydantic_graph.beta.GraphBuilder` and
`InvestigationState` for stage orchestration. The managed Python worker
already registers a `watch(state)` callback when it calls `run_episode`.
The watcher captures stage boundaries without introducing a new model call or
replacing any Graph node.

Following Pydantic's [Graphs documentation](https://pydantic.dev/docs/ai/graph/graph/),
this PR keeps Graph state and dependency injection under the existing
execution graph. A Pydantic v2 `SafeDeepSignals` projection converts
structured `InvestigationState` fields to **enum statuses, booleans and
counts**. A second Pydantic model `SafeDeepCheckpoint` validates the
compact stage-transition record. No generic `state.model_dump()` is sent
to the UI. Logfire or provider-level capture is **not** enabled because it
could contain private prompts or machine data.

## Source-to-frontend mapping

| Source state | Safe live output | Frontend interpretation |
| --- | --- | --- |
| `state.stage` (deep only) | stage, iteration, tool/evidence/hypothesis/decision counts, journal sequence | Observed transition in chronological order; stages can repeat |
| `state.critique.outcome` | enum critic status | Critic outcome; absence means not recorded |
| `state.recheck.outcome` | enum follow-up status | Follow-up status; no private question text |
| `state.critic_tool_calls_used`, `pruned_candidates`, `hypothesis_revisions` | integer counts | Critic/revision activity, not correctness |
| `state.conclusion` | assessment, recommendation, count of cited evidence IDs | Provisional agent conclusion without diagnosis text |
| `state.proposed_action.status` | enum proposal/review status | A proposal is not approval or execution |
| `state.action_started_tick`, `action_finish_tick` | booleans | Simulator action started/finished; not an OEM action |
| `state.verification.outcome`, `checked_tick` | enum, observed flag, tick | Observed or inconclusive verification; no inferred success |

The final diagnosis, citation text, action details and verification evidence
remain accessible only through the previously authorized completed audit
(#293). The stage journal stays metadata-only.

## Persistence and backward compatibility

`SimulatorRuns._emit` validates each deep watcher snapshot and, in the
existing atomic run/event transaction, stores the most recent **48 observed
stage transitions** in `snapshot.progress.deep_timeline` and the full
`deep_transition_total` count. Each checkpoint references the same
`run_events.seq` as the event journal; consecutive observations of the
same stage do not duplicate a transition. Stage revisits after another
stage do create a new transition. A terminal run remains immutable to late
watcher writes, and review/completion does not erase the ledger.

A dropped watcher update cannot be reconstructed as a stage transition.
The frontend therefore shows *observed* stages, no fabricated 100% progress,
and an explicit no-history message for legacy or dropped updates.
It does not infer Graph branches merely from the set of possible stages.

## Verification gates

- Test typed projection on realistic deep state doubles; unknown outcome
  strings are not emitted and additional private fields are forbidden.
- Test no prompts, API keys, provider responses or simulator answer keys
  cross the public progress contract.
- Test repeated stage updates, stage revisits, review requests, completion,
  restart, SSE replay and late-event rejection.
- Test journal truncation (48 entries) while preserving the transition count.
- Run local API privacy tests, React build/navigation, Ruff check+format,
  offline full suite/SNAP and PostgreSQL journal CI against the exact head.
- Run an authorized **deep-only** simulator episode and a triage-to-deep
  escalation in the browser on Local and Render, including reconnect and
  review, before production sign-off. No real-machine write is permitted.

**Not covered:** Separate two-service Render worker deployment (see #292/
#298), managed-run model-call timeline (see #297), full free-text hypothesis
streaming, raw model prompts, private audit dumps, OEM/Siemens controller
actions or hidden evaluation scores.
