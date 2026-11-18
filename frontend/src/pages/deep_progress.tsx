import type { DeepCheckpoint, ManagedRun } from '../types';
import { DataRow, InfoState, Panel, Pill, toneFor } from '../ui';

const LABELS: Record<string, string> = {
  observe: 'Observe', manual: 'Manual retrieval', plan: 'Plan',
  investigate: 'Investigate', hypothesize: 'Hypothesize', test: 'Test',
  critique: 'Critic review', recheck: 'Follow-up check',
  conclude: 'Conclude', decide: 'Decide', propose: 'Propose action',
  execute: 'Execute (simulator)', verify: 'Verify outcome',
};

function stageLabel(stage: string | null | undefined): string {
  return stage ? LABELS[stage] ?? 'Unknown stage' : 'Not yet observed';
}

function status(value: string | null | undefined): string {
  return value ? value.replaceAll('_', ' ') : 'Not recorded';
}

function started(value: boolean, complete: boolean): string {
  return value ? 'Yes, simulator only' : complete ? 'No start recorded' : 'Not observed yet';
}

function finished(value: boolean, complete: boolean): string {
  return value ? 'Yes, simulator only' : complete ? 'No finish recorded' : 'Not observed yet';
}

function checkpointDescription(step: DeepCheckpoint): string {
  return 'Iteration ' + step.iteration_count + ' · Tool calls ' + step.tool_calls +
    ' · Evidence ' + step.evidence_count + ' · Hypotheses ' + step.hypothesis_count +
    ' · Decisions ' + step.decision_count +
    (step.observed_tick == null ? '' : ' · Tick ' + step.observed_tick);
}

/** Durable read-only deep progress; never infer unvisited stages or verification. */
export function DeepInvestigationProgress({ run }: { run: ManagedRun | null }) {
  const progress = run?.snapshot.progress;
  const deep = progress?.deep;
  const signals = deep?.deep_signals;
  const timeline = progress?.deep_timeline ?? [];
  const total = progress?.deep_transition_total ?? timeline.length;
  const completed = run?.state === 'completed';
  const active = run?.state === 'running' || run?.state === 'awaiting_review';

  // Display after triage escalation as well as for explicitly deep-only runs.
  if (!run || (run.requested.mode !== 'deep' && !deep)) return null;

  return <Panel title="Full investigation lifecycle"
    subtitle="Source-safe Pydantic Graph checkpoints; no inferred stage completion">
    {deep ? <>
      <DataRow label={active ? 'Currently observed stage' : 'Last observed stage'}
        value={<Pill text={stageLabel(deep.stage)} tone={toneFor(run.state)}/>}/>
      <DataRow label="Investigation ID" value={deep.investigation_id}/>
      <DataRow label="Hypothesis revisions" value={signals?.hypothesis_revisions ?? 'Not recorded'}/>
      <DataRow label="Pruned alternatives" value={signals?.pruned_candidates ?? 'Not recorded'}/>
      <DataRow label="Critic tool calls" value={signals?.critic_tool_calls ?? 'Not recorded'}/>
      <DataRow label="Critic outcome" value={status(signals?.critic_outcome)}/>
      <DataRow label="Follow-up check outcome" value={status(signals?.recheck_outcome)}/>
      <DataRow label="Conclusion assessment" value={status(signals?.conclusion_assessment)}/>
      <DataRow label="Conclusion recommendation" value={status(signals?.conclusion_recommendation)}/>
      <DataRow label="Conclusion evidence references" value={signals?.conclusion_evidence_count ?? 'Not recorded'}/>
      <DataRow label="Proposal/review status" value={status(signals?.proposal_status)}/>
      {run.state === 'awaiting_review' && <InfoState kind="warning"
        title="Awaiting separate human review"
        detail="An approval requires the reviewer role. Approval does not prove a simulated action ran."/>}
      <DataRow label="Simulated action started" value={signals ?
        started(signals.action_started, completed) : 'Not recorded'}/>
      <DataRow label="Simulated action finished" value={signals ?
        finished(signals.action_finished, completed) : 'Not recorded'}/>
      <DataRow label="Verification check result" value={status(signals?.verification_outcome)}/>
      <DataRow label="Verification observation" value={signals ?
        (signals.verification_observed ? 'Recorded' : 'Not observed') : 'Not recorded'}/>
      <DataRow label="Verification tick" value={signals?.verification_tick == null ?
        'Not recorded' : 'Tick ' + signals.verification_tick}/>
    </> : <InfoState title="Deep investigation not observed yet"
      detail="The worker has not published a valid deep-stage snapshot. A triage escalation recommendation alone does not mean deep investigation started."/>}
    <h3>Observed stage transitions</h3>
    <DataRow label="Recorded transitions" value={total}/>
    {timeline.length > 0 ?
      timeline.map(checkpoint => <DataRow key={checkpoint.sequence}
        label={String(checkpoint.sequence).padStart(4, '0') + ' · ' + stageLabel(checkpoint.stage)}
        extra={checkpointDescription(checkpoint)}
        value="Observed"/>) :
      <InfoState title="No deep stage transitions recorded"
        detail="Earlier runs and dropped watcher updates may have no checkpoint history. The latest persisted deep state remains authoritative."/>}
    {total > timeline.length && <p className="body-copy">
      Showing the latest {timeline.length} of {total} observed transitions.
    </p>}
    <p className="body-copy">
      Stages may repeat or be skipped depending on the Graph policy and available evidence.
      Statuses are agent/worker observations, not simulator fault labels or independent
      verification. The completed authorized audit supplies detailed evidence and findings.
    </p>
  </Panel>;
}
