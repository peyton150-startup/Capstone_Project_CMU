import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Activity, ArrowRight, BrainCircuit, CheckCheck, ChevronRight,
  ClipboardCheck, FileSearch, ShieldAlert,
  ShieldCheck, Workflow,
} from 'lucide-react';
import { useResource } from '../api';
import { useUi } from '../context';
import { demoInvestigations } from '../preview';
import { useInvestigations } from '../pageData';
import type { Evidence, Investigation, InvestigationDetail } from '../types';
import {
  DataRow, formatNumber, InfoState, PageHeading, Panel, Pill,
  SummaryLink, toneFor, Unavailable,
} from '../ui';

function InvestigationRows({ items }: { items: Investigation[] }) {
  return <div className="incident-list">
    {items.map(item => <Link className="incident-row" key={item.id} to={'/investigations/' + item.id}>
      <span className="incident-icon"><BrainCircuit size={22}/></span>
      <div className="incident-body"><span className="incident-id">{item.id}</span><h3>{item.summary}</h3>
        <p>{item.diagnosis || 'No diagnosis supported from the available evidence'}</p></div>
      <div className="incident-meta"><Pill text={item.verification || 'Unverified'} tone={toneFor(item.verification)}/>
        <small>{item.evidence_count} evidence items</small></div><ChevronRight size={18}/>
    </Link>)}
  </div>;
}
export function InvestigationListPage() {
  const { items, error } = useInvestigations();
  const { workspace } = useUi();
  return <>
    <PageHeading eyebrow="DIAGNOSIS / INVESTIGATIONS" title="Investigations"
      description="From abnormal signal to a supported—or explicitly unresolved—conclusion."
      right={<SummaryLink to="/investigations/triage" label="Rapid triage" />}/>
    <div className="metric-grid">
      <div className="metric-card"><div className="metric-top">Recorded investigations <BrainCircuit size={17}/></div>
        <strong>{workspace === 'pilot' ? '—' : items.length || '—'}</strong><div className="metric-note">Only persisted, authorized records</div></div>
      <div className="metric-card"><div className="metric-top">Evidence-first analysis <FileSearch size={17}/></div>
        <strong>{items.length ? formatNumber(items.reduce((n, x) => n + x.evidence_count,0)) : '—'}</strong>
        <div className="metric-note">Cited evidence in available records</div></div>
      <div className="metric-card"><div className="metric-top">Verified interventions <CheckCheck size={17}/></div>
        <strong>{items.length ? items.filter(x => x.verification === 'verified').length : '—'}</strong>
        <div className="metric-note">Not inferred from model confidence</div></div>
      <div className="metric-card"><div className="metric-top">Model confidence <ShieldAlert size={17}/></div>
        <strong>Uncalibrated</strong><div className="metric-note">Rating is separate from evidence support</div></div>
    </div>
    <Panel title="Recorded cases" subtitle="Each case opens source-linked evidence and verification detail">
      {error && <InfoState kind="warning" title="Audit unavailable" detail={error}/>}
      {items.length ? <InvestigationRows items={items}/> : <Unavailable item="Investigation history"
        detail={workspace === 'pilot' ? 'Real-machine diagnoses remain disabled until field authorization and evidence acceptance.' :
          'Point the local API at an approved completed-investigation audit file or enter the explicit synthetic preview.'}/>}
    </Panel>
    <div className="three-column-link">
      <Link className="feature-row-link" to="/investigations/triage"><Activity size={21}/><div><strong>Rapid triage</strong><small>Questions, checks and conservative clearance</small></div><ArrowRight size={18}/></Link>
      <Link className="feature-row-link" to="/investigations/deep"><Workflow size={21}/><div><strong>Deep reasoning</strong><small>Investigation stages and hypotheses</small></div><ArrowRight size={18}/></Link>
      <Link className="feature-row-link" to="/investigations/review"><ClipboardCheck size={21}/><div><strong>Human review</strong><small>Actions, approval and verification boundaries</small></div><ArrowRight size={18}/></Link>
    </div>
  </>;
}
export function TriagePage() {
  const { preview, workspace } = useUi();
  const { items } = useInvestigations();
  return <>
    <PageHeading eyebrow="INVESTIGATIONS / DETERMINISTIC PATH" title="Rapid triage"
      description="A deliberately bounded investigation; code verifies evidence before the model's recommendation can clear."/>
    <div className="stage-strip"><span className="stage-pill">Observe</span><ArrowRight size={16}/>
      <span className="stage-pill">Plan</span><ArrowRight size={16}/>
      <span className="stage-pill">Investigate</span><ArrowRight size={16}/>
      <span className="stage-pill">Test</span><ArrowRight size={16}/>
      <span className="stage-pill stage-highlight">Conclude + checks</span></div>
    <div className="two-column uneven">
      <Panel title="Triage outcomes" subtitle="Never turn a successful tool call into a resolved question">
        {preview ? <><div className="triage-outcome"><Pill text="UNRESOLVED / ESCALATE" tone="warning"/>
          <h3>Temperature and load changed, but causality is not established.</h3>
          <p>The candidate explanation does not clear independent verification.
            Further machine-matched measurements are needed.</p></div>
          <DataRow label="Evidence collected" value="4 source-linked observations"/>
          <DataRow label="Question verdict" value={<Pill text="Held open" tone="warning"/>}/>
          <DataRow label="Recommended next check" value="Compare matching cutting cycles"/>
          <DataRow label="Deeper investigation" value="Recommended"/>
          <p className="body-copy"><strong>Synthetic example.</strong> Real triage-specific reports are not retained
            in the current general completion audit.</p>
        </> : <Unavailable item="Typed triage report" detail={workspace === 'pilot' ?
          'Physical-machine diagnosis remains gated by field validation.' :
          'TriageReport requires its own persisted read model. Existing completion audits cannot reconstruct all triage questions and predicate verdicts.'}/>}
      </Panel>
      <Panel title="Clearance policy" subtitle="Why a decision may remain unresolved">
        {[
          ['Observed coverage', 'Each required signal has an actual valid observation'],
          ['Question verdict', 'Code confirms the specific predicate, not just tool success'],
          ['Provenance', 'The claim cites real, relevant evidence'],
          ['Counterevidence', 'Conflicting and missing signals remain visible'],
          ['Time budget', 'A timeout never becomes evidence of normal operation'],
        ].map(([title, text],i) => <div className="process-step" key={title}>
          <span>{'0'+(i+1)}</span><div><strong>{title}</strong><p>{text}</p></div></div>)}
      </Panel>
    </div>
    <Panel title="Available investigations" subtitle="General completion records; not a replacement for TriageReport">
      {items.length ? <InvestigationRows items={items}/> : <Unavailable item="Recorded triage cases"/>}
    </Panel>
  </>;
}
export function DeepPage() {
  const { preview } = useUi();
  const { items } = useInvestigations();
  const stages = ['Observe','Manual','Plan','Investigate','Hypothesize','Test','Critique','Recheck','Conclude','Propose','Execute','Verify'];
  return <>
    <PageHeading eyebrow="INVESTIGATIONS / AGENT WORKFLOW" title="Deep investigations"
      description="Pydantic Graph orchestration, evidence-linked hypotheses and human-reviewed outcomes."/>
    <Panel title="Investigation lifecycle" subtitle="Possible stages; actual execution must be sourced from recorded trace">
      <div className="lifecycle-grid">{stages.map((stage,i)=>
        <div key={stage} className="lifecycle-step"><span>{String(i+1).padStart(2,'0')}</span><strong>{stage}</strong>
          <small>{['Manual','Critique','Recheck','Execute'].includes(stage) ? 'Conditional stage' : 'Workflow stage'}</small></div>)}</div>
      <div className="soft-note">{preview ? 'Lifecycle layout example; this is not a traced live run.' :
        'The existing completion audit does not persist every live graph transition or triage-only detail. No stage is marked executed without its own event.'}</div>
    </Panel>
    <Panel title="Past investigations" subtitle="Open a case for recorded evidence, hypotheses and verification">
      {items.length ? <InvestigationRows items={items}/> : <Unavailable item="Deep investigation records"/>}
    </Panel>
  </>;
}
export function ReviewPage() {
  const { workspace, preview } = useUi();
  const [decision, setDecision] = useState<'none'|'approved'|'rejected'>('none');
  return <>
    <PageHeading eyebrow="INVESTIGATIONS / HUMAN OVERSIGHT" title="Review & verification"
      description="Proposing, authorizing, executing and verifying are distinct states."/>
    <div className="two-column uneven">
      <Panel title="Action-review desk" subtitle="Simulator-only authorization boundary">
        {workspace === 'pilot' ? <InfoState kind="warning" title="No physical-machine controls"
          detail="The Prestige pilot is strictly read-only. Approvals, CNC writes, resets or commanded movements cannot be initiated from this interface."/> :
          preview ? <div className="approval-preview">
            <Pill text="SYNTHETIC REVIEW EXAMPLE" tone="warning"/>
            <h3>Inspect spindle load and cooling conditions</h3>
            <p>Human review is required before any simulated intervention; recommendation alone is not execution.</p>
            <DataRow label="Evidence" value="E-01, E-02"/>
            <DataRow label="Execution state" value="Not executed"/>
            <div className="approval-actions"><button className="button-primary" onClick={()=>setDecision('approved')}>Preview approval</button>
              <button className="button-secondary" onClick={()=>setDecision('rejected')}>Preview rejection</button></div>
            <div className="soft-note">UI preview decision: {decision}. Nothing is sent to the backend, persisted or executed.</div>
          </div> : <Unavailable item="Simulator approval bridge"
            detail="The backend has an ApprovalDesk, but this API does not yet host a managed run worker and secure, persistent human-review bridge. Approve/reject remains unavailable."/>}
      </Panel>
      <Panel title="Verification lifecycle" subtitle="An approved action is not a successful repair">
        {[
          ['Proposal received','Agent recommendation with machine and evidence references'],
          ['Human decision','Approve or reject under backend rules'],
          ['Simulation execution','Only the original simulator approval desk may execute'],
          ['Result verification','Compare actual observations with expected effect'],
          ['Final disposition','Verified, failed or unresolved—never silently assumed'],
        ].map(([a,b],i)=><div className="process-step" key={a}><span>{'0'+(i+1)}</span>
          <div><strong>{a}</strong><p>{b}</p></div></div>)}
      </Panel>
    </div>
    <Panel title="Review guidance" subtitle="The critical engineering distinction">
      <div className="rule-columns">
        <div><ShieldAlert size={24}/><h3>Not enough evidence</h3><p>Escalation is a legitimate outcome. Show the next discriminating check.</p></div>
        <div><ShieldCheck size={24}/><h3>Evidence checked</h3><p>Source IDs, numerical predicates and time windows must support a claim.</p></div>
        <div><ClipboardCheck size={24}/><h3>Independent verification</h3><p>Only observed outcomes, not the model's stated confidence, establish success.</p></div>
      </div>
    </Panel>
  </>;
}

