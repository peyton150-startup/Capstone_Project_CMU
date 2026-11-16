import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
const source = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const stylesheet = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
const routes = [...source.matchAll(/<Route path="([^"]+)"/g)].map(x => x[1]);
test('landing and all industrial workspaces have independent routes', () => {
  for (const route of ['/', '/overview', '/investigations', '/investigations/triage',
    '/investigations/deep', '/investigations/review', '/investigations/:id',
    '/machines', '/signals', '/recordings', '/recordings/quality', '/recordings/sessions',
    '/lab', '/lab/runs', '/lab/evaluations', '/lab/compare', '/knowledge',
    '/knowledge/manuals', '/knowledge/memory', '/system', '/system/observability',
    '/system/audit', '/system/settings']) assert.ok(routes.includes(route), route);
});
test('styles include industrial layout and high-contrast light option', () => {
  assert.match(stylesheet, /--nav:#171B20/);
  assert.match(stylesheet, /--accent:#00A1D1/);
  assert.match(stylesheet, /data-theme='light'/);
  assert.match(stylesheet, /@media\(max-width:760px\)/);
  assert.doesNotMatch(stylesheet, /@import url/);
});
test('operator navigation does not offer CNC control', () => {
  assert.doesNotMatch(source, /CNC write|Start machine|Acknowledge alarm/i);
});
