import { useEffect, useState } from 'react';
import type { ApiResource } from './types';
import { resolveApiUrl } from './backend.mjs';
import type { ApiBackend } from './backend.mjs';
import { useUi } from './context';
import { ApiProblem, problemForStatus } from './sourceState.mjs';
import { ROLE_DENIED_MESSAGES } from './access.mjs';

// A 403 that names a missing role token; null for any other detail, which is
// never shown because it could carry server data.
async function roleDenied(response: Response): Promise<string | null> {
  // Variables:
  //   detail: The server's 403 reason; shown only if it is one of the fixed
  //     ROLE_DENIED_MESSAGES.
  const payload: unknown = await response.json().catch(() => null);
  const detail = payload && typeof payload === 'object' && 'detail' in payload ?
    (payload as {detail?: unknown}).detail : null;
  return typeof detail === 'string' && ROLE_DENIED_MESSAGES.includes(detail) ?
    detail + '. Add it in Access (top right).' : null;
}

export async function getJson<T>(path: string, token: string, backend: ApiBackend, signal?: AbortSignal): Promise<T> {
  // Variables:
  //   response: The raw HTTP response; its status becomes an ApiProblem with a
  //     fixed message, so server, database or provider detail is never shown.
  const response = await fetch(resolveApiUrl(path, backend, window.location.hostname), {
    signal, cache: 'no-store',
    headers: token ? { Authorization: 'Bearer ' + token } : {},
  });
  if (!response.ok) {
    // A 403 that names the missing role token is a fixed server message and
    // safe to show; every other detail keeps the sanitized status message.
    if (response.status === 403) {
      const named = await roleDenied(response);
      if (named) throw new ApiProblem(403, named);
    }
    throw new ApiProblem(response.status, problemForStatus(response.status));
  }
  if (!response.headers.get('content-type')?.includes('application/json'))
    throw new ApiProblem(null, 'API returned non-JSON content. Check the selected backend and proxy.');
  try {
    return await response.json() as T;
  } catch (problem) {
    if (problem instanceof Error && problem.name === 'AbortError') throw problem;
    throw new ApiProblem(null, 'The API returned malformed JSON.');
  }
}

export async function postJson<T>(path: string, token: string, body: unknown, backend: ApiBackend, key?: string): Promise<T> {
  const response = await fetch(resolveApiUrl(path, backend, window.location.hostname), {
    method: 'POST', cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...(key ? { 'Idempotency-Key': key } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error('Session token required for the selected API. Open Access in the toolbar.');
    if (response.status === 403)
      throw new Error(await roleDenied(response) || 'This role or workspace is not authorized.');
    if (response.status === 409) {
      // Only fixed, reviewed server conflict messages are displayed. Never
      // forward arbitrary exception detail, which may contain provider data.
      const payload: unknown = await response.json().catch(() => null);
      const detail = payload && typeof payload === 'object' && 'detail' in payload ?
        (payload as {detail?: unknown}).detail : null;
      const safeDetails = [
        'Settings changed after preview; review before starting',
        'Settings changed after preview; validate again',
        'Idempotency key belongs to another request',
        'A simulator run is already active',
      ];
      throw new Error(
        typeof detail === 'string' && safeDetails.includes(detail) ?
          detail : 'This request has already been decided, or another run is active.',
      );
    }
    if (response.status === 422) throw new Error('Invalid settings or missing idempotency key.');
    throw new Error('Request failed (' + response.status + ').');
  }
  return response.json() as Promise<T>;
}

export function useResource<T>(path: string | null, token: string, pause = false, pollMs = 15000): ApiResource<T> {
  // Keep the request identity with its result. During a token or workspace
  // transition, never render a previous authorized source even for one frame.
  // Variables:
  //   requestKey: Everything that decides which source and credential a result
  //     belongs to; a result stored under another key is never returned.
  //   sequence: Counter for poll attempts, so a superseded response or error
  //     cannot overwrite a newer one.
  //   status: HTTP status of the last failure, kept so pages can tell an
  //     access problem from an outage; a failed poll clears data rather than
  //     leaving it to read as an empty history.
  const { backend } = useUi();
  const requestKey = JSON.stringify([path, token, pause, pollMs, backend]);
  const [state, setState] = useState<ApiResource<T> & { key: string }>({
    key: requestKey, data: null, loading: Boolean(path) && !pause, error: null, status: null,
  });
  useEffect(() => {
    setState({ key: requestKey, data: null, loading: Boolean(path) && !pause, error: null, status: null });
    if (pause || !path) return;

    let active = true;
    let sequence = 0;
    let controller: AbortController | null = null;
    const reload = () => {
      // Abort superseded polls and reject any late response independently.
      controller?.abort();
      controller = new AbortController();
      const current = ++sequence;
      getJson<T>(path, token, backend, controller.signal).then(data => {
        if (active && current === sequence)
          setState({ key: requestKey, data, error: null, loading: false, status: null });
      }).catch(error => {
        if (active && current === sequence && error.name !== 'AbortError')
          setState({ key: requestKey, data: null, error: String(error.message), loading: false,
            status: error instanceof ApiProblem ? error.status : null });
      });
    };
    reload();
    const timer = window.setInterval(reload, pollMs);
    return () => { active = false; controller?.abort(); window.clearInterval(timer); };
  }, [path, token, pause, pollMs, backend, requestKey]);
  if (state.key !== requestKey)
    return { data: null, loading: Boolean(path) && !pause, error: null, status: null };
  return { data: state.data, loading: state.loading, error: state.error, status: state.status };
}
