// ============================================================
// OpEx Platform — Dashboard con Apache ECharts
// ============================================================

// Instancias de gráficos (turno activo)
let gaugeChart = null;
let oeeLineChart = null;
let oeeAreaChart = null;

// Instancias de gráficos (supervisor)
let barChart = null;
let donutChart = null;
let heatmapChart = null;

let lastNominalSpeed = 1200;

const dashboardState = {
  lastCommentId: 0,
  failCount: 0,
  intervals: [],
  oeeHistory: [],   // { time, oee, availability, performance, quality }
};

// Paleta industrial
const PALETTE = {
  primary:    '#1a6faf',
  success:    '#27ae60',
  warning:    '#e67e22',
  danger:     '#c0392b',
  gray:       '#8a9bb0',
  bgDark:     '#1e2a3a',
  bgCard:     '#243447',
  gridLine:   '#2e3f52',
  textLight:  '#cdd6e0',
  textDim:    '#6b7f94',
};

// ── Colores de zonas OEE ─────────────────────────────────────
function oeeColor(v) {
  if (v >= 85) return PALETTE.success;
  if (v >= 60) return PALETTE.warning;
  return PALETTE.danger;
}

// ── Datos de ejemplo para heatmap y donut ────────────────────
function generateHeatmapData() {
  // Filas = días de la semana, Columnas = horas (0-23)
  const days   = ['Dom', 'Sáb', 'Vie', 'Jue', 'Mié', 'Mar', 'Lun'];
  const hours  = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);
  const data   = [];
  days.forEach((d, di) => {
    hours.forEach((h, hi) => {
      // Mayor probabilidad de paradas en cambios de turno y durante la noche
      let base = 0;
      if (hi >= 6 && hi <= 7)  base = 20;  // cambio mañana
      if (hi >= 14 && hi <= 15) base = 25; // cambio tarde
      if (hi >= 22 || hi <= 1)  base = 30; // turno noche
      if (di === 0 || di === 6) base += 10; // fines de semana
      const val = Math.max(0, base + (Math.random() * 15 - 5));
      data.push([hi, di, Math.round(val)]);
    });
  });
  return { days, hours, data };
}

function generateDonutData() {
  return [
    { value: 34, name: 'Mecánica' },
    { value: 22, name: 'Eléctrica' },
    { value: 18, name: 'Cambio formato' },
    { value: 14, name: 'Limpieza' },
    { value: 8,  name: 'Falta material' },
    { value: 4,  name: 'Otras' },
  ];
}

// ── Opciones comunes de tema oscuro ──────────────────────────
const COMMON_OPTS = {
  backgroundColor: 'transparent',
  textStyle: { color: PALETTE.textLight, fontFamily: 'inherit' },
};

// ============================================================
// TURNO ACTIVO
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
  if (typeof SHIFT_ID === 'undefined' || SHIFT_ID === null) {
    initSupervisorDashboard();
    return;
  }
  initOperatorDashboard();
});

function initOperatorDashboard() {
  initGaugeEChart();
  initOeeLineChart();
  loadInitialComments();
  PollManager.start(SHIFT_ID);
  document.addEventListener('visibilitychange', onVisibilityChange);
}

