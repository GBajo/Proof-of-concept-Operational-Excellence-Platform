"""routes/sqdcp.py — SQDCP Board: Safety · Quality · Delivery · Cost · People"""
from __future__ import annotations

import hashlib
from datetime import datetime, date, timedelta

from flask import Blueprint, g, jsonify, render_template, request

from database import get_db

bp = Blueprint("sqdcp", __name__)

PILLARS = ["S", "Q", "D", "C", "P"]
PILLAR_NAMES = {
    "S": "Safety", "Q": "Quality", "D": "Delivery", "C": "Cost", "P": "People"
}


def _site_lines() -> list[int]:
    from site_aggregator import SITES, DEFAULT_SITE
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    return SITES.get(site_id, SITES[DEFAULT_SITE]).get("lines", list(range(1, 6)))


def _compute_pillars(line: int, date_str: str, period: str = "day") -> dict:
    db = get_db()

    # ── Date range based on period ───────────────────────────────────────────
    selected = date.fromisoformat(date_str)
    if period == "week":
        date_from = (selected - timedelta(days=selected.weekday())).isoformat()
    elif period == "month":
        date_from = selected.replace(day=1).isoformat()
    else:
        date_from = date_str
    date_to = date_str
    days_in_period = max(1, (selected - date.fromisoformat(date_from)).days + 1)

    # ── KPI aggregados del período ───────────────────────────────────────────
    kpi = db.execute("""
        SELECT
            COALESCE(SUM(k.units_produced),   0) AS total_units,
            COALESCE(SUM(k.units_rejected),   0) AS total_rejected,
            COALESCE(SUM(k.downtime_minutes), 0) AS total_downtime,
            COALESCE(MAX(k.target_units),  9600) AS target_per_day
        FROM kpi_readings k
        JOIN shifts s ON k.shift_id = s.id
        WHERE s.line_number = ? AND date(s.start_time) BETWEEN ? AND ?
    """, (line, date_from, date_to)).fetchone()

    # ── Comentarios de seguridad ─────────────────────────────────────────────
    safety_comments = db.execute("""
        SELECT COUNT(*) AS cnt FROM comments c
        JOIN shifts s ON c.shift_id = s.id
        WHERE s.line_number = ? AND date(s.start_time) BETWEEN ? AND ?
          AND c.category = 'safety'
    """, (line, date_from, date_to)).fetchone()

    # ── Operadores activos en el período ─────────────────────────────────────
    people = db.execute("""
        SELECT COUNT(DISTINCT operator_id) AS cnt
        FROM shifts
        WHERE line_number = ? AND date(start_time) BETWEEN ? AND ?
    """, (line, date_from, date_to)).fetchone()

    total_units    = int(kpi["total_units"]   or 0)
    total_rejected = int(kpi["total_rejected"] or 0)
    total_downtime = float(kpi["total_downtime"] or 0)
    target_units   = int(kpi["target_per_day"] or 9600) * days_in_period

    # ── Safety: días sin LTI (simulado determinista por planta+línea+semana) ─
    week_key = f"{getattr(g, 'current_site', 'x')}{line}{date_str[:7]}"
    seed_val = int(hashlib.md5(week_key.encode()).hexdigest()[:4], 16)
    safety_days = 20 + (seed_val % 61)
    safety_target = 90

    # ── Quality: FPY ────────────────────────────────────────────────────────
    fpy = round((1 - total_rejected / total_units) * 100, 1) if total_units > 0 else 0.0
    fpy_target = 99.0

    # ── Delivery: OTD ───────────────────────────────────────────────────────
    otd = round(min(total_units / target_units, 1.0) * 100, 1) if target_units > 0 else 0.0
    otd_target = 100.0

    # ── Cost: downtime vs disponibilidad ────────────────────────────────────
    dt_target   = 30 * days_in_period
    max_minutes = 480 * days_in_period
    cost_pct    = max(0.0, round((1 - total_downtime / max_minutes) * 100, 1))

    # ── People: operadores / objetivo 3 por línea ────────────────────────────
    people_count  = int(people["cnt"] or 0)
    people_target = 3
    people_pct    = round(min(people_count / people_target, 1.0) * 100, 1)

    def _status(val: float, ok_thr: float, warn_thr: float) -> str:
        return "ok" if val >= ok_thr else ("warn" if val >= warn_thr else "bad")

    return {
        "S": {
            "letter": "S", "name": "Safety",
            "value": safety_days, "unit": "días sin LTI",
            "target": safety_target,
            "pct": round(min(safety_days / safety_target * 100, 100), 1),
            "status": _status(safety_days, 30, 15),
            "secondary": f"Avisos seguridad: {safety_comments['cnt']}",
        },
        "Q": {
            "letter": "Q", "name": "Quality",
            "value": fpy, "unit": "% FPY",
            "target": fpy_target,
            "pct": fpy,
            "status": _status(fpy, 98.0, 95.0),
            "secondary": f"Rechazadas: {total_rejected:,} uds",
        },
        "D": {
            "letter": "D", "name": "Delivery",
            "value": otd, "unit": "% OTD",
            "target": otd_target,
            "pct": otd,
            "status": _status(otd, 95.0, 80.0),
            "secondary": f"{total_units:,} / {target_units:,} uds",
        },
        "C": {
            "letter": "C", "name": "Cost",
            "value": int(total_downtime), "unit": "min parada",
            "target": dt_target,
            "pct": cost_pct,
            "status": "ok" if total_downtime <= dt_target else ("warn" if total_downtime <= dt_target * 2 else "bad"),
            "secondary": f"Disponibilidad: {cost_pct}%",
        },
        "P": {
            "letter": "P", "name": "People",
            "value": people_count, "unit": f"/ {people_target} ops.",
            "target": people_target,
            "pct": people_pct,
            "status": _status(people_count, people_target, people_target - 1),
            "secondary": "Presencia turno",
        },
    }


