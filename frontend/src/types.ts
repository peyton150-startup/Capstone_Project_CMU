export type Workspace = 'simulator' | 'pilot';
export type Availability = 'available' | 'not_configured' | 'file_missing' |
  'not_integrated' | 'unsupported_for_pilot' | 'unavailable' | 'error';

export type Signal = {
  id: string; label: string; value: number | boolean | string | null;
  unit: string | null; quality: string; received_at: string | null;
  last_received_age_s?: number | null; freshness: string;
  analysis_eligible: boolean; reason?: string;
  source_timestamp?: string | null;
};
export type Recorder = {
  id: string; source: string; process_state: string;
  connection_state: string; subscription_state: string;
  measurement_state: string; received: number; good: number;
  uncertain: number; bad: number; overflow: number; gaps: number;
  reconnections: number; invalid_lines: number; unsupported?: number;
  output_bytes: number; sink_state: string; analysis_eligible: number | null;
  last_receive_at: string | null; session_epoch: number | null;
  disk_free_bytes: number | null; window_scope: string;
};
export type RecorderSnapshot = {
  availability: Availability; message: string | null;
  recorder: Recorder | null; signals: Signal[];
  events: Array<{ event: string; at: string; epoch: number }>;
};
export type Investigation = {
  id: string; run_id?: string | null; summary: string; diagnosis: string;
  model_confidence: number | null; termination_reason?: string | null;
  evidence_count: number; hypothesis_count: number;
  tool_calls?: number | null; iterations?: number | null;
  verification?: string | null; symptoms?: string[];
};
export type Evidence = { id: string; source_id?: string; source_type?: string;
  content?: string; observed_at?: string | null; observed_tick?: number | null };
export type Hypothesis = { id: string; description?: string; claim?: string;
  status?: string; confidence?: number | null;
  supporting_evidence_ids?: string[]; contradicting_evidence_ids?: string[];
  discriminating_check?: string };
export type InvestigationDetail = Investigation & {
  evidence: Evidence[]; hypotheses: Hypothesis[];
  proposed_action?: { action?: string; reason?: string; machine_id?: string } | null;
  verification_detail?: { status?: string; outcome?: string; summary?: string } | null;
  decision_trace?: Array<{ sequence:number; phase:string; tool:string|null; outcome:string;
    evidence_ids:string[]; question_id:string|null; hypothesis_id:string|null;
    tick:number|null; termination_reason:string|null }>;
  reasoning_metrics?: {repeated_calls:number|null; failed_tool_calls:number|null;
    malformed_results:number|null; interpretation_failures:number|null};
  pruned_candidates?: Array<{id:string; status:string;confidence:number|null}>;
};
export type Evaluation = { id: string; scenario: string; seed: number;
  conclusion: string | null; assessment: string | null;
  recommendation: string | null; verification: string | null;
  wall_seconds: number | null; tool_count: number | null;
  model_questions: number | null; model_failures?: number | null;
  mode?: string; triage_seconds?: number | null; triage_deep_ran?: boolean | null;
  triage_assessment?: string | null; triage_outcome?: string | null };
export type Machine = { id: string; name: string; operating_state?: string;
  condition?: string; signal_count?: number;
  last_observed_at?: string | null };
export type Capabilities = {
  schema_version: number; workspaces: Workspace[];
  sources: Record<string, boolean>;
  features: Record<string, boolean>;
  limits: string[];
};
export type ListResponse<T> = { availability: Availability; items: T[]; message?: string };
export type ApiResource<T> = { data: T | null; loading: boolean; error: string | null };
export type Sample = { at: string; value: number | null; quality: string; epoch: number };

/** Source-safe, per-phase values projected from the Python investigation watcher. */
export type StageProgress = {
  investigation_id: string; mode: 'triage' | 'deep'; stage: string | null;
  iteration_count: number; tool_calls: number; evidence_count: number;
  hypothesis_count: number; unresolved_question_ids: string[];
  termination_reason: string | null; conclusion_available: boolean;
};
export type RunPhaseProgress = {
  latest?: 'triage' | 'deep'; triage?: StageProgress; deep?: StageProgress;
};

export type ManagedRun = {
  run_id: string; requested: { seed: number; kind: string; mode: string; hazards: boolean;
    tree_of_thought: boolean; manual: string };
  state: 'queued' | 'running' | 'awaiting_review' | 'completed' | 'failed' | 'interrupted';
  snapshot: { stage?: string | null; status?: string; mode?: string;
    progress?: RunPhaseProgress;
    triage_report?: TriageReport | null; investigation?: { stage: string | null;
      tool_calls: number; evidence_count: number; hypothesis_count: number;
      termination_reason: string | null; unresolved_question_ids: string[] };
    diagnosis?: string | null; recommendation?: string | null;
    action_executed?: boolean; verification_outcome?: string | null;
    deep_ran?: boolean; error_class?: string };
  created_at: string; updated_at: string;
};
export type TriageReport = {
  machine_id: string | null; alarm: string; outcome: string;
  termination_reason: string | null; diagnosis: string | null;
  assessment: string; recommendation: string; model_recommendation: string | null;
  confidence: number; deep_recommended: boolean; held_open_because: string[];
  unresolved_questions: string[]; next_check: string | null;
  findings: Array<{evidence_id:string;source_id:string;origin:string|null;
    observed_tick:number|null;excerpt:string}>;
  refused_because: string | null; summary: string;
};
export type ReviewRequest = {
  run_id: string; proposal_id: number; machine_id: string; action: string;
  reason: string; predicted_effect: string; note: string;
};
export type RunEvent = { seq: number; event: string; data: Record<string, unknown> };

export type Scorecard = {
  id: string; fault_correct: boolean | null; target_correct: boolean | null;
  action_correct: boolean | null; recommendation_correct: boolean | null;
  resolved: boolean | null; tool_calls: number | null; ticks_elapsed: number | null;
  iterations: number | null; causes_found: number | null; wrong_causes: number | null;
  causes_resolved: number | null; relevant_evidence_count: number | null;
  evidence_collected_count: number | null; judged: boolean;
};
