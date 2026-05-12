"""Modelo de datos para configuraciones de dashboards configurables por línea."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

# ── Layouts por tipo de equipo ────────────────────────────────────────────────

_BLISTER_LAYOUT = {
    "rows": [
        {
            "widgets": [
                {"type": "oee_gauge",       "size": "small",  "params": {"thresholds": [60, 85], "title": "OEE"}},
                {"type": "production_bars", "size": "medium", "params": {"days": 7, "title": "Producción vs Objetivo"}},
            ]
        },
        {
            "widgets": [
                {"type": "kpi_card", "size": "small", "params": {"metric": "reject_rate",      "title": "Tasa Rechazo",  "unit": "%",   "thresholds": [5, 2]}},
                {"type": "kpi_card", "size": "small", "params": {"metric": "units_produced",   "title": "Unidades",      "unit": "uds", "thresholds": [10000, 15000]}},
                {"type": "kpi_card", "size": "small", "params": {"metric": "downtime_minutes", "title": "Paros",         "unit": "min", "thresholds": [60, 30]}},
            ]
        },
        {
            "widgets": [
                {"type": "trend_line",   "size": "large",  "params": {"metric": "oee",   "period": "7d",  "title": "Tendencia OEE"}},
            ]
        },
        {
            "widgets": [
                {"type": "pareto_chart", "size": "large",  "params": {"days": 30, "max_causes": 8, "title": "Pareto de Paradas"}},
            ]
        },
    ]
}

_VIAL_LAYOUT = {
    "rows": [
        {
            "widgets": [
                {"type": "oee_gauge",   "size": "small", "params": {"thresholds": [65, 85], "title": "OEE"}},
                {"type": "speed_gauge", "size": "small", "params": {"nominal_speed": 200,   "title": "Velocidad"}},
                {"type": "reject_donut","size": "small", "params": {"days": 7,              "title": "Calidad"}},
            ]
        },
        {
            "widgets": [
                {"type": "trend_line", "size": "medium", "params": {"metric": "oee",          "period": "7d", "title": "Tendencia OEE"}},
                {"type": "kpi_card",  "size": "small",  "params": {"metric": "availability", "title": "Disponibilidad", "unit": "%", "thresholds": [80, 90]}},
            ]
        },
        {
            "widgets": [
                {"type": "downtime_heatmap", "size": "large", "params": {"days": 14, "title": "Heatmap de Paradas"}},
            ]
        },
    ]
}

_AUTOINJECTOR_LAYOUT = {
    "rows": [
        {
            "widgets": [
                {"type": "oee_gauge",       "size": "small",  "params": {"thresholds": [65, 85], "title": "OEE"}},
                {"type": "production_bars", "size": "medium", "params": {"days": 7,              "title": "Producción"}},
            ]
        },
        {
            "widgets": [
                {"type": "kpi_card", "size": "small", "params": {"metric": "quality",       "title": "Calidad",      "unit": "%",   "thresholds": [90, 95]}},
                {"type": "kpi_card", "size": "small", "params": {"metric": "reject_rate",   "title": "Defectos",     "unit": "%",   "thresholds": [3, 1]}},
                {"type": "kpi_card", "size": "small", "params": {"metric": "availability",  "title": "Disponib.",    "unit": "%",   "thresholds": [80, 90]}},
            ]
        },
        {
            "widgets": [
                {"type": "trend_line",    "size": "large", "params": {"metric": "units_produced", "period": "30d", "title": "Tendencia Producción"}},
            ]
        },
        {
            "widgets": [
                {"type": "sqdcp_summary", "size": "large", "params": {"days": 7, "title": "SQDCP"}},
            ]
        },
    ]
}

_GENERIC_LAYOUT = {
    "rows": [
        {
            "widgets": [
                {"type": "oee_gauge",     "size": "small", "params": {"thresholds": [60, 85], "title": "OEE"}},
                {"type": "kpi_card",      "size": "small", "params": {"metric": "units_produced",   "title": "Producción", "unit": "uds"}},
                {"type": "kpi_card",      "size": "small", "params": {"metric": "reject_rate",      "title": "Rechazo",    "unit": "%", "thresholds": [5, 2]}},
            ]
        },
        {
            "widgets": [
                {"type": "trend_line", "size": "large", "params": {"metric": "oee", "period": "7d", "title": "Tendencia OEE"}},
            ]
        },
        {
            "widgets": [
                {"type": "production_bars", "size": "medium", "params": {"days": 7,  "title": "Producción vs Objetivo"}},
                {"type": "reject_donut",    "size": "small",  "params": {"days": 7,  "title": "Rechazos"}},
            ]
        },
    ]
}

DEFAULT_CONFIGS: dict[str, dict] = {
    "blister":      {"layout": _BLISTER_LAYOUT,      "name": "Línea Blíster"},
    "vial":         {"layout": _VIAL_LAYOUT,          "name": "Viales / Inyectables"},
    "autoinjector": {"layout": _AUTOINJECTOR_LAYOUT,  "name": "Autoinyectores / Plumas"},
    "generic":      {"layout": _GENERIC_LAYOUT,       "name": "Genérico"},
}

# ── Creación de tabla ──────────────────────────────────────────────────────────

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_configs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id        TEXT    NOT NULL,
    line_number    INTEGER,
    equipment_type TEXT    NOT NULL DEFAULT 'generic',
    config_name    TEXT    NOT NULL,
    layout_json    TEXT    NOT NULL,
    created_by     TEXT    DEFAULT 'system',
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    is_default     INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_IDX = """
CREATE INDEX IF NOT EXISTS idx_dashcfg_site_line
    ON dashboard_configs (site_id, line_number);
