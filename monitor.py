"""
monitor.py — Motor de monitorización en segundo plano con alertas inteligentes.

Arranca un hilo daemon al iniciar la app Flask y evalúa:
  • Cada 30 s : reglas fijas (KPIs de turnos activos + pasos VSM)
  • Cada 5 min: análisis por IA (LLM Gateway) de tendencias y anomalías

Las alertas se guardan en la tabla `alerts` de cada planta y se envían
via Teams / email según el canal configurado en la regla.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Intervalos ────────────────────────────────────────────────────────────────
RULE_INTERVAL_S  = 30    # evaluación de reglas fijas
AI_INTERVAL_S    = 300   # análisis IA (5 minutos)

# ── Singleton del monitor ──────────────────────────────────────────────────────
_monitor_thread: threading.Thread | None = None
_stop_event = threading.Event()


# ── Conexión directa a BD (fuera de contexto Flask) ──────────────────────────

def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    # No activamos PRAGMA foreign_keys aquí: el monitor solo necesita leer
    # y escribir alertas; FK enforcement causaría fallos en DBs con datos
    # históricos que tienen violaciones de integridad referencial.
    conn.execute("PRAGMA journal_mode=WAL")  # concurrencia segura con Flask
    return conn


def _get_all_dbs() -> dict[str, str]:
    """Devuelve {site_id: db_path} de todas las plantas."""
    from site_aggregator import SITES
    return {sid: info["db_path"] for sid, info in SITES.items()}


def _get_rules_db_path() -> str:
    from site_aggregator import SITES, DEFAULT_SITE
    return SITES[DEFAULT_SITE]["db_path"]


# ── Lectura de reglas activas ─────────────────────────────────────────────────

def _load_rules() -> list[dict]:
    db_path = _get_rules_db_path()
    conn = None
    try:
        conn = _get_conn(db_path)
        rows = conn.execute(
            "SELECT * FROM alert_rules WHERE active = 1"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("[MONITOR] Error cargando reglas: %s", exc)
        return []
    finally:
        if conn:
            conn.close()


# ── Cooldown ──────────────────────────────────────────────────────────────────

def _is_in_cooldown(rules_conn: sqlite3.Connection, rule_id: int,
                    site_id: str, line_number: int, cooldown_minutes: int) -> bool:
    row = rules_conn.execute(
        """SELECT last_triggered FROM alert_rule_cooldowns
           WHERE rule_id=? AND site_id=? AND line_number=?""",
        (rule_id, site_id, line_number),
    ).fetchone()
    if not row:
        return False
    last = datetime.fromisoformat(row["last_triggered"]).replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 60
    return elapsed < cooldown_minutes


def _update_cooldown(rules_conn: sqlite3.Connection, rule_id: int,
                     site_id: str, line_number: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    # UPSERT: SQLite ≥3.24 soporta ON CONFLICT DO UPDATE; usar INSERT OR REPLACE
    # que actualiza si la clave UNIQUE ya existe.
    rules_conn.execute(
        """INSERT OR REPLACE INTO alert_rule_cooldowns
           (rule_id, site_id, line_number, last_triggered)
           VALUES (?,?,?,?)""",
        (rule_id, site_id, line_number, now),
    )
    rules_conn.commit()


# ── Persistencia de alertas ───────────────────────────────────────────────────

def _save_alert(site_conn: sqlite3.Connection, site_id: str, line_number: int,
                source: str, rule_id: int | None, severity: str,
                title: str, description: str, metric_name: str,
                metric_value: float | None, threshold_value: float | None,
                channels: list[str]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = site_conn.execute(
        """INSERT INTO alerts
           (site_id, line_number, timestamp, source, rule_id, severity,
            title, description, metric_name, metric_value, threshold_value,
            status, notification_sent_app, notification_sent_teams, notification_sent_email)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
        (
            site_id, line_number, now, source, rule_id, severity,
            title, description, metric_name,
            metric_value, threshold_value,
            1 if "app" in channels else 0,
            0,  # teams — se actualiza tras envío real
            0,  # email — ídem
        ),
    )
    site_conn.commit()
    return cur.lastrowid


