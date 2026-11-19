import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import {
  ROLES, ROLE_DENIED_MESSAGES, checkProblem, describeCheck, emptyTokens, envBlock, generateTokens,
  readToken, tokenFor,
} from '../src/access.mjs';

test('generated keys are four distinct url-safe tokens and an env block', () => {
  const tokens = generateTokens();
  const values = Object.values(tokens);
  assert.equal(new Set(values).size, 4);
  for (const value of values) assert.match(value, /^[A-Za-z0-9_-]{43}$/);
  const block = envBlock(tokens);
  for (const item of ROLES) assert.ok(block.includes(item.variable + '=' + tokens[item.role]));
  assert.ok(block.endsWith('CAPSTONE_UI_SIM_RUNS=1\n'));
});

test('reads use any token; actions send their own role and fall back for a clear error', () => {
  const tokens = { ...emptyTokens(), operator: 'op', reviewer: 'rev' };
  assert.equal(readToken(tokens), 'op');
  assert.equal(tokenFor(tokens, 'reviewer'), 'rev');
  assert.equal(tokenFor(tokens, 'evaluator'), 'op');
  assert.equal(readToken(emptyTokens()), '');
});

test('the dialog explains a mismatched or unknown token', () => {
  assert.deepEqual(describeCheck('operator', ['operator']), { ok: true, text: 'Recognised as operator' });
  assert.equal(describeCheck('operator', ['viewer']).text, 'This is the viewer token, not operator');
  assert.equal(describeCheck('operator', []).text, 'Not recognised by this backend');
});

test('browser role messages match the API exactly, and actions use role tokens', () => {
  const app = readFileSync(new URL('../../capstone-code/capstone/api/app.py', import.meta.url), 'utf8')
    .replace(/"\s*\n\s*"/g, '');
  for (const message of ROLE_DENIED_MESSAGES) assert.ok(app.includes('"' + message + '"'), message);
  const access = readFileSync(new URL('../../capstone-code/capstone/api/access.py', import.meta.url), 'utf8');
  for (const item of ROLES) assert.ok(access.includes('"' + item.variable + '"'), item.variable);
  const managed = readFileSync(new URL('../src/pages/managed.tsx', import.meta.url), 'utf8');
  assert.match(managed, /lab\/runs\?workspace=simulator', tokenFor\('operator'\)/);
  assert.match(managed, /tokenFor\('reviewer'\)/);
  const research = readFileSync(new URL('../src/pages/research.tsx', import.meta.url), 'utf8');
  assert.equal((research.match(/tokenFor\('evaluator'\)/g) || []).length, 2);
});

test('the Access dialog closes on Escape and its remember box is labelled', () => {
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
  const dialog = app.slice(app.indexOf('function AccessDialog'), app.indexOf('function', app.indexOf('function AccessDialog') + 10));
  assert.match(dialog, /event\.key === 'Escape'\)\s*\{?\s*close\(\)/);
  assert.match(dialog, /previousFocus\?\.focus\(\)/);
  assert.match(dialog, /event\.key !== 'Tab'/);
  assert.match(dialog, /event\.preventDefault\(\)/);
  assert.match(app, /className="access-remember"/);
  assert.match(app, /aria-label="Remember in this tab until it closes"/);
});

test('a backend without whoami gets a plain explanation, not a bare 404', () => {
  assert.match(checkProblem('API request failed (404).'), /older API without the token check/);
  assert.match(checkProblem('Session token required'), /could not be asked about them/);
});
