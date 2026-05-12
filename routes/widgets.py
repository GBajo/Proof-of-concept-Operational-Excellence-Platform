"""Blueprint API para gestión y renderizado de widgets del dashboard."""
from __future__ import annotations

import json

from flask import Blueprint, g, jsonify, request

bp = Blueprint("widgets", __name__)


def _render_layout(layout: dict, site_id: str, line_number: int | None) -> list[list[dict]]:
    """Renderiza todas las filas de un layout; devuelve lista de filas con widgets renderizados."""
    from widgets.base import create_widget

    result = []
    for row_idx, row in enumerate(layout.get("rows", [])):
        row_widgets = []
        for w_idx, w_cfg in enumerate(row.get("widgets", [])):
            widget = create_widget(w_cfg["type"], w_cfg)
            rendered = widget.render(site_id, line_number)
            rendered["id"] = f"w-{row_idx}-{w_idx}"
            row_widgets.append(rendered)
        result.append(row_widgets)
    return result


@bp.get("/api/widgets/layout")
def get_layout():
    """Devuelve la configuración de layout (sin renderizar) para la línea activa."""
    from models.dashboard_config import get_dashboard_config

    site_id = getattr(g, "current_site", "alcobendas")
    line_number = request.args.get("line_number", type=int)

    cfg = get_dashboard_config(site_id, line_number)
    return jsonify({
        "layout": cfg["layout"],
        "equipment_type": cfg["equipment_type"],
        "config_name": cfg["config_name"],
        "source": cfg["source"],
    })


@bp.get("/api/widgets/render")
def render_widgets():
    """Renderiza todos los widgets para una línea y devuelve sus ECharts configs."""
    from models.dashboard_config import get_dashboard_config

    site_id = getattr(g, "current_site", "alcobendas")
    line_number = request.args.get("line_number", type=int)
    equipment_type = request.args.get("equipment_type")

    if equipment_type:
        from models.dashboard_config import get_config_for_equipment
        cfg_data = get_config_for_equipment(site_id, equipment_type)
        layout = cfg_data["layout"]
    else:
        cfg = get_dashboard_config(site_id, line_number)
        layout = cfg["layout"]

    rows = _render_layout(layout, site_id, line_number)
    return jsonify({"rows": rows})


@bp.get("/api/widgets/refresh/<widget_type>")
def refresh_widget(widget_type: str):
    """Refresca un único widget; útil para auto-refresh por intervalo."""
    from widgets.base import create_widget

    site_id = getattr(g, "current_site", "alcobendas")
    line_number = request.args.get("line_number", type=int)
    raw_params = request.args.get("params", "{}")
    try:
        params = json.loads(raw_params)
    except Exception:
        params = {}

    widget = create_widget(widget_type, {"params": params, "size": request.args.get("size", "small")})
    rendered = widget.render(site_id, line_number)
    return jsonify(rendered)


@bp.get("/api/widgets/configs")
def list_configs():
    """Lista las configuraciones guardadas para el site activo."""
    from models.dashboard_config import list_configs as _list

    site_id = getattr(g, "current_site", "alcobendas")
    return jsonify({"configs": _list(site_id)})


@bp.post("/api/widgets/configs")
def save_config():
    """Guarda o actualiza una configuración de dashboard."""
    from models.dashboard_config import save_config as _save

    site_id = getattr(g, "current_site", "alcobendas")
    body = request.get_json(force=True, silent=True) or {}

    layout = body.get("layout")
    if not layout:
        return jsonify({"error": "layout requerido"}), 400

    config_id = _save(
        site_id=site_id,
        layout=layout,
        equipment_type=body.get("equipment_type", "generic"),
        config_name=body.get("config_name", "Mi Dashboard"),
        line_number=body.get("line_number"),
        created_by=body.get("created_by", "user"),
    )
    return jsonify({"id": config_id, "ok": True}), 201


@bp.get("/api/widgets/registry")
def widget_registry():
    """Devuelve el catálogo completo de widgets disponibles."""
    from widgets.registry import WIDGET_REGISTRY

    return jsonify({"widgets": WIDGET_REGISTRY})