# ── Envío de notificaciones por canal ─────────────────────────────────────────

def _dispatch_channels(site_conn: sqlite3.Connection, alert_id: int,
                       site_id: str, line_number: int, severity: str,
                       title: str, description: str, channels: list[str]) -> None:
    from notifications import (
        get_notification_config, send_teams_notification,
        log_notification, SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO,
    )
    cfg = get_notification_config()

    teams_sent = 0
    email_sent = 0

    if "teams" in channels and cfg.get("enabled") and cfg.get("webhook_url"):
        sev_map = {
            "critical": SEVERITY_CRITICAL,
            "warning":  SEVERITY_WARNING,
            "info":     SEVERITY_INFO,
        }
        result = send_teams_notification(
            webhook_url=cfg["webhook_url"],
            title=title,
            message=description,
            severity=sev_map.get(severity, SEVERITY_WARNING),
            site=site_id,
            line=line_number,
            problem_details="",
        )
        teams_sent = 1 if result.get("status") == "sent" else 0
        log_notification(
            db=None,
            event_type="monitor_alert",
            title=title,
            recipient=cfg["webhook_url"],
            status=result["status"],
            site_id=site_id,
            line=line_number,
            error_detail=result.get("error", ""),
        )

    if "email" in channels:
        # Marcamos como enviado aunque el email no esté implementado en demo
        logger.info(
            "[MONITOR] [EMAIL] %s | %s | Línea %s | %s",
            severity.upper(), site_id, line_number, title,
        )
        email_sent = 1

    if teams_sent or email_sent:
        site_conn.execute(
            """UPDATE alerts SET notification_sent_teams=?, notification_sent_email=?
               WHERE id=?""",
            (teams_sent, email_sent, alert_id),
        )
        site_conn.commit()


# ── Evaluación de reglas fijas ────────────────────────────────────────────────

