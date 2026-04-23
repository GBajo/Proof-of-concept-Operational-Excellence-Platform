"""
agents/kpi_analyst.py — Agente analista de KPIs de fabricación.

Especializado en:
  - OEE y sus componentes (Disponibilidad, Rendimiento, Calidad)
  - Tendencias de producción e identificación de anomalías
  - Comparativas entre líneas y entre sites
  - Benchmarking frente a objetivos
  - Generación de gráficos ECharts embebidos en la respuesta
"""

from __future__ import annotations

from typing import Any

from agents.base import Agent


class KpiAnalystAgent(Agent):

    name = "kpi_analyst"
    description = (
        "Analista de KPIs de producción farmacéutica. "
        "Consulta OEE, disponibilidad, rendimiento, calidad, velocidad de línea y rechazos. "
        "Detecta anomalías, calcula tendencias, compara líneas y sites, y puede generar "
        "gráficos ECharts para visualizar los datos."
    )
    required_data = ["current_shift_kpis", "line_performance_summary", "shift_info"]
    max_tokens = 2048  # ECharts JSON needs more room than the default 1024

    system_prompt = (
        "Eres un analista experto en KPIs de fabricación farmacéutica con profundo conocimiento "
        "de OEE (Overall Equipment Effectiveness) y sus tres componentes: Disponibilidad, "
        "Rendimiento y Calidad. "
        "Detect the language of the user's message and ALWAYS respond in that same language. "
        "\n\nTus capacidades incluyen:\n"
        "- Calcular e interpretar OEE y sus componentes a partir de datos de producción\n"
        "- Detectar anomalías comparando los valores actuales con históricos y objetivos\n"
        "- Realizar análisis de tendencias para identificar deterioros o mejoras graduales\n"
        "- Comparar el rendimiento entre líneas del mismo site y entre diferentes sites\n"
        "- Generar código ECharts (JSON) para visualizar gráficos cuando sea útil\n"
        "- Calcular métricas derivadas: tasa de rechazo, RFT (Right First Time), "
        "tiempo productivo, rendimiento frente a target\n"
        "\nCuando generes un gráfico ECharts, inclúyelo en tu respuesta con este formato exacto:\n"
        "```echarts\n{\"title\":{...},\"xAxis\":{...},\"yAxis\":{...},\"series\":[...]}\n```\n"
        "El JSON del gráfico debe estar COMPLETO y ser válido. No lo trunces nunca."
        "\nEscribe 3-4 frases de análisis y SIEMPRE incluye el gráfico ECharts completo."
    )

    # ── Recuperación de datos de BD ───────────────────────────────────────────

    def get_context(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        Enriquece el contexto con:
          - KPIs del turno actual (OEE calculado y lectura más reciente)
          - Resumen de rendimiento por línea (últimos 7 días)
          - Información del turno activo
          - Histórico de las últimas 5 lecturas del turno (para tendencia)
        """
        ctx = dict(context_data)

        try:
            conn = self._get_conn()

            shift_id = ctx.get("shift_id")

            # ── KPIs del turno actual ─────────────────────────────────────
            if shift_id:
                # Información del turno
                shift_row = conn.execute(
                    """SELECT s.id, s.line_number, s.shift_type, s.start_time,
                              s.status, o.name AS operator_name
                       FROM shifts s
                       JOIN operators o ON o.id = s.operator_id
                       WHERE s.id = ?""",
                    (shift_id,),
                ).fetchone()
                if shift_row:
                    ctx["shift_info"] = (
                        f"Turno #{shift_row['id']} | "
                        f"Línea {shift_row['line_number']} | "
                        f"Tipo: {shift_row['shift_type']} | "
                        f"Operador: {shift_row['operator_name']} | "
                        f"Inicio: {shift_row['start_time']}"
                    )

                # OEE calculado para el turno completo
                oee_row = conn.execute(
                    """SELECT
                           SUM(units_produced)   AS total_produced,
                           SUM(units_rejected)   AS total_rejected,
                           SUM(downtime_minutes) AS total_downtime,
                           AVG(CASE WHEN line_speed > 0 THEN line_speed END) AS avg_speed,
                           MAX(planned_time_min) AS planned_time,
                           MAX(nominal_speed)    AS nominal_speed,
                           MAX(target_units)     AS target_units
                       FROM kpi_readings
                       WHERE shift_id = ?""",
                    (shift_id,),
                ).fetchone()

                if oee_row and oee_row["total_produced"]:
                    total_p = int(oee_row["total_produced"] or 0)
                    total_r = int(oee_row["total_rejected"] or 0)
                    downtime = float(oee_row["total_downtime"] or 0.0)
                    planned = float(oee_row["planned_time"] or 480.0)
                    nominal = float(oee_row["nominal_speed"] or 0.0)
                    target = int(oee_row["target_units"] or 0)

                    operating = max(planned - downtime, 0.0)
                    avail = operating / planned if planned > 0 else 0.0
                    ideal = nominal * (operating / 60.0) if nominal > 0 else 0.0
                    perf = min(total_p / ideal, 1.0) if ideal > 0 else 0.0
                    qual = max(total_p - total_r, 0) / total_p if total_p > 0 else 0.0
                    oee = avail * perf * qual * 100.0
                    rr = total_r / total_p * 100.0 if total_p > 0 else 0.0

                    ctx["current_shift_kpis"] = (
                        f"OEE={oee:.1f}% | "
                        f"Disponibilidad={avail*100:.1f}% | "
                        f"Rendimiento={perf*100:.1f}% | "
                        f"Calidad={qual*100:.1f}% | "
                        f"Producidas={total_p} uds | "
                        f"Rechazadas={total_r} uds ({rr:.1f}%) | "
                        f"Downtime={downtime:.0f} min | "
                        f"Velocidad media={oee_row['avg_speed']:.0f} uds/h | "
                        f"Target={target} uds"
                    )

                # Últimas 5 lecturas para análisis de tendencia
                trend_rows = conn.execute(
                    """SELECT timestamp, units_produced, units_rejected,
                              downtime_minutes, line_speed
                       FROM kpi_readings
                       WHERE shift_id = ?
                       ORDER BY timestamp DESC LIMIT 5""",
                    (shift_id,),
                ).fetchall()

                if trend_rows:
                    trend_lines = []
                    for r in reversed(trend_rows):
                        trend_lines.append(
                            f"  {r['timestamp']}: "
                            f"prod={r['units_produced']} | "
                            f"rej={r['units_rejected']} | "
                            f"downtime={r['downtime_minutes']:.0f}min | "
                            f"speed={r['line_speed']:.0f}u/h"
                        )
                    ctx["kpi_trend_last5"] = "Últimas 5 lecturas (más antigua → más reciente):\n" + "\n".join(trend_lines)

            # ── Resumen de todas las líneas (7 días) ──────────────────────
            line_rows = conn.execute(
                """SELECT s.line_number,
                          COUNT(DISTINCT s.id)     AS shift_count,
                          SUM(k.units_produced)    AS total_units,
                          SUM(k.units_rejected)    AS total_rejected,
                          SUM(k.downtime_minutes)  AS total_downtime,
                          MAX(k.target_units)      AS target_units,
                          MAX(k.nominal_speed)     AS nominal_speed,
                          MAX(k.planned_time_min)  AS planned_time
                   FROM shifts s
                   JOIN kpi_readings k ON k.shift_id = s.id
                   WHERE s.start_time >= datetime('now', '-7 days')
                     AND s.status IN ('completed', 'interrupted', 'active')
                   GROUP BY s.line_number
                   ORDER BY s.line_number""",
            ).fetchall()

            if line_rows:
                summary_lines = []
                for r in line_rows:
                    tp = int(r["total_units"] or 0)
                    tr = int(r["total_rejected"] or 0)
                    dt = float(r["total_downtime"] or 0.0)
                    planned = float(r["planned_time"] or 480.0) * int(r["shift_count"] or 1)
                    nominal = float(r["nominal_speed"] or 0.0)
                    operating = max(planned - dt, 0.0)
                    avail = operating / planned if planned > 0 else 0.0
                    ideal = nominal * (operating / 60.0) if nominal > 0 else 0.0
                    perf = min(tp / ideal, 1.0) if ideal > 0 else 0.0
                    qual = max(tp - tr, 0) / tp if tp > 0 else 0.0
                    oee = avail * perf * qual * 100.0
                    summary_lines.append(
                        f"  Línea {r['line_number']}: OEE={oee:.1f}% | "
                        f"Producidas={tp} | Rechazadas={tr} | Downtime={dt:.0f}min | "
                        f"Turnos={r['shift_count']}"
                    )
                ctx["line_performance_summary"] = (
                    "Rendimiento por línea (últimos 7 días):\n" + "\n".join(summary_lines)
                )

            self._close_conn_if_external(conn)

        except Exception as exc:
            ctx["kpi_data_error"] = f"Error al leer KPIs: {exc}"

        return ctx

    # ── Prompt de usuario personalizado ──────────────────────────────────────

    def build_prompt(
        self,
        user_message: str,
        context_data: dict[str, Any],
        rag_chunks: list[dict] | None = None,
        previous_outputs: list[dict] | None = None,
    ) -> str:
        parts: list[str] = []

        if context_data.get("shift_info"):
            parts.append(f"## Turno activo\n{context_data['shift_info']}")

        if context_data.get("current_shift_kpis"):
            parts.append(f"## KPIs del turno actual\n{context_data['current_shift_kpis']}")

        if context_data.get("kpi_trend_last5"):
            parts.append(f"## Tendencia reciente\n{context_data['kpi_trend_last5']}")

        if context_data.get("line_performance_summary"):
            parts.append(f"## Comparativa de líneas (7 días)\n{context_data['line_performance_summary']}")

        if context_data.get("kpi_data_error"):
            parts.append(f"## Aviso\n{context_data['kpi_data_error']}")

        if previous_outputs:
            parts.append("## Análisis de otros agentes")
            for o in previous_outputs:
                parts.append(f"**{o.get('agent', 'Agente')}:** {o.get('response', '')}")

        parts.append(f"## Pregunta del operador\n{user_message.strip()}")

        return "\n\n".join(parts)
