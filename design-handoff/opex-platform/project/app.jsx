// Main React app — OpEx Industrial Dashboard
const { useState, useEffect, useRef, useMemo } = React;

// ── Sidebar icon nav ──────────────────────────────────────────
function Sidebar({ screen, onScreen }) {
  const items = [
    { id: 'overview', icon: '◧', label: 'Overview' },
    { id: 'sqdcp',    icon: '◎', label: 'SQDCP' },
    { id: 'vsm',      icon: '⇄', label: 'VSM' },
    { id: 'lines',    icon: '⊞', label: 'Líneas' },
    { id: 'oee',      icon: '⏱', label: 'OEE' },
    { id: 'alerts',   icon: '⚠', label: 'Alertas', dot: true },
    { id: 'orders',   icon: '📋', label: 'Órdenes' },
    { id: 'maint',    icon: '🛠', label: 'Mantenim.' },
    { id: 'people',   icon: '👥', label: 'Personal' },
  ];
  const bottom = [{ icon: '⚙', label: 'Ajustes' }, { icon: '?', label: 'Ayuda' }];
  return (
    <aside className="sidebar">
      <div className="sidebar__logo">L</div>
      {items.map((it) => (
        <div key={it.id}
             className={`nav-icon ${screen===it.id ? 'active' : ''}`}
             title={it.label}
             onClick={() => onScreen(it.id)}>
          <span>{it.icon}</span>
          {it.dot && <span className="nav-icon__dot" />}
        </div>
      ))}
      <div className="nav-divider" />
      <div className="sidebar__spacer" />
      {bottom.map((it, i) => (
        <div key={i} className="nav-icon" title={it.label}><span>{it.icon}</span></div>
      ))}
    </aside>
  );
}

// ── Topbar ────────────────────────────────────────────────────
function Topbar({ site, onSiteChange, screen }) {
  const crumb = screen === 'sqdcp' ? 'SQDCP' : screen === 'vsm' ? 'VSM' : 'Overview';
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(()=>setNow(new Date()), 1000); return ()=>clearInterval(t); }, []);
  const fmt = now.toLocaleTimeString('es-ES', { hour12: false });
  return (
    <header className="topbar">
      <div className="topbar__title">OpEx Console</div>
      <div className="crumbs">
        <span>Operaciones</span>
        <span className="sep">›</span>
        <span>Manufactura</span>
        <span className="sep">›</span>
        <strong>{crumb}</strong>
      </div>
      <div className="topbar__spacer" />
      <div className="live-pulse">
        <span className="live-pulse__dot" />
        Live · {fmt}
      </div>
      <SitePicker site={site} onChange={onSiteChange} />
      <button className="icon-btn" title="Búsqueda">⌕</button>
      <button className="icon-btn" title="Alertas">
        ◬<span className="icon-btn__badge">3</span>
      </button>
      <div className="user-chip">
        <div className="user-chip__avatar">MR</div>
        <div className="user-chip__name">M. Rivera</div>
      </div>
    </header>
  );
}

