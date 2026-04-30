/* global React */
// Alt B — Industrial Tactical : oscuro, cockpit, alta densidad

const TAC_KPIS = [
  { label: "OEE",       value: "84.2", unit: "%",   delta: "+2.1",  trend: "up",   target: 85,  status: "ok"   },
  { label: "PRODUCED",  value: "142.8",unit: "k u", delta: "+5.4%", trend: "up",   target: 150, status: "ok"   },
  { label: "FPY",       value: "98.7", unit: "%",   delta: "+0.3",  trend: "up",   target: 99,  status: "ok"   },
  { label: "DOWNTIME",  value: "47",   unit: "min", delta: "-12",   trend: "down", target: 60,  status: "warn" },
  { label: "SCRAP",     value: "1.84", unit: "%",   delta: "+0.12", trend: "up",   target: 1.5, status: "bad"  },
  { label: "SAFETY",    value: "47",   unit: "d",   delta: "no LTI",trend: "flat", target: "—", status: "ok"   },
];

const TAC_LINES = [
  { id: "L01", name: "SOLID DOSE 1", oee: 88, prod: 12420, status: "ok",   alarm: null },
  { id: "L02", name: "SOLID DOSE 2", oee: 82, prod: 11210, status: "ok",   alarm: null },
  { id: "L03", name: "LIQUIDS",      oee: 71, prod: 8740,  status: "warn", alarm: "Velocidad < 80%" },
  { id: "L04", name: "PACKAGING 1",  oee: 91, prod: 14900, status: "ok",   alarm: null },
  { id: "L05", name: "PACKAGING 2",  oee: 64, prod: 6210,  status: "bad",  alarm: "Paro · 12 min" },
  { id: "L06", name: "BLISTER",      oee: 0,  prod: 0,     status: "off",  alarm: "Cambio formato" },
];

const TAC_ALERTS = [
  { sev: "P1", line: "L05", t: "11:42", msg: "Paro mecánico — sello defectuoso" },
  { sev: "P2", line: "L03", t: "11:08", msg: "Velocidad por debajo de objetivo (78%)" },
  { sev: "P3", line: "L02", t: "10:31", msg: "Mantenimiento preventivo programado" },
];

