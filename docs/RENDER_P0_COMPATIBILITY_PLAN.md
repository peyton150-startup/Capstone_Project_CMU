# PR #298 P0 compatibility integration plan

Draft. Stacked on PR #298; do not merge/deploy before #293, #294, #296 and #297 are reconciled.

- Existing source ownership: #293/#294 public Pydantic safe stage schema, #296 Decide trace projection, #297 model-call/attempt sanitization. Do not copy or fork those modules.
- Replace hosted duplicate stage validation with a canonical alias when #294 exists; validate nested Decide timeline with #296's schema when integrated.
- Add hosted queue journal methods for sanitized model monitor/config/call/finished events, using #297's strict Pydantic models, transaction fencing and read-time revalidation.
- Add hosted adapter for #297's model-calls endpoint and record calls during the worker episode without altering model decisions.
- Keep the worker operative if the optional upstream model-call module is not yet integrated; mark telemetry unavailable, never claim it is complete.
- Require CI/SNAP, disposable Postgres, dual-process triage/deep, privacy negatives, SSE reconnect, before promotion.
