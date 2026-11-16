import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity, Archive, ArrowRight, Bell, BookOpen, Boxes, BrainCircuit, ChartNoAxesCombined,
  ChevronDown, ChevronLeft, ChevronRight, ClipboardCheck, ClipboardList, Database,
  FlaskConical, Gauge, GitCompareArrows, History, House, Layers, LockKeyhole,
  Menu, Moon, RadioTower, Search, Settings2, ShieldCheck, Signal,
  SlidersHorizontal, Sun, TerminalSquare, Waypoints, X,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { useUi } from './context';
import { useResource } from './api';
import { Pill } from './ui';
import type { Capabilities } from './types';
import {
  HomePage, OverviewPage, InvestigationListPage, InvestigationDetailPage,
  TriagePage, DeepPage, ReviewPage, MachinesPage, SignalsPage,
  RecordingsPage, QualityPage, SessionsPage,
  LabPage, RunsPage, EvaluationPage, ComparePage,
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
  return <>
    {mobileOpen && <button className="mobile-backdrop" aria-label="Close navigation" onClick={closeMobile} />}
    <aside className={'sidebar ' + (!expanded ? 'sidebar-compact ' : '') + (mobileOpen ? 'sidebar-open' : '')}>
      <Link to="/" className="brand" onClick={closeMobile}>
        <div className="brand-symbol"><Waypoints size={25} strokeWidth={1.8} /></div>
        {expanded && <div className="brand-words"><strong>FORGE<span className="brand-dot">.</span></strong>
          <small>Manufacturing Research AI</small></div>}
      </Link>
      {expanded && <div className="workspace-switch">
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
          {expanded && <div className="nav-group-label">{group}</div>}
          {nav.filter(item => item.group === group).map(item => {
            const Icon = item.icon;
            return <NavLink key={item.to} to={item.to} onClick={closeMobile}
              title={!expanded ? item.title : undefined} end={item.to === '/'}
              className={({ isActive }) => 'nav-item ' + (item.sub ? 'nav-sub ' : '') + (isActive ? 'active' : '')}>
              <Icon size={item.sub ? 17 : 19} strokeWidth={1.9} />
              {expanded && <span>{item.title}</span>}
            </NavLink>;
          })}
        </div>)}
      </nav>
      <div className="sidebar-bottom">
        {expanded && <div className="sidebar-safety"><LockKeyhole size={16} /><div><strong>Read-only pilot</strong>
          <small>No machine control or direct CNC access</small></div></div>}
        <button className="collapse-button" onClick={() => setExpanded(!expanded)}>
          {expanded ? <ChevronLeft size={17} /> : <ChevronRight size={17} />}
          {expanded && <span>Collapse sidebar</span>}
        </button>
      </div>
    </aside>
  </>;
}

function AccessDialog({ close }: { close: () => void }) {
  const { token, setToken } = useUi();
  const [value, setValue] = useState(token);
  return <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}>
    <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="access-title">
      <div className="dialog-top"><span className="tile-icon"><LockKeyhole size={21}/></span>
        <button className="icon-button" aria-label="Close" onClick={close}><X size={20}/></button></div>
      <h2 id="access-title">Local API access</h2>
      <p>Enter the token configured on the local FastAPI service. It stays in browser memory and is never saved to a file or local storage.</p>
      <label className="field-label" htmlFor="api-token">Session token</label>
      <input id="api-token" type="password" autoComplete="off" value={value}
        placeholder="CAPSTONE_UI_TOKEN" onChange={e => setValue(e.target.value)} />
      <div className="dialog-actions"><button className="button-secondary" onClick={() => { setToken(''); close(); }}>Clear access</button>
        <button className="button-primary" onClick={() => { setToken(value.trim()); close(); }}>Save for this session</button></div>
    </div>
  </div>;
}

function Topbar({ openMenu }: { openMenu: () => void }) {
  const { workspace, preview, setPreview, theme, setTheme, token } = useUi();
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
        <button className={'preview-toggle ' + (preview ? 'preview-active' : '')}
          onClick={() => setPreview(!preview)} title="Switch between real sources and labeled synthetic interface preview">
          <span className="preview-dot"/>{preview ? 'Exit preview' : 'Preview UI'}
        </button>
        <button className="icon-button" title="Toggle theme" aria-label="Toggle dark and light theme"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
          {theme === 'dark' ? <Sun size={19}/> : <Moon size={19}/>}
        </button>
        <button className="access-button" onClick={() => setShowAccess(true)}><LockKeyhole size={16}/>
          <span>{token ? 'Access set' : 'Access'}</span></button>
        <span className="header-environment">{workspace === 'pilot' ? 'PILOT' : 'SIM'}</span>
      </div>
    </header>
    {showAccess && <AccessDialog close={() => setShowAccess(false)} />}
  </>;
}

function Banner() {
  const { preview, workspace } = useUi();
  if (preview) return <div className="banner banner-demo">
    <Bell size={17}/><strong>SYNTHETIC INTERFACE PREVIEW</strong>
    <span>Illustrative data only. Not connected to a controller, live agent, or recorded factory data.</span>
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
  const { preview, token } = useUi();
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
        <span>Data panels remain unavailable until access is configured.</span>
      </div>}
      <main id="main-content" className="content">
        <Routes>
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
        <span>v0.1 · local industrial console</span></span></footer>
    </div>
  </div>;
}
