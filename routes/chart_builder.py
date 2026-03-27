"""
chart_builder.py — Generador de gráficos por lenguaje natural.

Rutas HTML:
    GET  /dashboard/builder          → Página del generador

Rutas API:
    POST /api/chart-builder/generate → Genera configuración ECharts vía LLM
    POST /api/chart-builder/save     → Guarda un gráfico en la BD
    GET  /api/chart-builder/history  → Lista de gráficos guardados
    DELETE /api/chart-builder/<id>   → Elimina un gráfico guardado
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from database import get_db
from llm_client import _call_gateway, _get_api_key, _mock_response
from ECHARTS_SYSTEM_PROMPT import ECHARTS_SYSTEM_PROMPT

bp = Blueprint("chart_builder", __name__)


# ── Consultas SQL para extraer datos relevantes ────────────────

def _query_db_for_prompt(prompt_lower: str, db) -> dict:
    """
    Decide qué datos extraer de la BD basándose en palabras clave del prompt.
    Devuelve un dict con los datos en formato serializable.
    """
    data: dict = {}
    now = datetime.utcnow()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    # OEE / rendimiento / tendencia
    if any(w in prompt_lower for w in ["oee", "rendimiento", "eficiencia", "tendencia"]):
        rows = db.execute("""
            SELECT s.line_number, s.start_time, s.shift_type,
                   SUM(k.units_produced) as total_prod,
                   SUM(k.units_rejected) as total_rej,
                   SUM(k.downtime_minutes) as total_dt,
                   MAX(k.target_units) as target,
                   MAX(k.nominal_speed) as nom_speed,
                   MAX(k.planned_time_min) as planned_min
            FROM shifts s
            JOIN kpi_readings k ON k.shift_id = s.id
            WHERE s.start_time >= ?
            GROUP BY s.id
            ORDER BY s.start_time ASC
            LIMIT 30
        """, (week_ago,)).fetchall()
        oee_list = []
        for r in rows:
            total = r["total_prod"] or 0
            rej = r["total_rej"] or 0
            dt = r["total_dt"] or 0
            target = r["target"] or 9600
            planned = r["planned_min"] or 480
            nom_speed = r["nom_speed"] or 1200
            availability = max(0, (planned - dt) / planned * 100) if planned else 0
            perf = min(100, total / (nom_speed * (planned - dt) / 60) * 100) if nom_speed and planned > dt else 0
            qual = (total - rej) / total * 100 if total else 100
            oee = round(availability * perf * qual / 10000, 1)
            oee_list.append({
                "fecha": r["start_time"][:10],
                "linea": r["line_number"],
                "turno": r["shift_type"],
                "oee": oee,
                "disponibilidad": round(availability, 1),
                "rendimiento": round(perf, 1),
                "calidad": round(qual, 1),
            })
        data["oee_por_turno"] = oee_list

    # Producción / unidades / objetivo
    if any(w in prompt_lower for w in ["produccion", "producción", "unidades", "objetivo", "output"]):
        rows = db.execute("""
            SELECT s.line_number,
                   SUM(k.units_produced) as total_prod,
                   SUM(k.units_rejected) as total_rej,
                   MAX(k.target_units) as target
            FROM shifts s
            JOIN kpi_readings k ON k.shift_id = s.id
            WHERE s.start_time >= ?
            GROUP BY s.line_number
            ORDER BY s.line_number
        """, (week_ago,)).fetchall()
        data["produccion_por_linea"] = [dict(r) for r in rows]

    # Paradas / downtime
    if any(w in prompt_lower for w in ["parada", "paradas", "downtime", "tiempo parado", "inactividad"]):
        rows = db.execute("""
            SELECT s.line_number, s.shift_type, s.start_time,
                   SUM(k.downtime_minutes) as total_dt
            FROM shifts s
            JOIN kpi_readings k ON k.shift_id = s.id
            WHERE s.start_time >= ?
            GROUP BY s.id
            ORDER BY s.start_time DESC
            LIMIT 20
        """, (week_ago,)).fetchall()
        data["paradas_por_turno"] = [dict(r) for r in rows]

    # Rechazos / calidad / tasa rechazo
    if any(w in prompt_lower for w in ["rechazo", "rechazos", "calidad", "defecto", "right first time", "rft"]):
        rows = db.execute("""
            SELECT s.line_number, s.start_time,
                   SUM(k.units_produced) as total_prod,
                   SUM(k.units_rejected) as total_rej
            FROM shifts s
            JOIN kpi_readings k ON k.shift_id = s.id
            WHERE s.start_time >= ?
            GROUP BY s.id
            ORDER BY s.start_time ASC
            LIMIT 20
        """, (week_ago,)).fetchall()
        data["rechazos_por_turno"] = [
            {**dict(r), "tasa_rechazo_pct": round(r["total_rej"] / r["total_prod"] * 100, 2)
             if r["total_prod"] else 0}
            for r in rows
        ]

    # Velocidad de línea
    if any(w in prompt_lower for w in ["velocidad", "speed", "uph", "cadencia"]):
        rows = db.execute("""
            SELECT s.line_number, k.timestamp, k.line_speed, k.nominal_speed
            FROM shifts s
            JOIN kpi_readings k ON k.shift_id = s.id
            WHERE s.start_time >= ?
            ORDER BY k.timestamp ASC
            LIMIT 50
        """, (week_ago,)).fetchall()
        data["velocidad_linea"] = [dict(r) for r in rows]

    # Comentarios / incidencias
    if any(w in prompt_lower for w in ["comentario", "comentarios", "incidencia", "categoria", "categoría"]):
        rows = db.execute("""
            SELECT category, COUNT(*) as total
            FROM comments
            WHERE timestamp >= ?
            GROUP BY category
        """, (week_ago,)).fetchall()
        data["comentarios_por_categoria"] = [dict(r) for r in rows]

    # Comparativa entre líneas
    if any(w in prompt_lower for w in ["línea 1", "línea 2", "linea 1", "linea 2", "compara", "comparar", "comparativa", "entre líneas"]):
        rows = db.execute("""
            SELECT s.line_number,
                   COUNT(DISTINCT s.id) as num_turnos,
                   SUM(k.units_produced) as total_prod,
                   SUM(k.units_rejected) as total_rej,
                   SUM(k.downtime_minutes) as total_dt
            FROM shifts s
            JOIN kpi_readings k ON k.shift_id = s.id
            WHERE s.start_time >= ?
            GROUP BY s.line_number
            ORDER BY s.line_number
        """, (month_ago,)).fetchall()
        data["resumen_por_linea"] = [dict(r) for r in rows]

    # Si no se detectó nada específico, devolver resumen general
    if not data:
        rows = db.execute("""
            SELECT s.line_number, s.status, s.shift_type,
                   COUNT(DISTINCT s.id) as turnos,
                   SUM(k.units_produced) as total_prod,
                   SUM(k.downtime_minutes) as total_dt
            FROM shifts s
            LEFT JOIN kpi_readings k ON k.shift_id = s.id
            WHERE s.start_time >= ?
            GROUP BY s.line_number
            ORDER BY s.line_number
        """, (week_ago,)).fetchall()
        data["resumen_semanal"] = [dict(r) for r in rows]

    return data


def _call_chart_llm(prompt: str, db_data: dict, api_key: str) -> str | None:
    """
    Llama al LLM Gateway con el prompt del usuario y los datos de la BD.
    Usa ECHARTS_SYSTEM_PROMPT como system prompt para forzar JSON puro.
    Devuelve el JSON raw de la opción ECharts, o None si falla.
    """
    schema_summary = """
