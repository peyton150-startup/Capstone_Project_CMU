import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { postJson, useResource } from '../api';
import { resolveApiUrl } from '../backend.mjs';
import type { ApiBackend } from '../backend.mjs';
import { useUi } from '../context';
import type { Capabilities, InvestigationDetail, ListResponse, ManagedRun, ReviewRequest, RunEvent, SafeHypothesisProgress, TriageReport, TriageRunDefaults, TriageRunOptions, TriageRunPreview } from '../types';
import { TriageRunEditor } from './triageRunEditor';
import { DataRow, formatStamp, InfoState, PageHeading, Panel, Pill, toneFor, Unavailable } from '../ui';

type OperationalEvent = { event: string; run_id?: string; investigation_id?: string;
  tick?: number; tool?: string; success?: boolean; counts?: Record<string,number> };

function useManagedRuns(pollMs = 5000) {
  const { workspace, preview, token } = useUi();
  return useResource<ListResponse<ManagedRun>>(
    workspace === 'simulator' && !preview ? '/api/v1/lab/runs?workspace=simulator' : null,
    token, preview || workspace !== 'simulator', pollMs,
  );
}

export function ManagedRunLauncher() {
  const { workspace, preview, token, backend } = useUi();
  const capability = useResource<Capabilities>('/api/v1/capabilities', token, preview);
  const navigate = useNavigate();
  const [seed, setSeed] = useState('3');
  const [kind, setKind] = useState<'standard' | 'challenge'>('standard');
  const [mode, setMode] = useState<'triage' | 'deep'>('triage');
  const [hazards, setHazards] = useState(false);
  const [tree, setTree] = useState(false);
  const [manual, setManual] = useState<'none' | 'keyword' | 'neon'>('none');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useRef<string | null>(null);
  const enabled = workspace === 'simulator' && !preview &&
    capability.data?.features.simulation_run_launch === true;
  const defaults = useResource<TriageRunDefaults>(
    enabled ? '/api/v1/lab/runs/configuration?workspace=simulator' : null,
    token, !enabled, 60000,
  );
  const [controls, setControls] = useState<TriageRunOptions | null>(null);
  const initializedFor = useRef<string | null>(null);
  const sourceKey = JSON.stringify([backend, token, workspace, preview]);
  useEffect(() => {
    if (defaults.data && initializedFor.current !== sourceKey) {
      initializedFor.current = sourceKey;
      setControls(defaults.data.defaults);
      key.current = null;
    }
  }, [defaults.data, sourceKey]);
  const parsedSeed = Number(seed);
  const validSeed = seed.trim() !== '' && Number.isInteger(parsedSeed) &&
    parsedSeed >= 0 && parsedSeed <= 1000000;
  const validBudget = mode === 'deep' || (controls != null &&
    Number.isFinite(controls.seconds) && controls.seconds >= 5 && controls.seconds <= 900 &&
    Number.isInteger(controls.tool_calls) && controls.tool_calls >= 1 &&
    controls.tool_calls <= 30 && Number.isFinite(controls.hypothesis_seconds) &&
    controls.hypothesis_seconds >= 0 && controls.hypothesis_seconds <= 300);
  const requested = controls || mode === 'deep' ? {
    seed: parsedSeed, kind, mode, hazards, tree_of_thought: tree, manual,
    ...(mode === 'triage' && controls ? {triage_settings: controls} : {}),
  } : null;
  const requestSignature = JSON.stringify(requested);
  const previewIdentity = JSON.stringify([requestSignature, token, backend, sourceKey]);
  const [resolved, setResolved] = useState<{
    identity: string; value: TriageRunPreview;
  } | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewPending, setPreviewPending] = useState(false);
  const confirmed = resolved?.identity === previewIdentity ? resolved.value : null;

  useEffect(() => {
    let active = true;
    setResolved(null);
    setPreviewError(null);
    if (!enabled || !validSeed || !validBudget || !requested) {
      setPreviewPending(false);
      return;
    }
    setPreviewPending(true);
    const timer = window.setTimeout(() => {
      void postJson<TriageRunPreview>('/api/v1/lab/runs/preview?workspace=simulator',
        token, requested, backend).then(value => {
          if (active) {
            setResolved({ identity: previewIdentity, value });
            setPreviewPending(false);
          }
        }).catch(problem => {
          if (active) {
            setPreviewError(problem instanceof Error ? problem.message : 'Preview failed');
            setPreviewPending(false);
          }
        });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [previewIdentity, enabled, validSeed, validBudget]);

  async function submit() {
    if (!enabled || !validSeed || !validBudget || !requested ||
      !confirmed || pending) return;
    setPending(true);
    setError(null);
    if (!key.current) key.current = crypto.randomUUID().replaceAll('-', '');
    try {
      const run = await postJson<ManagedRun>('/api/v1/lab/runs?workspace=simulator', token,
        { ...requested, configuration_fingerprint: confirmed.fingerprint },
        backend, key.current);
      navigate('/lab/runs/' + encodeURIComponent(run.run_id));
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Unable to start run');
    } finally {
      setPending(false);
    }
  }
  function resetKey() { key.current = null; setError(null); }

  if (workspace === 'pilot') return <InfoState kind="warning" title="Simulator controls unavailable in pilot"
    detail="Prestige remains a passive, read-only data acquisition environment."/>;
  return <Panel title="Managed simulator experiment" subtitle="An authorized local worker runs the existing Python episode">
    <div className="form-grid">
      <div><label className="field-label" htmlFor="managed-seed">Scenario seed</label>
        <input id="managed-seed" inputMode="numeric" value={seed} onChange={event=>{setSeed(event.target.value);resetKey();}}/></div>
      <div><label className="field-label" htmlFor="managed-kind">Scenario kind</label>
        <select id="managed-kind" value={kind} onChange={event=>{setKind(event.target.value as 'standard'|'challenge');resetKey();}}>
          <option value="standard">Standard seeded factory</option><option value="challenge">Compound challenge</option>
        </select></div>
      <div><label className="field-label" htmlFor="managed-mode">Investigation path</label>
        <select id="managed-mode" value={mode} onChange={event=>{setMode(event.target.value as 'triage'|'deep');resetKey();}}>
          <option value="triage">Rapid triage (optional deep escalation configured below)</option>
          <option value="deep">Deep investigation only</option>
        </select></div>
      <div><label className="field-label" htmlFor="managed-manual">Manual retrieval</label>
        <select id="managed-manual" value={manual} onChange={event=>{setManual(event.target.value as 'none'|'keyword'|'neon');resetKey();}}>
          <option value="none">Disabled</option><option value="keyword">Local keyword manual</option>
          {capability.data?.features.neon_manual_search && <option value="neon">Neon manual (SIM-CNC-001)</option>}
        </select></div>
    </div>
    <div className="quality-check"><label><input type="checkbox" checked={hazards} onChange={e=>{setHazards(e.target.checked);resetKey();}}/> Seeded tool hazards (synthetic faults)</label></div>
    <div className="quality-check"><label><input type="checkbox" checked={tree} onChange={e=>{setTree(e.target.checked);resetKey();}}/> Tree-of-Thought policy (model-only stages; deep unaffected by deterministic triage)</label></div>
    {controls ? <TriageRunEditor value={controls} mode={mode}
      onChange={next=>{setControls(next);resetKey();}}
      preview={confirmed} previewError={previewError}
      pending={previewPending} disabled={!enabled}/> :
      mode === 'triage' ? <Unavailable item="Validated per-run settings"
        detail={defaults.error || 'Connect the authorized simulator API to load stage defaults.'}/> :
      <p className="body-copy">Deep-only runs do not use triage settings.</p>}
    <p className="body-copy">Only this run receives the selected stage controls.
      Conclude remains model-backed. No pilot data or physical CNC commands are used.</p>
    {error && <InfoState kind="warning" title="Run not started" detail={error}/>}
    {!validSeed && <p role="alert">Seed must be an integer between 0 and 1,000,000.</p>}
    {enabled ? <button className="button-primary" type="button"
      disabled={!validSeed || !validBudget || !confirmed || pending} onClick={submit}>
      {pending ? 'Submitting…' : !confirmed ? 'Validate settings to start' :
        'Start run with confirmed settings'}</button> :
      <Unavailable item="Managed simulator runner" detail={preview ?
        'Exit synthetic preview to run a real simulator episode.' :
        capability.error || 'Enable CAPSTONE_UI_SIM_RUNS with approved local runner storage and operator credentials.'}/>}
    <p className="body-copy">Requires an operator token in the local Access dialog. The reviewer uses a distinct token.</p>
  </Panel>;
}

export function ManagedRunList() {
  const { data, error } = useManagedRuns();
  const { workspace, preview } = useUi();
  if (workspace === 'pilot' || preview) return null;
  return <Panel title="Managed local runs" subtitle="Durable status journal (simulator only)">
    {error && <InfoState title="Managed run history unavailable" detail={error} kind="warning"/>}
    {data?.items?.length ? <div className="incident-list">{data.items.map(run =>
      <Link to={'/lab/runs/' + encodeURIComponent(run.run_id)} className="incident-row" key={run.run_id}>
        <div className="incident-body"><strong>{run.run_id.slice(0, 13)}</strong>
          <p>Seed {run.requested.seed} · {run.requested.kind} · {run.requested.mode === 'triage' ?
            (run.requested.effective_configuration?.effective_triage?.then_deep === false ?
              'Triage only' : 'Triage (deep if needed)') : 'Deep only'}</p>
          <small>{formatStamp(run.updated_at)}
            {run.requested.effective_configuration?.fingerprint ?
              ' · config ' + run.requested.effective_configuration.fingerprint : ''}</small></div>
        <Pill text={run.state} tone={toneFor(run.state)}/>
      </Link>)}</div> : <Unavailable item="Managed run history"
      detail="No managed simulator runs have been submitted on this local installation."/>}
  </Panel>;
}

function useJournal(runId: string | undefined, token: string, enabled: boolean, backend: ApiBackend) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [status, setStatus] = useState('not_connected');
  const cursor = useRef(0);
  useEffect(() => {
    setEvents([]);
    cursor.current = 0;
    if (!enabled || !runId) return;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const abort = new AbortController();

    async function connect() {
      if (closed || !runId) return;
      try {
        setStatus('connecting');
        const url = resolveApiUrl('/api/v1/lab/runs/' + encodeURIComponent(runId) +
          '/events?workspace=simulator&since=' + cursor.current, backend, window.location.hostname);
        const response = await fetch(url, {
          headers: token ? { Authorization: 'Bearer ' + token } : {},
          signal: abort.signal, cache: 'no-store',
        });
        if (!response.ok || !response.body) throw new Error('Event stream unavailable (' + response.status + ')');
        setStatus('connected');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (!closed) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true }).replaceAll('\r\n', '\n');
          let end = buffer.indexOf('\n\n');
          while (end >= 0) {
            const frame = buffer.slice(0, end);
            buffer = buffer.slice(end + 2);
            let seq = 0, name = 'message', data = '';
            for (const line of frame.split('\n')) {
              if (line.startsWith('id: ')) seq = Number(line.slice(4));
              if (line.startsWith('event: ')) name = line.slice(7);
              if (line.startsWith('data: ')) data = line.slice(6);
            }
            if (seq > cursor.current && data) {
              const parsed: unknown = JSON.parse(data);
              cursor.current = seq;
              if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed))
                setEvents(previous=>[...previous, { seq, event: name, data: parsed as Record<string,unknown> }].slice(-250));
              if (name === 'run.completed' || name === 'run.failed' || name === 'run.interrupted') {
                setStatus('finished');
                closed = true;
              }
            }
            end = buffer.indexOf('\n\n');
          }
        }
      } catch (problem) {
        if (!closed) setStatus(problem instanceof Error ? problem.message : 'disconnected');
      }
      if (!closed) retry = setTimeout(connect, 2000);
    }
    void connect();
    return () => { closed = true; abort.abort(); if (retry) clearTimeout(retry); };
  }, [runId, token, enabled, backend]);
  return {events, status};
}

