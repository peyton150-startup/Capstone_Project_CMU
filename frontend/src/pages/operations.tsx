import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity, ArrowRight, BarChart3, Box, Boxes, BrainCircuit, CircleHelp,
  FlaskConical, RadioTower, ShieldCheck, Signal, Waypoints,
} from 'lucide-react';
import { useResource } from '../api';
import { useUi } from '../context';
import { demoChart } from '../preview';
import { useInvestigations, useMachines, useRecording } from '../pageData';
import type { ListResponse, Sample } from '../types';
import {
  DataRow, Eyebrow, formatNumber, formatStamp, InfoState, MachineLine,
  Metric, PageHeading, Panel, Pill, QualityExplanation,
  SummaryLink, TileLink, TimelineEvent, toneFor, TrendChart, Unavailable,
} from '../ui';

export function HomePage() {
  const { preview, setPreview, workspace } = useUi();
  return <>
    <div className="home-hero">
      <div className="hero-copy">
        <div className="hero-kicker"><span className="hero-kicker-line"/> INDUSTRIAL INTELLIGENCE / V01</div>
        <h1>See the signal.<br /><em>Understand the cause.</em></h1>
        <p>A research assistant for manufacturing operations—turning machine readings
          into grounded investigations, verifiable evidence, and clear next steps.</p>
        <div className="hero-actions">
          <Link className="button-primary" to="/overview">Explore workspace <ArrowRight size={18}/></Link>
          <button className="button-secondary" onClick={() => setPreview(!preview)}>
            {preview ? 'Return to actual sources' : 'Open synthetic preview'} <ArrowRight size={17}/>
          </button>
        </div>
        <div className="hero-footnote"><ShieldCheck size={16}/> {workspace === 'pilot'
          ? 'Prestige pilot · read-only collection' : 'Simulator Lab · evidence-first agent workflow'}</div>
      </div>
      <div className="hero-diagram" aria-hidden="true">
        <div className="diagram-meta"><span>OBSERVATION → REASONING</span><span>ENGINEERING VIEW / 01</span></div>
        <div className="diagram-track">
          <div className="diagram-stage"><span className="stage-number">01 / INPUT</span>
            <span className="diagram-glyph"><Signal size={32}/></span><strong>Telemetry</strong><small>Observed readings</small></div>
          <div className="diagram-junction"><span/><span/><span/></div>
          <div className="diagram-stage stage-active"><span className="stage-number">02 / ANALYZE</span>
            <span className="diagram-glyph"><BrainCircuit size={33}/></span><strong>Investigation</strong><small>Evidence &amp; tests</small></div>
          <div className="diagram-junction"><span/><span/><span/></div>
          <div className="diagram-stage"><span className="stage-number">03 / OUTPUT</span>
            <span className="diagram-glyph"><ShieldCheck size={32}/></span><strong>Verified insight</strong><small>Decision &amp; review</small></div>
        </div>
        <div className="diagram-bottom"><span className="signal-dot"/><span>HUMAN-REVIEWED DECISIONS</span>
          <span className="diagram-bottom-line"/></div>
      </div>
    </div>
    <div className="section-intro"><div><Eyebrow>EXPLORE THE PLATFORM</Eyebrow>
      <h2>One system. Every layer of the investigation.</h2>
      <p>Start with the big picture, or open the precise workspace you need.</p></div>
      <span className="section-index">01 — 06</span></div>
    <div className="tile-grid">
      <TileLink to="/overview" icon={<Waypoints size={25}/>} title="Operations overview"
        description="Equipment, observed conditions and attention items in one calm command center." />
      <TileLink to="/investigations" icon={<BrainCircuit size={25}/>} title="Investigations"
        description="Triage, hypotheses, evidence, conclusions and verification, with technical depth on demand." />
      <TileLink to="/signals" icon={<BarChart3 size={25}/>} title="Machines & signals"
        description="Trace sensor histories, quality intervals, source identity and machine operating context." />
      <TileLink to="/recordings" icon={<RadioTower size={25}/>} title="Recorder monitor"
        description="Understand actual OPC UA connection, received data, gaps and storage state." />
      <TileLink to="/lab" icon={<FlaskConical size={25}/>} title="Research lab"
        description="Inspect simulator experiments, evaluation artifacts and deterministic versus agent workflows." />
      <TileLink to="/system" icon={<ShieldCheck size={25}/>} title="System & engineering"
        description="Data boundaries, service health, safe logs and approved runtime configuration." />
    </div>
    <div className="home-stripe"><span className="stripe-icon"><CircleHelp size={23}/></span>
      <div><strong>Designed to tell you what the system does not know.</strong>
        <p>A connected recorder is not proof of valid data. A model answer is not a verified cause.</p></div>
      <Link to="/recordings/quality" className="text-link">Data-quality principles <ArrowRight size={17}/></Link></div>
  </>;
}

