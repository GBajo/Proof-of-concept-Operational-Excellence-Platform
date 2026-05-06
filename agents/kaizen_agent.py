"""
agents/kaizen_agent.py — Agente de Mejora Continua Lean/Six Sigma.

Especializado en:
  - Sugerir nuevas iniciativas kaizen basándose en problemas y KPIs de todos los sites
  - Identificar best practices transferibles entre plantas
  - Proponer estructuras A3 y charters de proyectos
  - Evaluar el impacto real de iniciativas completadas (antes vs. después)
  - Ejecutar análisis diario autónomo y guardar informe en kaizen_reports

Puede ejecutarse en modo "background" para generar informes periódicos
sin intervención del operador.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from agents.base import Agent
from site_aggregator import SITES


class KaizenAgent(Agent):

    name = "kaizen"
    description = (
        "Consultor Lean/Six Sigma especializado en fabricación farmacéutica. "
        "Analiza problemas recurrentes e iniciativas de todos los sites para sugerir "
        "nuevos proyectos kaizen, identificar best practices transferibles entre plantas "
        "y proponer A3s. Evalúa el impacto real de las iniciativas completadas. "
        "Activar cuando el operador pregunte por mejoras, oportunidades, kaizen, "
        "iniciativas, best practices o quiera saber qué están haciendo otras plantas."
    )
    required_data = [
        "cross_site_problems",
        "active_initiatives",
        "completed_initiatives_impact",
        "kaizen_opportunities",
    ]

    system_prompt = (
        "Eres un consultor Lean/Six Sigma con más de 15 años de experiencia en "
        "fabricación farmacéutica. Conoces profundamente DMAIC, A3 Thinking, Kaizen, "
        "SMED, TPM, VSM y las herramientas de Six Sigma. "
        "Detect the language of the user's message and ALWAYS respond in that same language. "
        "\n\nTus capacidades incluyen:\n"
        "- Identificar las mayores oportunidades de mejora a partir de datos de problemas y KPIs\n"
        "- Sugerir qué metodología aplicar (A3, Kaizen, DMAIC, 5Why) según el tipo de problema\n"
        "- Identificar best practices de un site que podrían replicarse en otros\n"
        "- Estimar el impacto potencial de una mejora en términos de OEE o unidades/año\n"
        "- Estructurar un A3 básico (situación actual, objetivo, causa raíz, contramedidas)\n"
        "- Evaluar si una iniciativa completada ha conseguido su objetivo\n"
        "\nCuando sugieras una iniciativa, incluye siempre:\n"
        "  - Título del proyecto\n"
        "  - Metodología recomendada\n"
        "  - KPI objetivo y mejora esperada (%)\n"
        "  - Owner sugerido (rol)\n"
        "  - Duración estimada\n"
        "\nSé práctico y orientado a resultados. Prioriza las oportunidades por impacto "
        "en OEE o reducción de costes. Máximo 6-7 frases o una lista estructurada."
    )

    # ── Recuperación de datos de BD ───────────────────────────────────────────

    def get_context(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        Enriquece el contexto con datos cross-site:
          - Top problemas de todos los sites (para identificar patrones globales)
          - Iniciativas activas y completadas con su impacto real
          - Comparativa de OEE entre sites para detectar best practices
          - Iniciativas completadas con beneficio declarado vs. actual
        """
        ctx = dict(context_data)

        # ── Datos cross-site ──────────────────────────────────────────────
        all_problems: list[str] = []
        all_initiatives: list[str] = []
        completed_impact: list[str] = []
        site_oee_comparison: list[str] = []

        for site_id, site_info in SITES.items():
            db_path = site_info["db_path"]
            site_name = site_info.get("name", site_id)
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row

                # Problemas recurrentes de este site
                prob_rows = conn.execute(
                    """SELECT problem_description AS title, category, frequency,
                              impact_score, line_number,
                              root_cause, countermeasure
                       FROM top_problems
                       WHERE date(last_occurrence) >= date('now', '-30 days')
                       ORDER BY impact_score DESC, frequency DESC
                       LIMIT 3""",
                ).fetchall()

                for p in prob_rows:
                    all_problems.append(
                        f"  [{site_name}] Línea {p['line_number']} — {p['title']} "
                        f"(cat={p['category']}, freq={p['frequency']}, "
                        f"impacto={p['impact_score']})"
                        + (f" → contramedida: {p['countermeasure']}" if p["countermeasure"] else "")
                    )

                # Iniciativas activas
                active_rows = conn.execute(
                    """SELECT title, methodology, status, owner,
                              expected_benefit, start_date, target_date
                       FROM improvement_initiatives
                       WHERE status IN ('En progreso', 'No iniciado')
                         AND deleted = 0
                       ORDER BY start_date DESC
                       LIMIT 5""",
                ).fetchall()

                for i in active_rows:
                    all_initiatives.append(
                        f"  [{site_name}] [{i['status'].upper()}] {i['title']} "
                        f"({i['methodology']}) | owner={i['owner']} | "
                        f"beneficio esperado: {i['expected_benefit'] or 'no definido'}"
                    )

                # Iniciativas completadas con beneficio real vs. esperado
                done_rows = conn.execute(
                    """SELECT title, methodology, expected_benefit, actual_benefit,
                              start_date, completion_date
                       FROM improvement_initiatives
                       WHERE status = 'Terminado'
                         AND actual_benefit IS NOT NULL
                         AND deleted = 0
                       ORDER BY completion_date DESC
                       LIMIT 3""",
                ).fetchall()

                for d in done_rows:
                    completed_impact.append(
                        f"  [{site_name}] ✅ {d['title']} ({d['methodology']}) | "
                        f"esperado: {d['expected_benefit']} → "
                        f"obtenido: {d['actual_benefit']}"
                    )

                # OEE promedio de la semana para comparativa
                oee_row = conn.execute(
                    """SELECT s.line_number,
                              SUM(k.units_produced)   AS tp,
                              SUM(k.units_rejected)   AS tr,
                              SUM(k.downtime_minutes) AS td,
                              MAX(k.planned_time_min) AS pt,
                              MAX(k.nominal_speed)    AS ns
                       FROM shifts s
                       JOIN kpi_readings k ON k.shift_id = s.id
                       WHERE s.start_time >= datetime('now', '-7 days')
                       GROUP BY s.line_number
                       LIMIT 1""",
                ).fetchone()

                if oee_row and oee_row["tp"]:
                    tp = int(oee_row["tp"] or 0)
                    tr = int(oee_row["tr"] or 0)
                    td = float(oee_row["td"] or 0.0)
                    pt = float(oee_row["pt"] or 480.0)
                    ns = float(oee_row["ns"] or 1200.0)
                    op_t = max(pt - td, 0.0)
                    av = op_t / pt if pt > 0 else 0.0
                    ideal = ns * (op_t / 60.0) if ns > 0 else 0.0
                    pf = min(tp / ideal, 1.0) if ideal > 0 else 0.0
                    ql = max(tp - tr, 0) / tp if tp > 0 else 0.0
                    oee_val = av * pf * ql * 100.0
                    target_oee = site_info.get("target_oee", 85)
                    gap = oee_val - target_oee
                    site_oee_comparison.append(
                        f"  {site_name}: OEE={oee_val:.1f}% "
                        f"(target={target_oee}%, gap={gap:+.1f}%)"
                    )

                conn.close()

            except Exception as exc:
                ctx.setdefault("kaizen_site_errors", []).append(
                    f"{site_id} ({site_name}): {str(exc)[:80]}"
                )

        if all_problems:
            ctx["cross_site_problems"] = (
                "Top problemas recurrentes cross-site (30 días):\n"
                + "\n".join(all_problems)
            )

        if all_initiatives:
            ctx["active_initiatives"] = (
                "Iniciativas activas / planificadas:\n"
                + "\n".join(all_initiatives)
            )

        if completed_impact:
            ctx["completed_initiatives_impact"] = (
                "Iniciativas completadas con beneficio real:\n"
                + "\n".join(completed_impact)
            )

        if site_oee_comparison:
            ctx["site_oee_comparison"] = (
                "Comparativa OEE entre sites (7 días):\n"
                + "\n".join(site_oee_comparison)
            )

        return ctx

    def build_prompt(
        self,
        user_message: str,
        context_data: dict[str, Any],
        rag_chunks: list[dict] | None = None,
        previous_outputs: list[dict] | None = None,
    ) -> str:
        parts: list[str] = []

        if context_data.get("site_oee_comparison"):
            parts.append(f"## Comparativa OEE entre sites\n{context_data['site_oee_comparison']}")

        if context_data.get("cross_site_problems"):
            parts.append(f"## Problemas recurrentes cross-site\n{context_data['cross_site_problems']}")

        if context_data.get("active_initiatives"):
            parts.append(f"## Iniciativas en curso\n{context_data['active_initiatives']}")

        if context_data.get("completed_initiatives_impact"):
            parts.append(f"## Impacto de iniciativas completadas\n{context_data['completed_initiatives_impact']}")

        if context_data.get("kaizen_site_errors"):
            errors = context_data["kaizen_site_errors"]
            parts.append(
                f"## Aviso: {len(errors)} site(s) con error al leer datos\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

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

        parts.append(f"## Mensaje / consulta\n{user_message.strip()}")

        return "\n\n".join(parts)

    # ── Análisis diario autónomo ──────────────────────────────────────────────

    def run_daily_analysis(self, db_path: str | None = None) -> dict[str, Any]:
        """
        Ejecuta el análisis diario de oportunidades kaizen y guarda el informe
        en la tabla kaizen_reports de la BD del site activo.

        Diseñado para ser llamado por la ruta /api/agents/kaizen-report (POST).

        Devuelve dict con: report_id, text, opportunities (lista), model, source.
        """
        target_db = db_path or self.db_path

        daily_prompt = (
            "Genera un informe diario de oportunidades de mejora continua para esta planta. "
            "Analiza los datos proporcionados y proporciona:\n"
            "1. TOP 3 oportunidades de mejora ordenadas por impacto potencial en OEE\n"
            "2. Una best practice de otro site que podría replicarse aquí\n"
            "3. Estado de las iniciativas en curso: ¿alguna en riesgo de no alcanzar el objetivo?\n"
            "4. Recomendación de metodología para la oportunidad #1\n"
            "Formato JSON estructurado:\n"
            "{\n"
            '  "summary": "Resumen ejecutivo en 2 frases",\n'
            '  "opportunities": [\n'
            '    {"rank": 1, "title": "...", "impact": "...", "methodology": "...", "owner": "..."},\n'
            '    ...\n'
            "  ],\n"
            '  "best_practice": {"site": "...", "practice": "...", "transferable_to": "..."},\n'
            '  "at_risk_initiatives": ["titulo1", "titulo2"]\n'
            "}"
        )

        result = self.run(
            user_message=daily_prompt,
            context_data={"db_path": target_db},
        )

        # Parsear el JSON de la respuesta (el LLM debería responder en JSON)
        opportunities: list[dict] = []
        summary = result["response"] if "response" in result else result.get("text", "")

        try:
            raw = summary
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
                summary = parsed.get("summary", raw)
                opportunities = parsed.get("opportunities", [])
        except Exception:
            pass

        # Guardar en kaizen_reports
        report_id = None
        try:
            conn = sqlite3.connect(target_db)
            cur = conn.execute(
                """INSERT INTO kaizen_reports
                   (site_id, report_text, opportunities_json,
                    model_used, source, generated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (
                    self.site_id,
                    summary if isinstance(summary, str) else json.dumps(summary, ensure_ascii=False),
                    json.dumps(opportunities, ensure_ascii=False),
                    result.get("model", "unknown"),
                    result.get("source", "mock"),
                ),
            )
            conn.commit()
            report_id = cur.lastrowid
            conn.close()
        except Exception as exc:
            result["db_error"] = str(exc)

        return {
            "report_id": report_id,
            "text": summary if isinstance(summary, str) else json.dumps(summary),
            "opportunities": opportunities,
            "model": result.get("model", "unknown"),
            "source": result.get("source", "mock"),
            "error": result.get("error"),
        }
