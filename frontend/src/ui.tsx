import type { ReactNode } from 'react';
import { Activity, AlertCircle, ArrowRight, CircleCheck, CircleHelp, Clock3, Info,
  Radio, ShieldAlert, Waypoints } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Sample } from './types';
import { describeSourceState, timeAxis } from './sourceState.mjs';
import type { SourceStateInput } from './sourceState.mjs';

export function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="eyebrow">{children}</div>;
}
export function PageHeading({ eyebrow, title, description, right }: {
  eyebrow: string; title: string; description?: string; right?: ReactNode;
}) {
  return <div className="page-heading">
    <div><Eyebrow>{eyebrow}</Eyebrow><h1>{title}</h1>
      {description && <p className="page-desc">{description}</p>}</div>
    {right && <div className="page-actions">{right}</div>}
  </div>;
}
export function Panel({ title, subtitle, action, children, className = '' }: {
  title?: string; subtitle?: string; action?: ReactNode;
  children: ReactNode; className?: string;
}) {
  return <section className={'panel ' + className}>
    {(title || action) && <div className="panel-head"><div>
      {title && <h2>{title}</h2>}{subtitle && <p>{subtitle}</p>}
    </div>{action && <div>{action}</div>}</div>}
    {children}
  </section>;
}
export function Pill({ text, tone = 'neutral' }: {
  text: string; tone?: 'good' | 'warning' | 'critical' | 'neutral' | 'info';
}) {
  return <span className={'pill pill-' + tone}>
    <span className="pill-mark" aria-hidden="true" />{text}</span>;
}
export function Metric({ label, value, note, icon, tone = 'neutral' }: {
  label: string; value: string | number | null | undefined; note?: string;
  icon?: ReactNode; tone?: 'good' | 'warning' | 'critical' | 'neutral' | 'info';
}) {
  return <div className="metric-card">
    <div className="metric-top"><span>{label}</span><span className={'metric-icon accent-' + tone}>{icon || <Activity size={17} />}</span></div>
    <strong>{value === null || value === undefined || value === '' ? '—' : value}</strong>
    <div className="metric-note">{note || 'Not available from source'}</div>
  </div>;
}
export function InfoState({ title, detail, kind = 'empty', action }: {
  title: string; detail: string; kind?: 'empty' | 'warning' | 'error'; action?: ReactNode;
}) {
  const Icon = kind === 'error' ? ShieldAlert : kind === 'warning' ? AlertCircle : CircleHelp;
  return <div className={'info-state state-' + kind}><span className="state-icon"><Icon size={22} /></span>
    <h3>{title}</h3><p>{detail}</p>{action && <div className="state-action">{action}</div>}</div>;
}
export function TileLink({ to, icon, title, description, hint }: {
  to: string; icon: ReactNode; title: string; description: string; hint?: string;
}) {
  return <Link className="tile-link" to={to}>
    <span className="tile-icon">{icon}</span><span className="tile-title">{title}</span>
    <span className="tile-description">{description}</span>
    <span className="tile-footer"><span>{hint || 'Open workspace'}</span><ArrowRight size={17} /></span>
  </Link>;
}
export function DataRow({ label, value, extra }: {
  label: string; value: ReactNode; extra?: ReactNode;
}) {
  return <div className="data-row"><div><div className="row-title">{label}</div>{extra && <div className="row-detail">{extra}</div>}</div>
    <div className="row-value">{value}</div></div>;
}
/** A capability this interface deliberately does not connect (a documented
 * architectural gap or a gate), as opposed to a source that is merely empty. */
export function Unavailable({ item = 'This view', detail }: { item?: string; detail?: string }) {
  return <InfoState title={item + ' is not connected'}
    detail={detail || 'No approved backend source is connected for this view. Sample readings are never substituted for real evidence.'} />;
}
/** Honest empty/loading/error/restricted state for a panel backed by an API
 * source. See describeSourceState for the precedence of the cases. */
