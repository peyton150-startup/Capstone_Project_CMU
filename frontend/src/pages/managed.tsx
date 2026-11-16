import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getJson, postJson, useResource } from '../api';
import { useUi } from '../context';
import type { Capabilities, ListResponse, ManagedRun, ReviewRequest, RunEvent, TriageReport } from '../types';
import { DataRow, formatStamp, InfoState, PageHeading, Panel, Pill, toneFor, Unavailable } from '../ui';

function useManagedRuns(pollMs = 5000) {
  const { workspace, preview, token } = useUi();
  return useResource<ListResponse<ManagedRun>>(
    workspace === 'simulator' && !preview ? '/api/v1/lab/runs?workspace=simulator' : null,
    token, preview || workspace !== 'simulator', pollMs,
  );
}

export function ManagedRunLauncher() {
  const { workspace, preview, token } = useUi();
  const capability = useResource<Capabilities>('/api/v1/capabilities', token, preview);
  const navigate = useNavigate();
  const [seed, setSeed] = useState('3');
  const [kind, setKind] = useState<'standard' | 'challenge'>('standard');
  const [mode, setMode] = useState<'triage' | 'deep'>('triage');
  const [hazards, setHazards] = useState(false);
  const [tree, setTree] = useState(false);
  const [manual, setManual] = useState<'none' | 'keyword'>('none');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useRef<string | null>(null);
  const enabled = workspace === 'simulator' && !preview &&
    capability.data?.features.simulation_run_launch === true;
  const parsedSeed = Number(seed);
  const validSeed = Number.isInteger(parsedSeed) && parsedSeed >= 0 && parsedSeed <= 1000000;

  async function submit() {
    if (!enabled || !validSeed || pending) return;
    setPending(true);
    setError(null);
    if (!key.current) key.current = crypto.randomUUID().replaceAll('-', '');
    try {
      const run = await postJson<ManagedRun>('/api/v1/lab/runs?workspace=simulator', token,
        { seed: parsedSeed, kind, mode, hazards, tree_of_thought: tree, manual }, key.current);
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
          <option value="triage">Rapid triage → deep if needed</option>
          <option value="deep">Deep investigation only</option>
        </select></div>
      <div><label className="field-label" htmlFor="managed-manual">Manual retrieval</label>
        <select id="managed-manual" value={manual} onChange={event=>{setManual(event.target.value as 'none'|'keyword');resetKey();}}>
          <option value="none">Disabled</option><option value="keyword">Local keyword manual</option>
        </select></div>
    </div>
    <div className="quality-check"><label><input type="checkbox" checked={hazards} onChange={e=>{setHazards(e.target.checked);resetKey();}}/> Seeded tool hazards</label></div>
    <div className="quality-check"><label><input type="checkbox" checked={tree} onChange={e=>{setTree(e.target.checked);resetKey();}}/> Tree-of-Thought policy</label></div>
    <p className="body-copy">The run uses server-owned model configuration. A triage run can escalate into a deep investigation under the Python decision policy. No pilot data or physical CNC commands are used.</p>
    {error && <InfoState kind="warning" title="Run not started" detail={error}/>}
    {!validSeed && <p role="alert">Seed must be an integer between 0 and 1,000,000.</p>}
    {enabled ? <button className="button-primary" type="button" disabled={!validSeed || pending} onClick={submit}>
      {pending ? 'Submitting…' : 'Start authorized simulator run'}</button> :
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
            'Triage (deep if needed)' : 'Deep only'}</p>
          <small>{formatStamp(run.updated_at)}</small></div>
        <Pill text={run.state} tone={toneFor(run.state)}/>
      </Link>)}</div> : <Unavailable item="Managed run history"
      detail="No managed simulator runs have been submitted on this local installation."/>}
  </Panel>;
}

function useJournal(runId: string | undefined, token: string, enabled: boolean) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [status, setStatus] = useState('not_connected');
  const cursor = useRef(0);
  useEffect(() => {
    setEvents([]);
    cursor.current = 0;
    if (!enabled || !runId || !token) return;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const abort = new AbortController();

    async function connect() {
      if (closed || !runId) return;
      try {
        setStatus('connecting');
        const response = await fetch('/api/v1/lab/runs/' + encodeURIComponent(runId) +
            '/events?workspace=simulator&since=' + cursor.current, {
          headers: { Authorization: 'Bearer ' + token }, signal: abort.signal, cache: 'no-store',
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
  }, [runId, token, enabled]);
  return {events, status};
}

export function RunDetailPage() {
  const { runId } = useParams();
  const { workspace, preview, token } = useUi();
  const enabled = workspace === 'simulator' && !preview && Boolean(runId);
  const resource = useResource<ManagedRun>(
    enabled ? '/api/v1/lab/runs/' + encodeURIComponent(runId!) + '?workspace=simulator' : null,
    token, !enabled, 3000,
  );
  const journal = useJournal(runId, token, enabled);
  const run = resource.data;
  if (!enabled) return <Unavailable item="Managed simulator run" detail="Select Simulator Lab and exit synthetic preview."/>;
  return <>
    <PageHeading eyebrow="LAB / LIVE EXPERIMENT" title="Managed investigation"
      description="The local Python worker owns execution, review, and final results." />
    {resource.error && <InfoState kind="warning" title="Run state unavailable" detail={resource.error}/>}
    <Panel title="Run status" subtitle={runId}>
      <DataRow label="State" value={<Pill text={run?.state || 'Unknown'} tone={toneFor(run?.state)}/>}/>
      <DataRow label="Scenario" value={run ? run.requested.kind + ', seed ' + run.requested.seed : 'Unconfirmed'}/>
      <DataRow label="Mode" value={run?.requested.mode === 'triage' ? 'Triage then deep if needed' : 'Deep only'}/>
      <DataRow label="Updated" value={formatStamp(run?.updated_at)}/>
      {run?.state === 'awaiting_review' && <InfoState title="Human decision required" kind="warning"
        detail="Open the Review & verification page with a reviewer token. Approval alone never executes an action."
        action={<Link className="text-link" to="/investigations/review">Review pending proposal</Link>}/>}
      {run?.snapshot?.error_class && <DataRow label="Failure classification" value={run.snapshot.error_class}/>}
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
  const {workspace, preview, token} = useUi();
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
      });
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
