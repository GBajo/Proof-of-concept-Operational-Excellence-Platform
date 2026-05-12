"""Funciones de acceso a datos reutilizadas por todos los widgets."""
from __future__ import annotations


def get_site_oee(site_id: str, days: int = 1) -> dict:
    from site_aggregator import get_site_kpis

    kpi = get_site_kpis(site_id, days=days) or {}
    return {
        "oee": round(kpi.get("oee") or 0, 1),
        "availability": round(kpi.get("availability") or 0, 1),
        "performance": round(kpi.get("performance") or 0, 1),
        "quality": round(kpi.get("quality") or 0, 1),
        "units_produced": int(kpi.get("units_produced") or 0),
        "units_rejected": int(kpi.get("units_rejected") or 0),
        "downtime_minutes": round(kpi.get("downtime_minutes") or 0, 1),
        "shifts_count": int(kpi.get("shifts_count") or 0),
    }


def get_line_performance(site_id: str, line_number: int | None = None, days: int = 7) -> list[dict]:
    from database import get_db

    db = get_db(site_id)
    line_filter = "AND s.line_number = ?" if line_number else ""
    params: list = [f"-{days} days"]
    if line_number:
        params.append(line_number)

    rows = db.execute(
        f"""
        SELECT s.line_number,
               COUNT(DISTINCT s.id)        AS shift_count,
               COALESCE(SUM(r.units_produced),   0) AS total_units,
               COALESCE(SUM(r.units_rejected),   0) AS total_rejected,
               COALESCE(SUM(r.downtime_minutes), 0) AS total_downtime,
               COALESCE(AVG(r.line_speed),       0) AS avg_speed
        FROM shifts s
        LEFT JOIN kpi_readings r ON r.shift_id = s.id
        WHERE s.start_time >= datetime('now', ?) {line_filter}
        GROUP BY s.line_number
        ORDER BY s.line_number
        """,
        params,
    ).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        # Objetivo aproximado: 300 uds/h × 8 h × nº turnos (demo)
        d["target_units"] = int(d["shift_count"]) * 300 * 8
        result.append(d)
    return result


def get_metric_trend(
    site_id: str,
    line_number: int | None,
    metric: str = "oee",
    period: str = "7d",
) -> dict:
    from database import get_db

    period_days = {"24h": 1, "7d": 7, "30d": 30}.get(period, 7)
    db = get_db(site_id)

    line_filter = "AND s.line_number = ?" if line_number else ""
    params: list = [f"-{period_days} days"]
    if line_number:
        params.append(line_number)

    metric_expr = {
        "oee": (
            "CASE WHEN SUM(r.units_produced + r.units_rejected) > 0 "
            "THEN ROUND(SUM(r.units_produced)*100.0/"
            "SUM(r.units_produced + r.units_rejected),1) ELSE 0 END"
        ),
        "units_produced": "COALESCE(SUM(r.units_produced), 0)",
        "reject_rate": (
            "CASE WHEN SUM(r.units_produced + r.units_rejected) > 0 "
            "THEN ROUND(SUM(r.units_rejected)*100.0/"
            "SUM(r.units_produced + r.units_rejected),2) ELSE 0 END"
        ),
        "downtime": "COALESCE(SUM(r.downtime_minutes), 0)",
    }.get(metric, "COALESCE(SUM(r.units_produced), 0)")

    rows = db.execute(
        f"""
        SELECT substr(s.start_time, 1, 16) AS label,
               {metric_expr}              AS value
        FROM shifts s
        LEFT JOIN kpi_readings r ON r.shift_id = s.id
        WHERE s.start_time >= datetime('now', ?) {line_filter}
        GROUP BY s.id
        ORDER BY s.start_time ASC
        LIMIT 30
        """,
        params,
    ).fetchall()

    labels = [r["label"].replace("T", " ").replace("-", "/") for r in rows]
    values = [round(r["value"] or 0, 2) for r in rows]
    return {"labels": labels, "values": values, "metric": metric}


def get_reject_distribution(
    site_id: str, line_number: int | None = None, days: int = 7
) -> dict:
    from database import get_db

    db = get_db(site_id)
    line_filter = "AND s.line_number = ?" if line_number else ""
    params: list = [f"-{days} days"]
    if line_number:
        params.append(line_number)

    row = db.execute(
        f"""
        SELECT COALESCE(SUM(r.units_produced), 0) AS produced,
               COALESCE(SUM(r.units_rejected), 0) AS rejected
        FROM kpi_readings r
        JOIN shifts s ON s.id = r.shift_id
        WHERE s.start_time >= datetime('now', ?) {line_filter}
        """,
        params,
    ).fetchone()

    produced = int(row["produced"] or 0) if row else 0
    rejected = int(row["rejected"] or 0) if row else 0
    good = max(0, produced - rejected)

    cat_rows = db.execute(
        f"""
        SELECT c.category, COUNT(*) AS cnt
        FROM comments c
        JOIN shifts s ON s.id = c.shift_id
        WHERE s.start_time >= datetime('now', ?) {line_filter}
        GROUP BY c.category
        """,
        params,
    ).fetchall()

    categories = {r["category"]: r["cnt"] for r in cat_rows}
    return {"good": good, "rejected": rejected, "total": produced, "categories": categories}


def get_kpi_metric_value(
    site_id: str,
    line_number: int | None = None,
    metric: str = "oee",
    days: int = 1,
) -> dict:
    current = get_site_oee(site_id, days=days)
    prev = get_site_oee(site_id, days=days * 2)

    value = current.get(metric, 0) or 0
    prev_value = prev.get(metric, 0) or 0
    trend = round(value - prev_value, 1)

    return {"value": value, "trend": trend, "metric": metric}


