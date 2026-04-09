"""
notifications.py — Módulo de notificaciones a Microsoft Teams.

Funcionalidad:
  - send_teams_notification(): envía Adaptive Card a un webhook de Teams
  - notify_maintenance_comment(): trigger para comentarios de mantenimiento
  - notify_vsm_stopped(): trigger para pasos VSM detenidos >5 min
  - log_notification(): persiste el resultado en la tabla notification_log
  - get_notification_config(): lee configuración desde la BD (site activo)

Si TEAMS_WEBHOOK_URL no está configurado, las notificaciones se loguean
en consola sin lanzar ningún error (graceful degradation).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen, ProxyHandler, build_opener
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

# ── Constantes de severidad ────────────────────────────────────────────────────

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING  = "warning"
SEVERITY_INFO     = "info"

_SEVERITY_COLOR = {
    SEVERITY_CRITICAL: "attention",   # rojo en Adaptive Cards
    SEVERITY_WARNING:  "warning",     # amarillo
    SEVERITY_INFO:     "good",        # verde
}

_SEVERITY_ICON = {
    SEVERITY_CRITICAL: "🔴",
    SEVERITY_WARNING:  "🟡",
    SEVERITY_INFO:     "🟢",
}

# ── Tipos de evento para filtrar notificaciones ────────────────────────────────

EVENT_MAINTENANCE_COMMENT = "maintenance_comment"
EVENT_VSM_STOPPED         = "vsm_stopped"
EVENT_LOW_OEE             = "low_oee"
EVENT_SHIFT_END           = "shift_end"

ALL_EVENTS = [
    EVENT_MAINTENANCE_COMMENT,
    EVENT_VSM_STOPPED,
    EVENT_LOW_OEE,
    EVENT_SHIFT_END,
]


# ── Construcción de Adaptive Card ─────────────────────────────────────────────

def _build_adaptive_card(
    title: str,
    message: str,
    severity: str,
    site: str,
    line: int | str,
    problem_details: str,
    app_url: str = "",
) -> dict[str, Any]:
    """
    Construye el payload JSON para enviar al webhook de Teams como Adaptive Card.
    Compatible con Teams Incoming Webhook (formato messageCard wrapper).
    """
    ts = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    color = _SEVERITY_COLOR.get(severity, "default")
    icon  = _SEVERITY_ICON.get(severity, "⚪")

    card_body: list[dict] = [
        {
            "type": "TextBlock",
            "text": f"{icon} {title}",
            "weight": "Bolder",
            "size": "Large",
            "color": color,
            "wrap": True,
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "Planta",       "value": site},
                {"title": "Línea",        "value": str(line)},
                {"title": "Severidad",    "value": severity.capitalize()},
                {"title": "Timestamp",    "value": ts},
            ],
        },
        {
            "type": "TextBlock",
            "text": message,
            "wrap": True,
            "spacing": "Medium",
        },
    ]

    if problem_details:
        card_body.append({
            "type": "TextBlock",
            "text": f"**Detalles:** {problem_details}",
            "wrap": True,
            "spacing": "Small",
            "isSubtle": True,
        })

    actions: list[dict] = []
    if app_url:
        actions.append({
            "type": "Action.OpenUrl",
            "title": "Ver en OpEx Platform",
            "url": app_url,
        })

    adaptive_card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": card_body,
        "actions": actions,
    }

    # Teams Incoming Webhook espera este wrapper
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": adaptive_card,
            }
        ],
    }


# ── Cliente webhook ────────────────────────────────────────────────────────────

def send_teams_notification(
    webhook_url: str | None,
    title: str,
    message: str,
    severity: str = SEVERITY_WARNING,
    site: str = "",
    line: int | str = "",
    problem_details: str = "",
    app_url: str = "",
) -> dict[str, Any]:
    """
    Envía una notificación formateada como Adaptive Card al webhook de Teams.

    Returns:
        {"status": "sent"}  si OK
        {"status": "skipped", "reason": "..."}  si no hay webhook configurado
        {"status": "failed", "error": "..."}  si hubo error HTTP/red
    """
    if not webhook_url:
        _log_console(title, message, severity, site, line)
        return {"status": "skipped", "reason": "webhook_url no configurada"}

    payload = _build_adaptive_card(
        title, message, severity, site, line, problem_details, app_url
    )
    body = json.dumps(payload).encode("utf-8")

    req = Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    # Soporte de proxy corporativo: leer HTTPS_PROXY / HTTP_PROXY del entorno
    proxy_url = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or ""
    )
    if proxy_url:
        opener = build_opener(ProxyHandler({"https": proxy_url, "http": proxy_url}))
        logger.debug("Usando proxy para Teams webhook: %s", proxy_url)
    else:
        opener = build_opener()

    try:
        with opener.open(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            if resp.status == 200 and resp_body.strip() == "1":
                logger.info("Teams notification sent: %s", title)
                return {"status": "sent"}
            # Teams a veces devuelve 200 con body "1" al aceptar
            logger.info("Teams webhook response %s: %s", resp.status, resp_body[:200])
            return {"status": "sent"}
    except HTTPError as exc:
        err = f"HTTP {exc.code}: {exc.reason}"
        logger.error("Teams notification failed: %s", err)
        return {"status": "failed", "error": err}
    except URLError as exc:
        reason = str(exc.reason)
        if "getaddrinfo failed" in reason or "Name or service not known" in reason:
            err = (
                f"DNS: no se puede resolver el host del webhook ({reason}). "
                "Configura la variable de entorno HTTPS_PROXY con el proxy corporativo "
                "o verifica la conectividad de red."
            )
        else:
            err = reason
        logger.error("Teams notification network error: %s", err)
        return {"status": "failed", "error": err}
    except Exception as exc:
        err = str(exc)
        logger.error("Teams notification unexpected error: %s", err)
        return {"status": "failed", "error": err}


def _log_console(title: str, message: str, severity: str, site: str, line: Any) -> None:
    icon = _SEVERITY_ICON.get(severity, "⚪")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        "[TEAMS-NOTIF] %s %s | Planta: %s | Línea: %s | %s — %s",
        icon, ts, site, line, title, message,
    )


# ── Lectura de configuración ──────────────────────────────────────────────────

_NOTIF_CONFIG_KEY = "global"  # Clave fija: la config del webhook es de plataforma, no por planta


def _get_config_db():
    """
    Devuelve una conexión a la BD donde se guarda la config de notificaciones.
    Siempre usa el DEFAULT_SITE para que la config sea independiente del site
    activo en la sesión del usuario.
    """
    import sqlite3
    from site_aggregator import SITES, DEFAULT_SITE
    db_path = SITES[DEFAULT_SITE]["db_path"]
    db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_notification_config(db=None, site_id: str | None = None) -> dict[str, Any]:
    """
    Lee la configuración de notificaciones.
    Siempre lee de la BD del DEFAULT_SITE con clave 'global', independientemente
    del site activo del usuario, para que la config persista al cambiar de menú.
    Fallback a variable de entorno TEAMS_WEBHOOK_URL.
    """
    env_url = os.environ.get("TEAMS_WEBHOOK_URL", "")

    defaults: dict[str, Any] = {
        "webhook_url": env_url,
        "enabled": bool(env_url),
        "events": {e: True for e in ALL_EVENTS},
    }

    config_db = None
    try:
        config_db = _get_config_db()
        row = config_db.execute(
            "SELECT config_json FROM notification_config WHERE site_id = ? LIMIT 1",
            (_NOTIF_CONFIG_KEY,),
        ).fetchone()
        if row:
            stored = json.loads(row["config_json"])
            if not stored.get("webhook_url"):
                stored["webhook_url"] = env_url
            stored.setdefault("enabled", bool(stored.get("webhook_url")))
            stored.setdefault("events", defaults["events"])
            return stored
    except Exception as exc:
        logger.error("Error leyendo notification_config: %s", exc)
    finally:
        if config_db:
            config_db.close()

    return defaults


def save_notification_config(
    db,  # parámetro mantenido por compatibilidad, no se usa
    webhook_url: str,
    enabled: bool,
    events: dict[str, bool],
    site_id: str = "global",  # ignorado, siempre se usa _NOTIF_CONFIG_KEY
) -> None:
    """
    Guarda la configuración de notificaciones en la BD global.
    Siempre usa la BD del DEFAULT_SITE con clave fija para que persista
    independientemente del site activo en la sesión.
    """
    cfg = json.dumps({
        "webhook_url": webhook_url,
        "enabled": enabled,
        "events": events,
    })
    config_db = None
    try:
        config_db = _get_config_db()
        existing = config_db.execute(
            "SELECT id FROM notification_config WHERE site_id = ?",
            (_NOTIF_CONFIG_KEY,),
        ).fetchone()
        if existing:
            config_db.execute(
                "UPDATE notification_config SET config_json=?, updated_at=datetime('now') WHERE site_id=?",
                (cfg, _NOTIF_CONFIG_KEY),
            )
        else:
            config_db.execute(
                "INSERT INTO notification_config (site_id, config_json) VALUES (?, ?)",
                (_NOTIF_CONFIG_KEY, cfg),
            )
        config_db.commit()
        logger.info("Notification config saved (enabled=%s)", enabled)
    except Exception as exc:
        logger.error("Error guardando notification_config: %s", exc)
        raise
    finally:
        if config_db:
            config_db.close()


# ── Log de notificaciones en BD ───────────────────────────────────────────────

def log_notification(
    db,  # puede ser None; si es None se abre la DB global
    event_type: str,
    title: str,
    recipient: str,
    status: str,
    site_id: str = "",
    line: int | str = "",
    error_detail: str = "",
) -> None:
    """Persiste el resultado de un intento de notificación en notification_log."""
    close_after = False
    if db is None:
        try:
            db = _get_config_db()
            close_after = True
        except Exception as exc:
            logger.error("No se pudo abrir DB para notification_log: %s", exc)
            return
    try:
        db.execute(
            """INSERT INTO notification_log
               (event_type, title, recipient, status, site_id, line_number,
                error_detail, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (event_type, title, recipient, status, site_id, str(line), error_detail),
        )
        db.commit()
    except Exception as exc:
        logger.error("Error guardando notification_log: %s", exc)
    finally:
        if close_after:
            db.close()


