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

export function useResource<T>(path: string | null, token: string, pause = false): ApiResource<T> {
  const [state, setState] = useState<ApiResource<T>>({ data: null, loading: true, error: null });
  useEffect(() => {
    if (pause || !path) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    let active = true;
    const reload = () => {
      getJson<T>(path, token, controller.signal).then(data => {
        if (active) setState({ data, error: null, loading: false });
      }).catch(error => {
        if (active && error.name !== 'AbortError')
          setState({ data: null, error: String(error.message), loading: false });
      });
    };
    reload();
    const timer = window.setInterval(reload, 15000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [path, token, pause]);
  return state;
}
