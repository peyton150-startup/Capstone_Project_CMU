// Framework-free reader for a managed run's server-sent stage journal.
// Plain JavaScript (typed in sseJournal.d.mts) so `node --test` can drive the
// whole connect / parse / retry loop with a fake fetch and a fake clock.
//
// The journal is a convenience view: the persisted run snapshot stays the
// source of truth. So the reader never gets stuck on one bad frame, never
// retries a request that cannot succeed, and records what it did so the page
// can show it and the console can log it.

import { ApiProblem, problemForStatus } from './sourceState.mjs';

/** Largest unfinished frame kept in memory, in characters. */
export const MAX_FRAME_CHARS = 65536;
/** Events that end a run's journal. */
export const TERMINAL_EVENTS = Object.freeze(['run.completed', 'run.failed', 'run.interrupted']);
/** Default reconnect delay, and the bounds a server `retry:` hint is clamped to. */
export const BASE_RETRY_MS = 2000;
export const MIN_RETRY_MS = 1000;
export const MAX_RETRY_MS = 30000;

/** A failure that retrying cannot fix (the same request would fail the same way). */
export class JournalStop extends Error {
  constructor(kind, message) {
    super(message);
    this.name = 'JournalStop';
    this.kind = kind;
  }
}

/** Split buffered text into complete frames and the unfinished remainder.
 * Accepts CRLF, LF and lone CR line endings, including a CRLF split across
 * two network chunks. Only the unfinished remainder is size-checked, so a
 * large replay of many small frames in one chunk is never rejected. */
export function takeFrames(buffer, maxFrameChars = MAX_FRAME_CHARS) {
  // Variables:
  //   heldCr: A trailing "\r" kept back unconverted, because the next chunk
  //     may begin with the "\n" that completes it.
  //   text: The buffer with every line ending turned into "\n".
  //   rest: The text after the last blank line: a frame still arriving.
  const heldCr = buffer.endsWith('\r') ? '\r' : '';
  const text = buffer.slice(0, buffer.length - heldCr.length).replace(/\r\n?/g, '\n');
  const frames = [];
  let start = 0;
  let end = text.indexOf('\n\n', start);
  while (end >= 0) {
    frames.push(text.slice(start, end));
    start = end + 2;
    end = text.indexOf('\n\n', start);
  }
  const rest = text.slice(start) + heldCr;
  if (rest.length > maxFrameChars)
    throw new JournalStop('oversize', 'A stage event exceeded the safe frame size.');
  return { frames, rest };
}

/** Read one frame's fields as the SSE specification does: the space after
 * the colon is optional, several data lines are joined with newlines, and
 * lines starting with ":" are comments. */
export function parseFrame(text) {
  // Variables:
  //   dataLines: Every data field in order; null data means the frame carried
  //     no payload (a keepalive, a comment or a retry hint).
  //   id: The last id field, kept as text so the caller validates it.
  let id = null, event = 'message', retry = null, comment = false;
  const dataLines = [];
  for (const line of text.split('\n')) {
    if (line === '') continue;
    if (line.startsWith(':')) { comment = true; continue; }
    const colon = line.indexOf(':');
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'data') dataLines.push(value);
    else if (field === 'event') event = value || 'message';
    else if (field === 'id') { if (!value.includes('\0')) id = value; }
    else if (field === 'retry') { if (/^\d+$/.test(value)) retry = Number(value); }
  }
  return { id, event, data: dataLines.length ? dataLines.join('\n') : null, retry, comment };
}

/** Decide what one parsed frame means for the journal.
 * Returns an action:
 *   'close'     the server ended a fully replayed terminal stream;
 *   'ignore'    nothing to record (keepalive, comment, retry hint);
 *   'duplicate' already seen at or below the cursor;
 *   'skip'      unusable; `reason` says why, and `cursor` moves past it when
 *               the frame had a valid id so a reconnect does not replay it;
 *   'event'     a stage event to show; `terminal` marks the run's last one. */
