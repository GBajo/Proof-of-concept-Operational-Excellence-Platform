"""models/tier.py — Funciones CRUD y consultas para el sistema de Tiers jerárquico."""
from __future__ import annotations

from typing import Optional

from database import get_db


# ── Consultas ─────────────────────────────────────────────────────────────────

def get_tiers(site_id: str) -> list[dict]:
    rows = get_db().execute(
        """SELECT t.*, COUNT(tg.id) AS group_count
           FROM tiers t
           LEFT JOIN tier_groups tg ON tg.tier_id = t.id
           WHERE t.site_id = ?
           GROUP BY t.id
           ORDER BY t.tier_level, t.name""",
        (site_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_tier_by_id(tier_id: int) -> Optional[dict]:
    row = get_db().execute("SELECT * FROM tiers WHERE id=?", (tier_id,)).fetchone()
    return dict(row) if row else None


def get_tier_groups(site_id: str, tier_level: Optional[int] = None) -> list[dict]:
    sql = """
        SELECT tg.*, t.tier_level, t.name AS tier_name,
               (SELECT COUNT(*) FROM tier_group_members m WHERE m.group_id = tg.id) AS member_count,
               (SELECT COUNT(*) FROM tier_group_assignments a WHERE a.parent_group_id = tg.id) AS child_count
        FROM tier_groups tg
        JOIN tiers t ON t.id = tg.tier_id
        WHERE tg.site_id = ?
    """
    params: list = [site_id]
    if tier_level is not None:
        sql += " AND t.tier_level = ?"
        params.append(tier_level)
    sql += " ORDER BY t.tier_level, tg.name"
    return [dict(r) for r in get_db().execute(sql, params).fetchall()]


def get_tier_group_by_id(group_id: int) -> Optional[dict]:
    row = get_db().execute(
        """SELECT tg.*, t.tier_level, t.name AS tier_name,
                  (SELECT COUNT(*) FROM tier_group_members m WHERE m.group_id = tg.id) AS member_count,
                  (SELECT COUNT(*) FROM tier_group_assignments a WHERE a.parent_group_id = tg.id) AS child_count
           FROM tier_groups tg
           JOIN tiers t ON t.id = tg.tier_id
           WHERE tg.id = ?""",
        (group_id,),
    ).fetchone()
    return dict(row) if row else None


def get_group_children(group_id: int) -> list[dict]:
    rows = get_db().execute(
        """SELECT tg.*, t.tier_level, t.name AS tier_name,
                  (SELECT COUNT(*) FROM tier_group_members m WHERE m.group_id = tg.id) AS member_count
           FROM tier_groups tg
           JOIN tiers t ON t.id = tg.tier_id
           JOIN tier_group_assignments a ON a.child_group_id = tg.id
           WHERE a.parent_group_id = ?
           ORDER BY t.tier_level, tg.name""",
        (group_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_group_parents(group_id: int) -> list[dict]:
    rows = get_db().execute(
        """SELECT tg.*, t.tier_level, t.name AS tier_name
           FROM tier_groups tg
           JOIN tiers t ON t.id = tg.tier_id
           JOIN tier_group_assignments a ON a.parent_group_id = tg.id
           WHERE a.child_group_id = ?
           ORDER BY t.tier_level, tg.name""",
        (group_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_group_members(group_id: int) -> list[dict]:
    rows = get_db().execute(
        """SELECT m.id AS member_id, m.role, m.assigned_at,
                  o.id AS operator_id, o.name, o.badge_number, o.role AS operator_role
           FROM tier_group_members m
           JOIN operators o ON o.id = m.operator_id
           WHERE m.group_id = ?
           ORDER BY CASE m.role WHEN 'leader' THEN 0 WHEN 'member' THEN 1 ELSE 2 END, o.name""",
        (group_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_escalation_paths(site_id: str) -> list[dict]:
    rows = get_db().execute(
        """SELECT ep.*, fg.name AS from_group_name, tg2.name AS to_group_name
           FROM escalation_paths ep
           JOIN tier_groups fg ON fg.id = ep.from_group_id
           JOIN tier_groups tg2 ON tg2.id = ep.to_group_id
           WHERE ep.site_id = ?
           ORDER BY ep.escalation_type, fg.name""",
        (site_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_escalation_path(from_group_id: int, escalation_type: str) -> Optional[dict]:
    row = get_db().execute(
        """SELECT ep.*, fg.name AS from_group_name, tg2.name AS to_group_name
           FROM escalation_paths ep
           JOIN tier_groups fg ON fg.id = ep.from_group_id
           JOIN tier_groups tg2 ON tg2.id = ep.to_group_id
           WHERE ep.from_group_id = ? AND ep.escalation_type = ?""",
        (from_group_id, escalation_type),
    ).fetchone()
    return dict(row) if row else None


def get_site_hierarchy(site_id: str) -> dict:
    """Construye el árbol jerárquico completo del site."""
    db = get_db()

    all_groups_rows = db.execute(
        """SELECT tg.id, tg.name, tg.description, tg.group_type, tg.created_at,
                  t.tier_level, t.id AS tier_id, t.name AS tier_name,
                  (SELECT COUNT(*) FROM tier_group_members m WHERE m.group_id = tg.id) AS member_count
           FROM tier_groups tg
           JOIN tiers t ON t.id = tg.tier_id
           WHERE tg.site_id = ?
           ORDER BY t.tier_level, tg.name""",
        (site_id,),
    ).fetchall()
    all_groups: dict[int, dict] = {r["id"]: dict(r) for r in all_groups_rows}
    for g in all_groups.values():
        g["children"]    = []
        g["child_count"] = 0

    assignments = db.execute(
        """SELECT a.parent_group_id, a.child_group_id
           FROM tier_group_assignments a
           JOIN tier_groups tg ON tg.id = a.parent_group_id
           WHERE tg.site_id = ?""",
        (site_id,),
    ).fetchall()

    has_parent: set[int] = set()
    for a in assignments:
        p, c = a["parent_group_id"], a["child_group_id"]
        if p in all_groups and c in all_groups:
            all_groups[p]["children"].append(all_groups[c])
            all_groups[p]["child_count"] = len(all_groups[p]["children"])
            has_parent.add(c)

    return {
        "tier2_groups":    [g for g in all_groups.values() if g["tier_level"] == 2 and g["id"] not in has_parent],
        "ungrouped_tier1": [g for g in all_groups.values() if g["tier_level"] == 1 and g["id"] not in has_parent],
        "ungrouped_tier0": [g for g in all_groups.values() if g["tier_level"] == 0 and g["id"] not in has_parent],
    }


# ── Tiers CRUD ────────────────────────────────────────────────────────────────

def create_tier(site_id: str, tier_level: int, name: str, description: str = "") -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO tiers (site_id, tier_level, name, description) VALUES (?,?,?,?)",
        (site_id, tier_level, name, description),
    )
    db.commit()
    return cur.lastrowid


def update_tier(tier_id: int, name: str, description: str = "") -> bool:
    db = get_db()
    db.execute("UPDATE tiers SET name=?, description=? WHERE id=?", (name, description, tier_id))
    db.commit()
    return True


def delete_tier(tier_id: int) -> bool:
    db = get_db()
    db.execute("DELETE FROM tiers WHERE id=?", (tier_id,))
    db.commit()
    return True


# ── Grupos CRUD ───────────────────────────────────────────────────────────────

def create_tier_group(site_id: str, tier_id: int, name: str,
                      description: str = "", group_type: str = "") -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO tier_groups (site_id, tier_id, name, description, group_type) VALUES (?,?,?,?,?)",
        (site_id, tier_id, name, description, group_type),
    )
    db.commit()
    return cur.lastrowid


def update_tier_group(group_id: int, name: str,
                      description: str = "", group_type: str = "") -> bool:
    db = get_db()
    db.execute(
        "UPDATE tier_groups SET name=?, description=?, group_type=? WHERE id=?",
        (name, description, group_type, group_id),
    )
    db.commit()
    return True


def delete_tier_group(group_id: int) -> tuple[bool, str]:
    """Elimina un grupo. Falla si tiene asignaciones activas."""
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) FROM tier_group_assignments WHERE parent_group_id=? OR child_group_id=?",
        (group_id, group_id),
    ).fetchone()[0]
    if count:
        return False, "El grupo tiene asignaciones activas. Desasígnalo primero."
    db.execute("DELETE FROM tier_groups WHERE id=?", (group_id,))
    db.commit()
    return True, "Grupo eliminado."


# ── Asignaciones ──────────────────────────────────────────────────────────────

def assign_group(parent_group_id: int, child_group_id: int) -> tuple[bool, str]:
    """Asigna un grupo hijo a un grupo padre. Valida que sean de tiers distintos."""
    parent = get_tier_group_by_id(parent_group_id)
    child  = get_tier_group_by_id(child_group_id)
    if not parent or not child:
        return False, "Grupo no encontrado."
    if parent["tier_level"] <= child["tier_level"]:
        return False, "El grupo padre debe ser de nivel superior al grupo hijo."
    try:
        db = get_db()
        db.execute(
            "INSERT INTO tier_group_assignments (parent_group_id, child_group_id) VALUES (?,?)",
            (parent_group_id, child_group_id),
        )
        db.commit()
        return True, "Asignación creada."
    except Exception:
        return False, "La asignación ya existe o no es válida."


def unassign_group(parent_group_id: int, child_group_id: int) -> bool:
    db = get_db()
    db.execute(
        "DELETE FROM tier_group_assignments WHERE parent_group_id=? AND child_group_id=?",
        (parent_group_id, child_group_id),
    )
    db.commit()
    return True


# ── Miembros ──────────────────────────────────────────────────────────────────

def assign_member(group_id: int, operator_id: int, role: str = "member") -> tuple[bool, str]:
    try:
        db = get_db()
        db.execute(
            "INSERT INTO tier_group_members (group_id, operator_id, role) VALUES (?,?,?)",
            (group_id, operator_id, role),
        )
        db.commit()
        return True, "Miembro asignado."
    except Exception:
        return False, "El operador ya es miembro de este grupo."


def unassign_member(group_id: int, operator_id: int) -> bool:
    db = get_db()
    db.execute(
        "DELETE FROM tier_group_members WHERE group_id=? AND operator_id=?",
        (group_id, operator_id),
    )
    db.commit()
    return True


# ── Escalado ──────────────────────────────────────────────────────────────────

def create_escalation_path(site_id: str, from_group_id: int, to_group_id: int,
                           escalation_type: str,
                           auto_escalate_after_minutes: Optional[int],
                           notification_channel: str) -> int:
    db = get_db()
    cur = db.execute(
        """INSERT INTO escalation_paths
           (site_id, from_group_id, to_group_id, escalation_type,
            auto_escalate_after_minutes, notification_channel)
           VALUES (?,?,?,?,?,?)""",
        (site_id, from_group_id, to_group_id, escalation_type,
         auto_escalate_after_minutes, notification_channel),
    )
    db.commit()
    return cur.lastrowid


def delete_escalation_path(path_id: int) -> bool:
    db = get_db()
    db.execute("DELETE FROM escalation_paths WHERE id=?", (path_id,))
    db.commit()
    return True