def _get_shifts(line: int, date_str: str) -> list[dict]:
    db = get_db()
    rows = db.execute("""
        SELECT
            s.id, s.shift_type, s.start_time, s.end_time, s.status,
            op.name AS operator_name,
            COALESCE(k.units_produced, 0)   AS units_produced,
            COALESCE(k.units_rejected, 0)   AS units_rejected,
            COALESCE(k.downtime_minutes, 0) AS downtime_minutes,
            COALESCE(k.target_units, 9600)  AS target_units
        FROM shifts s
        JOIN operators op ON s.operator_id = op.id
        LEFT JOIN (
            SELECT shift_id,
                   MAX(timestamp) AS ts,
                   units_produced, units_rejected, downtime_minutes, target_units
            FROM kpi_readings
            GROUP BY shift_id
        ) k ON k.shift_id = s.id
        WHERE s.line_number = ? AND date(s.start_time) = ?
        ORDER BY s.start_time DESC
    """, (line, date_str)).fetchall()
    return [dict(r) for r in rows]


def _get_actions(line: int, date_str: str) -> list[dict]:
    db = get_db()
    rows = db.execute("""
        SELECT id, pillar, title, owner, deadline, status, created_at
        FROM sqdcp_actions
        WHERE line_number = ? AND action_date = ?
        ORDER BY pillar, created_at
    """, (line, date_str)).fetchall()
    return [dict(r) for r in rows]


# ── Page ─────────────────────────────────────────────────────────────────────

@bp.get("/sqdcp")
def sqdcp_page():
    lines    = _site_lines()
    line     = int(request.args.get("line", lines[0] if lines else 1))
    date_str = request.args.get("date", date.today().isoformat())
    period   = request.args.get("period", "day")
    if period not in ("day", "week", "month"):
        period = "day"

    pillars = _compute_pillars(line, date_str, period)
    shifts  = _get_shifts(line, date_str)
    actions = _get_actions(line, date_str)

    return render_template(
        "sqdcp/index.html",
        pillars=pillars,
        pillar_keys=PILLARS,
        shifts=shifts,
        actions=actions,
        site_lines=lines,
        selected_line=line,
        selected_date=date_str,
        selected_period=period,
        today=date.today().isoformat(),
    )


# ── API: acciones CRUD ────────────────────────────────────────────────────────

@bp.post("/api/sqdcp/actions")
def add_action():
    data = request.get_json(force=True) or {}
    line     = int(data.get("line", 1))
    date_str = data.get("date", date.today().isoformat())
    pillar   = data.get("pillar", "S")
    title    = (data.get("title") or "").strip()
    owner    = (data.get("owner") or "").strip()
    deadline = (data.get("deadline") or "").strip()

    if not title or pillar not in PILLARS:
        return jsonify({"error": "Datos inválidos"}), 400

    db = get_db()
    cur = db.execute("""
        INSERT INTO sqdcp_actions (line_number, action_date, pillar, title, owner, deadline)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (line, date_str, pillar, title, owner, deadline))
    db.commit()
    return jsonify({"id": cur.lastrowid, "ok": True}), 201


@bp.patch("/api/sqdcp/actions/<int:action_id>")
def update_action(action_id: int):
    data   = request.get_json(force=True) or {}
    status = data.get("status")
    if status not in ("open", "in_progress", "done", "blocked"):
        return jsonify({"error": "Estado inválido"}), 400
    db = get_db()
    db.execute("UPDATE sqdcp_actions SET status = ? WHERE id = ?", (status, action_id))
    db.commit()
    return jsonify({"ok": True})


@bp.delete("/api/sqdcp/actions/<int:action_id>")
def delete_action(action_id: int):
    db = get_db()
    db.execute("DELETE FROM sqdcp_actions WHERE id = ?", (action_id,))
    db.commit()
    return jsonify({"ok": True})
