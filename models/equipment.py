"""models/equipment.py — CRUD y consultas para el modelo de equipos por grupo."""
from __future__ import annotations

from typing import Optional

from database import get_db

VALID_STATUSES = ("running", "stopped", "changeover", "maintenance", "idle")
VALID_TYPES = (
    "thermoformer", "filler", "weigher", "labeler", "serializer",
    "cartoner", "case_packer", "palletizer", "inspection", "other",
)


def get_equipment_by_group(group_id: int) -> list[dict]:
    rows = get_db().execute(
        """SELECT * FROM equipment WHERE group_id = ?
           ORDER BY equipment_type, name""",
        (group_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_equipment_by_id(equipment_id: int) -> Optional[dict]:
    row = get_db().execute(
        "SELECT * FROM equipment WHERE id = ?", (equipment_id,)
    ).fetchone()
    return dict(row) if row else None


def create_equipment(
    site_id: str,
    group_id: int,
    name: str,
    equipment_type: str = "other",
    model: Optional[str] = None,
    manufacturer: Optional[str] = None,
    serial_number: Optional[str] = None,
    status: str = "running",
    nominal_speed: Optional[float] = None,
    installed_date: Optional[str] = None,
    last_maintenance: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    db = get_db()
    cur = db.execute(
        """INSERT INTO equipment
           (site_id, group_id, name, equipment_type, model, manufacturer,
            serial_number, status, nominal_speed, installed_date,
            last_maintenance, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (site_id, group_id, name, equipment_type, model, manufacturer,
         serial_number, status, nominal_speed, installed_date,
         last_maintenance, notes),
    )
    db.commit()
    return cur.lastrowid


def update_equipment(
    equipment_id: int,
    name: str,
    equipment_type: str = "other",
    model: Optional[str] = None,
    manufacturer: Optional[str] = None,
    serial_number: Optional[str] = None,
    status: str = "running",
    nominal_speed: Optional[float] = None,
    installed_date: Optional[str] = None,
    last_maintenance: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    db = get_db()
    db.execute(
        """UPDATE equipment SET
           name=?, equipment_type=?, model=?, manufacturer=?,
           serial_number=?, status=?, nominal_speed=?,
           installed_date=?, last_maintenance=?, notes=?
           WHERE id=?""",
        (name, equipment_type, model, manufacturer, serial_number, status,
         nominal_speed, installed_date, last_maintenance, notes, equipment_id),
    )
    db.commit()
    return True


def delete_equipment(equipment_id: int) -> bool:
    db = get_db()
    db.execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))
    db.commit()
    return True


def update_equipment_status(equipment_id: int, status: str) -> bool:
    if status not in VALID_STATUSES:
        return False
    db = get_db()
    db.execute("UPDATE equipment SET status = ? WHERE id = ?", (status, equipment_id))
    db.commit()
    return True


def get_equipment_status_summary(group_id: int) -> dict:
    """Cuenta equipos por estado para un grupo."""
    rows = get_db().execute(
        """SELECT status, COUNT(*) AS cnt
           FROM equipment WHERE group_id = ?
           GROUP BY status""",
        (group_id,),
    ).fetchall()
    summary = {s: 0 for s in VALID_STATUSES}
    total = 0
    for r in rows:
        summary[r["status"]] = r["cnt"]
        total += r["cnt"]
    summary["total"] = total
    return summary


def get_all_equipment_for_site(site_id: str) -> list[dict]:
    """Devuelve todos los equipos del site con nombre y tier_level del grupo."""
    rows = get_db().execute(
        """SELECT e.*,
                  tg.name  AS group_name,
                  t.tier_level
           FROM equipment e
           JOIN tier_groups tg ON tg.id = e.group_id
           JOIN tiers t        ON t.id  = tg.tier_id
           WHERE e.site_id = ?
           ORDER BY tg.name, e.equipment_type, e.name""",
        (site_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def bulk_update_status(equipment_ids: list[int], status: str, site_id: str) -> int:
    """Actualiza el estado de múltiples equipos. Retorna el nº de filas actualizadas."""
    if status not in VALID_STATUSES or not equipment_ids:
        return 0
    db = get_db()
    placeholders = ",".join("?" * len(equipment_ids))
    cur = db.execute(
        f"UPDATE equipment SET status=? WHERE id IN ({placeholders}) AND site_id=?",
        [status, *equipment_ids, site_id],
    )
    db.commit()
    return cur.rowcount
