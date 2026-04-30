/* global React */
// Alt C — Modern Minimalist : SaaS clean (Linear / Vercel / Notion vibe)

const MIN_KPIS = [
  { label: "OEE",        value: "84.2%", delta: "+2.1",  trend: "up" },
  { label: "Producción", value: "142.8k",delta: "+5.4%", trend: "up" },
  { label: "FPY",        value: "98.7%", delta: "+0.3",  trend: "up" },
  { label: "Downtime",   value: "47 min",delta: "−12",   trend: "down-good" },
];

const MIN_LINES = [
  { line: "Línea 1",  product: "Solid Dose",  oee: 88, status: "ok"   },
  { line: "Línea 2",  product: "Solid Dose",  oee: 82, status: "ok"   },
  { line: "Línea 3",  product: "Liquids",     oee: 71, status: "warn" },
  { line: "Línea 4",  product: "Packaging",   oee: 91, status: "ok"   },
  { line: "Línea 5",  product: "Packaging",   oee: 64, status: "bad"  },
];

function Sparkline({ data, color = "#0a0a0a" }) {
  const w = 80, h = 24;
  const max = Math.max(...data), min = Math.min(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={w} height={h} className="min-spark">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MinimalArtboard() {
  const chartRef = React.useRef(null);
  React.useEffect(() => {
    if (!chartRef.current || !window.echarts) return;
    const c = window.echarts.init(chartRef.current);
    const days = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
    c.setOption({
      grid: { left: 36, right: 16, top: 16, bottom: 28 },
      tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#e5e5e5', textStyle: { color: '#0a0a0a' }, padding: [8,12]},
      xAxis: {
        type: 'category', data: days,
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: '#737373', fontFamily: 'Geist, Inter, sans-serif', fontSize: 11 },
      },
      yAxis: {
        type: 'value', min: 70, max: 95,
        axisLine: { show: false }, axisTick: { show: false },
        splitLine: { lineStyle: { color: '#f5f5f5' }},
        axisLabel: { color: '#a3a3a3', fontFamily: 'Geist, Inter, sans-serif', fontSize: 11 },
      },
      series: [
        {
          type: 'bar', data: [82,84,86,83,87,79,81], barWidth: 28,
          itemStyle: { color: '#171717', borderRadius: [4,4,0,0] },
          markLine: {
            symbol: 'none', silent: true,
            lineStyle: { color: '#a3a3a3', type: 'dashed', width: 1 },
            data: [{ yAxis: 85, label: { formatter: '85%', color: '#737373', fontSize: 10, fontFamily: 'Geist, Inter, sans-serif' }}],
          }
        }
      ]
    });
    const ro = new ResizeObserver(()=>c.resize()); ro.observe(chartRef.current);
    return () => { ro.disconnect(); c.dispose(); };
  }, []);

  return (
    <div className="min-root">
      {/* Topbar */}
      <header className="min-top">
        <div className="min-brand">
          <span className="min-logo">◢</span>
          <span className="min-name">opex</span>
          <span className="min-slash">/</span>
          <button className="min-workspace">
            Alcobendas P2
            <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.2" fill="none"/></svg>
          </button>
        </div>
        <div className="min-search">
          <span className="min-search-icon">⌕</span>
          <input placeholder="Buscar líneas, problemas, métricas…" />
          <span className="min-kbd">⌘K</span>
        </div>
        <div className="min-top-right">
          <button className="min-icon-btn" aria-label="notif">
            <span className="min-icon-dot" />
          </button>
          <div className="min-avatar">SR</div>
        </div>
      </header>

      <div className="min-shell">
        {/* Sidebar */}
        <aside className="min-side">
          <div className="min-side-section">
            <a className="min-side-item min-side-active">
              <span className="min-side-icon">⌂</span>Overview
            </a>
            <a className="min-side-item"><span className="min-side-icon">▦</span>Líneas</a>
            <a className="min-side-item"><span className="min-side-icon">↻</span>Turnos</a>
            <a className="min-side-item"><span className="min-side-icon">!</span>Problemas <span className="min-side-count">3</span></a>
            <a className="min-side-item"><span className="min-side-icon">★</span>Iniciativas</a>
          </div>
          <div className="min-side-section">
            <p className="min-side-label">Workspace</p>
            <a className="min-side-item"><span className="min-side-icon">⊞</span>Reportes</a>
            <a className="min-side-item"><span className="min-side-icon">⚙</span>Ajustes</a>
          </div>
        </aside>

        {/* Main */}
        <main className="min-main">
          {/* Page header */}
          <div className="min-page-head">
            <div className="min-crumbs">
              <span>Overview</span>
              <span className="min-crumb-sep">/</span>
              <span className="min-crumb-active">Hoy</span>
            </div>
            <div className="min-page-actions">
              <button className="min-btn">Filtrar</button>
              <button className="min-btn">Exportar</button>
              <button className="min-btn min-btn-primary">Nuevo turno</button>
            </div>
          </div>

          <div className="min-page-title-row">
            <div>
              <h1 className="min-h1">Overview</h1>
              <p className="min-sub">Martes, 15 oct · 5 líneas activas · 3 alertas</p>
            </div>
            <div className="min-segment">
              <button className="min-seg-btn min-seg-active">Hoy</button>
              <button className="min-seg-btn">Semana</button>
              <button className="min-seg-btn">Mes</button>
            </div>
          </div>

          {/* KPIs */}
          <section className="min-kpis">
            {MIN_KPIS.map((k, i) => (
              <div key={k.label} className="min-kpi">
                <div className="min-kpi-head">
                  <span className="min-kpi-label">{k.label}</span>
                  <Sparkline data={[8,9,7,10,8,11,9,12,10,11,12,13]} color="#0a0a0a" />
                </div>
                <div className="min-kpi-value">{k.value}</div>
                <div className="min-kpi-foot">
                  <span className={`min-delta min-delta-${k.trend}`}>
                    {k.trend === 'up' ? '↗' : k.trend === 'down-good' ? '↘' : '↘'} {k.delta}
                  </span>
                  <span className="min-kpi-vs">vs. ayer</span>
                </div>
              </div>
            ))}
          </section>

          {/* Chart + lines */}
          <section className="min-grid">
            <div className="min-card">
              <div className="min-card-head">
                <div>
                  <h3 className="min-card-title">OEE diario</h3>
                  <p className="min-card-sub">Últimos 7 días · objetivo 85%</p>
                </div>
                <button className="min-btn min-btn-sm">Ver detalle →</button>
              </div>
              <div ref={chartRef} className="min-chart" />
            </div>

            <div className="min-card">
              <div className="min-card-head">
                <div>
                  <h3 className="min-card-title">Líneas</h3>
                  <p className="min-card-sub">Estado actual</p>
                </div>
              </div>
              <div className="min-table">
                <div className="min-th">
                  <span>Línea</span><span>Producto</span><span className="min-r">OEE</span><span></span>
                </div>
                {MIN_LINES.map(l => (
                  <div key={l.line} className="min-tr">
                    <span className="min-cell-line">{l.line}</span>
                    <span className="min-cell-prod">{l.product}</span>
                    <span className="min-r min-cell-oee">{l.oee}%</span>
                    <span className={`min-tag min-tag-${l.status}`}>
                      {l.status === 'ok' ? 'En marcha' : l.status === 'warn' ? 'Bajo objetivo' : 'Parada'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

window.MinimalArtboard = MinimalArtboard;