# ── Triggers de alto nivel ─────────────────────────────────────────────────────

def notify_maintenance_comment(
    comment_text: str,
    operator_name: str,
    line_number: int | str,
    shift_id: int,
    site_id: str = "",
    base_url: str = "",
    db=None,  # ignorado; mantenido para compatibilidad de llamadas antiguas
) -> None:
    """
    Llamar cuando se registra un comentario con category='maintenance'.
    Envía notificación a Teams si el evento está habilitado.
    """
    cfg = get_notification_config()
    if not cfg.get("enabled") or not cfg["events"].get(EVENT_MAINTENANCE_COMMENT):
        _log_console(
            "Comentario de mantenimiento",
            comment_text,
            SEVERITY_WARNING, site_id, line_number,
        )
        return

    app_url = f"{base_url}/shift/{shift_id}/active" if base_url else ""
    result = send_teams_notification(
        webhook_url=cfg["webhook_url"],
        title="Aviso de Mantenimiento — Comentario Operador",
        message=f"**{operator_name}** ha registrado un comentario de mantenimiento en la Línea {line_number}:\n\n> {comment_text}",
        severity=SEVERITY_WARNING,
        site=site_id,
        line=line_number,
        problem_details="",
        app_url=app_url,
    )
    log_notification(
        db=None,
        event_type=EVENT_MAINTENANCE_COMMENT,
        title="Comentario mantenimiento",
        recipient=cfg["webhook_url"],
        status=result["status"],
        site_id=site_id,
        line=line_number,
        error_detail=result.get("error", ""),
    )


