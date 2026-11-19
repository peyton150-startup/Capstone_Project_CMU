import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity, Archive, ArrowRight, Bell, BookOpen, Boxes, BrainCircuit, ChartNoAxesCombined,
  ChevronDown, ChevronLeft, ChevronRight, ClipboardCheck, ClipboardList, Database,
  FlaskConical, Gauge, GitCompareArrows, History, House, Layers, LockKeyhole,
  Menu, Moon, RadioTower, Search, Server, Settings2, ShieldCheck, Signal,
  SlidersHorizontal, Sun, TerminalSquare, Waypoints, X,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { Check, Copy, KeyRound } from 'lucide-react';
import { useUi } from './context';
import { getJson, useResource } from './api';
import { checkProblem, countTokens, describeCheck, emptyTokens, envBlock, generateTokens, ROLES, RUNS_VARIABLE } from './access.mjs';
import type { Role, RoleTokens } from './access.mjs';
import { isLoopbackFrontend } from './backend.mjs';
import { Pill } from './ui';
import type { Capabilities } from './types';
import {
  HomePage, OverviewPage, InvestigationListPage, InvestigationDetailPage,
  TriagePage, DeepPage, ReviewPage, MachinesPage, SignalsPage,
  RecordingsPage, QualityPage, SessionsPage,
  LabPage, RunsPage, RunDetailPage, EvaluationPage, ComparePage,
  KnowledgePage, ManualsPage, MemoryPage,
  SystemPage, ObservabilityPage, AuditPage, SettingsPage,
} from './pages';

type IconComponent = ComponentType<{ size?: number; strokeWidth?: number }>;
type NavItem = { to: string; title: string; icon: IconComponent; group: string; sub?: boolean };
const nav: NavItem[] = [
  { to: '/', title: 'Home', icon: House, group: 'Workspace' },
  { to: '/overview', title: 'Overview', icon: Gauge, group: 'Workspace' },
  { to: '/investigations', title: 'Investigations', icon: BrainCircuit, group: 'Workspace' },
  { to: '/investigations/triage', title: 'Rapid triage', icon: Activity, group: 'Workspace', sub: true },
  { to: '/investigations/deep', title: 'Deep investigations', icon: Layers, group: 'Workspace', sub: true },
  { to: '/investigations/review', title: 'Review & verification', icon: ClipboardCheck, group: 'Workspace', sub: true },
  { to: '/machines', title: 'Machines', icon: Boxes, group: 'Equipment' },
  { to: '/signals', title: 'Signal explorer', icon: ChartNoAxesCombined, group: 'Equipment' },
  { to: '/recordings', title: 'Recordings', icon: RadioTower, group: 'Equipment' },
  { to: '/recordings/quality', title: 'Data quality', icon: Signal, group: 'Equipment', sub: true },
  { to: '/recordings/sessions', title: 'Session history', icon: Archive, group: 'Equipment', sub: true },
  { to: '/lab', title: 'Experiment lab', icon: FlaskConical, group: 'Research' },
  { to: '/lab/runs', title: 'Run history', icon: History, group: 'Research', sub: true },
  { to: '/lab/evaluations', title: 'Evaluation', icon: ClipboardList, group: 'Research', sub: true },
  { to: '/lab/compare', title: 'Compare runs', icon: GitCompareArrows, group: 'Research', sub: true },
  { to: '/knowledge', title: 'Knowledge', icon: BookOpen, group: 'Research' },
  { to: '/knowledge/manuals', title: 'Manual library', icon: Database, group: 'Research', sub: true },
  { to: '/knowledge/memory', title: 'Episodic memory', icon: History, group: 'Research', sub: true },
  { to: '/system', title: 'System health', icon: ShieldCheck, group: 'Engineering' },
  { to: '/system/observability', title: 'Observability', icon: Activity, group: 'Engineering', sub: true },
  { to: '/system/audit', title: 'Audit timeline', icon: TerminalSquare, group: 'Engineering', sub: true },
  { to: '/system/settings', title: 'Settings', icon: SlidersHorizontal, group: 'Engineering', sub: true },
];

