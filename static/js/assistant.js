// assistant.js — Integración del asistente IA y panel de agentes

// ── Utilidades ────────────────────────────────────────────────────────────────
// Definición local por si este script se carga sin voice.js
if (typeof escapeHtml === 'undefined') {
  // eslint-disable-next-line no-unused-vars
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}

// ── Estado ───────────────────────────────────────────────────────────────────
// SHIFT_ID may be defined by the host page (shift/active.html); fall back to null
if (typeof SHIFT_ID === 'undefined') { var SHIFT_ID = null; }
const assistantState = {
  pendingCommentId: null,
  modalOpen:        false,
  panelOpen:        false,
  agents:           [],      // [{name, description, category}]
  agentEnabled:     {},      // {name: bool} — toggle manual
  lastAgentsUsed:   [],      // agentes activados en la última consulta
  kaizenRunning:    false,
};

// ── Iconos por categoría de agente ───────────────────────────────────────────
const AGENT_ICONS = {
  production:    'bi-bar-chart-line',
  maintenance:   'bi-tools',
  documentation: 'bi-file-earmark-text',
  improvement:   'bi-lightbulb',
  general:       'bi-robot',
};
const AGENT_COLORS = {
  production:    '#0d6efd',
  maintenance:   '#fd7e14',
  documentation: '#6f42c1',
  improvement:   '#198754',
  general:       '#6c757d',
};

// ── Carga inicial de agentes ──────────────────────────────────────────────────

async function loadAgents() {
  try {
    const res = await fetch('/api/agents');
    if (!res.ok) return;
    const agents = await res.json();
    assistantState.agents = agents;
    // Todos habilitados por defecto
    agents.forEach(a => {
      if (assistantState.agentEnabled[a.name] === undefined)
        assistantState.agentEnabled[a.name] = true;
    });
    _renderAgentsList();
    _populateAgentSelector();
    _renderForceButtons();
  } catch (_) {}
}

// ── Render del panel ──────────────────────────────────────────────────────────

function _renderAgentsList() {
  const container = document.getElementById('agents-list');
  if (!container) return;

  if (!assistantState.agents.length) {
    container.innerHTML = '<div class="agents-panel__empty">Sin agentes registrados</div>';
    return;
  }

  container.innerHTML = assistantState.agents.map(agent => {
    const icon    = AGENT_ICONS[agent.category] || AGENT_ICONS.general;
    const color   = AGENT_COLORS[agent.category] || AGENT_COLORS.general;
    const enabled = assistantState.agentEnabled[agent.name] !== false;
    const active  = assistantState.lastAgentsUsed.includes(agent.name);
    return `
      <div class="agent-card ${active ? 'agent-card--active' : ''} ${!enabled ? 'agent-card--disabled' : ''}"
           id="agent-card-${agent.name}">
        <div class="agent-card__icon" style="color:${color}">
          <i class="bi ${icon}"></i>
        </div>
        <div class="agent-card__info">
          <div class="agent-card__name">${escapeHtml(agent.name.replace('_', ' '))}</div>
          <div class="agent-card__status" id="agent-status-${agent.name}">
            ${active ? '<span class="agent-status--working">● Activo</span>'
                     : '<span class="agent-status--idle">○ Inactivo</span>'}
          </div>
        </div>
        <div class="agent-card__toggle">
          <div class="form-check form-switch mb-0">
            <input class="form-check-input" type="checkbox"
                   id="toggle-${agent.name}"
                   ${enabled ? 'checked' : ''}
                   onchange="toggleAgent('${agent.name}', this.checked)"
                   title="Activar/desactivar ${agent.name}">
          </div>
        </div>
      </div>`;
  }).join('');
}

function _populateAgentSelector() {
  const sel = document.getElementById('assistant-modal-agent');
  if (!sel) return;
  // Mantener la opción "Orquestador"
  sel.innerHTML = '<option value="">🔀 Orquestador (automático)</option>';
  assistantState.agents.forEach(a => {
    if (assistantState.agentEnabled[a.name] !== false) {
      const icon = { production:'📊', maintenance:'🔧', documentation:'📄', improvement:'💡' }[a.category] || '🤖';
      const opt = document.createElement('option');
      opt.value = a.name;
      opt.textContent = `${icon} ${a.name.replace('_', ' ')}`;
      sel.appendChild(opt);
    }
  });
}

