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
};
export type Evaluation = { id: string; scenario: string; seed: number;
  conclusion: string | null; assessment: string | null;
  recommendation: string | null; verification: string | null;
  wall_seconds: number | null; tool_count: number | null;
  model_questions: number | null };
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
