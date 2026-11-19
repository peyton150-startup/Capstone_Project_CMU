import { useResource } from './api';
import { useUi } from './context';
import { demoEvaluations, demoInvestigations, demoMachines, demoRecorder } from './preview';
import type { Evaluation, Investigation, ListResponse, Machine, RecorderSnapshot } from './types';

export function useInvestigations() {
  const { workspace, preview, token } = useUi();
  const resource = useResource<ListResponse<Investigation>>(
    '/api/v1/investigations?workspace=' + workspace, token, preview);
  return { items: preview ? demoInvestigations : resource.data?.items || [],
    availability: preview ? 'synthetic' : resource.data?.availability || 'not_configured',
    error: resource.error, loading: resource.loading && !preview };
}
export function useMachines() {
  const { workspace, preview, token } = useUi();
  const resource = useResource<ListResponse<Machine>>(
    '/api/v1/machines?workspace=' + workspace, token, preview);
  return { items: preview ? (workspace === 'pilot' ? demoMachines.slice(0, 1) : demoMachines) : resource.data?.items || [],
    availability: preview ? 'synthetic' : resource.data?.availability || 'not_configured',
    error: resource.error };
}
export function useRecording() {
  const { preview, token } = useUi();
  const resource = useResource<RecorderSnapshot>('/api/v1/recordings/siemens-local/health', token, preview);
  return { snapshot: preview ? demoRecorder : resource.data, error: resource.error, loading: resource.loading && !preview };
}
export function useEvaluations() {
  const { workspace, preview, tokenFor } = useUi();
  const resource = useResource<ListResponse<Evaluation>>(
    '/api/v1/evaluations?workspace=' + workspace, tokenFor('evaluator'), preview || workspace === 'pilot');
  return { items: preview ? demoEvaluations : workspace === 'pilot' ? [] : resource.data?.items || [],
    availability: preview ? 'synthetic' : workspace === 'pilot' ? 'not_available_in_pilot' :
      resource.data?.availability || 'not_configured',
    error: resource.error, loading: resource.loading && !preview };
}
