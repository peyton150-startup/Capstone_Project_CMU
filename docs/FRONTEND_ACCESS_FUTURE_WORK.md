# Future Work — Role-aware API Access (not implemented)

**Status:** Future work only. Logged 2026-11-17 after local simulator testing.
**Priority:** Medium (operator ergonomics and credential correctness).
**Scope owner:** React industrial console + FastAPI authentication contract.
**Non-goal of the live-progress PR:** No role credential selector, token storage
change, authentication-route change, permission expansion or new authority.

## Current behavior and the observed problem

The industrial console currently has one per-backend, in-memory
`Session token` field. The FastAPI server deliberately requires three distinct
secrets when simulator runs are enabled:

- `CAPSTONE_UI_TOKEN`: viewer/read access.
- `CAPSTONE_UI_RUN_TOKEN`: operator/read plus simulator-run submission.
- `CAPSTONE_UI_REVIEW_TOKEN`: reviewer/read plus simulator approval/rejection.
- Optional `CAPSTONE_UI_EVALUATOR_TOKEN` is independently gated.

`GET /api/v1/capabilities` accepts any recognized secret. It does **not**
prove that the submitted credential is authorized for
`POST /api/v1/lab/runs`. As a result, a user can see `Access set` and an
apparently healthy UI but receive a `403` for a simulator action.
Tokens are held in browser memory per selected local/Render backend; a page
reload clears them. Clipboard-based manual workflows can overwrite a token
with copied shell commands.

## Proposed design (do not implement in this PR)

1. Make the Access dialog explicitly select a **viewer**, **operator**, or
   **reviewer** role (and evaluator where enabled), with one masked input per
   permitted role. Keep credentials in memory, separated by backend and role;
   never persist credentials in localStorage/sessionStorage, URL or logs.
2. Show which role is actively used for a **read**, **launch**, **review** or
   **evaluation** request, with an unobtrusive label. No auto-elevation:
   an authorized operator credential must be deliberately selected to launch.
3. The UI may display non-sensitive capability and permission status, but
   must distinguish `authenticated` from `authorized for the requested
   action`. Do **not** infer a role from a successful read-only response.
4. Preserve the existing FastAPI fail-closed checks
   (`require_role('operator')`, `require_role('reviewer')`, evaluator gates),
   separate local/Render token boundaries, pilot read-only restrictions and
   no-physical-machine-control policy.
5. Prefer a reviewed, narrowly scoped, authenticated **role verification**
   contract if needed; it must not enumerate secrets, leak matching
   credentials or bypass any permission check. Never parse a secret to
   infer roles or make the frontend the source of authorization truth.
6. Provide actionable errors when the *action* is denied: distinguish
   missing/unrecognized token (401), recognized but unauthorized role (403),
   and missing run ID (404) without revealing backend secrets.

## Acceptance criteria for a future focused PR

- Viewer can read approved data but cannot submit or approve a run.
- Operator can read and submit, but cannot approve/reject.
- Reviewer can read and approve/reject, but cannot launch.
- Switching role, backend, tab or workspace does not accidentally reuse
  the wrong credential; restarting the page requires reauthentication.
- Pilot mode offers no execution/approval controls.
- All credentials are redacted from app logs, network response bodies,
  persisted browser storage, screenshots and error messages.
- Simulated local and Render deployments exercise 200/202/401/403/404
  behavior, including an in-flight review, without changing API security.
- Automated React and FastAPI regression checks cover expected denial
  paths, cleanup and stale requests; final field security review precedes
  production rollout.

## Related work

The separate **managed investigation live-progress** PR improves the
read-only run detail page: per-phase counts, current step, stage journal,
diagnostics and final-audit distinction. It does not alter any role or
credential behavior. Existing users must still provide the operator
credential to launch a simulator run and the reviewer credential for
simulator-only reviews.