export function OverviewPage() {
  const { preview, workspace } = useUi();
  const machines = useMachines(), investigations = useInvestigations(), recording = useRecording();
  const pilot = workspace === 'pilot';
  const rec = recording.snapshot?.recorder;
  return <>
    <PageHeading eyebrow="OPERATIONS / WORKSPACE" title="Overview"
      description="A clear operational picture. Unknowns stay visible; detail is one click away."
      right={<Pill text={preview ? 'Preview data' : pilot ? 'Authorized pilot' : 'Simulator workspace'}
        tone={preview ? 'warning' : 'info'}/>} />
    <div className="metric-grid">
      <Metric label="Machines observed" value={machines.items.length || null}
        note={machines.items.length ? 'Current authorized view' : 'No machine inventory'}
        icon={<Box size={18}/>} />
      <Metric label="Open attention items" value={preview ? 2 : null}
        note={preview ? 'Illustrative incidents' : 'No supported live incident source'} icon={<Activity size={18}/>} tone="warning" />
      <Metric label="Telemetry received" value={rec ? formatNumber(rec.received) : null}
        note={rec ? 'Bounded recorder window, not full session' : 'No configured recording'} icon={<Signal size={18}/>} />
      <Metric label="Investigations" value={investigations.availability === 'not_configured' ? null : investigations.items.length}
        note={pilot ? 'Real-machine diagnosis not enabled' : 'Available recorded investigations'} icon={<BrainCircuit size={18}/>} />
    </div>
    <div className="overview-grid">
      <Panel title={pilot ? 'Authorized equipment' : 'Manufacturing line'}
        subtitle="Observed machines; unknown state remains unknown"
        action={<SummaryLink to="/machines" label="Machine details"/>}>
        <MachineLine machines={machines.items} pilot={pilot}/>
      </Panel>
      <Panel title="Needs attention" subtitle="Recent reported investigations and exceptions"
        action={<SummaryLink to="/investigations" label="View investigations"/>}>
        {!pilot && investigations.items.length ? <div className="compact-list">
          {investigations.items.slice(0, 4).map(item => <Link to={'/investigations/' + item.id}
            className="attention-item" key={item.id}><span className="attention-symbol"><Activity size={17}/></span>
            <div><strong>{item.summary}</strong><small>{item.termination_reason || 'Assessment not set'}</small></div>
            <ArrowRight size={16}/></Link>)}
        </div> : <InfoState title="No supported incident feed"
          detail={pilot ? 'Siemens field incidents require the real-machine acceptance gates; a recorder connection is not an anomaly.' :
            'Connect a completed-investigation audit file or select the synthetic UI preview.'}/>}
      </Panel>
    </div>
    <div className="two-column">
      <Panel title="Recent activity" subtitle="Recorded events, not inferred machine faults">
        {rec && recording.snapshot?.events.length ? recording.snapshot.events.slice(0, 4).map((event, index) =>
          <TimelineEvent key={index} label={'Collector ' + event.event}
            at={formatStamp(event.at)} status={event.event === 'gap' ? 'warning' :
              event.event === 'connected' ? 'good' : 'neutral'} />)
          : <Unavailable item="Recent activity" />}
      </Panel>
      <Panel title="Data confidence" subtitle="The evidence gate protects downstream diagnosis">
        <QualityExplanation/>
        <div className="quiet-stats">
          <DataRow label="OPC UA connection" value={<Pill text={rec?.connection_state || 'Unknown'} tone={toneFor(rec?.connection_state)}/>}/>
          <DataRow label="Measurement quality" value={<Pill text={rec ? rec.good + ' Good (recent window)' : 'Unknown'} tone="neutral"/>}/>
          <DataRow label="Analysis eligibility" value={<Pill text="Not established" tone="neutral"/>}/>
        </div>
      </Panel>
    </div>
  </>;
}

