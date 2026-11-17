import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { defaultApiBackend, resolveApiUrl } from '../src/backend.mjs';

test('the frontend picks the appropriate default environment', () => {
  assert.equal(defaultApiBackend('127.0.0.1'), 'local');
  assert.equal(defaultApiBackend('localhost'), 'local');
  assert.equal(defaultApiBackend('capstone-project-cmu.vercel.app'), 'render');
});
test('requests route to the selected local or Render API proxy', () => {
  const path = '/api/v1/lab/runs?workspace=simulator';
  assert.equal(resolveApiUrl(path, 'local', '127.0.0.1'), path);
  assert.equal(resolveApiUrl(path, 'render', '127.0.0.1'), '/render-api/v1/lab/runs?workspace=simulator');
  assert.equal(resolveApiUrl(path, 'render', 'capstone-project-cmu.vercel.app'), path);
});
test('hosted Local cannot accidentally leak into the Render proxy', () => {
  assert.throws(() => resolveApiUrl('/api/v1/health', 'local', 'capstone-project-cmu.vercel.app'), /locally served/);
  assert.throws(() => resolveApiUrl('https://other/api/v1/health', 'render', 'localhost'), /Only versioned/);
  assert.throws(() => resolveApiUrl('/api/v1/health', 'other', 'localhost'), /Unknown API/);
});
test('backend change isolates responses, credentials, routes and event streaming', () => {
  const api = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
  const context = readFileSync(new URL('../src/context.tsx', import.meta.url), 'utf8');
  const managed = readFileSync(new URL('../src/pages/managed.tsx', import.meta.url), 'utf8');
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.match(api, /JSON\.stringify\(\[path, token, pause, pollMs, backend\]\)/);
  assert.match(context, /Record<ApiBackend, string>/);
  assert.match(managed, /resolveApiUrl\('\/api\/v1\/lab\/runs\//);
  assert.match(app, /<Routes key=\{backend\}>/);
});
