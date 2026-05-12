/**
 * widgets.js — Inicialización y auto-refresh de widgets ECharts del dashboard.
 * Espera que el DOM tenga un elemento <script id="widget-data"> con JSON.
 */
(function () {
  "use strict";

  const REFRESH_INTERVAL_MS = 60_000; // refresca datos cada 60 s

  /** Mapa de instancias ECharts por widget id */
  const _charts = {};

  /**
   * Inicializa un widget ECharts en el contenedor indicado.
   * @param {string} containerId
   * @param {object} echartsConfig
   */
  function initChart(containerId, echartsConfig) {
    const el = document.getElementById(containerId);
    if (!el || !echartsConfig || Object.keys(echartsConfig).length === 0) return;

    const chart = echarts.init(el, null, { renderer: "canvas" });
    chart.setOption(echartsConfig);
    _charts[containerId] = chart;
  }

  /**
   * Actualiza un widget existente con nueva config de ECharts.
   */
  function updateChart(containerId, echartsConfig) {
    const chart = _charts[containerId];
    if (!chart || !echartsConfig) return;
    chart.setOption(echartsConfig, { notMerge: false });
  }

  /**
   * Refresca todos los widgets de un layout llamando a la API.
   * @param {number|null} lineNumber
   */
  function refreshAll(lineNumber) {
    const params = lineNumber ? `?line_number=${lineNumber}` : "";
    fetch(`/api/widgets/render${params}`)
      .then((r) => r.json())
      .then((data) => {
        (data.rows || []).forEach((row) => {
          row.forEach((w) => {
            if (w.render_type === "chart" && w.id) {
              updateChart(w.id, w.echarts_config);
            }
            // Las kpi_cards se actualizan vía dashboard.js existente
          });
        });
      })
      .catch(() => {});
  }

  /**
   * Punto de entrada: lee el JSON embebido y lanza los gráficos.
   */
  function init() {
    const dataEl = document.getElementById("widget-data");
    if (!dataEl) return;

    let widgetRows;
    try {
      widgetRows = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }

    widgetRows.forEach((row) => {
      row.forEach((w) => {
        if (w.render_type === "chart" && w.id) {
          initChart(w.id, w.echarts_config);
        }
      });
    });

    // Auto-refresh
    const lineNumber = window.WIDGET_LINE_NUMBER || null;
    setInterval(() => refreshAll(lineNumber), REFRESH_INTERVAL_MS);
  }

  // Redimensionar gráficos al cambiar el tamaño de la ventana
  window.addEventListener("resize", () => {
    Object.values(_charts).forEach((c) => c.resize());
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
