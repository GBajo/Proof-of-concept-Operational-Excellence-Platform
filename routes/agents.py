"""
routes/agents.py — API para el ecosistema de agentes inteligentes.

Endpoints:
  GET  /api/agents                        → Lista de agentes registrados
  POST /api/agents/kaizen-report          → Dispara análisis diario del KaizenAgent
  GET  /api/agents/kaizen-reports         → Lista informes kaizen guardados
  GET  /api/agents/kaizen-reports/unread  → Cuenta de informes no leídos
  POST /api/agents/kaizen-reports/<id>/read → Marca informe como leído
  POST /api/assistant/suggest-agent       → Fuerza un agente específico (sin orquestador)
"""

from __future__ import annotations

import json

from flask import Blueprint, g, jsonify, request

from database import get_db
from site_aggregator import SITES, DEFAULT_SITE

bp = Blueprint("agents_api", __name__)


def _site_db():
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    db_path = SITES.get(site_id, SITES[DEFAULT_SITE])["db_path"]
    return site_id, db_path, get_db()


# ── Lista de agentes disponibles ──────────────────────────────────────────────

@bp.get("/api/agents")
def list_agents_endpoint():
    """Devuelve la lista de agentes registrados con nombre, descripción y categoría."""
    from agents.registry import list_agents
    return jsonify(list_agents())


# ── Análisis kaizen diario (background agent) ─────────────────────────────────

@bp.post("/api/agents/kaizen-report")
def trigger_kaizen_report():
    """
    Dispara el análisis diario del KaizenAgent.
    Genera un informe de oportunidades de mejora y lo guarda en kaizen_reports.
    Rechaza la petición si ya se generó un informe en los últimos 5 minutos.
    """
    site_id, db_path, db = _site_db()

    # Protección anti-concurrencia: evitar doble ejecución en 5 minutos
    try:
        recent = db.execute(
            """SELECT COUNT(*) FROM kaizen_reports
               WHERE site_id = ? AND generated_at > datetime('now', '-5 minutes')""",
            (site_id,),
        ).fetchone()[0]
        if recent > 0:
            return jsonify({
                "error": "Ya se generó un informe en los últimos 5 minutos. Espera antes de volver a ejecutar."
            }), 429
    except Exception:
        pass  # Si la tabla aún no existe, continuar

    try:
        from agents.kaizen_agent import KaizenAgent
        agent = KaizenAgent(site_id=site_id, db_path=db_path)
        result = agent.run_daily_analysis(db_path=db_path)

        return jsonify({
            "report_id":     result.get("report_id"),
            "text":          result.get("text", ""),
            "opportunities": result.get("opportunities", []),
            "model":         result.get("model", "unknown"),
            "source":        result.get("source", "mock"),
            "error":         result.get("error"),
        }), 201

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Listado de informes kaizen ────────────────────────────────────────────────

@bp.get("/api/agents/kaizen-reports")
def list_kaizen_reports():
    """Devuelve los últimos 20 informes kaizen del site activo."""
    site_id, _, db = _site_db()

    try:
        rows = db.execute(
            """SELECT id, site_id, report_text, opportunities_json,
                      model_used, source, generated_at, read_at
               FROM kaizen_reports
               WHERE site_id = ?
               ORDER BY generated_at DESC
               LIMIT 20""",
            (site_id,),
        ).fetchall()

        reports = []
        for r in rows:
            d = dict(r)
            try:
                d["opportunities"] = json.loads(d["opportunities_json"] or "[]")
            except Exception:
                d["opportunities"] = []
            reports.append(d)

        return jsonify(reports)

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/agents/kaizen-reports/unread")
def unread_kaizen_reports():
    """Devuelve el conteo de informes kaizen no leídos del site activo."""
    site_id, _, db = _site_db()

    try:
        count = db.execute(
            "SELECT COUNT(*) FROM kaizen_reports WHERE site_id = ? AND read_at IS NULL",
            (site_id,),
        ).fetchone()[0]
        return jsonify({"unread": count})

    except Exception:
        return jsonify({"unread": 0})


@bp.post("/api/agents/kaizen-reports/<int:report_id>/read")
def mark_report_read(report_id: int):
    """Marca un informe como leído."""
    _, _, db = _site_db()

    try:
        updated = db.execute(
            "UPDATE kaizen_reports SET read_at = datetime('now') WHERE id = ? AND read_at IS NULL",
            (report_id,),
        ).rowcount
        db.commit()
        return jsonify({"ok": True, "updated": updated > 0})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Forzar un agente específico ───────────────────────────────────────────────

@bp.post("/api/assistant/suggest-agent")
def suggest_with_agent():
    """
    Llama directamente a un agente específico, saltándose el orquestador.
    Body JSON: { shift_id, query, category, agent_name, comment_id (opcional) }
    Permite al usuario forzar: "Pregunta solo al agente de mantenimiento".
    """
    data = request.get_json(silent=True) or {}
    shift_id   = data.get("shift_id")
    query      = (data.get("query") or "").strip()
    category   = data.get("category", "production")
    agent_name = (data.get("agent_name") or "").strip()
    comment_id = data.get("comment_id")

    if not query:
        return jsonify({"error": "query es obligatorio"}), 400
    if not agent_name:
        return jsonify({"error": "agent_name es obligatorio"}), 400

    site_id, db_path, db = _site_db()

    try:
        from agents.registry import get_agent
        from retriever import get_context

        agent = get_agent(agent_name, site_id=site_id, db_path=db_path)
        if agent is None:
            return jsonify({"error": f"Agente '{agent_name}' no encontrado"}), 404

        rag_chunks = get_context(query, top_k=4, db_path=db_path)
        sources = list({c["source_file"] for c in rag_chunks}) if rag_chunks else []

        result = agent.run(
            user_message=query,
            context_data={"shift_id": shift_id, "comment_id": comment_id, "category": category},
            rag_chunks=rag_chunks,
        )

        suggestion_id = None
        if shift_id:
            cur = db.execute(
                """INSERT INTO assistant_suggestions
                   (shift_id, comment_id, query_text, context_sources,
                    response_text, model_used, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    shift_id,
                    comment_id,
                    query,
                    json.dumps(sources, ensure_ascii=False),
                    result.get("response", ""),
                    result.get("model", "unknown"),
                    result.get("source", "mock"),
                ),
            )
            db.commit()
            suggestion_id = cur.lastrowid

        return jsonify({
            "id":          suggestion_id,
            "text":        result.get("response", ""),
            "sources":     sources,
            "model":       result.get("model", "unknown"),
            "source":      result.get("source", "mock"),
            "agents_used": [agent_name],
            "error":       result.get("error"),
        }), 201

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
