"""routes/tiers.py — Gestión de Tiers jerárquicos por planta."""
from flask import Blueprint, render_template, jsonify, request, g
from database import get_db  # noqa: F401 — importado por modelos
from site_aggregator import DEFAULT_SITE

bp = Blueprint("tiers", __name__)


def _site_id() -> str:
    return getattr(g, "current_site", DEFAULT_SITE)


# ── Página principal ──────────────────────────────────────────────────────────

@bp.get("/admin/tiers")
def tiers_admin():
    from models.operator import get_all_operators
    return render_template("admin/tiers.html", operators=get_all_operators())


# ── API: Jerarquía ────────────────────────────────────────────────────────────

@bp.get("/api/tiers/hierarchy")
def api_hierarchy():
    from models.tier import get_site_hierarchy
    return jsonify(get_site_hierarchy(_site_id()))


# ── API: Tiers ────────────────────────────────────────────────────────────────

@bp.get("/api/tiers/tiers")
def api_list_tiers():
    from models.tier import get_tiers
    return jsonify(get_tiers(_site_id()))


@bp.post("/api/tiers/tiers")
def api_create_tier():
    from models.tier import create_tier
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "El nombre es obligatorio."}), 400
    try:
        tier_level = int(data.get("tier_level", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Nivel de tier inválido."}), 400
    if tier_level not in (0, 1, 2):
        return jsonify({"ok": False, "message": "El nivel debe ser 0, 1 o 2."}), 400
    new_id = create_tier(_site_id(), tier_level, name, data.get("description") or "")
    return jsonify({"ok": True, "id": new_id})


@bp.put("/api/tiers/tiers/<int:tier_id>")
def api_update_tier(tier_id: int):
    from models.tier import update_tier
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "El nombre es obligatorio."}), 400
    update_tier(tier_id, name, data.get("description") or "")
    return jsonify({"ok": True})


@bp.delete("/api/tiers/tiers/<int:tier_id>")
def api_delete_tier(tier_id: int):
    from models.tier import delete_tier
    delete_tier(tier_id)
    return jsonify({"ok": True})


# ── API: Grupos ───────────────────────────────────────────────────────────────

@bp.get("/api/tiers/groups")
def api_list_groups():
    from models.tier import get_tier_groups
    tier_level = request.args.get("tier_level", type=int)
    return jsonify(get_tier_groups(_site_id(), tier_level))


@bp.post("/api/tiers/groups")
def api_create_group():
    from models.tier import create_tier_group
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "El nombre es obligatorio."}), 400
    try:
        tier_id = int(data["tier_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "message": "tier_id inválido."}), 400
    new_id = create_tier_group(
        _site_id(), tier_id, name,
        data.get("description") or "",
        data.get("group_type") or "",
    )
    return jsonify({"ok": True, "id": new_id})


@bp.put("/api/tiers/groups/<int:group_id>")
def api_update_group(group_id: int):
    from models.tier import update_tier_group
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "El nombre es obligatorio."}), 400
    update_tier_group(group_id, name, data.get("description") or "", data.get("group_type") or "")
    return jsonify({"ok": True})


@bp.delete("/api/tiers/groups/<int:group_id>")
def api_delete_group(group_id: int):
    from models.tier import delete_tier_group
    ok, msg = delete_tier_group(group_id)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 409)


# ── API: Asignaciones ─────────────────────────────────────────────────────────

@bp.post("/api/tiers/groups/<int:group_id>/assign")
def api_assign_group(group_id: int):
    from models.tier import assign_group
    data = request.get_json(silent=True) or {}
    try:
        child_id = int(data["child_group_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "message": "child_group_id inválido."}), 400
    ok, msg = assign_group(group_id, child_id)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@bp.post("/api/tiers/groups/<int:group_id>/unassign")
def api_unassign_group(group_id: int):
    from models.tier import unassign_group
    data = request.get_json(silent=True) or {}
    try:
        child_id = int(data["child_group_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "message": "child_group_id inválido."}), 400
    unassign_group(group_id, child_id)
    return jsonify({"ok": True})


# ── API: Miembros ─────────────────────────────────────────────────────────────

@bp.get("/api/tiers/groups/<int:group_id>/members")
def api_group_members(group_id: int):
    from models.tier import get_group_members
    return jsonify(get_group_members(group_id))


@bp.post("/api/tiers/groups/<int:group_id>/members")
def api_assign_member(group_id: int):
    from models.tier import assign_member
    data = request.get_json(silent=True) or {}
    try:
        op_id = int(data["operator_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "message": "operator_id inválido."}), 400
    role = data.get("role", "member")
    if role not in ("leader", "member", "support"):
        role = "member"
    ok, msg = assign_member(group_id, op_id, role)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 409)


@bp.delete("/api/tiers/groups/<int:group_id>/members/<int:operator_id>")
def api_unassign_member(group_id: int, operator_id: int):
    from models.tier import unassign_member
    unassign_member(group_id, operator_id)
    return jsonify({"ok": True})


# ── API: Escalado ─────────────────────────────────────────────────────────────

@bp.get("/api/tiers/escalation-paths")
def api_list_escalation():
    from models.tier import get_escalation_paths
    return jsonify(get_escalation_paths(_site_id()))


@bp.post("/api/tiers/escalation-paths")
def api_create_escalation():
    from models.tier import create_escalation_path
    data = request.get_json(silent=True) or {}
    try:
        from_id = int(data["from_group_id"])
        to_id   = int(data["to_group_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "message": "from_group_id / to_group_id inválidos."}), 400
    esc_type = data.get("escalation_type", "general")
    channel  = data.get("notification_channel", "app")
    minutes  = data.get("auto_escalate_after_minutes")
    if minutes is not None:
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            minutes = None
    new_id = create_escalation_path(_site_id(), from_id, to_id, esc_type, minutes, channel)
    return jsonify({"ok": True, "id": new_id})


@bp.delete("/api/tiers/escalation-paths/<int:path_id>")
def api_delete_escalation(path_id: int):
    from models.tier import delete_escalation_path
    delete_escalation_path(path_id)
    return jsonify({"ok": True})
