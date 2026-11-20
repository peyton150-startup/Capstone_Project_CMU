export const MAX_FRAME_CHARS: number;
export const TERMINAL_EVENTS: readonly string[];
export const BASE_RETRY_MS: number;
export const MIN_RETRY_MS: number;
export const MAX_RETRY_MS: number;

export type JournalStopKind = 'oversize' | 'incompatible';
export class JournalStop extends Error {
  constructor(kind: JournalStopKind, message: string);
  kind: JournalStopKind;
}

export type ParsedFrame = {
  id: string | null; event: string; data: string | null; retry: number | null; comment: boolean;
};
export type JournalEvent = { seq: number; event: string; data: Record<string, unknown> };
export type SkipReason = 'invalid_id' | 'malformed_json' | 'not_object' | 'private_event';
export type FrameVerdict =
  | { action: 'close'; reason: string; cursor: number }
  | { action: 'ignore'; cursor: number }
  | { action: 'duplicate'; seq: number; cursor: number }
  | { action: 'skip'; reason: SkipReason; seq?: number; cursor: number }
  | { action: 'event'; seq: number; cursor: number; terminal: boolean; event: JournalEvent };

export type FailureKind = 'http' | 'oversize' | 'incompatible' | 'network' | 'ended';

export type JournalDiagnostics = {
  state: 'idle' | 'connecting' | 'connected' | 'waiting' | 'finished' | 'stopped';
  connects: number; attempt: number; httpStatus: number | null; lastConnectedAt: string | null;
  lastError: string | null; lastErrorKind: FailureKind | null; lastErrorAt: string | null;
  frames: number; keepalives: number; accepted: number; duplicates: number;
  skipped: Record<SkipReason, number>;
  lastSeq: number; lastEventAt: string | null; chars: number; nextRetryMs: number | null;
  closeReason: string | null;
};

export type JournalLog = (level: 'debug' | 'info' | 'warn', message: string, fields?: Record<string, unknown>) => void;

export function takeFrames(buffer: string, maxFrameChars?: number): { frames: string[]; rest: string };
export function parseFrame(text: string): ParsedFrame;
export function acceptFrame(frame: ParsedFrame, cursor: number): FrameVerdict;
export function retryPlan(input: { kind: FailureKind; status?: number | null; attempt?: number; baseDelayMs?: number }):
  { retry: boolean; delayMs: number | null };
export function problemMessage(kind: FailureKind, status: number | null): string;
export function newDiagnostics(): JournalDiagnostics;
export function skippedCount(diagnostics: JournalDiagnostics): number;
export function describeJournal(diagnostics: JournalDiagnostics): string;
export function journalLogger(runId: string, sink?: Pick<Console, 'debug' | 'info' | 'warn'>): JournalLog;
export function abortableSleep(ms: number, signal: AbortSignal): Promise<boolean>;
export function runJournal(options: {
  fetchImpl: (url: string, init: RequestInit) => Promise<Response>;
  urlFor: (cursor: number) => string;
  headers?: Record<string, string>;
  signal: AbortSignal;
  sleep?: (ms: number, signal: AbortSignal) => Promise<boolean>;
  onEvent: (event: JournalEvent) => void;
  onDiagnostics?: (diagnostics: JournalDiagnostics) => void;
  log?: JournalLog;
  now?: () => string;
  maxFrameChars?: number;
}): Promise<JournalDiagnostics>;
