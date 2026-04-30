/* global React, ReactDOM */
// Alt A — "Pharma Premium" : brand-led Lilly, claro, editorial

const PHARMA_KPIS = [
  { label: "OEE Global", value: "84.2", unit: "%", delta: "+2.1", trend: "up", target: "85.0" },
  { label: "Producción", value: "142.8", unit: "k u", delta: "+5.4%", trend: "up", target: "150 k" },
  { label: "Calidad (FPY)", value: "98.7", unit: "%", delta: "+0.3", trend: "up", target: "99.0" },
  { label: "Seguridad", value: "47", unit: "días", delta: "sin LTI", trend: "flat", target: "—" },
];

const PHARMA_LINES = [
  { line: "Línea 1 — Solid Dose", oee: 88, status: "ok", shift: "Mañana" },
  { line: "Línea 2 — Solid Dose", oee: 82, status: "ok", shift: "Mañana" },
  { line: "Línea 3 — Liquids",    oee: 71, status: "warn", shift: "Mañana" },
  { line: "Línea 4 — Packaging",  oee: 91, status: "ok", shift: "Mañana" },
  { line: "Línea 5 — Packaging",  oee: 64, status: "bad", shift: "Mañana" },
];

function PharmaArtboard() {
  const chartRef = React.useRef(null);
  React.useEffect(() => {
    if (!chartRef.current || !window.echarts) return;
    const c = window.echarts.init(chartRef.current);
    const hours = Array.from({length: 12}, (_,i) => `${String(i*2).padStart(2,'0')}:00`);
    c.setOption({
      grid: { left: 48, right: 24, top: 24, bottom: 36 },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category', data: hours,
        axisLine: { lineStyle: { color: '#d8d4cf' } },
        axisLabel: { color: '#6b6661', fontFamily: 'Ringside, sans-serif', fontSize: 11 },
      },
      yAxis: {
        type: 'value', min: 60, max: 100,
        axisLine: { show: false }, splitLine: { lineStyle: { color: '#ece8e2' } },
        axisLabel: { color: '#6b6661', fontFamily: 'Ringside, sans-serif', fontSize: 11, formatter: '{value}%' },
      },
      series: [
        {
          name: 'OEE', type: 'line', smooth: true,
          data: [78,82,84,85,83,86,88,87,84,86,89,85],
          symbol: 'circle', symbolSize: 6,
          lineStyle: { color: '#d52b1e', width: 2.5 },
          itemStyle: { color: '#d52b1e' },
          areaStyle: {
            color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(213,43,30,0.18)' },
                { offset: 1, color: 'rgba(213,43,30,0.00)' },
              ]
            }
          },
          markLine: {
            symbol: 'none', lineStyle: { color: '#9b9690', type: 'dashed' },
            data: [{ yAxis: 85, label: { formatter: 'Objetivo 85%', color: '#6b6661', fontFamily: 'Ringside' }}]
          },
        }
      ]
    });
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(chartRef.current);
    return () => { ro.disconnect(); c.dispose(); };
  }, []);

  return (
    <div className="ph-root">
      {/* Topbar */}
      <header className="ph-top">
        <div className="ph-brand">
          <span className="ph-dot" />
          <span className="ph-wordmark">LILLY</span>
          <span className="ph-divider" />
          <span className="ph-product">Operational Excellence</span>
        </div>
        <nav className="ph-nav">
          <a className="ph-nav-item ph-active">Overview</a>
          <a className="ph-nav-item">Turnos</a>
          <a className="ph-nav-item">Problemas</a>
          <a className="ph-nav-item">Iniciativas</a>
          <a className="ph-nav-item">Reportes</a>
        </nav>
        <div className="ph-tools">
          <span className="ph-pill">Alcobendas · Planta 2</span>
          <span className="ph-avatar">SR</span>
        </div>
      </header>

      {/* Hero / page title */}
      <section className="ph-hero">
        <div>
          <p className="ph-eyebrow">Resumen del día · Martes 15 oct</p>
          <h1 className="ph-h1">Buenos días, Sara.</h1>
          <p className="ph-sub">3 líneas en marcha · 1 alerta activa · próximo cambio de turno en 02:14</p>
        </div>
        <div className="ph-hero-actions">
          <button className="ph-btn-ghost">Exportar</button>
          <button className="ph-btn-primary">Iniciar turno</button>
        </div>
      </section>

      {/* KPIs */}
      <section className="ph-kpis">
        {PHARMA_KPIS.map(k => (
          <div key={k.label} className="ph-kpi">
            <p className="ph-kpi-label">{k.label}</p>
            <div className="ph-kpi-value">
              <span className="ph-kpi-num">{k.value}</span>
              <span className="ph-kpi-unit">{k.unit}</span>
            </div>
            <div className="ph-kpi-foot">
              <span className={`ph-delta ph-delta-${k.trend}`}>
                {k.trend === 'up' ? '▲' : k.trend === 'down' ? '▼' : '—'} {k.delta}
              </span>
              <span className="ph-kpi-target">Obj. {k.target}</span>
            </div>
          </div>
        ))}
      </section>

      {/* Chart + lines */}
      <section className="ph-grid">
        <div className="ph-card ph-card-chart">
          <div className="ph-card-head">
            <div>
              <p className="ph-card-eyebrow">Tendencia · 24h</p>
              <h3 className="ph-card-title">OEE por hora</h3>
            </div>
            <div className="ph-tabs">
              <button className="ph-tab ph-tab-active">24h</button>
              <button className="ph-tab">7d</button>
              <button className="ph-tab">30d</button>
            </div>
          </div>
          <div ref={chartRef} className="ph-chart" />
        </div>

        <div className="ph-card ph-card-lines">
          <div className="ph-card-head">
            <div>
              <p className="ph-card-eyebrow">Estado actual</p>
              <h3 className="ph-card-title">Líneas activas</h3>
            </div>
          </div>
          <ul className="ph-lines">
            {PHARMA_LINES.map(l => (
              <li key={l.line} className="ph-line">
                <span className={`ph-line-status ph-status-${l.status}`} />
                <div className="ph-line-info">
                  <p className="ph-line-name">{l.line}</p>
                  <p className="ph-line-shift">{l.shift}</p>
                </div>
                <div className="ph-line-oee">
                  <span className="ph-line-num">{l.oee}</span>
                  <span className="ph-line-pct">%</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

window.PharmaArtboard = PharmaArtboard;
