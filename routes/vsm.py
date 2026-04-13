"""
vsm.py — Value Stream Map dinámico para líneas de empaquetado farmacéutico.

Rutas HTML:
    GET  /vsm                           → Página principal del VSM

Rutas API:
    GET  /api/vsm/steps?line=N          → Pasos de proceso de la línea
    GET  /api/vsm/live-data?line=N      → Datos en vivo de todos los pasos
    GET  /api/vsm/step-history/<id>     → Historial del step (cycle time, últimas 20 lecturas)
    POST /api/vsm/seed                  → (re)carga datos de ejemplo
"""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, g

from database import get_db

bp = Blueprint("vsm", __name__)

# ── Traducciones de nombres de paso ──────────────────────────────────────────

STEP_NAME_EN = {
    "Recepción granel":  "Bulk Reception",
    "Alimentación":      "Feeding",
    "Llenado":           "Filling",
    "Pesaje":            "Weighing",
    "Cierre":            "Capping",
    "Etiquetado":        "Labelling",
    "Serialización":     "Serialization",
    "Estuchado":         "Cartoning",
    "Encajado":          "Case Packing",
    "Paletizado":        "Palletizing",
}


def _translate_step_name(name: str, lang: str) -> str:
    if lang == "en":
        return STEP_NAME_EN.get(name, name)
    return name


# ── Definición de pasos para empaquetado farmacéutico ─────────────────────────

PHARMA_STEPS = [
    # (order, name, type,             nominal_ct_s, nominal_co_min)
    (1,  "Recepción granel",   "non-value-add", 45.0,  15.0),
    (2,  "Alimentación",       "value-add",      8.0,  20.0),
    (3,  "Llenado",            "value-add",      6.0,  45.0),
    (4,  "Pesaje",             "value-add",      4.0,  15.0),
    (5,  "Cierre",             "value-add",      5.0,  30.0),
    (6,  "Etiquetado",         "value-add",      4.5,  25.0),
    (7,  "Serialización",      "value-add",      3.0,  20.0),
    (8,  "Estuchado",          "value-add",      6.5,  35.0),
    (9,  "Encajado",           "value-add",     12.0,  20.0),
    (10, "Paletizado",         "non-value-add", 18.0,  10.0),
]

STATUSES = ["running", "running", "running", "running", "stopped", "changeover", "waiting"]


def _seed_vsm(db, lines: list[int] = None) -> None:
    """Inserta los pasos y datos de ejemplo para las líneas indicadas."""
    if lines is None:
        lines = [1, 2, 3, 4]

    for line in lines:
        for order, name, stype, nom_ct, nom_co in PHARMA_STEPS:
            existing = db.execute(
                "SELECT id FROM process_steps WHERE line_number=? AND step_order=?",
                (line, order),
            ).fetchone()
            if not existing:
                db.execute(
                    """INSERT INTO process_steps
                       (site_id, line_number, step_order, step_name, step_type,
                        nominal_cycle_time_seconds, nominal_changeover_minutes)
                       VALUES (1,?,?,?,?,?,?)""",
                    (line, order, name, stype, nom_ct, nom_co),
                )

    db.commit()

    # Generar ~20 lecturas históricas por paso en las últimas 5 horas
    now = datetime.utcnow()
    rows = db.execute(
        "SELECT id, nominal_cycle_time_seconds, line_number FROM process_steps WHERE line_number IN (%s)"
        % ",".join("?" * len(lines)),
        lines,
    ).fetchall()

    for row in rows:
        step_id = row["id"]
        nom = row["nominal_cycle_time_seconds"]
        # Comprobar si ya tiene datos
        count = db.execute(
            "SELECT COUNT(*) as c FROM step_live_data WHERE step_id=?", (step_id,)
        ).fetchone()["c"]
        if count >= 5:
            continue

        for i in range(20):
            ts = (now - timedelta(minutes=(20 - i) * 15)).isoformat(sep=" ", timespec="seconds")
            jitter = random.uniform(0.85, 1.30)
            ct = round(nom * jitter, 2)
            wip = random.randint(0, 80)
            status = random.choice(STATUSES)
            speed = round(3600 / ct if ct > 0 else 0, 1)
            defects = random.randint(0, 3) if random.random() < 0.2 else 0
            db.execute(
                """INSERT INTO step_live_data
                   (step_id, timestamp, actual_cycle_time, units_in_wip,
                    status, current_speed, defect_count)
                   VALUES (?,?,?,?,?,?,?)""",
                (step_id, ts, ct, wip, status, speed, defects),
            )

    db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_per_step(db, line_number: int) -> list[dict]:
    """Devuelve la lectura más reciente de cada paso de la línea."""
    rows = db.execute(
        """
        SELECT ps.id          AS step_id,
               ps.step_order,
               ps.step_name,
               ps.step_type,
               ps.nominal_cycle_time_seconds  AS nom_ct,
               ps.nominal_changeover_minutes  AS nom_co,
               ld.actual_cycle_time,
               ld.units_in_wip,
               ld.status,
               ld.current_speed,
               ld.defect_count,
               ld.timestamp
        FROM process_steps ps
        LEFT JOIN step_live_data ld ON ld.id = (
            SELECT id FROM step_live_data
            WHERE step_id = ps.id
            ORDER BY timestamp DESC
            LIMIT 1
        )
        WHERE ps.line_number = ?
        ORDER BY ps.step_order
        """,
        (line_number,),
    ).fetchall()
    return [dict(r) for r in rows]


