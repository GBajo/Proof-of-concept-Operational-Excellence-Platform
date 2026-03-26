// Web Speech API — grabación de voz y gestión de comentarios

let recognition = null;
let isRecording = false;
let selectedCategory = 'production';
// Almacena todos los comentarios cargados para filtrado local
let allComments = [];

// ── Estados del grabador ───────────────────────────────────

function showState(stateId) {
  ['recorder-idle', 'recorder-active', 'recorder-confirm', 'recorder-error']
    .forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = (id === stateId) ? '' : 'none';
    });
}

// ── Inicio de grabación ────────────────────────────────────

function startRecording() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showMicError('Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.');
    return;
  }

  // Si ya hay una sesión abierta, pararla antes de crear otra
  if (recognition) {
    recognition.abort();
    recognition = null;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'es-ES';
  recognition.continuous = true;   // captura frases largas
  recognition.interimResults = true;

  let finalTranscript = '';

  recognition.onstart = () => {
    isRecording = true;
    finalTranscript = '';
    showState('recorder-active');
    setInterim('');
    setRecLabel('Escuchando...');
  };

  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) {
        finalTranscript += result[0].transcript + ' ';
      } else {
        interim += result[0].transcript;
      }
    }
    // Muestra texto acumulado + lo provisional en tiempo real
    setInterim((finalTranscript + interim).trim());
  };

  recognition.onend = () => {
    isRecording = false;
    recognition = null;
    const text = finalTranscript.trim();
    if (text) {
      openConfirm(text, 'voice');
    } else {
      // Nada capturado: volver al idle
      showState('recorder-idle');
    }
  };

  recognition.onerror = (event) => {
    isRecording = false;
    recognition = null;
    const msgs = {
      'not-allowed': 'Permiso de micrófono denegado. Actívalo en la configuración del navegador.',
      'no-speech':   'No se detectó voz. Intenta de nuevo.',
      'network':     'Error de red al procesar el audio.',
      'aborted':     null,  // cancelado manualmente, no mostrar error
    };
    const msg = msgs[event.error];
    if (msg !== undefined) {
      if (msg) showMicError(msg);
      else showState('recorder-idle');
    } else {
      showMicError('Error de reconocimiento: ' + event.error);
    }
  };

  recognition.start();
}

// ── Detener grabación manualmente ──────────────────────────

function stopRecording() {
  if (recognition) {
    recognition.stop();   // dispara onend → abre confirm si hay texto
  }
}

// ── Entrada manual (sin voz) ───────────────────────────────

function openManualEntry() {
  openConfirm('', 'manual');
  const ta = document.getElementById('transcript-text');
  if (ta) {
    ta.dataset.source = 'manual';
    setTimeout(() => ta.focus(), 50);
  }
}

// ── Mostrar panel de confirmación ─────────────────────────

function openConfirm(text, source) {
  showState('recorder-confirm');
  const ta = document.getElementById('transcript-text');
  if (ta) {
    ta.value = text;
    ta.dataset.source = source;
  }
  setCategory(selectedCategory);
  const errEl = document.getElementById('save-error');
  if (errEl) errEl.style.display = 'none';
  const btn = document.getElementById('btn-save');
  if (btn) { btn.disabled = false; btn.textContent = 'Guardar comentario'; }
}

// ── Selección de categoría ─────────────────────────────────

function selectCategory(btn) {
  setCategory(btn.dataset.cat);
}

function setCategory(cat) {
  selectedCategory = cat;
  document.querySelectorAll('#cat-picker .cat-btn').forEach(b => {
    b.classList.toggle('cat-btn--active', b.dataset.cat === cat);
  });
}

// ── Guardar comentario ─────────────────────────────────────

async function submitComment() {
  const ta = document.getElementById('transcript-text');
  const text = ta ? ta.value.trim() : '';

  if (!text) {
    if (ta) {
      ta.classList.add('voice-transcript-area--error');
      ta.focus();
      setTimeout(() => ta.classList.remove('voice-transcript-area--error'), 1500);
    }
    return;
  }

  const btn = document.getElementById('btn-save');
  if (btn) { btn.disabled = true; btn.textContent = 'Guardando...'; }

  const source = (ta && ta.dataset.source === 'manual') ? 'manual' : 'voice';

  const payload = {
    shift_id:    SHIFT_ID,
    operator_id: OPERATOR_ID,
    text,
    category:    selectedCategory,
    source,
  };

  try {
    const res = await fetch('/api/comments', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Error al guardar');
    }
    const comment = await res.json();
    addCommentToList(comment);
    cancelComment();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Guardar comentario'; }
    showSaveError(err.message);
  }
}

