# Frontend connection ledger (follow-up to PR #321)

Date: 2026-11-19. Branch `feature/frontend-connection-states`, cut from
`origin/main` at `a650ddcb` (2026-11-19 10:12 -0500). PR #321's head when it
was read: `ce98ff24`.

PR #321 lists 43 placements of the shared message "… is not connected yet",
produced by 42 `Unavailable` call sites (`MachineLine` appears on Overview and
Machines). This ledger records what each placement actually meant, what was
changed and how it was checked. Its main finding: almost none of the 43 were
missing integrations. The single message covered loading, failed requests,
missing credentials, unconfigured files, endpoints the API does not
implement, pilot gates, runs that had not reached a stage, and sources that
were connected but returned no records.

## What changed

- `frontend/src/sourceState.mjs` (new, plain JS so `node --test` checks it):
  `decodeListResponse` validates `{availability, items}` at runtime;
  `describeSourceState` turns loading, error/status, availability and record
  count into one state (precedence: records → error → loading → availability);
  `problemForStatus` gives fixed messages for 401/403/404/409/422/503;
  `timeAxis` positions chart samples by timestamp; `selectTriageReport` and
  `reportHasAcceptedConclusion` drive the Rapid Triage report.
- `ui.tsx`: new `SourceState` component; `Unavailable` kept for deliberate
  gates only ("… is not connected", no "yet"); `TrendChart` spaces points by
  source timestamp and says so, falling back to recorded order with a caption
  when timestamps are invalid, equal or out of order; `MachineLine` takes the
  source facts.
- `api.ts`: `getJson` throws `ApiProblem` with the HTTP status and a fixed
  message, and turns malformed JSON into a contract error. `useResource`
  returns `status`. The request key is unchanged (an existing test pins it).
- `pageData.ts`: hooks decode list responses and return `source` facts.
  `availability` stays `null` until a response is decoded, so a failed or
  pending request is no longer reported as `not_configured`. `useRecording(true)`
  does not request the Siemens capture in the simulator workspace.
- `types.ts`: `Availability` gains `not_recorded`, `not_available_in_pilot`,
  `synthetic`, `unrecognized`; `ApiResource` gains `status`.
- Pages: every data-backed placement uses `SourceState`; Rapid Triage gets
  `ManagedTriageReportPicker`; `TriageReportView` hides the diagnosis unless
  the outcome is `model_conclusion`; Compare requires the investigation path to
  match as well as scenario and seed.

No Python, API contract, persistence, worker or graph code changed.

## Dispositions

Key: **C** connected and verified · **P** already connected; presentation
corrected · **E** correct empty state · **R** correctly restricted ·
**N** not configured; setup dependency verified · **G** not implemented;
documented architectural gap · **B** blocked by an unavailable external
source.