def _step_color(step: dict) -> str:
    status = step.get("status") or "waiting"
    nom = step.get("nom_ct") or 1
    actual = step.get("actual_cycle_time") or nom

    if status == "stopped":
        return "red"
    if status == "changeover":
        return "blue"
    if status == "waiting":
        return "gray"
    # running — evaluar vs nominal
    ratio = actual / nom if nom else 1
    if ratio > 1.25:
        return "red"
    if ratio > 1.10:
        return "yellow"
    return "green"


def _compute_metrics(steps: list[dict]) -> dict:
    """Calcula métricas resumen del VSM a partir de los pasos."""
    total_ct = 0.0
    va_ct = 0.0
    total_wip = 0
    max_ratio = 0.0
    bottleneck_name = ""
    total_defects = 0
    running_count = 0
    total_count = len(steps)

    for s in steps:
        nom = s.get("nom_ct") or 1
        actual = s.get("actual_cycle_time") or nom
        total_ct += actual
        if s.get("step_type") == "value-add":
            va_ct += actual
        total_wip += s.get("units_in_wip") or 0
        total_defects += s.get("defect_count") or 0
        ratio = actual / nom if nom else 1
        if ratio > max_ratio:
            max_ratio = ratio
            bottleneck_name = s.get("step_name", "")
        if (s.get("status") or "waiting") == "running":
            running_count += 1

    va_ratio = round(va_ct / total_ct * 100, 1) if total_ct else 0
    availability = round(running_count / total_count * 100, 1) if total_count else 0
    quality = round((1 - total_defects / max(total_wip, 1)) * 100, 1)
    quality = max(0.0, min(100.0, quality))
    # OEE simplificado: Disp * 1 (no tenemos performance por línea aquí) * Calidad
    oee = round(availability * quality / 100, 1)

    return {
        "lead_time_s": round(total_ct, 1),
        "va_time_s": round(va_ct, 1),
        "va_ratio_pct": va_ratio,
        "bottleneck": bottleneck_name,
        "total_wip": total_wip,
        "oee_pct": oee,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_and_notify_stopped_steps(
    db, steps: list[dict], line_number: int, base_url: str = ""
) -> None:
    """
    Para cada paso con status='stopped', comprueba cuánto tiempo lleva parado.
    Si supera STOPPED_THRESHOLD_MIN minutos, dispara la notificación a Teams.
    Para evitar spam, sólo notifica una vez por paso en una ventana de
    NOTIFY_COOLDOWN_MIN minutos (comprobando notification_log).
    """
    STOPPED_THRESHOLD_MIN = 5
    NOTIFY_COOLDOWN_MIN = 15  # no repetir la misma notificación antes de X min

    from site_aggregator import DEFAULT_SITE
    site_id = getattr(g, "current_site", DEFAULT_SITE)

    for step in steps:
        if step.get("status") != "stopped":
            continue

        step_id = step.get("step_id")
        step_name = step.get("step_name", f"Paso {step_id}")
        ts_str = step.get("timestamp")

        if not ts_str:
            continue

        # Calcular duración de la parada actual
        try:
            ts_dt = datetime.fromisoformat(ts_str)
        except ValueError:
            continue

        stopped_minutes = (datetime.utcnow() - ts_dt).total_seconds() / 60
        if stopped_minutes < STOPPED_THRESHOLD_MIN:
            continue

        # Comprobar cooldown usando la DB global de notificaciones
        try:
            import sqlite3 as _sqlite3
            from site_aggregator import SITES, DEFAULT_SITE as _DEFAULT_SITE
            _log_db = _sqlite3.connect(SITES[_DEFAULT_SITE]["db_path"])
            _log_db.row_factory = _sqlite3.Row
            try:
                recent = _log_db.execute(
                    """SELECT id FROM notification_log
                       WHERE event_type = 'vsm_stopped'
                         AND line_number = ?
                         AND site_id = ?
                         AND title LIKE ?
                         AND sent_at >= datetime('now', ?)
                       LIMIT 1""",
                    (
                        str(line_number),
                        site_id,
                        f"%{step_name}%",
                        f"-{NOTIFY_COOLDOWN_MIN} minutes",
                    ),
                ).fetchone()
            finally:
                _log_db.close()
        except Exception:
            recent = None

        if recent:
            continue

        # Disparar notificación
        try:
            from notifications import notify_vsm_stopped
            notify_vsm_stopped(
                step_name=step_name,
                step_id=step_id,
                line_number=line_number,
                stopped_minutes=stopped_minutes,
                site_id=site_id,
                base_url=base_url,
            )
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).exception("Error al enviar notificación VSM stopped")


