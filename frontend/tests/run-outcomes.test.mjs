import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';

const managed = readFileSync(new URL('../src/pages/managed.tsx', import.meta.url), 'utf8');
const outcomes = readFileSync(new URL('../src/pages/run_outcome.tsx', import.meta.url), 'utf8');
const types = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');

test('the managed investigation reads distinct server-authorized phase audits', () => {
  assert.match(managed, /auditPhase !== 'final'/);
  assert.match(managed, /&phase=/);
  assert.match(managed, /setAuditPhase\('triage'\)/);
  assert.match(managed, /setAuditPhase\('deep'\)/);
  assert.match(managed, /AuditPhaseOutcome detail=/);
  assert.match(managed, /finalAudit\.data/);
});

test('the end result shows distinct diagnosis review execution and verification', () => {
  for (const field of ['conclusion_detail', 'model_confidence', 'proposal_status',
    'action_started_tick', 'action_finish_tick', 'verification_detail',
    'verification_outcome', 'review_count', 'deep_ran']) {
    assert.ok(outcomes.includes(field), field);
  }
  assert.match(outcomes, /uncalibrated model rating/);
  assert.match(outcomes, /A proposal or approval is not an executed intervention/);
  assert.match(outcomes, /No verified check recorded/);
  assert.doesNotMatch(outcomes, /simulator_ground_truth|score_episode|provider_prompt/);
});

test('the UI has bounded backend result types and no new authorization controls', () => {
  assert.match(types, /conclusion_detail\?:/);
  assert.match(types, /unexplained_evidence_ids\?:/);
  assert.match(types, /proposal_status\?:/);
  assert.match(types, /observed_tick\?:/);
  assert.doesNotMatch(managed, /CAPSTONE_UI_RUN_TOKEN.*Set-Clipboard/);
});
