import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowRight, Database, Gauge, LockKeyhole,
  RadioTower, SlidersHorizontal, TerminalSquare } from 'lucide-react';
import { useResource } from '../api';
import { useUi } from '../context';
import { useRecording } from '../pageData';
import { DataRow, formatStamp, Metric, PageHeading,
  Panel, Pill, TimelineEvent, toneFor, Unavailable } from '../ui';

type SystemStatus = {
  api: string; simulation_worker: string; progress_stream: string;
  recorder_connection: string; recorder_sink: string; model_provider: string; storage: string;
};
type AuditEntry = { at?: string; session_epoch?: number; stage?: string; outcome?: string };
type SettingsRecord = { name: string; value: string | null; configured: boolean };
type SettingsData = {
  editable: boolean;
  items: SettingsRecord[];
  triage_profile?: Record<string,string|boolean|number>;
  conclude?: string;
};

export function SystemPage() {
  const {token,preview}=useUi();
  const data=useResource<SystemStatus>('/api/v1/system',token,preview);
  const recorder=useRecording().snapshot?.recorder;
  return <>
    <PageHeading eyebrow="ENGINEERING / SERVICE STATUS" title="System health"
      description="Operational indicators backed by a source or clearly marked unknown."/>
    <div className="metric-grid">
      <Metric label="Local API" value={data.data?.api||null} note="Read-only FastAPI service" icon={<Gauge size={17}/>}/>
      <Metric label="Investigation worker" value={data.data?.simulation_worker||null}
        note="No managed background worker integrated" icon={<Activity size={17}/>}/>
      <Metric label="Recorder connection" value={recorder?.connection_state||null}
        note="Cannot establish machine health" icon={<RadioTower size={17}/>}/>
      <Metric label="Storage health" value={recorder?.sink_state||null}
        note="No storage supervisor integrated" icon={<Database size={17}/>}/>
    </div>
    <div className="two-column">
      <Panel title="Service components" subtitle="These fields cannot substitute for checks against real measurements">
        {data.data?Object.entries(data.data).map(([name,value])=>
          <DataRow key={name} label={name.replaceAll('_',' ')}
            value={<Pill text={String(value).replaceAll('_',' ')} tone={toneFor(value)}/>}/>):
          <Unavailable item="System status" detail={data.error||'Connect the local API to inspect service status.'}/>}
      </Panel>
      <Panel title="System boundaries" subtitle="Read-only industrial pilot">
        <div className="quality-check"><span className="check-ring"/><div><strong>Controller connection</strong>
          <small>Only the independent Siemens collector may contact the CNC</small></div></div>
        <div className="quality-check"><span className="check-ring"/><div><strong>Model providers</strong>
          <small>API health does not prove external LLM access or responsiveness</small></div></div>
        <div className="quality-check"><span className="check-ring"/><div><strong>Audit and source files</strong>
          <small>Access requires configured private files and a local API token</small></div></div>
        <div className="quality-check"><span className="check-ring"/><div><strong>Physical actions</strong>
          <small>None are exposed by the local web service</small></div></div>
      </Panel>
    </div>
    <div className="three-column-link">
      <a className="feature-row-link" href="/system/observability"><Activity size={21}/>
        <div><strong>Agent observability</strong><small>Traceability and timing sources</small></div><ArrowRight size={17}/></a>
      <a className="feature-row-link" href="/system/audit"><TerminalSquare size={21}/>
        <div><strong>Collector audit</strong><small>Connection and error metadata</small></div><ArrowRight size={17}/></a>
      <a className="feature-row-link" href="/system/settings"><SlidersHorizontal size={21}/>
        <div><strong>Settings</strong><small>Allowlisted effective values</small></div><ArrowRight size={17}/></a>
    </div>
  </>;
}
export function ObservabilityPage() {
  const {snapshot}=useRecording();
  const rec=snapshot?.recorder;
  return <>
    <PageHeading eyebrow="ENGINEERING / OBSERVABILITY" title="Observability"
      description="Model and tool diagnostics without leaking private traces or inventing measurements."/>
    <div className="metric-grid">
      <Metric label="Collector gaps" value={rec?.gaps} note="Recent capture tail" tone="warning"/>
      <Metric label="Reconnects" value={rec?.reconnections} note="Recent capture tail"/>
      <Metric label="Invalid records" value={rec?.invalid_lines} note="Rejected v2 lines" tone="warning"/>
      <Metric label="Stage p95 latency" value={null} note="No approved live model-call service"/>
    </div>
    <div className="two-column">
      <Panel title="Collector events" subtitle="Valid OPC UA session markers">
        {snapshot?.events.length?snapshot.events.slice(0,9).map((e,i)=>
          <TimelineEvent key={i} label={e.event} at={formatStamp(e.at)}
            status={e.event==='gap'?'warning':'neutral'}/>):
          <Unavailable item="Live collector event stream"/>}
      </Panel>
      <Panel title="Agent diagnostics" subtitle="Work to wire to original Python event and audit sources">
        {[
          ['Stage timing','Observe, plan, investigate, hypothesize, test and conclude'],
          ['Model routing','Attempt, timeout, fallback, token counts when reported'],
          ['Tool calls','Reads made, blocked repeats, failed/unsupported results'],
          ['Verification','Conclusion-check time, unresolved questions and clearance'],
          ['Progress events','Nonblocking watcher queue and reconnectable SSE'],
        ].map(([a,b])=><div className="quality-check" key={a}><span className="check-ring"/>
          <div><strong>{a}</strong><small>{b}</small></div></div>)}
        <div className="soft-note">The existing observability logger intentionally keeps only
          safe metadata. Full investigation audits require a separate access-controlled projection.</div>
      </Panel>
    </div>
  </>;
}
export function AuditPage() {
  const {token,preview}=useUi();
  const resource=useResource<{availability:string;items:AuditEntry[]}>('/api/v1/system/audit',token,preview);
  return <>
    <PageHeading eyebrow="ENGINEERING / LOCAL EVENTS" title="Audit timeline"
      description="Lifecycle metadata only; credentials, OPC UA endpoints and raw exception messages are not exposed."/>
    <Panel title="Collector connection audit" subtitle="Read-only projection of the configured private audit file">
      {resource.data?.items.length?resource.data.items.map((item,i)=>
        <TimelineEvent key={i} label={(item.outcome||'Unknown')+' · '+(item.stage||'stage unknown')}
          at={formatStamp(item.at)} status={item.outcome==='refused'||item.outcome==='failed'?'warning':'neutral'}
          note={'Connection epoch '+(item.session_epoch??'unknown')}/>):
        <Unavailable item="Collector audit" detail={resource.error||'No authorized audit file is configured. Enable the synthetic preview for a labeled layout example.'}/>}
    </Panel>
    <Panel title="Audit policy" subtitle="Not a raw diagnostic dump">
      <DataRow label="Visible" value="Timestamp, stage, outcome, session epoch"/>
      <DataRow label="Excluded" value="Endpoint, credentials, reason text, private evidence"/>
      <DataRow label="Scope" value="Local permissioned artifact"/>
    </Panel>
  </>;
}
export function SettingsPage() {
  const {token,preview,theme,setTheme}=useUi();
  const data=useResource<SettingsData>('/api/v1/settings/effective',token,preview);
  const [filter,setFilter]=useState('');
  const settings=useMemo(()=>data.data?.items.filter(item=>item.name.toLowerCase().includes(filter.toLowerCase()))||[],
    [data.data,filter]);
  return <>
    <PageHeading eyebrow="ENGINEERING / CONFIGURATION" title="Settings"
      description="Server-wide environment is read-only. Simulator experiments can edit and freeze their own validated settings when launched."
      right={<Pill text="GLOBAL SETTINGS READ ONLY" tone="neutral"/>}/>
    <div className="two-column uneven">
      <Panel title="Validated server defaults" subtitle="Explicit allowlist; not an editable .env browser">
        <div className="settings-toolbar"><input aria-label="Filter settings" placeholder="Filter by variable name..."
          value={filter} onChange={e=>setFilter(e.target.value)}/><Pill text="LOCAL API" tone="info"/></div>
        {settings.length?settings.map(s=><div className="settings-row" key={s.name}>
          <div><strong>{s.name}</strong><small>{s.configured?'Process override':'Validated default or private .env value'}</small></div>
          <span className="settings-value">{s.value||'Not configured'}</span></div>):
          <Unavailable item="Settings read model" detail={data.error||'Connect an authorized API to inspect allowlisted effective values.'}/>}
        <div className="soft-note"><LockKeyhole size={17}/> These are actual validated
          global scalar settings, not just variables set in process memory.
          API keys, database credentials, certificates and paths are excluded.</div>
      </Panel>
      <Panel title="Interface preferences" subtitle="These controls affect the browser only">
        <DataRow label="Color scheme" value={<div className="button-group"><button
          className={theme==='dark'?'button-selected':'button-outline'} onClick={()=>setTheme('dark')}>Dark</button>
          <button className={theme==='light'?'button-selected':'button-outline'}
            onClick={()=>setTheme('light')}>Light</button></div>}/>
        <div className="divider-soft"/>
        <h3>Engineering boundaries</h3>
        <p className="body-copy">The server owns credentials and model-provider routing.
          The simulator launch editor can select triage mode, stage routes, time/tool budgets
          and Conclude controls for each new run. Those values are validated by the API
          and saved at submission; global settings and existing runs do not change.</p>
        <Link className="button-primary" to="/lab">Open per-run triage settings</Link>
      </Panel>
    </div>
    <Panel title="Effective global triage profile" subtitle="The deterministic override can supersede the individual raw settings above">
      <DataRow label="Final Conclude stage" value={data.data?.conclude || 'Not recorded'}/>
      {Object.entries(data.data?.triage_profile || {}).map(([name,value])=>
        <DataRow key={name} label={name.replaceAll('_',' ')}
          value={String(value)}/>)}
      <p className="body-copy">The managed simulator launch can override these stage
        values per run, and the saved run detail records the actual resolved controls.</p>
    </Panel>
    <Panel title="Configuration groups" subtitle="Global controls remain server-owned; experiment controls can change per run">
      <div className="settings-categories">{['Investigation & triage','Model routing','Critic & review',
        'Manuals & retrieval','Runtime budgets','Recording & privacy'].map((g,i)=>
        <div className="settings-category" key={g}><span>{'0'+(i+1)}</span><strong>{g}</strong>
          <Pill text={g==='Investigation & triage'||g==='Runtime budgets'?
            'Editable per simulator run':'Server controlled'} tone="neutral"/></div>)}</div>
    </Panel>
  </>;
}
