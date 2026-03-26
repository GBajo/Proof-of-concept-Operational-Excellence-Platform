// Gestión de turnos: formulario inicio y formulario fin

document.addEventListener('DOMContentLoaded', () => {
  const startForm = document.getElementById('start-shift-form');
  if (startForm) startForm.addEventListener('submit', handleStartShift);

  const endForm = document.getElementById('end-shift-form');
  if (endForm) endForm.addEventListener('submit', handleEndShift);
});

async function handleStartShift(e) {
  e.preventDefault();
  const form = e.target;
  const errorBox = document.getElementById('form-error');
  errorBox.style.display = 'none';

  const payload = {
    operator_id: parseInt(form.operator_id.value),
    line_number: parseInt(form.line_number.value),
    shift_type: form.shift_type.value,
  };

  try {
    const res = await fetch('/api/shifts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      errorBox.textContent = data.error || 'Error al iniciar turno';
      errorBox.style.display = 'block';
      return;
    }
    window.location.href = `/shift/${data.id}/active`;
  } catch {
    errorBox.textContent = 'Error de conexión. Inténtalo de nuevo.';
    errorBox.style.display = 'block';
  }
}

async function handleEndShift(e) {
  e.preventDefault();
  const form = e.target;
  const shiftId = form.dataset.shiftId;
  const errorBox = document.getElementById('form-error');
  errorBox.style.display = 'none';

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
      errorBox.textContent = data.error || 'Error al cerrar turno';
      errorBox.style.display = 'block';
      return;
    }
    window.location.href = `/shift/${shiftId}/summary`;
  } catch {
    errorBox.textContent = 'Error de conexión. Inténtalo de nuevo.';
    errorBox.style.display = 'block';
  }
}

async function endShift() {
  if (!confirm('¿Seguro que quieres finalizar este turno?')) return;
  window.location.href = `/shift/${SHIFT_ID}/end`;
}
