import { Link } from 'react-router-dom';
import { Activity, ArrowRight, Database, RadioTower, ShieldCheck, Signal, Wifi } from 'lucide-react';
import { useRecording } from '../pageData';
import { useResource } from '../api';
import { useUi } from '../context';
import { DataRow, formatBytes, formatNumber, formatStamp, InfoState, Metric, PageHeading, Panel, Pill, QualityExplanation, SummaryLink, TimelineEvent, toneFor, SourceState } from '../ui';

export function RecordingsPage() {
  // Variables:
  //   recording: The Siemens capture read with its loading, failure and
  //     availability facts, so a missing file and a failed request differ.
  const recording = useRecording();
  const { snapshot } = recording;
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
    {!r && <SourceState item="Siemens recording" loading={recording.loading} error={recording.error} status={recording.status} availability={snapshot?.availability ?? null}
      detail={snapshot?.message || 'Configure an approved Siemens v2 JSONL capture in the local API. Start the collector independently in PowerShell.'}/>}
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
        </div> : r ? <SourceState item="Signals" availability="available" count={0}
          emptyDetail="The capture holds no approved signal rows in its bounded window."/> :
          <InfoState title="No signal inventory" detail="Signals appear once a Siemens capture is readable."/>}
      </Panel>
      <Panel title="Collector activity" subtitle="Events from real v2 session markers" action={<SummaryLink to="/recordings/sessions" label="Session details"/>}>
        {snapshot?.events.length ? snapshot.events.slice(0, 7).map((event,i) =>
          <TimelineEvent key={i} label={event.event} at={formatStamp(event.at)} note={'Epoch ' + event.epoch}
            status={event.event === 'gap' || event.event === 'disconnected' ? 'warning' :
              event.event === 'connected' ? 'good' : 'neutral'}/>) : r ?
          <SourceState item="Collector events" availability="available" count={0}
            emptyDetail="The capture holds no session markers."/> :
          <InfoState title="No collector events" detail="Events appear once a Siemens capture is readable."/>}
      </Panel>
    </div>
    <MTConnectPanel />
    <Panel title="Collection architecture" subtitle="No browser-to-controller connection">
      <div className="boundary-grid"><div><strong>01 / Approved source</strong><p>Siemens OPC UA with exact read-only scope</p></div>
        <ArrowRight size={20}/><div><strong>02 / Local collector</strong><p>PowerShell process → v2 JSONL + audit</p></div>
        <ArrowRight size={20}/><div><strong>03 / This screen</strong><p>FastAPI reads private artifacts; no CNC commands</p></div></div>
      <QualityExplanation/>
    </Panel>
  </>;
}
export function QualityPage() {
  const recording = useRecording();
  const { snapshot } = recording;
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
          : <SourceState item="Signal qualification" loading={recording.loading} error={recording.error} status={recording.status} availability={snapshot?.availability ?? null} count={0}
            emptyDetail="The capture holds no signal rows to qualify."/>}
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
  const recording = useRecording();
  const { snapshot } = recording;
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
        </> : <SourceState item="Session inventory" loading={recording.loading} error={recording.error} status={recording.status} availability={snapshot?.availability ?? null} count={0}
          detail={snapshot?.message ?? null}/>}
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
        : <SourceState item="Session markers" loading={recording.loading} error={recording.error} status={recording.status} availability={snapshot?.availability ?? null} count={0}
          emptyDetail="The capture holds no stored connection or session events."/>}
    </Panel>
    <div className="page-bottom-nav"><Link to="/recordings" className="text-link"><Wifi size={16}/> Recorder overview</Link>
      <Link to="/recordings/quality" className="text-link">Quality details <ArrowRight size={17}/></Link></div>
  </>;
}


type LegacyHealth = {
  availability: string;
  recorder: null | { id:string; source:string; process_state:string; connection_state:string;
    measurement_state:string; received:number; available:number; unavailable:number;
    gaps:number; invalid_lines:number; last_receive_at:string|null; output_bytes:number;
    quality_scheme:string; window_scope:string };
  signals: Array<{id:string;label:string;machine:string;component:string;category:string;
    value:number|string|null;quality:string;freshness:string;unit:null;analysis_eligible:false;
    received_at:string}>;
  events: Array<{event:string;at:string;reason_code:string}>;
};
export function MTConnectPanel() {
  const {preview,token}=useUi();
  const source=useResource<LegacyHealth>('/api/v1/recordings/mtconnect-local/health',token,preview);
  const data=source.data;
  const r=data?.recorder;
  return <Panel title="Legacy MTConnect recorder" subtitle="Separate v1 capture adapter; never parsed as Siemens OPC UA">
    {r ? <>
      <div className="metric-grid">
        <Metric label="v1 observations" value={r.received} note="Bounded recent window"/>
        <Metric label="Available" value={r.available} note="MTConnect channel availability, not OPC UA Good"/>
        <Metric label="Unavailable" value={r.unavailable} note="Never replaced with zero" tone="warning"/>
        <Metric label="Capture gaps" value={r.gaps} note="Separate from machine alarms" tone="warning"/>
      </div>
      <div className="two-column">
        <Panel title="Collector evidence" subtitle="No unverified process-liveness claims">
          <DataRow label="Last observation" value={formatStamp(r.last_receive_at)}/>
          <DataRow label="Measurement state" value={<Pill text={r.measurement_state} tone={toneFor(r.measurement_state)}/>}/>
          <DataRow label="Collector process" value={r.process_state}/>
          <DataRow label="File size" value={formatBytes(r.output_bytes)}/>
          <DataRow label="Invalid lines" value={r.invalid_lines}/>
        </Panel>
        <Panel title="Approved legacy signals" subtitle="Source identity is hashed before reaching the browser">
          {data?.signals.length ? data.signals.slice(0,25).map(signal=>
            <DataRow key={signal.id} label={signal.machine + ' / ' + signal.label}
              extra={signal.component + ' · ' + signal.category}
              value={<Pill text={signal.quality} tone={toneFor(signal.quality)}/>}/>):
            <SourceState item="MTConnect signals" availability="available" count={0}
              emptyDetail="The legacy capture holds no approved signal rows."/>}
        </Panel>
      </div>
      <div className="soft-note">MTConnect availability does not establish Siemens StatusCode, valid engineering units, freshness policy or diagnostic eligibility.</div>
    </> : preview ? <InfoState title="MTConnect v1 capture hidden in preview"
      detail="Real capture is hidden during synthetic UI preview."/> :
      <SourceState item="MTConnect v1 capture" loading={source.loading} error={source.error}
        status={source.status} availability={data?.availability ?? null} count={0}
        detail="Configure an approved CAPSTONE_UI_MTCONNECT JSONL artifact. No browser-to-MTConnect-agent access is permitted."/>}
  </Panel>;
}