export function SourceState(props: SourceStateInput) {
  // Variables:
  //   view: The one state describeSourceState chose; 'ready' renders nothing
  //     because the panel's own records are shown instead.
  const view = describeSourceState(props);
  if (view.kind === 'ready') return null;
  return <div role={view.kind === 'loading' ? 'status' : undefined} data-source-state={view.kind}>
    <InfoState title={view.title} detail={view.detail}
      kind={view.tone === 'error' ? 'error' : view.tone === 'warning' ? 'warning' : 'empty'}/></div>;
}
export function formatStamp(value: string | null | undefined) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Invalid timestamp' : date.toLocaleString();
}
export function formatNumber(value: number | null | undefined, digits = 0) {
  return value === null || value === undefined ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: digits });
}
export function formatBytes(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  return value > 1024 * 1024 ? (value / (1024 * 1024)).toFixed(1) + ' MB' :
    value > 1024 ? (value / 1024).toFixed(1) + ' KB' : String(value) + ' B';
}
export function toneFor(value: string | null | undefined): 'good' | 'warning' | 'critical' | 'neutral' | 'info' {
  const v = (value || '').toLowerCase();
  if (['good', 'connected', 'confirmed', 'healthy', 'running', 'supported', 'nominal', 'verified'].includes(v)) return 'good';
  if (['bad', 'failed', 'error', 'disconnected', 'critical', 'down'].includes(v)) return 'critical';
  if (['warning', 'uncertain', 'degraded', 'unresolved', 'review', 'gap', 'stale_or_none', 'revision_mismatch'].includes(v)) return 'warning';
  if (['received_recently', 'active'].includes(v)) return 'info';
  return 'neutral';
}
export function TrendChart({ items, label = 'Observation history' }: { items: Sample[]; label?: string }) {
  // Variables:
  //   axis: Horizontal positions from the samples' own timestamps, or from
  //     their order (flagged in the caption) when timestamps are missing,
  //     invalid or out of order. Even spacing is never implied silently.
  //   segments: Polylines of consecutive good samples; a bad sample or an
  //     epoch change (reconnect) ends one, so no line crosses a gap.
  const axis = timeAxis(items);
  const values = items.filter(p => p.value !== null && p.quality === 'good').map(p => p.value as number);
  if (values.length < 2) return <InfoState title="Insufficient chart data"
    detail="This chart requires at least two qualified numeric samples. Missing readings are never replaced with zero." />;
  const min = Math.min(...values), max = Math.max(...values);
  const range = Math.max(max - min, 4);
  const low = min - range * 0.16, high = max + range * 0.16;
  const x = (i: number) => 58 + axis.positions[i] * 690;
  const y = (v: number) => 280 - (v - low) / (high - low) * 240;
  const segments: string[] = [];
  let points: string[] = [];
  items.forEach((item, i) => {
    if (item.value === null || item.quality !== 'good') {
      if (points.length >= 2) segments.push(points.join(' '));
      points = [];
    } else {
      // A reconnect starts a new epoch; never draw continuity across a missing interval.
      if (i > 0 && items[i - 1].epoch !== item.epoch) {
        if (points.length >= 2) segments.push(points.join(' '));
        points = [];
      }
      points.push(x(i).toFixed(1) + ',' + y(item.value).toFixed(1));
    }
  });
  if (points.length >= 2) segments.push(points.join(' '));
  return <div className="trend" role="img" aria-label={label + '. ' + values.length + ' good numerical values; invalid values shown as gaps.'}>
    <svg viewBox="0 0 790 320" preserveAspectRatio="xMidYMid meet">
      {Array.from({ length: 5 }, (_, i) => {
        const v = high - (high - low) * i / 4, py = y(v);
        return <g key={i}><line x1="58" x2="748" y1={py} y2={py} className="chart-grid" />
          <text x="47" y={py + 4} textAnchor="end" className="chart-label">{formatNumber(v, 1)}</text></g>;
      })}
      {segments.map((segment, i) => <polyline key={i} points={segment} className="chart-line" />)}
      {items.map((item, i) => item.value === null || item.quality !== 'good' ?
        <g key={i}><line x1={x(i)} x2={x(i)} y1="33" y2="280" className="chart-gap" />
          <circle cx={x(i)} cy="284" r="3" className="chart-gap-dot" /></g> : null)}
      <text x="58" y="308" className="chart-label">Earlier</text>
      <text x="748" y="308" textAnchor="end" className="chart-label">Latest</text>
    </svg><div className="chart-caption"><span><span className="legend-mark" /> Good numeric observation</span>
      <span><span className="legend-gap" /> Bad / missing data gap</span>
      <span>{axis.mode === 'time' ? 'Horizontal spacing follows source timestamps' :
        'Timestamps unusable: points are in recorded order, not to time scale'}</span></div>
  </div>;
}
export function MachineLine({ machines, pilot = false, source }: {
  machines: Array<{ id: string; name: string; operating_state?: string; condition?: string }>;
  pilot?: boolean; source?: Omit<SourceStateInput, 'item'>;
}) {
  // Variables:
  //   source: Loading, error and availability facts for the machine list; when
  //     given, an empty lineup says why it is empty instead of a fixed message.
  if (!machines.length) return source ? <SourceState item="Machine lineup" {...source}/> :
    <Unavailable item="Machine lineup" detail="No authorized machine inventory is connected. The UI will never invent CNC states." />;
  return <div className={'machine-line ' + (pilot ? 'single-machine' : '')}>
    {machines.map((machine, i) => <div className="line-unit" key={machine.id}>
      <Link to={'/machines?selected=' + encodeURIComponent(machine.id)} className="machine-unit">
        <div className="machine-head"><Waypoints size={17} /><span>{'0' + (i + 1)}</span></div>
        <div className="machine-sketch" aria-hidden="true"><div className="sketch-housing">
          <div className="sketch-window"><span className="sketch-tool" /><span className="sketch-platform" /></div>
          <div className="sketch-console"><span /><span /><span /></div>
        </div></div>
        <h3>{machine.name}</h3><Pill text={machine.operating_state || 'Unknown'} tone={toneFor(machine.condition || machine.operating_state)} />
      </Link>{i < machines.length - 1 && <span className="line-connector" aria-hidden="true"><Radio size={15}/></span>}
    </div>)}
  </div>;
}
export function QualityExplanation() {
  return <div className="quality-rule"><Info size={18} />
    <span><strong>Evidence policy:</strong> connected does not mean subscribed; received does not mean valid;
      native Good quality does not establish an approved unit, freshness policy or diagnosis eligibility.</span></div>;
}
export function TableHead({ children }: { children: ReactNode }) {
  return <div className="table-head">{children}</div>;
}
export function SummaryLink({ to, label }: { to: string; label: string }) {
  return <Link to={to} className="text-link">{label}<ArrowRight size={16} /></Link>;
}
export function TimelineEvent({ label, at, status = 'neutral', note }: {
  label: string; at?: string; status?: 'good' | 'warning' | 'critical' | 'neutral'; note?: string;
}) {
  return <div className="timeline-event"><span className={'timeline-node accent-' + status}>
    {status === 'good' ? <CircleCheck size={15}/> : status === 'warning' ? <AlertCircle size={15}/> : <Clock3 size={15}/>}</span>
    <div><strong>{label}</strong>{note && <p>{note}</p>}</div>
    <time>{at || 'Not timestamped'}</time></div>;
}
