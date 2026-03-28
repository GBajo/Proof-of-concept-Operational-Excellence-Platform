from typing import Optional
from database import get_db


def create_shift(operator_id: int, line_number: int, shift_type: str) -> int:
    db = get_db()
    cursor = db.execute(
        """INSERT INTO shifts (operator_id, line_number, shift_type)
           VALUES (?, ?, ?)""",
        (operator_id, line_number, shift_type),
    )
    db.commit()
    return cursor.lastrowid


def get_shift_by_id(shift_id: int) -> Optional[dict]:
    db = get_db()
    row = db.execute(
        """SELECT s.*, o.name AS operator_name, o.badge_number
           FROM shifts s
           JOIN operators o ON o.id = s.operator_id
           WHERE s.id = ?""",
        (shift_id,),
    ).fetchone()
    return dict(row) if row else None


def get_active_shift_by_line(line_number: int) -> Optional[dict]:
    db = get_db()
    row = db.execute(
        """SELECT s.*, o.name AS operator_name
           FROM shifts s
           JOIN operators o ON o.id = s.operator_id
           WHERE s.line_number = ? AND s.status = 'active'""",
        (line_number,),
    ).fetchone()
    return dict(row) if row else None


def get_shifts(status: Optional[str] = None, line: Optional[int] = None) -> list[dict]:
    db = get_db()
    query = """SELECT s.id, s.line_number, s.shift_type, s.start_time, s.end_time,
                      s.status, o.name AS operator_name
               FROM shifts s
               JOIN operators o ON o.id = s.operator_id
               WHERE 1=1"""
    params: list = []
    if status:
        query += " AND s.status = ?"
        params.append(status)
    if line is not None:
        query += " AND s.line_number = ?"
        params.append(line)
    query += " ORDER BY s.start_time DESC"
    return [dict(r) for r in db.execute(query, params).fetchall()]


def end_shift(shift_id: int, handover_notes: Optional[str] = None,
              status: str = "completed") -> bool:
    db = get_db()
    cursor = db.execute(
        """UPDATE shifts
           SET end_time = datetime('now'), status = ?, handover_notes = ?
           WHERE id = ? AND status = 'active'""",
        (status, handover_notes, shift_id),
    )
    db.commit()
    return cursor.rowcount > 0


def update_shift(shift_id: int, fields: dict) -> bool:
    allowed = {"handover_notes", "status", "end_time"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [shift_id]
    db = get_db()
    db.execute(f"UPDATE shifts SET {set_clause} WHERE id = ?", params)
    db.commit()
    return True


def get_active_lines() -> list[dict]:
    db = get_db()
    rows = db.execute(
        """SELECT s.line_number, o.name AS operator_name, s.start_time, s.id AS shift_id
           FROM shifts s
           JOIN operators o ON o.id = s.operator_id
           WHERE s.status = 'active'
           ORDER BY s.line_number"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_shifts_history(
    line: Optional[int] = None,
    operator: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Turnos completados o interrumpidos con su última lectura KPI."""
    db = get_db()
    query = """
        SELECT s.id, s.line_number, s.shift_type, s.start_time, s.end_time,
               s.status, s.handover_notes,
               o.name AS operator_name,
               k.units_produced  AS last_units_produced,
               k.units_rejected  AS last_units_rejected,
               k.downtime_minutes AS last_downtime,
               k.target_units    AS last_target
        FROM shifts s
        JOIN operators o ON o.id = s.operator_id
        LEFT JOIN kpi_readings k ON k.id = (
            SELECT id FROM kpi_readings
            WHERE shift_id = s.id
            ORDER BY timestamp DESC LIMIT 1
        )
        WHERE s.status IN ('completed', 'interrupted')
    """
    params: list = []
    if line:
        query += " AND s.line_number = ?"
        params.append(line)
    if operator:
        query += " AND o.name LIKE ?"
        params.append(f"%{operator}%")
    if date_from:
        query += " AND date(s.start_time) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date(s.start_time) <= ?"
        params.append(date_to)
    if status:
        query += " AND s.status = ?"
        params.append(status)
    query += " ORDER BY s.start_time DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in db.execute(query, params).fetchall()]


def get_line_performance_summary(days: int = 7) -> list[dict]:
    """KPIs agregados por línea de los últimos N días."""
    db = get_db()
    rows = db.execute(
        """
        SELECT s.line_number,
               COUNT(DISTINCT s.id)     AS shift_count,
               SUM(k.units_produced)    AS total_units,
               SUM(k.units_rejected)    AS total_rejected,
               SUM(k.downtime_minutes)  AS total_downtime,
               MAX(k.target_units)      AS target_units
        FROM shifts s
        JOIN kpi_readings k ON k.shift_id = s.id
        WHERE s.start_time >= datetime('now', ? || ' days')
          AND s.status IN ('completed', 'interrupted', 'active')
        GROUP BY s.line_number
        ORDER BY s.line_number
        """,
        (f"-{days}",),
    ).fetchall()
    return [dict(r) for r in rows]
