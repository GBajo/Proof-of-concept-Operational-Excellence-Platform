"""
site_aggregator.py — Gestión multi-planta.

Define las 4 plantas del grupo, sus bases de datos SQLite y funciones
de agregación cross-site para comparativas y rankings.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

# ── Definición de plantas ────────────────────────────────────────────────────

SITES: dict[str, dict] = {
    "alcobendas": {
        "name":       "Alcobendas",
        "country":    "España",
        "flag":       "🇪🇸",
        "timezone":   "Europe/Madrid",
        "utc_offset": 1,
        "db_path":    "site_alcobendas.db",
        "target_oee": 82,
        "lines":      [1, 2, 3],
    },
    "indianapolis": {
        "name":       "Indianapolis",
        "country":    "USA",
        "flag":       "🇺🇸",
        "timezone":   "America/Indianapolis",
        "utc_offset": -5,
        "db_path":    "site_indianapolis.db",
        "target_oee": 88,
        "lines":      [1, 2, 3],
    },
    "fegersheim": {
        "name":       "Fegersheim",
        "country":    "France",
        "flag":       "🇫🇷",
        "timezone":   "Europe/Paris",
        "utc_offset": 1,
        "db_path":    "site_fegersheim.db",
        "target_oee": 79,
        "lines":      [1, 2, 3],
    },
    "sesto": {
        "name":       "Sesto S.G.",
        "country":    "Italia",
        "flag":       "🇮🇹",
        "timezone":   "Europe/Rome",
        "utc_offset": 1,
        "db_path":    "site_sesto.db",
        "target_oee": 85,
        "lines":      [1, 2, 3],
    },
    "seishin": {
        "name":       "Seishin",
        "country":    "Japan",
        "flag":       "🇯🇵",
        "timezone":   "Asia/Tokyo",
        "utc_offset": 9,
        "db_path":    "site_seishin.db",
        "target_oee": 90,
        "lines":      [1, 2, 3],
    },
}

DEFAULT_SITE = "alcobendas"

# ── Conexión directa (fuera de contexto Flask) ────────────────────────────────

def get_site_connection(site_id: str) -> sqlite3.Connection:
    """Abre una conexión directa a la BD del site (sin Flask g)."""
    site = SITES.get(site_id, SITES[DEFAULT_SITE])
    conn = sqlite3.connect(site["db_path"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Cálculo de OEE ────────────────────────────────────────────────────────────

def _calc_oee(units: float, rejected: float, downtime: float,
              shifts: int, planned_time: float = 0.0, nom_speed: float = 1200.0) -> dict:
    planned = planned_time if planned_time > 0 else shifts * 480.0
    avail = max(0.0, (planned - downtime) / planned * 100) if planned else 0.0
    perf  = units / (nom_speed * max(planned - downtime, 1) / 60) * 100 if nom_speed and planned else 0.0
    qual  = (units - rejected) / units * 100 if units else 0.0
    oee   = round(avail * perf * qual / 10_000, 1)
    return {
        "oee":          oee,
        "availability": round(avail, 1),
        "performance":  round(perf, 1),
        "quality":      round(qual, 1),
    }


# ── KPIs por planta ───────────────────────────────────────────────────────────

def get_site_kpis(site_id: str, days: int = 7) -> dict:
    """Devuelve KPI resumen para una planta."""
    conn = get_site_connection(site_id)
    try:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat(sep=" ")
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT s.id)      AS total_shifts,
                SUM(k.units_produced)     AS total_units,
                SUM(k.units_rejected)     AS total_rejected,
                SUM(k.downtime_minutes)   AS total_downtime,
                SUM(k.planned_time_min)   AS total_planned_time,
                AVG(k.nominal_speed)      AS avg_nominal_speed
            FROM shifts s
            JOIN kpi_readings k ON k.shift_id = s.id
            WHERE s.start_time >= ? AND s.status = 'completed'
        """, (since,)).fetchone()

        total   = row["total_units"]        or 0
        rej     = row["total_rejected"]     or 0
        dt      = row["total_downtime"]     or 0
        shifts  = row["total_shifts"]       or 1
        planned = row["total_planned_time"] or (shifts * 480.0)
        nom_spd = row["avg_nominal_speed"]  or 1200.0

        oee_data = _calc_oee(total, rej, dt, shifts, planned_time=planned, nom_speed=nom_spd)

        return {
            "site_id":       site_id,
            "site_name":     SITES[site_id]["name"],
            "flag":          SITES[site_id]["flag"],
            "country":       SITES[site_id]["country"],
            "target_oee":    SITES[site_id]["target_oee"],
            "total_units":   int(total),
            "total_rejected":int(rej),
            "total_downtime":round(dt, 0),
            "total_shifts":  int(shifts),
            **oee_data,
        }
    finally:
        conn.close()


