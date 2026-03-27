// PollManager: actualización periódica del dashboard

let oeeChart = null;
let gaugeChart = null;
let lastNominalSpeed = 1200;

const dashboardState = {
  lastCommentId: 0,
  failCount: 0,
  intervals: [],
};

document.addEventListener('DOMContentLoaded', () => {
  if (typeof SHIFT_ID === 'undefined' || SHIFT_ID === null) {
    initSupervisorDashboard();
    return;
  }
  initOperatorDashboard();
});

// ── Operador: turno activo ──────────────────────────────────

function initOperatorDashboard() {
  initOeeChart();
  initGaugeChart();
  loadInitialComments();
  PollManager.start(SHIFT_ID);
  document.addEventListener('visibilitychange', onVisibilityChange);
}

function initOeeChart() {
  const ctx = document.getElementById('oee-chart');
  if (!ctx) return;
  oeeChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'OEE %',
        data: [],
        borderColor: '#27ae60',
        backgroundColor: 'rgba(39,174,96,0.08)',
        tension: 0.3,
        fill: true,
        pointRadius: 3,
      }],
    },
    options: {
      responsive: true,
      animation: false,
      scales: {
        y: { min: 0, max: 100, ticks: { callback: v => v + '%' } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function initGaugeChart() {
  const ctx = document.getElementById('oee-gauge');
  if (!ctx) return;
  gaugeChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [0, 100],
        backgroundColor: ['#27ae60', '#e9ecef'],
        borderWidth: 0,
        hoverOffset: 0,
      }],
    },
    options: {
      circumference: 180,
      rotation: -90,
      cutout: '72%',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
      animation: { duration: 600 },
    },
  });
}

function updateGauge(value) {
  if (!gaugeChart) return;
  const v = Math.min(Math.max(value || 0, 0), 100);
  const color = v >= 85 ? '#27ae60' : v >= 60 ? '#f39c12' : '#e74c3c';
  gaugeChart.data.datasets[0].data = [v, 100 - v];
  gaugeChart.data.datasets[0].backgroundColor[0] = color;
  gaugeChart.update('active');
}

