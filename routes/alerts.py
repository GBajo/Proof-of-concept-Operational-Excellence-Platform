"""
routes/alerts.py — Blueprint para el sistema de alertas.

Endpoints:
  GET  /api/alerts/active                  → alertas activas del site (JSON)
  POST /api/alerts/<id>/acknowledge        → marcar como aceptada
  POST /api/alerts/<id>/resolve            → marcar como resuelta
  GET  /alerts/history                     → pantalla historial
  GET  /admin/alert-rules                  → gestión de reglas
  POST /admin/alert-rules                  → crear regla
  PUT  /admin/alert-rules/<id>             → editar regla
  DELETE /admin/alert-rules/<id>           → eliminar regla
  POST /admin/alert-rules/<id>/toggle      → activar/desactivar regla
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, render_template, request

bp = Blueprint("alerts", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_db():
    from database import get_db
    return get_db()


def _get_rules_db():
    """Conexión a la BD donde se guardan las reglas (DEFAULT_SITE)."""
    import sqlite3
    from site_aggregator import SITES, DEFAULT_SITE
    db_path = SITES[DEFAULT_SITE]["db_path"]
    key = "_alerts_rules_db"
    db = getattr(g, key, None)
    if db is None:
        db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        setattr(g, key, db)
    return db


# ── API: alertas activas ───────────────────────────────────────────────────────

@bp.get("/api/alerts/active")
def active_alerts():
    """Alertas activas del site actual + conteo total."""
    db = _get_db()
    site_id = getattr(g, "current_site", "alcobendas")
    rows = db.execute(
        """SELECT id, site_id, line_number, timestamp, source, rule_id,
                  severity, title, description, metric_name, metric_value,
                  threshold_value, status
           FROM alerts
           WHERE site_id=? AND status='active'
           ORDER BY
             CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
             timestamp DESC
           LIMIT 50""",
        (site_id,),
    ).fetchall()
    alerts = [dict(r) for r in rows]

    # Conteo global (todas las plantas) para el badge de la campana
    all_sites_count = 0
    from site_aggregator import SITES
    import sqlite3
    for sid, info in SITES.items():
        try:
            c = sqlite3.connect(info["db_path"])
            cnt = c.execute(
                "SELECT COUNT(*) FROM alerts WHERE status='active'"
            ).fetchone()[0]
            all_sites_count += cnt
            c.close()
        except Exception:
            pass

    return jsonify({"alerts": alerts, "total_active": all_sites_count})


# ── API: acknowledge / resolve ─────────────────────────────────────────────────

@bp.post("/api/alerts/<int:alert_id>/acknowledge")
def acknowledge_alert(alert_id: int):
    db = _get_db()
    body = request.get_json(silent=True) or {}
    by   = body.get("acknowledged_by", "operador")
    now  = datetime.now(timezone.utc).isoformat()
    db.execute(
        """UPDATE alerts
           SET status='acknowledged', acknowledged_by=?, acknowledged_at=?
           WHERE id=? AND status='active'""",
        (by, now, alert_id),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.post("/api/alerts/<int:alert_id>/resolve")
def resolve_alert(alert_id: int):
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """UPDATE alerts
           SET status='resolved', resolved_at=?
           WHERE id=? AND status IN ('active','acknowledged')""",
        (now, alert_id),
    )
    db.commit()
    return jsonify({"ok": True})


# ── Historial de alertas ───────────────────────────────────────────────────────

@bp.get("/alerts/history")
def alerts_history():
    db      = _get_db()
    site_id = getattr(g, "current_site", "alcobendas")

    # Filtros
    filt_severity = request.args.get("severity", "")
    filt_source   = request.args.get("source", "")
    filt_status   = request.args.get("status", "")
    filt_line     = request.args.get("line", "")
    filt_from     = request.args.get("date_from", "")
    filt_to       = request.args.get("date_to", "")

    query  = "SELECT * FROM alerts WHERE site_id=?"
    params: list = [site_id]

    if filt_severity:
        query += " AND severity=?"
        params.append(filt_severity)
    if filt_source:
        query += " AND source=?"
        params.append(filt_source)
    if filt_status:
        query += " AND status=?"
        params.append(filt_status)
    if filt_line:
        query += " AND line_number=?"
        params.append(int(filt_line))
    if filt_from:
        query += " AND date(timestamp) >= ?"
        params.append(filt_from)
    if filt_to:
        query += " AND date(timestamp) <= ?"
        params.append(filt_to)

    query += " ORDER BY timestamp DESC LIMIT 500"
    rows   = db.execute(query, params).fetchall()
    alerts = [dict(r) for r in rows]

    # ── Datos para gráficos ECharts ──────────────────────────────────────────
    # 1) Alertas por día (últimos 14 días) por severidad
    chart_days = db.execute(
        """SELECT date(timestamp) AS day,
                  SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) AS critical,
                  SUM(CASE WHEN severity='warning'  THEN 1 ELSE 0 END) AS warning,
                  SUM(CASE WHEN severity='info'     THEN 1 ELSE 0 END) AS info
           FROM alerts
           WHERE site_id=? AND timestamp >= datetime('now', '-14 days')
           GROUP BY day ORDER BY day ASC""",
        (site_id,),
    ).fetchall()
    chart_days_data = [dict(r) for r in chart_days]

    # 2) Top 5 reglas que más se disparan
    # alert_rules solo existe en la BD de alcobendas (DEFAULT_SITE);
    # hacemos el conteo en la BD del site y luego enriquecemos con los
    # nombres desde rules_db para evitar el crash en otros sites.
    rule_counts = db.execute(
        """SELECT rule_id, COUNT(*) AS cnt
           FROM alerts
           WHERE site_id=? AND source='rule' AND rule_id IS NOT NULL
           GROUP BY rule_id
           ORDER BY cnt DESC LIMIT 5""",
        (site_id,),
    ).fetchall()
    if not rule_counts:
        top_rules_data = []
    else:
        rules_db = _get_rules_db()
        top_rules_data = []
        for row in rule_counts:
            rule_row = rules_db.execute(
                "SELECT name FROM alert_rules WHERE id=?", (row["rule_id"],)
            ).fetchone()
            top_rules_data.append({
                "name": rule_row["name"] if rule_row else f"Regla #{row['rule_id']}",
                "cnt":  row["cnt"],
            })

    # 3) Tiempo medio de resolución (minutos)
    avg_res = db.execute(
        """SELECT severity,
                  AVG(
                      (julianday(resolved_at) - julianday(timestamp)) * 1440
                  ) AS avg_minutes
           FROM alerts
           WHERE site_id=? AND status='resolved' AND resolved_at IS NOT NULL
           GROUP BY severity""",
        (site_id,),
    ).fetchall()
    avg_res_data = [dict(r) for r in avg_res]

    return render_template(
        "alerts/history.html",
        alerts=alerts,
        chart_days=json.dumps(chart_days_data),
        top_rules=json.dumps(top_rules_data),
        avg_res=json.dumps(avg_res_data),
        filt_severity=filt_severity,
        filt_source=filt_source,
        filt_status=filt_status,
        filt_line=filt_line,
        filt_from=filt_from,
        filt_to=filt_to,
    )


# ── Gestión de reglas ──────────────────────────────────────────────────────────

@bp.get("/admin/alert-rules")
def alert_rules_page():
    rules_db = _get_rules_db()
    rules    = [dict(r) for r in rules_db.execute(
        "SELECT * FROM alert_rules ORDER BY severity DESC, name ASC"
    ).fetchall()]

    # Conteo de disparos por regla (en el site activo)
    site_id  = getattr(g, "current_site", "alcobendas")
    db       = _get_db()
    fire_counts = {}
    for rule in rules:
        cnt = db.execute(
            "SELECT COUNT(*) FROM alerts WHERE rule_id=? AND site_id=?",
            (rule["id"], site_id),
        ).fetchone()[0]
        fire_counts[rule["id"]] = cnt

    return render_template(
        "admin/alert_rules.html",
        rules=rules,
        fire_counts=fire_counts,
    )


@bp.post("/admin/alert-rules")
def create_rule():
    data = request.get_json(silent=True) or request.form
    rules_db  = _get_rules_db()
    channels  = data.get("notification_channels", '["app"]')
    if isinstance(channels, list):
        channels = json.dumps(channels)
    rules_db.execute(
        """INSERT INTO alert_rules
           (name, metric, operator, threshold_value, severity,
            active, notification_channels, cooldown_minutes)
           VALUES (?,?,?,?,?,1,?,?)""",
        (
            data.get("name", "Nueva regla"),
            data.get("metric", "oee"),
            data.get("operator", "less_than"),
            float(data.get("threshold_value", 0)),
            data.get("severity", "warning"),
            channels,
            int(data.get("cooldown_minutes", 30)),
        ),
    )
    rules_db.commit()
    return jsonify({"ok": True})


@bp.put("/admin/alert-rules/<int:rule_id>")
def update_rule(rule_id: int):
    data      = request.get_json(silent=True) or {}
    rules_db  = _get_rules_db()
    channels  = data.get("notification_channels", '["app"]')
    if isinstance(channels, list):
        channels = json.dumps(channels)
    rules_db.execute(
        """UPDATE alert_rules
           SET name=?, metric=?, operator=?, threshold_value=?, severity=?,
               notification_channels=?, cooldown_minutes=?
           WHERE id=?""",
        (
            data.get("name"),
            data.get("metric"),
            data.get("operator"),
            float(data.get("threshold_value", 0)),
            data.get("severity"),
            channels,
            int(data.get("cooldown_minutes", 30)),
            rule_id,
        ),
    )
    rules_db.commit()
    return jsonify({"ok": True})


@bp.delete("/admin/alert-rules/<int:rule_id>")
def delete_rule(rule_id: int):
    rules_db = _get_rules_db()
    rules_db.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
    rules_db.commit()
    return jsonify({"ok": True})


@bp.post("/admin/alert-rules/<int:rule_id>/toggle")
def toggle_rule(rule_id: int):
    rules_db = _get_rules_db()
    rules_db.execute(
        "UPDATE alert_rules SET active = 1 - active WHERE id=?", (rule_id,)
    )
    rules_db.commit()
    return jsonify({"ok": True})