function _renderForceButtons() {
  const section = document.getElementById('agents-force-section');
  const btns    = document.getElementById('agents-force-buttons');
  if (!section || !btns) return;

  const enabled = assistantState.agents.filter(a => assistantState.agentEnabled[a.name] !== false);
  if (!enabled.length) { section.style.display = 'none'; return; }

  section.style.display = '';
  btns.innerHTML = enabled.map(a => {
    const icon  = AGENT_ICONS[a.category] || AGENT_ICONS.general;
    const color = AGENT_COLORS[a.category] || AGENT_COLORS.general;
    return `<button class="btn btn-sm agent-force-btn"
                    style="border-color:${color};color:${color}"
                    onclick="openAssistantModalWithAgent('${a.name}')">
              <i class="bi ${icon} me-1"></i>${a.name.replace('_', ' ')}
            </button>`;
  }).join('');
}

// ── Estado working de cada agente ─────────────────────────────────────────────

function _setAgentsWorking(names) {
  assistantState.agents.forEach(a => {
    const card      = document.getElementById('agent-card-' + a.name);
    const statusEl  = document.getElementById('agent-status-' + a.name);
    const working   = names.includes(a.name);
    if (card) {
      card.classList.toggle('agent-card--active', working);
      card.classList.toggle('agent-card--working', working);
    }
    if (statusEl) {
      statusEl.innerHTML = working
        ? '<span class="agent-status--working"><span class="ai-suggestion__spinner"></span> Trabajando...</span>'
        : '<span class="agent-status--idle">○ Inactivo</span>';
    }
  });
}

function _setAgentsDone(namesUsed) {
  assistantState.lastAgentsUsed = namesUsed;
  _renderAgentsList();

  // Actualizar "última activación"
  const lastRun  = document.getElementById('agents-last-run');
  const lastList = document.getElementById('agents-last-run-list');
  if (lastRun && lastList) {
    if (namesUsed.length) {
      lastRun.style.display = '';
      lastList.innerHTML = namesUsed.map(n => {
        const a    = assistantState.agents.find(x => x.name === n) || { category: 'general' };
        const icon = AGENT_ICONS[a.category] || AGENT_ICONS.general;
        const col  = AGENT_COLORS[a.category] || AGENT_COLORS.general;
        return `<span class="agent-used-badge" style="border-color:${col};color:${col}">
                  <i class="bi ${icon} me-1"></i>${n.replace('_', ' ')}
                </span>`;
      }).join('');
    } else {
      lastRun.style.display = 'none';
    }
  }
}

// ── Toggle de agentes ─────────────────────────────────────────────────────────

function toggleAgent(name, enabled) {
  assistantState.agentEnabled[name] = enabled;
  const card = document.getElementById('agent-card-' + name);
  if (card) card.classList.toggle('agent-card--disabled', !enabled);
  _populateAgentSelector();
  _renderForceButtons();
}

// ── Panel sidebar ─────────────────────────────────────────────────────────────

function toggleAgentsPanel() {
  const panel = document.getElementById('agents-panel');
  if (!panel) return;
  assistantState.panelOpen = !assistantState.panelOpen;
  panel.style.display = assistantState.panelOpen ? 'flex' : 'none';
  if (assistantState.panelOpen && !assistantState.agents.length) loadAgents();
}

// ── Modo automático: llamado desde voice.js tras guardar comentario ───────────

async function triggerAutoSuggest(comment) {
  const cardEl = document.getElementById('comment-' + comment.id);
  if (!cardEl) return;

  const suggZone = document.createElement('div');
  suggZone.className = 'ai-suggestion ai-suggestion--loading';
  suggZone.id = 'sugg-' + comment.id;
  suggZone.innerHTML =
    '<span class="ai-suggestion__spinner"></span>' +
    '<span class="ai-suggestion__status">Consultando agentes...</span>';
  cardEl.appendChild(suggZone);

  // Activar indicador visual de todos los agentes
  _setAgentsWorking(assistantState.agents.map(a => a.name));

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
    _setAgentsDone(data.agents_used || []);
    renderSuggestionInCard(suggZone, data);
  } catch (err) {
    _setAgentsDone([]);
    suggZone.innerHTML =
      '<span class="ai-suggestion__error">⚠ Asistente no disponible: ' +
      escapeHtml(err.message) + '</span>';
    suggZone.classList.remove('ai-suggestion--loading');
    suggZone.classList.add('ai-suggestion--error');
  }
}

// ── Render de sugerencia ──────────────────────────────────────────────────────

/**
 * Separa un texto que puede contener bloques ```echarts {...}``` en partes:
 * [{type:'text',content:'...'}, {type:'echarts',content:{...}}, ...]
 */