function SitePicker({ site, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    function onClick(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener('mousedown', onClick); return ()=>document.removeEventListener('mousedown', onClick);
  }, []);
  const cur = window.SITES.find(s => s.id === site) || window.SITES[0];
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div className="site-pill" onClick={()=>setOpen(o=>!o)}>
        <span className="site-pill__flag">{cur.flag}</span>
        <span>{cur.name}</span>
        <span className="site-pill__caret">▾</span>
      </div>
      {open && (
        <div style={{ position:'absolute', top:'calc(100% + 6px)', right:0, background:'var(--bg-elev)',
          border:'1px solid var(--line-mid)', borderRadius:8, padding:4, minWidth:200, zIndex:20,
          boxShadow:'var(--shadow-pop)' }}>
          {window.SITES.map(s => (
            <div key={s.id} onClick={()=>{ onChange(s.id); setOpen(false); }}
              style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 10px', borderRadius:6,
                cursor:'pointer', fontSize:12, color: s.id===site?'var(--text)':'var(--text-mid)',
                background: s.id===site?'var(--bg-hover)':'transparent' }}>
              <span style={{ fontSize:14 }}>{s.flag}</span>
              <span style={{ flex:1 }}>{s.name}</span>
              {s.id===site && <span style={{ color:'var(--accent)' }}>✓</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page header ───────────────────────────────────────────────
function PageHead({ range, setRange }) {
  return (
    <div className="page-head">
      <div>
        <h1>Operations Overview</h1>
        <p className="page-head__sub">
          6 plantas activas · 24 líneas · turno actual <strong>T2 · 14:00–22:00</strong>
        </p>
      </div>
      <div className="page-head__actions">
        <div className="seg">
          {['Turno','Día','Semana','Mes','YTD'].map(r => (
            <button key={r} className={range===r?'active':''} onClick={()=>setRange(r)}>{r}</button>
          ))}
        </div>
        <button className="icon-btn" title="Filtros">⚲</button>
        <button className="icon-btn" title="Exportar">⬇</button>
      </div>
    </div>
  );
}

// ── KPI card ──────────────────────────────────────────────────
function KpiCard({ kpi }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const color = kpi.status === 'good' ? getCss('--good')
                : kpi.status === 'warn' ? getCss('--warn')
                : kpi.status === 'bad'  ? getCss('--bad')
                : getCss('--info');
    const c = ChartFactory.sparkline(ref.current, kpi.spark, color);
    const onResize = () => c.resize();
    window.addEventListener('resize', onResize);
    return () => { window.removeEventListener('resize', onResize); c.dispose(); };
  }, [kpi]);

  const arrow = kpi.delta > 0 ? '▲' : kpi.delta < 0 ? '▼' : '─';
  const goodDirection = !['down','reject'].includes(kpi.key);
  const isPositive = goodDirection ? kpi.delta > 0 : kpi.delta < 0;
  const deltaCls = kpi.delta === 0 ? 'flat' : isPositive ? 'up' : 'down';

  const pct = Math.min(100, Math.max(0, (kpi.value / kpi.target) * 100));
  const barColor = kpi.status === 'good' ? 'var(--good)'
                 : kpi.status === 'warn' ? 'var(--warn)'
                 : kpi.status === 'bad'  ? 'var(--bad)'
                 : 'var(--info)';

  return (
    <div className={`kpi kpi--${kpi.status}`}>
      <div className="kpi__head">
        <span className="kpi__label">{kpi.label}</span>
        <span className="kpi__icon">{iconFor(kpi.key)}</span>
      </div>
      <div className="kpi__value-row">
        <span className="kpi__value t-num">{formatVal(kpi.value, kpi.unit)}</span>
        <span className="kpi__unit">{kpi.unit}</span>
      </div>
      <div className="kpi__spark" ref={ref} />
      <div className="kpi__bar"><div className="kpi__bar-fill" style={{ width: pct+'%', background: barColor }} /></div>
      <div className="kpi__foot">
        <span className={`kpi__delta kpi__delta--${deltaCls}`}>
          {arrow} {Math.abs(kpi.delta)}{kpi.unit==='%' || kpi.unit==='min' ? (kpi.unit==='min'?'m':'pp') : '%'}
        </span>
        <span>Meta {formatVal(kpi.target, kpi.unit)}{kpi.unit==='%'?'%':''}</span>
      </div>
    </div>
  );
}
function getCss(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
function formatVal(v, u) {
  if (u === 'uds') return v.toLocaleString('es-ES');
  if (u === 'min') return v;
  return v;
}
function iconFor(k) {
  return { oee:'◐', units:'▦', avail:'◷', reject:'⊘', down:'⏻', rft:'✓' }[k] || '·';
}

// ── Lines panel ───────────────────────────────────────────────
function LinesPanel() {
  return (
    <div className="panel">
      <div className="panel__head">
        <div>
          <span className="panel__title">Líneas activas</span>
          <span className="panel__sub">6 de 24 mostradas · ordenadas por OEE</span>
        </div>
        <button className="icon-btn" style={{ width: 28, height: 28, fontSize: 14 }}>⋯</button>
      </div>
      <div className="lines-grid">
        {window.LINES.map(l => <LineCard key={l.id} line={l} />)}
      </div>
    </div>
  );
}
function LineCard({ line }) {
  const oeeCls = line.oee === 0 ? 'bad' : line.oee >= 85 ? 'good' : line.oee >= 70 ? 'warn' : 'bad';
  const rejCls = line.reject < 1 ? 'good' : line.reject < 2 ? 'warn' : 'bad';
  const statusMap = { running: 'En marcha', warn: 'Atención', down: 'Parada', idle: 'Inactiva' };
  return (
    <div className="line-card">
      <div className="line-card__head">
        <div>
          <div className="line-card__id">{line.id} <span>· {line.site}</span></div>
          <div className="line-card__op">{line.product} · {line.op}</div>
        </div>
        <span className={`status-led status-led--${line.status}`}>
          <span className="dot" />{statusMap[line.status]}
        </span>
      </div>
      <div className="line-card__metrics">
        <div className="line-metric">
          <span className="line-metric__l">OEE</span>
          <span className={`line-metric__v line-metric__v--${oeeCls}`}>{line.oee.toFixed(1)}%</span>
        </div>
        <div className="line-metric">
          <span className="line-metric__l">Unidades</span>
          <span className="line-metric__v">{(line.units/1000).toFixed(1)}k</span>
        </div>
        <div className="line-metric">
          <span className="line-metric__l">Rechazo</span>
          <span className={`line-metric__v line-metric__v--${rejCls}`}>{line.reject}%</span>
        </div>
      </div>
    </div>
  );
}

// ── Alerts panel ──────────────────────────────────────────────
function AlertsPanel() {
  return (
    <div className="panel">
      <div className="panel__head">
        <div>
          <span className="panel__title">Alertas activas</span>
          <span className="panel__sub">últimos 60 min</span>
        </div>
        <span className="chip chip--bad">2 críticas</span>
      </div>
      <div className="alert-list">
        {window.ALERTS.map((a, i) => (
          <div key={i} className="alert-row">
            <div className={`alert-row__bar alert-row__bar--${a.sev}`} />
            <div className="alert-row__main">
              <div className="alert-row__title">{a.title}</div>
              <div className="alert-row__meta">{a.line}</div>
            </div>
            <div className="alert-row__time t-num">{a.time}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Generic chart panel ───────────────────────────────────────
function ChartPanel({ title, sub, chip, factory, height = 280 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const c = factory(ref.current);
    const onR = () => c.resize();
    window.addEventListener('resize', onR);
    return () => { window.removeEventListener('resize', onR); c.dispose(); };
  }, []);
  return (
    <div className="panel">
      <div className="panel__head">
        <div>
          <span className="panel__title">{title}</span>
          {sub && <span className="panel__sub">{sub}</span>}
        </div>
        {chip}
      </div>
      <div className="panel__body">
        <div className="panel__chart" ref={ref} style={{ height }} />
      </div>
    </div>
  );
}

// ── Tweaks ───────────────────────────────────────────────────
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "industrial",
  "accent": "#3fb6ff",
  "compact": false,
  "showLines": true
}/*EDITMODE-END*/;

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [site, setSite] = useState('global');
  const [range, setRange] = useState('Turno');
  const [screen, setScreen] = useState('overview');

  useEffect(() => {
    const t = tweaks.theme === 'industrial' ? '' : tweaks.theme;
    if (t) document.documentElement.setAttribute('data-theme', t);
    else document.documentElement.removeAttribute('data-theme');
    document.documentElement.style.setProperty('--accent', tweaks.accent);
  }, [tweaks.theme, tweaks.accent]);

  return (
    <div className="app" data-compact={tweaks.compact}>
      <Sidebar screen={screen} onScreen={setScreen} />
      <div className="main">
        <Topbar site={site} onSiteChange={setSite} screen={screen} />
        {screen === 'sqdcp' ? <window.SQDCPPage /> : screen === 'vsm' ? <window.VSMPage /> : <>
        <PageHead range={range} setRange={setRange} />
        <div className="page">

          <div className="kpi-row">
            {window.KPIS.map(k => <KpiCard key={k.key} kpi={k} />)}
          </div>

          <div className="row-2">
            <ChartPanel title="OEE — últimos 14 turnos" sub="Meta 85%"
              chip={<span className="chip chip--warn">Bajo meta 4 turnos</span>}
              factory={ChartFactory.oeeTrend} />
            <ChartPanel title="Producción vs Objetivo" sub="turno actual"
              chip={<span className="chip chip--ghost">6 líneas</span>}
              factory={ChartFactory.prodVsTarget} />
          </div>

          <div className="row-mix">
            <ChartPanel title="Heatmap de paradas" sub="min · últimos 7 días × hora"
              factory={ChartFactory.heatmap} />
            <ChartPanel title="Categorías de paro" sub="min · turno actual"
              factory={ChartFactory.stopDonut} />
            <AlertsPanel />
          </div>

          <div className="row-2">
            <ChartPanel title="OEE por planta" sub="comparativa · YTD"
              chip={<span className="chip chip--good">2 sobre meta</span>}
              factory={ChartFactory.sitesBar} height={260} />
            {tweaks.showLines && <LinesPanel />}
          </div>

        </div>
        </>}
      </div>

      <TweaksPanel title="Tweaks">
        <TweakSection title="Tema">
          <TweakSelect label="Skin" value={tweaks.theme} onChange={v=>setTweak('theme', v)}
            options={[
              {value:'industrial', label:'Industrial (azul)'},
              {value:'tactical',   label:'Tactical (oscuro)'},
              {value:'graphite',   label:'Graphite (neutro)'},
            ]} />
          <TweakColor label="Color de acento" value={tweaks.accent} onChange={v=>setTweak('accent', v)} />
        </TweakSection>
        <TweakSection title="Layout">
          <TweakToggle label="Modo compacto" value={tweaks.compact} onChange={v=>setTweak('compact', v)} />
          <TweakToggle label="Mostrar líneas" value={tweaks.showLines} onChange={v=>setTweak('showLines', v)} />
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
