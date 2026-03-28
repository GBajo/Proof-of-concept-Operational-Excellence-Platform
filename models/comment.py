from typing import Optional
from database import get_db


def create_comment(shift_id: int, operator_id: int, text: str,
                   category: str, source: str = "voice") -> dict:
    db = get_db()
    cursor = db.execute(
        """INSERT INTO comments (shift_id, operator_id, text, category, source)
           VALUES (?, ?, ?, ?, ?)""",
        (shift_id, operator_id, text, category, source),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM comments WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def get_comments_by_shift(shift_id: int,
                          category: Optional[str] = None) -> list[dict]:
    db = get_db()
    query = """SELECT c.*, o.name AS operator_name
               FROM comments c
               JOIN operators o ON o.id = c.operator_id
               WHERE c.shift_id = ?"""
    params: list = [shift_id]
    if category:
        query += " AND c.category = ?"
        params.append(category)
    query += " ORDER BY c.timestamp ASC"
    return [dict(r) for r in db.execute(query, params).fetchall()]


def delete_comment(comment_id: int) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    db.commit()
    return cursor.rowcount > 0
