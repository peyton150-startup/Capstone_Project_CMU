import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen, BrainCircuit, Database, FileText, FlaskConical,
  GitCompareArrows, History, Play, Search, ShieldCheck } from 'lucide-react';
import { useUi } from '../context';
import { useEvaluations } from '../pageData';
import type { Evaluation } from '../types';
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
  const [seed,setSeed] = useState('3'), [mode,setMode] = useState('triage');
  return <>
    <PageHeading eyebrow="RESEARCH / SIMULATOR" title="Experiment lab"
      description="Reproducible scenarios, deterministic triage, deep investigations and evidence-based evaluation."
      right={<Pill text={workspace==='pilot'?'SIMULATOR ONLY':preview?'SYNTHETIC PREVIEW':'WORKER NOT CONNECTED'} tone="warning"/>}/>
    <div className="two-column uneven">
      <Panel title="Experiment setup" subtitle="Requires a managed Python runner and per-run validated settings">
        {workspace==='pilot'? <InfoState kind="warning" title="Not available for real equipment"
          detail="The Prestige pilot is read-only; no simulator actions are exposed in this environment."/>:
        <><div className="form-grid"><div><label className="field-label" htmlFor="seed">Scenario seed</label>
          <input id="seed" value={seed} onChange={e=>setSeed(e.target.value)} inputMode="numeric"/></div>
          <div><label className="field-label" htmlFor="mode">Investigation mode</label>
            <select id="mode" value={mode} onChange={e=>setMode(e.target.value)}>
              <option value="triage">Rapid triage</option><option value="deep">Full investigation</option></select></div></div>
          <DataRow label="Seed" value={seed||'Unset'}/><DataRow label="Selected mode" value={mode}/>
          <div className="blocked-action"><button className="button-primary" disabled><Play size={17}/> Start experiment</button>
            <p>Not executable yet. The FastAPI service deliberately has no unmanaged simulator worker or approval bypass.</p></div></>}
      </Panel>
      <Panel title="Research workflow" subtitle="Existing Python remains the source of truth">
        {[
          ['Seeded environment','Hidden simulator causes stay outside investigator evidence'],
          ['Evidence collection','Deterministic triage or Pydantic Graph'],
          ['Human review','Approve/reject simulated actions under existing rules'],
          ['Verification','Compare observed results, not model confidence'],
          ['Independent evaluation','Only evaluator-authorized views may use labels'],
        ].map(([a,b],i)=><div className="process-step" key={a}><span>{'0'+(i+1)}</span>
          <div><strong>{a}</strong><p>{b}</p></div></div>)}
      </Panel>
    </div>
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
    </div><Panel title="Run journal" subtitle="Available evaluation artifacts only">
      {error&&<InfoState kind="warning" title="Evaluator access unavailable" detail={error}/>}
      {items.length?<RunTable items={items}/>:<Unavailable item="Run history" detail="Configure the approved experiment file, evaluator access and token; or enter clearly marked synthetic preview."/>}
    </Panel></>;
}
export function EvaluationPage() {
  const {items}=useEvaluations();
  return <><PageHeading eyebrow="RESEARCH / SCORING" title="Evaluation" description="Evidence, cause correctness and outcomes have different measurement requirements."/>
    <div className="two-column uneven">
      <Panel title="Evaluation results" subtitle="Safe run summaries, not full evaluator truth">
        {items.length?<RunTable items={items}/>:<Unavailable item="Evaluation results"/>}
      </Panel>
      <Panel title="Scoring dimensions" subtitle="Python owns scoring and ground-truth comparison">
        {[
          ['Diagnosis and target correctness','Judged labels only; unjudged is not incorrect'],
          ['Recommendation and intervention','Human approval is not execution'],
          ['Evidence quality','Supported, contradicted and unresolved claims'],
          ['Verification','Observed outcome after authorized intervention'],
          ['Latency and tool cost','Compare on matched scenarios'],
          ['Calibration','Track false reassurance and abstention'],
        ].map(([a,b])=><div className="quality-check" key={a}><span className="check-ring"/>
          <div><strong>{a}</strong><small>{b}</small></div></div>)}
        <div className="soft-note">The API excludes raw ExperimentRecord.score because it may contain simulator hidden truth. A full scorecard requires a separately authorized read model.</div>
      </Panel>
    </div></>;
}
export function ComparePage() {
  const {items}=useEvaluations();
  const [left,setLeft]=useState(''),[right,setRight]=useState('');
  const a=items.find(i=>i.id===(left||items[0]?.id)), b=items.find(i=>i.id===(right||items[1]?.id));
  return <><PageHeading eyebrow="RESEARCH / COMPARISON" title="Compare runs"
    description="Compare observed metrics; different seeds or scenarios are not interchangeable."/>
    {items.length>1?<div className="two-column">
      {[{title:'Run A',run:a,value:left,set:setLeft},{title:'Run B',run:b,value:right,set:setRight}].map(x=>
        <Panel key={x.title} title={x.title} subtitle="Recorded result">
          <label className="field-label" htmlFor={x.title}>{x.title}</label>
          <select id={x.title} value={x.value||x.run?.id} onChange={e=>x.set(e.target.value)}>
            {items.map(i=><option value={i.id} key={i.id}>{i.id}</option>)}</select>
          {x.run&&<><DataRow label="Scenario" value={x.run.scenario||'Unknown'}/>
            <DataRow label="Seed" value={x.run.seed??'Unknown'}/>
            <DataRow label="Assessment" value={<Pill text={x.run.assessment||'Unjudged'} tone={toneFor(x.run.assessment)}/>}/>
            <DataRow label="Wall seconds" value={x.run.wall_seconds==null?'N/A':formatNumber(x.run.wall_seconds,2)}/>
            <DataRow label="Tool calls" value={x.run.tool_count??'N/A'}/>
            <DataRow label="Model questions" value={x.run.model_questions??'N/A'}/></>}
        </Panel>)}</div>:
      <Unavailable item="Comparison" detail="At least two accessible run records are required for a comparison."/>}
    {a&&b&&<Panel title="Comparison caveat" subtitle="Matched evaluation conditions are required">
      <p className="body-copy">{a.scenario===b.scenario?'Scenario identifiers match, but seeds, model routes and evaluation policy may still differ.':'The scenarios differ; timing alone cannot establish a better research policy.'}</p>
      <DataRow label="Wall-time difference (A - B)" value={a.wall_seconds!=null&&b.wall_seconds!=null?(a.wall_seconds-b.wall_seconds).toFixed(2)+' s':'Unknown'}/>
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
export function ManualsPage() {
  const [q,setQ]=useState('');
  return <><PageHeading eyebrow="KNOWLEDGE / REFERENCES" title="Manual library"
    description="No source is treated as applicable until model, revision and permissions are verified."/>
    <Panel title="Technical reference search" subtitle="The retrieval API is not integrated yet">
      <div className="search-field-wide"><Search size={19}/><input value={q} onChange={e=>setQ(e.target.value)}
        placeholder="Search a topic or alarm description..." aria-label="Manual search term"/>
        <button className="button-secondary" disabled>Search approved manuals</button></div>
      <Unavailable item="Manual search" detail="Python manual retrieval exists, but this API has no permissioned, version-matched retrieval endpoint. No results are fabricated."/>
    </Panel><Panel title="Reference gate" subtitle="Before displaying an OEM procedure">
      <DataRow label="Source identity" value="Required"/><DataRow label="Controller match" value="Required"/>
      <DataRow label="Revision compatibility" value="Required"/><DataRow label="Citation to exact passage" value="Required"/>
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
