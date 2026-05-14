"""routes/group_view.py — Pantalla de grupo con 3 tabs: Dashboard, SQDCP, Equipment."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, g, jsonify, render_template, request

from database import get_db
from site_aggregator import DEFAULT_SITE

bp = Blueprint("group_view", __name__)


def _site_id() -> str:
    return getattr(g, "current_site", DEFAULT_SITE)


# ── Página principal: /group/<group_id> ───────────────────────────────────────

@bp.get("/group/<int:group_id>")
def group_page(group_id: int):
    from models.tier import get_tier_group_by_id, get_group_parents, get_group_children
    from models.equipment import get_equipment_by_group, get_equipment_status_summary

    group = get_tier_group_by_id(group_id)
    if not group:
        abort(404)

    # Breadcrumb: walk up to root
    breadcrumb: list[dict] = [group]
    parents = get_group_parents(group_id)
    if parents:
        breadcrumb.insert(0, parents[0])
        grandparents = get_group_parents(parents[0]["id"])
        if grandparents:
            breadcrumb.insert(0, grandparents[0])

    # Child groups (for T1/T2 — info display)
    children = get_group_children(group_id)

    # Equipment for this group
    equipment = get_equipment_by_group(group_id)
    eq_summary = get_equipment_status_summary(group_id)

    # Dashboard widgets
    site_id = _site_id()
    line_number = request.args.get("line", type=int)
    widget_rows = _build_widget_rows(site_id, line_number, request.args.get("equipment"))

    # SQDCP data
    from site_aggregator import SITES
    site_lines = SITES.get(site_id, SITES[DEFAULT_SITE]).get("lines", list(range(1, 6)))
    sqdcp_line = request.args.get("sqdcp_line", type=int) or (site_lines[0] if site_lines else 1)
    sqdcp_date = request.args.get("sqdcp_date", date.today().isoformat())
    sqdcp_period = request.args.get("sqdcp_period", "day")
    if sqdcp_period not in ("day", "week", "month"):
        sqdcp_period = "day"

    from routes.sqdcp import _compute_pillars, _get_shifts, _get_actions, PILLARS
    pillars = _compute_pillars(sqdcp_line, sqdcp_date, sqdcp_period)
    shifts = _get_shifts(sqdcp_line, sqdcp_date)
    actions = _get_actions(sqdcp_line, sqdcp_date)

    active_tab = request.args.get("tab", "dashboard")
    if active_tab not in ("dashboard", "sqdcp", "equipment"):
        active_tab = "dashboard"

    return render_template(
        "group/index.html",
        group=group,
        breadcrumb=breadcrumb,
        children=children,
        equipment=equipment,
        eq_summary=eq_summary,
        widget_rows=widget_rows,
        line_number=line_number,
        site_lines=site_lines,
        pillars=pillars,
        pillar_keys=PILLARS,
        shifts=shifts,
        actions=actions,
        selected_line=sqdcp_line,
        selected_date=sqdcp_date,
        selected_period=sqdcp_period,
        today=date.today().isoformat(),
        active_tab=active_tab,
    )


def _build_widget_rows(site_id: str, line_number, equipment_type) -> list[list[dict]]:
    from models.dashboard_config import get_dashboard_config, get_config_for_equipment
    from widgets.base import create_widget
    from widgets.registry import WIDGET_REGISTRY

    if equipment_type:
        cfg_data = get_config_for_equipment(site_id, equipment_type)
        layout = cfg_data["layout"]
    else:
        layout = get_dashboard_config(site_id, line_number)["layout"]

    widget_rows: list[list[dict]] = []
    for row_idx, row in enumerate(layout.get("rows", [])):
        row_data: list[dict] = []
        for w_idx, w_cfg in enumerate(row.get("widgets", [])):
            widget = create_widget(w_cfg["type"], w_cfg)
            rendered = widget.render(site_id, line_number)
            rendered["id"] = f"gw-{row_idx}-{w_idx}"
            if not rendered.get("title"):
                rendered["title"] = WIDGET_REGISTRY.get(w_cfg["type"], {}).get("name", w_cfg["type"])
            row_data.append(rendered)
        widget_rows.append(row_data)
    return widget_rows


# ── API: cambiar estado de equipo ─────────────────────────────────────────────

@bp.put("/api/equipment/<int:equipment_id>/status")
def api_update_status(equipment_id: int):
    from models.equipment import update_equipment_status, VALID_STATUSES
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in VALID_STATUSES:
        return jsonify({"ok": False, "message": f"Estado inválido. Válidos: {', '.join(VALID_STATUSES)}"}), 400
    ok = update_equipment_status(equipment_id, status)
    return jsonify({"ok": ok})


# ── API: CRUD equipos ─────────────────────────────────────────────────────────

@bp.post("/api/equipment")
def api_create_equipment():
    from models.equipment import create_equipment, VALID_STATUSES, VALID_TYPES
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "El nombre es obligatorio."}), 400
    try:
        group_id = int(data["group_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "message": "group_id inválido."}), 400
    eq_type = data.get("equipment_type", "other")
    if eq_type not in VALID_TYPES:
        eq_type = "other"
    status = data.get("status", "running")
    if status not in VALID_STATUSES:
        status = "running"
    speed = data.get("nominal_speed")
    if speed is not None:
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            speed = None
    new_id = create_equipment(
        site_id=_site_id(),
        group_id=group_id,
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
    return jsonify({"ok": True, "id": new_id}), 201


@bp.delete("/api/equipment/<int:equipment_id>")
def api_delete_equipment(equipment_id: int):
    from models.equipment import delete_equipment
    delete_equipment(equipment_id)
    return jsonify({"ok": True})
