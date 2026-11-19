# One-switch deterministic triage Graph profile — implementation contract (before code)

## Dependency and semantics
**Stacked on #299 → #295.** `TRIAGE_RUN_MODE=deterministic` is an explicit **triage-only** execution profile, not another LLM or a replacement Graph. It **wins over all individual triage stage settings**, even if contradictory values were configured. `TRIAGE_RUN_MODE=custom` (default) preserves direct individual-knob behavior for controlled A/B comparison. The profile never changes a subsequent deep investigation. **Conclude remains the existing model-backed `policy.conclude` stage** (historical Graph state.stage=`decide`).


## Activation precedence (explicit caller wins)
`TRIAGE_RUN_MODE=deterministic` turns on triage for an unspecified `run_episode(..., triage=None)` even when the legacy `TRIAGE=off` setting is unchanged. It never overrides an explicit `triage=False` or an API deep-only request. Explicit `triage=True` runs triage; `TRIAGE_RUN_MODE=custom` retains the legacy `TRIAGE` default for an unspecified request. This precedence is tested separately from the per-stage control-plane override.

## Exact precedence and per-stage behavior
| Stage | deterministic profile effective behavior |
| --- | --- |
| Observe | Existing read-only qualified packet; mandatory clock/data-source checks; `TRIAGE_PACKET=on`, `TRIAGE_OBSERVE_CALLS=separate`, no model |
| Manual | Existing authorized read-only manual lookup if configured; no generated plans/model calls; no change to OEM permissions |
| Plan | Fixed questions/predicates, `TRIAGE_PLAN=fixed`, no LLM |
| Investigate | Pydantic Graph deterministic read selector + precommit evidence validation; `TRIAGE_INVESTIGATE=deterministic` |
| Hypothesize | Versioned, typed, unscored deterministic candidate packet; `TRIAGE_HYPOTHESIZE=deterministic` |
| Test / Decide / Interpret | Deterministic Test scheduling, no model-written tests, `TRIAGE_EVIDENCE_TESTS=on`; no Decide, Interpret or ToT revaluation model |
| Critique / Recheck / ToT reinstate | Explicit no-op in triage profile, no critic model or policy follow-up; typed Graph edges remain |
| Conclude | **One existing model-backed Conclude** with same provider routing, answer validation, abstention/escalation, timing limits and triage report |
| Propose / Execute / Verify | Existing triage read-only/finish behavior; no simulated or Siemens write action in triage |
| Optional deep escalation | `TRIAGE_THEN_DEEP` remains as configured; deep uses original unmodified model/critic/configuration |

## Variables and implementation
- Add typed, central `TriageExecutionProfile` and `Settings.triage_run_mode` (alias `TRIAGE_RUN_MODE`). Resolve raw `Settings` once to effective triage fields; do **not** mutate deep/global `Settings` settings or use unchecked `model_copy(update=...)`.
- Cross-setting Pydantic validators must allow conflicting raw knob values **only when the deterministic profile supersedes them**, while maintaining strict validation for custom mode.
- Apply profile in both `episode.run_triage_then_deep` and `recorded_investigation.run_recorded_investigation`, and guard direct `run_investigation` graph entry as a second line of defense. Preserve approved tool catalogs, channel allowlists and source/time freshness gates; these **cannot** be overridden by configuration.
- Track effective profile name on typed investigation state for audit and safe UI display; keep older serialized records readable.
- Preserve the existing `GraphBuilder` and `StepContext` stages/edges; no new `pydantic_ai.Agent`, model-backed planning or graph-specific persistence. Pydantic docs: https://pydantic.dev/docs/ai/graph/builder/, https://pydantic.dev/docs/validation/latest/concepts/validators/, https://pydantic.dev/docs/validation/latest/concepts/models/.

## Three verification passes
1. **Control-flow audit:** simulate conflicting env knobs, assert only Conclude calls the model in deterministic triage, compare custom and deep behavior, and cover timeouts/no-data/no-candidates.
2. **Variable/data-flow audit:** assert typed resolved profile propagates to all run entrypoints, state/deps, per-stage budgets, clock/source gating and stop reasons. No cross-talk into deep or machine control.
3. **Reliability/security/UI audit:** old tests and serializations, live effective-mode display, no secret/raw/ground-truth exposure, no model fallback after invalid inputs; run Ruff/pytest/frontend/CI/SNAP/inventory as available and record results.

## Non-goals
No change to LLM model/provider selection for Conclude; no forcing `TRIAGE_THEN_DEEP` off; no new autonomous actions; no production Siemens control or telemetry ingestion; no claim of accuracy calibration without comparative evaluation.

## Merge
Draft/open only, **do not merge**. Merge dependency order #295 → #299 → this PR after tests and reconciliation with the separate #293/#294/#296 live-progress stack.