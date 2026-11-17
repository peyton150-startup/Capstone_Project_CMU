import type { InvestigationDetail, ManagedRun } from '../types';
import { DataRow, InfoState, Panel, Pill, toneFor } from '../ui';

/** These are agent ratings, not calibrated probabilities of a real fault. */
function rating(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ?
    Math.round(value * 100) + '/100 (uncalibrated model rating)' : 'Not recorded';
}

function ids(values: string[] | undefined): string {
  return values?.length ? values.join(', ') : 'Not recorded';
}

function statements(values: string[] | undefined): string {
  return values?.length ? values.join('; ') : 'None recorded';
}

function tick(value: number | null | undefined): string {
  return value == null ? 'Not recorded' : 'Tick ' + value;
}

/** The live-run snapshot and final audit remain independent evidence sources. */
export function FinalRunOutcome({ run, detail }: {
  run: ManagedRun | null; detail: InvestigationDetail | null;
}) {
  const finished = run?.state === 'completed';
  const snapshot = run?.snapshot;
  return <>
    <Panel title="Final diagnosis" subtitle="Recorded agent conclusion, not independently certified ground truth">
      {!finished ? <InfoState title="Final diagnosis not established"
        detail={run?.state === 'failed' || run?.state === 'interrupted' ?
          'The worker did not complete successfully. Check the failure classification and permitted trace.' :
          'The investigation is still underway; a current stage is not a final diagnosis.'}/> : <>
        <DataRow label="Incident" value={detail?.summary || 'Not recorded'}/>
        <DataRow label="Observed symptoms" value={statements(detail?.symptoms)}/>
        <DataRow label="Diagnosis" value={snapshot?.diagnosis || detail?.diagnosis || 'Not recorded'}/>
        <DataRow label="Assessment" value={detail?.conclusion_detail?.assessment || 'Not recorded'}/>
        <DataRow label="Model rating" value={rating(detail?.model_confidence)}/>
        <DataRow label="Leading hypothesis" value={detail?.conclusion_detail?.hypothesis_id || 'Not recorded'}/>
        <DataRow label="Evidence cited by conclusion" value={ids(detail?.conclusion_detail?.evidence_ids)}/>
        <DataRow label="Recommendation" value={snapshot?.recommendation || 'Not recorded'}/>
        <DataRow label="Decision rationale" value={detail?.conclusion_detail?.action_rationale || 'Not recorded'}/>
        <DataRow label="Unresolved questions" value={statements(detail?.conclusion_detail?.unresolved_questions)}/>
        <DataRow label="Next discriminating check" value={detail?.conclusion_detail?.next_check || 'Not recorded'}/>
        <DataRow label="Termination reason" value={detail?.termination_reason ||
          snapshot?.investigation?.termination_reason || 'Not recorded'}/>
        <DataRow label="Iterations / tool calls" value={detail ?
          detail.iterations + ' / ' + detail.tool_calls : 'Not recorded'}/>
        <DataRow label="Evidence / hypotheses" value={detail ?
          detail.evidence_count + ' / ' + detail.hypothesis_count : 'Not recorded'}/>
        <DataRow label="Escalated to deep" value={snapshot?.deep_ran == null ?
          'Unknown' : snapshot.deep_ran ? 'Yes' : 'No'}/>
      </>}
    </Panel>
    <Panel title="Proposed action and human review" subtitle="A proposal or approval is not an executed intervention">
      {!finished ? <InfoState title="Action outcome pending"
        detail="Pending review requests appear in Review & verification. No final action outcome has been established."/> : <>
        <DataRow label="Proposed action" value={detail?.proposed_action?.action || 'None recorded'}/>
        <DataRow label="Target machine" value={detail?.proposed_action?.machine_id || 'Not recorded'}/>
        <DataRow label="Proposal rationale" value={detail?.proposed_action?.reason || 'Not recorded'}/>
        <DataRow label="Proposal evidence IDs" value={ids(detail?.proposed_action?.evidence_ids)}/>
        <DataRow label="Proposal ID" value={detail?.proposal_id ?? 'Not recorded'}/>
        <DataRow label="Recorded proposal/review status" value={detail?.proposal_status || 'Not recorded'}/>
        <DataRow label="Number of submitted reviews" value={snapshot?.review_count ?? 'Not recorded'}/>
        <DataRow label="Simulated action started" value={snapshot?.action_executed == null ?
          'Unknown' : snapshot.action_executed ? 'Yes' : 'No'}/>
        <DataRow label="Action start" value={tick(detail?.action_started_tick)}/>
        <DataRow label="Action finish" value={tick(detail?.action_finish_tick)}/>
      </>}
    </Panel>
    <Panel title="Verification after intervention" subtitle="Only recorded observations establish whether a simulated intervention helped">
      {!finished ? <InfoState title="Verification pending"
        detail="No final verification can be assumed before the investigation finishes."/> : <>
        <DataRow label="Verification status" value={
          detail?.verification_detail?.status || 'Not recorded'}/>
        <DataRow label="Observed outcome" value={
          detail?.verification_detail?.outcome || snapshot?.verification_outcome || 'Not recorded'}/>
        <DataRow label="Observation summary" value={
          detail?.verification_detail?.summary || 'Not recorded'}/>
        <DataRow label="Observed at" value={tick(detail?.verification_detail?.observed_tick)}/>
        <DataRow label="Verification evidence IDs" value={
          ids(detail?.verification_detail?.evidence_ids)}/>
        {!detail?.verification_detail && <InfoState title="No verified check recorded"
          detail="An absent or inconclusive verification is not proof that the fault was fixed."/>}
      </>}
    </Panel>
  </>;
}

