import { useResource } from '../api';
import { useUi } from '../context';
import { DataRow, InfoState, Panel, Pill } from '../ui';

type AttemptOutcome = 'answered' | 'invalid_reply' | 'timeout' | 'rate_limited' |
  'unauthorized' | 'forbidden' | 'request_rejected' | 'provider_error' |
  'unavailable' | 'budget_exhausted' | 'skipped' | 'other_error';

type Attempt = {
  attempt_index: number;
  model: string;
  outcome: AttemptOutcome;
  seconds: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  prompt_chars: number | null;
  prompt_version: string | null;
  retry: boolean;
  fallback: boolean;
};
type ModelCall = {
  seq: number;
  schema_version: 1;
  question_index: number;
  job: string;
  agent: string;
  stage: string | null;
  mode: 'triage' | 'deep' | null;
  outcome: 'answered' | 'invalid_reply' | 'no_answer';
  answered_by: string | null;
  attempts: Attempt[];
  omitted_attempts: number;
  retry_count: number;
  fallback_selected: boolean;
  fallback_succeeded: boolean;
};
type ModelCallResponse = {
  availability: 'available' | 'not_recorded';
  window_scope: 'latest_200';
  truncated: boolean;
  configuration: 'configured' | 'missing_credentials' | 'invalid_configuration' | null;
  summary: {
    schema_version: 1;
    questions_seen: number;
    questions_persisted: number;
    write_failures: number;
    complete: boolean;
  } | null;
  items: ModelCall[];
};

function tone(outcome: string): 'good' | 'warning' | 'critical' | 'neutral' {
  if (outcome === 'answered') return 'good';
  if (['unauthorized', 'forbidden', 'no_answer', 'provider_error'].includes(outcome))
    return 'critical';
  if (outcome === 'skipped') return 'neutral';
  return 'warning';
}

function detail(attempt: Attempt): string {
  const elapsed = attempt.seconds == null ? 'Time unreported' :
    attempt.seconds.toFixed(3) + ' s';
  const tokens = attempt.input_tokens == null && attempt.output_tokens == null ?
    'Token usage unavailable' :
    'Tokens in/out: ' + (attempt.input_tokens ?? '—') + ' / ' +
      (attempt.output_tokens ?? '—');
  const route = attempt.fallback ? ' · fallback' : attempt.retry ? ' · retry' : '';
  return elapsed + ' · ' + tokens + route +
    (attempt.prompt_chars == null ? '' : ' · prompt chars ' + attempt.prompt_chars) +
    (attempt.prompt_version ? ' · prompt version ' + attempt.prompt_version.slice(0, 12) : '');
}

/** Safe, durable metadata only. The server never exposes prompts or raw exceptions. */
export function ModelCallTimeline({ runId }: { runId: string | undefined }) {
  const { workspace, preview, token } = useUi();
  const enabled = workspace === 'simulator' && !preview && Boolean(runId);
  const resource = useResource<ModelCallResponse>(
    enabled ? '/api/v1/lab/runs/' + encodeURIComponent(runId!) +
      '/model-calls?workspace=simulator' : null,
    token, !enabled, 4000,
  );
  if (!enabled) return null;
  const calls = resource.data?.items ?? [];
  const attempts = calls.reduce((sum, call) => sum + call.attempts.length, 0);
  const inTokens = calls.reduce((sum, call) =>
    sum + call.attempts.reduce((sub, a) => sub + (a.input_tokens ?? 0), 0), 0);
  const outTokens = calls.reduce((sum, call) =>
    sum + call.attempts.reduce((sub, a) => sub + (a.output_tokens ?? 0), 0), 0);
  return <Panel title="Model request timeline"
    subtitle="Persisted attempt metadata · local or Render backend · no model prompts or responses">
    {resource.error && <InfoState kind="warning" title="Model telemetry unavailable"
      detail={resource.error}/>}
    {resource.data?.availability === 'not_recorded' && <InfoState
      title="Model telemetry was not collected for this run"
      detail="Older investigations predate model-call recording. Run a new investigation with an updated backend."/>}
    {resource.loading && !resource.data && <p className="body-copy">Reading model request history…</p>}
    {resource.data?.configuration === 'missing_credentials' && <InfoState
      kind="warning" title="Model provider credentials were not configured"
      detail="The backend could not initialize the selected model. For Local, check the API process environment and .env; for Render, check that service's secret environment variables."/>}
    {resource.data?.configuration === 'invalid_configuration' && <InfoState
      kind="warning" title="Model provider configuration failed"
      detail="The backend could not construct its model client. Check the selected backend's model routing and provider settings; private exception details are never sent to the browser."/>}
    {resource.data?.summary && !resource.data.summary.complete && <InfoState
      kind="warning" title="Model call history is incomplete"
      detail={'The worker observed ' + resource.data.summary.questions_seen +
        ' questions but persisted ' + resource.data.summary.questions_persisted +
        '. A storage error prevented complete telemetry capture.'}/>}
    {resource.data?.availability === 'available' && <>
      <div className="form-grid">
        <DataRow label="Model questions" value={calls.length}/>
        <DataRow label="Recorded attempts" value={attempts}/>
        <DataRow label="Journal completeness" value={resource.data.summary ?
          resource.data.summary.complete ? 'Complete' : 'Incomplete' : 'In progress / unknown'}/>
        <DataRow label="Reported input tokens" value={inTokens || 'None reported'}/>
        <DataRow label="Reported output tokens" value={outTokens || 'None reported'}/>
      </div>
      {resource.data.truncated && <InfoState kind="warning" title="Older calls omitted"
        detail="This endpoint shows the 200 most recent model questions, not an unlimited history."/>}
      {!calls.length && <InfoState title="No model question attempted yet"
        detail="The worker has enabled model-call monitoring, but has not recorded a model question. Deterministic stages can run without an LLM."/>}
      {calls.map(call=><div className="hypothesis-card" key={call.seq}>
        <h3>{call.question_index}. {call.mode || 'unknown mode'} · {call.stage || 'unknown stage'} · {call.job}</h3>
        <Pill text={call.outcome} tone={tone(call.outcome)}/>
        <DataRow label="Agent" value={call.agent}/>
        <DataRow label="Answered by" value={call.answered_by || 'No accepted model answer'}/>
        <DataRow label="Retries / fallback" value={call.retry_count + ' retries · ' +
          (call.fallback_succeeded ? 'fallback answered' :
            call.fallback_selected ? 'fallback attempted' : 'no fallback attempted')}/>
        {call.attempts.length ? call.attempts.map(attempt=>
          <DataRow key={attempt.attempt_index}
            label={'Attempt ' + attempt.attempt_index + ' · ' + attempt.model}
            extra={detail(attempt)}
            value={<Pill text={attempt.outcome} tone={tone(attempt.outcome)}/>}/>
        ) : <p className="body-copy">No request attempts recorded for this question.</p>}
        {call.omitted_attempts > 0 && <p className="body-copy">
          {call.omitted_attempts} additional attempts omitted by the safety limit.</p>}
      </div>)}
    </>}
    <p className="body-copy">Attempt failures are categorized on the server. No API keys,
      provider error bodies, prompt text, response text, tool arguments or simulator
      hidden truth are included. Token counts appear only when the provider reports them.</p>
  </Panel>;
}