| # | Route → panel (label) | Source (endpoint / artifact) | Before | Now | Disp. |
|---|---|---|---|---|---|
| 1 | `/overview` → Machine lineup (`MachineLine`) | `GET /machines` | generic | `SourceState`; simulator: "not configured" with the API's own message | N (sim), P (pilot) |
| 2 | `/overview` → Recent activity | Siemens capture health | showed Siemens events in the simulator workspace | simulator: "No simulator activity feed"; pilot: `SourceState` | R (sim), P (pilot) |
| 3 | `/investigations` → Investigation history | `GET /investigations` (`CAPSTONE_UI_INVESTIGATIONS`) | generic; error shown beside it | `SourceState` (error, loading, not_configured, file_missing, unsupported_for_pilot) | N |
| 4 | `/investigations/triage` → Typed triage report | `GET /lab/runs` → `snapshot.triage_report` | claimed a read model was missing | **report picker over persisted managed-run reports** | C (mocked browser + unit tests) |
| 5 | `/investigations/triage` → Managed triage reports | `GET /lab/runs` | generic | `SourceState` | P |
| 6 | `/investigations/triage` → Recorded triage cases | `GET /investigations` | generic | `SourceState` | N |
| 7 | `/investigations/deep` → Deep investigation records | `GET /investigations` | generic | `SourceState` | N |
| 8 | `/investigations/review` → Pending simulator reviews | `GET /simulator/reviews` | generic | `SourceState` (not_integrated without managed runs; empty queue reads as empty) | P |
| 9 | `/investigations/:id` → Evidence payload | `GET /investigations/{id}` | generic | "No evidence recorded" (case loaded, list empty) | E |
| 10 | `/investigations/:id` → Hypothesis history | same | generic | "No hypotheses recorded" | E |
| 11 | `/machines` → Machine inventory | `GET /machines` | generic | `SourceState` | N (sim), P (pilot) |
| 12 | `/machines` → Machine lineup (`MachineLine`) | `GET /machines` | generic | `SourceState` | N (sim), P (pilot) |
| 13 | `/signals` → Signal browser | Siemens capture | listed Siemens signals in the simulator workspace | simulator: "No simulator signal source"; pilot: `SourceState` | R (sim), P (pilot) |
| 14 | `/signals` → Signal history | `GET /signals/{id}/samples` | generic even when a request failed | error / loading / chart; "No signal selected" | P |
| 15 | `/recordings` → Siemens recording | `CAPSTONE_UI_CAPTURE` | generic | `SourceState` with the API's message (not_configured / file_missing) | N |
| 16 | `/recordings` → Approved signal inventory | same | generic | empty-in-capture vs. no capture | E |
| 17 | `/recordings` → Collector event history | same | generic | empty-in-capture vs. no capture | E |
| 18 | `/recordings` → MTConnect v1 capture | `CAPSTONE_UI_MTCONNECT` | generic | preview notice or `SourceState` | N |
| 19 | `/recordings` → MTConnect signal inventory | same | generic | "No MTConnect signals recorded" | E |
| 20 | `/recordings/quality` → Signal qualification | Siemens capture | generic | `SourceState` | N |
| 21 | `/recordings/sessions` → Session inventory | Siemens capture | generic | `SourceState` | N |
| 22 | `/recordings/sessions` → Session markers | Siemens capture | generic | `SourceState` | N |
| 23 | `/lab` → Validated per-run settings | `GET /lab/runs/configuration` | generic | loading / request failure / not returned | P |
| 24 | `/lab` → Managed simulator runner | capability `CAPSTONE_UI_SIM_RUNS` | generic | kept as a deliberate gate (`Unavailable`) | R |
| 25 | `/lab/runs` → Managed run history | `GET /lab/runs` | generic | `SourceState` (not_integrated vs. no runs) | P |
| 26 | `/lab/runs` → Run history (offline) | `GET /evaluations` | generic; 403 shown beside it | `SourceState` ("authorization required") | R / N |
| 27 | `/lab/runs/:id` → Managed simulator run | workspace/preview gate | generic | kept as a deliberate gate (`Unavailable`) | R |
| 28 | `/lab/runs/:id` → Evidence tab (Source evidence) | phase audit | generic | "No source evidence recorded" for that phase | E |
| 29 | `/lab/runs/:id` → Hypotheses tab | phase audit | generic | "No recorded hypotheses recorded" for that phase | E |
| 30 | `/lab/runs/:id` → Trace tab (Decision trace) | phase audit | generic | "No decision trace recorded" | E |
| 31 | `/lab/runs/:id` → Run diagnostics | `GET …/observability` | generic | `SourceState` (loading, failure, not_recorded, empty) | P |
| 32 | `/lab/runs/:id` → Stage updates | SSE `…/events` | generic | "Connecting…" / "No stage updates yet (stream: …)" | P |
| 33 | `/lab/runs/:id` → Evidence citations (triage report) | `snapshot.triage_report.findings` | generic | "This report cites no findings" | E |
| 34 | `/lab/evaluations` → Evaluation results | `GET /evaluations` | generic | `SourceState` | R / N |
| 35 | `/lab/evaluations` → Evaluator scorecards | `GET /evaluations/scorecards` | generic | simulator-only notice or `SourceState` | R |
| 36 | `/lab/compare` → Comparison | `GET /evaluations` | generic | "needs two records" (one present) or `SourceState` | R / N |
| 37 | `/knowledge/manuals` → Manual sections | `GET /knowledge/manuals` | generic, also before any search | `SourceState`; "no section matches …" | P |
| 38 | `/knowledge/memory` → Authorized episodic memories | `GET /knowledge/memories` | generic | `SourceState` | P / N |
| 39 | `/knowledge/memory` → Promotion review history | `GET /knowledge/promotions` | generic | simulator-only notice or `SourceState` | R |
| 40 | `/system` → System status | `GET /system` | generic | loading / failure | P |
| 41 | `/system/observability` → Live collector event stream | Siemens capture | generic | `SourceState` | N |
| 42 | `/system/audit` → Collector audit | `GET /system/audit` | generic | `SourceState` | N |
| 43 | `/system/settings` → Settings read model | `GET /settings/effective` | generic, also when the filter matched nothing | "No setting matches the filter" vs. `SourceState` | P |

