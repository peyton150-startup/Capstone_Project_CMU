import type { TriageRunOptions, TriageRunPreview } from '../types';
import { DataRow, Panel } from '../ui';

type Props = {
  value: TriageRunOptions;
  onChange: (next: TriageRunOptions) => void;
  mode: 'triage' | 'deep';
  preview: TriageRunPreview | null;
  previewError: string | null;
  pending: boolean;
  disabled: boolean;
};

const visibleFields: Array<{key: keyof TriageRunOptions; label: string}> = [
  {key:'run_mode', label:'Execution profile'},
  {key:'plan', label:'Plan'},
  {key:'investigate', label:'Investigate / Decide / Interpret / Test'},
  {key:'hypothesize', label:'Hypothesize'},
  {key:'evidence_tests', label:'Evidence qualification'},
  {key:'packet', label:'Observe evidence packet'},
  {key:'packet_prompt', label:'Packet coverage in model context'},
  {key:'observe_calls', label:'Observe call budget'},
  {key:'hypothesis_seconds', label:'Hypothesis reserve (seconds)'},
  {key:'then_deep', label:'Escalate to deep if unresolved'},
  {key:'conclude_brief', label:'Conclude evidence brief'},
  {key:'conclude_cap', label:'Conclude time cap'},
  {key:'seconds', label:'Total triage deadline (seconds)'},
  {key:'tool_calls', label:'Research tool-call budget'},
];

const modes = [
  ['observe', 'Observe'],
  ['manual', 'Manual retrieval'],
  ['plan', 'Plan'],
  ['investigate', 'Investigate'],
  ['decide_interpret', 'Decide / Interpret'],
  ['hypothesize', 'Hypothesize'],
  ['test', 'Test'],
  ['critic_recheck', 'Critique / Recheck'],
  ['conclude', 'Conclude'],
  ['triage_actions', 'Triage actions'],
  ['deep_escalation', 'Deep escalation'],
] as const;

