import { useMemo } from 'react';
import { useResource } from './api';
import { useUi } from './context';
import { demoEvaluations, demoInvestigations, demoMachines, demoRecorder } from './preview';
import { decodeListResponse } from './sourceState.mjs';
import type { SourceStateInput } from './sourceState.mjs';
import type { ApiResource, Evaluation, Investigation, Machine, RecorderSnapshot } from './types';

/** Facts a page passes to SourceState; the panel adds its own label. */
export type SourceFacts = Omit<SourceStateInput, 'item'>;

/** Decode a list response once per payload and describe its source state.
 * A malformed payload becomes an error, not an empty list. */
function useListSource<T>(resource: ApiResource<unknown>, preview: boolean, previewItems: T[]) {
  // Variables:
  //   decoded: The validated list, or the contract problem that rejected it.
  //   availability: Stays null until a response is decoded, so loading and
  //     failures are never reported as "not configured".
  const decoded = useMemo(() => {
    if (resource.data === null) return null;
    try { return { list: decodeListResponse<T>(resource.data), problem: null }; }
    catch (problem) { return { list: null, problem: problem instanceof Error ? problem.message : 'Invalid response' }; }
  }, [resource.data]);
  if (preview) return { items: previewItems, availability: 'synthetic',
    source: { availability: 'synthetic', count: previewItems.length } as SourceFacts, error: null, loading: false };
  const items = decoded?.list?.items || [];
  const error = resource.error || decoded?.problem || null;
  const availability = decoded?.list?.availability ?? null;
  return { items, availability, error, loading: resource.loading,
    source: { loading: resource.loading, error, status: resource.status ?? null,
      availability, count: items.length, detail: decoded?.list?.message ?? null } as SourceFacts };
}

export function useInvestigations() {
  const { workspace, preview, token } = useUi();
  const resource = useResource<unknown>('/api/v1/investigations?workspace=' + workspace, token, preview);
  return useListSource<Investigation>(resource, preview, demoInvestigations);
}
export function useMachines() {
  const { workspace, preview, token } = useUi();
  const resource = useResource<unknown>('/api/v1/machines?workspace=' + workspace, token, preview);
  return useListSource<Machine>(resource, preview,
    workspace === 'pilot' ? demoMachines.slice(0, 1) : demoMachines);
}
/** The Siemens capture is a physical-pilot source. Views that describe the
 * selected workspace pass pilotOnly so simulator pages never show it. */
export function useRecording(pilotOnly = false) {
  // Variables:
  //   blocked: True when the caller only shows pilot data and the simulator
  //     workspace is selected; the request is not made at all.
  const { preview, token, workspace } = useUi();
  const blocked = pilotOnly && workspace !== 'pilot';
  const resource = useResource<RecorderSnapshot>(blocked ? null : '/api/v1/recordings/siemens-local/health',
    token, preview || blocked);
  return { snapshot: preview ? demoRecorder : blocked ? null : resource.data, error: resource.error,
    status: resource.status ?? null, loading: resource.loading && !preview, blocked };
}
export function useEvaluations() {
  const { workspace, preview, tokenFor } = useUi();
  const pilot = workspace === 'pilot';
  const resource = useResource<unknown>('/api/v1/evaluations?workspace=' + workspace, tokenFor('evaluator'), preview || pilot);
  const list = useListSource<Evaluation>(resource, preview, demoEvaluations);
  if (pilot && !preview) return { ...list, items: [], availability: 'not_available_in_pilot',
    source: { availability: 'not_available_in_pilot', count: 0 } as SourceFacts };
  return list;
}
