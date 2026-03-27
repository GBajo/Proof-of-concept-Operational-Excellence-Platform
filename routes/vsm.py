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
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from database import get_db

bp = Blueprint("vsm", __name__)

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
    db = get_db()
    rows = db.execute(
        """SELECT id, step_order, step_name, step_type,
                  nominal_cycle_time_seconds, nominal_changeover_minutes
           FROM process_steps WHERE line_number=? ORDER BY step_order""",
        (line,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.get("/api/vsm/live-data")
def api_vsm_live():
    line = int(request.args.get("line", 1))
    db = get_db()
    steps = _latest_per_step(db, line)

    # Añadir color dinámico
    for s in steps:
        s["color"] = _step_color(s)
        s["ratio"] = round((s.get("actual_cycle_time") or s.get("nom_ct") or 1)
                           / (s.get("nom_ct") or 1), 3)

    metrics = _compute_metrics(steps)
    return jsonify({"steps": steps, "metrics": metrics})


@bp.get("/api/vsm/step-history/<int:step_id>")
def api_step_history(step_id: int):
    db = get_db()
    step = db.execute(
        "SELECT * FROM process_steps WHERE id=?", (step_id,)
    ).fetchone()
    if not step:
        return jsonify({"error": "Step not found"}), 404

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
        "step": dict(step),
        "history": [dict(r) for r in reversed(history)],
        "recent_stops": [dict(r) for r in stops],
    })


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
