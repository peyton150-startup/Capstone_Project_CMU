# Deterministic Hypothesize hardening — implementation contract (authored before code)

## Dependency and non-goals
**Base #295**, which makes triage fixed Plan and deterministic Investigate/Decide the defaults. Keep #295 and #296 open and unmodified. This PR ONLY upgrades triage Hypothesize/Test candidate compilation, its safe metadata, and dedicated tests/docs. **Conclude remains model-backed**, deep investigations remain unchanged, and an unscored candidate is never a confirmed diagnosis, confidence or permission for no-action/plant intervention.

## Planned implementation (P0-P2)
- **P0**: Make `TRIAGE_HYPOTHESIZE=deterministic` the default (Pydantic Settings and `.env.example`), retain `model` as an explicit experimental comparison arm; retain existing Pydantic cross-field guards and add runtime fail-closed checks against incompatible fixed-plan/evidence/catalog inputs. Do not add any model fallback.
- **P1**: Introduce an explicit typed `TriageHypothesisPacket` (Pydantic v2) with version, immutable/source-cutoff context, unscored candidates and selected canonical Test requirement IDs. Validate that candidate IDs, families, evidence provenance, missing/unsupported status, requirement references, and Test read eligibility are internally consistent **before** committing state. Existing state/experiment records remain backwards compatible. Tighten candidate `family` to a known `Literal` rule registry; never use `model_copy(update=...)` for untrusted fields because Pydantic does not validate those updates.
- **P1**: Version the stable rule catalog, preserve deterministic replay and inject no external provider calls. Preserve the fixed Test scheduling and redacted logging. Provide a safe, bounded hypothesis summary for the managed simulator progress contract, with frontend support for candidate IDs/family/status/coverage metrics only (no raw explanations, numeric telemetry, secrets, fault labels or provider messages).
- **P2**: Add narrowly grounded candidate checks for multi-machine/coverage-gap observations, retaining explicit unavailable/unknown outcomes. These are checkable *possibilities*, never claimed causes. Add representative missing/delayed/partial telemetry, unsupported channels, multiple-machine context, and unchanged-repeatability regression tests; preserve source boundary. Provide comparison guidance against `TRIAGE_HYPOTHESIZE=model`; do not claim calibration parity without evaluation runs.

## Pydantic AI/Graph design
Use the *existing* `GraphBuilder` and `StepContext[state,deps,input]` Hypothesize node, where Python/Pydantic contracts perform deterministic compilation and conditional routing. No separate agent/LLM, no new graph framework, no hidden ground truth; the current Graph/SQLite or PostgreSQL journal owns persistence. Docs: https://pydantic.dev/docs/ai/graph/builder/ and https://pydantic.dev/docs/validation/latest/concepts/validators/.

## Three review passes after implementation
1. Configuration, graph route, side-effect and deep-path regression; verify zero Hypothesize/revalue model calls and model Conclude preserved.
2. Contract/variable audit: every source, ID, candidate, requirement, timestamp/cutoff and Test target; failures fail closed with no invented confidence.
3. Frontend/public projection, journal and backward-compatibility/security audit; automated CI, frontend tests, replay and source-matched inventories. Any checks not run must be disclosed honestly.

## Merge
Open as draft; do not merge. Merge/rebase only after #295 and any conflicting upstream live-progress PRs reconcile.

## Scope boundary
The single later triage-run profile override is implemented in the separate follow-up PR, not here.