function _parseResponseParts(text) {
  const parts = [];
  const regex = /```echarts\s*([\s\S]*?)```/g;
  let lastIndex = 0, match;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex)
      parts.push({ type: 'text', content: text.slice(lastIndex, match.index) });
    try {
      parts.push({ type: 'echarts', content: JSON.parse(match[1].trim()) });
    } catch (_) {
      parts.push({ type: 'text', content: match[0] }); // devolver raw si JSON inválido
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length)
    parts.push({ type: 'text', content: text.slice(lastIndex) });
  return parts;
}

/** Renderiza un bloque echarts en un div y lo añade al container. */
function _renderEchartsBlock(option, container) {
  if (typeof echarts === 'undefined') return; // CDN no cargado
  const chartDiv = document.createElement('div');
  chartDiv.className = 'ai-suggestion__chart';
  chartDiv.style.cssText = 'width:100%;height:240px;margin-top:0.75rem;border-radius:0.4rem;overflow:hidden;';
  container.appendChild(chartDiv);
  try {
    // Tema oscuro para integrarse con el panel
    const chart = echarts.init(chartDiv, 'dark', { renderer: 'canvas' });
    chart.setOption(option);
    // Responsive
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(chartDiv);
  } catch (_) {}
}

function renderSuggestionInCard(container, suggestion) {
  const isMock      = suggestion.source === 'mock';
  const sources     = (suggestion.sources || []).join(', ') || '';
  const agentsUsed  = suggestion.agents_used || [];
  const sourceTag   = sources
    ? `<div class="ai-suggestion__source">📄 ${escapeHtml(sources)}</div>` : '';
  const agentsTag   = agentsUsed.length
    ? `<div class="ai-suggestion__agents">🤖 ${agentsUsed.map(n =>
        `<span class="agent-used-chip">${escapeHtml(n.replace('_',' '))}</span>`).join('')}</div>` : '';

  container.className = 'ai-suggestion' + (isMock ? ' ai-suggestion--mock' : '');

  // Parsear el texto en partes texto + echarts
  const parts = _parseResponseParts(suggestion.text || '');
  const hasCharts = parts.some(p => p.type === 'echarts');

  // Construir HTML para las partes de texto (los charts se añaden vía DOM después)
  const textHtml = parts
    .filter(p => p.type === 'text')
    .map(p => escapeHtml(p.content))
    .join('');

  container.innerHTML =
    '<div class="ai-suggestion__header">' +
      '<span class="ai-suggestion__icon">🤖</span>' +
      '<span class="ai-suggestion__label">' +
        (isMock ? 'Asistente (modo demo)' : 'Asistente IA') +
      '</span>' +
    '</div>' +
    '<div class="ai-suggestion__text">' + textHtml + '</div>' +
    (hasCharts ? '<div class="ai-suggestion__charts-zone" id="charts-' + suggestion.id + '"></div>' : '') +
    sourceTag + agentsTag +
    '<div class="ai-suggestion__feedback" id="fb-' + suggestion.id + '">' +
      '<span class="ai-suggestion__feedback-label">¿Fue útil?</span>' +
      '<button class="ai-fb-btn ai-fb-btn--yes" ' +
              'onclick="sendFeedback(' + suggestion.id + ',\'useful\',this)">👍 Útil</button>' +
      '<button class="ai-fb-btn ai-fb-btn--no" ' +
              'onclick="sendFeedback(' + suggestion.id + ',\'not_useful\',this)">👎 No útil</button>' +
    '</div>';

  // Renderizar gráficos ECharts tras insertar el HTML
  if (hasCharts) {
    const chartsZone = document.getElementById('charts-' + suggestion.id);
    if (chartsZone) {
      parts.filter(p => p.type === 'echarts').forEach(p => {
        _renderEchartsBlock(p.content, chartsZone);
      });
    }
  }
}


// ── Feedback ──────────────────────────────────────────────────────────────────

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

// ── Modal: apertura ───────────────────────────────────────────────────────────

function openAssistantModal() {
  _openModal('');
}

function openAssistantModalWithAgent(agentName) {
  _openModal(agentName);
}

function _openModal(preselectedAgent) {
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

  const agentSel = document.getElementById('assistant-modal-agent');
  if (agentSel) agentSel.value = preselectedAgent || '';

  // Actualizar el título del modal si hay agente preseleccionado
  const title = modal.querySelector('.ai-modal__title');
  if (title) {
    title.textContent = preselectedAgent
      ? `Agente: ${preselectedAgent.replace('_', ' ')}`
      : 'Asistente IA';
  }
}

function closeAssistantModal() {
  const modal = document.getElementById('assistant-modal');
  if (modal) modal.style.display = 'none';
  assistantState.modalOpen = false;
}

// ── Modal: envío ──────────────────────────────────────────────────────────────