export function acceptFrame(frame, cursor) {
  // Variables:
  //   seq: The frame's sequence number; only a plain non-negative integer
  //     counts, so the cursor can never move to NaN or a fraction.
  //   cursor: The highest sequence already handled; frames at or below it
  //     were delivered before a reconnect.
  if (frame.event === 'stream.closed') return { action: 'close', reason: 'terminal_replay_complete', cursor };
  if (frame.data === null) return { action: 'ignore', cursor };
  if (frame.id === null || !/^\d{1,15}$/.test(frame.id))
    return { action: 'skip', reason: 'invalid_id', cursor };
  const seq = Number(frame.id);
  if (seq <= cursor) return { action: 'duplicate', seq, cursor };
  // Defense in depth: the API already keeps model-call envelopes out of SSE.
  if (frame.event.startsWith('model.')) return { action: 'skip', reason: 'private_event', seq, cursor: seq };
  let parsed;
  try {
    parsed = JSON.parse(frame.data);
  } catch {
    return { action: 'skip', reason: 'malformed_json', seq, cursor: seq };
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed))
    return { action: 'skip', reason: 'not_object', seq, cursor: seq };
  return { action: 'event', seq, cursor: seq, terminal: TERMINAL_EVENTS.includes(frame.event),
    event: { seq, event: frame.event, data: parsed } };
}

/** Whether and when to reconnect after a failed or ended connection.
 * Client errors other than 408/429 would fail the same way again, so they
 * stop; everything else backs off exponentially up to MAX_RETRY_MS. */
export function retryPlan({ kind, status = null, attempt = 0, baseDelayMs = BASE_RETRY_MS }) {
  // Variables:
  //   kind: What went wrong: 'http' (a non-2xx response), 'oversize',
  //     'incompatible', 'network' or 'ended' (the server closed the stream).
  //   attempt: Failed attempts since the last successful connection; it
  //     doubles the delay each time.
  if (kind === 'oversize' || kind === 'incompatible') return { retry: false, delayMs: null };
  if (kind === 'http' && status !== null && status >= 400 && status < 500 && status !== 408 && status !== 429)
    return { retry: false, delayMs: null };
  const delayMs = Math.min(baseDelayMs * 2 ** Math.min(attempt, 10), MAX_RETRY_MS);
  return { retry: true, delayMs };
}

/** Fixed message for each way a connection can end. Never raw exception text. */
export function problemMessage(kind, status) {
  if (kind === 'http' && status !== null) return problemForStatus(status);
  if (kind === 'oversize') return 'A stage event exceeded the safe frame size; the journal stopped.';
  if (kind === 'incompatible') return 'The API did not answer with an event stream.';
  if (kind === 'ended') return 'The API closed the event stream before the run finished.';
  return 'The event stream connection dropped.';
}

/** A fresh, empty diagnostics record for one run's journal. */
export function newDiagnostics() {
  return {
    state: 'idle', connects: 0, attempt: 0, httpStatus: null, lastConnectedAt: null,
    lastError: null, lastErrorKind: null, lastErrorAt: null, frames: 0, keepalives: 0,
    accepted: 0, duplicates: 0,
    skipped: { invalid_id: 0, malformed_json: 0, not_object: 0, private_event: 0 },
    lastSeq: 0, lastEventAt: null, chars: 0, nextRetryMs: null, closeReason: null,
  };
}

/** Total skipped frames across every reason. */
export function skippedCount(diagnostics) {
  return Object.values(diagnostics.skipped).reduce((sum, n) => sum + n, 0);
}

/** One short line for the journal panel's subtitle. */
export function describeJournal(diagnostics) {
  // Variables:
  //   state: Where the reader is in its loop; 'waiting' means a reconnect is
  //     scheduled and 'stopped' means it gave up on purpose.
  const d = diagnostics;
  if (d.state === 'idle') return 'not connected';
  if (d.state === 'connecting') return d.connects > 1 ? 'reconnecting (attempt ' + d.connects + ')' : 'connecting';
  if (d.state === 'connected') return 'connected';
  if (d.state === 'waiting') return 'retrying in ' + Math.round((d.nextRetryMs || 0) / 1000) + ' s';
  if (d.state === 'finished') return 'finished';
  return 'stopped: ' + (d.lastError || 'unknown reason');
}

