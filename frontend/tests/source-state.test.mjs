import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import {
  ApiProblem, decodeListResponse, describeSourceState, problemForStatus,
  reportHasAcceptedConclusion, selectTriageReport, timeAxis,
} from '../src/sourceState.mjs';

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');

test('list decoder rejects shapes a TypeScript cast would have trusted', () => {
  assert.throws(() => decodeListResponse(null), ApiProblem);
  assert.throws(() => decodeListResponse([]), /incompatible response/);
  assert.throws(() => decodeListResponse({ availability: 'available' }), /record list/);
  assert.throws(() => decodeListResponse({ availability: 'available', items: [1, 2] }), /record list/);
  assert.throws(() => decodeListResponse({ availability: 'available', items: 'x' }), /record list/);
});

test('unknown availability is reported as unrecognized, never as available', () => {
  const list = decodeListResponse({ availability: 'totally_new', items: [] });
  assert.equal(list.availability, 'unrecognized');
  assert.equal(decodeListResponse({ items: [] }).availability, 'unrecognized');
  assert.equal(decodeListResponse({ availability: 'not_recorded', items: [] }).availability, 'not_recorded');
  const view = describeSourceState({ item: 'Run history', availability: list.availability });
  assert.equal(view.kind, 'unrecognized');
  assert.equal(view.tone, 'warning');
});

test('loading, valid empty and unconfigured sources read differently', () => {
  const loading = describeSourceState({ item: 'Run history', loading: true });
  const empty = describeSourceState({ item: 'Run history', availability: 'available', count: 0 });
  const missing = describeSourceState({ item: 'Run history', availability: 'not_configured' });
  const file = describeSourceState({ item: 'Run history', availability: 'file_missing' });
  const notRecorded = describeSourceState({ item: 'Decision trace', availability: 'not_recorded' });
  assert.equal(loading.kind, 'loading');
  assert.equal(empty.kind, 'empty');
  assert.match(empty.title, /^No run history recorded$/);
  assert.match(empty.detail, /not proof/);
  assert.equal(missing.kind, 'not_configured');
  assert.equal(file.kind, 'file_missing');
  assert.equal(notRecorded.kind, 'not_recorded');
  for (const view of [loading, empty, missing, file, notRecorded])
    assert.doesNotMatch(view.title, /not connected yet/);
});

test('a failed request is never presented as an empty or unconfigured source', () => {
  // Polling failure after an earlier success: data is cleared, error wins.
  const failed = describeSourceState({ item: 'Run history', error: 'API request failed (500).',
    status: 500, availability: 'available', count: 0, loading: true });
  assert.equal(failed.kind, 'failed');
  assert.equal(failed.tone, 'error');
  const denied = describeSourceState({ item: 'Scorecards', error: problemForStatus(403), status: 403 });
  assert.equal(denied.kind, 'denied');
  assert.match(denied.title, /^Scorecards: authorization required$/);
  assert.equal(failed.title, 'Run history: request failed');
  const unauth = describeSourceState({ item: 'Scorecards', error: problemForStatus(401), status: 401 });
  assert.equal(unauth.kind, 'denied');
});

