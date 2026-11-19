// Pure, framework-free rules for describing why a panel has no data.
// Kept in plain JavaScript (with backend.d.mts-style types in
// sourceState.d.mts) so `node --test` can check them without a bundler.

/** Every availability value the Python API emits today, plus the pilot gate
 * the frontend applies itself. Anything else is reported as unrecognized. */
export const KNOWN_AVAILABILITY = Object.freeze([
  'available', 'not_configured', 'file_missing', 'not_integrated',
  'unsupported_for_pilot', 'not_available_in_pilot', 'not_recorded',
  'unavailable', 'error', 'synthetic',
]);

/** Error thrown by request helpers; keeps the HTTP status for presentation. */
export class ApiProblem extends Error {
  constructor(status, message) {
    super(message);
    this.name = 'ApiProblem';
    this.status = status;
  }
}

/** Fixed, sanitized message for an HTTP status. Server detail is never shown. */
export function problemForStatus(status) {
  if (status === 401) return 'Session token required for the selected API. Open Access in the toolbar.';
  if (status === 403) return 'The current credential or workspace is not authorized for this source.';
  if (status === 404) return 'The selected API does not provide this record or endpoint.';
  if (status === 409) return 'The request conflicts with the current server state.';
  if (status === 422) return 'The API rejected the request parameters.';
  if (status === 503) return 'The selected API reported this service as unavailable.';
  return 'API request failed (' + status + ').';
}

/** Validate the `{availability, items, message?}` list contract at runtime.
 * A TypeScript cast proves nothing about a response, so malformed shapes
 * become a contract error instead of an empty list. */
export function decodeListResponse(payload) {
  // Variables:
  //   availability: The server's stated source state; unknown values are kept
  //     as 'unrecognized' rather than trusted as 'available'.
  //   items: The record array; anything that is not an array of objects is a
  //     contract violation, never silently treated as "no records".
  if (!payload || typeof payload !== 'object' || Array.isArray(payload))
    throw new ApiProblem(null, 'The API returned an incompatible response shape.');
  const items = payload.items;
  if (!Array.isArray(items) || items.some(item => !item || typeof item !== 'object'))
    throw new ApiProblem(null, 'The API returned an incompatible record list.');
  const availability = typeof payload.availability === 'string' &&
    KNOWN_AVAILABILITY.includes(payload.availability) ? payload.availability : 'unrecognized';
  const message = typeof payload.message === 'string' ? payload.message.slice(0, 300) : undefined;
  return { availability, items, message };
}

const AVAILABILITY_TEXT = {
  not_configured: ['not configured', 'The selected API has no approved source configured for this view.', 'empty'],
  file_missing: ['source file missing', 'A source is configured, but its file was not found on the API host.', 'warning'],
  not_integrated: ['not integrated', 'The selected API does not implement this capability.', 'empty'],
  unsupported_for_pilot: ['not available in the pilot workspace', 'This view is limited to the simulator workspace.', 'empty'],
  not_available_in_pilot: ['not available in the pilot workspace', 'This view is limited to the simulator workspace.', 'empty'],
  not_recorded: ['not recorded', 'The run has not persisted this artifact. It may not have reached that stage.', 'empty'],
  unavailable: ['unavailable', 'The API reported this source as unavailable.', 'warning'],
  error: ['in an error state', 'The API reported an error reading this source.', 'error'],
  unrecognized: ['in an unrecognized state', 'The API returned an availability value this interface does not know. Nothing is shown rather than guessing.', 'warning'],
};

/** Turn request and source facts into one honest panel state.
 * Order matters: loading and request failures are checked before the
 * availability so a failed poll never reads as "no records". */
export function describeSourceState({ item, loading = false, error = null, status = null,
  availability = null, count = 0, emptyDetail = null, detail = null }) {
  // Variables:
  //   status: HTTP status of the failed request, used to separate access
  //     problems (401/403) from other failures.
  //   availability: The source state the API stated; null when no response
  //     was decoded yet.
  //   count: How many records the decoded response held; zero with
  //     'available' is a valid empty result, not a missing connection.
  //   emptyDetail / detail: Panel-specific wording that overrides the generic
  //     text for an empty result or an unconfigured source.
  if (count > 0) return { kind: 'ready', tone: 'empty', title: item, detail: '' };
  if (error) {
    const denied = status === 401 || status === 403;
    return { kind: denied ? 'denied' : 'failed', tone: denied ? 'warning' : 'error',
      title: item + (denied ? ': authorization required' : ': request failed'), detail: String(error) };
  }
  if (loading) return { kind: 'loading', tone: 'empty', title: 'Loading ' + item.toLowerCase(), detail: 'Waiting for the selected API.' };
  if (availability === null || availability === undefined)
    return { kind: 'idle', tone: 'empty', title: item + ': not requested', detail: detail || 'Select a source to load this view.' };
  if (availability === 'available' || availability === 'synthetic')
    return { kind: 'empty', tone: 'empty', title: 'No ' + item.toLowerCase() + ' recorded',
      detail: emptyDetail || 'The source is connected and returned no records. An empty result is not proof that nothing happened.' };
  const [suffix, generic, tone] = AVAILABILITY_TEXT[availability] || AVAILABILITY_TEXT.unrecognized;
  return { kind: availability, tone, title: item + ': ' + suffix, detail: detail || generic };
}

/** Horizontal positions (0..1) for chart samples. Uses real timestamps when
 * every sample has a valid, non-decreasing one; otherwise falls back to the
 * sample order and says so, so even spacing is never implied silently. */
export function timeAxis(samples) {
  // Variables:
  //   times: Parsed sample timestamps in milliseconds; a NaN or a decrease
  //     means the timestamps cannot position the samples honestly.
  //   span: The interval from the first to the last sample; zero falls back
  //     to order because every sample would land on one point.
  const fallback = () => ({ mode: 'order', positions: samples.map((_, i) => samples.length > 1 ? i / (samples.length - 1) : 0) });
  if (samples.length < 2) return fallback();
  const times = samples.map(sample => Date.parse(sample.at));
  for (let i = 0; i < times.length; i++)
    if (Number.isNaN(times[i]) || (i > 0 && times[i] < times[i - 1])) return fallback();
  const span = times[times.length - 1] - times[0];
  if (span <= 0) return fallback();
  return { mode: 'time', positions: times.map(t => (t - times[0]) / span) };
}

/** Pick the triage report to show: the requested run if it has one, else the
 * most recently updated run with a persisted report. Never invents a report. */
export function selectTriageReport(runs, selectedRunId) {
  // Variables:
  //   withReports: Only runs whose persisted snapshot carries a triage_report.
  //   selectedRunId: The run the user chose; ignored when that run has no
  //     report, so an old selection cannot show another run's report under its name.
  const withReports = (runs || []).filter(run => run && run.snapshot && run.snapshot.triage_report)
    .slice().sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  const chosen = withReports.find(run => run.run_id === selectedRunId) || withReports[0] || null;
  return { runs: withReports, run: chosen, report: chosen ? chosen.snapshot.triage_report : null };
}

/** Whether a triage report may show an accepted diagnosis and a model rating. */
export function reportHasAcceptedConclusion(report) {
  return Boolean(report) && report.outcome === 'model_conclusion';
}