// ── Gauge OEE (ECharts) ──────────────────────────────────────
function initGaugeEChart() {
  const el = document.getElementById('oee-gauge');
  if (!el) return;
  gaugeChart = echarts.init(el, null, { renderer: 'svg' });

  const option = {
    ...COMMON_OPTS,
    series: [{
      type: 'gauge',
      startAngle: 200,
      endAngle: -20,
      min: 0,
      max: 100,
      splitNumber: 5,
      radius: '90%',
      center: ['50%', '60%'],
      axisLine: {
        lineStyle: {
          width: 18,
          color: [
            [0.60, PALETTE.danger],
            [0.85, PALETTE.warning],
            [1.00, PALETTE.success],
          ],
        },
      },
      pointer: {
        icon: 'path://M12.8,0.7l12,40.1H0.7L12.8,0.7z',
        length: '55%',
        width: 10,
        offsetCenter: [0, '-15%'],
        itemStyle: { color: '#e0eaf5' },
      },
      axisTick: { distance: -22, length: 6, lineStyle: { color: '#fff', width: 1 } },
      splitLine: { distance: -28, length: 14, lineStyle: { color: '#fff', width: 2 } },
      axisLabel: {
        distance: 6,
        color: PALETTE.textDim,
        fontSize: 10,
        formatter: (v) => v === 0 || v === 60 || v === 85 || v === 100 ? v + '%' : '',
      },
      anchor: {
        show: true,
        showAbove: true,
        size: 18,
        itemStyle: { borderWidth: 8, borderColor: '#e0eaf5', color: PALETTE.bgDark },
      },
      detail: {
        offsetCenter: [0, '30%'],
        fontSize: 32,
        fontWeight: '800',
        color: '#e0eaf5',
        formatter: '{value}%',
      },
      title: {
        offsetCenter: [0, '56%'],
        fontSize: 11,
        color: PALETTE.textDim,
        fontWeight: '600',
      },
      data: [{ value: 0, name: 'OEE' }],
    }],
  };
  gaugeChart.setOption(option);
  window.addEventListener('resize', () => gaugeChart && gaugeChart.resize());
}

function updateGauge(value) {
  if (!gaugeChart) return;
  const v = Math.min(Math.max(value || 0, 0), 100);
  gaugeChart.setOption({
    series: [{ data: [{ value: Math.round(v * 10) / 10, name: 'OEE' }] }],
  });
}

// ── Gráfico de línea OEE (turno activo) ─────────────────────
function initOeeLineChart() {
  const el = document.getElementById('oee-chart');
  if (!el) return;
  oeeLineChart = echarts.init(el, null, { renderer: 'svg' });

  const option = {
    ...COMMON_OPTS,
    grid: { top: 20, right: 20, bottom: 40, left: 48 },
    xAxis: {
      type: 'category',
      data: [],
      axisLine: { lineStyle: { color: PALETTE.gridLine } },
      axisLabel: { color: PALETTE.textDim, fontSize: 10 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      min: 0, max: 100,
      interval: 25,
      axisLine: { show: false },
      axisLabel: { color: PALETTE.textDim, fontSize: 10, formatter: '{value}%' },
      splitLine: { lineStyle: { color: PALETTE.gridLine, type: 'dashed' } },
    },
    series: [{
      name: 'OEE %',
      type: 'line',
      data: [],
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { color: PALETTE.primary, width: 2.5 },
      itemStyle: { color: PALETTE.primary },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(26,111,175,0.4)' },
          { offset: 1, color: 'rgba(26,111,175,0.02)' },
        ]),
      },
      markLine: {
        silent: true,
        symbol: 'none',
        data: [
          { yAxis: 85, lineStyle: { color: PALETTE.success, type: 'dashed', width: 1 },
            label: { formatter: '85%', color: PALETTE.success, fontSize: 10 } },
          { yAxis: 60, lineStyle: { color: PALETTE.warning, type: 'dashed', width: 1 },
            label: { formatter: '60%', color: PALETTE.warning, fontSize: 10 } },
        ],
      },
    }],
    tooltip: {
      trigger: 'axis',
      backgroundColor: PALETTE.bgCard,
      borderColor: PALETTE.gridLine,
      textStyle: { color: PALETTE.textLight, fontSize: 12 },
      formatter: (p) => `${p[0].name}<br/>OEE: <b>${p[0].value}%</b>`,
    },
    animation: false,
  };
  oeeLineChart.setOption(option);
  window.addEventListener('resize', () => oeeLineChart && oeeLineChart.resize());
}

// ── Polling ──────────────────────────────────────────────────
async function loadInitialComments() {
  try {
    const res = await fetch(`/api/comments/${SHIFT_ID}`);
    const comments = await res.json();
    if (typeof loadComments === 'function') loadComments(comments);
  } catch (e) { console.warn('loadInitialComments:', e); }
}

const PollManager = {
  start(shiftId) {
    this.stop();
    dashboardState.intervals = [
      setInterval(() => fetchKpis(shiftId), 30000),
      setInterval(() => fetchNewComments(shiftId), 30000),
      setInterval(() => fetchShiftStatus(shiftId), 60000),
    ];
    fetchKpis(shiftId);
  },
  stop() {
    dashboardState.intervals.forEach(clearInterval);
    dashboardState.intervals = [];
  },
  pause() { this.stop(); },
  resume(shiftId) { this.start(shiftId); },
};

