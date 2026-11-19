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

test('mobile drawer reveals navigation labels after desktop collapse', () => {
  const sidebar = source.slice(source.indexOf('function Sidebar'), source.indexOf('type WhoAmI'));
  assert.match(sidebar, /const showLabels = expanded \|\| mobileOpen/);
  assert.match(sidebar, /showLabels && <span>{item\.title}<\/span>/);
  assert.match(sidebar, /showLabels && <div className="workspace-switch">/);
});
test('System cards use client-side links and selected backend labels', () => {
  const engineering = readFileSync(new URL('../src/pages/engineering.tsx', import.meta.url), 'utf8');
  for (const path of ['/system/observability', '/system/audit', '/system/settings']) {
    assert.ok(engineering.includes('to="' + path + '"'), path);
    assert.ok(!engineering.includes('href="' + path + '"'), path);
  }
  assert.match(engineering, /backend === "local" \? "LOCAL API" : "RENDER API"/);
});
test('form controls keep intrinsic checkbox sizing and reduced motion', () => {
  assert.match(stylesheet, /input:not\(\[type='checkbox'\]\):not\(\[type='radio'\]\),select/);
  assert.match(stylesheet, /input\[type='checkbox'\],input\[type='radio'\]/);
  assert.match(stylesheet, /prefers-reduced-motion:reduce/);
});