function Sidebar({ expanded, setExpanded, mobileOpen, closeMobile }: {
  expanded: boolean; setExpanded: (value: boolean) => void; mobileOpen: boolean;
  closeMobile: () => void;
}) {
  const { workspace, setWorkspace, preview } = useUi();
  const groups = ['Workspace', 'Equipment', 'Research', 'Engineering'];
  // Variables:
  //   showLabels: Mobile navigation always exposes labels even when desktop navigation is collapsed.
  const showLabels = expanded || mobileOpen;
  return <>
    {mobileOpen && <button className="mobile-backdrop" aria-label="Close navigation" onClick={closeMobile} />}
    <aside className={'sidebar ' + (!showLabels ? 'sidebar-compact ' : '') + (mobileOpen ? 'sidebar-open' : '')}>
      <Link to="/" className="brand" onClick={closeMobile}>
        <div className="brand-symbol"><Waypoints size={25} strokeWidth={1.8} /></div>
        {showLabels && <div className="brand-words"><strong>FORGE<span className="brand-dot">.</span></strong>
          <small>Manufacturing Research AI</small></div>}
      </Link>
      {showLabels && <div className="workspace-switch">
        <label htmlFor="workspace">ACTIVE ENVIRONMENT</label>
        <div className="workspace-select-wrap">
          <span className="workspace-marker" />
          <select id="workspace" value={workspace}
            onChange={event => setWorkspace(event.target.value as 'simulator' | 'pilot')}>
            <option value="simulator">Simulator Lab</option>
            <option value="pilot">Prestige Pilot</option>
          </select><ChevronDown size={14} />
        </div>
        <span className="workspace-hint">{preview ? 'Synthetic interface preview' : 'Approved sources only'}</span>
      </div>}
      <nav className="primary-nav" aria-label="Main navigation">
        {groups.map(group => <div className="nav-group" key={group}>
          {showLabels && <div className="nav-group-label">{group}</div>}
          {nav.filter(item => item.group === group).map(item => {
            const Icon = item.icon;
            return <NavLink key={item.to} to={item.to} onClick={closeMobile}
              title={!showLabels ? item.title : undefined} end={item.to === '/'}
              className={({ isActive }) => 'nav-item ' + (item.sub ? 'nav-sub ' : '') + (isActive ? 'active' : '')}>
              <Icon size={item.sub ? 17 : 19} strokeWidth={1.9} />
              {showLabels && <span>{item.title}</span>}
            </NavLink>;
          })}
        </div>)}
      </nav>
      <div className="sidebar-bottom">
        {showLabels && <div className="sidebar-safety"><LockKeyhole size={16} /><div><strong>Read-only pilot</strong>
          <small>No machine control or direct CNC access</small></div></div>}
        <button className="collapse-button" onClick={() => setExpanded(!expanded)}>
          {expanded ? <ChevronLeft size={17} /> : <ChevronRight size={17} />}
          {showLabels && <span>Collapse sidebar</span>}
        </button>
      </div>
    </aside>
  </>;
}

type WhoAmI = { open: boolean; roles: Role[]; runs_enabled: boolean };

