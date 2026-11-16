import { useState } from 'react';
import { BookOpen, BrainCircuit, FileText, FlaskConical,
  GitCompareArrows, History, Search, ShieldCheck } from 'lucide-react';
import { useUi } from '../context';
import { useResource } from '../api';
import { useEvaluations } from '../pageData';
import { ManagedRunLauncher, ManagedRunList } from './managed';
export { RunDetailPage } from './managed';
import type { Evaluation, ListResponse, Scorecard } from '../types';
import { DataRow, formatNumber, InfoState, Metric, PageHeading, Panel, Pill,
  SummaryLink, TileLink, toneFor, Unavailable } from '../ui';

function RunTable({ items }: { items: Evaluation[] }) {
  return <div className="data-table">
    <div className="eval-table-head"><span>Run</span><span>Scenario</span><span>Assessment</span><span>Time</span><span>Tools</span></div>
    {items.map(r => <div className="eval-table-row" key={r.id}>
      <div><strong>{r.id}</strong><small>{r.conclusion || 'No conclusion recorded'}</small></div>
      <span>{r.scenario || 'Unknown'}</span><Pill text={r.assessment || 'Unjudged'} tone={toneFor(r.assessment)}/>
      <span>{r.wall_seconds == null ? '—' : r.wall_seconds.toFixed(1) + 's'}</span>
      <span>{r.tool_count ?? '—'}</span>
    </div>)}
  </div>;
}
export function LabPage() {
  const { workspace, preview } = useUi();
  return <>
    <PageHeading eyebrow="RESEARCH / SIMULATOR" title="Experiment lab"
      description="Reproducible scenarios, deterministic triage, deep investigations and evidence-based evaluation."
      right={<Pill text={workspace==='pilot'?'SIMULATOR ONLY':preview?'SYNTHETIC PREVIEW':'MANAGED PYTHON RUNNER'}
        tone="warning"/>}/>
    <ManagedRunLauncher />
    <Panel title="Research workflow" subtitle="Python remains the source of truth">
      {[
        ['Seeded environment','Hidden simulator causes stay outside investigator evidence'],
        ['Evidence collection','Deterministic triage or Pydantic Graph'],
        ['Human review','Approve/reject simulated actions under existing rules'],
        ['Verification','Compare observed results, not model confidence'],
        ['Independent evaluation','Only evaluator-authorized views may use labels'],
      ].map(([a,b],i)=><div className="process-step" key={a}>
        <span>{'0'+(i+1)}</span><div><strong>{a}</strong><p>{b}</p></div>
      </div>)}
    </Panel>
    <div className="tile-grid compact-tiles">
      <TileLink to="/lab/runs" icon={<History size={24}/>} title="Run history" description="Browse existing offline experiment records."/>
      <TileLink to="/lab/evaluations" icon={<FlaskConical size={24}/>} title="Evaluation" description="Inspect recorded metrics and outstanding correctness gates."/>
      <TileLink to="/lab/compare" icon={<GitCompareArrows size={24}/>} title="Compare runs" description="Place two experiment records side by side."/>
    </div>
  </>;
}
export function RunsPage() {
  const {items,error}=useEvaluations();
  return <><PageHeading eyebrow="RESEARCH / HISTORY" title="Run history"
    description="Persisted experiments are read-only and evaluator-gated." right={<SummaryLink to="/lab/compare" label="Compare runs"/>}/>
    <div className="metric-grid">
      <Metric label="Accessible runs" value={items.length||null} note="Authorized JSONL records"/>
      <Metric label="Wall time recorded" value={items.length?items.filter(i=>i.wall_seconds!=null).length:null} note="No invented runtimes"/>
      <Metric label="Model counts recorded" value={items.length?items.filter(i=>i.model_questions!=null).length:null} note="May be unavailable"/>
      <Metric label="Live worker" value={null} note="Not integrated"/>
    </div><ManagedRunList/><Panel title="Offline experiment records" subtitle="Available evaluation artifacts only">
      {error&&<InfoState kind="warning" title="Evaluator access unavailable" detail={error}/>}
      {items.length?<RunTable items={items}/>:<Unavailable item="Run history" detail="Configure the approved experiment file, evaluator access and token; or enter clearly marked synthetic preview."/>}
    </Panel></>;
}
export function EvaluationPage() {
  const {items}=useEvaluations();
  const {token, preview, workspace}=useUi();
  const score = useResource<ListResponse<Scorecard>>(
    workspace === 'simulator' && !preview ? '/api/v1/evaluations/scorecards?workspace=simulator' : null,
    token, workspace !== 'simulator' || preview,
  );
  const judged = score.data?.items.filter(x=>x.judged) || [];
  const unjudged = score.data?.items.filter(x=>!x.judged) || [];
  return <><PageHeading eyebrow="RESEARCH / SCORING" title="Evaluation"
    description="Correctness, abstention and verification are separate from model confidence."/>
    <div className="metric-grid">
      <Metric label="Judged outcomes" value={score.data ? judged.length : null} note="Evaluator-only labels"/>
      <Metric label="Unjudged outcomes" value={score.data ? unjudged.length : null} note="Not counted as incorrect"/>
      <Metric label="Correct diagnoses" value={score.data ? judged.filter(i=>i.fault_correct===true).length : null}
        note="Within judged records"/>
      <Metric label="Failed verification" value={score.data ?
        judged.filter(i=>i.resolved===false).length : null} note="Recorded simulator outcomes"/>
    </div>
    <div className="two-column uneven">
      <Panel title="Evaluation results" subtitle="Safe experiment run summaries">
        {items.length ? <RunTable items={items}/> : <Unavailable item="Evaluation results"/>}
      </Panel>
      <Panel title="Scorecard acceptance criteria" subtitle="Python scoring owns correctness and hidden truth">
        {[
          ['Cause and target correctness', 'Missing human judgement stays unjudged'],
          ['Recommendation and intervention', 'Approval is not execution'],
          ['Evidence coverage', 'Only measured evidence counts'],
          ['Verified outcome', 'Simulator observation after action'],
          ['Latency and tool cost', 'Matched scenarios and timing policies'],
          ['Calibration', 'Distinguish abstention from confident errors'],
        ].map(([label,detail])=><div className="quality-check" key={label}>
          <span className="check-ring"/><div><strong>{label}</strong><small>{detail}</small></div>
        </div>)}
        <div className="soft-note">No raw simulator ground truth is serialized by this view.</div>
      </Panel>
    </div>
    <Panel title="Evaluator-only scorecards" subtitle="Correctness flags are protected separately from ordinary investigation evidence">
      {score.error && <InfoState kind="warning" title="Evaluator authorization required" detail={score.error}/>}
      {score.data?.items.length ? score.data.items.map(item=><div className="settings-row" key={item.id}>
        <div><strong>{item.id}</strong><small>{item.judged ? 'Judged' : 'Unjudged'}</small></div>
        <div><Pill text={item.fault_correct == null ? 'Unjudged' : item.fault_correct ? 'Correct' : 'Incorrect'}
          tone={item.fault_correct == null ? 'neutral' : item.fault_correct ? 'good' : 'warning'}/></div>
        <div>Action: {item.action_correct == null ? 'unknown' : item.action_correct ? 'correct' : 'incorrect'}</div>
        <div>Resolved: {item.resolved == null ? 'unknown' : item.resolved ? 'yes' : 'no'}</div>
      </div>) : <Unavailable item="Evaluator scorecards" detail="Enable the evaluator role and configure an approved experiment record file."/>}
    </Panel>
  </>;
}
export function ComparePage() {
  const {items}=useEvaluations();
  const [left,setLeft]=useState(''),[right,setRight]=useState('');
  const a=items.find(i=>i.id===(left||items[0]?.id)), b=items.find(i=>i.id===(right||items[1]?.id));
  const matched = Boolean(a && b && a.scenario === b.scenario && a.seed === b.seed);
  return <><PageHeading eyebrow="RESEARCH / COMPARISON" title="Compare runs"
    description="Compare matched scenarios and seeds; timing alone is never proof of diagnostic quality."/>
    {items.length>1?<div className="two-column">
      {[{title:'Run A',run:a,value:left,set:setLeft},{title:'Run B',run:b,value:right,set:setRight}].map(x=>
        <Panel key={x.title} title={x.title} subtitle="Recorded experiment result">
          <label className="field-label" htmlFor={x.title}>{x.title}</label>
          <select id={x.title} value={x.value||x.run?.id} onChange={e=>x.set(e.target.value)}>
            {items.map(i=><option value={i.id} key={i.id}>{i.id}</option>)}</select>
          {x.run&&<><DataRow label="Scenario" value={x.run.scenario||'Unknown'}/>
            <DataRow label="Seed" value={x.run.seed??'Unknown'}/>
            <DataRow label="Path" value={x.run.mode||'Unknown'}/>
            <DataRow label="Triage assessment" value={x.run.triage_assessment||'Not recorded'}/>
            <DataRow label="Deep escalation" value={x.run.triage_deep_ran == null ?
              'Not recorded' : x.run.triage_deep_ran ? 'Yes' : 'No'}/>
            <DataRow label="Assessment" value={<Pill text={x.run.assessment||'Unjudged'} tone={toneFor(x.run.assessment)}/>}/>
            <DataRow label="Wall seconds" value={x.run.wall_seconds==null?'N/A':formatNumber(x.run.wall_seconds,2)}/>
            <DataRow label="Triage seconds" value={x.run.triage_seconds==null?'N/A':formatNumber(x.run.triage_seconds,2)}/>
            <DataRow label="Tool calls" value={x.run.tool_count??'N/A'}/>
            <DataRow label="Model questions" value={x.run.model_questions??'N/A'}/>
            <DataRow label="Model outage attempts" value={x.run.model_failures??'N/A'}/></>}
        </Panel>)}</div>:
      <Unavailable item="Comparison" detail="At least two evaluator-authorized records are required."/>}
    {a&&b&&<Panel title="Comparison validity" subtitle="Only valid matched comparisons support a performance claim">
      <Pill text={matched ? 'Scenario and seed match' : 'Not matched'} tone={matched ? 'info' : 'warning'}/>
      <p className="body-copy">{matched ?
        'Scenario and seed match, but model routes, settings and evaluator version still require confirmation.' :
        'These records differ in scenario or seed; their latency and accuracy should not be ranked against each other.'}</p>
      <DataRow label="Wall-time delta (A − B)" value={matched && a.wall_seconds!=null && b.wall_seconds!=null ?
        (a.wall_seconds-b.wall_seconds).toFixed(2)+' s' : 'Not comparable'}/>
    </Panel>}</>;
}
export function KnowledgePage() {
  return <><PageHeading eyebrow="RESEARCH / KNOWLEDGE" title="Knowledge" description="Manual sources, case history and long-term learning stay traceable."/>
    <div className="tile-grid compact-tiles">
      <TileLink to="/knowledge/manuals" icon={<BookOpen size={24}/>} title="Manual library" description="Version-matched technical references and citations."/>
      <TileLink to="/knowledge/memory" icon={<BrainCircuit size={24}/>} title="Episodic memory" description="Verified outcomes and rejected alternatives."/>
      <TileLink to="/investigations" icon={<FileText size={24}/>} title="Investigation history" description="Open the source records behind any learned case."/>
    </div><Panel title="Source boundaries" subtitle="Synthetic and real-machine knowledge are not interchangeable">
      <DataRow label="Simulator manual" value="Simulator investigations only"/>
      <DataRow label="Prestige manual" value="Requires approved OEM/version-specific source"/>
      <DataRow label="Historical diagnosis" value="Claim, not automatically verified machine fact"/>
    </Panel></>;
}
type ManualSection = {citation:string;section_id:string;title:string;revision:string;text:string};
export function ManualsPage() {
  const {token,preview,workspace}=useUi();
  const [query,setQuery]=useState(''),[submitted,setSubmitted]=useState('');
  const active=workspace==='simulator'&&!preview;
  const path='/api/v1/knowledge/manuals?workspace=simulator'+
    (submitted?'&q='+encodeURIComponent(submitted):'');
  const resource=useResource<ListResponse<ManualSection>>(active?path:null,token,!active);
  return <><PageHeading eyebrow="KNOWLEDGE / REFERENCES" title="Manual library"
    description="Source-matched, cited manual sections; simulator documentation never authorizes a pilot intervention."/>
    <Panel title="Simulator manual search" subtitle="Validated keyword search over SIM-CNC-001">
      {workspace==='pilot'? <InfoState kind="warning" title="OEM manual not authorized"
        detail="A Siemens manual must be controller- and revision-matched before it may be used for pilot diagnosis."/>:
      <div className="search-field-wide"><Search size={19}/><input value={query}
        onChange={e=>setQuery(e.target.value)} maxLength={120}
        onKeyDown={e=>{if(e.key==='Enter')setSubmitted(query.trim());}}
        placeholder="Search by sensor, alarm, or maintenance topic" aria-label="Manual search term"/>
        <button className="button-secondary" type="button" disabled={!active}
          onClick={()=>setSubmitted(query.trim())}>Search local manual</button></div>}
      {resource.error && <InfoState kind="warning" title="Manual API unavailable" detail={resource.error}/>}
      {active && resource.data?.items.length ? resource.data.items.map(item=>
        <div className="hypothesis-card" key={item.citation}>
          <span className="eyebrow">{item.citation} · Rev {item.revision}</span>
          <h3>{item.title}</h3><p>{item.text}</p>
        </div>): <Unavailable item="Manual sections" detail="No approved matching sections or the API has not loaded the local manual."/>}
    </Panel>
    <Panel title="Reference gate" subtitle="Never transfer a simulator manual to the Prestige machine without field verification">
      <DataRow label="Document identity" value="SIM-CNC-001, simulator only"/>
      <DataRow label="Controller match" value="Pilot: not verified"/>
      <DataRow label="Revision compatibility" value="Pilot: not verified"/>
      <DataRow label="Citation" value="Exact section and document revision"/>
    </Panel></>;
}
export function MemoryPage() {
  const {preview}=useUi();
  return <><PageHeading eyebrow="KNOWLEDGE / LONG TERM" title="Episodic memory"
    description="Experience is useful only with evidence, outcome and correction history."/>
    <div className="metric-grid">
      <Metric label="Connected cases" value={null} note="No memory read adapter"/>
      <Metric label="Verified lessons" value={null} note="Technician signoff for real machines"/>
      <Metric label="Rejected promotions" value={null} note="Review records unavailable"/>
      <Metric label="Source lineage" value={null} note="Must be preserved"/>
    </div><div className="two-column">
      <Panel title="Case library" subtitle="No anonymous or invented memory cases">
        {preview?<div className="manual-preview"><Pill text="SYNTHETIC LAYOUT" tone="warning"/>
          <h3>Case card placeholder</h3><p>Symptoms, alternatives, action, result and verifier would appear here. No memory case is loaded.</p></div>:
          <Unavailable item="Episodic memory listing" detail="The Python memory service does not yet expose an authorized local list/search API."/>}
      </Panel>
      <Panel title="Promotion criteria" subtitle="Learning is not confidence accumulation">
        {['Source investigation','Evidence and rejected hypotheses','Outcome of intervention',
          'Independent verification','Permission and retention'].map((item,i)=>
          <div className="process-step" key={item}><span>{'0'+(i+1)}</span><div><strong>{item}</strong></div></div>)}
        <div className="soft-note"><ShieldCheck size={18}/> A model conclusion is not independently confirmed field truth.</div>
      </Panel>
    </div></>;
}