def _evaluate_rules_for_site(site_id: str, db_path: str,
                              rules: list[dict], rules_conn: sqlite3.Connection) -> None:
    try:
        conn = _get_conn(db_path)
    except Exception as exc:
        logger.error("[MONITOR] No se pudo abrir BD %s: %s", db_path, exc)
        return

    try:
        # Turnos activos en esta planta
        active_shifts = conn.execute(
            """SELECT s.id AS shift_id, s.line_number,
                      s.start_time, o.name AS operator_name
               FROM shifts s
               JOIN operators o ON o.id = s.operator_id
               WHERE s.status = 'active'"""
        ).fetchall()

        for shift in active_shifts:
            shift_id    = shift["shift_id"]
            line_number = shift["line_number"]

            # KPIs del turno actual
            kpi = conn.execute(
                """SELECT
                       SUM(units_produced)   AS total_produced,
                       SUM(units_rejected)   AS total_rejected,
                       SUM(downtime_minutes) AS total_downtime,
                       AVG(CASE WHEN line_speed > 0 THEN line_speed END) AS avg_speed,
                       MAX(planned_time_min) AS planned_time,
                       MAX(nominal_speed)    AS nominal_speed
                   FROM kpi_readings
                   WHERE shift_id=?""",
                (shift_id,),
            ).fetchone()

            if kpi is None or kpi["total_produced"] is None:
                continue

            total_produced = float(kpi["total_produced"] or 0)
            total_rejected = float(kpi["total_rejected"] or 0)
            total_downtime = float(kpi["total_downtime"] or 0)
            avg_speed      = float(kpi["avg_speed"] or 0)
            planned_time   = float(kpi["planned_time"] or 480)
            nominal_speed  = float(kpi["nominal_speed"] or 0)

            # Calcular métricas
            operating_time = max(planned_time - total_downtime, 0)
            availability   = operating_time / planned_time if planned_time > 0 else 0
            ideal_units    = nominal_speed * (operating_time / 60) if nominal_speed > 0 else 0
            performance    = min(total_produced / ideal_units, 1.0) if ideal_units > 0 else 0
            good_units     = max(total_produced - total_rejected, 0)
            quality        = good_units / total_produced if total_produced > 0 else 0
            oee            = availability * performance * quality * 100
            reject_rate    = (total_rejected / total_produced * 100) if total_produced > 0 else 0
            speed_pct      = (avg_speed / nominal_speed * 100) if nominal_speed > 0 else 0

            metric_values = {
                "oee":         oee,
                "reject_rate": reject_rate,
                "downtime":    total_downtime,
                "line_speed":  speed_pct,
            }

            for rule in rules:
                metric = rule["metric"]
                if metric == "cycle_time":
                    continue  # se evalúa en sección VSM abajo
                if metric not in metric_values:
                    continue

                value     = metric_values[metric]
                threshold = rule["threshold_value"]
                op        = rule["operator"]
                triggered = (
                    (op == "less_than"    and value < threshold) or
                    (op == "greater_than" and value > threshold) or
                    (op == "equals"       and abs(value - threshold) < 0.01)
                )

                if not triggered:
                    continue

                rule_id  = rule["id"]
                cooldown = rule["cooldown_minutes"]
                if _is_in_cooldown(rules_conn, rule_id, site_id, line_number, cooldown):
                    logger.debug(
                        "[MONITOR] Cooldown activo — regla %d | %s L%d",
                        rule_id, site_id, line_number,
                    )
                    continue

                channels = json.loads(rule.get("notification_channels") or '["app"]')
                severity = rule["severity"]
                metric_labels = {
                    "oee":         "OEE",
                    "reject_rate": "Tasa de rechazo",
                    "downtime":    "Tiempo de parada",
                    "line_speed":  "Velocidad de línea",
                }
                metric_units = {
                    "oee":         "%",
                    "reject_rate": "%",
                    "downtime":    " min",
                    "line_speed":  "% nominal",
                }
                mlabel = metric_labels.get(metric, metric)
                munit  = metric_units.get(metric, "")
                title  = f"{rule['name']} — Línea {line_number}"
                desc   = (
                    f"{mlabel} actual: {value:.1f}{munit} "
                    f"(umbral: {op.replace('_', ' ')} {threshold:.1f}{munit}) "
                    f"en planta {site_id}, línea {line_number}."
                )

                alert_id = _save_alert(
                    conn, site_id, line_number, "rule", rule_id,
                    severity, title, desc, metric, value, threshold, channels,
                )
                _update_cooldown(rules_conn, rule_id, site_id, line_number)
                _dispatch_channels(conn, alert_id, site_id, line_number,
                                   severity, title, desc, channels)

                logger.info(
                    "[MONITOR] ALERTA [%s] %s | %s L%d | %s=%.1f (umbral %.1f)",
                    severity.upper(), rule["name"], site_id, line_number,
                    metric, value, threshold,
                )

        # ── Evaluación VSM (cycle_time) ──────────────────────────────────────
        vsm_rules = [r for r in rules if r["metric"] == "cycle_time"]
        if vsm_rules:
            steps = conn.execute(
                """SELECT ps.id, ps.line_number, ps.step_name,
                          ps.nominal_cycle_time_seconds,
                          sld.actual_cycle_time
                   FROM process_steps ps
                   JOIN step_live_data sld ON sld.step_id = ps.id
                   WHERE sld.id = (
                       SELECT id FROM step_live_data
                       WHERE step_id = ps.id
                       ORDER BY timestamp DESC LIMIT 1
                   )"""
            ).fetchall()

            for step in steps:
                nom_ct  = float(step["nominal_cycle_time_seconds"] or 0)
                act_ct  = float(step["actual_cycle_time"] or 0)
                if nom_ct <= 0:
                    continue
                ct_pct  = act_ct / nom_ct * 100
                line_number = step["line_number"]

                for rule in vsm_rules:
                    threshold = rule["threshold_value"]
                    op        = rule["operator"]
                    triggered = (
                        (op == "less_than"    and ct_pct < threshold) or
                        (op == "greater_than" and ct_pct > threshold) or
                        (op == "equals"       and abs(ct_pct - threshold) < 0.01)
                    )
                    if not triggered:
                        continue
                    rule_id  = rule["id"]
                    cooldown = rule["cooldown_minutes"]
                    if _is_in_cooldown(rules_conn, rule_id, site_id, line_number, cooldown):
                        continue

                    channels = json.loads(rule.get("notification_channels") or '["app"]')
                    severity = rule["severity"]
                    title    = (f"Ciclo VSM elevado — {step['step_name']} "
                                f"Línea {line_number}")
                    desc     = (
                        f"Tiempo de ciclo en «{step['step_name']}»: "
                        f"{act_ct:.1f}s ({ct_pct:.0f}% del nominal {nom_ct:.1f}s). "
                        f"Planta {site_id}, línea {line_number}."
                    )
                    alert_id = _save_alert(
                        conn, site_id, line_number, "rule", rule_id,
                        severity, title, desc, "cycle_time", ct_pct, threshold, channels,
                    )
                    _update_cooldown(rules_conn, rule_id, site_id, line_number)
                    _dispatch_channels(conn, alert_id, site_id, line_number,
                                       severity, title, desc, channels)
                    logger.info(
                        "[MONITOR] ALERTA VSM [%s] %s | L%d | cycle=%.0f%%",
                        severity.upper(), site_id, line_number, ct_pct,
                    )

    except Exception as exc:
        logger.exception("[MONITOR] Error evaluando reglas para %s: %s", site_id, exc)
    finally:
        conn.close()


