import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import {
  acceptFrame, describeJournal, journalLogger, JournalStop, newDiagnostics, parseFrame,
  retryPlan, runJournal, skippedCount, takeFrames,
} from '../src/sseJournal.mjs';

const encoder = new TextEncoder();

// A Response whose body arrives in exactly these chunks.
function streamResponse(chunks, { status = 200, type = 'text/event-stream' } = {}) {
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status, headers: type ? { 'content-type': type } : {} });
}

// Runs the journal against a scripted list of responses (or thrown errors).
async function drive(script, extra = {}) {
  const urls = [], events = [], logs = [], delays = [];
  const abort = new AbortController();
  let call = 0;
  const final = await runJournal({
    fetchImpl: async url => {
      urls.push(url);
      const next = script[call++];
      if (next === undefined) { abort.abort(); throw new DOMException('aborted', 'AbortError'); }
      if (next instanceof Error) throw next;
      return typeof next === 'function' ? next() : next;
    },
    urlFor: cursor => '/events?since=' + cursor,
    headers: { Authorization: 'Bearer secret-token' },
    signal: abort.signal,
    sleep: async ms => { delays.push(ms); return true; },
    onEvent: event => events.push(event),
    log: (level, message, fields) => logs.push({ level, message, fields }),
    now: () => '2026-11-19T12:00:00Z',
    ...extra,
  });
  return { final, urls, events, logs, delays };
}

const frame = (id, event, data) => 'id: ' + id + '\nevent: ' + event + '\ndata: ' + data + '\n\n';

test('frames split on any line ending, including CRLF across chunks', () => {
  const first = takeFrames('id: 1\r\ndata: {}\r');
  assert.deepEqual(first.frames, []);
  assert.equal(first.rest, 'id: 1\ndata: {}\r');
  // A trailing CR could still be half of a CRLF, so it is held until the next chunk.
  const second = takeFrames(first.rest + '\n\r\nid: 2\rdata: {}\r\r');
  assert.deepEqual(second.frames, ['id: 1\ndata: {}']);
  assert.equal(second.rest, 'id: 2\ndata: {}\n\r');
  const third = takeFrames(second.rest + 'id: 3');
  assert.deepEqual(third.frames, ['id: 2\ndata: {}']);
  assert.equal(third.rest, 'id: 3');
});

test('a large replay of small frames is accepted; one oversized frame stops', () => {
  const many = Array.from({ length: 2000 }, (_, i) => frame(i + 1, 'stage.updated', '{"n":' + i + '}')).join('');
  assert.ok(many.length > 65536);
  assert.equal(takeFrames(many).frames.length, 2000);
  assert.throws(() => takeFrames('data: ' + 'x'.repeat(70000)), error =>
    error instanceof JournalStop && error.kind === 'oversize');
});

test('fields follow the SSE specification', () => {
  assert.deepEqual(parseFrame('id:7\nevent:stage.updated\ndata:{"a":\ndata: 1}'),
    { id: '7', event: 'stage.updated', data: '{"a":\n1}', retry: null, comment: false });
  assert.equal(parseFrame(': keepalive').comment, true);
  assert.equal(parseFrame(': keepalive').data, null);
  assert.equal(parseFrame('retry: 2000').retry, 2000);
  assert.equal(parseFrame('retry: soon').retry, null);
  assert.equal(parseFrame('data').data, '');
  assert.equal(parseFrame('id: 1\0\ndata: {}').id, null);
  assert.equal(parseFrame('event:\ndata: {}').event, 'message');
});

