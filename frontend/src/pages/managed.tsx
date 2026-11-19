import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { postJson, useResource } from '../api';
import { resolveApiUrl } from '../backend.mjs';
import type { ApiBackend } from '../backend.mjs';
import { useUi } from '../context';
import type { Capabilities, InvestigationDetail, ListResponse, ManagedRun, ReviewRequest, RunEvent, SafeHypothesisProgress, StageProgress, TriageReport, TriageRunDefaults, TriageRunOptions, TriageRunPreview } from '../types';
import { TriageRunEditor } from './triageRunEditor';
import { DataRow, formatStamp, InfoState, PageHeading, Panel, Pill, SourceState, toneFor, Unavailable } from '../ui';
import { reportHasAcceptedConclusion, selectTriageReport } from '../sourceState.mjs';
import { ModelCallTimeline } from './model_call_timeline';
import { AuditPhaseOutcome, FinalRunOutcome } from './run_outcome';
import { DeepInvestigationProgress } from './deep_progress';

type OperationalEvent = { event: string; run_id?: string; investigation_id?: string;
  tick?: number; tool?: string; success?: boolean; counts?: Record<string,number>;
  phase?: string; status?: string; reason_code?: string; attempt?: number; duration_ms?: number;
  request_hash?: string };

// Plain-English labels for the hosted worker's fixed run failure codes.
const FAILURE_LABELS: Record<string, string> = {
  artifact: 'Could not store the audit and trace files',
  configuration_mismatch: 'Worker settings differ from the submitted run',
  contract: 'A result failed its safety contract',
  database: 'Database unavailable',
  execution: 'Investigation raised an error',
  invalid_configuration: 'Malformed host run settings',
  model_setup: 'Model provider could not be configured',
};

function failureLabel(code: string | undefined, errorClass: string | undefined): string | null {
  if (code) return FAILURE_LABELS[code] ? FAILURE_LABELS[code] + ' (' + code + ')' : code;
  return errorClass ?? null;
}

const INTERRUPT_LABELS: Record<string, string> = {
  worker_lease_expired: 'Worker stopped renewing its lease',
};

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
  const [previewRevision, setPreviewRevision] = useState(0);
  const previewIdentity = JSON.stringify([
    requestSignature, token, backend, sourceKey, previewRevision,
  ]);
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
      const message = problem instanceof Error ?
        problem.message : 'Unable to start run';
      setError(message);
      if (message.includes('409') || message.includes('Settings changed')) {
        // The server may have changed after validation. Re-fetch a fresh
        // authoritative preview and avoid reusing a stale idempotency key.
        key.current = null;
        setPreviewRevision(previous => previous + 1);
      }
    } finally {
      setPending(false);
    }
  }
  function resetKey() { key.current = null; setError(null); }

  if (workspace === 'pilot') return <InfoState kind="warning" title="Simulator controls unavailable in pilot"
    detail="Prestige remains a passive, read-only data acquisition environment."/>;
  return <Panel title="Managed simulator experiment" subtitle="The selected backend runs the existing simulator episode">
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
      mode === 'triage' ? <SourceState item="Validated per-run settings" loading={defaults.loading}
        error={defaults.error} status={defaults.status}
        availability={defaults.loading || defaults.error ? null : 'not_integrated'}
        detail="The selected API did not return triage stage defaults."/> :
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
        capability.error || 'Enable CAPSTONE_UI_SIM_RUNS with approved server storage and operator credentials.'}/>}
    <p className="body-copy">Requires an operator token for the selected backend in Access. The reviewer uses a distinct token.</p>
  </Panel>;
}