def notify_vsm_stopped(
    step_name: str,
    step_id: int,
    line_number: int | str,
    stopped_minutes: float,
    site_id: str = "",
    base_url: str = "",
    db=None,  # ignorado; mantenido para compatibilidad
) -> None:
    """
    Llamar cuando un paso VSM lleva más de 5 minutos con status='stopped'.
    Envía notificación crítica a Teams.
    """
    cfg = get_notification_config()
    if not cfg.get("enabled") or not cfg["events"].get(EVENT_VSM_STOPPED):
        _log_console(
            f"VSM PARADO: {step_name}",
            f"Línea {line_number} — {stopped_minutes:.1f} min parada",
            SEVERITY_CRITICAL, site_id, line_number,
        )
        return

    app_url = f"{base_url}/vsm?line={line_number}" if base_url else ""
    result = send_teams_notification(
        webhook_url=cfg["webhook_url"],
        title=f"PARADA DE LÍNEA — {step_name}",
        message=f"El paso **{step_name}** en la Línea {line_number} lleva **{stopped_minutes:.1f} minutos** con status PARADO.",
        severity=SEVERITY_CRITICAL,
        site=site_id,
        line=line_number,
        problem_details=f"Paso VSM: {step_name} (ID {step_id}) — Duración parada: {stopped_minutes:.1f} min",
        app_url=app_url,
    )
    log_notification(
        db=None,
        event_type=EVENT_VSM_STOPPED,
        title=f"VSM parado: {step_name}",
        recipient=cfg["webhook_url"],
        status=result["status"],
        site_id=site_id,
        line=line_number,
        error_detail=result.get("error", ""),
    )


