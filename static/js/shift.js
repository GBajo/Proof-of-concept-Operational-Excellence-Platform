// Gestión de turnos: formulario inicio y formulario fin

document.addEventListener('DOMContentLoaded', () => {
  const startForm = document.getElementById('start-shift-form');
  if (startForm) {
    startForm.addEventListener('submit', handleStartShift);
    initStartScreen();
  }

  const endForm = document.getElementById('end-shift-form');
  if (endForm) endForm.addEventListener('submit', handleEndShift);
});

// ── Pantalla de inicio de turno ────────────────────────────────────

function initStartScreen() {
  startLiveClock();
  loadLineStatus();
}

function startLiveClock() {
  const el = document.getElementById('live-clock');
  if (!el) return;
  const tick = () => {
    el.textContent = new Date().toLocaleTimeString(
      document.documentElement.lang === 'en' ? 'en-US' : 'es-ES',
      { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }
    );
  };
  tick();
  setInterval(tick, 1000);
}

async function loadLineStatus() {
  let active = 0;
  const lineCards = document.querySelectorAll('#line-grid .line-card');
  const total = lineCards.length;

  for (let line = 1; line <= total; line++) {
    try {
      const res = await fetch(`/api/shifts/active?line=${line}`);
      const card = document.getElementById(`line-card-${line}`);
      const statusEl = document.getElementById(`line-status-${line}`);
      const input = card ? card.querySelector('input[type="radio"]') : null;

      if (res.ok) {
        // Línea ocupada
        const data = await res.json();
        active++;
        if (statusEl) {
          statusEl.innerHTML =
            '<span class="line-dot line-dot--occupied"></span>' +
            `<span class="line-status-text" style="color:#c0392b">${(typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.occupied : 'OCUPADA')}</span>`;
        }
        if (card) card.classList.add('line-card--occupied');
        if (input) input.disabled = true;

        // Añadir a la lista del aside
        const occupiedList = document.getElementById('occupied-list');
        const infoPanel = document.getElementById('active-lines-info');
        if (occupiedList) {
          const li = document.createElement('li');
          const lbl = typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.lineLabel : 'Línea';
          const op  = typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.activeOperator : 'Operario activo';
          li.textContent = `${lbl} ${line} — ${data.operator_name || op}`;
          occupiedList.appendChild(li);
        }
        if (infoPanel) infoPanel.style.display = '';
      } else {
        // Línea libre
        if (statusEl) {
          statusEl.innerHTML =
            '<span class="line-dot line-dot--free"></span>' +
            `<span class="line-status-text" style="color:#27ae60">${(typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.free : 'LIBRE')}</span>`;
        }
      }
    } catch {
      const statusEl = document.getElementById(`line-status-${line}`);
      if (statusEl) {
        statusEl.innerHTML =
          '<span class="line-dot" style="background:#a0aab4"></span>' +
          '<span class="line-status-text">—</span>';
      }
    }
  }

  // Actualizar estadísticas del aside
  const statActive = document.getElementById('stat-active');
  const statFree = document.getElementById('stat-free');
  if (statActive) statActive.textContent = active;
  if (statFree) statFree.textContent = total - active;
}

async function handleStartShift(e) {
  e.preventDefault();
  const form = e.target;
  const errorBox = document.getElementById('form-error');
  errorBox.style.display = 'none';

  // Validación manual de radios (required no funciona con radio custom)
  const operatorSelect = form.querySelector('select[name="operator_id"]');
  const operatorId = operatorSelect ? operatorSelect.value : null;
  const lineNumber  = form.querySelector('input[name="line_number"]:checked');
  const shiftType   = form.querySelector('input[name="shift_type"]:checked');

  if (!operatorId) {
    showError(errorBox, typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.errSelectOp : 'Por favor, seleccione un operario.');
    return;
  }
  if (!lineNumber) {
    showError(errorBox, typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.errSelectLine : 'Por favor, seleccione una línea de packaging.');
    return;
  }

  const submitBtn = form.querySelector('button[type="submit"]');
  const origText  = submitBtn.innerHTML;
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span class="btn-icon">⏳</span> ${typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.btnStarting : 'Iniciando…'}`;

  const payload = {
    operator_id: parseInt(operatorId),
    line_number:  parseInt(lineNumber.value),
    shift_type:   shiftType ? shiftType.value : 'morning',
  };

  try {
    const res = await fetch('/api/shifts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      showError(errorBox, data.error || (typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.errStartShift : 'Error al iniciar turno.'));
      submitBtn.disabled = false;
      submitBtn.innerHTML = origText;
      return;
    }
    window.location.href = `/shift/${data.id}/active`;
  } catch {
    showError(errorBox, typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.errConnection : 'Error de conexión. Inténtalo de nuevo.');
    submitBtn.disabled = false;
    submitBtn.innerHTML = origText;
  }
}

function showError(box, msg) {
  box.textContent = msg;
  box.style.display = 'block';
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function handleEndShift(e) {
  e.preventDefault();
  const form = e.target;
  const shiftId = form.dataset.shiftId;
  const errorBox = document.getElementById('form-error');
  errorBox.style.display = 'none';

  const submitBtn = document.getElementById('end-btn');
  const origHTML = submitBtn ? submitBtn.innerHTML : '';
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.btnClosingShift : 'Cerrando turno...';
  }

  const status = form.querySelector('input[name="status"]:checked').value;
  const payload = {
    status,
    handover_notes: form.handover_notes.value.trim() || null,
  };

  try {
    const res = await fetch(`/api/shifts/${shiftId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = origHTML; }
      errorBox.textContent = data.error || (typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.errCloseShift : 'Error al cerrar turno');
      errorBox.style.display = 'block';
      return;
    }
    window.location.href = `/shift/${shiftId}/summary`;
  } catch {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = origHTML; }
    errorBox.textContent = typeof SHIFT_I18N !== 'undefined' ? SHIFT_I18N.errConnection : 'Error de conexión. Inténtalo de nuevo.';
    errorBox.style.display = 'block';
  }
}

async function endShift() {
  if (!confirm('¿Seguro que quieres finalizar este turno?')) return;
  window.location.href = `/shift/${SHIFT_ID}/end`;
}
