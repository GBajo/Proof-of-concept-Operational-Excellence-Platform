// Navegación entre screens + charts ECharts del PoC original
(function () {
  // ===== Screen routing =====
  const navLinks = document.querySelectorAll('[data-screen]');
  const screens  = document.querySelectorAll('.screen[data-screen]');
  const triggers = document.querySelectorAll('[data-screen-link]');

  function go(name) {
    screens.forEach(s => s.classList.toggle('active', s.dataset.screen === name));
    document.querySelectorAll('.sidebar .nav-link[data-screen]').forEach(l => {
      l.classList.toggle('active', l.dataset.screen === name);
    });
    window.scrollTo({ top: 0, behavior: 'instant' });
    setTimeout(initChartsForScreen, 50);
  }
  navLinks.forEach(link => {
    if (link.tagName === 'A') {
      link.addEventListener('click', e => { e.preventDefault(); go(link.dataset.screen); });
    }
  });
  triggers.forEach(t => t.addEventListener('click', e => { e.preventDefault(); go(t.dataset.screenLink); }));

  // ===== Sidebar collapse =====
  document.getElementById('sidebarToggle').addEventListener('click', () => {
    document.body.classList.toggle('sidebar-collapsed');
  });

  // ===== Live clock (Shift Start) =====
  const clock = document.getElementById('live-clock');
  if (clock) {
    setInterval(() => {
      const d = new Date();
      const pad = n => String(n).padStart(2, '0');
      clock.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }, 1000);
  }

  // ===== History rows =====
  const tbody = document.getElementById('history-tbody');
  if (tbody) {
    const ROWS = [
      [1183, '2024/04/15', '06:12 → 14:00', 'Carlos Pérez', 2, '☀ Mañana', '7h 48m', 9421, 9600, 1.3, 38, 'completed'],
      [1182, '2024/04/14', '22:00 → 06:00', 'Ana Martín',   1, '🌙 Noche',  '8h 00m', 9580, 9600, 0.8, 24, 'completed'],
      [1181, '2024/04/14', '14:00 → 22:00', 'María González',4, '🌤 Tarde', '8h 00m', 8920, 9600, 2.4, 52, 'completed'],
      [1180, '2024/04/14', '06:00 → 14:00', 'Pedro López',  3, '☀ Mañana', '8h 00m', 9234, 9600, 1.6, 41, 'completed'],
      [1179, '2024/04/13', '22:00 → 04:30', 'Javier Ruiz',  2, '🌙 Noche',  '6h 30m', 6840, 9600, 3.1, 78, 'interrupted'],
      [1178, '2024/04/13', '14:00 → 22:00', 'Carlos Pérez', 5, '🌤 Tarde', '8h 00m', 9412, 9600, 1.0, 32, 'completed'],
      [1177, '2024/04/13', '06:00 → 14:00', 'Ana Martín',   1, '☀ Mañana', '8h 00m', 9620, 9600, 0.6, 18, 'completed'],
      [1176, '2024/04/12', '14:00 → 22:00', 'María González',4, '🌤 Tarde', '8h 00m', 9128, 9600, 1.8, 44, 'completed'],
    ];
    tbody.innerHTML = ROWS.map(r => {
      const [id, date, hours, op, line, type, dur, units, target, rejPct, dt, status] = r;
      const fmt = n => n.toLocaleString('es-ES');
      const pct = Math.round(units / target * 100);
      const pctCls = pct >= 95 ? 'bg-success' : pct >= 80 ? 'bg-warning' : 'bg-danger';
      const rejCls = rejPct <= 1 ? 'text-success' : rejPct <= 3 ? 'text-warning' : 'text-danger';
      const stCls  = status === 'completed' ? 'bg-success' : 'bg-warning text-dark';
      const stTxt  = status === 'completed' ? 'Completado' : 'Interrumpido';
      const trCls  = status === 'interrupted' ? ' class="table-warning"' : '';
      return `<tr${trCls}>
        <td class="text-muted small">${id}</td>
        <td><div class="small fw-semibold">${date}</div><div class="text-muted" style="font-size:.75rem;">${hours}</div></td>
        <td>${op}</td>
        <td><span class="badge bg-primary">L${line}</span></td>
        <td class="small">${type}</td>
        <td class="small">${dur}</td>
        <td><strong>${fmt(units)}</strong>
          <div class="progress mt-1" style="height:4px; width:80px;"><div class="progress-bar ${pctCls}" style="width:${Math.min(pct,100)}%"></div></div>
        </td>
        <td><span class="fw-semibold ${rejCls}">${rejPct}%</span></td>
        <td>${dt} min</td>
        <td><span class="badge ${stCls}">${stTxt}</span></td>
        <td><button class="btn btn-outline-primary btn-sm" data-screen-link="summary">Ver</button></td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('[data-screen-link]').forEach(b => b.addEventListener('click', e => {
      e.preventDefault(); go(b.dataset.screenLink);
    }));
  }

  // ===== Charts =====
  const charts = {};
  function makeOEEGauge(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    if (charts[id]) return charts[id];
    const c = echarts.init(el);
    c.setOption({
      series: [{
        type: 'gauge',
        startAngle: 200,
        endAngle: -20,
        min: 0, max: 100,
        progress: { show: true, width: 14, itemStyle: { color: '#f39c12' } },
        axisLine: { lineStyle: { width: 14, color: [[1, '#e8ecf0']] } },
        pointer: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        title: { show: false },
        detail: {
          valueAnimation: true,
          fontSize: 36, fontWeight: 800, color: '#1a2230',
          formatter: '{value}%',
          offsetCenter: [0, '0%'],
        },
        data: [{ value: 80.4 }],
      }],
    });
    charts[id] = c;
    return c;
  }
  function makeOEEEvolution(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    if (charts[id]) return charts[id];
    const c = echarts.init(el);
    const labels = ['07h','08h','09h','10h','11h','12h','13h','14h'];
    const oee = [78, 82, 85, 76, 79, 81, 83, 80];
    const target = labels.map(_=>85);
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { top: 16, right: 12, bottom: 28, left: 36 },
      xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: '#dee2e6' } } },
      yAxis: { type: 'value', min: 60, max: 100, splitLine: { lineStyle: { type: 'dashed', color: '#e8ecf0' } } },
      series: [
        { name: 'OEE', type: 'line', smooth: true, data: oee, lineStyle: { color: '#0d6efd', width: 3 }, itemStyle: { color: '#0d6efd' }, areaStyle: { color: 'rgba(13,110,253,0.12)' } },
        { name: 'Objetivo', type: 'line', symbol: 'none', data: target, lineStyle: { color: '#198754', type: 'dashed' } },
      ],
    });
    charts[id] = c;
    return c;
  }
  // ===== VSM =====
  let vsmActiveLine = 1;
  function renderVSM() {
    if (!window.VSM_LINES || !window.VSM_LINE_DATA) return;
    const tabs = document.getElementById('vsm-tabs');
    if (tabs && !tabs.children.length) {
      tabs.innerHTML = window.VSM_LINES.map(l =>
        `<button class="btn btn-sm ${l.id===vsmActiveLine?'btn-primary':'btn-outline-secondary'}" data-vsm-line="${l.id}">${l.label}</button>`
      ).join('');
      tabs.querySelectorAll('[data-vsm-line]').forEach(b => b.addEventListener('click', e => {
        vsmActiveLine = +e.currentTarget.dataset.vsmLine;
        tabs.innerHTML = '';
        document.getElementById('vsm-flow').innerHTML = '';
        document.getElementById('vsm-metrics').innerHTML = '';
        if (charts['vsm-cycle']) { charts['vsm-cycle'].dispose(); delete charts['vsm-cycle']; }
        renderVSM();
      }));
    }
    const data = window.VSM_LINE_DATA[vsmActiveLine];
    const m = data.metrics;

    const metrics = document.getElementById('vsm-metrics');
    if (metrics && !metrics.children.length) {
      const cards = [
        {l:'Lead time',     v: m.lead_time_s,    u:'s', cls:'kpi-card-border-blue'},
        {l:'Tiempo VA',     v: m.va_time_s,      u:'s', cls:'kpi-card-border-success'},
        {l:'% Valor añadido', v: m.va_ratio_pct, u:'%', cls:'kpi-card-border-purple'},
        {l:'WIP total',     v: m.total_wip,      u:'uds', cls:'kpi-card-border-teal'},
        {l:'Cuello botella',v: m.bottleneck,     u:'',  cls:'kpi-card-border-red'},
        {l:'OEE',           v: m.oee_pct,        u:'%', cls:'kpi-card-border-primary'},
      ];
      metrics.innerHTML = cards.map(c => `
        <div class="col-6 col-md-4 col-xl-2">
          <div class="card border-0 shadow-sm h-100 ${c.cls}">
            <div class="card-body p-3">
              <small class="text-uppercase fw-bold text-muted" style="font-size:.7rem;">${c.l}</small>
              <h4 class="fw-bold mt-1 mb-0" style="font-size:${typeof c.v==='string'?'.95rem':'1.4rem'};">${c.v}<small class="text-muted ms-1" style="font-size:.7rem;">${c.u}</small></h4>
            </div>
          </div>
        </div>`).join('');
    }

    const flow = document.getElementById('vsm-flow');
    if (flow && !flow.children.length) {
      flow.innerHTML = data.steps.map((s, i) => {
        const arrow = i < data.steps.length - 1 ? `<div class="vsm-arrow">→</div>` : '';
        return `
          <div class="vsm-step vsm-step--${s.color}">
            <div class="vsm-step__order">${s.step_order}</div>
            <span class="vsm-step__type-badge ${s.step_type==='value-add'?'vsm-step__type-badge--va':''}">${s.step_type==='value-add'?'VA':'NVA'}</span>
            <div class="vsm-step__name">${s.step_name}</div>
            <div class="vsm-step__metric"><span>CT</span><strong>${s.actual_cycle_time}s</strong></div>
            <div class="vsm-step__metric"><span>Nom</span><span>${s.nom_ct}s</span></div>
            <div class="vsm-step__metric"><span>WIP</span><strong>${s.units_in_wip}</strong></div>
            <span class="vsm-step__status vsm-step__status--${s.status}">${s.status}</span>
          </div>
          ${arrow}`;
      }).join('');
    }

    const el = document.getElementById('vsm-cycle');
    if (el && !charts['vsm-cycle']) {
      const c = echarts.init(el);
      c.setOption({
        tooltip: { trigger: 'axis' },
        legend: { bottom: 0 },
        grid: { top: 16, right: 16, bottom: 50, left: 40 },
        xAxis: { type: 'category', data: data.steps.map(s => s.step_name), axisLabel: { interval: 0, rotate: 25, fontSize: 10 } },
        yAxis: { type: 'value', name: 's' },
        series: [
          { name: 'Real',    type: 'bar', data: data.steps.map(s => s.actual_cycle_time), itemStyle:{ color: '#0d6efd' } },
          { name: 'Nominal', type: 'line', data: data.steps.map(s => s.nom_ct), itemStyle: { color: '#198754' }, lineStyle: { type: 'dashed' } },
        ],
      });
      charts['vsm-cycle'] = c;
    }
  }

  function renderSQDCP() {
    const grid = document.getElementById('sqdcp-cards');
    if (!grid || !window.SQDCP) return;
    if (grid.children.length > 0) return;
    grid.innerHTML = window.SQDCP.map(p => {
      const overall = Math.round((p.rings.daily + p.rings.weekly + p.rings.monthly) / 3);
      const status = overall >= 95 ? 'success' : overall >= 85 ? 'warning' : 'danger';
      const sub = p.sub.map(s => `
        <div class="sqdcp-sub-row">
          <span class="sqdcp-sub-l">${s.l}</span>
          <span class="sqdcp-sub-v">${s.v}</span>
          <span class="sqdcp-sub-d">${s.delta || ''}</span>
        </div>`).join('');
      return `
      <div class="col-md-6 col-xl">
        <div class="card border-0 shadow-sm sqdcp-card" style="border-top: 3px solid ${p.color} !important;">
          <div class="card-body">
            <div class="sqdcp-pillar-head">
              <div class="sqdcp-pillar-icon" style="background:${p.color}22; color:${p.color};">${p.icon}</div>
              <div class="sqdcp-pillar-letter" style="background:${p.color}; color:#fff;">${p.key}</div>
              <div class="flex-grow-1 min-w-0">
                <div class="sqdcp-pillar-name">${p.label}</div>
                <div class="sqdcp-pillar-desc">${p.desc}</div>
              </div>
              <span class="badge bg-${status}">${overall}%</span>
            </div>

            ${(() => {
              const cx = 65, cy = 65;
              const sw = 9;
              const rings = [
                { l: 'Diario',  v: p.rings.daily,   r: 56, op: 1 },
                { l: 'Semanal', v: p.rings.weekly,  r: 44, op: 0.7 },
                { l: 'Mensual', v: p.rings.monthly, r: 32, op: 0.4 },
              ];
              const overall = Math.round((p.rings.daily + p.rings.weekly + p.rings.monthly) / 3);
              const arcs = rings.map(rg => {
                const C = 2 * Math.PI * rg.r;
                const off = C * (1 - rg.v / 100);
                return `
                  <circle class="sqdcp-ring-track" cx="${cx}" cy="${cy}" r="${rg.r}" stroke-width="${sw}"></circle>
                  <circle class="sqdcp-ring-arc"   cx="${cx}" cy="${cy}" r="${rg.r}" stroke-width="${sw}"
                          stroke="${p.color}" stroke-opacity="${rg.op}"
                          stroke-dasharray="${C.toFixed(2)}" stroke-dashoffset="${off.toFixed(2)}"></circle>`;
              }).join('');
              const legend = rings.map(rg => `
                <div class="sqdcp-ring-legend-row">
                  <span class="sqdcp-ring-legend-sw" style="background:${p.color}; opacity:${rg.op};"></span>
                  <span class="sqdcp-ring-legend-l">${rg.l}</span>
                  <span class="sqdcp-ring-legend-v">${rg.v}%</span>
                </div>`).join('');
              return `
              <div class="sqdcp-rings">
                <div class="sqdcp-ring-svg-wrap">
                  <svg class="sqdcp-ring-svg" viewBox="0 0 130 130">${arcs}</svg>
                  <div class="sqdcp-ring-center">
                    <span class="sqdcp-ring-center-val">${overall}%</span>
                    <span class="sqdcp-ring-center-lbl">Global</span>
                  </div>
                </div>
                <div class="sqdcp-ring-legend">${legend}</div>
              </div>`;
            })()}

            <div class="sqdcp-primary">
              <span class="sqdcp-primary-name">${p.metric.name}</span>
              <span class="sqdcp-primary-val">${p.metric.value}</span>
              <span class="sqdcp-primary-unit">${p.metric.unit}</span>
              <span class="sqdcp-primary-target">meta ${p.metric.target}</span>
            </div>

            <div class="sqdcp-sub">${sub}</div>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  function makeSQDCPTrend(id) {
    const el = document.getElementById(id);
    if (!el || !window.SQDCP_TREND) return null;
    if (charts[id]) return charts[id];
    const c = echarts.init(el);
    const t = window.SQDCP_TREND;
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8 },
      grid: { top: 16, right: 16, bottom: 40, left: 40 },
      xAxis: { type: 'category', data: t.weeks, axisLine: { lineStyle: { color: '#dee2e6' } } },
      yAxis: { type: 'value', min: 70, max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { type: 'dashed', color: '#e8ecf0' } } },
      series: window.SQDCP.map(p => ({
        name: p.label, type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
        data: t[p.key], lineStyle: { color: p.color, width: 2 }, itemStyle: { color: p.color },
      })),
    });
    charts[id] = c;
    return c;
  }

  function makeInitiativesCharts() {
    const sav = document.getElementById('initiatives-savings');
    if (sav && !charts['initiatives-savings']) {
      const c = echarts.init(sav);
      c.setOption({
        tooltip: { trigger: 'axis' },
        grid: { top: 16, right: 16, bottom: 30, left: 56 },
        xAxis: { type: 'category', data: ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'] },
        yAxis: { type: 'value', axisLabel: { formatter: '€{value}k' } },
        series: [
          { name: 'Real', type: 'line', smooth: true, areaStyle: { color: 'rgba(13,110,253,.15)' }, lineStyle: { color: '#0d6efd', width: 3 }, itemStyle: { color: '#0d6efd' }, data: [80,180,310,540,820,1240,null,null,null,null,null,null] },
          { name: 'Plan', type: 'line', smooth: true, lineStyle: { color: '#198754', type: 'dashed' }, symbol: 'none', data: [100,210,340,500,720,1050,1380,1620,1850,2100,2350,2600] },
        ],
      });
      charts['initiatives-savings'] = c;
    }
    const typ = document.getElementById('initiatives-by-type');
    if (typ && !charts['initiatives-by-type']) {
      const c = echarts.init(typ);
      c.setOption({
        tooltip: { trigger: 'item' },
        legend: { bottom: 0, icon: 'circle' },
        series: [{
          type: 'pie', radius: ['45%', '72%'], avoidLabelOverlap: false,
          label: { show: true, formatter: '{b}\n{c}' },
          data: [
            { value: 4, name: 'SMED',   itemStyle:{color:'#0dcaf0'} },
            { value: 3, name: 'TPM',    itemStyle:{color:'#ffc107'} },
            { value: 2, name: '5S',     itemStyle:{color:'#0d6efd'} },
            { value: 3, name: 'Kaizen', itemStyle:{color:'#198754'} },
          ],
        }],
      });
      charts['initiatives-by-type'] = c;
    }
  }

  function makeBuilderChart(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    if (charts[id]) return charts[id];
    const c = echarts.init(el);
    c.setOption({
      color: ['#0057a8','#27ae60','#e67e22','#c0392b','#8e44ad'],
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { top: 30, right: 16, bottom: 50, left: 50 },
      xAxis: { type: 'category', data: ['Mañana','Tarde','Noche','Mañana','Tarde','Noche'], axisLabel: { interval: 0 } },
      yAxis: { type: 'value', min: 60, max: 100, axisLabel: { formatter: '{value}%' } },
      series: [
        { name: 'L1', type: 'bar', data: [88, 84, 79, 91, 86, 82] },
        { name: 'L2', type: 'bar', data: [82, 80, 76, 84, 81, 78] },
        { name: 'L3', type: 'bar', data: [86, 83, 80, 88, 85, 81] },
        { name: 'L4', type: 'bar', data: [79, 76, 73, 82, 78, 75] },
        { name: 'L5', type: 'bar', data: [90, 87, 84, 92, 89, 86] },
      ],
    });
    charts[id] = c;
    return c;
  }

  function initChartsForScreen() {
    try { makeOEEGauge('oee-gauge'); } catch(e) { console.error('gauge', e); }
    try { makeOEEEvolution('oee-evolution'); } catch(e) { console.error('evol', e); }
    try { renderVSM(); } catch(e) { console.error('vsm', e); }
    try { renderSQDCP(); } catch(e) { console.error('sqdcp render', e); }
    try { makeSQDCPTrend('sqdcp-trend'); } catch(e) { console.error('sqdcp trend', e); }
    try { makeBuilderChart('builder-chart'); } catch(e) { console.error('builder', e); }
    try { makeInitiativesCharts(); } catch(e) { console.error('init', e); }
    Object.values(charts).forEach(c => c && c.resize());
  }
  window.__opex = { initChartsForScreen, renderSQDCP };
  window.addEventListener('resize', () => Object.values(charts).forEach(c => c && c.resize()));

  // Init on load
  initChartsForScreen();
})();