def notify_low_oee(
    oee_value: float,
    threshold: float,
    line_number: int | str,
    shift_id: int,
    site_id: str = "",
    base_url: str = "",
    db=None,
) -> None:
    """Notifica cuando el OEE cae por debajo del umbral configurado."""
    cfg = get_notification_config()
    if not cfg.get("enabled") or not cfg["events"].get(EVENT_LOW_OEE):
        return

    app_url = f"{base_url}/shift/{shift_id}/active" if base_url else ""
    result = send_teams_notification(
        webhook_url=cfg["webhook_url"],
        title=f"OEE Bajo Umbral — Línea {line_number}",
        message=f"El OEE de la Línea {line_number} ha bajado al **{oee_value:.1f}%** (umbral: {threshold:.1f}%).",
        severity=SEVERITY_WARNING,
        site=site_id,
        line=line_number,
        problem_details=f"OEE actual: {oee_value:.1f}% — Umbral configurado: {threshold:.1f}%",
        app_url=app_url,
    )
    log_notification(
        db=None,
        event_type=EVENT_LOW_OEE,
        title=f"OEE bajo: {oee_value:.1f}%",
        recipient=cfg["webhook_url"],
        status=result["status"],
        site_id=site_id,
        line=line_number,
        error_detail=result.get("error", ""),
    )


def notify_shift_end(
    operator_name: str,
    line_number: int | str,
    shift_id: int,
    oee_value: float | None,
    site_id: str = "",
    base_url: str = "",
    db=None,
) -> None:
    """Notifica al finalizar un turno con resumen de OEE."""
    cfg = get_notification_config()
    if not cfg.get("enabled") or not cfg["events"].get(EVENT_SHIFT_END):
        return

    oee_txt = f"{oee_value:.1f}%" if oee_value is not None else "N/D"
    app_url = f"{base_url}/shift/{shift_id}/summary" if base_url else ""
    result = send_teams_notification(
        webhook_url=cfg["webhook_url"],
        title=f"Fin de Turno — Línea {line_number}",
        message=f"El operador **{operator_name}** ha cerrado el turno en la Línea {line_number}. OEE del turno: **{oee_txt}**.",
        severity=SEVERITY_INFO,
        site=site_id,
        line=line_number,
        problem_details="",
        app_url=app_url,
    )
    log_notification(
        db=None,
        event_type=EVENT_SHIFT_END,
        title=f"Fin turno L{line_number}",
        recipient=cfg["webhook_url"],
        status=result["status"],
        site_id=site_id,
        line=line_number,
        error_detail=result.get("error", ""),
    )
