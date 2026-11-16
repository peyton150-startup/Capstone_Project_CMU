import { Link } from 'react-router-dom';
import { Activity, ArrowRight, Database, RadioTower, ShieldCheck, Signal, Wifi } from 'lucide-react';
import { useRecording } from '../pageData';
import { useUi } from '../context';
import { DataRow, formatBytes, formatNumber, formatStamp, InfoState, Metric, PageHeading, Panel, Pill, QualityExplanation, SummaryLink, TimelineEvent, toneFor, Unavailable } from '../ui';

export function RecordingsPage() {
  const { snapshot, error } = useRecording();
  const { preview } = useUi();
  const r = snapshot?.recorder;
  const statuses = [
    ['Recorder process', r?.process_state, 'Collector supervisor not integrated'],
    ['OPC UA connection', r?.connection_state, 'Transport status only'],
    ['Subscription', r?.subscription_state, 'Independent confirmation required'],
    ['Measurements', r?.measurement_state, 'Receipt is not validity'],
    ['Storage', r?.sink_state, 'Flush is not durable persistence'],
  ];
  return <>
    <PageHeading eyebrow="DATA ACQUISITION / LOCAL CAPTURE" title="Recorder monitor"
      description="Know what is connected, what is recording, and what can actually be trusted."
      right={<Pill text={preview ? 'SYNTHETIC FIXTURE' : 'LOCAL / READ ONLY'} tone={preview ? 'warning' : 'info'}/>} />
    <div className="state-grid">{statuses.map(([label, status, note]) =>
      <div className="state-tile" key={label}><div className="state-tile-head"><RadioTower size={17}/>{label}</div>
        <Pill text={(status || 'unknown').replaceAll('_', ' ')} tone={toneFor(status)}/><small>{note}</small></div>)}</div>
    {error && <InfoState kind="warning" title="Recorder API unavailable" detail={error}/>}
    {!r && <Unavailable item="Siemens recording" detail="Configure an approved Siemens v2 JSONL capture in the local API. Start the collector independently in PowerShell."/>}
    <div className="metric-grid">
      <Metric label="Received" value={r ? formatNumber(r.received) : null} note="Bounded capture window" icon={<Database size={18}/>} />
      <Metric label="Native Good" value={r ? formatNumber(r.good) : null} note="Not automatically eligible for analysis" icon={<ShieldCheck size={18}/>} />
      <Metric label="Quality exceptions" value={r ? r.bad + r.uncertain + r.invalid_lines : null}
        note="Bad + Uncertain + invalid" icon={<Activity size={18}/>} tone="warning" />
      <Metric label="Detected gaps" value={r?.gaps} note="Bounded window only" icon={<Signal size={18}/>} tone={r?.gaps ? 'warning' : 'neutral'} />
    </div>
    <div className="two-column uneven">
      <Panel title="Approved signals" subtitle="No inferred units or physical mappings" action={<SummaryLink to="/recordings/quality" label="Quality details"/>}>
        {snapshot?.signals.length ? <div className="data-table">
          <div className="data-table-head"><span>Signal</span><span>Value</span><span>Quality</span><span>Freshness</span></div>
          {snapshot.signals.map(s => <div className="data-table-row" key={s.id}>
            <div className="cell-primary"><strong>{s.label}</strong><small>{s.unit || 'Unit unverified'}</small></div>
            <div className="cell-mono">{s.value === null ? 'Restricted / —' : String(s.value) + (s.unit ? ' ' + s.unit : '')}</div>
            <Pill text={s.quality} tone={toneFor(s.quality)}/><span className="cell-muted">{s.freshness}</span>
          </div>)}
        </div> : <Unavailable item="Approved signal inventory"/>}
      </Panel>
      <Panel title="Collector activity" subtitle="Events from real v2 session markers" action={<SummaryLink to="/recordings/sessions" label="Session details"/>}>
        {snapshot?.events.length ? snapshot.events.slice(0, 7).map((event,i) =>
          <TimelineEvent key={i} label={event.event} at={formatStamp(event.at)} note={'Epoch ' + event.epoch}
            status={event.event === 'gap' || event.event === 'disconnected' ? 'warning' :
              event.event === 'connected' ? 'good' : 'neutral'}/>) : <Unavailable item="Collector event history"/>}
      </Panel>
    </div>
    <Panel title="Collection architecture" subtitle="No browser-to-controller connection">
      <div className="boundary-grid"><div><strong>01 / Approved source</strong><p>Siemens OPC UA with exact read-only scope</p></div>
        <ArrowRight size={20}/><div><strong>02 / Local collector</strong><p>PowerShell process → v2 JSONL + audit</p></div>
        <ArrowRight size={20}/><div><strong>03 / This screen</strong><p>FastAPI reads private artifacts; no CNC commands</p></div></div>
      <QualityExplanation/>
    </Panel>
  </>;
}
export function QualityPage() {
  const { snapshot } = useRecording();
  const r = snapshot?.recorder;
  const share = r?.received ? (100 * r.good / r.received).toFixed(1) + '%' : null;
  return <>
    <PageHeading eyebrow="ACQUISITION / EVIDENCE QUALITY" title="Data quality"
      description="Native quality, continuity, freshness and eligibility are different questions."/>
    <div className="metric-grid">
      <Metric label="Native Good / received" value={share} note="Only the bounded recent window" icon={<ShieldCheck size={17}/>} />
      <Metric label="Uncertain" value={r?.uncertain} note="Never assumed valid" tone="warning"/>
      <Metric label="Bad" value={r?.bad} note="Never converted into zero" tone="critical"/>
      <Metric label="Gap indicators" value={r ? r.gaps + r.overflow : null} note="Gaps + queue overflows" tone="warning"/>
    </div>
    <div className="two-column">
      <Panel title="Per-signal status" subtitle="A Good StatusCode is only the first gate">
        {snapshot?.signals.length ? snapshot.signals.map(s =>
          <DataRow key={s.id} label={s.label} extra={'Eligibility: ' + (s.analysis_eligible ? 'verified' : 'unverified')}
            value={<Pill text={s.quality} tone={toneFor(s.quality)}/>}/>)
          : <Unavailable item="Signal qualification"/>}
      </Panel>
      <Panel title="Qualification checklist" subtitle="Each criterion needs evidence">
        {[
          ['Authorized node identity', 'Machine, channel, spindle and approved source'],
          ['Native quality & type', 'Good, Uncertain, Bad, unsupported'],
          ['Time fidelity', 'Source, server and receive timestamps'],
          ['Freshness policy', 'Change-only differs from periodic signals'],
          ['Meaning, units & operating state', 'Technician-confirmed mapping'],
          ['Continuity', 'Losses remain explicit; no interpolated truth'],
        ].map(([a,b]) => <div className="quality-check" key={a}><span className="check-ring"/>
          <div><strong>{a}</strong><small>{b}</small></div></div>)}
      </Panel>
    </div>
    <Panel title="Continuity timeline" subtitle="Collector failures are not machine alarms">
      {snapshot?.events.filter(e => ['gap','disconnected'].includes(e.event)).length ?
        snapshot.events.filter(e => ['gap','disconnected'].includes(e.event)).map((e,i) =>
          <TimelineEvent key={i} label={'Capture ' + e.event} at={formatStamp(e.at)} status="warning"/>)
        : <InfoState title="No gaps in the bounded window" detail="That does not establish historical continuity or complete signal coverage."/>}
    </Panel><QualityExplanation/>
  </>;
}
export function SessionsPage() {
  const { snapshot } = useRecording();
  const r = snapshot?.recorder;
  return <>
    <PageHeading eyebrow="ACQUISITION / SESSION HISTORY" title="Recording sessions"
      description="Connection epochs and stored evidence, without inventing recorder uptime."/>
    <div className="two-column uneven">
      <Panel title="Current configured artifact" subtitle="One local Siemens v2 data source">
        {r ? <>
          <div className="session-name"><RadioTower size={28}/><div><strong>Siemens OPC UA · local file</strong>
            <p>{r.window_scope}</p></div><Pill text={r.connection_state} tone={toneFor(r.connection_state)}/></div>
          <DataRow label="Latest connection epoch" value={r.session_epoch ?? 'Unknown'}/>
          <DataRow label="Latest received measurement" value={formatStamp(r.last_receive_at)}/>
          <DataRow label="Capture file size" value={formatBytes(r.output_bytes)}/>
          <DataRow label="Durable storage state" value={<Pill text={r.sink_state} tone={toneFor(r.sink_state)}/>}/>
          <DataRow label="Recent-window reconnects" value={r.reconnections}/>
          <DataRow label="Recent-window readings" value={formatNumber(r.received)}/>
        </> : <Unavailable item="Session inventory"/>}
      </Panel>
      <Panel title="Before unattended collection" subtitle="A short capture is not seven-day approval">
        {[
          'Obtain exact IT/OT authorization for source and node scope',
          'Verify a technician recognizes the signals and cycles',
          'Confirm storage retention, disk capacity and recovery procedure',
          'Get separate approval and named owner for extended capture',
        ].map((item,i) => <div className="process-step" key={item}>
          <span>{'0' + (i + 1)}</span><div><strong>{item}</strong></div></div>)}
      </Panel>
    </div>
    <Panel title="Recorded events" subtitle="Session markers from the approved file">
      {snapshot?.events.length ? snapshot.events.map((e,i) =>
        <TimelineEvent key={i} label={'Epoch ' + e.epoch + ' · ' + e.event} at={formatStamp(e.at)}
          status={e.event === 'gap' ? 'warning' : 'neutral'}/>)
        : <Unavailable item="Session markers"/>}
    </Panel>
    <div className="page-bottom-nav"><Link to="/recordings" className="text-link"><Wifi size={16}/> Recorder overview</Link>
      <Link to="/recordings/quality" className="text-link">Quality details <ArrowRight size={17}/></Link></div>
  </>;
}
