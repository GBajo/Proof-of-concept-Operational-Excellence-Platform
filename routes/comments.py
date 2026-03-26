from flask import Blueprint, jsonify, request
from models.comment import create_comment, get_comments_by_shift, delete_comment

bp = Blueprint("comments", __name__)


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
