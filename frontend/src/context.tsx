import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { Workspace } from './types';

type UiContextValue = {
  workspace: Workspace;
  setWorkspace: (value: Workspace) => void;
  preview: boolean;
  setPreview: (value: boolean) => void;
  theme: 'dark' | 'light';
  setTheme: (value: 'dark' | 'light') => void;
  token: string;
  setToken: (value: string) => void;
};
const Context = createContext<UiContextValue | null>(null);

export function UiProvider({ children }: { children: ReactNode }) {
  const [workspace, setWorkspace] = useState<Workspace>('simulator');
  const [preview, setPreview] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [token, setToken] = useState('');
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const value = useMemo(
    () => ({ workspace, setWorkspace, preview, setPreview, theme, setTheme, token, setToken }),
    [workspace, preview, theme, token],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useUi(): UiContextValue {
  const value = useContext(Context);
  if (!value) throw new Error('UI context unavailable');
  return value;
}
