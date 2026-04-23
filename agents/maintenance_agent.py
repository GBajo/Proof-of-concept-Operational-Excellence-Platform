"""
agents/maintenance_agent.py — Agente de mantenimiento predictivo.

Especializado en:
  - Detección temprana de fallos por tendencias en cycle time y paradas
  - Root cause analysis de averías y alertas activas
  - Recomendaciones de mantenimiento preventivo según SOPs
  - Cálculo de MTBF (Mean Time Between Failures) y MTTR (Mean Time To Repair)
  - Análisis de problemas recurrentes por línea y equipo
"""

from __future__ import annotations

from typing import Any

from agents.base import Agent


class MaintenanceAgent(Agent):

    name = "maintenance"
    description = (
        "Ingeniero de mantenimiento predictivo para equipos de packaging farmacéutico. "
        "Analiza alertas activas, problemas recurrentes y datos de cycle time del VSM "
        "para detectar fallos inminentes, identificar causas raíz y recomendar "
        "acciones de mantenimiento preventivo. Calcula MTBF y MTTR."
    )
    required_data = ["active_alerts", "top_problems", "vsm_step_data", "maintenance_summary"]

    system_prompt = (
        "Eres un ingeniero de mantenimiento experto en equipos de líneas de packaging "
        "farmacéutico (llenado, etiquetado, serialización, estuchado, encajado, paletizado). "
        "Detect the language of the user's message and ALWAYS respond in that same language. "
        "\n\nTus capacidades incluyen:\n"
        "- Analizar tendencias de cycle time para detectar degradación antes de que cause avería\n"
        "- Identificar causas raíz de paradas y fallos recurrentes (5 Whys, Ishikawa)\n"
        "- Calcular MTBF (Media de Tiempo Entre Fallos) y MTTR (Media de Tiempo de Reparación)\n"
        "- Priorizar intervenciones de mantenimiento según impacto en OEE\n"
        "- Recomendar ajustes preventivos basados en datos históricos\n"
        "- Evaluar si una alerta es aislada o forma parte de un patrón\n"
        "\nFormato de respuesta:\n"
        "1. Estado actual (alertas críticas primero)\n"
        "2. Diagnóstico / causa probable\n"
        "3. Acciones recomendadas (inmediatas y preventivas)\n"
        "4. MTBF/MTTR si los datos lo permiten\n"
        "\nSé directo y técnico. Prioriza la seguridad del proceso sobre el rendimiento. "
        "Máximo 6 frases. Cita el documento fuente si aplica."
    )

    # ── Recuperación de datos de BD ───────────────────────────────────────────

    def get_context(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        Enriquece el contexto con:
          - Alertas activas del site (severity critical primero)
          - Top problemas recurrentes del mes
          - Datos de step_live_data del VSM (cycle times actuales vs. nominal)
          - Resumen de paradas por paso de proceso
        """
        ctx = dict(context_data)

        try:
            conn = self._get_conn()

            # ── Alertas activas ───────────────────────────────────────────
            alert_rows = conn.execute(
                """SELECT severity, title, description, line_number,
                          metric_name, metric_value, threshold_value,
                          timestamp, source
                   FROM alerts
                   WHERE status = 'active'
                   ORDER BY
                     CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                     timestamp DESC
                   LIMIT 10""",
            ).fetchall()

            if alert_rows:
                alert_lines = []
                for a in alert_rows:
                    alert_lines.append(
                        f"  [{a['severity'].upper()}] Línea {a['line_number']} — "
                        f"{a['title']}: {a['description']} "
                        f"(métrica={a['metric_name']}, valor={a['metric_value']}, "
                        f"umbral={a['threshold_value']}, ts={a['timestamp']})"
                    )
                ctx["active_alerts"] = (
                    f"{len(alert_rows)} alerta(s) activa(s):\n" + "\n".join(alert_lines)
                )
            else:
                ctx["active_alerts"] = "Sin alertas activas en este momento."

            # ── Problemas recurrentes (top 10 por impacto, últimos 30 días) ──
            problem_rows = conn.execute(
                """SELECT problem_description AS title, category, frequency,
                          impact_score, line_number, last_occurrence,
                          root_cause, countermeasure
                   FROM top_problems
                   WHERE date(last_occurrence) >= date('now', '-30 days')
                   ORDER BY impact_score DESC, frequency DESC
                   LIMIT 10""",
            ).fetchall()

            if problem_rows:
                prob_lines = []
                for p in problem_rows:
                    prob_lines.append(
                        f"  [{p['category']}] Línea {p['line_number']} — "
                        f"{p['title']} | frecuencia={p['frequency']} | "
                        f"impacto={p['impact_score']} | "
                        f"última ocurrencia={p['last_occurrence']}"
                        + (f" | causa raíz: {p['root_cause']}" if p["root_cause"] else "")
                        + (f" | contramedida: {p['countermeasure']}" if p["countermeasure"] else "")
                    )
                ctx["top_problems"] = (
                    "Top problemas recurrentes (30 días):\n" + "\n".join(prob_lines)
                )
            else:
                ctx["top_problems"] = "Sin problemas registrados en los últimos 30 días."

            # ── Datos VSM: cycle times actuales vs. nominal ───────────────
            # step_live_data: step_id, timestamp, cycle_time_s, status, wip_units, downtime_s
            # process_steps: id, line_number, step_order, name, step_type, nominal_ct_s
            vsm_rows = conn.execute(
                """SELECT ps.step_name, ps.line_number,
                          ps.nominal_cycle_time_seconds AS nominal_ct_s, ps.step_type,
                          sld.actual_cycle_time AS cycle_time_s, sld.status,
                          sld.units_in_wip, sld.current_speed, sld.timestamp
                   FROM step_live_data sld
                   JOIN process_steps ps ON ps.id = sld.step_id
                   WHERE sld.id IN (
                       SELECT MAX(id) FROM step_live_data GROUP BY step_id
                   )
                   ORDER BY ps.line_number, ps.step_order""",
            ).fetchall()

            if vsm_rows:
                vsm_lines = []
                anomalies = []
                for r in vsm_rows:
                    deviation = ""
                    if r["nominal_ct_s"] and r["cycle_time_s"]:
                        ratio = r["cycle_time_s"] / r["nominal_ct_s"]
                        if ratio > 1.20:
                            deviation = f" ⚠ +{(ratio-1)*100:.0f}% sobre nominal"
                            anomalies.append(
                                f"{r['step_name']} (Línea {r['line_number']}): "
                                f"CT={r['cycle_time_s']:.1f}s vs nominal={r['nominal_ct_s']:.1f}s"
                            )

                    vsm_lines.append(
                        f"  Línea {r['line_number']} — {r['step_name']}: "
                        f"CT={r['cycle_time_s']:.1f}s (nominal={r['nominal_ct_s']:.1f}s){deviation} | "
                        f"estado={r['status']} | velocidad={r['current_speed']:.0f} uds/min | "
                        f"WIP={r['units_in_wip']}"
                    )

                ctx["vsm_step_data"] = "Cycle times actuales (última lectura):\n" + "\n".join(vsm_lines)

                if anomalies:
                    ctx["vsm_anomalies"] = (
                        "⚠ Pasos con cycle time >20% sobre nominal:\n"
                        + "\n".join(f"  - {a}" for a in anomalies)
                    )

            # ── MTBF/MTTR estimado desde alertas resueltas ────────────────
            mtbf_rows = conn.execute(
                """SELECT line_number,
                          COUNT(*) AS total_failures,
                          AVG(
                              CASE WHEN metric_name = 'downtime_minutes'
                              THEN CAST(metric_value AS REAL) ELSE NULL END
                          ) AS avg_downtime_min
                   FROM alerts
                   WHERE status = 'resolved'
                     AND timestamp >= datetime('now', '-30 days')
                   GROUP BY line_number
                   ORDER BY line_number""",
            ).fetchall()

            if mtbf_rows:
                mtbf_lines = []
                for r in mtbf_rows:
                    # MTBF aproximado: 30 días / nº de fallos (en horas)
                    mtbf_h = (30 * 24) / r["total_failures"] if r["total_failures"] > 0 else None
                    mttr = r["avg_downtime_min"]
                    line = f"  Línea {r['line_number']}: {r['total_failures']} fallos/30d"
                    if mtbf_h:
                        line += f" | MTBF≈{mtbf_h:.1f}h"
                    if mttr:
                        line += f" | MTTR≈{mttr:.1f}min"
                    mtbf_lines.append(line)
                ctx["maintenance_summary"] = (
                    "Resumen de fiabilidad (últimos 30 días):\n" + "\n".join(mtbf_lines)
                )

            self._close_conn_if_external(conn)

        except Exception as exc:
            ctx["maintenance_data_error"] = f"Error al leer datos de mantenimiento: {exc}"

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

        if context_data.get("active_alerts"):
            parts.append(f"## Alertas activas\n{context_data['active_alerts']}")

        if context_data.get("vsm_anomalies"):
            parts.append(f"## Anomalías de cycle time detectadas\n{context_data['vsm_anomalies']}")

        if context_data.get("vsm_step_data"):
            parts.append(f"## Estado VSM (cycle times)\n{context_data['vsm_step_data']}")

        if context_data.get("top_problems"):
            parts.append(f"## Problemas recurrentes\n{context_data['top_problems']}")

        if context_data.get("maintenance_summary"):
            parts.append(f"## Fiabilidad MTBF/MTTR\n{context_data['maintenance_summary']}")

        if rag_chunks:
            parts.append("## Documentación técnica relevante")
            for chunk in rag_chunks:
                source = chunk.get("source_file", "Desconocido")
                text = chunk.get("chunk_text", "").strip()
                parts.append(f"[Fuente: {source}]\n{text}")

        if previous_outputs:
            parts.append("## Análisis de otros agentes")
            for o in previous_outputs:
                parts.append(f"**{o.get('agent', 'Agente')}:** {o.get('response', '')}")

        if context_data.get("maintenance_data_error"):
            parts.append(f"## Aviso\n{context_data['maintenance_data_error']}")

        parts.append(f"## Mensaje del operador\n{user_message.strip()}")

        return "\n\n".join(parts)