function TacticalArtboard() {
  const chartRef = React.useRef(null);
  const heatRef = React.useRef(null);
  const [clock, setClock] = React.useState("11:43:27");

  React.useEffect(() => {
    if (!chartRef.current || !window.echarts) return;
    const c = window.echarts.init(chartRef.current);
    const labels = Array.from({length:24}, (_,i)=>`${String(i).padStart(2,'0')}`);
    c.setOption({
      grid: { left: 36, right: 16, top: 14, bottom: 22 },
      tooltip: { trigger: 'axis', backgroundColor: '#0a1018', borderColor: '#263849', textStyle: { color: '#cdd6e0', fontFamily: 'JetBrains Mono' }},
      xAxis: {
        type: 'category', data: labels,
        axisLine: { lineStyle: { color: '#263849' }},
        axisLabel: { color: '#5e7186', fontFamily: 'JetBrains Mono', fontSize: 9 },
      },
      yAxis: {
        type: 'value', min: 50, max: 100,
        axisLine: { show: false }, splitLine: { lineStyle: { color: '#1c2a3a' }},
        axisLabel: { color: '#5e7186', fontFamily: 'JetBrains Mono', fontSize: 9 },
      },
      series: [
        {
          type: 'line', smooth: false, symbol: 'none',
          data: [72,75,78,82,84,85,83,86,88,87,84,86,89,85,82,80,84,86,88,90,87,85,82,84],
          lineStyle: { color: '#5ad1ff', width: 1.5 },
          areaStyle: {
            color: { type: 'linear', x:0,y:0,x2:0,y2:1, colorStops:[
              { offset: 0, color: 'rgba(90,209,255,0.32)' },
              { offset: 1, color: 'rgba(90,209,255,0.00)' },
            ]}
          },
          markLine: {
            symbol: 'none', silent: true,
            lineStyle: { color: '#f5a623', type: 'dashed', width: 1 },
            data: [{ yAxis: 85 }],
          },
        }
      ]
    });
    const ro = new ResizeObserver(()=>c.resize()); ro.observe(chartRef.current);
    return () => { ro.disconnect(); c.dispose(); };
  }, []);

  React.useEffect(() => {
    if (!heatRef.current || !window.echarts) return;
    const c = window.echarts.init(heatRef.current);
    const days = ['L','M','X','J','V','S','D'];
    const hours = Array.from({length:24}, (_,i)=>`${i}`);
    const data = [];
    for (let d=0; d<7; d++) for (let h=0; h<24; h++) {
      const v = Math.max(0, Math.round(Math.sin(d*1.3+h*0.4)*4 + Math.random()*6));
      data.push([h, d, v]);
    }
    c.setOption({
      grid: { left: 24, right: 8, top: 8, bottom: 22 },
      tooltip: { backgroundColor: '#0a1018', borderColor: '#263849', textStyle:{color:'#cdd6e0'}},
      xAxis: { type:'category', data: hours, splitArea:{show:false},
        axisLine:{lineStyle:{color:'#263849'}}, axisLabel:{color:'#5e7186', fontFamily:'JetBrains Mono', fontSize: 8 }},
      yAxis: { type:'category', data: days, splitArea:{show:false},
        axisLine:{lineStyle:{color:'#263849'}}, axisLabel:{color:'#5e7186', fontFamily:'JetBrains Mono', fontSize: 9 }},
      visualMap: { min:0, max:10, show:false, inRange:{color:['#0f1822','#1a3a5a','#3fb6ff','#f5a623','#ff5466']}},
      series: [{ type:'heatmap', data, itemStyle:{borderColor:'#0a1018', borderWidth:1}}]
    });
    const ro = new ResizeObserver(()=>c.resize()); ro.observe(heatRef.current);
    return () => { ro.disconnect(); c.dispose(); };
  }, []);

  return (
    <div className="tac-root">
      {/* Header bar */}
      <header className="tac-header">
        <div className="tac-brand">
          <span className="tac-led tac-led-pulse" />
          <span className="tac-wordmark">LILLY · OPEX</span>
          <span className="tac-sep">/</span>
          <span className="tac-ctx">PLANT_02</span>
          <span className="tac-sep">/</span>
          <span className="tac-ctx-active">CONTROL_ROOM</span>
        </div>
        <div className="tac-header-mid">
          <span className="tac-status-pill tac-pill-ok">● LIVE</span>
          <span className="tac-clock">{clock}</span>
          <span className="tac-shift">SHIFT_A · 06:00→14:00</span>
        </div>
        <div className="tac-header-right">
          <button className="tac-icon-btn" title="alerts">
            <span className="tac-badge">3</span>⚠
          </button>
          <span className="tac-user">SR_REYES</span>
        </div>
      </header>

      {/* KPI strip */}
      <section className="tac-kpis">
        {TAC_KPIS.map(k => (
          <div key={k.label} className={`tac-kpi tac-kpi-${k.status}`}>
            <div className="tac-kpi-head">
              <span className="tac-kpi-label">{k.label}</span>
              <span className={`tac-kpi-led tac-led-${k.status}`} />
            </div>
            <div className="tac-kpi-value">
              <span className="tac-kpi-num">{k.value}</span>
              <span className="tac-kpi-unit">{k.unit}</span>
            </div>
            <div className="tac-kpi-foot">
              <span className={`tac-delta tac-delta-${k.trend}`}>
                {k.trend === 'up' ? '↑' : k.trend === 'down' ? '↓' : '·'} {k.delta}
              </span>
              <span className="tac-target">→ {k.target}</span>
            </div>
          </div>
        ))}
      </section>

      {/* Main grid */}
      <section className="tac-grid">
        {/* Chart */}
        <div className="tac-panel tac-panel-chart">
          <div className="tac-panel-head">
            <span className="tac-panel-title">OEE_24H · TREND</span>
            <span className="tac-panel-meta">REFRESH 5s · TARGET 85%</span>
          </div>
          <div ref={chartRef} className="tac-chart" />
        </div>

        {/* Heatmap */}
        <div className="tac-panel tac-panel-heat">
          <div className="tac-panel-head">
            <span className="tac-panel-title">DOWNTIME_HEATMAP</span>
            <span className="tac-panel-meta">7d × 24h · min</span>
          </div>
          <div ref={heatRef} className="tac-heat" />
        </div>

        {/* Lines */}
        <div className="tac-panel tac-panel-lines">
          <div className="tac-panel-head">
            <span className="tac-panel-title">LINE_STATUS</span>
            <span className="tac-panel-meta">6 lines · 5 active</span>
          </div>
          <table className="tac-table">
            <thead><tr>
              <th>ID</th><th>LINE</th><th className="tac-r">OEE</th><th className="tac-r">UNITS</th><th>STATE</th>
            </tr></thead>
            <tbody>
              {TAC_LINES.map(l => (
                <tr key={l.id}>
                  <td className="tac-mono tac-dim">{l.id}</td>
                  <td className="tac-mono">{l.name}</td>
                  <td className="tac-r tac-mono"><strong>{l.oee}</strong>%</td>
                  <td className="tac-r tac-mono">{l.prod.toLocaleString()}</td>
                  <td>
                    <span className={`tac-state tac-state-${l.status}`}>
                      <span className={`tac-led tac-led-${l.status}`} />
                      {l.status === 'ok' ? 'RUN' : l.status === 'warn' ? 'WARN' : l.status === 'bad' ? 'STOP' : 'IDLE'}
                    </span>
                    {l.alarm && <span className="tac-alarm">{l.alarm}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Alerts */}
        <div className="tac-panel tac-panel-alerts">
          <div className="tac-panel-head">
            <span className="tac-panel-title">ACTIVE_ALERTS</span>
            <span className="tac-panel-meta">{TAC_ALERTS.length}</span>
          </div>
          <ul className="tac-alerts">
            {TAC_ALERTS.map((a,i) => (
              <li key={i} className={`tac-alert tac-alert-${a.sev}`}>
                <span className="tac-alert-sev">{a.sev}</span>
                <div className="tac-alert-body">
                  <p className="tac-alert-msg">{a.msg}</p>
                  <p className="tac-alert-meta">{a.line} · {a.t}</p>
                </div>
                <button className="tac-alert-ack">ACK</button>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

window.TacticalArtboard = TacticalArtboard;