/** A console logger for one run's journal. Logs only run id, sequence
 * numbers, counts, HTTP status and fixed reasons: never tokens, URLs with
 * credentials or event payloads. */
export function journalLogger(runId, sink = console) {
  // Variables:
  //   sink: Where lines go (the browser console by default); a level the sink
  //     lacks is dropped rather than thrown.
  return (level, message, fields = {}) => {
    const write = sink && typeof sink[level] === 'function' ? sink[level] : null;
    if (write) write.call(sink, '[journal] ' + message, { run_id: runId, ...fields });
  };
}

/** Sleep that ends early (resolving false) when the signal aborts. */
export function abortableSleep(ms, signal) {
  return new Promise(resolve => {
    if (signal.aborted) return resolve(false);
    const timer = setTimeout(() => { signal.removeEventListener('abort', stop); resolve(true); }, ms);
    function stop() { clearTimeout(timer); resolve(false); }
    signal.addEventListener('abort', stop, { once: true });
  });
}

/** Connect, read, and reconnect until the run's journal ends, a stop
 * condition is reached, or the signal aborts. Resolves with the final
 * diagnostics; never rejects for a stream problem. */
export async function runJournal({ fetchImpl, urlFor, headers = {}, signal, sleep = abortableSleep,
  onEvent, onDiagnostics = () => {}, log = () => {}, now = () => new Date().toISOString(),
  maxFrameChars = MAX_FRAME_CHARS }) {
  // Variables:
  //   cursor: Highest sequence handled; each reconnect asks the API for
  //     events after it, so a dropped connection resumes instead of replaying.
  //   diag: The running diagnostics record; a copy goes to onDiagnostics
  //     after every change so the page never holds a mutable reference.
  //   attempt: Failed attempts since the last healthy connection, which sets
  //     the backoff delay. Only a connection that delivers a real frame (an
  //     event, a keepalive or stream.closed) resets it, so a proxy that
  //     answers 200 and closes at once still backs off to MAX_RETRY_MS.
  //   baseDelayMs: Reconnect delay, taken from the server's retry hint when it
  //     sends one, clamped to MIN_RETRY_MS..MAX_RETRY_MS.
  //   signal: Once aborted, no event or diagnostics callback fires again, so
  //     a superseded reader cannot write into a newer run's view.
  let cursor = 0, attempt = 0, baseDelayMs = BASE_RETRY_MS;
  const diag = newDiagnostics();
  // After abort the caller has moved on (another run, credential or
  // backend), so nothing more is reported to it.
  const publish = patch => {
    Object.assign(diag, patch);
    if (!signal.aborted) onDiagnostics({ ...diag, skipped: { ...diag.skipped } });
  };

  while (!signal.aborted) {
    publish({ state: 'connecting', connects: diag.connects + 1, attempt, nextRetryMs: null });
    log('info', 'connect', { cursor, attempt });
    let failure = null;
    try {
      const outcome = await readOnce();
      if (signal.aborted) break;
      if (outcome !== 'ended') {
        publish({ state: 'finished', closeReason: outcome });
        log('info', 'finished', { reason: outcome, last_seq: cursor, accepted: diag.accepted,
          skipped: skippedCount(diag) });
        return { ...diag, skipped: { ...diag.skipped } };
      }
      failure = { kind: 'ended', status: null };
    } catch (problem) {
      if (signal.aborted) break;
      failure = problem instanceof JournalStop ? { kind: problem.kind, status: null }
        : problem instanceof ApiProblem ? { kind: 'http', status: problem.status }
        : { kind: 'network', status: null, name: problem && problem.name };
    }
    const message = problemMessage(failure.kind, failure.status);
    const plan = retryPlan({ kind: failure.kind, status: failure.status, attempt, baseDelayMs });
    if (!plan.retry) {
      publish({ state: 'stopped', lastError: message, lastErrorKind: failure.kind, lastErrorAt: now() });
      log('warn', 'stopped', { kind: failure.kind, status: failure.status, last_seq: cursor });
      return { ...diag, skipped: { ...diag.skipped } };
    }
    attempt += 1;
    publish({ state: 'waiting', lastError: message, lastErrorKind: failure.kind, lastErrorAt: now(),
      nextRetryMs: plan.delayMs, attempt });
    log(failure.kind === 'ended' ? 'info' : 'warn', 'retry scheduled', { kind: failure.kind,
      status: failure.status, error_name: failure.name, delay_ms: plan.delayMs, attempt, last_seq: cursor });
    if (!(await sleep(plan.delayMs, signal))) break;
  }
  publish({ state: 'idle', nextRetryMs: null });
  log('debug', 'aborted', { last_seq: cursor });
  return { ...diag, skipped: { ...diag.skipped } };

  // One connection: returns 'ended' when the server closed the stream
  // without finishing, or the close reason when the journal is complete.
  async function readOnce() {
    // Variables:
    //   buffer: Text received but not yet split into complete frames.
    //   result: Set once a terminal event or stream.closed arrives, so the
    //     loop stops reading and the caller does not reconnect.
    const response = await fetchImpl(urlFor(cursor), { headers, signal, cache: 'no-store' });
    if (!response.ok) throw new ApiProblem(response.status, problemForStatus(response.status));
    const type = response.headers && response.headers.get ? response.headers.get('content-type') : null;
    if (!response.body || (type && !type.includes('text/event-stream')))
      throw new JournalStop('incompatible', 'The API did not answer with an event stream.');
    publish({ state: 'connected', httpStatus: response.status, lastConnectedAt: now() });
    log('info', 'open', { status: response.status, cursor });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let result = null;
    try {
      while (result === null) {
        const { done, value } = await reader.read();
        if (signal.aborted) return 'ended';
        if (done) {
          const tail = decoder.decode();
          if ((buffer + tail).trim()) log('warn', 'incomplete frame dropped', { chars: (buffer + tail).length });
          return 'ended';
        }
        const text = decoder.decode(value, { stream: true });
        diag.chars += text.length;
        const { frames, rest } = takeFrames(buffer + text, maxFrameChars);
        buffer = rest;
        for (const raw of frames) {
          if (signal.aborted) break;
          result = handle(parseFrame(raw));
          if (result !== null) break;
        }
      }
    } finally {
      reader.cancel().catch(() => {});
    }
    return result;
  }

  // Apply one frame; returns a close reason when the journal is complete.
  function handle(frame) {
    // Variables:
    //   verdict: acceptFrame's decision for this frame; its cursor is adopted
    //     even for a skipped frame, so a reconnect does not fetch it again.
    //   attempt: Reset here, on the connection's first real frame, rather
    //     than when the response headers arrive.
    diag.frames += 1;
    if (frame.retry !== null) baseDelayMs = Math.min(Math.max(frame.retry, MIN_RETRY_MS), MAX_RETRY_MS);
    const verdict = acceptFrame(frame, cursor);
    cursor = verdict.cursor;
    // A bare retry hint proves little; any other frame shows the stream works.
    if (attempt !== 0 && (frame.comment || verdict.action !== 'ignore')) {
      attempt = 0;
      diag.attempt = 0;
      log('debug', 'backoff reset', { seq: cursor });
    }
    if (verdict.action === 'close') return verdict.reason;
    if (verdict.action === 'ignore') {
      if (frame.comment) diag.keepalives += 1;
      return null;
    }
    if (verdict.action === 'duplicate') { diag.duplicates += 1; return null; }
    if (verdict.action === 'skip') {
      diag.skipped[verdict.reason] += 1;
      publish({ lastSeq: cursor });
      log('warn', 'frame skipped', { reason: verdict.reason, seq: verdict.seq ?? null, event: frame.event });
      return null;
    }
    if (!signal.aborted) onEvent(verdict.event);
    publish({ accepted: diag.accepted + 1, lastSeq: cursor, lastEventAt: now() });
    return verdict.terminal ? frame.event : null;
  }
}
