"""
agents/ci_coach_agent.py — Coach de Mejora Continua (CI Coach).

Especializado en:
  - Buscar iniciativas similares en todos los sites y reportar qué funcionó
  - Revisar iniciativas y verificar las 8 secciones del A3
  - Estimar beneficio cuantificable comparando con proyectos similares completados
  - Sugerir hitos, plazos razonables y métricas de seguimiento
"""

from __future__ import annotations

import sqlite3
from typing import Any

from agents.base import Agent
from site_aggregator import SITES


_A3_SECTIONS = [
    "Antecedentes / contexto",
    "Condición actual",
    "Objetivo / meta",
    "Análisis de causa raíz",
    "Contramedidas / plan de acción",
    "Plan de implementación",
    "Confirmación de efecto / resultados",
    "Seguimiento / próximos pasos",
]

# Language of the content stored in each site's database
_SITE_LANGUAGE: dict[str, str] = {
    "alcobendas":   "es",
    "indianapolis": "en",
    "fegersheim":   "fr",
    "sesto":        "it",
    "seishin":      "ja",
}

# Human-readable display name for each UI language (used in the system prompt)
_UI_LANG_DISPLAY: dict[str, str] = {
    "es": "Spanish (español)",
    "en": "English",
    "fr": "French (français)",
    "it": "Italian (italiano)",
    "ja": "Japanese (日本語)",
}