# ── Análisis por IA ────────────────────────────────────────────────────────────

def _build_ai_prompt(site_id: str, line_number: int, kpi_rows: list[dict]) -> str:
    lines = [
        f"Planta: {site_id} — Línea {line_number}",
        f"Últimas {len(kpi_rows)} lecturas de KPI (30 minutos):",
    ]
    for row in kpi_rows:
        lines.append(
            f"  {row.get('timestamp','')} | "
            f"Producidas: {row.get('units_produced',0)} | "
            f"Rechazadas: {row.get('units_rejected',0)} | "
            f"Parada: {row.get('downtime_minutes',0):.1f} min | "
            f"Velocidad: {row.get('line_speed',0):.0f} u/h"
        )

    lines += [
        "",
        "Analiza estos datos de producción de los últimos 30 minutos. Busca:",
        "- Tendencias de degradación gradual (métricas que empeoran progresivamente)",
        "- Patrones anómalos (comportamiento fuera de lo habitual)",
        "- Correlaciones preocupantes (ej: aumento de rechazos + descenso de velocidad)",
        "- Riesgo de parada inminente basado en los patrones",
        "",
        "Responde SOLO con un JSON con las anomalías detectadas (array 'anomalies'), "
        "cada una con: severity (info/warning/critical), description (in the same language as this prompt), "
        "affected_metric, confidence (0-1), recommendation.",
        "Si no detectas anomalías, responde: {\"anomalies\": []}",
    ]
    return "\n".join(lines)