function onVisibilityChange() {
  if (document.hidden) PollManager.pause();
  else PollManager.resume(SHIFT_ID);
}

async function fetchKpis(shiftId) {
  try {
    const res = await fetch(`/api/kpis/${shiftId}/latest`);
    if (!res.ok) throw new Error('fetch failed');
    const data = await res.json();
    updateKpiCards(data.oee_snapshot || {}, data);
    dashboardState.failCount = 0;
    hideBanner();
  } catch {
    dashboardState.failCount++;
    if (dashboardState.failCount >= 3) showBanner();
  }
}

async function fetchNewComments(shiftId) {
  try {
    const res = await fetch(`/api/comments/${shiftId}`);
    const comments = await res.json();
    const newOnes = comments.filter(c => c.id > dashboardState.lastCommentId);
    if (newOnes.length > 0) {
      newOnes.forEach(c => {
        dashboardState.lastCommentId = Math.max(dashboardState.lastCommentId, c.id);
      });
      if (typeof onNewComments === 'function') onNewComments(newOnes);
    }
  } catch { /* silencioso */ }
}

async function fetchShiftStatus(shiftId) {
  try {
    const res = await fetch(`/api/shifts/${shiftId}`);
    const shift = await res.json();
    if (shift.status !== 'active') {
      window.location.href = `/shift/${shiftId}/summary`;
    }
  } catch { /* silencioso */ }
}

function updateKpiCards(oee, raw) {
  const oeeVal = oee.oee;
  const now    = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

  // Gauge ECharts
  updateGauge(oeeVal);

  // Breakdown
  setText('kpi-availability', formatPct(oee.availability));
  setText('kpi-performance',  formatPct(oee.performance));
  setText('kpi-quality-val',  formatPct(oee.quality));
  setText('kpi-avail-card',   formatPct(oee.availability));
  setText('kpi-perf-card',    formatPct(oee.performance));
  setText('kpi-last-update',  now);

  // Unidades
  const produced = oee.total_units_produced || 0;
  const target   = oee.target_units || raw.target_units || 0;
  setText('kpi-units',        formatNumber(produced));
  setText('kpi-units-target', formatNumber(target));
  if (target > 0) {
    const pct = Math.min((produced / target) * 100, 100);
    setStyle('units-bar-fill', 'width', pct.toFixed(1) + '%');
    setBarColor('units-bar-fill', pct >= 95 ? PALETTE.success : pct >= 80 ? PALETTE.warning : PALETTE.danger);
    setText('units-pct-label', pct.toFixed(1) + '%');
  }

  setText('kpi-rejected-count', formatNumber(oee.total_units_rejected));
  setText('kpi-rft',             formatPct(oee.right_first_time_pct));

  // Velocidad
  const speed   = raw.line_speed || 0;
  const nominal = raw.nominal_speed || lastNominalSpeed;
  if (nominal) lastNominalSpeed = nominal;
  setText('kpi-speed',   formatNumber(Math.round(speed)));
  setText('kpi-nominal', formatNumber(nominal));
  if (nominal > 0) {
    const speedPct = Math.min((speed / nominal) * 100, 110);
    setStyle('speed-bar-fill', 'width', Math.min(speedPct, 100).toFixed(1) + '%');
    const diff  = ((speed - nominal) / nominal * 100).toFixed(1);
    const badge = document.getElementById('speed-indicator');
    if (badge) {
      if (speed >= nominal * 0.95) {
        badge.textContent = '▲ ' + diff + '% vs nominal';
        badge.className = 'dash-speed-badge dash-speed-badge--good';
      } else if (speed >= nominal * 0.80) {
        badge.textContent = '▼ ' + diff + '% vs nominal';
        badge.className = 'dash-speed-badge dash-speed-badge--warn';
      } else {
        badge.textContent = '▼ ' + diff + '% vs nominal';
        badge.className = 'dash-speed-badge dash-speed-badge--bad';
      }
    }
  }

  // KPIs secundarios
  setText('kpi-reject',   formatPct(oee.reject_rate_pct));
  setText('kpi-downtime', oee.total_downtime_minutes != null
    ? Math.round(oee.total_downtime_minutes) : '—');

  const rejectCard = document.getElementById('card-reject');
  if (rejectCard && oee.reject_rate_pct != null) {
    rejectCard.classList.toggle('kpi-card--alert', oee.reject_rate_pct > 3);
  }

  // Actualizar gráfico de línea OEE
  if (oeeLineChart && oeeVal != null) {
    const snapshot = dashboardState.oeeHistory;
    snapshot.push({ time: now, oee: Math.round(oeeVal * 10) / 10 });
    if (snapshot.length > 30) snapshot.shift();
    oeeLineChart.setOption({
      xAxis: { data: snapshot.map(p => p.time) },
      series: [{ data: snapshot.map(p => p.oee) }],
    });
  }
}