Datos disponibles de la BD (últimos días):
""" + json.dumps(db_data, ensure_ascii=False, default=str, indent=2)

    user_message = f"""Petición del usuario: {prompt}

{schema_summary}

Genera la configuración ECharts para visualizar estos datos según la petición.
Devuelve ÚNICAMENTE el JSON del objeto option, sin markdown ni explicaciones."""

    result = _call_gateway(user_message, api_key, system=ECHARTS_SYSTEM_PROMPT)
    return result.get("text", "")


def _extract_json(raw: str) -> dict | None:
    """
    Extrae y parsea el primer objeto JSON válido de la respuesta del LLM.
    Elimina bloques markdown si los hay.
    """
    if not raw:
        return None
    # Eliminar bloques ```json ... ```
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    # Buscar el primer { ... } completo
    start = cleaned.find("{")
    if start == -1:
        return None
    depth = 0
    end = -1
    for i, ch in enumerate(cleaned[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None


def _mock_chart(prompt: str, db_data: dict) -> dict:
    """
    Genera una configuración ECharts de ejemplo cuando el gateway no está disponible.
    """
    prompt_lower = prompt.lower()

    # Gráfico de líneas para OEE
    if any(w in prompt_lower for w in ["oee", "tendencia", "rendimiento"]):
        oee_data = db_data.get("oee_por_turno", [])
        if oee_data:
            fechas = [d["fecha"] for d in oee_data[-10:]]
            oee_vals = [d["oee"] for d in oee_data[-10:]]
        else:
            fechas = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
            oee_vals = [72, 75, 68, 81, 79, 74, 77]
        return {
            "title": {"text": "Tendencia OEE", "left": "center"},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": fechas},
            "yAxis": {"type": "value", "min": 0, "max": 100,
                      "axisLabel": {"formatter": "{value}%"}},
            "series": [{"name": "OEE", "type": "line", "data": oee_vals,
                        "smooth": True, "lineStyle": {"width": 3},
                        "areaStyle": {"opacity": 0.15}}]
        }

    # Gráfico de barras para producción
    if any(w in prompt_lower for w in ["produccion", "producción", "unidades", "objetivo"]):
        prod_data = db_data.get("produccion_por_linea", [])
        if prod_data:
            lineas = [f"L{d['line_number']}" for d in prod_data]
            prod = [d["total_prod"] or 0 for d in prod_data]
            targets = [d["target"] or 9600 for d in prod_data]
        else:
            lineas = ["L1", "L2", "L3", "L4"]
            prod = [8200, 7500, 9100, 6800]
            targets = [9600, 9600, 9600, 9600]
        return {
            "title": {"text": "Producción vs Objetivo por Línea", "left": "center"},
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["Producido", "Objetivo"], "bottom": 0},
            "xAxis": {"type": "category", "data": lineas},
            "yAxis": {"type": "value"},
            "series": [
                {"name": "Producido", "type": "bar", "data": prod,
                 "itemStyle": {"color": "#0057a8"}},
                {"name": "Objetivo", "type": "bar", "data": targets,
                 "itemStyle": {"color": "#a0aab4"}}
            ]
        }

    # Dona para rechazos / categorías
    if any(w in prompt_lower for w in ["rechazo", "calidad", "comentario", "categoría", "categoria"]):
        cat_data = db_data.get("comentarios_por_categoria", [])
        if cat_data:
            pie_data = [{"value": d["total"], "name": d["category"].capitalize()}
                        for d in cat_data]
        else:
            pie_data = [{"value": 35, "name": "Producción"}, {"value": 25, "name": "Mantenimiento"},
                        {"value": 20, "name": "Calidad"}, {"value": 20, "name": "Seguridad"}]
        return {
            "title": {"text": "Distribución por Categoría", "left": "center"},
            "tooltip": {"trigger": "item"},
            "legend": {"bottom": "5%", "left": "center"},
            "series": [{"type": "pie", "radius": ["40%", "70%"],
                        "avoidLabelOverlap": False,
                        "label": {"show": False},
                        "emphasis": {"label": {"show": True, "fontSize": 18}},
                        "data": pie_data}]
        }

    # Default: resumen semanal en barras
    resumen = db_data.get("resumen_semanal", [])
    if resumen:
        lineas = [f"L{d['line_number']}" for d in resumen]
        prod = [d["total_prod"] or 0 for d in resumen]
    else:
        lineas = ["L1", "L2", "L3"]
        prod = [8000, 7200, 9000]
    return {
        "title": {"text": "Resumen Semanal", "left": "center"},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": lineas},
        "yAxis": {"type": "value"},
        "series": [{"name": "Unidades producidas", "type": "bar",
                    "data": prod, "itemStyle": {"color": "#0057a8"}}]
    }


# ── Rutas HTML ─────────────────────────────────────────────────

@bp.get("/dashboard/builder")
def chart_builder():
    return render_template("dashboard/builder.html")


# ── Rutas API ──────────────────────────────────────────────────

@bp.post("/api/chart-builder/generate")
def generate_chart():
    """
    Recibe un prompt en lenguaje natural, consulta la BD, llama al LLM
    y devuelve la configuración ECharts lista para renderizar.
    """
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "El prompt no puede estar vacío"}), 400

    db = get_db()
    prompt_lower = prompt.lower()

    # 1. Extraer datos relevantes de la BD
    db_data = _query_db_for_prompt(prompt_lower, db)

    # 2. Llamar al LLM
    api_key = _get_api_key()
    source = "gateway"
    echarts_option = None
    error_msg = None

    if api_key:
        try:
            raw = _call_chart_llm(prompt, db_data, api_key)
            echarts_option = _extract_json(raw)
            if echarts_option is None:
                # Reintentar una vez
                raw2 = _call_chart_llm(
                    f"IMPORTANTE: devuelve SOLO JSON válido sin markdown. {prompt}",
                    db_data, api_key
                )
                echarts_option = _extract_json(raw2)
                if echarts_option is None:
                    error_msg = "El LLM devolvió JSON inválido tras dos intentos. Mostrando gráfico de ejemplo."
                    source = "mock"
        except Exception as e:
            error_msg = f"Error al conectar con el gateway: {str(e)[:120]}"
            source = "mock"
    else:
        error_msg = "Token de autenticación no disponible — mostrando gráfico de ejemplo"
        source = "mock"

    # Fallback al mock
    if echarts_option is None:
        echarts_option = _mock_chart(prompt, db_data)

    return jsonify({
        "option": echarts_option,
        "source": source,
        "error": error_msg,
        "data_rows": sum(len(v) if isinstance(v, list) else 1 for v in db_data.values()),
    }), 200


@bp.post("/api/chart-builder/save")
def save_chart():
    """Guarda la configuración ECharts junto con el prompt que la generó."""
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    title = (data.get("title") or prompt[:60] or "Gráfico sin título").strip()
    option = data.get("option")

    if not prompt or not option:
        return jsonify({"error": "Faltan campos requeridos (prompt, option)"}), 400

    try:
        echarts_json = json.dumps(option, ensure_ascii=False)
    except (TypeError, ValueError):
        return jsonify({"error": "La opción ECharts no es JSON serializable"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO saved_charts (title, prompt_text, echarts_json) VALUES (?, ?, ?)",
        (title, prompt, echarts_json),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "title": title}), 201


@bp.get("/api/chart-builder/history")
def chart_history():
    """Devuelve los gráficos guardados, del más reciente al más antiguo."""
    db = get_db()
    rows = db.execute(
        "SELECT id, title, prompt_text, created_at FROM saved_charts ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@bp.delete("/api/chart-builder/<int:chart_id>")
def delete_chart(chart_id: int):
    db = get_db()
    db.execute("DELETE FROM saved_charts WHERE id = ?", (chart_id,))
    db.commit()
    return jsonify({"deleted": chart_id}), 200