test('HTTP statuses map to fixed sanitized messages', () => {
  for (const status of [401, 403, 404, 409, 422, 503, 500]) {
    const message = problemForStatus(status);
    assert.ok(message.length > 10);
    assert.doesNotMatch(message, /Traceback|psycopg|sk-|\\\\|\/home\//);
  }
  assert.match(problemForStatus(500), /\(500\)/);
});

test('records present always win over availability wording', () => {
  assert.equal(describeSourceState({ item: 'x', availability: 'not_configured', count: 3 }).kind, 'ready');
});

test('chart spacing follows timestamps and falls back to order honestly', () => {
  const irregular = timeAxis([
    { at: '2026-11-19T10:00:00Z' }, { at: '2026-11-19T10:00:01Z' }, { at: '2026-11-19T10:00:10Z' },
  ]);
  assert.equal(irregular.mode, 'time');
  assert.deepEqual(irregular.positions, [0, 0.1, 1]);
  const outOfOrder = timeAxis([{ at: '2026-11-19T10:00:05Z' }, { at: '2026-11-19T10:00:01Z' }]);
  assert.equal(outOfOrder.mode, 'order');
  assert.deepEqual(outOfOrder.positions, [0, 1]);
  assert.equal(timeAxis([{ at: 'not a time' }, { at: '2026-11-19T10:00:01Z' }]).mode, 'order');
  assert.equal(timeAxis([{ at: '2026-11-19T10:00:01Z' }, { at: '2026-11-19T10:00:01Z' }]).mode, 'order');
  assert.deepEqual(timeAxis([{ at: 'x' }]).positions, [0]);
});

const report = outcome => ({ outcome, diagnosis: outcome === 'model_conclusion' ? 'bearing' : null, confidence: 0 });
const run = (id, updated, triage) => ({ run_id: id, updated_at: updated, snapshot: { triage_report: triage } });

test('triage report selection only shows a run that has its own report', () => {
  const runs = [run('a', '2026-11-19T10:00:00Z', report('model_conclusion')),
    run('b', '2026-11-19T12:00:00Z', null), run('c', '2026-11-19T11:00:00Z', report('no_model_answer'))];
  const latest = selectTriageReport(runs, null);
  assert.deepEqual(latest.runs.map(r => r.run_id), ['c', 'a']);
  assert.equal(latest.run.run_id, 'c');
  assert.equal(selectTriageReport(runs, 'a').run.run_id, 'a');
  // A selection pointing at a run without a report never borrows another label.
  const stale = selectTriageReport(runs, 'b');
  assert.equal(stale.run.run_id, 'c');
  assert.equal(stale.report, runs[2].snapshot.triage_report);
  assert.equal(selectTriageReport([], 'a').report, null);
  assert.equal(selectTriageReport(undefined, null).run, null);
});

test('refused and no-answer reports never count as accepted conclusions', () => {
  assert.equal(reportHasAcceptedConclusion(report('model_conclusion')), true);
  assert.equal(reportHasAcceptedConclusion(report('model_answer_refused')), false);
  assert.equal(reportHasAcceptedConclusion(report('no_model_answer')), false);
  assert.equal(reportHasAcceptedConclusion(null), false);
  const view = read('../src/pages/managed.tsx');
  assert.match(view, /value=\{accepted && report\.diagnosis \? report\.diagnosis :/);
  assert.match(view, /<ManagedTriageReportPicker|export function ManagedTriageReportPicker/);
});

test('pages no longer use the generic placeholder for data-backed panels', () => {
  const pages = ['operations', 'investigations', 'managed', 'recordings', 'research', 'engineering']
    .map(name => [name, read('../src/pages/' + name + '.tsx')]);
  const remaining = pages.flatMap(([name, text]) =>
    [...text.matchAll(/<Unavailable item="([^"]+)"/g)].map(m => name + ':' + m[1]));
  // Only deliberate gates remain: pilot diagnosis, preview/workspace gates and
  // the launcher capability switch.
  assert.deepEqual(remaining.sort(), [
    'investigations:Typed triage report',
    'managed:Managed simulator run',
    'managed:Managed simulator runner',
  ]);
  assert.doesNotMatch(read('../src/ui.tsx'), /is not connected yet/);
});

test('simulator views never request the physical Siemens recording', () => {
  const data = read('../src/pageData.ts');
  assert.match(data, /const blocked = pilotOnly && workspace !== 'pilot';/);
  assert.match(data, /blocked \? null : '\/api\/v1\/recordings\/siemens-local\/health'/);
  const ops = read('../src/pages/operations.tsx');
  assert.equal((ops.match(/useRecording\(true\)/g) || []).length, 2);
});