export function MachinesPage() {
  const machines = useMachines();
  const { workspace } = useUi();
  return <>
    <PageHeading eyebrow="EQUIPMENT / MACHINES" title="Machines"
      description="Every machine has its own physical identity, state and source coverage."/>
    <div className="two-column uneven">
      <Panel title="Machine inventory" subtitle={workspace === 'pilot' ? 'Only approved physical equipment' : 'Simulated production line'}>
        {machines.items.length ? machines.items.map(machine => <div className="machine-list-card" key={machine.id}>
          <div className="machine-list-icon"><Boxes size={26}/></div>
          <div><h3>{machine.name}</h3><p>{machine.signal_count ?? '—'} available signal identifiers</p></div>
          <Pill text={machine.operating_state || 'Unknown'} tone={toneFor(machine.condition || machine.operating_state)}/>
          <Link to={'/signals?machine=' + encodeURIComponent(machine.id)} className="text-link">Inspect <ArrowRight size={16}/></Link>
        </div>) : <Unavailable item="Machine inventory" />}
      </Panel>
      <Panel title="Source boundaries" subtitle="A physical machine is not a simulator record">
        <div className="principle-list">
          <DataRow label="Environment" value={workspace === 'pilot' ? 'Prestige pilot' : 'Simulator Lab'}/>
          <DataRow label="Machine status" value="Observed only"/>
          <DataRow label="Cross-source identity" value="Separate per physical source"/>
          <DataRow label="Plant-wide estimates" value={<Pill text="Not assumed" tone="neutral"/>}/>
        </div>
        <div className="soft-note">A physical source can contain multiple CNC channels, axes or spindles.
          A matching display name is not enough to combine them.</div>
      </Panel>
    </div>
    <Panel title="Equipment relationships" subtitle="Only resolved equipment is shown">
      <MachineLine machines={machines.items} pilot={workspace === 'pilot'}/>
    </Panel>
  </>;
}

export function SignalsPage() {
  const { preview, token } = useUi();
  const { snapshot } = useRecording();
  const signals = snapshot?.signals || [];
  const [selected, setSelected] = useState<string | null>(null);
  const current = useMemo(() => signals.find(s => s.id === selected) || signals[0], [signals, selected]);
  const resource = useResource<ListResponse<Sample>>(
    current && !preview ? '/api/v1/signals/' + current.id + '/samples' : null,
    token, preview || !current);
  const samples = preview ? demoChart : resource.data?.items || [];
  return <>
    <PageHeading eyebrow="EQUIPMENT / ANALYTICS" title="Signal explorer"
      description="Time-aligned measurements with explicit quality and source integrity."
      right={<SummaryLink to="/recordings/quality" label="Inspect data quality" />} />
    <div className="signals-layout">
      <Panel title="Signal browser" subtitle="Approved observed channels" className="signal-browser">
        <div className="signal-browser-list">
          {signals.length ? signals.map(signal => <button key={signal.id}
            onClick={() => setSelected(signal.id)}
            className={'signal-option ' + (signal.id === current?.id ? 'selected' : '')}>
            <span className="signal-option-icon"><Signal size={17}/></span>
            <span><strong>{signal.label}</strong><small>{signal.unit || 'Unit not verified'}</small></span>
            <span className={'quality-dot ' + signal.quality}/>
          </button>) : <Unavailable item="Signal browser" detail="No authorized Siemens capture or preview signal is available."/>}
        </div>
      </Panel>
      <div className="signal-main">
        <Panel title={current?.label || 'Signal trend'} subtitle="Native source timestamps; missing observations remain gaps"
          action={current && <Pill text={current.quality} tone={toneFor(current.quality)}/>}>
          {current ? <><div className="signal-hero-value">
            <strong>{current.value ?? '—'}</strong><span>{current.unit || 'Unverified unit'}</span>
            <small>{current.value === null ? 'Value not authorized or unavailable' : 'Latest recorded value'}</small>
          </div><TrendChart items={samples} label={current.label + ' history'}/></>
            : <Unavailable item="Signal history"/>}
        </Panel>
        <div className="two-column">
          <Panel title="Source integrity" subtitle="No inferred engineering units">
            <DataRow label="Latest quality" value={<Pill text={current?.quality || 'Unknown'} tone={toneFor(current?.quality)}/>}/>
            <DataRow label="Last received" value={formatStamp(current?.received_at)}/>
            <DataRow label="Freshness" value={current?.freshness || 'Unknown'}/>
            <DataRow label="Analysis eligibility" value={<Pill text={current?.analysis_eligible ? 'Eligible' : 'Unverified'} tone={current?.analysis_eligible ? 'good' : 'neutral'}/>}/>
          </Panel>
          <Panel title="Understanding this graph" subtitle="Operational semantics">
            <p className="body-copy">Only qualified numeric observations form plotted lines.
              Invalid or unavailable samples are gaps. Preview samples are synthetic and clearly labeled.
              The real API never invents values or a sampling interval.</p>
            <QualityExplanation/>
          </Panel>
        </div>
      </div>
    </div>
  </>;
}
