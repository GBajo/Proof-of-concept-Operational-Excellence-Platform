// PollManager: actualización periódica del dashboard

let oeeChart = null;
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

async function loadInitialComments() {
  try {
    const res = await fetch(`/api/comments/${SHIFT_ID}`);
    const comments = await res.json();
    const list = document.getElementById('comments-list');
    list.innerHTML = '';
    comments.forEach(c => {
      if (c.id > dashboardState.lastCommentId) dashboardState.lastCommentId = c.id;
      list.appendChild(buildCommentElement(c));
    });
    const badge = document.getElementById('comments-count');
    if (badge) badge.textContent = comments.length;
  } catch { /* silencioso */ }
}

const PollManager = {
  start(shiftId) {
    this.stop();
    dashboardState.intervals = [
      setInterval(() => fetchKpis(shiftId), 15000),
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
  resume(shiftId) { this.start(shiftId); fetchKpis(shiftId); },
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
    const list = document.getElementById('comments-list');
    let added = 0;
    comments
      .filter(c => c.id > dashboardState.lastCommentId)
      .forEach(c => {
        dashboardState.lastCommentId = Math.max(dashboardState.lastCommentId, c.id);
        list.prepend(buildCommentElement(c));
        added++;
      });
    if (added > 0) updateCommentCount(added);
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
  setText('kpi-oee', formatPct(oee.oee));
  setText('kpi-units', formatNumber(oee.total_units_produced));
  setText('kpi-speed', formatNumber(raw.line_speed));
  setText('kpi-reject', formatPct(oee.reject_rate_pct));
  setText('kpi-downtime', oee.total_downtime_minutes != null ? oee.total_downtime_minutes : '—');
  setText('kpi-rft', formatPct(oee.right_first_time_pct));

  const targetEl = document.getElementById('kpi-units-target');
  if (targetEl && raw.target_units) {
    targetEl.textContent = `objetivo: ${formatNumber(raw.target_units)}`;
  }

  if (oeeChart) {
    const now = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    oeeChart.data.labels.push(now);
    oeeChart.data.datasets[0].data.push(oee.oee || 0);
    if (oeeChart.data.labels.length > 30) {
      oeeChart.data.labels.shift();
      oeeChart.data.datasets[0].data.shift();
    }
    oeeChart.update('none');
  }
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function showBanner() {
  const b = document.getElementById('connection-banner');
  if (b) b.style.display = 'block';
}
function hideBanner() {
  const b = document.getElementById('connection-banner');
  if (b) b.style.display = 'none';
}

// ── Supervisor: todas las líneas ───────────────────────────

function initSupervisorDashboard() {
  const cards = document.querySelectorAll('[data-shift]');
  cards.forEach(card => {
    const shiftId = parseInt(card.dataset.shift);
    const lineNum = parseInt(card.dataset.line);
    pollSupervisorLine(shiftId, lineNum);
    setInterval(() => pollSupervisorLine(shiftId, lineNum), 15000);
  });
}

async function pollSupervisorLine(shiftId, lineNum) {
  try {
    const res = await fetch(`/api/kpis/${shiftId}/aggregate`);
    const kpi = await res.json();
    setText(`sv-oee-${lineNum}`, formatPct(kpi.oee) + '%');
    setText(`sv-units-${lineNum}`, formatNumber(kpi.total_units_produced));
    setText(`sv-reject-${lineNum}`, formatPct(kpi.reject_rate_pct) + '%');
  } catch { /* silencioso */ }
}
