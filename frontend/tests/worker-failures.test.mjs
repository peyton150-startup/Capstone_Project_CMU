import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';

const managed = readFileSync(new URL('../src/pages/managed.tsx', import.meta.url), 'utf8');
const engineering = readFileSync(new URL('../src/pages/engineering.tsx', import.meta.url), 'utf8');
const types = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');

test('a failed hosted run shows its fixed failure code, not only the Python class', () => {
  for (const code of ['artifact', 'configuration_mismatch', 'contract', 'database',
    'execution', 'invalid_configuration', 'model_setup']) {
    assert.ok(managed.includes(code + ':'), code);
  }
  assert.match(managed, /failureLabel\(run\.snapshot\?\.failure_code, run\.snapshot\?\.error_class\)/);
  assert.match(types, /failure_code\?: string/);
});

test('an interrupted run names why it stopped and how long its worker was silent', () => {
  assert.match(managed, /Interruption reason/);
  assert.match(managed, /worker_lease_expired/);
  assert.match(managed, /heartbeat_age_seconds/);
  assert.match(managed, /Last worker heartbeat/);
  assert.match(types, /heartbeat_age_seconds\?: number \| null/);
});

test('the journal summary shows dropped live updates and terminal reasons', () => {
  assert.match(managed, /event\.event === 'resync\.required'/);
  assert.match(managed, /dropped_ui_updates/);
  assert.match(managed, /event\.event === 'run\.failed'/);
  assert.match(managed, /event\.event === 'run\.interrupted'/);
});

test('run diagnostics show the newly projected safe operational fields', () => {
  for (const field of ['phase', 'status', 'reason_code', 'attempt', 'duration_ms',
    'request_hash']) {
    assert.match(managed, new RegExp('event\\.' + field), field);
  }
  assert.doesNotMatch(managed, /config_fingerprint/);
});

test('worker process problems appear on the System page, not in a run journal', () => {
  assert.match(engineering, /last_worker_problem/);
  for (const code of ['poll_failed', 'worker_pulse_failed', 'contracts_missing'])
    assert.ok(engineering.includes(code), code);
  assert.match(engineering, /label="last worker problem"/);
  assert.doesNotMatch(managed, /last_worker_problem/);
});
