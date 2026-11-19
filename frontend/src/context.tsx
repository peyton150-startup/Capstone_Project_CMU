import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { Workspace } from './types';
import { defaultApiBackend } from './backend.mjs';
import type { ApiBackend } from './backend.mjs';
import { emptyTokens, readToken, tokenFor as pickToken } from './access.mjs';
import type { Role, RoleTokens } from './access.mjs';

type UiContextValue = {
  workspace: Workspace;
  setWorkspace: (value: Workspace) => void;
  preview: boolean;
  setPreview: (value: boolean) => void;
  theme: 'dark' | 'light';
  setTheme: (value: 'dark' | 'light') => void;
  backend: ApiBackend;
  setBackend: (value: ApiBackend) => void;
  // Read token: any configured role can read, so pages use this one.
  token: string;
  // Each role's token for the selected backend, and the token one action needs.
  roleTokens: RoleTokens;
  setRoleTokens: (value: RoleTokens) => void;
  tokenFor: (role: Role) => string;
  // Opt-in: keep this backend's tokens in sessionStorage until the tab closes.
  remember: boolean;
  setRemember: (value: boolean) => void;
};
const Context = createContext<UiContextValue | null>(null);
const storageKey = (backend: ApiBackend) => 'capstone-access-' + backend;

function loadTokens(backend: ApiBackend): RoleTokens | null {
  try {
    const saved = window.sessionStorage.getItem(storageKey(backend));
    if (!saved) return null;
    const value = JSON.parse(saved) as Partial<RoleTokens>;
    const tokens = emptyTokens();
    for (const role of Object.keys(tokens) as Role[])
      if (typeof value[role] === 'string') tokens[role] = value[role] as string;
    return tokens;
  } catch { return null; }
}

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
  // Credentials never cross API environments. They stay in memory unless the
  // user ticks "remember in this tab", which uses sessionStorage only.
  const [tokens, setTokens] = useState<Record<ApiBackend, RoleTokens>>(() => ({
    local: loadTokens('local') || emptyTokens(),
    render: loadTokens('render') || emptyTokens(),
  }));
  const [remembered, setRemembered] = useState<Record<ApiBackend, boolean>>(() => ({
    local: loadTokens('local') !== null,
    render: loadTokens('render') !== null,
  }));
  const roleTokens = tokens[backend];
  const token = readToken(roleTokens);
  const remember = remembered[backend];
  const setRoleTokens = useCallback((value: RoleTokens) =>
    setTokens(previous => ({ ...previous, [backend]: value })), [backend]);
  const setRemember = useCallback((value: boolean) =>
    setRemembered(previous => ({ ...previous, [backend]: value })), [backend]);
  const tokenFor = useCallback((role: Role) => pickToken(roleTokens, role), [roleTokens]);
  useEffect(() => {
    try {
      for (const name of ['local', 'render'] as ApiBackend[]) {
        if (remembered[name]) window.sessionStorage.setItem(storageKey(name), JSON.stringify(tokens[name]));
        else window.sessionStorage.removeItem(storageKey(name));
      }
    } catch { /* optional storage */ }
  }, [tokens, remembered]);
  useEffect(() => {
    try { window.sessionStorage.setItem('capstone-api-backend', backend); } catch { /* optional storage */ }
  }, [backend]);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const value = useMemo(
    () => ({
      workspace, setWorkspace, preview, setPreview, theme, setTheme, backend, setBackend,
      token, roleTokens, setRoleTokens, tokenFor, remember, setRemember,
    }),
    [workspace, preview, theme, backend, token, roleTokens, setRoleTokens, tokenFor, remember, setRemember],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useUi(): UiContextValue {
  const value = useContext(Context);
  if (!value) throw new Error('UI context unavailable');
  return value;
}