function AccessDialog({ close }: { close: () => void }) {
  // Variables:
  //   values: The four boxes being edited; saved to context only on Save.
  //   checks: What the backend said each saved token is (null = not checked).
  //   server: Whether the backend needs a token at all and has runs switched on.
  //   generated: Keys made in this browser for the user to install server-side.
  const { roleTokens, setRoleTokens, backend, remember, setRemember } = useUi();
  const [values, setValues] = useState<RoleTokens>(roleTokens);
  const [checks, setChecks] = useState<Record<Role, Role[] | null>>(
    { viewer: null, operator: null, reviewer: null, evaluator: null });
  const [server, setServer] = useState<Omit<WhoAmI, 'roles'> | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [generated, setGenerated] = useState<RoleTokens | null>(null);
  const [copied, setCopied] = useState(false);
  const label = backend === 'local' ? 'Local' : 'Render';
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Variables:
    //   previousFocus: The control to restore when the modal closes.
    //   focusable: Controls currently available inside the modal for Tab wrapping.
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.querySelector<HTMLInputElement>('input')?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { close(); return; }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href]'
      )).filter(element => element.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('keydown', onKey); previousFocus?.focus(); };
  }, [close]);

  async function save() {
    const next = Object.fromEntries(ROLES.map(item => [item.role, values[item.role].trim()])) as RoleTokens;
    setRoleTokens(next);
    setValues(next);
    setChecking(true);
    setProblem(null);
    try {
      const results = await Promise.all(ROLES.map(item => next[item.role] ?
        getJson<WhoAmI>('/api/v1/access/whoami', next[item.role], backend) : Promise.resolve(null)));
      const base = results.find(Boolean) || await getJson<WhoAmI>('/api/v1/access/whoami', '', backend);
      setServer({ open: base.open, runs_enabled: base.runs_enabled });
      setChecks(Object.fromEntries(ROLES.map((item, index) =>
        [item.role, results[index] ? results[index]!.roles : null])) as Record<Role, Role[] | null>);
    } catch (error) {
      setProblem(checkProblem(error instanceof Error ? error.message : 'Check failed.'));
    } finally {
      setChecking(false);
    }
  }

  async function copyGenerated() {
    if (!generated) return;
    try { await navigator.clipboard.writeText(envBlock(generated)); setCopied(true); }
    catch { setCopied(false); }
  }

  return <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}>
    <div ref={dialogRef} className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby="access-title">
      <div className="dialog-top"><span className="tile-icon"><LockKeyhole size={21}/></span>
        <button className="icon-button" aria-label="Close" onClick={close}><X size={20}/></button></div>
      <h2 id="access-title">{label} API access</h2>
      <p>Each role has its own token. Reads use any of them; starting a run sends the operator
        token and approvals send the reviewer token. Tokens are kept separately for Local and Render.</p>
      {ROLES.map(item => {
        const status = values[item.role] && checks[item.role] !== null ?
          describeCheck(item.role, checks[item.role]) : null;
        return <div key={item.role} className="access-row">
          <label className="field-label" htmlFor={'token-' + item.role}>
            <span className="access-role">{item.role}</span> {item.purpose}
            <code>{item.variable}</code></label>
          <input id={'token-' + item.role} type="password" autoComplete="off" value={values[item.role]}
            onChange={e => { setValues({ ...values, [item.role]: e.target.value }); setChecks({ ...checks, [item.role]: null }); }} />
          {status && <small className={status.ok ? 'accent-good' : 'accent-warning'} role="status">
            {status.ok ? '✓ ' : '✗ '}{status.text}</small>}
        </div>;
      })}
      {server && <p role="status">{label} backend: {server.open ? 'reads need no token' : 'reads need a token'} ·
        runs {server.runs_enabled ? 'switched on' : <>off (set <code>{RUNS_VARIABLE}=1</code> on the API service)</>}</p>}
      {problem && <p className="accent-warning" role="alert">{problem}</p>}
      <label className="access-remember"><input type="checkbox" checked={remember}
        aria-label="Remember in this tab until it closes"
        onChange={e => setRemember(e.target.checked)}/> Remember in this tab until it closes</label>
      <div className="dialog-actions">
        <button className="button-secondary" onClick={() => {
          setValues(emptyTokens()); setRoleTokens(emptyTokens()); setRemember(false); close(); }}>Clear all</button>
        <button className="button-primary" disabled={checking} onClick={() => void save()}>
          {checking ? 'Checking…' : 'Save and check'}</button></div>

      <div className="divider-soft"/>
      <h3 className="access-heading"><KeyRound size={16}/> Generate keys</h3>
      <p>Makes four new random tokens in this browser; nothing is sent anywhere. They work only after
        you add them to the API service's environment ({backend === 'render' ? 'Render → Environment' : 'your local .env'})
        and it restarts. The old tokens stop working once replaced.</p>
      {!generated ? <button className="button-secondary" onClick={() => { setGenerated(generateTokens()); setCopied(false); }}>
        Generate keys</button> : <>
        <textarea className="access-env" readOnly rows={6} value={envBlock(generated)} aria-label="Generated environment variables"
          onFocus={event => event.currentTarget.select()}/>
        <div className="dialog-actions">
          <button className="button-secondary" onClick={() => { setGenerated(generateTokens()); setCopied(false); }}>Regenerate</button>
          <button className="button-secondary" onClick={() => void copyGenerated()}>
            {copied ? <><Check size={15}/> Copied</> : <><Copy size={15}/> Copy for {backend === 'render' ? 'Render' : '.env'}</>}</button>
          <button className="button-primary" onClick={() => { setValues(generated); setChecks(
            { viewer: null, operator: null, reviewer: null, evaluator: null }); }}>Fill boxes above</button>
        </div>
        <p>After the service restarts with these values, press <strong>Save and check</strong>: each box should show ✓.</p>
      </>}
    </div>
  </div>;
}