export function RunDetailPage() {
  const { runId } = useParams();
  const { workspace, preview, token, backend } = useUi();
  const enabled = workspace === 'simulator' && !preview && Boolean(runId);
  const resource = useResource<ManagedRun>(
    enabled ? '/api/v1/lab/runs/' + encodeURIComponent(runId!) + '?workspace=simulator' : null,
    token, !enabled, 3000,
  );
  const journal = useJournal(runId, token, enabled, backend);
  const audit = useResource<{availability:string; detail:InvestigationDetail|null}>(
    enabled ? '/api/v1/lab/runs/' + encodeURIComponent(runId!) +
      '/investigation?workspace=simulator' : null,
    token, !enabled, 5000,
  );
  const operational = useResource<{availability:string;window_scope?:string;items:OperationalEvent[]}>(
    enabled ? '/api/v1/lab/runs/' + encodeURIComponent(runId!) +
      '/observability?workspace=simulator' : null,
    token, !enabled, 5000,
  );
  const [section, setSection] = useState<'evidence'|'hypotheses'|'trace'>('evidence');
  const detail = audit.data?.detail;
  const run = resource.data;
  const configuration = run?.requested.effective_configuration ||
    run?.snapshot?.effective_configuration;
  const lastTriage = [...journal.events].reverse().find(event =>
    event.event === 'stage.updated' && event.data.mode === 'triage' &&
    event.data.hypothesis_progress != null
  );
  const hypothesis = (lastTriage?.data.hypothesis_progress ??
    run?.snapshot?.investigation?.hypothesis_progress) as
    SafeHypothesisProgress | null | undefined;
  if (!enabled) return <Unavailable item="Managed simulator run" detail="Select Simulator Lab and exit synthetic preview."/>;
  return <>
    <PageHeading eyebrow="LAB / LIVE EXPERIMENT" title="Managed investigation"
      description="The local Python worker owns execution, review, and final results." />
    {resource.error && <InfoState kind="warning" title="Run state unavailable" detail={resource.error}/>}
    <Panel title="Run status" subtitle={runId}>
      <DataRow label="State" value={<Pill text={run?.state || 'Unknown'} tone={toneFor(run?.state)}/>}/>
      <DataRow label="Scenario" value={run ? run.requested.kind + ', seed ' + run.requested.seed : 'Unconfirmed'}/>
      <DataRow label="Mode" value={run?.requested.mode === 'triage' ? 'Triage then deep if needed' : 'Deep only'}/>
      {run?.requested.mode === 'triage' && <DataRow label="Effective triage profile"
        value={(lastTriage?.data.triage_run_mode as string | undefined) ||
          run?.snapshot?.investigation?.triage_run_mode || 'Not recorded'}/>
      <DataRow label="Updated" value={formatStamp(run?.updated_at)}/>
      {run?.state === 'awaiting_review' && <InfoState title="Human decision required" kind="warning"
        detail="Open the Review & verification page with a reviewer token. Approval alone never executes an action."
        action={<Link className="text-link" to="/investigations/review">Review pending proposal</Link>}/>}
      {run?.snapshot?.error_class && <DataRow label="Failure classification" value={run.snapshot.error_class}/>}
    </Panel>
    <Panel title="Effective configuration for this run"
      subtitle="Immutable at submission; compare with requested stage settings">
      <DataRow label="Configuration fingerprint"
        value={configuration?.fingerprint || 'Not recorded (older run)'}/>
      <DataRow label="Triage applied"
        value={configuration ? configuration.applied ? 'Yes' : 'No, deep-only' : 'Not recorded'}/>
      <DataRow label="Conclude configured primary"
        value={configuration?.configured_conclude_primary || 'Not recorded'}/>
      <DataRow label="Model provider status"
        value={configuration?.model_attempts || 'Check run model-call observability'}/>
      {configuration?.effective_triage && ([
        ['run_mode','Deterministic override'],
        ['plan','Plan'],['investigate','Investigate / Decide / Interpret / Test'],
        ['hypothesize','Hypothesize'],['evidence_tests','Evidence tests'],
        ['packet','Observe packet'],['packet_prompt','Packet in model context'],
        ['observe_calls','Observe calls'],['then_deep','Deep escalation'],
        ['conclude_brief','Conclude evidence brief'],['conclude_cap','Conclude cap'],
        ['seconds','Triage seconds'],['tool_calls','Research tool calls'],
        ['hypothesis_seconds','Hypothesis reserve seconds'],
      ] as const).map(([key,label])=>{
        const value = configuration.effective_triage?.[key];
        const display = typeof value === 'boolean' ? value ? 'On' : 'Off' :
          value == null ? 'Unknown' : String(value);
        return <DataRow key={key} label={label} value={display}/>;
      })}
      {configuration?.overridden?.length ? <p className="body-copy">
        Requested values overridden by deterministic profile: {configuration.overridden.join(', ')}
      </p> : null}
      {configuration && <DataRow label="Graph routing"
        value={Object.entries(configuration.stages).map(([stage,method])=>
          stage + ': ' + method).join(' · ')}/>}
      <p className="body-copy">Settings are saved with the submission and cannot
        retroactively change a run. Actual model attempts require the separate audit.</p>
    </Panel>
    <Panel title="Conclusion and validation" subtitle="Only values persisted by the existing investigator">
      <DataRow label="Diagnosis" value={run?.snapshot?.diagnosis || 'Not recorded'}/>
      <DataRow label="Recommendation" value={run?.snapshot?.recommendation || 'Not recorded'}/>
      <DataRow label="Intervention executed" value={run?.snapshot?.action_executed == null ?
        'Not established' : run.snapshot.action_executed ? 'Yes, simulator only' : 'No'}/>
      <DataRow label="Verification outcome" value={run?.snapshot?.verification_outcome || 'Not verified'}/>
      <DataRow label="Escalated to deep" value={run?.snapshot?.deep_ran == null ?
        'Unknown' : run.snapshot.deep_ran ? 'Yes' : 'No'}/>
    </Panel>
    {run?.snapshot?.triage_report && <TriageReportView report={run.snapshot.triage_report}/>}
    {run?.requested.mode === 'triage' && <Panel title="Deterministic hypothesis candidates"
      subtitle="Model-free, unscored possibilities and their evidence gaps">
      <DataRow label="Rule version" value={hypothesis?.rule_version || 'Not recorded'}/>
      <DataRow label="Compiler outcome" value={hypothesis?.last_action || 'Not recorded'}/>
      <DataRow label="Candidates" value={hypothesis?.candidate_count ?? 'Not recorded'}/>
      <DataRow label="Test requirements" value={hypothesis?.test_requirements ?? 'Not recorded'}/>
      <DataRow label="Trace records" value={hypothesis?.trace_records ?? 'Not recorded'}/>
      <DataRow label="Logging failures" value={hypothesis?.logging_failures ?? 'Not recorded'}/>
      {hypothesis?.candidates.map(candidate=>
        <div key={candidate.id} className="hypothesis-card">
          <strong>{candidate.id} · {candidate.family.replaceAll('_', ' ')}</strong>
          <DataRow label="Status" value={candidate.status}/>
          <DataRow label="Qualified source references" value={candidate.qualified_sources}/>
          <DataRow label="Required checks" value={candidate.required_tests}/>
          <DataRow label="Missing checks" value={candidate.missing_tests}/>
          <DataRow label="Unavailable checks" value={candidate.unavailable_tests}/>
          <DataRow label="Open questions" value={candidate.open_questions}/>
        </div>)}
      {hypothesis?.candidates_truncated && <p className="body-copy">
        Showing the first 12 candidates.</p>}
      <p className="body-copy">Compiled candidates do not prove causation, clearance,
        or confidence. Missing telemetry remains unresolved.</p>
    </Panel>}
    <Panel title="Audited technical investigation" subtitle="Safe projection of the real completed Python audit">
      <div className="content-tabs" role="tablist" aria-label="Managed investigation details">
        {(['evidence','hypotheses','trace'] as const).map(tab=>
          <button key={tab} role="tab" aria-selected={section===tab}
            className={section===tab?'current':''} onClick={()=>setSection(tab)}>{tab}</button>)}
      </div>
      {!detail && <Unavailable item="Completed investigation audit"
        detail="The authorized audit is not present yet, or the run has not completed."/>}
      {detail && section==='evidence' && (detail.evidence.length ?
        detail.evidence.map(e=><div className="hypothesis-card" key={e.id}>
          <strong>{e.id} · {e.source_id || 'Unknown source'}</strong>
          <p>{e.content || 'No content recorded'}</p><small>{e.observed_at || 'Tick ' + (e.observed_tick ?? 'unknown')}</small>
        </div>) : <Unavailable item="Source evidence"/>)}
      {detail && section==='hypotheses' && (detail.hypotheses.length ?
        detail.hypotheses.map(h=><div className="hypothesis-card" key={h.id}>
          <h3>{h.id} · {h.description || h.claim || 'Hypothesis'}</h3>
          <Pill text={h.status || 'unverified'} tone={toneFor(h.status)}/>
          <DataRow label="Supporting evidence" value={(h.supporting_evidence_ids || []).join(', ') || 'None'}/>
          <DataRow label="Contradicting evidence" value={(h.contradicting_evidence_ids || []).join(', ') || 'None'}/>
          <DataRow label="Discriminating check" value={h.discriminating_check || 'Not recorded'}/>
        </div>) : <Unavailable item="Recorded hypotheses"/>)}
      {detail && section==='trace' && <>
        <DataRow label="Rejected/repeated calls" value={detail.reasoning_metrics?.repeated_calls ?? 'Unknown'}/>
        <DataRow label="Failed calls" value={detail.reasoning_metrics?.failed_tool_calls ?? 'Unknown'}/>
        <DataRow label="Uninterpreted evidence" value={detail.reasoning_metrics?.interpretation_failures ?? 'Unknown'}/>
        {detail.decision_trace?.length ? detail.decision_trace.map(d=>
          <DataRow key={d.sequence} label={String(d.sequence)+' · '+d.phase}
            extra={'Evidence: '+(d.evidence_ids || []).join(', ')}
            value={(d.tool || 'No tool')+' · '+d.outcome}/>) :
          <Unavailable item="Decision trace"/>}
        {detail.pruned_candidates?.length ? <div className="soft-note">
          <strong>Pruned Tree-of-Thought candidates:</strong>
          {detail.pruned_candidates.map(candidate =>
            <DataRow key={candidate.id} label={candidate.id}
              value={(candidate.status || 'unjudged') + ' · model rating ' +
                (candidate.confidence == null ? 'unknown' : String(candidate.confidence))}/>)}
        </div> : null}
        <p className="body-copy">Decision outcomes and pruned alternatives are documented verdicts, not hidden chain-of-thought. Tool arguments and raw provider responses are intentionally excluded.</p>
      </>}
    </Panel>
    <Panel title="Operational diagnostics" subtitle="Validated counters and event identifiers; no prompts, secrets or private evidence">
      {operational.error && <InfoState kind="warning" title="Diagnostics unavailable" detail={operational.error}/>}
      {operational.data?.items.length ? operational.data.items.slice(-60).reverse().map((event,index)=>
        <DataRow key={index} label={event.event}
          extra={'Investigation: ' + (event.investigation_id || 'not recorded') +
            ' · Tick: ' + (event.tick ?? 'unknown')}
          value={(event.tool || 'no tool') + ' · ' +
            (event.success == null ? 'unjudged' : event.success ? 'success' : 'failed') +
            (event.counts ? ' · ' + Object.entries(event.counts).map(([k,v])=>k+': '+v).join(', ') : '')}/>
      ) : <Unavailable item="Run diagnostics" detail="No operational trace has been recorded for this run."/>}
      <p className="body-copy">Recent event window only. These are source-linked counters, not verified fault labels.</p>
    </Panel>
    <Panel title="Stage event journal" subtitle={'Nonblocking and reconnectable · ' + journal.status}>
      {journal.events.length ? journal.events.map(row=>
        <div className="settings-row" key={row.seq}><span>{String(row.seq).padStart(4, '0')} · {row.event}</span>
          <span className="settings-value">{typeof row.data.stage === 'string' ? row.data.stage :
            typeof row.data.status === 'string' ? row.data.status : 'Recorded'}</span></div>):
        <Unavailable item="Stage updates" detail="The worker has not published any permitted stage events yet."/>}
      <p className="body-copy">Event updates are metadata only. If a UI update is dropped, the authoritative persisted run snapshot remains the source of truth.</p>
    </Panel>
  </>;
}

export function TriageReportView({ report }: { report: TriageReport }) {
  return <Panel title="Deterministic triage report" subtitle="A successful sensor read does not imply the predicate passed">
    <Pill text={report.outcome} tone={toneFor(report.assessment)}/>
    <h3>{report.summary}</h3>
    <DataRow label="Assessment" value={report.assessment}/>
    <DataRow label="Diagnosis" value={report.diagnosis || 'No accepted model diagnosis'}/>
    <DataRow label="Recommendation" value={report.recommendation}/>
    <DataRow label="Deep recommended" value={report.deep_recommended ? 'Yes' : 'No'}/>
    <DataRow label="Next discriminating check" value={report.next_check || 'Not recorded'}/>
    <DataRow label="Model answer refused because" value={report.refused_because || 'No refusal recorded'}/>
    {report.held_open_because.length > 0 && <div className="soft-note">
      <strong>Held open:</strong> {report.held_open_because.join('; ')}</div>}
    {report.unresolved_questions.length > 0 && <div className="soft-note">
      <strong>Unresolved questions:</strong> {report.unresolved_questions.join(', ')}</div>}
    {report.findings.length ? report.findings.map(item=>
      <DataRow key={item.evidence_id} label={item.evidence_id + ' · ' + item.source_id}
        value={item.excerpt}/>) : <Unavailable item="Evidence citations"/>}
  </Panel>;
}

export function ManagedTriageOverview() {
  const resource = useManagedRuns(8000);
  const reports = (resource.data?.items || []).filter(run=>run.snapshot.triage_report);
  const {preview, workspace}=useUi();
  if (preview || workspace !== 'simulator') return null;
  return <Panel title="Completed managed triage reports" subtitle="Persisted from actual run state, not inferred from completion audits">
    {reports.length ? reports.slice(0, 10).map(run=><div key={run.run_id} className="settings-row">
      <Link to={'/lab/runs/' + encodeURIComponent(run.run_id)} className="text-link">{run.run_id.slice(0,12)}</Link>
      <span>{run.snapshot.triage_report?.assessment} · {run.snapshot.triage_report?.recommendation}</span></div>):
      <Unavailable item="Managed triage reports" detail="Run a simulator investigation using the managed worker to populate this view."/>}
  </Panel>;
}

export function ManagedReviewDesk() {
  const {workspace, preview, token, backend} = useUi();
  const authorized = workspace === 'simulator' && !preview;
  const resource = useResource<ListResponse<ReviewRequest>>(
    authorized ? '/api/v1/simulator/reviews?workspace=simulator' : null, token, !authorized, 2000,
  );
  const [notes, setNotes] = useState<Record<string,string>>({});
  const [busy, setBusy] = useState<string|null>(null);
  const [message, setMessage] = useState<string|null>(null);
  if (!authorized) return null;
  async function decide(item: ReviewRequest, action: 'approve'|'reject') {
    const key = item.run_id + ':' + item.proposal_id;
    setBusy(key);
    setMessage(null);
    try {
      await postJson('/api/v1/simulator/reviews/' + encodeURIComponent(item.run_id) +
        '?workspace=simulator', token, {
        proposal_id: item.proposal_id, decision: action, note: notes[key] || '',
      }, backend);
      setMessage('Decision recorded. Execution and verification remain separate.');
    } catch (problem) {
      setMessage(problem instanceof Error ? problem.message : 'Review failed');
    } finally {
      setBusy(null);
    }
  }
  return <Panel title="Pending simulator reviews" subtitle="Authoritative approval requests from the Python worker">
    {message && <div className="soft-note" role="status">{message}</div>}
    {resource.error && <InfoState kind="warning" title="Review service unavailable" detail={resource.error}/>}
    {resource.data?.items.length ? resource.data.items.map(item=>{
      const key=item.run_id+':'+item.proposal_id;
      return <div className="hypothesis-card" key={key}>
        <h3>Proposal {item.proposal_id} · {item.action}</h3>
        <DataRow label="Machine" value={item.machine_id}/>
        <DataRow label="Reason" value={item.reason}/>
        <DataRow label="Expected effect" value={item.predicted_effect || 'Not recorded'}/>
        <label className="field-label" htmlFor={'review-note-'+item.proposal_id}>Decision note (optional)</label>
        <input id={'review-note-'+item.proposal_id} value={notes[key] || ''}
          maxLength={200} onChange={event=>setNotes(prev=>({...prev,[key]:event.target.value}))}/>
        <div className="approval-actions">
          <button className="button-primary" disabled={busy !== null} onClick={()=>decide(item,'approve')}>Approve in simulator</button>
          <button className="button-secondary" disabled={busy !== null} onClick={()=>decide(item,'reject')}>Reject proposal</button>
        </div>
        <Link to={'/lab/runs/'+item.run_id} className="text-link">View investigation</Link>
      </div>;
    }) : <Unavailable item="Pending simulator reviews"
      detail="No pending authorized requests. A reviewer token is required to approve or reject when one appears."/>}
    <p className="body-copy">No physical-machine commands or approval routes exist in the pilot workspace.</p>
  </Panel>;
}
