# PR A — Haas VF-4 MTConnect transport and security (P0-01–06)

**DEPENDENCY: PR #307** (`integration/capstone-batch-300-305-20261118`); stack A → B → C → D. **DRAFT, DO NOT MERGE independently.** The initial commit is a durable implementation contract, NOT a production-ready adapter. Do not merge until #307 is reconciled, green, and this head is rebased/re-tested against its final commit.

## Goal / source truth
One explicitly approved Haas NGC machine, HTTP MTConnect GET only, no controller writes, no commands, no port scan, no cloud connection to CNC. Haas official NGC reference: https://www.haascnc.com/service/online-manuals/next-gen-control-electrical---service-manual/ngc---machine-data-collection.html . Documented GET endpoints `/probe`, `/current`, `/sample` on TCP 8082; model-specific URL paths; recommended NGC 100.20.000.1200+, machine-name '/' case 100.24.000.1200+. Actual controller, endpoint, identity and firmware must be verified with technician. CHC/RS-232 and MDC Q/E are separate future protocols, never guessed from VF-4 model.

## Implementation tasks
- [ ] Inspect #307 and root AGENTS.md, old collector and privacy/pilot_preflight before each small edit.
- [ ] Pydantic v2 strict `HaasConnectionProfile` and `HaasPreflightReport`, isolated from global Settings; explicit consent, one pinned IP/port/path, machine ID, fields, approvals, interval, output, retention. Validate config before network IO.
- [ ] No automatic endpoint guessing, redirects, environment proxies, alternate hosts, public egress or broad discovery. Resolve/verify approved destination, verify MTConnectDevices probe identity and scoped data items; fail closed.
- [ ] Strict, bounded HTTP response handling and XML size/structure checks; MTConnect Error support; validate nonnegative/monotonic instance/header/observation sequences, prevent non-progressing sample pagination, preserve gap evidence; no invented values.
- [ ] Enforce request rate even during backlog drain; finite retries/backoff, timeout, cancellation, memory/storage bounds.
- [ ] Durable atomic resume/checkpoint design coupled to persisted accepted observations; explicit restart/gap semantics and idempotent replay. Avoid false `stopped` on crash.
- [ ] No unapproved field acquisition. If MTConnect source cannot pre-filter authorized fields before acquisition, require authorization for FULL reply or an approved shop-filtered gateway; post-filter alone is insufficient.
- [ ] Safe metadata-only logging: collector_session, agent instance, endpoint fingerprint (not secret URL), connection status, request latency, status category, response bytes, sequence/gap, retry and disk failures. Reuse capstone.observability; optional Logfire spans with payload capture disabled.
- [ ] Maintain existing CLI flags/contracts and old fixtures unless explicitly versioned. Add safe `preflight` subcommand; no change to Siemens OPC UA.
- [ ] Add offline malformed XML/proxy/redirect/overrun/empty-stall/restart/rate-limit/storage/permission tests; no network to actual CNC in CI.

## Pydantic-first micro-iteration loop (repeat for EACH change)
1. Pick one contract/function, write test; 2. compare file with #307 head and overlapping PRs; 3. consult current Pydantic AI/Pydantic Graph/Pydantic validation/Settings/observability docs; 4. implement minimal change using existing Pydantic models; 5. run focused pytest/Ruff, inspect variables and logs; 6. repeat and record commit/test proof in PR.
Docs: https://pydantic.dev/docs/validation/latest/concepts/validators/ ; https://pydantic.dev/docs/ai/graph/graph/ ; https://pydantic.dev/docs/ai/production/observability/ .
Never introduce an LLM or PydanticAI Agent into industrial polling.

## Acceptance gates / handoff
1. No machine connected, no production claim. Build offline fixtures first.
2. Block on mismatched identity/permissions/firmware/missing probe and unsafe transport; rate remains bounded when catching up.
3. Replayable captures exactly match committed sequence boundaries or show gap; no stale/invalid record marked good.
4. Focused tests + full tests + source-matched evaluation inventory and #307 CI; approval to merge depends on user and field acceptance.
**Handoff:** next chat read this PR body and `docs/haas_vf4/PR_A_MTCONNECT_TRANSPORT.md`, then #307, then check current branch/tests.