// ============================================================
// HELPERS DOM
// ============================================================

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}
function setStyle(id, prop, value) {
  const el = document.getElementById(id);
  if (el) el.style[prop] = value;
}
function setBarColor(id, color) {
  const el = document.getElementById(id);
  if (el) el.style.background = color;
}
function showBanner() {
  const b = document.getElementById('connection-banner');
  if (b) b.style.display = 'block';
}
function hideBanner() {
  const b = document.getElementById('connection-banner');
  if (b) b.style.display = 'none';
}

// ============================================================
// FORMULARIO MANUAL KPI
// ============================================================

function toggleKpiForm() {
  const section = document.getElementById('kpi-entry-section');
  if (!section) return;
  const visible = section.style.display !== 'none';
  section.style.display = visible ? 'none' : '';
  if (!visible) section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function submitManualKpi(e) {
  e.preventDefault();
  const form     = e.target;
  const errorBox = document.getElementById('kpi-form-error');
  const btn      = document.getElementById('kpi-submit-btn');
  errorBox.style.display = 'none';
  btn.disabled    = true;
  btn.textContent = 'Guardando...';

  const payload = {
    shift_id:         SHIFT_ID,
    units_produced:   parseInt(form.units_produced.value),
    units_rejected:   parseInt(form.units_rejected.value),
    downtime_minutes: parseFloat(form.downtime_minutes.value),
    line_speed:       parseFloat(form.line_speed.value),
    target_units:     parseInt(form.target_units.value),
    nominal_speed:    parseFloat(form.nominal_speed.value),
    planned_time_min: 480.0,
  };

  try {
    const res  = await fetch('/api/kpis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      errorBox.textContent    = data.error || 'Error al guardar la lectura';
      errorBox.style.display  = 'block';
      btn.disabled            = false;
      btn.textContent         = 'Guardar lectura';
      return;
    }
    await fetchKpis(SHIFT_ID);
    toggleKpiForm();
    form.reset();
    form.target_units.value  = '9600';
    form.nominal_speed.value = '1200';
  } catch {
    errorBox.textContent   = 'Error de conexión. Inténtalo de nuevo.';
    errorBox.style.display = 'block';
  }
  btn.disabled    = false;
  btn.textContent = 'Guardar lectura';
}

// ============================================================
// DASHBOARD SUPERVISOR — ECharts avanzado
// ============================================================

function initSupervisorDashboard() {
  // Leer filtros desde la URL
  const params     = new URLSearchParams(window.location.search);
  const filterLine = params.get('line') ? parseInt(params.get('line')) : null;

  initSupervisorMetricCards();
  initBarChart();
  initDonutChart();
  initHeatmapChart();
  initOeeAreaChart();
  initOeeKpiLineChart();

  // Polling de líneas activas
  const cards = document.querySelectorAll('[data-shift]');
  cards.forEach(card => {
    const shiftId = parseInt(card.dataset.shift);
    const lineNum  = parseInt(card.dataset.line);
    pollSupervisorLine(shiftId, lineNum);
    setInterval(() => pollSupervisorLine(shiftId, lineNum), 30000);
  });

  // Actualizar datos de ejemplo de gráficos cada 30 s
  setInterval(refreshSupervisorCharts, 30000);

  // Filtros
  const lineSelect = document.getElementById('filter-line-select');
  if (lineSelect) {
    lineSelect.addEventListener('change', () => {
      const url = new URL(window.location.href);
      if (lineSelect.value) url.searchParams.set('line', lineSelect.value);
      else url.searchParams.delete('line');
      window.location.href = url.toString();
    });
    if (filterLine) lineSelect.value = filterLine;
  }
}

function initSupervisorMetricCards() {
  // Las tarjetas superiores se actualizan via pollSupervisorLine
  // Aquí establecemos valores de ejemplo iniciales
  const now = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
  setText('sv-last-update', now);
}

// ── Barras horizontales: producción real vs objetivo ─────────
function initBarChart() {
  const el = document.getElementById('chart-bars');
  if (!el) return;
  barChart = echarts.init(el, null, { renderer: 'svg' });

  const lines    = ['Línea 1', 'Línea 2', 'Línea 3', 'Línea 4', 'Línea 5'];
  const targets  = [9600, 9600, 9600, 9600, 9600];
  const produced = [8940, 9250, 7800, 9600, 9120];

  barChart.setOption({
    ...COMMON_OPTS,
    grid: { top: 10, right: 80, bottom: 10, left: 70, containLabel: false },
    xAxis: {
      type: 'value',
      max: 11000,
      axisLabel: { color: PALETTE.textDim, fontSize: 10, formatter: v => v >= 1000 ? (v/1000).toFixed(0)+'k' : v },
      splitLine: { lineStyle: { color: PALETTE.gridLine, type: 'dashed' } },
      axisLine: { show: false },
    },
    yAxis: {
      type: 'category',
      data: lines,
      axisLabel: { color: PALETTE.textLight, fontSize: 11 },
      axisLine: { lineStyle: { color: PALETTE.gridLine } },
      axisTick: { show: false },
    },
    series: [
      {
        name: 'Objetivo',
        type: 'bar',
        data: targets,
        barGap: '-100%',
        barCategoryGap: '40%',
        itemStyle: { color: 'rgba(255,255,255,0.07)', borderRadius: 4 },
        z: 1,
      },
      {
        name: 'Producido',
        type: 'bar',
        data: produced.map((v, i) => ({
          value: v,
          itemStyle: {
            color: v >= targets[i] * 0.95 ? PALETTE.success
                 : v >= targets[i] * 0.80 ? PALETTE.warning
                 : PALETTE.danger,
            borderRadius: 4,
          },
        })),
        barCategoryGap: '40%',
        label: {
          show: true,
          position: 'right',
          color: PALETTE.textLight,
          fontSize: 10,
          formatter: p => p.value.toLocaleString('es-ES'),
        },
        z: 2,
      },
    ],
    legend: {
      data: ['Objetivo', 'Producido'],
      textStyle: { color: PALETTE.textDim, fontSize: 10 },
      right: 0, top: 0,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: PALETTE.bgCard,
      borderColor: PALETTE.gridLine,
      textStyle: { color: PALETTE.textLight, fontSize: 12 },
    },
  });
  window.addEventListener('resize', () => barChart && barChart.resize());
}

// ── Donut: distribución tipos de parada ─────────────────────
function initDonutChart() {
  const el = document.getElementById('chart-donut');
  if (!el) return;
  donutChart = echarts.init(el, null, { renderer: 'svg' });

  const colors = ['#1a6faf', '#27ae60', '#e67e22', '#8e44ad', '#c0392b', '#2c8c8c'];

  donutChart.setOption({
    ...COMMON_OPTS,
    color: colors,
    legend: {
      orient: 'vertical',
      right: '2%',
      top: 'center',
      textStyle: { color: PALETTE.textLight, fontSize: 10 },
      icon: 'circle',
    },
    series: [{
      name: 'Tipo parada',
      type: 'pie',
      radius: ['42%', '68%'],
      center: ['38%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 6, borderColor: PALETTE.bgDark, borderWidth: 2 },
      label: {
        show: true,
        position: 'center',
        formatter: () => 'Paradas\n(min)',
        color: PALETTE.textDim,
        fontSize: 11,
        lineHeight: 16,
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 13,
          fontWeight: 'bold',
          color: PALETTE.textLight,
          formatter: '{b}\n{d}%',
        },
      },
      labelLine: { show: false },
      data: generateDonutData(),
    }],
    tooltip: {
      trigger: 'item',
      backgroundColor: PALETTE.bgCard,
      borderColor: PALETTE.gridLine,
      textStyle: { color: PALETTE.textLight, fontSize: 12 },
      formatter: '{b}: {c} min ({d}%)',
    },
  });
  window.addEventListener('resize', () => donutChart && donutChart.resize());
}

// ── Heatmap: paradas por hora y día ─────────────────────────
function initHeatmapChart() {
  const el = document.getElementById('chart-heatmap');
  if (!el) return;
  heatmapChart = echarts.init(el, null, { renderer: 'svg' });

  const { days, hours, data } = generateHeatmapData();

  heatmapChart.setOption({
    ...COMMON_OPTS,
    grid: { top: 10, right: 20, bottom: 60, left: 42 },
    xAxis: {
      type: 'category',
      data: hours,
      splitArea: { show: true },
      axisLabel: {
        color: PALETTE.textDim,
        fontSize: 9,
        interval: 2,
        rotate: 45,
      },
      axisLine: { lineStyle: { color: PALETTE.gridLine } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: days,
      splitArea: { show: true },
      axisLabel: { color: PALETTE.textLight, fontSize: 10 },
      axisLine: { lineStyle: { color: PALETTE.gridLine } },
      axisTick: { show: false },
    },
    visualMap: {
      min: 0,
      max: 40,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: {
        color: ['#1e2a3a', '#1a4f7e', PALETTE.warning, PALETTE.danger],
      },
      textStyle: { color: PALETTE.textDim, fontSize: 9 },
    },
    series: [{
      name: 'Paradas (min)',
      type: 'heatmap',
      data,
      label: { show: false },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
    }],
    tooltip: {
      position: 'top',
      backgroundColor: PALETTE.bgCard,
      borderColor: PALETTE.gridLine,
      textStyle: { color: PALETTE.textLight, fontSize: 12 },
      formatter: (p) => {
        const h = hours[p.data[0]];
        const d = days[p.data[1]];
        return `${d} ${h}<br/>Paradas: <b>${p.data[2]} min</b>`;
      },
    },
  });
  window.addEventListener('resize', () => heatmapChart && heatmapChart.resize());
}

// ── Área apilada: D × R × C a lo largo del turno ────────────
function initOeeAreaChart() {
  const el = document.getElementById('chart-area');
  if (!el) return;
  oeeAreaChart = echarts.init(el, null, { renderer: 'svg' });

  // Datos de ejemplo: últimas 8 horas
  const hours = [];
  const dispData = [], rendData = [], calData = [];
  for (let i = 0; i < 16; i++) {
    const h = new Date(Date.now() - (15 - i) * 30 * 60000);
    hours.push(h.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }));
    dispData.push(+(88 + Math.random() * 8 - 4).toFixed(1));
    rendData.push(+(84 + Math.random() * 10 - 5).toFixed(1));
    calData.push(+(92 + Math.random() * 6 - 3).toFixed(1));
  }

  oeeAreaChart.setOption({
    ...COMMON_OPTS,
    grid: { top: 30, right: 20, bottom: 40, left: 48 },
    legend: {
      data: ['Disponibilidad', 'Rendimiento', 'Calidad'],
      textStyle: { color: PALETTE.textDim, fontSize: 10 },
      top: 2,
    },
    xAxis: {
      type: 'category',
      data: hours,
      boundaryGap: false,
      axisLabel: { color: PALETTE.textDim, fontSize: 9, interval: 3, rotate: 30 },
      axisLine: { lineStyle: { color: PALETTE.gridLine } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      min: 60, max: 100,
      axisLabel: { color: PALETTE.textDim, fontSize: 10, formatter: '{value}%' },
      splitLine: { lineStyle: { color: PALETTE.gridLine, type: 'dashed' } },
      axisLine: { show: false },
    },
    series: [
      {
        name: 'Disponibilidad',
        type: 'line',
        data: dispData,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#1a6faf', width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(26,111,175,0.35)' },
            { offset: 1, color: 'rgba(26,111,175,0.05)' },
          ]),
        },
      },
      {
        name: 'Rendimiento',
        type: 'line',
        data: rendData,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: PALETTE.warning, width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(230,126,34,0.25)' },
            { offset: 1, color: 'rgba(230,126,34,0.03)' },
          ]),
        },
      },
      {
        name: 'Calidad',
        type: 'line',
        data: calData,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: PALETTE.success, width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(39,174,96,0.25)' },
            { offset: 1, color: 'rgba(39,174,96,0.03)' },
          ]),
        },
      },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: PALETTE.bgCard,
      borderColor: PALETTE.gridLine,
      textStyle: { color: PALETTE.textLight, fontSize: 12 },
      formatter: (params) => {
        let s = `<b>${params[0].name}</b><br/>`;
        params.forEach(p => { s += `${p.marker}${p.seriesName}: ${p.value}%<br/>`; });
        return s;
      },
    },
  });
  window.addEventListener('resize', () => oeeAreaChart && oeeAreaChart.resize());
}

