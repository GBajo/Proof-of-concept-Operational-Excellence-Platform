// Web Speech API: grabación de voz y envío de comentarios

let recognition = null;
let isRecording = false;

function toggleRecording() {
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
}

function startRecording() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert('Tu navegador no soporta reconocimiento de voz. Usa Chrome.');
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'es-ES';
  recognition.continuous = false;
  recognition.interimResults = true;

  const btn = document.getElementById('btn-voice');
  const transcriptBox = document.getElementById('voice-transcript');
  const textArea = document.getElementById('transcript-text');

  recognition.onstart = () => {
    isRecording = true;
    btn.classList.add('voice-btn--recording');
    btn.querySelector('.voice-btn__label').textContent = 'Escuchando... (pulsa para parar)';
    transcriptBox.style.display = 'flex';
    textArea.value = '';
  };

  recognition.onresult = (event) => {
    let transcript = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }
    textArea.value = transcript;
  };

  recognition.onend = () => {
    isRecording = false;
    btn.classList.remove('voice-btn--recording');
    btn.querySelector('.voice-btn__label').textContent = 'Grabar comentario';
  };

  recognition.onerror = (event) => {
    console.error('Error de reconocimiento:', event.error);
    stopRecording();
  };

  recognition.start();
}

function stopRecording() {
  if (recognition) {
    recognition.stop();
    recognition = null;
  }
  isRecording = false;
}

async function submitComment() {
  const text = document.getElementById('transcript-text').value.trim();
  const category = document.getElementById('comment-category').value;

  if (!text) {
    alert('El comentario no puede estar vacío.');
    return;
  }

  const payload = {
    shift_id: SHIFT_ID,
    operator_id: OPERATOR_ID,
    text,
    category,
    source: 'voice',
  };

  try {
    const res = await fetch('/api/comments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Error al guardar');

    const comment = await res.json();
    prependComment(comment);
    cancelComment();
    updateCommentCount(1);
  } catch (err) {
    alert('No se pudo guardar el comentario: ' + err.message);
  }
}

function cancelComment() {
  document.getElementById('voice-transcript').style.display = 'none';
  document.getElementById('transcript-text').value = '';
  stopRecording();
}

function prependComment(comment) {
  const list = document.getElementById('comments-list');
  const el = buildCommentElement(comment);
  list.prepend(el);
}

function buildCommentElement(comment) {
  const div = document.createElement('div');
  div.className = 'comment-entry';
  div.id = `comment-${comment.id}`;
  const cat = comment.category || 'production';
  div.innerHTML = `
    <div class="comment-entry__meta">
      <span class="badge ${categoryBadgeClass(cat)}">${categoryLabel(cat)}</span>
      <span>${isoToTime(comment.timestamp)}</span>
      ${comment.source === 'voice' ? '<span>🎤</span>' : ''}
    </div>
    <div>${escapeHtml(comment.text)}</div>
  `;
  return div;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function updateCommentCount(delta) {
  const badge = document.getElementById('comments-count');
  if (badge) badge.textContent = (parseInt(badge.textContent) || 0) + delta;
}