export function ManagedRunList() {
  // Variables:
  //   status: HTTP status of a failed list request, so missing run credentials
  //     read as an authorization problem rather than "no runs".
  const { data, error, loading, status } = useManagedRuns();
  const { workspace, preview } = useUi();
  if (workspace === 'pilot' || preview) return null;
  return <Panel title="Managed simulator runs" subtitle="Durable status journal on the selected backend">
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
      </Link>)}</div> : <SourceState item="Managed run history" loading={loading} error={error} status={status}
      availability={data?.availability ?? null} count={0}
      emptyDetail="No managed simulator runs have been submitted to this backend."
      detail="Enable CAPSTONE_UI_SIM_RUNS with approved server storage on the selected API."/>}
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
          // Normalize after concatenation: CR/LF can cross network chunks.
          buffer = (buffer + decoder.decode(value, { stream: true })).replaceAll('\r\n', '\n');
          if (buffer.length > 65536) throw new Error('Event frame exceeded safe size');
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
            // Terminal runs may have no explicit final journal event after
            // recovery. The server marks a fully replayed terminal stream.
            if (name === 'stream.closed') {
              setStatus('finished');
              closed = true;
            }
            if (seq > cursor.current && Number.isSafeInteger(seq) && data) {
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

function readableStage(value: string | null | undefined): string {
  // Python's historical "decide" stage is actually model-backed Conclude;
  // do not mislabel it as the deterministic read-selection controller.
  if (value === 'decide') return 'Conclude (model-backed)';
  return value ? value.replaceAll('_', ' ') : 'Not reported yet';
}

/** The approved metadata contract is complete; never render unknown payload keys. */
const SAFE_METRIC_GROUPS: Array<{
  title: string;
  fields: Array<[keyof StageProgress, string]>;
}> = [
  {title: 'Decisions and budgets', fields: [
    ['answered_question_count', 'Answered questions'],
    ['decision_count', 'Recorded decisions'],
    ['remaining_iterations', 'Iterations available'],
    ['remaining_tool_calls', 'Tool calls available'],
    ['repeated_calls', 'Repeated calls blocked'],
    ['failed_tool_calls', 'Failed tool calls'],
    ['malformed_results', 'Malformed results'],
    ['interpretation_failures', 'Interpretation failures'],
    ['unproductive_steps', 'Unproductive steps'],
  ]},
  {title: 'Evidence collection', fields: [
    ['screening_tool_calls', 'Screening reads'],
    ['observe_tool_calls', 'Observe reads'],
    ['followup_tool_calls', 'Follow-up reads'],
    ['last_observed_tick', 'Last source tick'],
    ['observation_cutoff_tick', 'Authorized cutoff tick'],
    ['clock_verified', 'Source clock verified'],
    ['triage_evidence_accepted', 'Qualified evidence admissions'],
    ['triage_evidence_rejected', 'Rejected evidence admissions'],
  ]},
  {title: 'Deterministic triage', fields: [
    ['triage_requirement_total', 'Requirements compiled'],
    ['triage_requirement_satisfied', 'Requirements satisfied'],
    ['triage_requirement_open', 'Requirements still open'],
    ['triage_question_gaps', 'Unresolved evidence gaps'],
    ['triage_decide_reads', 'Deterministic Decide reads'],
    ['triage_decide_stops', 'Deterministic Decide stops'],
    ['triage_candidates', 'Unscored candidates'],
    ['triage_test_requirements', 'Test requirements'],
    ['triage_trace_events', 'Typed trace events'],
    ['triage_logging_failures', 'Diagnostic log failures'],
    ['triage_test_records', 'Evidence test records'],
    ['deep_recommended', 'Deep escalation recommended'],
  ]},
  {title: 'Source coverage packet', fields: [
    ['packet_roster_verified', 'Line roster verified'],
    ['packet_roster_size', 'Machines in roster'],
    ['packet_screened_machines', 'Machines screened'],
    ['packet_missing_machines', 'Machines absent from screening'],
    ['packet_calls_mandatory', 'Mandatory packet calls'],
    ['packet_calls_optional', 'Optional packet calls'],
    ['packet_calls_qualified', 'Qualified packet calls'],
    ['packet_calls_unavailable', 'Skipped unavailable calls'],
    ['packet_items_qualified', 'Qualified packet items'],
    ['packet_items_missing', 'Missing packet items'],
  ]},
];

function safeMetricValue(value: StageProgress[keyof StageProgress]): string | number {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  if (value === null || value === undefined) return 'Not recorded';
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  return 'Not recorded';
}

/** Only counts and IDs from the approved Python watcher, never raw evidence. */
function LiveProgress({ run }: { run: ManagedRun | null }) {
  const progress = run?.snapshot.progress;
  const latest = progress?.latest === 'triage' ? progress.triage :
    progress?.latest === 'deep' ? progress.deep : undefined;
  const active = run?.state === 'running' || run?.state === 'awaiting_review';
  const phases: Array<{ mode: 'triage' | 'deep'; name: string; data?: StageProgress }> = [
    {mode: 'triage', name: 'Rapid triage', data: progress?.triage},
    {mode: 'deep', name: 'Deep investigation', data: progress?.deep},
  ];
  return <Panel title="Investigation progress"
    subtitle="Live watcher snapshots preserved across triage and deep transitions">
    <DataRow label={active ? 'Current path' : 'Last observed path'}
      value={latest?.mode === 'triage' ? 'Rapid triage' :
        latest?.mode === 'deep' ? 'Deep investigation' : 'Awaiting stage update'}/>
    <DataRow label={active ? 'Current step' : 'Last observed step'}
      value={readableStage(latest?.stage ?? run?.snapshot.stage)}/>
    <DataRow label="Last journal update" value={formatStamp(run?.updated_at)}/>
    <div className="form-grid">
      {phases.filter(phase => phase.mode === 'deep' || run?.requested.mode === 'triage')
        .map(phase => <div className="hypothesis-card" key={phase.mode}>
          <h3>{phase.name}</h3>
          <Pill text={phase.data ?
            (active && progress?.latest === phase.mode ? 'Latest stage' : 'Recorded') :
            'Not observed'} tone={phase.data ? 'neutral' : 'warning'}/>
          {phase.data ? <>
            <DataRow label="Step" value={readableStage(phase.data.stage)}/>
            <DataRow label="Iterations" value={phase.data.iteration_count}/>
            <DataRow label="Tool calls" value={phase.data.tool_calls}/>
            <DataRow label="Evidence records" value={phase.data.evidence_count}/>
            <DataRow label="Hypotheses" value={phase.data.hypothesis_count}/>
            <DataRow label="Unresolved questions" value={Math.max(
              phase.data.unresolved_question_count ?? 0, phase.data.unresolved_question_ids.length)}/>
            {phase.data.unresolved_question_ids.length > 0 &&
              <p className="body-copy">Open question IDs: {phase.data.unresolved_question_ids.join(', ')}</p>}
            {phase.data.termination_reason &&
              <DataRow label="Termination reason" value={readableStage(phase.data.termination_reason)}/>}
            <DataRow label="Conclusion formed" value={phase.data.conclusion_available ? 'Yes' : 'Not yet'}/>
            {SAFE_METRIC_GROUPS.filter(group => phase.mode === 'triage' ||
              !['Deterministic triage', 'Source coverage packet'].includes(group.title)).map(group =>
              <div key={group.title}>
                <h4>{group.title}</h4>
                {group.fields.filter(([key]) => phase.data?.[key] !== undefined).map(([key, label]) =>
                  <DataRow key={key} label={label} value={safeMetricValue(phase.data![key])}/>)}
              </div>)}
            {phase.data.requirement_statuses?.length ? <div>
              <h4>Evidence requirements (read-only status)</h4>
              {phase.data.requirement_statuses.map(requirement =>
                <DataRow key={requirement.requirement_id}
                  label={requirement.requirement_id}
                  extra={'Qualified evidence references: ' + requirement.evidence_count}
                  value={<Pill text={requirement.status} tone={toneFor(requirement.status)}/>}/>)}
              {phase.data.requirement_statuses_truncated &&
                <p className="body-copy">Showing the first 32 requirements.
                  Total and open counts above include the full set.</p>}
            </div> : null}
            {phase.mode === 'triage' && phase.data.decide_events_recent?.length ? <div>
              <h4>Deterministic Decide trace</h4>
              <p className="body-copy">Safe metadata only. Read selection is not a diagnosis.</p>
              {phase.data.decide_events_recent.map(event =>
                <DataRow key={event.sequence}
                  label={'#' + event.sequence + ' ' + event.event.replaceAll('.', ' · ')}
                  value={readableStage(event.reason_code)}
                  extra={[
                    event.phase, event.tool,
                    event.status ? 'Status: ' + readableStage(event.status) : null,
                    event.requirement_ids.length ?
                      'Requirements: ' + event.requirement_ids.join(', ') : null,
                    event.requirement_count > event.requirement_ids.length ?
                      'Requirement IDs omitted: ' +
                        (event.requirement_count - event.requirement_ids.length) : null,
                    event.question_ids.length ?
                      'Questions: ' + event.question_ids.join(', ') : null,
                    event.question_count > event.question_ids.length ?
                      'Question IDs omitted: ' +
                        (event.question_count - event.question_ids.length) : null,
                    'Evidence references: ' + event.evidence_count,
                    event.iteration !== null ? 'Iteration: ' + event.iteration : null,
                    event.attempt !== null ? 'Attempt: ' + event.attempt : null,
                    event.candidate_count !== null ?
                      'Eligible reads: ' + event.candidate_count : null,
                    event.remaining_tool_calls !== null ?
                      'Remaining calls: ' + event.remaining_tool_calls : null,
                    event.source_cutoff_tick !== null ?
                      'Source cutoff: ' + event.source_cutoff_tick : null,
                    event.duration_ms !== null ?
                      'Duration: ' + event.duration_ms.toFixed(1) + ' ms' : null,
                    event.request_hash ? 'Request: ' + event.request_hash : null,
                  ].filter(Boolean).join(' · ')}/>)}
              {phase.data.decide_events_truncated &&
                <p className="body-copy">Showing the latest {phase.data.decide_events_recent.length}
                  of {phase.data.decide_event_total} safe Decide events. Earlier events remain
                  in the private audit; no missing events are presented as observed.</p>}
            </div> : null}
          </> : <p className="body-copy">No authenticated stage snapshot for this path yet.</p>}
        </div>)}
    </div>
    <p className="body-copy">Counts reflect observed progress, not completion percentages or verified fault probabilities.
      Evidence text, hypotheses and recommendations require a recorded, authorized audit.
      Earlier runs may have no phase-specific snapshots.</p>
  </Panel>;
}

function operationalOutcome(event: OperationalEvent): string {
  if (event.event === 'triage_packet_call_skipped_unavailable') return 'Skipped: source unavailable';
  if (event.success === false) return 'Failed';
  if (event.success === true) return 'Succeeded';
  return 'Outcome not recorded';
}

function eventStageSummary(event: RunEvent): string {
  if (event.event === 'resync.required')
    return typeof event.data.dropped_ui_updates === 'number' ?
      'Live updates dropped: ' + event.data.dropped_ui_updates : 'Live updates dropped';
  if (event.event === 'run.failed') {
    const label = failureLabel(event.data.failure_code as string | undefined,
      event.data.error_class as string | undefined);
    return label ? 'failed · ' + label : 'failed';
  }
  if (event.event === 'run.interrupted') {
    const reason = typeof event.data.reason === 'string' ?
      INTERRUPT_LABELS[event.data.reason] || readableStage(event.data.reason) : null;
    const age = event.data.heartbeat_age_seconds;
    return ['interrupted', reason,
      typeof age === 'number' ? 'Last heartbeat ' + age + ' s before recovery' : null]
      .filter(Boolean).join(' · ');
  }
  if (event.event !== 'stage.updated')
    return typeof event.data.status === 'string' ? event.data.status : 'Recorded';
  const mode = event.data.mode === 'triage' ? 'Triage' :
    event.data.mode === 'deep' ? 'Deep' : 'Path unknown';
  const stage = typeof event.data.stage === 'string' ?
    readableStage(event.data.stage) : 'Step not reported';
  const tools = event.data.tool_calls;
  const evidence = event.data.evidence_count;
  return [mode, stage,
    typeof tools === 'number' ? 'Tools: ' + tools : null,
    typeof evidence === 'number' ? 'Evidence: ' + evidence : null]
    .filter(Boolean).join(' · ');
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
  const [auditPhase, setAuditPhase] = useState<'final' | 'triage' | 'deep'>('final');
  useEffect(() => { setAuditPhase('final'); }, [runId]);
  const baseAuditPath = enabled ? '/api/v1/lab/runs/' +
    encodeURIComponent(runId!) + '/investigation?workspace=simulator' : null;
  const finalAudit = useResource<{availability:string; detail:InvestigationDetail|null}>(
    baseAuditPath, token, !enabled, 5000,
  );
  const phaseAudit = useResource<{availability:string; detail:InvestigationDetail|null}>(
    baseAuditPath && auditPhase !== 'final' ? baseAuditPath + '&phase=' + auditPhase : null,
    token, !enabled || auditPhase === 'final', 5000,
  );
  const audit = auditPhase === 'final' ? finalAudit : phaseAudit;
  const operational = useResource<{availability:string;window_scope?:string;items:OperationalEvent[]}>(
    enabled ? '/api/v1/lab/runs/' + encodeURIComponent(runId!) +
      '/observability?workspace=simulator' : null,
    token, !enabled, 5000,
  );
  const [section, setSection] = useState<'evidence'|'hypotheses'|'trace'>('evidence');
  const detail = audit.data?.detail;
  const finalDetail = finalAudit.data?.detail ?? null;
  const run = resource.data;
  const packet = operational.data?.items.slice().reverse().find(
    item => item.event === 'triage_packet_built',
  );
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
      description="The selected backend owns the simulator investigation and durable progress journal." />
    {resource.error && <InfoState kind="warning" title="Run state unavailable" detail={resource.error}/>}
    <Panel title="Run status" subtitle={runId}>
      <DataRow label="State" value={<Pill text={run?.state || 'Unknown'} tone={toneFor(run?.state)}/>}/>
      <DataRow label="Scenario" value={run ? run.requested.kind + ', seed ' + run.requested.seed : 'Unconfirmed'}/>
      <DataRow label="Mode" value={run?.requested.mode === 'triage'
        ? configuration?.effective_triage?.then_deep === false
          ? 'Triage only — no deep escalation'
          : 'Triage → deep if recommended'
        : 'Deep only'}/>
      {run?.requested.mode === 'triage' && <DataRow label="Effective triage profile"
        value={(lastTriage?.data.triage_run_mode as string | undefined) ||
          run?.snapshot?.investigation?.triage_run_mode || 'Not recorded'}/>}
      <DataRow label="Updated" value={formatStamp(run?.updated_at)}/>
      {run?.state === 'awaiting_review' && <InfoState title="Human decision required" kind="warning"
        detail="Open the Review & verification page with a reviewer token. Approval alone never executes an action."
        action={<Link className="text-link" to="/investigations/review">Review pending proposal</Link>}/>}
      {(run?.state === 'running' || run?.state === 'awaiting_review') &&
        typeof run.heartbeat_age_seconds === 'number' &&
        <DataRow label="Last worker heartbeat"
          value={<Pill text={run.heartbeat_age_seconds + ' s ago'}
            tone={run.heartbeat_age_seconds > 30 ? 'warning' : 'neutral'}/>}
          extra={run.heartbeat_age_seconds > 30 ?
            'The worker renews every 10 s; a run silent this long may be frozen.' : undefined}/>}
      {run?.state === 'failed' && failureLabel(run.snapshot?.failure_code, run.snapshot?.error_class) &&
        <DataRow label="Failure classification"
          value={failureLabel(run.snapshot?.failure_code, run.snapshot?.error_class)}/>}
      {run?.state === 'interrupted' && run.snapshot?.reason &&
        <DataRow label="Interruption reason"
          value={INTERRUPT_LABELS[run.snapshot.reason] || readableStage(run.snapshot.reason)}
          extra={typeof run.snapshot.heartbeat_age_seconds === 'number' ?
            'Last worker heartbeat ' + run.snapshot.heartbeat_age_seconds +
              ' s before recovery' : undefined}/>}
    </Panel>
    <LiveProgress run={run}/>
    <DeepInvestigationProgress run={run}/>
    {run?.requested.mode === 'triage' && <Panel title="Triage evidence packet"
      subtitle="Source-linked coverage, not a root-cause finding">
      {packet?.counts ? <>
        <div className="form-grid">
          <DataRow label="Qualified evidence items" value={packet.counts.items_qualified ?? 'Not recorded'}/>
          <DataRow label="Observed tool calls" value={packet.counts.calls_observed ?? 'Not recorded'}/>
          <DataRow label="Skipped: unavailable" value={packet.counts.calls_skipped_unavailable ?? 'Not recorded'}/>
          <DataRow label="Mandatory calls" value={packet.counts.calls_mandatory ?? 'Not recorded'}/>
          <DataRow label="Qualified calls" value={packet.counts.calls_qualified ?? 'Not recorded'}/>
          <DataRow label="Absent from screening" value={packet.counts.absent_from_screening ?? 'Not recorded'}/>
        </div>
        <p className="body-copy">A source may be unavailable without a failed tool execution.
          Qualification counts do not establish a correct diagnosis.</p>
      </> : <InfoState title="Triage packet not reported"
        detail="The collector has not published an approved packet summary for this run yet."/>}
    </Panel>}
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
    {run?.snapshot?.triage_execution && <Panel title="Observed triage execution"
      subtitle="Stage flags captured from the completed Graph, even if a deep investigation followed">
      {([
        ['run_mode','Executed profile'],
        ['fixed_plan_executed','Fixed Plan completed'],
        ['packet_enabled','Evidence packet enabled'],
        ['packet_collected','Evidence packet collected'],
        ['observe_calls_separate','Separate Observe allowance'],
        ['conclude_brief_enabled','Conclude evidence brief enabled'],
        ['conclude_cap_enabled','Conclude time cap enabled'],
        ['hypothesis_reserve_seconds','Effective hypothesis reserve (seconds)'],
        ['deadline_seconds','Triage deadline (seconds)'],
        ['research_tool_call_budget','Research tool-call limit'],
        ['actual_research_tool_calls','Research tool calls used'],
        ['deterministic_decide_reads','Deterministic Decide reads'],
        ['compiled_candidates','Compiled candidate count'],
        ['conclusion_available','Conclude stage completed'],
        ['deep_recommended','Deep investigation recommended'],
      ] as const).map(([key,label])=>{
        const value = run.snapshot.triage_execution?.[key];
        const shown = typeof value === 'boolean' ? value ? 'On' : 'Off' :
          value == null ? 'Unknown' : String(value);
        return <DataRow key={key} label={label} value={shown}/>;
      })}
      <p className="body-copy">These fields describe actual Graph state, not
        model-call success. See model-call observability for provider attempts.</p>
    </Panel>}
    {finalAudit.error && <InfoState kind="warning" title="Final audit request failed"
      detail={finalAudit.error}/>}
    <FinalRunOutcome run={run} detail={finalDetail}/>
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
    <Panel title="Audited technical investigation"
      subtitle="Select a completed phase; the viewer never receives simulator hidden truth">
      <div className="content-tabs" role="tablist" aria-label="Completed audit phase">
        <button role="tab" aria-selected={auditPhase === 'final'}
          className={auditPhase === 'final' ? 'current' : ''}
          onClick={() => setAuditPhase('final')}>Final audit</button>
        {run?.requested.mode === 'triage' && <button role="tab"
          aria-selected={auditPhase === 'triage'}
          className={auditPhase === 'triage' ? 'current' : ''}
          onClick={() => setAuditPhase('triage')}>Triage audit</button>}
        {run?.requested.mode === 'triage' &&
          (run?.snapshot.progress?.deep || run?.snapshot.deep_ran === true) && <button
            role="tab" aria-selected={auditPhase === 'deep'}
            className={auditPhase === 'deep' ? 'current' : ''}
            onClick={() => setAuditPhase('deep')}>Deep audit</button>}
      </div>
      {audit.error && <InfoState kind="warning" title="Selected audit request failed"
        detail={audit.error}/>}
      {detail && <AuditPhaseOutcome detail={detail} phase={auditPhase}/>}
      <div className="content-tabs" role="tablist" aria-label="Managed investigation details">
        {(['evidence','hypotheses','trace'] as const).map(tab=>
          <button key={tab} role="tab" aria-selected={section===tab}
            className={section===tab?'current':''} onClick={()=>setSection(tab)}>{tab}</button>)}
      </div>
      {!detail && !audit.error && <InfoState
        title={audit.loading ? 'Loading authorized audit' :
          run?.state === 'running' || run?.state === 'awaiting_review' ?
            'Selected phase audit pending' : 'Selected phase audit not recorded'}
        detail={audit.loading ? 'Reading the selected completed investigation record.' :
          run?.state === 'running' || run?.state === 'awaiting_review' ?
            'A phase audit appears only after the corresponding investigation is completed and recorded.' :
            'No permitted audit was recorded for this phase. Earlier runs may lack separate triage/deep identifiers.'}/>}
      {detail && section==='evidence' && (detail.evidence.length ?
        detail.evidence.map(e=><div className="hypothesis-card" key={e.id}>
          <strong>{e.id} · {e.source_id || 'Unknown source'}</strong>
          <p>{e.content || 'No content recorded'}</p><small>{e.observed_at || 'Tick ' + (e.observed_tick ?? 'unknown')}</small>
        </div>) : <SourceState item="Source evidence" availability="available" count={0}
          emptyDetail="This phase audit recorded no evidence items."/>)}
      {detail && section==='hypotheses' && (detail.hypotheses.length ?
        detail.hypotheses.map(h=><div className="hypothesis-card" key={h.id}>
          <h3>{h.id} · {h.description || h.claim || 'Hypothesis'}</h3>
          <Pill text={h.status || 'unverified'} tone={toneFor(h.status)}/>
          <DataRow label="Model rating" value={h.confidence == null ?
            'Not recorded' : Math.round(h.confidence * 100) + '/100 (uncalibrated)'}/>
          <DataRow label="Unexplained evidence" value={(h.unexplained_evidence_ids || []).join(', ') || 'None recorded'}/>
          <DataRow label="Supporting evidence" value={(h.supporting_evidence_ids || []).join(', ') || 'None'}/>
          <DataRow label="Contradicting evidence" value={(h.contradicting_evidence_ids || []).join(', ') || 'None'}/>
          <DataRow label="Discriminating check" value={h.discriminating_check || 'Not recorded'}/>
        </div>) : <SourceState item="Recorded hypotheses" availability="available" count={0}
          emptyDetail="This phase audit recorded no candidate explanations."/>)}
      {detail && section==='trace' && <>
        <DataRow label="Iterations" value={detail.reasoning_metrics?.iterations ?? 'Not recorded'}/>
        <DataRow label="Tool calls" value={detail.reasoning_metrics?.tool_calls ?? 'Not recorded'}/>
        <DataRow label="Repeated calls" value={detail.reasoning_metrics?.repeated_calls ?? 'Not recorded'}/>
        <DataRow label="Failed calls" value={detail.reasoning_metrics?.failed_tool_calls ?? 'Not recorded'}/>
        <DataRow label="Malformed results" value={detail.reasoning_metrics?.malformed_results ?? 'Not recorded'}/>
        <DataRow label="Interpretation failures" value={detail.reasoning_metrics?.interpretation_failures ?? 'Not recorded'}/>
        <DataRow label="Hypothesis revisions" value={detail.reasoning_metrics?.hypothesis_revisions ?? 'Not recorded'}/>
        {detail.decision_trace?.length ? detail.decision_trace.map(d=>
          <DataRow key={d.sequence} label={String(d.sequence)+' · '+d.phase}
            extra={'Tick: ' + (d.tick ?? 'unknown') +
              ' · Question: ' + (d.question_id || 'not recorded') +
              ' · Hypothesis: ' + (d.hypothesis_id || 'not recorded') +
              ' · Evidence: ' + (d.evidence_ids || []).join(', ')}
            value={(d.tool || 'No tool')+' · '+d.outcome +
              (d.termination_reason ? ' · stopped: ' + d.termination_reason : '')}/>) :
          <SourceState item="Decision trace" availability="available" count={0}
            emptyDetail="This phase audit recorded no decision steps."/>}
        {detail.pruned_candidates?.length ? <div className="soft-note">
          <strong>Pruned Tree-of-Thought candidates:</strong>
          {detail.pruned_candidates.map(candidate =>
            <DataRow key={candidate.id} label={candidate.id}
              value={(candidate.status || 'unjudged') + ' · model rating ' +
                (candidate.confidence == null ? 'unknown' : String(candidate.confidence)) +
                ' · supporting: ' + ((candidate.supporting_evidence_ids || []).join(', ') || 'not recorded') +
                ' · contradicting: ' + ((candidate.contradicting_evidence_ids || []).join(', ') || 'not recorded')}/>)}
        </div> : null}
        <p className="body-copy">Decision outcomes and pruned alternatives are documented verdicts, not hidden chain-of-thought. Tool arguments and raw provider responses are intentionally excluded.</p>
      </>}
    </Panel>
    <ModelCallTimeline runId={runId}/>
    <Panel title="Operational diagnostics" subtitle="Bounded availability and evidence-packet coverage">
      {operational.data?.items.length ? operational.data.items.slice(-60).reverse().map((event,index)=>
        <DataRow key={index} label={readableStage(event.event)}
          extra={['Investigation: ' + (event.investigation_id || 'not recorded'),
            'Tick: ' + (event.tick ?? 'unknown'),
            event.phase ? 'Phase: ' + readableStage(event.phase) : null,
            event.status ? 'Status: ' + readableStage(event.status) : null,
            event.reason_code ? 'Reason: ' + readableStage(event.reason_code) : null,
            event.attempt != null ? 'Attempt ' + event.attempt : null,
            event.duration_ms != null ? Math.round(event.duration_ms) + ' ms' : null,
            event.request_hash ? 'Request: ' + event.request_hash : null]
            .filter(Boolean).join(' · ')}
          value={(event.tool || 'No tool selected') + ' · ' + operationalOutcome(event) +
            (event.counts ? ' · ' + Object.entries(event.counts).map(([k,v])=>
              readableStage(k)+': '+v).join(', ') : '')}/>
      ) : <SourceState item="Run diagnostics" loading={operational.loading} error={operational.error}
        status={operational.status} availability={operational.data?.availability ?? null} count={0}
        emptyDetail="No operational trace has been recorded for this run yet."/>}
      <p className="body-copy">Skipped unavailable sources are not failed executions.
        Packet counts and qualified calls indicate observed coverage, not proof of root cause.</p>
    </Panel>
    <Panel title="Stage event journal" subtitle={'Nonblocking and reconnectable · ' + journal.status}>
      {journal.events.length ? journal.events.map(row=>
        <div className="settings-row" key={row.seq}><span>{String(row.seq).padStart(4, '0')} · {row.event}</span>
          <span className="settings-value">{eventStageSummary(row)}</span></div>):
        <InfoState title={journal.status === 'connecting' ? 'Connecting to the stage journal' : 'No stage updates yet'}
          detail={'The worker has not published any permitted stage events for this run (stream: ' + journal.status + ').'}/>}
      <p className="body-copy">Event updates are metadata only. If a UI update is dropped, the authoritative persisted run snapshot remains the source of truth.</p>
    </Panel>
  </>;
}

export function TriageReportView({ report }: { report: TriageReport }) {
  // Variables:
  //   accepted: True only for an accepted model conclusion; a refused or
  //     missing model answer never shows a diagnosis or a 0/100 rating.
  const accepted = reportHasAcceptedConclusion(report);
  return <Panel title="Deterministic triage report"
    subtitle="The model answer, Python checks, and observed evidence are distinct results">
    <Pill text={report.outcome} tone={toneFor(report.assessment)}/>
    <h3>{report.summary}</h3>
    <DataRow label="Alarmed machine" value={report.machine_id || 'Not recorded'}/>
    <DataRow label="Alarm / initial anomaly" value={report.alarm}/>
    <DataRow label="Alarm observed at" value={report.alarm_tick == null ?
      'Not recorded' : 'Tick ' + report.alarm_tick}/>
    <DataRow label="Assessment" value={report.assessment}/>
    <DataRow label="Diagnosis" value={accepted && report.diagnosis ? report.diagnosis :
      'No accepted model diagnosis'}/>
    <DataRow label="Model rating" value={!accepted ?
      'Not applicable — no accepted model answer' :
      Math.round(report.confidence * 100) + '/100 (uncalibrated)'}/>
    <DataRow label="Model's initial recommendation" value={report.model_recommendation || 'Not recorded'}/>
    <DataRow label="Final checked recommendation" value={report.recommendation}/>
    <DataRow label="Termination reason" value={report.termination_reason || 'Not recorded'}/>
    <DataRow label="Deep recommended" value={report.deep_recommended ? 'Yes' : 'No'}/>
    <DataRow label="Next discriminating check" value={report.next_check || 'Not recorded'}/>
    <DataRow label="Model answer refused because" value={report.refused_because || 'No refusal recorded'}/>
    {report.held_open_because.length > 0 && <div className="soft-note">
      <strong>Held open:</strong> {report.held_open_because.join('; ')}</div>}
    {report.unresolved_questions.length > 0 && <div className="soft-note">
      <strong>Unresolved questions:</strong> {report.unresolved_questions.join(', ')}</div>}
    {report.findings.length ? report.findings.map(item=>
      <div className="hypothesis-card" key={item.evidence_id}>
        <strong>{item.evidence_id} · {item.source_id}</strong>
        <p>{item.excerpt}</p>
        <DataRow label="Provenance" value={item.origin || 'Not recorded'}/>
        <DataRow label="Observed tick" value={item.observed_tick ?? 'Not recorded'}/>
      </div>) : <SourceState item="Evidence citations" availability="available" count={0}
        emptyDetail="This report cites no findings."/>}
    <p className="body-copy">A successful sensor read does not imply a passed predicate or a verified fault.
      The listed model rating is not a calibrated fault probability.</p>
  </Panel>;
}

/** Rapid Triage: choose a managed run and read its persisted TriageReport.
 * The report comes from the run snapshot the worker wrote, never rebuilt. */
export function ManagedTriageReportPicker() {
  // Variables:
  //   selected: The run id the user picked; selectTriageReport ignores it when
  //     that run has no report, so a stale choice cannot mislabel another run.
  //   picked: The runs that carry a report, the chosen run and its report.
  const resource = useManagedRuns(8000);
  const [selected, setSelected] = useState<string | null>(null);
  const picked = selectTriageReport(resource.data?.items, selected);
  if (!picked.report || !picked.run) return <SourceState item="Typed triage report" loading={resource.loading}
    error={resource.error} status={resource.status} availability={resource.data?.availability ?? null} count={0}
    emptyDetail="No managed run on this backend has persisted a typed triage report yet. Start a Rapid triage run in the Experiment lab."
    detail="Typed triage reports come from managed simulator runs; enable CAPSTONE_UI_SIM_RUNS on the selected API."/>;
  return <>
    <label className="field-label" htmlFor="triage-report-run">Managed run</label>
    <select id="triage-report-run" value={picked.run.run_id}
      onChange={event => setSelected(event.target.value)}>
      {picked.runs.map(run => <option key={run.run_id} value={run.run_id}>
        {run.run_id.slice(0, 12) + ' · seed ' + run.requested.seed + ' · ' + formatStamp(run.updated_at)}</option>)}
    </select>
    <TriageReportView report={picked.report}/>
    <Link to={'/lab/runs/' + encodeURIComponent(picked.run.run_id)} className="text-link">Open the full run</Link>
  </>;
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
      <SourceState item="Managed triage reports" loading={resource.loading} error={resource.error}
        status={resource.status} availability={resource.data?.availability ?? null} count={0}
        emptyDetail="No managed run on this backend has persisted a triage report yet. Run a triage investigation from the Experiment lab."/>}
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
    }) : <SourceState item="Pending simulator reviews" loading={resource.loading} error={resource.error}
      status={resource.status} availability={resource.data?.availability ?? null} count={0}
      emptyDetail="No proposal is waiting for review. A reviewer token is required to approve or reject one when it appears."/>}
    <p className="body-copy">No physical-machine commands or approval routes exist in the pilot workspace.</p>
  </Panel>;
}