def _run_ai_analysis_for_site(site_id: str, db_path: str) -> None:
    try:
        conn = _get_conn(db_path)

        # Obtener turnos activos
        active_shifts = conn.execute(
            "SELECT id AS shift_id, line_number FROM shifts WHERE status='active'"
        ).fetchall()

        for shift in active_shifts:
            shift_id    = shift["shift_id"]
            line_number = shift["line_number"]

            # Lecturas de los últimos 30 min
            kpi_rows = conn.execute(
                """SELECT timestamp, units_produced, units_rejected,
                          downtime_minutes, line_speed
                   FROM kpi_readings
                   WHERE shift_id=?
                     AND timestamp >= datetime('now', '-30 minutes')
                   ORDER BY timestamp ASC""",
                (shift_id,),
            ).fetchall()
            kpi_list = [dict(r) for r in kpi_rows]

            if len(kpi_list) < 2:
                continue

            prompt = _build_ai_prompt(site_id, line_number, kpi_list)

            try:
                from llm_client import _get_api_key, _call_gateway
                api_key = _get_api_key()
                if not api_key:
                    continue

                system_prompt = (
                    "Eres un sistema experto en monitorización de líneas de empaquetado "
                    "farmacéutico. Detecta anomalías y riesgos en los datos de producción. "
                    "Responde SIEMPRE con JSON válido únicamente."
                )
                result = _call_gateway(prompt, api_key, system=system_prompt)
                raw_text = result.get("text", "").strip()

                # Extraer JSON de la respuesta
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()

                data = json.loads(raw_text)
                anomalies = data.get("anomalies", [])

            except (ImportError, json.JSONDecodeError, Exception) as exc:
                logger.debug("[MONITOR][AI] Fallback para %s L%d: %s",
                             site_id, line_number, exc)
                continue

            for anomaly in anomalies:
                sev     = anomaly.get("severity", "warning")
                if sev not in ("info", "warning", "critical"):
                    sev = "warning"
                desc    = anomaly.get("description", "Anomalía detectada por IA")
                metric  = anomaly.get("affected_metric", "")
                conf    = float(anomaly.get("confidence", 0))
                rec     = anomaly.get("recommendation", "")

                if conf < 0.5:
                    continue  # descartar detecciones poco confiadas

                title   = f"[IA] Anomalía detectada — Línea {line_number}"
                full_desc = f"{desc}"
                if rec:
                    full_desc += f" Recomendación: {rec}"

                channels = ["app"]
                if sev in ("warning", "critical"):
                    channels.append("teams")
                if sev == "critical":
                    channels.append("email")

                alert_id = _save_alert(
                    conn, site_id, line_number, "ai", None,
                    sev, title, full_desc, metric, None, None, channels,
                )
                _dispatch_channels(conn, alert_id, site_id, line_number,
                                   sev, title, full_desc, channels)
                logger.info(
                    "[MONITOR][AI] %s | %s L%d | %s (conf=%.2f)",
                    sev.upper(), site_id, line_number, desc[:80], conf,
                )

        conn.close()
    except Exception as exc:
        logger.exception("[MONITOR][AI] Error análisis IA para %s: %s", site_id, exc)


# ── Bucle principal del monitor ───────────────────────────────────────────────

def _monitor_loop() -> None:
    logger.info("[MONITOR] Hilo de monitorización iniciado.")
    rules_db_path = _get_rules_db_path()
    last_ai_run   = 0.0

    while not _stop_event.is_set():
        tick_start = time.monotonic()

        try:
            rules = _load_rules()
            all_dbs = _get_all_dbs()

            rules_conn = _get_conn(rules_db_path)
            try:
                for site_id, db_path in all_dbs.items():
                    logger.debug("[MONITOR] Evaluando reglas para %s …", site_id)
                    _evaluate_rules_for_site(site_id, db_path, rules, rules_conn)
            finally:
                rules_conn.close()

            # Análisis IA cada 5 min
            now = time.monotonic()
            if now - last_ai_run >= AI_INTERVAL_S:
                last_ai_run = now
                for site_id, db_path in all_dbs.items():
                    logger.debug("[MONITOR][AI] Análisis IA para %s …", site_id)
                    _run_ai_analysis_for_site(site_id, db_path)

        except Exception as exc:
            logger.exception("[MONITOR] Error inesperado en bucle: %s", exc)

        elapsed = time.monotonic() - tick_start
        sleep_s = max(0, RULE_INTERVAL_S - elapsed)
        logger.debug("[MONITOR] Ciclo completado en %.1fs; próximo en %.0fs.",
                     elapsed, sleep_s)
        _stop_event.wait(sleep_s)

    logger.info("[MONITOR] Hilo de monitorización detenido.")


# ── API pública ───────────────────────────────────────────────────────────────

def start_monitor() -> None:
    """Arranca el hilo daemon de monitorización. Seguro si se llama varias veces."""
    global _monitor_thread
    if _monitor_thread is not None and _monitor_thread.is_alive():
        logger.debug("[MONITOR] Ya está en ejecución, ignorando start.")
        return
    _stop_event.clear()
    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        name="opex-monitor",
        daemon=True,
    )
    _monitor_thread.start()
    logger.info("[MONITOR] Hilo iniciado (id=%d).", _monitor_thread.ident)


def stop_monitor() -> None:
    """Señaliza al hilo que se detenga limpiamente."""
    _stop_event.set()
    if _monitor_thread and _monitor_thread.is_alive():
        _monitor_thread.join(timeout=5)
    logger.info("[MONITOR] Monitor detenido.")