def get_downtime_heatmap(
    site_id: str, line_number: int | None = None, days: int = 14
) -> dict:
    from database import get_db

    db = get_db(site_id)
    line_filter = "AND s.line_number = ?" if line_number else ""
    params: list = [f"-{days} days"]
    if line_number:
        params.append(line_number)

    rows = db.execute(
        f"""
        SELECT CAST(strftime('%w', r.timestamp) AS INTEGER) AS dow,
               CAST(strftime('%H', r.timestamp) AS INTEGER) AS hour,
               COALESCE(SUM(r.downtime_minutes), 0)         AS total_dt
        FROM kpi_readings r
        JOIN shifts s ON s.id = r.shift_id
        WHERE r.timestamp >= datetime('now', ?) {line_filter}
        GROUP BY dow, hour
        """,
        params,
    ).fetchall()

    data = [[r["hour"], r["dow"], round(r["total_dt"] or 0, 1)] for r in rows]
    max_val = max((r["total_dt"] or 0 for r in rows), default=10)
    return {"data": data, "max_val": max(float(max_val), 1.0)}


def get_pareto_data(
    site_id: str,
    line_number: int | None = None,
    days: int = 30,
    max_causes: int = 8,
) -> dict:
    from database import get_db

    db = get_db(site_id)
    line_filter = "AND s.line_number = ?" if line_number else ""
    params: list = [f"-{days} days", max_causes]
    if line_number:
        params.insert(1, line_number)

    rows = db.execute(
        f"""
        SELECT c.category, COUNT(*) AS cnt
        FROM comments c
        JOIN shifts s ON s.id = c.shift_id
        WHERE s.start_time >= datetime('now', ?) {line_filter}
        GROUP BY c.category
        ORDER BY cnt DESC
        LIMIT ?
        """,
        params,
    ).fetchall()

    labels = [r["category"] for r in rows]
    counts = [r["cnt"] for r in rows]
    total = sum(counts) or 1
    cumulative: list[float] = []
    acc = 0
    for c in counts:
        acc += c
        cumulative.append(round(acc * 100 / total, 1))

    return {"labels": labels, "counts": counts, "cumulative": cumulative}


def get_line_speed(site_id: str, line_number: int | None = None) -> dict:
    from database import get_db

    db = get_db(site_id)
    line_filter = "AND s.line_number = ?" if line_number else ""
    params: list = []
    if line_number:
        params.append(line_number)

    row = db.execute(
        f"""
        SELECT r.line_speed
        FROM kpi_readings r
        JOIN shifts s ON s.id = r.shift_id
        WHERE s.status = 'active' {line_filter}
        ORDER BY r.timestamp DESC
        LIMIT 1
        """,
        params,
    ).fetchone()

    if not row:
        row = db.execute(
            f"""
            SELECT r.line_speed
            FROM kpi_readings r
            JOIN shifts s ON s.id = r.shift_id
            WHERE 1=1 {line_filter}
            ORDER BY r.timestamp DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    return {"speed": round(float(row["line_speed"] or 0), 0) if row else 0.0}


def get_vsm_data(site_id: str, line_number: int | None = None) -> dict:
    # Demo: pasos genéricos de una línea de blíster farmacéutico
    return {
        "steps": [
            {"name": "Alimentación", "cycle_time": 2.5, "uptime": 95},
            {"name": "Termoformado", "cycle_time": 3.2, "uptime": 88},
            {"name": "Llenado", "cycle_time": 2.8, "uptime": 92},
            {"name": "Sellado", "cycle_time": 3.0, "uptime": 90},
            {"name": "Inspección", "cycle_time": 1.5, "uptime": 98},
            {"name": "Encartuchado", "cycle_time": 2.2, "uptime": 94},
        ]
    }


def get_sqdcp_data(site_id: str, line_number: int | None = None, days: int = 7) -> dict:
    from database import get_db

    db = get_db(site_id)
    line_filter = "AND line_number = ?" if line_number else ""
    params: list = [f"-{days} days"]
    if line_number:
        params.append(line_number)

    try:
        rows = db.execute(
            f"""
            SELECT category, AVG(score) AS avg_score
            FROM sqdcp_scores
            WHERE recorded_at >= datetime('now', ?) {line_filter}
            GROUP BY category
            """,
            params,
        ).fetchall()
        if rows:
            scores = {r["category"]: round(r["avg_score"] or 0, 1) for r in rows}
            return {
                "seguridad": scores.get("S", scores.get("safety", 80)),
                "calidad": scores.get("Q", scores.get("quality", 75)),
                "entrega": scores.get("D", scores.get("delivery", 85)),
                "coste": scores.get("C", scores.get("cost", 70)),
                "personal": scores.get("P", scores.get("people", 82)),
            }
    except Exception:
        pass

    # Fallback derivado de datos de KPI
    oee_data = get_site_oee(site_id, days=days)
    produced = oee_data.get("units_produced", 1) or 1
    rejected = oee_data.get("units_rejected", 0) or 0
    reject_pct = (rejected / produced) * 100

    return {
        "seguridad": round(min(98, 85 + (days % 10)), 1),
        "calidad": round(max(0, 100 - reject_pct * 3), 1),
        "entrega": oee_data.get("availability", 80),
        "coste": oee_data.get("performance", 75),
        "personal": round(min(95, 72 + (days % 18)), 1),
    }
