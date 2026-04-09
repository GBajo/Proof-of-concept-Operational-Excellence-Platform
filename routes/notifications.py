"""
routes/notifications.py — Configuración y log de notificaciones a Teams.

Rutas:
    GET  /admin/notifications          → Formulario de configuración
    POST /admin/notifications          → Guardar configuración
    GET  /admin/notifications/log      → Log de notificaciones (JSON)
    POST /admin/notifications/test     → Enviar notificación de prueba
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, flash, redirect, url_for, g

from database import get_db
from notifications import (
    ALL_EVENTS, EVENT_MAINTENANCE_COMMENT, EVENT_VSM_STOPPED,
    EVENT_LOW_OEE, EVENT_SHIFT_END,
    get_notification_config, save_notification_config, send_teams_notification,
    log_notification, SEVERITY_INFO,
)

bp = Blueprint("notifications_admin", __name__)

EVENT_LABELS = {
    EVENT_MAINTENANCE_COMMENT: "Comentario de mantenimiento",
    EVENT_VSM_STOPPED:         "Parada de línea (VSM >5 min)",
    EVENT_LOW_OEE:             "OEE bajo umbral",
    EVENT_SHIFT_END:           "Fin de turno",
}


@bp.get("/admin/notifications")
def notifications_config():
    db = get_db()
    from site_aggregator import DEFAULT_SITE
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    cfg = get_notification_config(db, site_id)

    # Log reciente (últimas 50 entradas)
    try:
        rows = db.execute(
            """SELECT id, sent_at, event_type, title, status, site_id,
                      line_number, error_detail
               FROM notification_log
               ORDER BY sent_at DESC
               LIMIT 50"""
        ).fetchall()
        log_entries = [dict(r) for r in rows]
    except Exception:
        log_entries = []

    return render_template(
        "admin/notifications.html",
        cfg=cfg,
        event_labels=EVENT_LABELS,
        log_entries=log_entries,
        site_id=site_id,
    )


@bp.post("/admin/notifications")
def save_notifications_config():
    db = get_db()
    from site_aggregator import DEFAULT_SITE
    site_id = getattr(g, "current_site", DEFAULT_SITE)

    webhook_url = (request.form.get("webhook_url") or "").strip()
    enabled = request.form.get("enabled") == "on"

    events: dict[str, bool] = {}
    for event_key in ALL_EVENTS:
        events[event_key] = request.form.get(f"event_{event_key}") == "on"

    save_notification_config(db, webhook_url, enabled, events, site_id)
    flash("Configuración de notificaciones guardada correctamente.", "success")
    return redirect(url_for("notifications_admin.notifications_config"))


@bp.post("/admin/notifications/test")
def test_notification():
    db = get_db()
    from site_aggregator import DEFAULT_SITE
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    cfg = get_notification_config(db, site_id)

    base_url = request.host_url.rstrip("/")
    result = send_teams_notification(
        webhook_url=cfg.get("webhook_url"),
        title="Prueba de Notificación — OpEx Platform",
        message="Esta es una notificación de prueba para verificar la integración con Microsoft Teams.",
        severity=SEVERITY_INFO,
        site=site_id,
        line="—",
        problem_details="",
        app_url=f"{base_url}/admin/notifications",
    )
    log_notification(
        db,
        event_type="test",
        title="Prueba manual",
        recipient=cfg.get("webhook_url", ""),
        status=result["status"],
        site_id=site_id,
        line="—",
        error_detail=result.get("error", ""),
    )
    return jsonify(result)


@bp.get("/admin/notifications/log")
def notifications_log():
    db = get_db()
    limit = request.args.get("limit", 100, type=int)
    event_type = request.args.get("event_type")

    query = "SELECT * FROM notification_log"
    params: list = []
    if event_type:
        query += " WHERE event_type = ?"
        params.append(event_type)
    query += " ORDER BY sent_at DESC LIMIT ?"
    params.append(limit)

    try:
        rows = db.execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