"""


def create_dashboard_tables(db_path: str) -> None:
    """Crea la tabla dashboard_configs en la BD indicada (idempotente)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE_SQL)
        conn.execute(_CREATE_IDX)
        conn.commit()
    finally:
        conn.close()


# ── Seed de configs por defecto ───────────────────────────────────────────────

def seed_default_configs() -> None:
    """Inserta las configuraciones por defecto si la tabla está vacía."""
    from site_aggregator import SITES
    from database import get_db

    for site_id in SITES:
        db = get_db(site_id)
        count = db.execute("SELECT COUNT(*) FROM dashboard_configs WHERE site_id=? AND is_default=1", (site_id,)).fetchone()[0]
        if count > 0:
            continue
        now = datetime.utcnow().isoformat(timespec="seconds")
        for equip_type, cfg in DEFAULT_CONFIGS.items():
            db.execute(
                """INSERT INTO dashboard_configs
                   (site_id, line_number, equipment_type, config_name, layout_json, created_by, created_at, updated_at, is_default)
                   VALUES (?,NULL,?,?,?,?,?,?,1)""",
                (site_id, equip_type, cfg["name"], json.dumps(cfg["layout"]), "system", now, now),
            )
        db.commit()


# ── Queries ────────────────────────────────────────────────────────────────────

def get_dashboard_config(site_id: str, line_number: int | None = None) -> dict:
    """
    Devuelve el layout JSON para site+línea.
    Orden de búsqueda: config específica de línea → default de equipo → generic.
    """
    from database import get_db

    db = get_db(site_id)

    # 1. Config específica de la línea
    if line_number:
        row = db.execute(
            "SELECT layout_json, equipment_type, config_name FROM dashboard_configs "
            "WHERE site_id=? AND line_number=? ORDER BY updated_at DESC LIMIT 1",
            (site_id, line_number),
        ).fetchone()
        if row:
            return {
                "layout": json.loads(row["layout_json"]),
                "equipment_type": row["equipment_type"],
                "config_name": row["config_name"],
                "source": "line_specific",
            }

    # 2. Default genérico del site
    row = db.execute(
        "SELECT layout_json, equipment_type, config_name FROM dashboard_configs "
        "WHERE site_id=? AND is_default=1 AND equipment_type='generic' LIMIT 1",
        (site_id,),
    ).fetchone()
    if row:
        return {
            "layout": json.loads(row["layout_json"]),
            "equipment_type": row["equipment_type"],
            "config_name": row["config_name"],
            "source": "default",
        }

    # 3. Fallback en memoria (nunca falla)
    return {
        "layout": _GENERIC_LAYOUT,
        "equipment_type": "generic",
        "config_name": "Genérico",
        "source": "fallback",
    }


def get_config_for_equipment(site_id: str, equipment_type: str) -> dict:
    """Devuelve el layout para un tipo de equipo concreto."""
    from database import get_db

    db = get_db(site_id)
    row = db.execute(
        "SELECT layout_json, config_name FROM dashboard_configs "
        "WHERE site_id=? AND equipment_type=? AND is_default=1 LIMIT 1",
        (site_id, equipment_type),
    ).fetchone()
    if row:
        return {"layout": json.loads(row["layout_json"]), "config_name": row["config_name"]}
    cfg = DEFAULT_CONFIGS.get(equipment_type, DEFAULT_CONFIGS["generic"])
    return {"layout": cfg["layout"], "config_name": cfg["name"]}


def list_configs(site_id: str) -> list[dict]:
    """Lista todas las configuraciones disponibles para un site."""
    from database import get_db

    db = get_db(site_id)
    rows = db.execute(
        "SELECT id, site_id, line_number, equipment_type, config_name, is_default, updated_at "
        "FROM dashboard_configs WHERE site_id=? ORDER BY is_default DESC, line_number ASC",
        (site_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_config(
    site_id: str,
    layout: dict,
    equipment_type: str = "generic",
    config_name: str = "Mi Dashboard",
    line_number: int | None = None,
    created_by: str = "user",
) -> int:
    """Guarda una configuración de dashboard. Devuelve el id insertado."""
    from database import get_db

    db = get_db(site_id)
    now = datetime.utcnow().isoformat(timespec="seconds")

    # Actualiza si ya existe config para esa línea
    if line_number:
        existing = db.execute(
            "SELECT id FROM dashboard_configs WHERE site_id=? AND line_number=? AND is_default=0 LIMIT 1",
            (site_id, line_number),
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE dashboard_configs SET layout_json=?,equipment_type=?,config_name=?,updated_at=? WHERE id=?",
                (json.dumps(layout), equipment_type, config_name, now, existing["id"]),
            )
            db.commit()
            return existing["id"]

    cur = db.execute(
        "INSERT INTO dashboard_configs (site_id,line_number,equipment_type,config_name,layout_json,created_by,created_at,updated_at,is_default) "
        "VALUES (?,?,?,?,?,?,?,?,0)",
        (site_id, line_number, equipment_type, config_name, json.dumps(layout), created_by, now, now),
    )
    db.commit()
    return cur.lastrowid