function showSaveError(msg) {
  let el = document.getElementById('save-error');
  if (!el) {
    el = document.createElement('p');
    el.id = 'save-error';
    el.className = 'rec-save-error';
    const confirm = document.getElementById('recorder-confirm');
    if (confirm) confirm.appendChild(el);
  }
  el.textContent = '\u26a0 ' + msg;
  el.style.display = '';
}

// ── Cancelar ───────────────────────────────────────────────

function cancelComment() {
  if (recognition) { recognition.abort(); recognition = null; }
  isRecording = false;
  showState('recorder-idle');
  const ta = document.getElementById('transcript-text');
  if (ta) { ta.value = ''; delete ta.dataset.source; }
  const errEl = document.getElementById('save-error');
  if (errEl) errEl.style.display = 'none';
}

// ── Error de micrófono ─────────────────────────────────────

function showMicError(msg) {
  const el = document.getElementById('recorder-error-msg');
  if (el) el.textContent = msg;
  showState('recorder-error');
}

function dismissError() {
  showState('recorder-idle');
}

// ── Helpers de UI durante grabación ───────────────────────

function setInterim(text) {
  const el = document.getElementById('transcript-interim');
  if (!el) return;
  if (text) {
    el.textContent = text;
    el.classList.remove('rec-interim--empty');
  } else {
    el.innerHTML = '<em>Di tu comentario en voz alta...</em>';
    el.classList.add('rec-interim--empty');
  }
}

function setRecLabel(msg) {
  const el = document.getElementById('rec-label');
  if (el) el.textContent = msg;
}

// ── Gestión de la lista de comentarios ────────────────────

function addCommentToList(comment) {
  allComments.unshift(comment);
  updateCommentCount(allComments.length);
  const filter = document.getElementById('filter-category');
  renderComments(filter ? filter.value : '');
}

function renderComments(filterCat) {
  const list = document.getElementById('comments-list');
  const empty = document.getElementById('comments-empty');
  if (!list) return;

  const filtered = filterCat
    ? allComments.filter(c => c.category === filterCat)
    : allComments;

  // Limpiar entradas previas (conservar el div de empty)
  list.querySelectorAll('.comment-entry').forEach(el => el.remove());

  if (filtered.length === 0) {
    if (empty) empty.style.display = '';
    return;
  }
  if (empty) empty.style.display = 'none';

  filtered.forEach(c => list.appendChild(buildCommentElement(c)));
}

function filterComments(cat) {
  renderComments(cat);
}

function buildCommentElement(comment) {
  const div = document.createElement('div');
  div.className = 'comment-entry comment-entry--in';
  div.id = 'comment-' + comment.id;
  const cat = comment.category || 'production';
  div.innerHTML =
    '<div class="comment-entry__meta">' +
      '<span class="badge ' + categoryBadgeClass(cat) + '">' + categoryLabel(cat) + '</span>' +
      '<span class="comment-entry__time">' + isoToTime(comment.timestamp) + '</span>' +
      (comment.source === 'voice'
        ? '<span class="comment-entry__src" title="Capturado por voz">🎤</span>'
        : '<span class="comment-entry__src" title="Escrito manualmente">✏️</span>') +
    '</div>' +
    '<div class="comment-entry__text">' + escapeHtml(comment.text) + '</div>';
  return div;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function updateCommentCount(total) {
  const badge = document.getElementById('comments-count');
  if (badge) badge.textContent = total;
}

// ── Carga inicial (llamada desde dashboard.js) ─────────────

function loadComments(comments) {
  // La API devuelve orden ASC; queremos más recientes arriba
  allComments = comments.slice().reverse();
  updateCommentCount(allComments.length);
  renderComments('');
  if (comments.length > 0 && typeof dashboardState !== 'undefined') {
    dashboardState.lastCommentId = Math.max(...comments.map(c => c.id));
  }
}

// Llamada por el polling de dashboard.js al recibir comentarios nuevos
function onNewComments(newComments) {
  newComments.forEach(c => allComments.unshift(c));
  updateCommentCount(allComments.length);
  const filter = document.getElementById('filter-category');
  renderComments(filter ? filter.value : '');
}
