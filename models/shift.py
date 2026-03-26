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
    db.execute(
        """UPDATE shifts
           SET end_time = datetime('now'), status = ?, handover_notes = ?
           WHERE id = ? AND status = 'active'""",
        (status, handover_notes, shift_id),
    )
    db.commit()
    return db.execute(
        "SELECT changes()"
    ).fetchone()[0] > 0


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
