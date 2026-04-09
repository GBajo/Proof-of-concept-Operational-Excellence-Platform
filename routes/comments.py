from flask import Blueprint, jsonify, request, g
import logging
from models.comment import create_comment, get_comments_by_shift, delete_comment
from models.shift import get_shift_by_id
from database import get_db

bp = Blueprint("comments", __name__)
logger = logging.getLogger(__name__)


@bp.post("/api/comments")
def add_comment():
    data = request.get_json(silent=True) or {}
    shift_id = data.get("shift_id")
    operator_id = data.get("operator_id")
    text = (data.get("text") or "").strip()
    category = data.get("category", "production")
    source = data.get("source", "voice")

    if not shift_id or not operator_id or not text:
        return jsonify({"error": "shift_id, operator_id y text son obligatorios"}), 400

    if category not in ("safety", "quality", "production", "maintenance"):
        return jsonify({"error": "Categoría no válida"}), 400

    try:
        comment = create_comment(shift_id, operator_id, text, category, source)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # ── Trigger: notificar a Teams si es un comentario de mantenimiento ────────
    if category == "maintenance":
        try:
            from notifications import notify_maintenance_comment
            from site_aggregator import DEFAULT_SITE
            site_id = getattr(g, "current_site", DEFAULT_SITE)
            shift = get_shift_by_id(shift_id)
            operator_name = (shift or {}).get("operator_name", f"Operador #{operator_id}")
            line_number = (shift or {}).get("line_number", "?")
            base_url = request.host_url.rstrip("/")
            notify_maintenance_comment(
                comment_text=text,
                operator_name=operator_name,
                line_number=line_number,
                shift_id=shift_id,
                site_id=site_id,
                base_url=base_url,
            )
        except Exception:
            logger.exception("Error al enviar notificación de mantenimiento")

    return jsonify(comment), 201


@bp.get("/api/comments/<int:shift_id>")
def list_comments(shift_id: int):
    category = request.args.get("category")
    return jsonify(get_comments_by_shift(shift_id, category=category))


@bp.delete("/api/comments/<int:comment_id>")
def remove_comment(comment_id: int):
    if not delete_comment(comment_id):
        return jsonify({"error": "Comentario no encontrado"}), 404
    return jsonify({"ok": True})
