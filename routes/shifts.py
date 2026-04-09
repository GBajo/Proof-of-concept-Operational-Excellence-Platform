from flask import Blueprint, jsonify, request, g
from models.shift import (
    create_shift, get_shift_by_id, get_shifts,
    get_active_shift_by_line, end_shift, update_shift,
)
from models.comment import get_comments_by_shift
from models.kpi import calculate_oee

bp = Blueprint("shifts", __name__)


@bp.get("/api/shifts")
def list_shifts():
    status = request.args.get("status")
    line = request.args.get("line", type=int)
    return jsonify(get_shifts(status=status, line=line))


@bp.post("/api/shifts")
def start_shift():
    data = request.get_json(silent=True) or {}
    operator_id = data.get("operator_id")
    line_number = data.get("line_number")
    shift_type = data.get("shift_type", "morning")

    if not operator_id or not line_number:
        return jsonify({"error": "operator_id y line_number son obligatorios"}), 400

    # Verificar que no haya turno activo en la línea
    if get_active_shift_by_line(line_number):
        return jsonify({"error": f"La línea {line_number} ya tiene un turno activo"}), 409

    try:
        shift_id = create_shift(operator_id, line_number, shift_type)
    except Exception as e:
        err = str(e)
        if "UNIQUE constraint failed" in err:
            return jsonify({"error": f"La línea {line_number} ya tiene un turno activo"}), 409
        return jsonify({"error": err}), 400

    return jsonify(get_shift_by_id(shift_id)), 201


@bp.get("/api/shifts/active")
def active_shift():
    line = request.args.get("line", type=int)
    if not line:
        return jsonify({"error": "Parámetro 'line' requerido"}), 400
    shift = get_active_shift_by_line(line)
    if not shift:
        return jsonify({"error": "No hay turno activo en esta línea"}), 404
    return jsonify(shift)


@bp.get("/api/shifts/<int:shift_id>")
def detail_shift(shift_id: int):
    shift = get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Turno no encontrado"}), 404
    shift["comments"] = get_comments_by_shift(shift_id)
    shift["kpi_summary"] = calculate_oee(shift_id)
    return jsonify(shift)


@bp.patch("/api/shifts/<int:shift_id>")
def update_shift_endpoint(shift_id: int):
    shift = get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Turno no encontrado"}), 404

    data = request.get_json(silent=True) or {}
    allowed = {"handover_notes", "status"}
    fields = {k: v for k, v in data.items() if k in allowed}

    if "status" in fields and fields["status"] in ("completed", "interrupted"):
        end_shift(shift_id, fields.get("handover_notes"), fields["status"])
        # ── Trigger: notificar fin de turno a Teams ────────────────────────────
        try:
            from notifications import notify_shift_end
            from site_aggregator import DEFAULT_SITE
            updated = get_shift_by_id(shift_id)
            oee_data = calculate_oee(shift_id)
            oee_val = (oee_data or {}).get("oee")
            site_id = getattr(g, "current_site", DEFAULT_SITE)
            base_url = request.host_url.rstrip("/")
            notify_shift_end(
                operator_name=(updated or {}).get("operator_name", ""),
                line_number=(updated or shift).get("line_number", "?"),
                shift_id=shift_id,
                oee_value=oee_val,
                site_id=site_id,
                base_url=base_url,
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Error al enviar notificación fin de turno")
    else:
        update_shift(shift_id, fields)

    return jsonify(get_shift_by_id(shift_id))


@bp.get("/api/shifts/<int:shift_id>/summary")
def shift_summary(shift_id: int):
    shift = get_shift_by_id(shift_id)
    if not shift:
        return jsonify({"error": "Turno no encontrado"}), 404

    comments = get_comments_by_shift(shift_id)
    kpi = calculate_oee(shift_id)

    # Agrupar comentarios por categoría
    by_category: dict = {}
    for c in comments:
        by_category.setdefault(c["category"], []).append(c)

    return jsonify({
        "shift": shift,
        "kpi": kpi,
        "comments": comments,
        "comments_by_category": by_category,
        "total_comments": len(comments),
    })
