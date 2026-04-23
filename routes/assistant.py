from flask import Blueprint, jsonify, request, g
from database import get_db
from site_aggregator import SITES, DEFAULT_SITE
import json

bp = Blueprint("assistant", __name__)


@bp.post("/api/assistant/suggest")
def suggest():
    """
    Recibe un comentario y devuelve una sugerencia del asistente.
    Usa el Orchestrator para clasificar el mensaje, activar agentes
    especializados y sintetizar una respuesta final.
    Body JSON: { shift_id, comment_id (opcional), query, category }
    """
    data = request.get_json(silent=True) or {}
    shift_id   = data.get("shift_id")
    comment_id = data.get("comment_id")
    query      = (data.get("query") or "").strip()
    category   = data.get("category", "production")

    if not query:
        return jsonify({"error": "query es obligatorio"}), 400

    try:
        from agents.orchestrator import Orchestrator

        site_id = getattr(g, "current_site", DEFAULT_SITE)
        db_path = SITES.get(site_id, SITES[DEFAULT_SITE])["db_path"]

        orchestrator = Orchestrator(site_id=site_id, db_path=db_path)
        result = orchestrator.run(
            user_message=query,
            shift_id=shift_id,
            comment_id=comment_id,
            category=category,
        )

        sources = result.get("sources", [])
        suggestion_id = None

        # Solo guardar en BD si hay turno activo
        if shift_id:
            db = get_db()
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
                    result["text"],
                    result.get("model", "unknown"),
                    result.get("source", "mock"),
                ),
            )
            db.commit()
            suggestion_id = cur.lastrowid

        return jsonify({
            "id":          suggestion_id,
            "text":        result["text"],
            "sources":     sources,
            "model":       result.get("model", "unknown"),
            "source":      result.get("source", "mock"),
            "agents_used": result.get("agents_used", []),
            "reasoning":   result.get("reasoning"),
            "error":       result.get("error"),
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.post("/api/assistant/feedback/<int:suggestion_id>")
def feedback(suggestion_id: int):
    """
    Guarda el feedback del operario sobre una sugerencia.
    Body JSON: { feedback: "useful" | "not_useful" }
    """
    data     = request.get_json(silent=True) or {}
    fb_value = data.get("feedback")

    if fb_value not in ("useful", "not_useful"):
        return jsonify({"error": "feedback debe ser 'useful' o 'not_useful'"}), 400

    db      = get_db()
    updated = db.execute(
        "UPDATE assistant_suggestions SET feedback = ? WHERE id = ?",
        (fb_value, suggestion_id),
    ).rowcount
    db.commit()

    if not updated:
        return jsonify({"error": "Sugerencia no encontrada"}), 404

    return jsonify({"ok": True, "feedback": fb_value})


@bp.get("/api/assistant/suggestions/<int:shift_id>")
def list_suggestions(shift_id: int):
    """Devuelve todas las sugerencias de un turno."""
    db   = get_db()
    rows = db.execute(
        """SELECT id, comment_id, query_text, context_sources,
                  response_text, model_used, source, feedback, created_at
           FROM assistant_suggestions
           WHERE shift_id = ?
           ORDER BY created_at ASC""",
        (shift_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])