async function submitAssistantModal() {
  const input    = document.getElementById('assistant-modal-input');
  const catEl    = document.getElementById('assistant-modal-category');
  const agentSel = document.getElementById('assistant-modal-agent');
  const respEl   = document.getElementById('assistant-modal-response');
  const btn      = document.getElementById('assistant-modal-btn');

  const query      = input ? input.value.trim() : '';
  const category   = catEl ? catEl.value : 'production';
  const agentName  = agentSel ? agentSel.value : '';

  if (!query) { if (input) input.focus(); return; }

  btn.disabled    = true;
  btn.textContent = 'Consultando...';
  if (respEl) {
    respEl.style.display = '';
    respEl.innerHTML =
      '<div class="ai-suggestion ai-suggestion--loading">' +
        '<span class="ai-suggestion__spinner"></span>' +
        '<span class="ai-suggestion__status">Consultando ' +
          (agentName ? `agente ${agentName.replace('_',' ')}` : 'agentes') + '...</span>' +
      '</div>';
  }

  // Activar indicador visual
  if (agentName) {
    _setAgentsWorking([agentName]);
  } else {
    _setAgentsWorking(assistantState.agents.map(a => a.name));
  }

  try {
    let url = '/api/assistant/suggest';
    let body = { shift_id: SHIFT_ID, query, category };

    if (agentName) {
      url  = '/api/assistant/suggest-agent';
      body = { ...body, agent_name: agentName };
    }

    const res  = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Error del asistente');

    _setAgentsDone(data.agents_used || (agentName ? [agentName] : []));

    if (respEl) {
      const zone = document.createElement('div');
      renderSuggestionInCard(zone, data);
      respEl.innerHTML = '';
      respEl.appendChild(zone);
    }
  } catch (err) {
    _setAgentsDone([]);
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

// ── Kaizen: análisis diario ───────────────────────────────────────────────────

async function triggerKaizenAnalysis() {
  if (assistantState.kaizenRunning) return;
  assistantState.kaizenRunning = true;

  const btn    = document.getElementById('kaizen-btn');
  const status = document.getElementById('kaizen-status');

  if (btn)    { btn.disabled = true; btn.innerHTML = '<span class="ai-suggestion__spinner"></span> Analizando...'; }
  if (status) { status.style.display = ''; status.innerHTML = '<span class="ai-suggestion__status">Generando informe kaizen...</span>'; }

  const kaizenCard = document.getElementById('agent-card-kaizen');
  if (kaizenCard) kaizenCard.classList.add('agent-card--working');

  try {
    const res  = await fetch('/api/agents/kaizen-report', { method: 'POST' });
    const data = await res.json();
    if (res.status === 429) {
      if (status) status.innerHTML = `<span class="ai-suggestion__error">⏳ ${escapeHtml(data.error)}</span>`;
      return;
    }
    if (!res.ok) throw new Error(data.error || 'Error al generar informe');

    if (status) {
      const opps = (data.opportunities || []).length;
      status.innerHTML =
        `<div class="kaizen-report-preview">` +
          `<div class="kaizen-report-preview__title">✅ Informe generado</div>` +
          `<div class="kaizen-report-preview__text">${escapeHtml((data.text || '').slice(0, 200))}${data.text && data.text.length > 200 ? '…' : ''}</div>` +
          (opps ? `<div class="kaizen-report-preview__opps">${opps} oportunidad(es) identificada(s)</div>` : '') +
        `</div>`;
    }

    // Mostrar badge en FAB
    _refreshKaizenBadge();

  } catch (err) {
    if (status) {
      status.innerHTML = `<span class="ai-suggestion__error">⚠ ${escapeHtml(err.message)}</span>`;
    }
  }

  if (btn) { btn.disabled = false; btn.innerHTML = '<i class="bi bi-lightbulb me-1"></i>Ejecutar análisis diario'; }
  if (kaizenCard) kaizenCard.classList.remove('agent-card--working');
  assistantState.kaizenRunning = false;
}

async function _refreshKaizenBadge() {
  try {
    const res  = await fetch('/api/agents/kaizen-reports/unread');
    const data = await res.json();
    const badge = document.getElementById('agents-fab-badge');
    if (badge) {
      if (data.unread > 0) {
        badge.textContent = data.unread;
        badge.style.display = '';
      } else {
        badge.style.display = 'none';
      }
    }
  } catch (_) {}
}

// ── Cerrar modal ──────────────────────────────────────────────────────────────

document.addEventListener('click', (e) => {
  const modal = document.getElementById('assistant-modal');
  if (modal && e.target === modal) closeAssistantModal();
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (assistantState.modalOpen) closeAssistantModal();
    else if (assistantState.panelOpen) toggleAgentsPanel();
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadAgents();
  _refreshKaizenBadge();
});
