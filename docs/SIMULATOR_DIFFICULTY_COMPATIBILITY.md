# Simulator difficulty compatibility verification

Checked 2026-10-18 against this checkout. The developer authorized harder
simulator behavior only if it requires no investigation-side code changes.
This check adds tests, not new production behavior.

| Capability | Verified evidence | Limit |
|---|---|---|
| Compound faults | Existing `BearingDegradation` and `WrongSetting` run together; the provider returns readings, settings, events and proposals. | No solver runtime is present to test reasoning or completion behavior. |
| Similar symptoms from different causes | A worn bearing and an excessive speed setting produce identical noise-free vibration samples. | Other observations can distinguish them; this is intentional ambiguity in one sensor. |
| Drift, transient anomalies and missing samples | Synthetic sample fixtures pass through existing reading and summary tools; gaps stay gaps, empty summaries have null statistics, endpoint rates use elapsed ticks. | Tests verify representation, not implemented causal drift/dropout/transient models. |
| Partial improvement after intervention | A human-approved bearing replacement reduces vibration while the simultaneous speed fault leaves it above baseline. Existing tools show the residual evidence. | Only bearing replacement is currently allowed; no setting-reset action is implemented. |
| Delayed historical maintenance records | Appending an earlier-tick record after a later event is rejected by `EventLog.record()`. | `EventObservation` has one tick, not separate occurrence/publication times. A publication-time event with the occurrence time in its message could preserve the shape, but that convention and consumer behavior have not been verified. |

The compatibility tests are in `tests/test_difficulty_tool_compatibility.py`.
They exercise the actual provider, simulator, scenarios, sensors, approval desk,
and action tools. Synthetic observation fixtures are explicitly identified.
Existing provider tests separately verify all read-tool shapes and deny hidden
truth/approval tools; sensor-summary tests cover sparse and empty histories.

`CompletedInvestigation` has one `proposed_action` and one conclusion whose
diagnosis is free text. Several diagnoses could be written into that string,
but structured reporting of multiple causes/interventions is not established
by the current contract. `LLMProvider` is a protocol, not an executable solver.
Consequently, tool-shape compatibility is demonstrated for the cases above;
zero changes to an actual investigation runtime cannot be certified here.

Decision: do not introduce the full requested difficulty bundle under the
strict zero-investigation-change condition. Preserve the existing interfaces;
resolve delayed-record semantics and test the actual solver before claiming
end-to-end compatibility. No new LLM is necessary for these simulator features.