// ── Línea OEE histórico 7 días (supervisor) ──────────────────
function initOeeKpiLineChart() {
  const el = document.getElementById('chart-oee-line');
  if (!el) return;

  const svChart = echarts.init(el, null, { renderer: 'svg' });

  // Últimos 14 turnos de ejemplo
  const turnos   = [];
  const oeeVals  = [];
  const now      = new Date();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 8 * 3600000);
    turnos.push(d.toLocaleDateString('es-ES', { month: 'numeric', day: 'numeric' }) + '\n' +
                d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }));
    oeeVals.push(+(70 + Math.random() * 22).toFixed(1));
  }

  svChart.setOption({
    ...COMMON_OPTS,
    grid: { top: 20, right: 20, bottom: 50, left: 50 },
    xAxis: {
      type: 'category',
      data: turnos,
      axisLabel: { color: PALETTE.textDim, fontSize: 9, interval: 0 },
      axisLine: { lineStyle: { color: PALETTE.gridLine } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      min: 50, max: 100,
      axisLabel: { color: PALETTE.textDim, fontSize: 10, formatter: '{value}%' },
      splitLine: { lineStyle: { color: PALETTE.gridLine, type: 'dashed' } },
      axisLine: { show: false },
    },
    series: [{
      type: 'line',
      data: oeeVals.map(v => ({
        value: v,
        itemStyle: { color: oeeColor(v) },
      })),
      smooth: true,
      symbol: 'circle',
      symbolSize: 7,
      lineStyle: { color: PALETTE.primary, width: 2.5 },
      markLine: {
        silent: true,
        symbol: 'none',
        data: [
          { yAxis: 85, lineStyle: { color: PALETTE.success, type: 'dashed' },
            label: { formatter: 'Meta 85%', color: PALETTE.success, fontSize: 10 } },
        ],
      },
    }],
    tooltip: {
      trigger: 'axis',
      backgroundColor: PALETTE.bgCard,
      borderColor: PALETTE.gridLine,
      textStyle: { color: PALETTE.textLight, fontSize: 12 },
      formatter: (p) => `${p[0].name}<br/>OEE: <b>${p[0].value}%</b>`,
    },
  });
  window.addEventListener('resize', () => svChart && svChart.resize());
}

function refreshSupervisorCharts() {
  // Regenera datos de ejemplo en heatmap (en producción vendría de API)
  if (heatmapChart) {
    const { data } = generateHeatmapData();
    heatmapChart.setOption({ series: [{ data }] });
  }
}

async function pollSupervisorLine(shiftId, lineNum) {
  try {
    const res = await fetch(`/api/kpis/${shiftId}/aggregate`);
    const kpi = await res.json();
    const oee = kpi.oee != null ? kpi.oee.toFixed(1) : '—';
    setText(`sv-oee-${lineNum}`,    oee !== '—' ? oee + '%' : '—');
    setText(`sv-units-${lineNum}`,  formatNumber(kpi.total_units_produced));
    setText(`sv-reject-${lineNum}`, kpi.reject_rate_pct != null
      ? kpi.reject_rate_pct.toFixed(1) + '%' : '—');

    // Colorear badge OEE
    const oeeEl = document.getElementById(`sv-oee-${lineNum}`);
    if (oeeEl && kpi.oee != null) {
      oeeEl.style.color = oeeColor(kpi.oee);
    }
  } catch { /* silencioso */ }
}
