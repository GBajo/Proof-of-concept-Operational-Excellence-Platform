// assistant.js — Integración del asistente IA en el turno activo

// ── Estado ───────────────────────────────────────────────────
const assistantState = {
  pendingCommentId: null,
  modalOpen: false,
};

// ── Modo automático: llamado desde voice.js tras guardar comentario ──

async function triggerAutoSuggest(comment) {
  const cardEl = document.getElementById('comment-' + comment.id);
  if (!cardEl) return;

  // Añadir zona de sugerencia con spinner al DOM del comentario
  const suggZone = document.createElement('div');
  suggZone.className = 'ai-suggestion ai-suggestion--loading';
  suggZone.id = 'sugg-' + comment.id;
  suggZone.innerHTML =
    '<span class="ai-suggestion__spinner"></span>' +
    '<span class="ai-suggestion__status">Consultando documentación...</span>';
  cardEl.appendChild(suggZone);

  try {
    const res = await fetch('/api/assistant/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shift_id:   SHIFT_ID,
        comment_id: comment.id,
        query:      comment.text,
        category:   comment.category,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error del asistente');
    renderSuggestionInCard(suggZone, data);
  } catch (err) {
    suggZone.innerHTML =
      '<span class="ai-suggestion__error">⚠ Asistente no disponible: ' +
      escapeHtml(err.message) + '</span>';
    suggZone.classList.remove('ai-suggestion--loading');
    suggZone.classList.add('ai-suggestion--error');
  }
}

function renderSuggestionInCard(container, suggestion) {
  const isMock   = suggestion.source === 'mock';
  const sources  = (suggestion.sources || []).join(', ') || 'sin fuente';
  const sourceTag = suggestion.sources && suggestion.sources.length
    ? '<div class="ai-suggestion__source">📄 ' + escapeHtml(sources) + '</div>'
    : '';

  container.className = 'ai-suggestion' + (isMock ? ' ai-suggestion--mock' : '');
  container.innerHTML =
    '<div class="ai-suggestion__header">' +
      '<span class="ai-suggestion__icon">🤖</span>' +
      '<span class="ai-suggestion__label">' +
        (isMock ? 'Asistente (modo demo)' : 'Asistente IA') +
      '</span>' +
    '</div>' +
    '<div class="ai-suggestion__text">' + escapeHtml(suggestion.text) + '</div>' +
    sourceTag +
    '<div class="ai-suggestion__feedback" id="fb-' + suggestion.id + '">' +
      '<span class="ai-suggestion__feedback-label">¿Fue útil?</span>' +
      '<button class="ai-fb-btn ai-fb-btn--yes" ' +
              'onclick="sendFeedback(' + suggestion.id + ',\'useful\',this)">👍 Útil</button>' +
      '<button class="ai-fb-btn ai-fb-btn--no" ' +
              'onclick="sendFeedback(' + suggestion.id + ',\'not_useful\',this)">👎 No útil</button>' +
    '</div>';
}

// ── Feedback ─────────────────────────────────────────────────

async function sendFeedback(suggestionId, value, btnEl) {
  const fbZone = document.getElementById('fb-' + suggestionId);
  try {
    await fetch('/api/assistant/feedback/' + suggestionId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback: value }),
    });
    if (fbZone) {
      fbZone.innerHTML =
        '<span class="ai-suggestion__feedback-done">' +
        (value === 'useful' ? '👍 Gracias por tu valoración' : '👎 Gracias, lo tendremos en cuenta') +
        '</span>';
    }
  } catch {
    if (btnEl) btnEl.disabled = true;
  }
}

// ── Modo manual: modal ────────────────────────────────────────

function openAssistantModal() {
  const modal = document.getElementById('assistant-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  assistantState.modalOpen = true;
  const input = document.getElementById('assistant-modal-input');
  if (input) { input.value = ''; input.focus(); }
  const respEl = document.getElementById('assistant-modal-response');
  if (respEl) respEl.style.display = 'none';
  const catEl = document.getElementById('assistant-modal-category');
  if (catEl) catEl.value = typeof selectedCategory !== 'undefined' ? selectedCategory : 'production';
}

function closeAssistantModal() {
  const modal = document.getElementById('assistant-modal');
  if (modal) modal.style.display = 'none';
  assistantState.modalOpen = false;
}

async function submitAssistantModal() {
  const input  = document.getElementById('assistant-modal-input');
  const catEl  = document.getElementById('assistant-modal-category');
  const respEl = document.getElementById('assistant-modal-response');
  const btn    = document.getElementById('assistant-modal-btn');

  const query    = input ? input.value.trim() : '';
  const category = catEl ? catEl.value : 'production';

  if (!query) {
    if (input) input.focus();
    return;
  }

  btn.disabled    = true;
  btn.textContent = 'Consultando...';
  if (respEl) {
    respEl.style.display = '';
    respEl.innerHTML =
      '<div class="ai-suggestion ai-suggestion--loading">' +
        '<span class="ai-suggestion__spinner"></span>' +
        '<span class="ai-suggestion__status">Consultando documentación...</span>' +
      '</div>';
  }

  try {
    const res = await fetch('/api/assistant/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shift_id: SHIFT_ID,
        query,
        category,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error del asistente');

    if (respEl) {
      const zone = document.createElement('div');
      renderSuggestionInCard(zone, data);
      respEl.innerHTML = '';
      respEl.appendChild(zone);
    }
  } catch (err) {
    if (respEl) {
      respEl.innerHTML =
        '<div class="ai-suggestion ai-suggestion--error">' +
          '<span class="ai-suggestion__error">⚠ ' + escapeHtml(err.message) + '</span>' +
        '</div>';
    }
  }

  btn.disabled    = false;
  btn.textContent = 'Consultar asistente';
}

// Cerrar modal al pulsar fuera
document.addEventListener('click', (e) => {
  const modal = document.getElementById('assistant-modal');
  if (modal && e.target === modal) closeAssistantModal();
});

// Cerrar modal con Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && assistantState.modalOpen) closeAssistantModal();
});