function Topbar({ openMenu }: { openMenu: () => void }) {
  const { workspace, preview, setPreview, theme, setTheme, roleTokens, backend, setBackend } = useUi();
  const held = countTokens(roleTokens);
  const location = useLocation(), navigate = useNavigate();
  const [showAccess, setShowAccess] = useState(false);
  const [search, setSearch] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const matches = useMemo(
    () => search.trim().length < 2 ? [] : nav.filter(item =>
      item.title.toLowerCase().includes(search.trim().toLowerCase())).slice(0, 8),
    [search],
  );
  const page = nav.find(item => item.to === location.pathname);
  return <>
    <header className="topbar">
      <button className="icon-button mobile-only" onClick={openMenu} aria-label="Open navigation"><Menu size={21}/></button>
      <div className="breadcrumb"><span>Workspace</span><ChevronRight size={14}/><strong>{page?.title || 'Investigation detail'}</strong></div>
      <div className="topbar-right">
        <div className="search-wrap">
          <Search size={17} />
          <input value={search} onChange={e => { setSearch(e.target.value); setSearchOpen(true); }}
            onFocus={() => setSearchOpen(true)} onKeyDown={event => {
              if (event.key === 'Enter' && matches[0]) {
                navigate(matches[0].to); setSearch(''); setSearchOpen(false);
              } if (event.key === 'Escape') setSearchOpen(false);
            }} placeholder="Find a page..." aria-label="Search pages" />
          {searchOpen && matches.length > 0 && <div className="search-results">
            {matches.map(item => <button key={item.to} onClick={() => {
              navigate(item.to); setSearch(''); setSearchOpen(false);
            }}>{item.title}<ArrowRight size={15}/></button>)}
          </div>}
        </div>
        <button className={'backend-switch ' + (backend === 'render' ? 'backend-render' : '')}
          onClick={() => setBackend(backend === 'local' ? 'render' : 'local')}
          aria-label={'API backend: ' + backend + '. Switch to ' + (backend === 'local' ? 'Render' : 'Local')}
          aria-pressed={backend === 'render'}
          title={backend === 'local' ? 'Local FastAPI at 127.0.0.1:8000' : 'Render FastAPI'}>
          <Server size={16}/><span>{backend === 'local' ? 'Local' : 'Render'}</span>
        </button>
        <button className={'preview-toggle ' + (preview ? 'preview-active' : '')}
          onClick={() => setPreview(!preview)} title="Switch between real sources and labeled synthetic interface preview">
          <span className="preview-dot"/>{preview ? 'Exit preview' : 'Preview UI'}
        </button>
        <button className="icon-button" title="Toggle theme" aria-label="Toggle dark and light theme"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
          {theme === 'dark' ? <Sun size={19}/> : <Moon size={19}/>}
        </button>
        <button className="access-button" onClick={() => setShowAccess(true)}><LockKeyhole size={16}/>
          <span>{held ? 'Access · ' + held + (held === 1 ? ' role' : ' roles') : 'Access'}</span></button>
        <span className="header-environment">{workspace === 'pilot' ? 'PILOT' : 'SIM'}</span>
      </div>
    </header>
    {showAccess && <AccessDialog close={() => setShowAccess(false)} />}
  </>;
}