export function TriageRunEditor({
  value, onChange, mode, preview, previewError, pending, disabled,
}: Props) {
  const isTriage = mode === 'triage';
  const off = disabled || !isTriage;
  const forced = value.run_mode === 'deterministic';

  function update<K extends keyof TriageRunOptions>(
    key: K, next: TriageRunOptions[K],
  ) { onChange({...value, [key]:next}); }

  const customProblem = !forced && (
    value.investigate === 'deterministic' && value.plan !== 'fixed' ?
      'Deterministic Investigate requires fixed Plan.' :
    value.hypothesize === 'deterministic' &&
    (value.plan !== 'fixed' || value.investigate !== 'deterministic' || !value.evidence_tests) ?
      'Deterministic Hypothesize requires fixed Plan, deterministic Investigate and evidence tests.' :
    value.packet_prompt && !value.packet ?
      'Packet coverage requires the Observe evidence packet.' : null
  );

  return <Panel title="Per-run triage configuration"
    subtitle="Changes apply to this new simulator run only; existing runs and server .env are unchanged">
    <div className="quality-check">
      <strong>Deterministic triage override</strong>
      <div className="button-group" role="group" aria-label="Deterministic triage">
        <button type="button" className={forced?'button-selected':'button-outline'}
          aria-pressed={forced} disabled={off}
          onClick={()=>update('run_mode','deterministic')}>On — deterministic</button>
        <button type="button" className={!forced?'button-selected':'button-outline'}
          aria-pressed={!forced} disabled={off}
          onClick={()=>update('run_mode','custom')}>Off — customize stages</button>
      </div>
    </div>
    <p className="body-copy">
      {forced ?
        'On: fixes Plan, Investigate, Decide, Interpret, Hypothesize and Test to deterministic execution; forces qualified evidence and disables triage critic calls. Conclude still uses the model.' :
        'Off: each stage uses the controls below. Invalid combinations are rejected before the run starts.'}
      {!isTriage ? ' Deep-only runs do not execute triage; the controls below are inactive.' : ''}
    </p>
    <div className="form-grid">
      <div><label className="field-label" htmlFor="triage-plan">Plan</label>
        <select id="triage-plan" disabled={off||forced} value={value.plan}
          onChange={e=>update('plan',e.target.value as TriageRunOptions['plan'])}>
          <option value="fixed">Fixed rules (no model)</option><option value="model">Model-backed</option>
        </select></div>
      <div><label className="field-label" htmlFor="triage-investigate">Investigate / Decide / Interpret / Test</label>
        <select id="triage-investigate" disabled={off||forced} value={value.investigate}
          onChange={e=>update('investigate',e.target.value as TriageRunOptions['investigate'])}>
          <option value="deterministic">Deterministic (no model)</option>
          <option value="advisory">Advisory (model + advice)</option>
          <option value="on">Compiler with model fallback</option>
          <option value="off">Model-backed</option>
        </select></div>
      <div><label className="field-label" htmlFor="triage-hypothesize">Hypothesize</label>
        <select id="triage-hypothesize" disabled={off||forced} value={value.hypothesize}
          onChange={e=>update('hypothesize',e.target.value as TriageRunOptions['hypothesize'])}>
          <option value="deterministic">Rule-based candidates</option><option value="model">Model-backed</option>
        </select></div>
      <div><label className="field-label" htmlFor="triage-observe-calls">Observe tool-call budget</label>
        <select id="triage-observe-calls" disabled={off||forced} value={value.observe_calls}
          onChange={e=>update('observe_calls',e.target.value as TriageRunOptions['observe_calls'])}>
          <option value="separate">Separate from research</option>
          <option value="shared">Shared with research</option>
        </select></div>
      <div><label className="field-label" htmlFor="triage-seconds">Triage deadline (seconds)</label>
        <input id="triage-seconds" type="number" min="5" max="900" step="1"
          disabled={off} value={value.seconds}
          onChange={e=>update('seconds',Number(e.target.value))}/></div>
      <div><label className="field-label" htmlFor="triage-tool-calls">Research tool-call budget</label>
        <input id="triage-tool-calls" type="number" min="1" max="30" step="1"
          disabled={off} value={value.tool_calls}
          onChange={e=>update('tool_calls',Number(e.target.value))}/></div>
      <div><label className="field-label" htmlFor="triage-hypothesis-seconds">Hypothesis reserve (seconds)</label>
        <input id="triage-hypothesis-seconds" type="number" min="0" max="300" step="1"
          disabled={off||forced} value={value.hypothesis_seconds}
          onChange={e=>update('hypothesis_seconds',Number(e.target.value))}/></div>
    </div>
    <div className="quality-check">
      {([
        ['evidence_tests','Evidence qualification and rival checks',forced],
        ['packet','Observe evidence packet',forced],
        ['packet_prompt','Show packet coverage to Conclude',forced],
        ['then_deep','Allow escalation into a separate deep run',false],
        ['conclude_brief','Include evidence coverage in model Conclude',false],
        ['conclude_cap','Cap the model Conclude time window',false],
      ] as const).map(([key,label,locked])=>
        <label key={key}><input type="checkbox" checked={value[key]}
          disabled={off||locked} onChange={e=>update(key,e.target.checked)}/> {label}
          {locked && forced ? ' (forced on)' : ''}</label>)}
    </div>
    {customProblem && <p role="alert">{customProblem}</p>}
    <h3>Exactly what this run will use</h3>
    {pending && <p className="body-copy">Validating the settings with the server…</p>}
    {previewError && <p role="alert">{previewError}</p>}
    {!preview && !pending && !previewError &&
      <p className="body-copy">The server has not confirmed an effective configuration.</p>}
    {preview && <>
      <DataRow label="Configuration ID" value={preview.fingerprint}/>
      <DataRow label="Scenario" value={preview.run_inputs.kind +
        ', seed ' + String(preview.run_inputs.seed)}/>
      <DataRow label="Tools & research" value={
        'Hazards: ' + (preview.run_inputs.hazards?'on':'off') +
        ' · Tree-of-Thought: ' + (preview.run_inputs.tree_of_thought?'on':'off') +
        ' · Manual: ' + preview.run_inputs.manual}/>
      <DataRow label="Conclude model (configured primary)" value={preview.configured_conclude_primary}/>
      <DataRow label="Model execution" value={preview.model_attempts}/>
      {!preview.applied && <p className="body-copy">
        Deep-only: no triage stages execute, regardless of the saved triage controls.</p>}
      {preview.applied && preview.effective_triage && <>
        {visibleFields.map(field=>{
          const effective = preview.effective_triage;
          if (!effective) return null;
          const requested = value[field.key];
          const actual = effective[field.key];
          const overridden = preview.overridden.includes(field.key);
          return <DataRow key={field.key} label={field.label}
            extra={overridden ? 'Overridden by deterministic mode' : 'Effective for this run'}
            value={String(actual) + (overridden ? ' (requested '+String(requested)+')' : '')}/>;
        })}
        <h3>Graph stage routing</h3>
        {modes.map(([key,label])=>
          <DataRow key={key} label={label} value={preview.stages[key] || 'Not recorded'}/>)}
      </>}
    </>}
    <p className="body-copy">Conclude remains model-backed in deterministic triage. Actual provider responses,
      retries and fallback models require the run's model-call trace, not this preflight.</p>
  </Panel>;
}