class CICoachAgent(Agent):

    name = "ci_coach"
    description = (
        "Coach experto en mejora continua y lean manufacturing farmacéutico. "
        "Busca iniciativas similares en todos los sites para aprender de lo que ya funcionó. "
        "Revisa el contenido de iniciativas y verifica que los A3 tengan las 8 secciones "
        "completas. Estima beneficios cuantificables comparando con iniciativas similares "
        "completadas. Sugiere hitos, plazos razonables y métricas de seguimiento. "
        "Activar cuando el usuario pregunte cómo gestionar una iniciativa, quiera feedback "
        "sobre un proyecto en curso, necesite estimar el beneficio esperado, quiera saber si "
        "los plazos son realistas, o busque aprender de lo que funcionó en otras plantas."
    )
    required_data = [
        "related_initiatives_cross_site",
        "completed_benchmarks",
        "kpi_context",
    ]
    max_tokens = 1536

    # Base prompt (overridden dynamically in run() based on ui_lang from context_data)
    system_prompt = (
        "You are an expert coach in continuous improvement and lean pharmaceutical manufacturing "
        "with 20 years of experience. Respond in the language specified by the LANGUAGE RULE."
    )

    # ── Dynamic system prompt ─────────────────────────────────────────────────

    @staticmethod
    def _build_system_prompt(ui_lang: str) -> str:
        lang = _UI_LANG_DISPLAY.get(ui_lang, "English")
        return f"""You are an expert coach in continuous improvement and lean pharmaceutical manufacturing with 20 years of experience. Your role is to help people managing improvement initiatives across a global pharma network.

LANGUAGE RULE (MANDATORY): The user's interface language is {lang}. Write your ENTIRE response in {lang}. This applies regardless of the language of the initiative data. Never mix languages in your response.

CROSS-SITE TRANSLATION RULE: Each initiative in the context is tagged with [LANG:xx] (its original content language), [ID:xx] and [SITE:xx] (for linking). When you reference an initiative whose [LANG:xx] differs from {lang}:
  1. Translate its title and description into {lang}.
  2. Add a translation marker right after the title, written in {lang} — e.g. "[Translated from French]" or "[Traducido del japonés]".
  3. Append a link using [ID:xx] and [SITE:xx]: build URL /initiatives/[ID]/edit?site=[SITE] and label it appropriately in {lang} — e.g. "See original at Fegersheim: /initiatives/42/edit?site=fegersheim".
  4. NEVER translate: personal names (e.g. Carlos García, 鈴木 一郎, John Smith), equipment codes (e.g. L-12A, OPTIMA-3200), model/serial numbers, brand names, or site names.

YOUR CAPABILITIES:
1. CROSS-SITE SEARCH: Find related initiatives across all sites. Report what was done and what worked, citing initiative name, site, and measured benefit.
2. CONTENT REVIEW: Review initiatives and suggest concrete improvements. For A3 methodology, verify all 8 sections: (1) Background/context, (2) Current state, (3) Goal, (4) Root cause analysis, (5) Countermeasures/action plan, (6) Implementation plan, (7) Results confirmation, (8) Follow-up. Flag missing or thin sections explicitly.
3. BENEFIT ESTIMATION: Estimate quantifiable benefit using historical KPIs and similar completed initiatives. Always cite reference initiatives with their actual results.
4. MILESTONES & TIMELINES: Suggest realistic milestones by complexity. Warn if aggressive (< 4 weeks for DMAIC/complex) or conservative (> 6 months for simple 5Why/Kaizen).

RESPONSE PRINCIPLES:
- Cite concrete data: real initiative names, dates, benefits.
- Be direct and practical. Prioritize the most impactful recommendations.
- Maximum 8 sentences or one structured list. Avoid generic advice.
- CRITICAL: ALL OUTPUT TEXT MUST BE IN {lang.upper()}."""

    # ── Runtime override for dynamic system prompt ────────────────────────────

    def run(
        self,
        user_message: str,
        context_data: dict[str, Any] | None = None,
        rag_chunks: list[dict] | None = None,
        previous_outputs: list[dict] | None = None,
    ) -> dict[str, Any]:
        ctx_input = context_data or {}
        ui_lang = ctx_input.get("ui_lang", "es")
        saved = self.system_prompt
        self.system_prompt = self._build_system_prompt(ui_lang)
        try:
            return super().run(user_message, ctx_input, rag_chunks, previous_outputs)
        finally:
            self.system_prompt = saved

    # ── Recuperación de datos ─────────────────────────────────────────────────

    def get_context(self, context_data: dict[str, Any]) -> dict[str, Any]:
        ctx = dict(context_data)

        all_initiatives: list[str] = []
        completed_benchmarks: list[str] = []
        kpi_lines: list[str] = []

        for site_id, site_info in SITES.items():
            db_path = site_info["db_path"]
            site_name = site_info.get("name", site_id)
            site_lang = _SITE_LANGUAGE.get(site_id, "es")
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row

                # Iniciativas activas + completadas recientes de todos los sites
                rows = conn.execute(
                    """SELECT id, title, description, methodology, status, category,
                              owner, expected_benefit, actual_benefit,
                              start_date, target_date, completion_date
                       FROM improvement_initiatives
                       WHERE deleted = 0
                         AND (status IN ('En progreso', 'No iniciado')
                              OR (status = 'Terminado'
                                  AND date(completion_date) >= date('now', '-180 days')))
                       ORDER BY
                         CASE status
                           WHEN 'En progreso' THEN 1
                           WHEN 'No iniciado' THEN 2
                           WHEN 'Terminado'   THEN 3
                           ELSE 4
                         END,
                         start_date DESC
                       LIMIT 12""",
                ).fetchall()

                for r in rows:
                    benefit_info = ""
                    if r["actual_benefit"]:
                        benefit_info = f" | real: {r['actual_benefit']}"
                    elif r["expected_benefit"]:
                        benefit_info = f" | esperado: {r['expected_benefit']}"

                    duration_info = ""
                    if r["start_date"] and r["target_date"]:
                        duration_info = f" | {r['start_date']} → {r['target_date']}"
                    if r["completion_date"]:
                        duration_info += f" (completado: {r['completion_date']})"

                    desc_snippet = (r["description"] or "")[:100].strip()

                    # Tag each entry with ID, site, and language so the LLM can
                    # translate cross-site content and construct links to originals.
                    all_initiatives.append(
                        f"  [ID:{r['id']}] [SITE:{site_id}] [LANG:{site_lang}]"
                        f" [{site_name}] [{r['status'].upper()}] [{r['methodology']}]"
                        f" [{r['category']}] {r['title']}"
                        + (f" — {desc_snippet}" if desc_snippet else "")
                        + benefit_info
                        + duration_info
                        + f" | owner: {r['owner'] or 'sin asignar'}"
                    )

                # Benchmarks: iniciativas completadas con beneficio real verificado
                bench_rows = conn.execute(
                    """SELECT id, title, methodology, category, expected_benefit,
                              actual_benefit, start_date, completion_date
                       FROM improvement_initiatives
                       WHERE status = 'Terminado'
                         AND actual_benefit IS NOT NULL
                         AND actual_benefit != ''
                         AND deleted = 0
                       ORDER BY completion_date DESC
                       LIMIT 6""",
                ).fetchall()

                for b in bench_rows:
                    start = b["start_date"] or "?"
                    end = b["completion_date"] or "?"
                    completed_benchmarks.append(
                        f"  [ID:{b['id']}] [SITE:{site_id}] [LANG:{site_lang}]"
                        f" [{site_name}] {b['title']} ({b['methodology']}, {b['category']}) |"
                        f" esperado: {b['expected_benefit']} → obtenido: {b['actual_benefit']} |"
                        f" duración: {start} a {end}"
                    )

                # KPIs de las líneas del site para estimar impacto económico
                kpi_rows = conn.execute(
                    """SELECT s.line_number,
                              SUM(k.units_produced)   AS tp,
                              SUM(k.units_rejected)   AS tr,
                              SUM(k.downtime_minutes) AS td,
                              MAX(k.planned_time_min) AS pt,
                              MAX(k.nominal_speed)    AS ns,
                              COUNT(DISTINCT s.id)    AS num_shifts
                       FROM shifts s
                       JOIN kpi_readings k ON k.shift_id = s.id
                       WHERE s.start_time >= datetime('now', '-30 days')
                       GROUP BY s.line_number
                       ORDER BY s.line_number
                       LIMIT 3""",
                ).fetchall()

                for k in kpi_rows:
                    tp = int(k["tp"] or 0)
                    tr = int(k["tr"] or 0)
                    td = float(k["td"] or 0.0)
                    pt = float(k["pt"] or 480.0)
                    ns = float(k["ns"] or 1200.0)
                    if tp > 0 and pt > 0:
                        op_t = max(pt - td, 0.0)
                        av = op_t / pt
                        ideal = ns * (op_t / 60.0) if ns > 0 else 0.0
                        pf = min(tp / ideal, 1.0) if ideal > 0 else 0.0
                        ql = max(tp - tr, 0) / tp
                        oee_val = av * pf * ql * 100.0
                        reject_rate = round(tr / tp * 100, 1)
                        kpi_lines.append(
                            f"  [{site_name}] Línea {k['line_number']}: "
                            f"OEE={oee_val:.1f}%, "
                            f"producido={tp:,} u, "
                            f"rechazos={reject_rate}%, "
                            f"downtime={td:.0f} min "
                            f"({k['num_shifts']} turnos / 30 días)"
                        )

                conn.close()

            except Exception as exc:
                ctx.setdefault("ci_coach_site_errors", []).append(
                    f"{site_name}: {str(exc)[:80]}"
                )

        if all_initiatives:
            ctx["related_initiatives_cross_site"] = (
                "Initiatives across all sites — tagged [ID:xx] [SITE:xx] [LANG:xx] for translation and linking:\n"
                + "\n".join(all_initiatives)
            )

        if completed_benchmarks:
            ctx["completed_benchmarks"] = (
                "Completed initiatives with verified benefit (benchmarks):\n"
                + "\n".join(completed_benchmarks)
            )

        if kpi_lines:
            ctx["kpi_context"] = (
                "KPIs por línea (últimos 30 días) para estimar impacto de mejoras:\n"
                + "\n".join(kpi_lines)
            )

        ctx["a3_sections_checklist"] = (
            "Mandatory A3 sections:\n"
            + "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(_A3_SECTIONS))
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

        if context_data.get("related_initiatives_cross_site"):
            parts.append(
                "## Cross-site initiatives (active and recent)\n"
                + context_data["related_initiatives_cross_site"]
            )

        if context_data.get("completed_benchmarks"):
            parts.append(
                "## Benchmarks: completed initiatives with verified benefit\n"
                + context_data["completed_benchmarks"]
            )

        if context_data.get("kpi_context"):
            parts.append(
                "## Reference KPIs for impact estimation\n"
                + context_data["kpi_context"]
            )

        if context_data.get("a3_sections_checklist"):
            parts.append(
                "## A3 sections checklist\n"
                + context_data["a3_sections_checklist"]
            )

        if context_data.get("ci_coach_site_errors"):
            errors = context_data["ci_coach_site_errors"]
            parts.append(
                f"## Warning: {len(errors)} site(s) had read errors\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        if rag_chunks:
            parts.append("## Relevant technical documentation")
            for chunk in rag_chunks:
                source = chunk.get("source_file", "Unknown")
                text = chunk.get("chunk_text", "").strip()
                parts.append(f"[Source: {source}]\n{text}")

        if previous_outputs:
            parts.append("## Analysis from other agents")
            for o in previous_outputs:
                parts.append(f"**{o.get('agent', 'Agent')}:** {o.get('response', '')}")

        parts.append(f"## User query\n{user_message.strip()}")

        return "\n\n".join(parts)