/** A separate conclusion for each completed, authorized triage/deep audit. */
export function AuditPhaseOutcome({ detail, phase }: {
  detail: InvestigationDetail; phase: 'final' | 'triage' | 'deep';
}) {
  const conclusion = detail.conclusion_detail;
  return <Panel title={phase === 'triage' ? 'Completed triage assessment' :
    phase === 'deep' ? 'Completed deep investigation' : 'Completed final investigation'}
    subtitle="Source-projected conclusion; no simulator answer key or private model trace">
    <DataRow label="Investigation ID" value={detail.id}/>
    <DataRow label="Anomaly" value={detail.summary}/>
    <DataRow label="Symptoms" value={statements(detail.symptoms)}/>
    <DataRow label="Diagnosis" value={detail.diagnosis || 'Not recorded'}/>
    <DataRow label="Model assessment" value={conclusion?.assessment || 'Not recorded'}/>
    <DataRow label="Model confidence" value={rating(detail.model_confidence)}/>
    <DataRow label="Leading hypothesis" value={conclusion?.hypothesis_id || 'Not recorded'}/>
    <DataRow label="Conclusion evidence IDs" value={ids(conclusion?.evidence_ids)}/>
    <DataRow label="Next check" value={conclusion?.next_check || 'Not recorded'}/>
    <DataRow label="Unresolved questions" value={statements(conclusion?.unresolved_questions)}/>
    <DataRow label="Recommended action rationale" value={conclusion?.action_rationale || 'Not recorded'}/>
    <DataRow label="Termination" value={detail.termination_reason || 'Not recorded'}/>
    <DataRow label="Iterations / tool calls" value={
      detail.iterations + ' / ' + detail.tool_calls}/>
    <DataRow label="Evidence / hypotheses" value={
      detail.evidence_count + ' / ' + detail.hypothesis_count}/>
    <DataRow label="Proposed intervention" value={detail.proposed_action?.action || 'None recorded'}/>
    <DataRow label="Proposed target" value={detail.proposed_action?.machine_id || 'Not recorded'}/>
    <DataRow label="Proposal status" value={<Pill text={detail.proposal_status || 'Unknown'}
      tone={toneFor(detail.proposal_status)}/>}/>
    <DataRow label="Action started / finished" value={
      tick(detail.action_started_tick) + ' / ' + tick(detail.action_finish_tick)}/>
    <DataRow label="Verification status" value={detail.verification_detail?.status || 'Not recorded'}/>
    <DataRow label="Verification outcome" value={detail.verification_detail?.outcome || 'Not recorded'}/>
    <DataRow label="Verification summary" value={detail.verification_detail?.summary || 'Not recorded'}/>
    <DataRow label="Verification tick" value={tick(detail.verification_detail?.observed_tick)}/>
    <DataRow label="Verification evidence IDs" value={ids(detail.verification_detail?.evidence_ids)}/>
  </Panel>;
}
