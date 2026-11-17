import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { Workspace } from './types';
import { defaultApiBackend } from './backend.mjs';
import type { ApiBackend } from './backend.mjs';

type UiContextValue = {
  workspace: Workspace;
  setWorkspace: (value: Workspace) => void;
  preview: boolean;
  setPreview: (value: boolean) => void;
  theme: 'dark' | 'light';
  setTheme: (value: 'dark' | 'light') => void;
  backend: ApiBackend;
  setBackend: (value: ApiBackend) => void;
  token: string;
  setToken: (value: string) => void;
};
const Context = createContext<UiContextValue | null>(null);

export function UiProvider({ children }: { children: ReactNode }) {
  const [workspace, setWorkspace] = useState<Workspace>('simulator');
  const [preview, setPreview] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [backend, setBackend] = useState<ApiBackend>(() => {
    const fallback = defaultApiBackend(window.location.hostname);
    try {
      const saved = window.sessionStorage.getItem('capstone-api-backend');
      return saved === 'local' || saved === 'render' ? saved : fallback;
    } catch { return fallback; }
  });
  // Credentials never cross API environments and are never persisted.
  const [tokens, setTokens] = useState<Record<ApiBackend, string>>({ local: '', render: '' });
  const token = tokens[backend];
  const setToken = useCallback((value: string) =>
    setTokens(previous => ({ ...previous, [backend]: value })), [backend]);
  useEffect(() => {
    try { window.sessionStorage.setItem('capstone-api-backend', backend); } catch { /* optional storage */ }
  }, [backend]);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const value = useMemo(
    () => ({ workspace, setWorkspace, preview, setPreview, theme, setTheme, backend, setBackend, token, setToken }),
    [workspace, preview, theme, backend, token, setToken],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useUi(): UiContextValue {
  const value = useContext(Context);
  if (!value) throw new Error('UI context unavailable');
  return value;
}