def get_all_sites_kpis(days: int = 7) -> list[dict]:
    """Devuelve KPI resumen para todas las plantas."""
    return [get_site_kpis(sid, days) for sid in SITES]


def get_site_rankings(metric: str = "oee", days: int = 7) -> list[dict]:
    """Devuelve las plantas ordenadas por una métrica."""
    kpis = get_all_sites_kpis(days)
    kpis.sort(key=lambda x: x.get(metric, 0), reverse=True)
    for i, s in enumerate(kpis):
        s["rank"] = i + 1
    return kpis


# ── Comparativa temporal cross-site ──────────────────────────────────────────

def get_cross_site_comparison(metric: str = "oee", days: int = 14) -> dict:
    """
    Devuelve series temporales de una métrica para todas las plantas.
    Útil para generar gráficos comparativos.
    """
    result: dict = {}
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(sep=" ")

    for site_id in SITES:
        conn = get_site_connection(site_id)
        try:
            rows = conn.execute("""
                SELECT
                    DATE(s.start_time)        AS date,
                    SUM(k.units_produced)     AS units,
                    SUM(k.units_rejected)     AS rejected,
                    SUM(k.downtime_minutes)   AS downtime,
                    COUNT(DISTINCT s.id)      AS shifts,
                    SUM(k.planned_time_min)   AS planned_time,
                    AVG(k.nominal_speed)      AS avg_nominal_speed
                FROM shifts s
                JOIN kpi_readings k ON k.shift_id = s.id
                WHERE s.start_time >= ? AND s.status = 'completed'
                GROUP BY DATE(s.start_time)
                ORDER BY date
            """, (since,)).fetchall()

            series = []
            for r in rows:
                oee_data = _calc_oee(
                    r["units"] or 0, r["rejected"] or 0,
                    r["downtime"] or 0, r["shifts"] or 1,
                    planned_time=r["planned_time"] or 0,
                    nom_speed=r["avg_nominal_speed"] or 1200.0,
                )
                val = {
                    "oee":          oee_data["oee"],
                    "availability": oee_data["availability"],
                    "performance":  oee_data["performance"],
                    "quality":      oee_data["quality"],
                    "units":        r["units"] or 0,
                    "downtime":     round(r["downtime"] or 0, 1),
                }.get(metric)  # devuelve None si la métrica no existe, no silencia con OEE
                if val is None:
                    val = oee_data.get(metric, 0)  # último recurso: 0, no valor incorrecto
                series.append({"date": r["date"], "value": val})

            result[site_id] = {
                "name":   SITES[site_id]["name"],
                "flag":   SITES[site_id]["flag"],
                "series": series,
            }
        finally:
            conn.close()

    return result


# ── Resumen global agregado ───────────────────────────────────────────────────

def get_global_summary(days: int = 7) -> dict:
    """Agrega KPIs de todas las plantas en un único resumen global."""
    all_kpis = get_all_sites_kpis(days)
    total_units    = sum(k["total_units"]    for k in all_kpis)
    total_rejected = sum(k["total_rejected"] for k in all_kpis)
    total_downtime = sum(k["total_downtime"] for k in all_kpis)
    total_shifts   = sum(k["total_shifts"]   for k in all_kpis)

    oee_data = _calc_oee(total_units, total_rejected, total_downtime, total_shifts,
                         planned_time=0.0, nom_speed=1200.0)
    return {
        "sites":         len(all_kpis),
        "total_units":   total_units,
        "total_rejected":total_rejected,
        "total_downtime":round(total_downtime, 0),
        "total_shifts":  total_shifts,
        **oee_data,
    }