test('frame verdicts never stall the cursor on a bad payload', () => {
  const at = (id, event, data) => acceptFrame({ id, event, data, retry: null, comment: false }, 4);
  assert.equal(at(null, 'stream.closed', '{}').action, 'close');
  assert.equal(at(null, 'message', null).action, 'ignore');
  assert.deepEqual(at('3', 'stage.updated', '{}'), { action: 'duplicate', seq: 3, cursor: 4 });
  assert.deepEqual(at('x', 'stage.updated', '{}'), { action: 'skip', reason: 'invalid_id', cursor: 4 });
  assert.deepEqual(at('1.5', 'stage.updated', '{}'), { action: 'skip', reason: 'invalid_id', cursor: 4 });
  assert.deepEqual(at('5', 'stage.updated', '{oops'), { action: 'skip', reason: 'malformed_json', seq: 5, cursor: 5 });
  assert.deepEqual(at('6', 'stage.updated', '[1]'), { action: 'skip', reason: 'not_object', seq: 6, cursor: 6 });
  assert.deepEqual(at('7', 'model.call', '{}'), { action: 'skip', reason: 'private_event', seq: 7, cursor: 7 });
  const ok = at('8', 'run.failed', '{"code":"x"}');
  assert.equal(ok.action, 'event');
  assert.equal(ok.terminal, true);
  assert.deepEqual(ok.event, { seq: 8, event: 'run.failed', data: { code: 'x' } });
});

test('retry policy stops on requests that cannot succeed and backs off otherwise', () => {
  for (const status of [400, 401, 403, 404, 422]) assert.equal(retryPlan({ kind: 'http', status }).retry, false);
  for (const status of [408, 429, 500, 503]) assert.equal(retryPlan({ kind: 'http', status }).retry, true);
  assert.equal(retryPlan({ kind: 'oversize' }).retry, false);
  assert.equal(retryPlan({ kind: 'incompatible' }).retry, false);
  assert.deepEqual([0, 1, 2, 3, 4, 50].map(attempt => retryPlan({ kind: 'network', attempt }).delayMs),
    [2000, 4000, 8000, 16000, 30000, 30000]);
});

test('a malformed frame is skipped and counted; the journal still reaches the end', async () => {
  const { final, events, logs } = await drive([streamResponse([
    'retry: 2000\n\n', ': keepalive\n\n',
    frame(1, 'stage.updated', '{"stage":"triage"}'),
    frame(2, 'stage.updated', '{not json'),
    frame(3, 'run.completed', '{"state":"completed"}'),
  ])]);
  assert.deepEqual(events.map(e => e.seq), [1, 3]);
  assert.equal(final.state, 'finished');
  assert.equal(final.closeReason, 'run.completed');
  assert.equal(final.skipped.malformed_json, 1);
  assert.equal(skippedCount(final), 1);
  assert.equal(final.keepalives, 1);
  assert.equal(final.lastSeq, 3);
  assert.ok(logs.some(l => l.level === 'warn' && l.message === 'frame skipped' && l.fields.reason === 'malformed_json'));
});

test('reconnects resume from the cursor, back off, and reset after a good connection', async () => {
  const { final, urls, events, delays } = await drive([
    streamResponse([frame(1, 'stage.updated', '{}'), frame(2, 'stage.updated', '{}')]),
    new TypeError('fetch failed'),
    streamResponse([], { status: 503 }),
    streamResponse([frame(2, 'stage.updated', '{}'), frame(3, 'stage.updated', '{}')]),
    streamResponse(['event: stream.closed\ndata: {"reason":"terminal_replay_complete"}\n\n']),
  ]);
  assert.deepEqual(urls, ['/events?since=0', '/events?since=2', '/events?since=2', '/events?since=2', '/events?since=3']);
  assert.deepEqual(events.map(e => e.seq), [1, 2, 3]);
  assert.equal(final.duplicates, 1);
  // ended -> 2 s; network -> 4 s; 503 -> 8 s; ended after a good connection -> 2 s again.
  assert.deepEqual(delays, [2000, 4000, 8000, 2000]);
  assert.equal(final.state, 'finished');
  assert.equal(final.closeReason, 'terminal_replay_complete');
});

test('authorization and missing runs stop instead of retrying forever', async () => {
  for (const status of [401, 403, 404]) {
    const { final, urls, delays } = await drive([streamResponse([], { status })]);
    assert.equal(urls.length, 1);
    assert.deepEqual(delays, []);
    assert.equal(final.state, 'stopped');
    assert.equal(final.lastErrorKind, 'http');
    assert.match(describeJournal(final), /^stopped: /);
  }
});

