"""routes/equipment_admin.py — Pantalla de administración de equipos."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, render_template, request

from database import get_db  # noqa: F401
from site_aggregator import DEFAULT_SITE

bp = Blueprint("equipment_admin", __name__)


def _site_id() -> str:
    return getattr(g, "current_site", DEFAULT_SITE)


# ── Página ────────────────────────────────────────────────────────────────────

@bp.get("/admin/equipment")
def equipment_page():
    from models.equipment import get_all_equipment_for_site, VALID_STATUSES, VALID_TYPES
    from models.tier import get_tier_groups

    site_id = _site_id()
    equipment = get_all_equipment_for_site(site_id)
    tier0_groups = get_tier_groups(site_id, tier_level=0)

    # Agrupar equipos por group_id para la vista
    groups_map: dict[int, dict] = {}
    for g0 in tier0_groups:
        groups_map[g0["id"]] = {"group": g0, "items": []}
    ungrouped: list[dict] = []
    for eq in equipment:
        gid = eq["group_id"]
        if gid in groups_map:
            groups_map[gid]["items"].append(eq)
        else:
            ungrouped.append(eq)

    grouped = [v for v in groups_map.values() if v["items"]]

    return render_template(
        "admin/equipment.html",
        grouped=grouped,
        ungrouped=ungrouped,
        tier0_groups=tier0_groups,
        valid_statuses=VALID_STATUSES,
        valid_types=VALID_TYPES,
        total=len(equipment),
    )


# ── API: editar equipo completo ───────────────────────────────────────────────

@bp.put("/api/equipment/<int:equipment_id>")
def api_update_equipment(equipment_id: int):
    from models.equipment import update_equipment, get_equipment_by_id, VALID_STATUSES, VALID_TYPES
    eq = get_equipment_by_id(equipment_id)
    if not eq:
        return jsonify({"ok": False, "message": "Equipo no encontrado."}), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "El nombre es obligatorio."}), 400

    eq_type = data.get("equipment_type", "other")
    if eq_type not in VALID_TYPES:
        eq_type = "other"
    status = data.get("status", "running")
    if status not in VALID_STATUSES:
        status = "running"

    speed = data.get("nominal_speed")
    if speed is not None:
        try:
            speed = float(speed) if str(speed).strip() else None
        except (TypeError, ValueError):
            speed = None

    # group_id update (must belong to same site)
    group_id_raw = data.get("group_id")
    if group_id_raw is not None:
        try:
            new_gid = int(group_id_raw)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "message": "group_id inválido."}), 400
        from database import get_db as _get_db
        row = _get_db().execute(
            "SELECT id FROM tier_groups WHERE id=? AND site_id=?",
            (new_gid, _site_id()),
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "message": "Grupo no válido para este site."}), 400
        # Update group_id separately
        _get_db().execute("UPDATE equipment SET group_id=? WHERE id=?", (new_gid, equipment_id))
        _get_db().commit()

    update_equipment(
        equipment_id,
        name=name,
        equipment_type=eq_type,
        model=data.get("model") or None,
        manufacturer=data.get("manufacturer") or None,
        serial_number=data.get("serial_number") or None,
        status=status,
        nominal_speed=speed,
        installed_date=data.get("installed_date") or None,
        last_maintenance=data.get("last_maintenance") or None,
        notes=data.get("notes") or None,
    )
    return jsonify({"ok": True})


# ── API: cambio de estado masivo ──────────────────────────────────────────────

@bp.post("/api/equipment/bulk-status")
def api_bulk_status():
    from models.equipment import bulk_update_status, VALID_STATUSES
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in VALID_STATUSES:
        return jsonify({"ok": False, "message": f"Estado inválido. Válidos: {', '.join(VALID_STATUSES)}"}), 400
    ids_raw = data.get("ids") or []
    if not isinstance(ids_raw, list):
        return jsonify({"ok": False, "message": "ids debe ser una lista."}), 400
    try:
        ids = [int(i) for i in ids_raw]
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "ids contiene valores no numéricos."}), 400
    if not ids:
        return jsonify({"ok": False, "message": "No se han seleccionado equipos."}), 400
    updated = bulk_update_status(ids, status, _site_id())
    return jsonify({"ok": True, "updated": updated})
