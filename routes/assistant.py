from flask import Blueprint, jsonify, request
from database import get_db
import json

bp = Blueprint("assistant", __name__)


@bp.post("/api/assistant/suggest")
def suggest():
    """
    Recibe un comentario y devuelve una sugerencia del asistente.
    Body JSON: { shift_id, comment_id (opcional), query, category }
    """
    data = request.get_json(silent=True) or {}
    shift_id   = data.get("shift_id")
    comment_id = data.get("comment_id")
    query      = (data.get("query") or "").strip()
    category   = data.get("category", "production")

    if not shift_id or not query:
        return jsonify({"error": "shift_id y query son obligatorios"}), 400

    try:
        from retriever import get_context
        from llm_client import ask_assistant

        chunks  = get_context(query, top_k=4)
        result  = ask_assistant(query, chunks, category=category)

        sources = list({c["source_file"] for c in chunks}) if chunks else []

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
            "id":       suggestion_id,
            "text":     result["text"],
            "sources":  sources,
            "model":    result.get("model", "unknown"),
            "source":   result.get("source", "mock"),
            "error":    result.get("error"),
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
