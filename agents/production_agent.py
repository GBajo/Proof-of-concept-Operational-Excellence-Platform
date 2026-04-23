"""
agents/production_agent.py — Agente planificador de producción.

Especializado en:
  - Análisis de capacidad de línea frente a plan y objetivos
  - Detección de cuellos de botella (paso más lento del VSM)
  - Cálculo del impacto de paradas sobre el plan de producción
  - Sugerencias de ajuste de secuencia, velocidad y changeover
  - Proyección de cierre de turno (¿llegará al target?)
"""

from __future__ import annotations

from typing import Any

from agents.base import Agent


class ProductionAgent(Agent):

    name = "production"
    description = (
        "Planificador de producción farmacéutica. Analiza la capacidad de cada línea, "
        "detecta cuellos de botella en el flujo de proceso, calcula el impacto de paradas "
        "en el plan de producción y proyecta si el turno alcanzará el target. "
        "Activar cuando el operador pregunte por planificación, capacidad, si llegarán al "
        "objetivo, cuánto se ha perdido por paradas, o cómo recuperar producción."
    )
    required_data = [
        "production_plan_status",
        "bottleneck_analysis",
        "shift_projection",
        "changeover_impact",
    ]

    system_prompt = (
        "Eres un planificador de producción experto en líneas de packaging farmacéutico "
        "con sólidos conocimientos de Lean Manufacturing, teoría de restricciones (TOC) "
        "y planificación de capacidad. "
        "Detect the language of the user's message and ALWAYS respond in that same language. "
        "\n\nTus capacidades incluyen:\n"
        "- Calcular si el turno alcanzará el target dado el ritmo actual y el tiempo restante\n"
        "- Identificar el cuello de botella del proceso comparando cycle times entre pasos\n"
        "- Cuantificar unidades perdidas por paradas y su impacto en el plan\n"
        "- Sugerir ajustes de secuencia, batch sizes o changeover para recuperar producción\n"
        "- Calcular la velocidad necesaria para alcanzar el target en el tiempo restante\n"
        "- Identificar si el cuello de botella es interno (proceso) o externo (material, personal)\n"
        "\nFormato de respuesta:\n"
        "1. Estado del plan: % completado, proyección de cierre\n"
        "2. Cuello de botella identificado (si lo hay)\n"
        "3. Unidades perdidas por paradas y causa principal\n"
        "4. Recomendación accionable para recuperar producción\n"
        "\nSé específico con los números. Calcula la velocidad necesaria para alcanzar el target. "
        "Si el target no es alcanzable, indícalo claramente con el gap estimado. "
        "Máximo 5-6 frases."
    )

    # ── Recuperación de datos de BD ───────────────────────────────────────────

    def get_context(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        Enriquece el contexto con:
          - Estado actual del plan: producido vs target, % completado
          - Tiempo restante estimado del turno
          - Cuello de botella: paso del VSM con cycle time más alto respecto al nominal
          - Impacto de paradas: unidades perdidas por downtime
          - Proyección de cierre: ¿llegará al target con el ritmo actual?
          - Histórico de changeovers del turno
        """
        ctx = dict(context_data)

        try:
            conn = self._get_conn()

            shift_id = ctx.get("shift_id")

            if shift_id:
                # ── Datos del turno y KPIs acumulados ────────────────────
                shift_row = conn.execute(
                    """SELECT s.id, s.line_number, s.shift_type, s.start_time,
                              s.status, o.name AS operator_name
                       FROM shifts s
                       JOIN operators o ON o.id = s.operator_id
                       WHERE s.id = ?""",
                    (shift_id,),
                ).fetchone()

                kpi_agg = conn.execute(
                    """SELECT
                           SUM(units_produced)    AS total_produced,
                           SUM(units_rejected)    AS total_rejected,
                           SUM(downtime_minutes)  AS total_downtime,
                           AVG(CASE WHEN line_speed > 0 THEN line_speed END) AS avg_speed,
                           MAX(planned_time_min)  AS planned_time,
                           MAX(nominal_speed)     AS nominal_speed,
                           MAX(target_units)      AS target_units
                       FROM kpi_readings
                       WHERE shift_id = ?""",
                    (shift_id,),
                ).fetchone()

                if kpi_agg and kpi_agg["total_produced"] is not None:
                    produced = int(kpi_agg["total_produced"] or 0)
                    target = int(kpi_agg["target_units"] or 0)
                    downtime = float(kpi_agg["total_downtime"] or 0.0)
                    planned = float(kpi_agg["planned_time"] or 480.0)
                    nominal = float(kpi_agg["nominal_speed"] or 1200.0)
                    avg_speed = float(kpi_agg["avg_speed"] or 0.0)

                    pct = produced / target * 100.0 if target > 0 else 0.0
                    # Unidades perdidas por downtime al ritmo nominal
                    lost_units = int(nominal * (downtime / 60.0))
                    # Tiempo transcurrido desde inicio del turno (más preciso que entre lecturas)
                    elapsed_min = 0.0
                    if shift_row and shift_row["start_time"]:
                        try:
                            from datetime import datetime, timezone
                            t0 = datetime.fromisoformat(shift_row["start_time"])
                            # SQLite guarda sin timezone; asumir local
                            now = datetime.now()
                            elapsed_min = (now - t0).total_seconds() / 60.0
                            # Clamp: no puede superar planned_time
                            elapsed_min = min(elapsed_min, planned)
                        except Exception:
                            pass
                    remaining_min = max(planned - elapsed_min - downtime, 0.0)
                    # Proyección: con velocidad actual, ¿cuánto más produciremos?
                    projected_extra = int(avg_speed * (remaining_min / 60.0)) if avg_speed > 0 else 0
                    projected_total = produced + projected_extra
                    gap = target - projected_total
                    # Velocidad necesaria para cerrar el gap en el tiempo restante
                    speed_needed = (
                        (target - produced) / (remaining_min / 60.0)
                        if remaining_min > 10 else 0.0
                    )

                    ctx["production_plan_status"] = (
                        f"Producido={produced} uds ({pct:.1f}% del target={target}) | "
                        f"Rechazadas={kpi_agg['total_rejected']} uds | "
                        f"Downtime={downtime:.0f} min | "
                        f"Velocidad media={avg_speed:.0f} uds/h | "
                        f"Tiempo restante estimado={remaining_min:.0f} min"
                    )
                    ctx["shift_projection"] = (
                        f"Proyección de cierre: {projected_total} uds "
                        f"({'ALCANZA' if gap <= 0 else 'NO alcanza'} el target) | "
                        f"Gap={abs(gap)} uds | "
                        f"Velocidad necesaria para recuperar={speed_needed:.0f} uds/h "
                        f"(nominal={nominal:.0f})"
                    )
                    ctx["production_plan_status"] += (
                        f" | Unidades perdidas por downtime≈{lost_units} uds"
                    )

            # ── Cuello de botella: paso con mayor desviación sobre nominal ──
            bottleneck = conn.execute(
                """SELECT ps.step_name AS name, ps.line_number,
                          ps.nominal_cycle_time_seconds AS nominal_ct_s, ps.step_order,
                          sld.actual_cycle_time AS cycle_time_s, sld.status,
                          sld.current_speed
                   FROM step_live_data sld
                   JOIN process_steps ps ON ps.id = sld.step_id
                   WHERE sld.id IN (
                       SELECT MAX(id) FROM step_live_data GROUP BY step_id
                   )
                     AND ps.nominal_cycle_time_seconds > 0
                   ORDER BY (CAST(sld.actual_cycle_time AS REAL) / ps.nominal_cycle_time_seconds) DESC
                   LIMIT 1""",
            ).fetchone()

            if bottleneck and bottleneck["cycle_time_s"]:
                ratio = bottleneck["cycle_time_s"] / bottleneck["nominal_ct_s"]
                ctx["bottleneck_analysis"] = (
                    f"Cuello de botella detectado: paso '{bottleneck['name']}' "
                    f"(Línea {bottleneck['line_number']}, orden={bottleneck['step_order']}) | "
                    f"CT actual={bottleneck['cycle_time_s']:.1f}s vs nominal={bottleneck['nominal_ct_s']:.1f}s "
                    f"({ratio*100-100:+.1f}% sobre nominal) | "
                    f"estado={bottleneck['status']} | "
                    f"velocidad actual={bottleneck['current_speed']:.0f} uds/min"
                )

            # ── Tiempo de changeover del turno activo ─────────────────────
            # Aproximado como suma de downtime de pasos con status='changeover'
            co_rows = conn.execute(
                """SELECT ps.step_name AS name, sld.actual_cycle_time, sld.current_speed
                   FROM step_live_data sld
                   JOIN process_steps ps ON ps.id = sld.step_id
                   WHERE sld.status = 'changeover'
                   ORDER BY sld.actual_cycle_time DESC
                   LIMIT 5""",
            ).fetchall()

            if co_rows:
                co_items = [
                    f"{r['name']}: CT={r['actual_cycle_time']:.0f}s" for r in co_rows
                ]
                ctx["changeover_impact"] = (
                    "Pasos en changeover actualmente: " + " | ".join(co_items)
                )

            self._close_conn_if_external(conn)

        except Exception as exc:
            ctx["production_data_error"] = f"Error al leer datos de producción: {exc}"

        return ctx

    def build_prompt(
        self,
        user_message: str,
        context_data: dict[str, Any],
        rag_chunks: list[dict] | None = None,
        previous_outputs: list[dict] | None = None,
    ) -> str:
        parts: list[str] = []

        if context_data.get("production_plan_status"):
            parts.append(f"## Estado del plan de producción\n{context_data['production_plan_status']}")

        if context_data.get("shift_projection"):
            parts.append(f"## Proyección de cierre de turno\n{context_data['shift_projection']}")

        if context_data.get("bottleneck_analysis"):
            parts.append(f"## Cuello de botella\n{context_data['bottleneck_analysis']}")

        if context_data.get("changeover_impact"):
            parts.append(f"## Changeovers activos\n{context_data['changeover_impact']}")

        if rag_chunks:
            parts.append("## Documentación de referencia")
            for chunk in rag_chunks:
                source = chunk.get("source_file", "Desconocido")
                text = chunk.get("chunk_text", "").strip()
                parts.append(f"[Fuente: {source}]\n{text}")

        if previous_outputs:
            parts.append("## Análisis de otros agentes")
            for o in previous_outputs:
                parts.append(f"**{o.get('agent', 'Agente')}:** {o.get('response', '')}")

        if context_data.get("production_data_error"):
            parts.append(f"## Aviso\n{context_data['production_data_error']}")

        parts.append(f"## Mensaje del operador\n{user_message.strip()}")

        return "\n\n".join(parts)
