export const KNOWN_AVAILABILITY: readonly string[];
export class ApiProblem extends Error {
  constructor(status: number | null, message: string);
  status: number | null;
}
export function problemForStatus(status: number): string;
export function decodeListResponse<T = Record<string, unknown>>(payload: unknown): {
  availability: string; items: T[]; message?: string;
};
export type SourceStateInput = {
  item: string; loading?: boolean; error?: string | null; status?: number | null;
  availability?: string | null; count?: number; emptyDetail?: string | null; detail?: string | null;
};
export type SourceStateView = {
  kind: string; tone: 'empty' | 'warning' | 'error'; title: string; detail: string;
};
export function describeSourceState(input: SourceStateInput): SourceStateView;
export function timeAxis(samples: Array<{ at: string }>): { mode: 'time' | 'order'; positions: number[] };
export function selectTriageReport<R extends { run_id: string; updated_at?: string | null;
  snapshot: { triage_report?: unknown } }>(runs: R[] | null | undefined, selectedRunId: string | null):
  { runs: R[]; run: R | null; report: R['snapshot']['triage_report'] | null };
export function reportHasAcceptedConclusion(report: { outcome: string } | null | undefined): boolean;
