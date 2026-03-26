from flask import Blueprint, jsonify
from models.operator import get_all_operators, get_operator_by_id

bp = Blueprint("operators", __name__)


@bp.get("/api/operators")
def list_operators():
    return jsonify(get_all_operators())


@bp.get("/api/operators/<int:operator_id>")
def detail_operator(operator_id: int):
    op = get_operator_by_id(operator_id)
    if not op:
        return jsonify({"error": "Operario no encontrado"}), 404
    return jsonify(op)