test('a non-stream answer and an oversized frame stop with fixed messages', async () => {
  const html = await drive([streamResponse(['<html>'], { type: 'text/html' })]);
  assert.equal(html.final.state, 'stopped');
  assert.equal(html.final.lastErrorKind, 'incompatible');
  const big = await drive([streamResponse(['data: ' + 'x'.repeat(70000)])]);
  assert.equal(big.final.lastErrorKind, 'oversize');
  assert.match(big.final.lastError, /safe frame size/);
});

test('the server retry hint sets the base delay within bounds', async () => {
  const { delays } = await drive([streamResponse(['retry: 5000\n\n']), streamResponse(['retry: 10\n\n'])]);
  assert.deepEqual(delays, [5000, 1000]);
});

test('logs carry counts and reasons, never tokens, URLs or payloads', async () => {
  const { logs } = await drive([
    new TypeError('fetch failed'),
    streamResponse([frame(1, 'stage.updated', '{"secret":"payload-text"}'), frame(2, 'stage.updated', '{bad'),
      frame(3, 'run.completed', '{}')]),
  ]);
  const text = JSON.stringify(logs);
  for (const forbidden of ['secret-token', 'payload-text', '/events?since', '{bad'])
    assert.doesNotMatch(text, new RegExp(forbidden.replace(/[?{]/g, '\\$&')));
  assert.deepEqual(logs.map(l => l.message),
    ['connect', 'retry scheduled', 'connect', 'open', 'frame skipped', 'finished']);
  const lines = [];
  journalLogger('run-1', { warn: (...args) => lines.push(args) })('warn', 'stopped', { status: 401 });
  assert.deepEqual(lines, [['[journal] stopped', { run_id: 'run-1', status: 401 }]]);
  journalLogger('run-1', {})('info', 'ignored');
});

test('an aborted reader reports nothing more, even mid-stream', async () => {
  const abort = new AbortController();
  const events = [], states = [];
  let release;
  const body = new ReadableStream({
    async start(controller) {
      controller.enqueue(encoder.encode(frame(1, 'stage.updated', '{}')));
      await new Promise(resolve => { release = resolve; });
      controller.enqueue(encoder.encode(frame(2, 'stage.updated', '{}') + frame(3, 'run.completed', '{}')));
      controller.close();
    },
  });
  const done = runJournal({
    fetchImpl: async () => new Response(body, { headers: { 'content-type': 'text/event-stream' } }),
    urlFor: () => '/events', signal: abort.signal, sleep: async () => true,
    onEvent: event => events.push(event.seq), onDiagnostics: d => states.push(d.state),
  });
  while (events.length < 1) await new Promise(resolve => setTimeout(resolve, 1));
  abort.abort();
  const reported = states.length;
  release();
  await done;
  assert.deepEqual(events, [1]);
  assert.equal(states.length, reported);
  assert.ok(!states.includes('idle'));
});

test('diagnostics start empty and describe every state', () => {
  const d = newDiagnostics();
  assert.equal(describeJournal(d), 'not connected');
  assert.equal(describeJournal({ ...d, state: 'connecting', connects: 3 }), 'reconnecting (attempt 3)');
  assert.equal(describeJournal({ ...d, state: 'waiting', nextRetryMs: 4000 }), 'retrying in 4 s');
  assert.equal(describeJournal({ ...d, state: 'finished' }), 'finished');
});

test('the run page uses the tested journal reader and shows its diagnostics', () => {
  const managed = readFileSync(new URL('../src/pages/managed.tsx', import.meta.url), 'utf8');
  assert.match(managed, /runJournal\(\{/);
  assert.doesNotMatch(managed, /JSON\.parse\(data\)/);
  assert.match(managed, /<JournalDiagnosticsRows/);
});