Count: 43 placements; 3 remain deliberate `Unavailable` gates (pilot typed
triage report, managed run outside the simulator, runner capability).

## Overlap with open pull requests

Checked 2026-11-19. None was merged or cherry-picked; this branch is based on
`main` without them.

| PR | Overlapping files here | Effect |
|---|---|---|
| #318 per-role tokens | `api.ts`, `pageData.ts`, `pages/managed.tsx`, `pages/research.tsx` | Textual conflicts likely. Neither change alters the other's meaning: this branch never reads `token` differently and adds no credential storage. Whichever merges second should pass `tokenFor(role)` where #318 does and keep `SourceState`. The request key is unchanged here, so #318's role-aware key wins. |
| #322 FORGE layout | none of its files except via `App.tsx`/`engineering.tsx` (this branch edits `engineering.tsx` only at four call sites) | Small conflict possible in `engineering.tsx`. |
| #316 run's own `evidence_tests` | none (Python) | Compare still cannot confirm per-run triage settings from evaluation rows; the page now says so. |
| #317 recorded detector, #320 unknown machine state | none | `MachineLine` already shows `unknown` as "Unknown"; the WARNING/FAULT split is not displayed anywhere on these pages. |
| #319 hosted worker hardening | none | System page unchanged apart from its empty/error state. |

## Verification

- `npm test`: 33 passed (22 existing + 11 in `tests/source-state.test.mjs`).
- `npm run build` (tsc + vite): passes.
- Browser (in-app, local dev server against `python -m capstone.api` with no
  sources configured and no token): clicked all 20 sidebar routes; every
  placement showed a specific state ("…: not configured", "…: not
  integrated", "…: authorization required") and none showed "not connected
  yet". Rapid Triage was checked with **mocked** `/api/v1/lab/runs` data for
  the three report outcomes: refused and no-answer reports show no diagnosis
  and no rating, even when the mocked refused report carried a diagnosis
  string. Phone width (375 px): no horizontal scroll.
- Not run: a live managed run, Render/hosted backends, PostgreSQL, any model.

## Not done (left for later, by design)

- A server-owned simulator machine inventory (placement 1/11/12): the API
  still has no live simulator machine source; inventing one from a run
  snapshot would mix historical and live state.
- Unifying general investigation history with managed runs: the two stay
  separate lists, and the Investigations page now points to Run history.
- Runtime decoders for the non-list contracts (run snapshot, system status,
  settings, triage report); only list responses are decoded.
- SSE journal parser hardening and its tests, review-desk reconciliation after
  a decision, and the PR #318 role-token merge: separate, smaller PRs.
