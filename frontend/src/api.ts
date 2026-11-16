import { useEffect, useState } from 'react';
import type { ApiResource } from './types';

export async function getJson<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    signal, cache: 'no-store',
    headers: token ? { Authorization: 'Bearer ' + token } : {},
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error('Local session token required. Open Access in the toolbar.');
    if (response.status === 403) throw new Error('This source is not authorized for the selected workspace.');
    throw new Error('API request failed (' + response.status + ').');
  }
  return response.json() as Promise<T>;
}

export async function postJson<T>(path: string, token: string, body: unknown, key?: string): Promise<T> {
  const response = await fetch(path, {
    method: 'POST', cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...(key ? { 'Idempotency-Key': key } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    if (response.status === 403) throw new Error('This role or workspace is not authorized.');
    if (response.status === 409) throw new Error('This request has already been decided, or another run is active.');
    if (response.status === 422) throw new Error('Invalid settings or missing idempotency key.');
    throw new Error('Request failed (' + response.status + ').');
  }
  return response.json() as Promise<T>;
}

export function useResource<T>(path: string | null, token: string, pause = false, pollMs = 15000): ApiResource<T> {
  // Keep the request identity with its result. During a token or workspace
  // transition, never render a previous authorized source even for one frame.
  const requestKey = JSON.stringify([path, token, pause, pollMs]);
  const [state, setState] = useState<ApiResource<T> & { key: string }>({
    key: requestKey, data: null, loading: Boolean(path) && !pause, error: null,
  });
  useEffect(() => {
    setState({ key: requestKey, data: null, loading: Boolean(path) && !pause, error: null });
    if (pause || !path) return;

    let active = true;
    let sequence = 0;
    let controller: AbortController | null = null;
    const reload = () => {
      // Abort superseded polls and reject any late response independently.
      controller?.abort();
      controller = new AbortController();
      const current = ++sequence;
      getJson<T>(path, token, controller.signal).then(data => {
        if (active && current === sequence)
          setState({ key: requestKey, data, error: null, loading: false });
      }).catch(error => {
        if (active && current === sequence && error.name !== 'AbortError')
          setState({ key: requestKey, data: null, error: String(error.message), loading: false });
      });
    };
    reload();
    const timer = window.setInterval(reload, pollMs);
    return () => { active = false; controller?.abort(); window.clearInterval(timer); };
  }, [path, token, pause, pollMs, requestKey]);
  if (state.key !== requestKey)
    return { data: null, loading: Boolean(path) && !pause, error: null };
  return { data: state.data, loading: state.loading, error: state.error };
}
