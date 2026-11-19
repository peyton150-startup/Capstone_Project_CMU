import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const managed = readFileSync(new URL('../src/pages/managed.tsx', import.meta.url), 'utf8');
const deep = readFileSync(new URL('../src/pages/deep_progress.tsx', import.meta.url), 'utf8');
const types = readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8');

test('full investigation progress is integrated into managed run detail', () => {
  assert.match(managed, /<DeepInvestigationProgress run=\{run\}\s*\/>/);
  assert.match(deep, /Full investigation lifecycle/);
  assert.match(deep, /deep_timeline/);
  assert.match(deep, /deep_transition_total/);
  assert.match(deep, /run\.requested\.mode !== 'deep' && !deep/);
});

test('deep lifecycle shows critic, proposal, action, and verification independently', () => {
  for (const source of ['critic_outcome', 'recheck_outcome', 'pruned_candidates',
    'hypothesis_revisions', 'conclusion_evidence_count', 'proposal_status',
    'action_started', 'action_finished', 'verification_observed',
    'verification_outcome', 'verification_tick']) {
    assert.ok(deep.includes(source), source);
    assert.ok(types.includes(source), source + ': typed');
  }
  assert.match(deep, /Approval does not prove a simulated action ran/);
  assert.match(deep, /not a guessed or planned step|Observed stage transitions/);
  assert.doesNotMatch(deep, /ground_truth|provider_prompt|model_messages|API_KEY/);
});

test('deep checkpoints display source counts and avoid fake completion percentages', () => {
  for (const value of ['iteration_count', 'tool_calls', 'evidence_count',
    'hypothesis_count', 'decision_count', 'observed_tick']) {
    assert.ok(deep.includes(value), value);
  }
  assert.match(deep, /total > timeline.length/);
  assert.match(deep, /Stages may repeat or be skipped/);
  assert.doesNotMatch(deep, /percentComplete|progressPercent|100% complete/);
});