async function loadInitialComments() {
  try {
    const res = await fetch(`/api/comments/${SHIFT_ID}`);
    const comments = await res.json();
    if (typeof loadComments === 'function') {
      loadComments(comments);
    }
  } catch (e) { console.warn('loadInitialComments: error al cargar comentarios', e); }
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
  if (document.hidden) {
    PollManager.pause();
  } else {
    PollManager.resume(SHIFT_ID);
  }
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
      if (typeof onNewComments === 'function') {
        onNewComments(newOnes);
      }
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

  // Gauge
  updateGauge(oeeVal);

  // Valor OEE y breakdown
  setText('kpi-oee', formatPct(oeeVal));
  setText('kpi-availability', formatPct(oee.availability));
  setText('kpi-performance',  formatPct(oee.performance));
  setText('kpi-quality-val',  formatPct(oee.quality));
  setText('kpi-avail-card',   formatPct(oee.availability));
  setText('kpi-perf-card',    formatPct(oee.performance));

  // Timestamp
  const now = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
  setText('kpi-last-update', now);

  // Unidades producidas + barra progreso
  const produced = oee.total_units_produced || 0;
  const target   = oee.target_units || raw.target_units || 0;
  setText('kpi-units', formatNumber(produced));
  setText('kpi-units-target', formatNumber(target));
  if (target > 0) {
    const pct = Math.min((produced / target) * 100, 100);
    setStyle('units-bar-fill', 'width', pct.toFixed(1) + '%');
    setBarColor('units-bar-fill', pct >= 95 ? '#27ae60' : pct >= 80 ? '#f39c12' : '#e74c3c');
    setText('units-pct-label', pct.toFixed(1) + '%');
  }

  // Unidades rechazadas y RFT
  setText('kpi-rejected-count', formatNumber(oee.total_units_rejected));
  setText('kpi-rft', formatPct(oee.right_first_time_pct));

  // Velocidad de línea + barra
  const speed   = raw.line_speed || 0;
  const nominal = raw.nominal_speed || lastNominalSpeed;
  if (nominal) lastNominalSpeed = nominal;
  setText('kpi-speed',   formatNumber(Math.round(speed)));
  setText('kpi-nominal', formatNumber(nominal));
  if (nominal > 0) {
    const speedPct = Math.min((speed / nominal) * 100, 110);
    setStyle('speed-bar-fill', 'width', Math.min(speedPct, 100).toFixed(1) + '%');
    const diff = ((speed - nominal) / nominal * 100).toFixed(1);
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

  // Colorear tarjeta de rechazo
  const rejectCard = document.getElementById('card-reject');
  if (rejectCard && oee.reject_rate_pct != null) {
    rejectCard.classList.toggle('kpi-card--alert', oee.reject_rate_pct > 3);
  }

  // Gráfico de línea OEE
  if (oeeChart && oeeVal != null) {
    oeeChart.data.labels.push(now);
    oeeChart.data.datasets[0].data.push(oeeVal);
    if (oeeChart.data.labels.length > 30) {
      oeeChart.data.labels.shift();
      oeeChart.data.datasets[0].data.shift();
    }
    oeeChart.update('none');
  }
}

// ── Helpers ────────────────────────────────────────────────

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

// ── Formulario manual de KPI ───────────────────────────────

function toggleKpiForm() {
  const section = document.getElementById('kpi-entry-section');
  if (!section) return;
  const visible = section.style.display !== 'none';
  section.style.display = visible ? 'none' : '';
  if (!visible) section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function submitManualKpi(e) {
  e.preventDefault();
  const form = e.target;
  const errorBox = document.getElementById('kpi-form-error');
  const btn = document.getElementById('kpi-submit-btn');
  errorBox.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Guardando...';

  const payload = {
    shift_id:        SHIFT_ID,
    units_produced:  parseInt(form.units_produced.value),
    units_rejected:  parseInt(form.units_rejected.value),
    downtime_minutes: parseFloat(form.downtime_minutes.value),
    line_speed:      parseFloat(form.line_speed.value),
    target_units:    parseInt(form.target_units.value),
    nominal_speed:   parseFloat(form.nominal_speed.value),
    planned_time_min: 480.0,
  };

  try {
    const res = await fetch('/api/kpis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      errorBox.textContent = data.error || 'Error al guardar la lectura';
      errorBox.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Guardar lectura';
      return;
    }
    // Actualizar dashboard inmediatamente
    await fetchKpis(SHIFT_ID);
    toggleKpiForm();
    form.reset();
    form.target_units.value = '9600';
    form.nominal_speed.value = '1200';
  } catch {
    errorBox.textContent = 'Error de conexión. Inténtalo de nuevo.';
    errorBox.style.display = 'block';
  }
  btn.disabled = false;
  btn.textContent = 'Guardar lectura';
}

// ── Supervisor: todas las líneas ───────────────────────────

function initSupervisorDashboard() {
  const cards = document.querySelectorAll('[data-shift]');
  cards.forEach(card => {
    const shiftId = parseInt(card.dataset.shift);
    const lineNum  = parseInt(card.dataset.line);
    pollSupervisorLine(shiftId, lineNum);
    setInterval(() => pollSupervisorLine(shiftId, lineNum), 30000);
  });
}

async function pollSupervisorLine(shiftId, lineNum) {
  try {
    const res = await fetch(`/api/kpis/${shiftId}/aggregate`);
    const kpi = await res.json();
    setText(`sv-oee-${lineNum}`,    formatPct(kpi.oee) + '%');
    setText(`sv-units-${lineNum}`,  formatNumber(kpi.total_units_produced));
    setText(`sv-reject-${lineNum}`, formatPct(kpi.reject_rate_pct) + '%');
  } catch { /* silencioso */ }
}