export function InvestigationDetailPage() {
  const { id } = useParams();
  const { preview, token, workspace } = useUi();
  const resource = useResource<InvestigationDetail>(
    id && !preview ? '/api/v1/investigations/' + encodeURIComponent(id) + '?workspace=' + workspace : null,
    token, preview || !id);
  const item = preview ? demoInvestigations.find(x=>x.id===id) : resource.data;
  const [tab,setTab] = useState('evidence');
  const [selectedEvidence,setSelectedEvidence] = useState<Evidence|null>(null);
  if (!item) return <><PageHeading eyebrow="INVESTIGATIONS / DETAIL" title="Investigation detail"/>
    <InfoState title="No authorized investigation detail" detail={resource.error || 'Select an available investigation; a missing case is not the same as a confirmed normal machine.'}
      action={<Link className="text-link" to="/investigations">Back to investigations <ArrowRight size={16}/></Link>}/></>;
  const sections = [['evidence','Evidence'],['hypotheses','Hypotheses'],['checks','Questions & tests'],
    ['conclusion','Conclusion'],['actions','Actions & verification'],['trace','Technical trace']];
  return <>
    <PageHeading eyebrow={'INVESTIGATIONS / ' + item.id} title={item.summary}
      description={item.termination_reason || 'Termination reason unavailable'}
      right={<Pill text={item.verification || 'Unverified'} tone={toneFor(item.verification)}/>}/>
    <div className="investigation-lead">
      <div><span className="eyebrow">LEADING EXPLANATION</span>
        <h2>{item.diagnosis || 'No supported diagnosis recorded'}</h2>
        <p>The conclusion shown here is an agent statement. Evidence and independent verification are assessed separately.</p></div>
      <div className="conclusion-quick"><span>MODEL RATING</span>
        <strong>{item.model_confidence == null ? '—' : Math.round(item.model_confidence*100) + '/100'}</strong>
        <small>Not a calibrated fault probability</small></div>
    </div>
    <div className="metric-grid">
      <div className="metric-card"><div className="metric-top">Evidence items</div><strong>{item.evidence_count}</strong><div className="metric-note">Recorded sources</div></div>
      <div className="metric-card"><div className="metric-top">Hypotheses</div><strong>{item.hypothesis_count}</strong><div className="metric-note">Candidate explanations</div></div>
      <div className="metric-card"><div className="metric-top">Tool calls</div><strong>{item.tool_calls ?? '—'}</strong><div className="metric-note">Recorded agent activity</div></div>
      <div className="metric-card"><div className="metric-top">Verification</div><strong className="small-strong">{item.verification || 'Unknown'}</strong><div className="metric-note">Actual outcome, not recommendation</div></div>
    </div>
    <div className="content-tabs" role="tablist" aria-label="Investigation sections">
      {sections.map(([key,label])=><button role="tab" aria-selected={tab===key} className={tab===key?'current':''}
        key={key} onClick={()=>setTab(key)}>{label}</button>)}
    </div>
    {tab==='evidence' && <Panel title="Source-linked observations" subtitle="Select evidence to inspect exact recorded content">
      {item.evidence.length ? <div className="evidence-grid">{item.evidence.map(e =>
        <button key={e.id} onClick={()=>setSelectedEvidence(e)} className="evidence-card">
          <span className="evidence-top"><span>{e.id}</span><FileSearch size={18}/></span>
          <strong>{e.source_id || e.source_type || 'Unknown source'}</strong>
          <p>{e.content || 'No recorded content'}</p><small>Observation {e.observed_tick == null ? 'time unknown' : 'tick ' + e.observed_tick}</small>
        </button>)}</div> : <Unavailable item="Evidence payload"/>}
    </Panel>}
    {tab==='hypotheses' && <Panel title="Competing explanations" subtitle="Sources and discriminating checks stay visible">
      {item.hypotheses.length ? item.hypotheses.map(h=><div className="hypothesis-card" key={h.id}>
        <div className="hypothesis-title"><span className="hypothesis-id">{h.id}</span><h3>{h.description || h.claim || 'Hypothesis'}</h3>
          <Pill text={h.status || 'unverified'} tone={toneFor(h.status)}/></div>
        <div className="hypothesis-sources"><span>Supporting: {(h.supporting_evidence_ids||[]).join(', ')||'None recorded'}</span>
          <span>Contradicting: {(h.contradicting_evidence_ids||[]).join(', ')||'None recorded'}</span></div>
        <p><strong>Discriminating check:</strong> {h.discriminating_check || 'Not recorded'}</p>
      </div>) : <Unavailable item="Hypothesis history"/>}
    </Panel>}
    {tab==='checks' && <Panel title="Question and predicate checks" subtitle="No inferred test result from a successful read">
      <InfoState title="Detailed predicates not persisted in this record"
        detail="The general completed-investigation audit does not preserve every triage question, test verdict or conclusion-check trace. Only an explicit typed source may populate this view."/>
    </Panel>}
    {tab==='conclusion' && <Panel title="Conclusion & evidence" subtitle="A model rating is not an empirical probability">
      <DataRow label="Diagnosis" value={item.diagnosis||'Unresolved'}/>
      <DataRow label="Termination" value={item.termination_reason||'Not recorded'}/>
      <DataRow label="Verification" value={item.verification||'Unknown'}/>
      <DataRow label="Model rating" value={item.model_confidence==null?'Unknown':String(item.model_confidence)}/>
      <InfoState kind="warning" title="Source verification remains independent"
        detail="Only actual numerical evidence checks and later observations establish whether a claim or intervention holds."/>
    </Panel>}
    {tab==='actions' && <Panel title="Action proposal and outcome" subtitle="Pilot mode has no physical action surface">
      <DataRow label="Proposal" value={item.proposed_action?.action||'No action proposed'}/>
      <DataRow label="Reason" value={item.proposed_action?.reason||'Not recorded'}/>
      <DataRow label="Execution" value="Not inferred from proposal"/>
      <DataRow label="Verification" value={item.verification_detail?.status||'Unverified'}/>
      <DataRow label="Outcome" value={item.verification_detail?.summary||'No independent outcome recorded'}/>
      <Link to="/investigations/review" className="text-link">Review policy <ArrowRight size={16}/></Link>
    </Panel>}
    {tab==='trace' && <Panel title="Technical trace" subtitle="Detailed records require a separate authorized persistence adapter">
      <DataRow label="Run ID" value={item.run_id||'Unknown'}/>
      <DataRow label="Investigation ID" value={item.id}/>
      <DataRow label="Iterations" value={item.iterations??'Unknown'}/>
      <DataRow label="Tool calls" value={item.tool_calls??'Unknown'}/>
      <InfoState title="Full audit trace not exposed"
        detail="The existing audit may include private evidence, provider requests and model decisions. The API intentionally exposes only a strict projection rather than returning the whole audit record."/>
    </Panel>}
    {selectedEvidence && <div className="drawer-backdrop" onClick={()=>setSelectedEvidence(null)}>
      <aside className="evidence-drawer" role="dialog" aria-modal="true" aria-label="Evidence detail"
        onClick={e=>e.stopPropagation()}>
        <button className="close-drawer" onClick={()=>setSelectedEvidence(null)}>Close ✕</button>
        <span className="eyebrow">SOURCE / {selectedEvidence.id}</span>
        <h2>{selectedEvidence.source_id||'Observation'}</h2>
        <p>{selectedEvidence.content||'No content'}</p>
        <DataRow label="Source type" value={selectedEvidence.source_type||'Unknown'}/>
        <DataRow label="Observed at" value={selectedEvidence.observed_at||'Not recorded'}/>
        <DataRow label="Simulator tick" value={selectedEvidence.observed_tick??'Not recorded'}/>
      </aside>
    </div>}
  </>;
}
