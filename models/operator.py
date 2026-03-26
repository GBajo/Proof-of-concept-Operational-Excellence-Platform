from typing import Optional
from database import get_db


def get_all_operators() -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT id, name, role, badge_number FROM operators ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def get_operator_by_id(operator_id: int) -> Optional[dict]:
    db = get_db()
    row = db.execute(
        "SELECT id, name, role, badge_number FROM operators WHERE id = ?",
        (operator_id,),
    ).fetchone()
    return dict(row) if row else None
