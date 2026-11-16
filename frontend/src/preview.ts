import type { Evaluation, InvestigationDetail, Machine, RecorderSnapshot, Sample } from './types';

// Explicit visual preview only. Never sent to the Python backend, never called shop data.
export const demoMachines: Machine[] = [
  { id: 'CNC-01', name: 'CNC-01', operating_state: 'Running', condition: 'Nominal', signal_count: 5 },
  { id: 'CNC-02', name: 'CNC-02', operating_state: 'Investigating', condition: 'Warning', signal_count: 6 },
  { id: 'CNC-04', name: 'CNC-04', operating_state: 'Idle', condition: 'Nominal', signal_count: 4 },
];
export const demoInvestigations: InvestigationDetail[] = [
  {
    id: 'DEMO-1042', run_id: 'DEMO-A17', summary: 'Spindle temperature increased above its recent baseline',
    symptoms: ['Sustained temperature rise', 'Spindle load higher than preceding window'],
    diagnosis: 'Increased mechanical load is a plausible explanation, not verified',
    model_confidence: 0.71, termination_reason: 'unresolved / further evidence required',
    evidence_count: 4, hypothesis_count: 3, tool_calls: 6, iterations: 4,
    verification: 'unverified',
    evidence: [
      { id: 'E-01', source_id: 'TemperatureSensor', source_type: 'telemetry', content: 'Spindle temperature above earlier samples', observed_tick: 122 },
      { id: 'E-02', source_id: 'LoadSensor', source_type: 'telemetry', content: 'Load increased during the same observation window', observed_tick: 125 },
      { id: 'E-03', source_id: 'RoomTemperature', source_type: 'telemetry', content: 'Room temperature changed modestly', observed_tick: 127 },
      { id: 'E-04', source_id: 'ManualSearch', source_type: 'document', content: 'Recommended checks depend on actual tooling and duty cycle', observed_tick: 129 },
    ],
    hypotheses: [
      { id: 'H-01', description: 'Increased spindle load', status: 'unresolved', confidence: 0.71,
        supporting_evidence_ids: ['E-01', 'E-02'], contradicting_evidence_ids: [],
        discriminating_check: 'Compare similar cutting cycles under matched tools and feed' },
      { id: 'H-02', description: 'Thermal drift', status: 'possible', confidence: 0.43,
        supporting_evidence_ids: ['E-01'], contradicting_evidence_ids: ['E-03'],
        discriminating_check: 'Compare coolant and ambient readings' },
      { id: 'H-03', description: 'Sensor measurement fault', status: 'possible', confidence: 0.29,
        supporting_evidence_ids: [], contradicting_evidence_ids: [],
        discriminating_check: 'Cross-check a verified independent sensor' },
    ],
    proposed_action: null,
    verification_detail: { status: 'unverified', outcome: 'unknown', summary: 'No intervention was executed' },
  },
  {
    id: 'DEMO-1041', run_id: 'DEMO-A16', summary: 'Load sensor data unavailable during an alarm',
    diagnosis: '', model_confidence: null, termination_reason: 'insufficient reliable telemetry',
    evidence_count: 2, hypothesis_count: 0, tool_calls: 3, iterations: 2,
    verification: 'unverified', evidence: [], hypotheses: [], proposed_action: null,
  },
];
export const demoRecorder: RecorderSnapshot = {
  availability: 'available', message: 'Synthetic preview — no OPC UA connection',
  recorder: {
    id: 'siemens-demo', source: 'SIMULATED OPC UA FIXTURE',
    process_state: 'running', connection_state: 'connected',
    subscription_state: 'confirmed', measurement_state: 'received_recently',
    received: 12450, good: 12375, uncertain: 43, bad: 32,
    overflow: 0, gaps: 1, reconnections: 1, invalid_lines: 0, unsupported: 0,
    output_bytes: 6428000, sink_state: 'healthy',
    analysis_eligible: null, last_receive_at: new Date().toISOString(),
    session_epoch: 2, disk_free_bytes: null, window_scope: 'SYNTHETIC_PREVIEW',
  },
  signals: [
    { id: 'demo-rpm', label: 'Spindle RPM', value: 8200, unit: 'rpm', quality: 'good', freshness: 'fresh', analysis_eligible: false, received_at: new Date().toISOString() },
    { id: 'demo-load', label: 'Spindle load', value: 42.1, unit: '%', quality: 'good', freshness: 'fresh', analysis_eligible: false, received_at: new Date().toISOString() },
    { id: 'demo-temp', label: 'Spindle temperature', value: 147.6, unit: '°F', quality: 'uncertain', freshness: 'review', analysis_eligible: false, received_at: new Date().toISOString() },
    { id: 'demo-state', label: 'Execution state', value: 'Running', unit: null, quality: 'good', freshness: 'change-only', analysis_eligible: false, received_at: new Date().toISOString() },
  ],
  events: [
    { event: 'heartbeat', at: new Date().toISOString(), epoch: 2 },
    { event: 'connected', at: new Date(Date.now() - 900000).toISOString(), epoch: 2 },
    { event: 'gap', at: new Date(Date.now() - 930000).toISOString(), epoch: 1 },
  ],
};
export const demoEvaluations: Evaluation[] = [
  { id: 'RUN-A0-001', scenario: 'KA-01', seed: 3, conclusion: 'Unresolved — further tests',
    assessment: 'unresolved', recommendation: 'escalate',
    verification: 'unverified', wall_seconds: 24.3, tool_count: 5, model_questions: 1 },
  { id: 'RUN-A0-002', scenario: 'KA-02', seed: 4, conclusion: 'Temperature trend supported',
    assessment: 'supported', recommendation: 'no_action',
    verification: 'unverified', wall_seconds: 30.1, tool_count: 7, model_questions: 2 },
  { id: 'RUN-DP-001', scenario: 'KA-03', seed: 9, conclusion: 'Needs technician confirmation',
    assessment: 'unresolved', recommendation: 'escalate',
    verification: 'unverified', wall_seconds: 71.7, tool_count: 11, model_questions: 8 },
];
export const demoChart: Sample[] = Array.from({ length: 66 }, (_, index) => ({
  at: new Date(Date.now() - (65 - index) * 60000).toISOString(),
  value: Math.round((37 + Math.sin(index * 0.26) * 7 + Math.cos(index * 0.12) * 4 +
    (index > 43 ? (index - 43) * 0.7 : 0)) * 10) / 10,
  quality: index === 31 || index === 32 ? 'bad' : 'good', epoch: 1,
}));