function Banner() {
  const { preview, workspace, backend } = useUi();
  if (preview) return <div className="banner banner-demo">
    <Bell size={17}/><strong>SYNTHETIC INTERFACE PREVIEW</strong>
    <span>Illustrative data only. Not connected to a controller, live agent, or recorded factory data.</span>
  </div>;
  if (backend === 'local' && !isLoopbackFrontend(window.location.hostname)) return <div className="banner banner-pilot">
    <ShieldCheck size={17}/><strong>LOCAL API UNAVAILABLE</strong>
    <span>A Vercel-hosted frontend cannot access your laptop's loopback API. Open the local frontend or switch to Render.</span>
  </div>;
  if (workspace === 'pilot') return <div className="banner banner-pilot">
    <ShieldCheck size={17}/><strong>READ-ONLY PILOT</strong>
    <span>Displays approved local artifacts only. No CNC commands or machine-control actions.</span>
  </div>;
  return null;
}

export function App() {
  const [expanded, setExpanded] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { preview, token, backend } = useUi();
  const capability = useResource<Capabilities>('/api/v1/capabilities', token, preview);
  const location = useLocation();
  useEffect(() => { window.scrollTo({ top: 0 }); }, [location.pathname]);
  return <div className={'application ' + (expanded ? '' : 'app-compact')}>
    <Sidebar expanded={expanded} setExpanded={setExpanded}
      mobileOpen={mobileOpen} closeMobile={() => setMobileOpen(false)}/>
    <div className="app-body">
      <Topbar openMenu={() => setMobileOpen(true)}/>
      <Banner />
      {!preview && capability.error && <div className="api-warning">
        <LockKeyhole size={17}/>{capability.error}
        <span>Check the selected API, connectivity, and access credentials.</span>
      </div>}
      <main id="main-content" className="content">
        <Routes key={backend}>
          <Route path="/" element={<HomePage/>}/>
          <Route path="/overview" element={<OverviewPage/>}/>
          <Route path="/investigations" element={<InvestigationListPage/>}/>
          <Route path="/investigations/triage" element={<TriagePage/>}/>
          <Route path="/investigations/deep" element={<DeepPage/>}/>
          <Route path="/investigations/review" element={<ReviewPage/>}/>
          <Route path="/investigations/:id" element={<InvestigationDetailPage/>}/>
          <Route path="/machines" element={<MachinesPage/>}/>
          <Route path="/signals" element={<SignalsPage/>}/>
          <Route path="/recordings" element={<RecordingsPage/>}/>
          <Route path="/recordings/quality" element={<QualityPage/>}/>
          <Route path="/recordings/sessions" element={<SessionsPage/>}/>
          <Route path="/lab" element={<LabPage/>}/>
          <Route path="/lab/runs" element={<RunsPage/>}/>
          <Route path="/lab/runs/:runId" element={<RunDetailPage/>}/>
          <Route path="/lab/evaluations" element={<EvaluationPage/>}/>
          <Route path="/lab/compare" element={<ComparePage/>}/>
          <Route path="/knowledge" element={<KnowledgePage/>}/>
          <Route path="/knowledge/manuals" element={<ManualsPage/>}/>
          <Route path="/knowledge/memory" element={<MemoryPage/>}/>
          <Route path="/system" element={<SystemPage/>}/>
          <Route path="/system/observability" element={<ObservabilityPage/>}/>
          <Route path="/system/audit" element={<AuditPage/>}/>
          <Route path="/system/settings" element={<SettingsPage/>}/>
          <Route path="*" element={<div className="not-found"><Settings2 size={38}/><h1>Page not found</h1>
            <p>This route is not in the workspace.</p><Link to="/" className="button-primary">Go to home<ArrowRight size={16}/></Link></div>}/>
        </Routes>
      </main>
      <footer className="footer"><span>FORGE / Manufacturing Research Assistant</span><span><Pill text={preview ? 'SYNTHETIC' : 'SOURCE-BOUND'} tone={preview ? 'warning' : 'neutral'}/>
        <span>v0.1 · {backend.toUpperCase()} API</span></span></footer>
    </div>
  </div>;
}