# ── Rutas HTML ────────────────────────────────────────────────────────────────

@bp.get("/vsm")
def vsm_page():
    db = get_db()
    # Seed automático la primera vez
    _seed_vsm(db)
    # Líneas disponibles (las que tienen pasos definidos)
    lines_raw = db.execute(
        "SELECT DISTINCT line_number FROM process_steps ORDER BY line_number"
    ).fetchall()
    lines = [r["line_number"] for r in lines_raw]
    selected_line = int(request.args.get("line", lines[0] if lines else 1))
    return render_template("vsm/index.html", lines=lines, selected_line=selected_line)


# ── Rutas API ─────────────────────────────────────────────────────────────────

@bp.get("/api/vsm/steps")
def api_vsm_steps():
    line = int(request.args.get("line", 1))
    lang = request.args.get("lang", "es")
    db = get_db()
    rows = db.execute(
        """SELECT id, step_order, step_name, step_type,
                  nominal_cycle_time_seconds, nominal_changeover_minutes
           FROM process_steps WHERE line_number=? ORDER BY step_order""",
        (line,),
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["step_name"] = _translate_step_name(d["step_name"], lang)
        result.append(d)
    return jsonify(result)


@bp.get("/api/vsm/live-data")
def api_vsm_live():
    line = int(request.args.get("line", 1))
    lang = request.args.get("lang", "es")
    db = get_db()
    steps = _latest_per_step(db, line)

    # Traducir nombres y añadir color dinámico
    for s in steps:
        s["step_name"] = _translate_step_name(s["step_name"], lang)
        s["color"] = _step_color(s)
        s["ratio"] = round((s.get("actual_cycle_time") or s.get("nom_ct") or 1)
                           / (s.get("nom_ct") or 1), 3)

    metrics = _compute_metrics(steps)

    # ── Trigger: detectar pasos stopped durante más de 5 minutos ──────────────
    _check_and_notify_stopped_steps(db, steps, line, request.host_url.rstrip("/"))

    return jsonify({"steps": steps, "metrics": metrics})


@bp.get("/api/vsm/step-history/<int:step_id>")
def api_step_history(step_id: int):
    lang = request.args.get("lang", "es")
    db = get_db()
    step = db.execute(
        "SELECT * FROM process_steps WHERE id=?", (step_id,)
    ).fetchone()
    if not step:
        return jsonify({"error": "Step not found"}), 404

    step_dict = dict(step)
    step_dict["step_name"] = _translate_step_name(step_dict["step_name"], lang)

    history = db.execute(
        """SELECT timestamp, actual_cycle_time, units_in_wip,
                  status, current_speed, defect_count
           FROM step_live_data WHERE step_id=?
           ORDER BY timestamp DESC LIMIT 20""",
        (step_id,),
    ).fetchall()

    # Paradas recientes (últimas 5 lecturas con status != running)
    stops = db.execute(
        """SELECT timestamp, status, actual_cycle_time
           FROM step_live_data
           WHERE step_id=? AND status IN ('stopped','changeover','waiting')
           ORDER BY timestamp DESC LIMIT 5""",
        (step_id,),
    ).fetchall()

    return jsonify({
        "step": step_dict,
        "history": [dict(r) for r in reversed(history)],
        "recent_stops": [dict(r) for r in stops],
    })


@bp.get("/api/vsm/compare")
def api_vsm_compare():
    """
    Devuelve comparativa de cycle time (real y nominal) de todas las plantas
    para la línea indicada.  Formato de respuesta:
    {
      "steps":  ["Recepción granel", "Alimentación", ...],   # nombres de los pasos
      "sites": [
        {
          "site_id":   "alcobendas",
          "site_name": "Alcobendas",
          "flag":      "🇪🇸",
          "line":      1,
          "data": [                           # un elemento por paso, en orden
            {
              "step_name":    "Recepción granel",
              "nom_ct":       45.0,
              "actual_ct":    48.2,           # null si no hay lectura
              "ratio":        1.07,           # actual / nominal
              "status":       "running",
              "color":        "yellow",
            }, ...
          ],
          "metrics": { ... }                  # igual que /api/vsm/live-data
        }, ...
      ]
    }
    """
    from site_aggregator import SITES, get_site_connection

    line = int(request.args.get("line", 1))
    lang = request.args.get("lang", "es")

    # Obtener nombres canónicos de pasos (orden fijo, usamos PHARMA_STEPS)
    step_names = [_translate_step_name(name, lang) for _, name, *_ in PHARMA_STEPS]

    result_sites = []

    for site_id, site_meta in SITES.items():
        # Sólo procesamos si la línea existe para este site
        if line not in site_meta.get("lines", []):
            continue
        try:
            conn = get_site_connection(site_id)
            # Asegurar row_factory antes de pasar la conexión a _seed_vsm
            conn.row_factory = sqlite3.Row
            # Asegurar que existen datos de ejemplo para esta línea
            _seed_vsm(conn, lines=[line])

            rows = conn.execute(
                """
                SELECT ps.id AS step_id, ps.step_order, ps.step_name, ps.step_type,
                       ps.nominal_cycle_time_seconds AS nom_ct,
                       ps.nominal_changeover_minutes AS nom_co,
                       ld.actual_cycle_time, ld.units_in_wip,
                       ld.status, ld.current_speed, ld.defect_count, ld.timestamp
                FROM process_steps ps
                LEFT JOIN step_live_data ld ON ld.id = (
                    SELECT id FROM step_live_data
                    WHERE step_id = ps.id
                    ORDER BY timestamp DESC LIMIT 1
                )
                WHERE ps.line_number = ?
                ORDER BY ps.step_order
                """,
                (line,),
            ).fetchall()
            conn.close()
        except Exception:
            continue

        steps = [dict(r) for r in rows]
        for s in steps:
            s["step_name"] = _translate_step_name(s["step_name"], lang)
            s["color"] = _step_color(s)
            nom = s.get("nom_ct") or 1
            actual = s.get("actual_cycle_time") or nom
            s["ratio"] = round(actual / nom, 3)

        metrics = _compute_metrics(steps)
        result_sites.append({
            "site_id":   site_id,
            "site_name": site_meta["name"],
            "flag":      site_meta["flag"],
            "line":      line,
            "data":      steps,
            "metrics":   metrics,
        })

    return jsonify({"steps": step_names, "sites": result_sites})


@bp.post("/api/vsm/seed")
def api_vsm_seed():
    """Endpoint para regenerar datos de ejemplo (útil en demos)."""
    db = get_db()
    # Borrar datos live existentes para forzar regeneración
    db.execute("""
        DELETE FROM step_live_data
        WHERE step_id IN (SELECT id FROM process_steps)
    """)
    db.commit()
    _seed_vsm(db)
    return jsonify({"ok": True, "message": "Datos de ejemplo regenerados"})
