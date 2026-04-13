from typing import Optional
from database import get_db


def create_kpi_reading(shift_id: int, units_produced: int, units_rejected: int,
                       downtime_minutes: float, line_speed: float,
                       target_units: int, nominal_speed: float,
                       planned_time_min: float = 480.0) -> int:
    db = get_db()
    cursor = db.execute(
        """INSERT INTO kpi_readings
           (shift_id, units_produced, units_rejected, downtime_minutes,
            line_speed, target_units, nominal_speed, planned_time_min)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (shift_id, units_produced, units_rejected, downtime_minutes,
         line_speed, target_units, nominal_speed, planned_time_min),
    )
    db.commit()
    return cursor.lastrowid


def get_kpi_readings_by_shift(shift_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM kpi_readings WHERE shift_id = ? ORDER BY timestamp ASC",
        (shift_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_kpi_reading(shift_id: int) -> Optional[dict]:
    db = get_db()
    row = db.execute(
        "SELECT * FROM kpi_readings WHERE shift_id = ? ORDER BY timestamp DESC LIMIT 1",
        (shift_id,),
    ).fetchone()
    return dict(row) if row else None


def calculate_oee(shift_id: int) -> dict:
    """Calcula OEE y KPIs agregados para un turno. Nunca almacenado."""
    db = get_db()
    row = db.execute(
        """SELECT
               SUM(units_produced)   AS total_produced,
               SUM(units_rejected)   AS total_rejected,
               SUM(downtime_minutes) AS total_downtime,
               AVG(CASE WHEN line_speed > 0 THEN line_speed END) AS avg_speed,
               MAX(planned_time_min) AS planned_time,
               MAX(nominal_speed)    AS nominal_speed,
               MAX(target_units)     AS target_units
           FROM kpi_readings
           WHERE shift_id = ?""",
        (shift_id,),
    ).fetchone()

    if not row or row["total_produced"] is None:
        return _empty_oee()

    total_produced = int(row["total_produced"] or 0)
    total_rejected = int(row["total_rejected"] or 0)
    total_downtime = float(row["total_downtime"] or 0.0)
    planned_time = float(row["planned_time"] or 480.0)
    nominal_speed = float(row["nominal_speed"] or 0.0)
    target_units = int(row["target_units"] or 0)

    # Disponibilidad
    operating_time = max(planned_time - total_downtime, 0.0)
    availability = operating_time / planned_time if planned_time > 0 else 0.0

    # Rendimiento (clamp a 100 %: no se puede superar el nominal)
    ideal_units = nominal_speed * (operating_time / 60.0) if nominal_speed > 0 else 0.0
    performance = min((total_produced / ideal_units), 1.0) if ideal_units > 0 else 0.0

    # Calidad
    good_units = max(total_produced - total_rejected, 0)
    quality = good_units / total_produced if total_produced > 0 else 0.0

    oee = availability * performance * quality * 100.0

    reject_rate = (total_rejected / total_produced * 100.0) if total_produced > 0 else 0.0

    return {
        "oee": round(oee, 1),
        "availability": round(availability * 100, 1),
        "performance": round(performance * 100, 1),
        "quality": round(quality * 100, 1),
        "total_units_produced": total_produced,
        "total_units_rejected": total_rejected,
        "good_units": good_units,
        "reject_rate_pct": round(reject_rate, 1),
        "right_first_time_pct": round(quality * 100, 1),
        "total_downtime_minutes": round(total_downtime, 1),
        "operating_time_minutes": round(operating_time, 1),
        "planned_time_minutes": round(planned_time, 1),
        "target_units": target_units,
    }


def _empty_oee() -> dict:
    return {
        "oee": 0.0, "availability": 0.0, "performance": 0.0, "quality": 0.0,
        "total_units_produced": 0, "total_units_rejected": 0, "good_units": 0,
        "reject_rate_pct": 0.0, "right_first_time_pct": 0.0,
        "total_downtime_minutes": 0.0, "operating_time_minutes": 0.0,
        "planned_time_minutes": 480.0, "target_units": 0,
    }
