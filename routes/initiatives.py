"""
initiatives.py — Iniciativas de Mejora Continua.

Rutas HTML:
    GET  /initiatives                   → Página principal (lista + Gantt)
    GET  /initiatives/new               → Formulario crear iniciativa
    GET  /initiatives/<id>/edit         → Formulario editar iniciativa

Rutas API:
    GET    /api/initiatives               → Lista de iniciativas (filtrada)
    POST   /api/initiatives               → Crear iniciativa
    GET    /api/initiatives/<id>          → Detalle de una iniciativa
    PUT    /api/initiatives/<id>          → Editar iniciativa (con audit log)
    DELETE /api/initiatives/<id>          → Borrado lógico
    GET    /api/initiatives/<id>/document → Documento completo (A3, etc.)
    GET    /api/initiatives/<id>/audit    → Historial de cambios
    GET    /api/initiatives/gantt         → Datos para Gantt simplificado
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, render_template, request

from database import get_db
from site_aggregator import SITES, DEFAULT_SITE

bp = Blueprint("initiatives", __name__)

VALID_STATUSES  = ("No iniciado", "En progreso", "Terminado", "Cancelado")
VALID_METHODS   = ("A3", "Kaizen", "DMAIC", "5Why", "other")
VALID_CATEGORIES = ("Safety", "Quality", "Delivery", "Cost", "People")

# Transiciones de estado permitidas: clave = estado actual, valor = estados destino válidos
VALID_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "No iniciado": ("En progreso", "Cancelado"),
    "En progreso": ("Terminado", "Cancelado"),
    "Terminado":   (),
    "Cancelado":   (),
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _get_initiatives(
    site_id: str,
    status: str | None = None,
    methodology: str | None = None,
    line: int | None = None,
    category: str | None = None,
    owner: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    db = get_db(site_id)
    where = ["i.deleted = 1"] if include_deleted else ["i.deleted = 0"]
    params: list = []
    if status:
        where.append("i.status = ?")
        params.append(status)
    if methodology:
        where.append("i.methodology = ?")
        params.append(methodology)
    if line:
        where.append("i.line_number = ?")
        params.append(line)
    if category:
        where.append("i.category = ?")
        params.append(category)
    if owner:
        where.append("i.owner LIKE ?")
        params.append(f"%{owner}%")

    order_clause = (
        "i.deleted_at DESC"
        if include_deleted else
        "CASE i.status WHEN 'En progreso' THEN 1 WHEN 'No iniciado' THEN 2 "
        "WHEN 'Cancelado' THEN 3 WHEN 'Terminado' THEN 4 END, i.start_date DESC"
    )
    sql = f"""
        SELECT i.*,
               p.problem_description AS problem_desc,
               p.status              AS problem_status,
               d.id                  AS doc_id,
               d.document_type       AS doc_type,
               d.title               AS doc_title
        FROM improvement_initiatives i
        LEFT JOIN top_problems p ON p.id = i.linked_problem_id
        LEFT JOIN initiative_documents d ON d.id = (
            SELECT id FROM initiative_documents
            WHERE initiative_id = i.id ORDER BY id LIMIT 1
        )
        WHERE {" AND ".join(where)}
        ORDER BY {order_clause}
    """
    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _get_initiative(site_id: str, initiative_id: int) -> dict | None:
    db = get_db(site_id)
    row = db.execute(
        """SELECT i.*,
                  p.problem_description AS problem_desc
           FROM improvement_initiatives i
           LEFT JOIN top_problems p ON p.id = i.linked_problem_id
           WHERE i.id = ? AND i.deleted = 0""",
        (initiative_id,),
    ).fetchone()
    return dict(row) if row else None


def _get_problems(site_id: str) -> list[dict]:
    db = get_db(site_id)
    rows = db.execute(
        "SELECT id, problem_description FROM top_problems ORDER BY id",
    ).fetchall()
    return [dict(r) for r in rows]


def _write_audit(
    db,
    initiative_id: int,
    changed_by: str,
    changes: list[tuple[str, str | None, str | None]],
) -> None:
    """Inserta una fila en initiative_audit_log por cada campo modificado."""
    ts = _now_utc()
    for field, old_val, new_val in changes:
        db.execute(
            """INSERT INTO initiative_audit_log
               (initiative_id, field_changed, old_value, new_value, changed_by, changed_at)
               VALUES (?,?,?,?,?,?)""",
            (initiative_id, field, old_val, new_val, changed_by, ts),
        )


# ── Rutas HTML ─────────────────────────────────────────────────────────────────

@bp.get("/initiatives")
def initiatives_page():
    site_id     = getattr(g, "current_site", DEFAULT_SITE)
    if site_id == "global":
        site_id = DEFAULT_SITE

    status      = request.args.get("status")     or None
    methodology = request.args.get("methodology") or None
    line        = request.args.get("line", type=int)
    category    = request.args.get("category")   or None
    owner       = request.args.get("owner")       or None
    highlight   = request.args.get("highlight", type=int)

    initiatives = _get_initiatives(site_id, status, methodology, line, category, owner)
    site_lines  = SITES.get(site_id, {}).get("lines", [1, 2, 3])

    return render_template(
        "initiatives/index.html",
        initiatives=initiatives,
        site_lines=site_lines,
        site_id=site_id,
        current_status=status,
        current_method=methodology,
        current_line=line,
        current_category=category,
        current_owner=owner,
        highlight=highlight,
        valid_statuses=VALID_STATUSES,
        valid_categories=VALID_CATEGORIES,
    )


@bp.get("/initiatives/new")
def initiative_new_page():
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    if site_id == "global":
        site_id = DEFAULT_SITE
    problems   = _get_problems(site_id)
    site_lines = SITES.get(site_id, {}).get("lines", [1, 2, 3])
    return render_template(
        "initiatives/form.html",
        initiative=None,
        audit_log=[],
        problems=problems,
        site_lines=site_lines,
        site_id=site_id,
        valid_methods=VALID_METHODS,
        valid_categories=VALID_CATEGORIES,
    )


@bp.get("/initiatives/<int:initiative_id>/edit")
def initiative_edit_page(initiative_id: int):
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    if site_id == "global":
        site_id = DEFAULT_SITE
    ini = _get_initiative(site_id, initiative_id)
    if not ini:
        return render_template("404.html"), 404

    db = get_db(site_id)
    audit_rows = db.execute(
        """SELECT * FROM initiative_audit_log
           WHERE initiative_id = ?
           ORDER BY changed_at DESC""",
        (initiative_id,),
    ).fetchall()
    audit_log  = [dict(r) for r in audit_rows]
    problems   = _get_problems(site_id)
    site_lines = SITES.get(site_id, {}).get("lines", [1, 2, 3])

    return render_template(
        "initiatives/form.html",
        initiative=ini,
        audit_log=audit_log,
        problems=problems,
        site_lines=site_lines,
        site_id=site_id,
        valid_methods=VALID_METHODS,
        valid_categories=VALID_CATEGORIES,
        valid_statuses=VALID_STATUSES,
        valid_transitions=VALID_TRANSITIONS,
    )


# ── Rutas API ──────────────────────────────────────────────────────────────────

@bp.get("/api/initiatives")
def api_initiatives():
    site_id     = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    status      = request.args.get("status")     or None
    methodology = request.args.get("methodology") or None
    line        = request.args.get("line", type=int)
    category    = request.args.get("category")   or None
    owner       = request.args.get("owner")      or None
    return jsonify(_get_initiatives(site_id, status, methodology, line, category, owner))


@bp.post("/api/initiatives")
def api_create_initiative():
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    data = request.get_json(force=True) or {}

    title       = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    methodology = data.get("methodology", "Kaizen")
    category    = data.get("category", "Quality")
    owner       = (data.get("owner") or "").strip()
    start_date  = (data.get("start_date") or "").strip()
    target_date = (data.get("target_date") or "").strip()
    benefit_exp = (data.get("expected_benefit") or "").strip() or None
    linked_id   = data.get("linked_problem_id") or None
    line_number = data.get("line_number") or None
    created_by  = (data.get("created_by") or "Operario").strip()

    if not title or not description or not owner or not start_date or not target_date:
        return jsonify({"error": "Faltan campos obligatorios"}), 400
    if methodology not in VALID_METHODS:
        return jsonify({"error": "Metodología no válida"}), 400
    if category not in VALID_CATEGORIES:
        return jsonify({"error": "Categoría no válida"}), 400

    db = get_db(site_id)
    cur = db.execute(
        """INSERT INTO improvement_initiatives
           (site_id, line_number, title, description, methodology,
            status, category, owner, start_date, target_date,
            expected_benefit, linked_problem_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            site_id, line_number, title, description, methodology,
            "No iniciado", category, owner, start_date, target_date,
            benefit_exp, linked_id,
        ),
    )
    new_id = cur.lastrowid
    _write_audit(db, new_id, created_by, [
        ("status", None, "No iniciado"),
        ("title",  None, title),
    ])
    db.commit()
    return jsonify({"id": new_id, "status": "No iniciado"}), 201


@bp.get("/api/initiatives/<int:initiative_id>")
def api_get_initiative(initiative_id: int):
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    ini = _get_initiative(site_id, initiative_id)
    if not ini:
        return jsonify({"error": "Iniciativa no encontrada"}), 404
    return jsonify(ini)


@bp.put("/api/initiatives/<int:initiative_id>")
def api_update_initiative(initiative_id: int):
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    db  = get_db(site_id)
    old = db.execute(
        "SELECT * FROM improvement_initiatives WHERE id = ? AND deleted = 0",
        (initiative_id,),
    ).fetchone()
    if not old:
        return jsonify({"error": "Iniciativa no encontrada"}), 404

    old = dict(old)
    data       = request.get_json(force=True) or {}
    changed_by = (data.get("changed_by") or "Operario").strip()

    EDITABLE_FIELDS = {
        "title": str,
        "description": str,
        "methodology": str,
        "status": str,
        "category": str,
        "owner": str,
        "start_date": str,
        "target_date": str,
        "completion_date": str,
        "expected_benefit": str,
        "actual_benefit": str,
        "linked_problem_id": lambda v: int(v) if v else None,
        "line_number": lambda v: int(v) if v else None,
    }

    updates: dict = {}
    audit_changes: list[tuple] = []

    for field, cast in EDITABLE_FIELDS.items():
        if field not in data:
            continue
        raw_new = data[field]
        try:
            new_val = cast(raw_new) if raw_new not in (None, "") else None
        except (ValueError, TypeError):
            new_val = None

        if field == "status" and new_val not in VALID_STATUSES:
            return jsonify({"error": f"Estado no válido: {new_val}"}), 400
        if field == "status" and new_val is not None:
            current_status = old.get("status")
            allowed = VALID_TRANSITIONS.get(current_status, ())
            if new_val != current_status and new_val not in allowed:
                return jsonify({
                    "error": f"Transición no permitida: '{current_status}' → '{new_val}'. "
                             f"Transiciones válidas: {list(allowed) or 'ninguna (estado final)'}",
                }), 400
        if field == "methodology" and new_val and new_val not in VALID_METHODS:
            return jsonify({"error": f"Metodología no válida: {new_val}"}), 400
        if field == "category" and new_val and new_val not in VALID_CATEGORIES:
            return jsonify({"error": f"Categoría no válida: {new_val}"}), 400

        old_val = old.get(field)
        str_old = str(old_val) if old_val is not None else None
        str_new = str(new_val) if new_val is not None else None
        if str_old != str_new:
            updates[field] = new_val
            audit_changes.append((field, str_old, str_new))

    # Si hay cambio de estado, exigir comentario
    status_changed = any(f == "status" for f, _, _ in audit_changes)
    if status_changed:
        status_comment = (data.get("status_comment") or "").strip()
        if not status_comment:
            return jsonify({"error": "El cambio de estado requiere un comentario obligatorio"}), 400
        audit_changes.append(("status_comment", None, status_comment))

    if not updates:
        return jsonify({"message": "Sin cambios"}), 200

    set_clause = ", ".join(f"{f} = ?" for f in updates)
    values     = list(updates.values()) + [initiative_id]
    db.execute(
        f"UPDATE improvement_initiatives SET {set_clause} WHERE id = ?",
        values,
    )
    _write_audit(db, initiative_id, changed_by, audit_changes)
    db.commit()
    return jsonify({"message": "Actualizado", "changes": len(audit_changes)})


@bp.delete("/api/initiatives/<int:initiative_id>")
def api_delete_initiative(initiative_id: int):
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    db  = get_db(site_id)
    row = db.execute(
        "SELECT id, title FROM improvement_initiatives WHERE id = ? AND deleted = 0",
        (initiative_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Iniciativa no encontrada"}), 404

    data           = request.get_json(force=True) or {}
    deleted_by     = (data.get("deleted_by") or "Operario").strip()
    deletion_reason = (data.get("deletion_reason") or "").strip()
    if not deletion_reason:
        return jsonify({"error": "El motivo de eliminación es obligatorio"}), 400
    ts             = _now_utc()

    db.execute(
        """UPDATE improvement_initiatives
           SET deleted = 1, deleted_at = ?, deleted_by = ?, deletion_reason = ?
           WHERE id = ?""",
        (ts, deleted_by, deletion_reason, initiative_id),
    )
    _write_audit(db, initiative_id, deleted_by, [
        ("deleted", "0", "1"),
        ("deletion_reason", None, deletion_reason),
    ])
    db.commit()
    return jsonify({"message": "Eliminada"})


@bp.get("/api/initiatives/<int:initiative_id>/document")
def api_initiative_document(initiative_id: int):
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    db  = get_db(site_id)
    row = db.execute(
        """SELECT d.*, i.title AS initiative_title, i.owner, i.methodology
           FROM initiative_documents d
           JOIN improvement_initiatives i ON i.id = d.initiative_id
           WHERE d.initiative_id = ?
           ORDER BY d.id LIMIT 1""",
        (initiative_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Documento no encontrado"}), 404
    return jsonify(dict(row))


@bp.get("/api/initiatives/<int:initiative_id>/audit")
def api_initiative_audit(initiative_id: int):
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    db   = get_db(site_id)
    rows = db.execute(
        """SELECT * FROM initiative_audit_log
           WHERE initiative_id = ?
           ORDER BY changed_at DESC""",
        (initiative_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.get("/api/initiatives/gantt")
def api_gantt():
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    db   = get_db(site_id)
    rows = db.execute(
        """SELECT id, title, methodology, status, category,
                  start_date, target_date, completion_date, owner
           FROM improvement_initiatives
           WHERE deleted = 0
           ORDER BY start_date""",
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.get("/api/initiatives/stats")
def api_initiatives_stats():
    """Devuelve conteos por estado y mes (start_date) para el gráfico de evolución."""
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    db   = get_db(site_id)
    rows = db.execute(
        """SELECT
               substr(start_date, 1, 7)  AS month,
               status,
               COUNT(*)                  AS total
           FROM improvement_initiatives
           WHERE deleted = 0
           GROUP BY month, status
           ORDER BY month""",
    ).fetchall()
    # Totals by current status (for summary badges)
    totals = db.execute(
        """SELECT status, COUNT(*) AS total
           FROM improvement_initiatives
           WHERE deleted = 0
           GROUP BY status""",
    ).fetchall()
    return jsonify({
        "by_month": [dict(r) for r in rows],
        "totals":   {r["status"]: r["total"] for r in totals},
    })


# ── Archived (soft-deleted) ────────────────────────────────────────────────────

@bp.get("/initiatives/archived")
def initiatives_archived_page():
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    if site_id == "global":
        site_id = DEFAULT_SITE
    initiatives = _get_initiatives(site_id, include_deleted=True)
    return render_template(
        "initiatives/archived.html",
        initiatives=initiatives,
        site_id=site_id,
    )


@bp.get("/api/initiatives/archived")
def api_initiatives_archived():
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    return jsonify(_get_initiatives(site_id, include_deleted=True))


# ── CI Coach ───────────────────────────────────────────────────────────────────

@bp.post("/api/initiatives/coach-chat")
def initiatives_coach_chat():
    """
    Chat con el agente CI Coach, opcionalmente con contexto de una iniciativa concreta.
    Body JSON: { query, initiative_id (opcional), site_id (opcional) }
    """
    data         = request.get_json(silent=True) or {}
    query        = (data.get("query") or "").strip()
    initiative_id = data.get("initiative_id")

    if not query:
        return jsonify({"error": "query es obligatorio"}), 400

    site_id = request.args.get("site") or data.get("site_id") or getattr(g, "current_site", DEFAULT_SITE)
    if site_id == "global":
        site_id = DEFAULT_SITE
    db_path = SITES.get(site_id, SITES[DEFAULT_SITE])["db_path"]

    ui_lang = request.cookies.get("lang", "es")
    if ui_lang not in ("es", "en", "fr", "it", "ja"):
        ui_lang = "es"

    context_data: dict = {"category": "improvement", "ui_lang": ui_lang}

    # Enriquecer con datos de la iniciativa si se proporciona
    if initiative_id:
        try:
            ini = _get_initiative(site_id, int(initiative_id))
            if ini:
                lines = [
                    f"Iniciativa actual: [{ini['status']}] {ini['title']}",
                    f"Metodología: {ini['methodology']} | Categoría: {ini['category']}",
                    f"Owner: {ini['owner']}",
                    f"Fechas: {ini['start_date']} → {ini['target_date']}",
                ]
                if ini.get("expected_benefit"):
                    lines.append(f"Beneficio esperado: {ini['expected_benefit']}")
                if ini.get("actual_benefit"):
                    lines.append(f"Resultado real: {ini['actual_benefit']}")
                if ini.get("description"):
                    lines.append(f"Descripción: {(ini['description'] or '')[:300]}")
                context_data["initiative_context"] = "\n".join(lines)
        except Exception:
            pass

    try:
        from agents.registry import get_agent
        from retriever import get_context as rag_get_context

        agent = get_agent("ci_coach", site_id=site_id, db_path=db_path)
        if agent is None:
            return jsonify({"error": "Agente ci_coach no disponible"}), 503

        rag_chunks = rag_get_context(query, top_k=4, db_path=db_path)
        sources = list({c["source_file"] for c in rag_chunks}) if rag_chunks else []

        result = agent.run(
            user_message=query,
            context_data=context_data,
            rag_chunks=rag_chunks,
        )

        return jsonify({
            "text":        result.get("response", ""),
            "sources":     sources,
            "model":       result.get("model", "unknown"),
            "source":      result.get("source", "mock"),
            "agents_used": ["ci_coach"],
            "error":       result.get("error"),
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/initiatives/<int:initiative_id>/related")
def find_related_initiatives(initiative_id: int):
    """
    Busca en todos los sites iniciativas similares (misma categoría o metodología)
    que ya estén terminadas y tengan beneficio verificado.
    Devuelve: { initiative_id, initiative_title, count, related: [{site, title, ...}] }
    """
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE

    ini = _get_initiative(site_id, initiative_id)
    if not ini:
        return jsonify({"error": "Iniciativa no encontrada"}), 404

    import sqlite3 as _sqlite3

    related: list[dict] = []
    for sid, site_info in SITES.items():
        try:
            conn = _sqlite3.connect(site_info["db_path"])
            conn.row_factory = _sqlite3.Row
            rows = conn.execute(
                """SELECT title, status, methodology, category,
                          expected_benefit, actual_benefit,
                          start_date, completion_date
                   FROM improvement_initiatives
                   WHERE deleted = 0
                     AND (category = ? OR methodology = ?)
                     AND id != ?
                     AND (status = 'Terminado' OR status = 'En progreso')
                   ORDER BY
                     CASE status WHEN 'Terminado' THEN 1 ELSE 2 END,
                     completion_date DESC
                   LIMIT 4""",
                (ini["category"], ini["methodology"], initiative_id if sid == site_id else -1),
            ).fetchall()
            for r in rows:
                related.append({
                    "site":             site_info.get("name", sid),
                    "title":            r["title"],
                    "status":           r["status"],
                    "methodology":      r["methodology"],
                    "category":         r["category"],
                    "expected_benefit": r["expected_benefit"],
                    "actual_benefit":   r["actual_benefit"],
                    "start_date":       r["start_date"],
                    "completion_date":  r["completion_date"],
                })
            conn.close()
        except Exception:
            pass

    return jsonify({
        "initiative_id":    initiative_id,
        "initiative_title": ini["title"],
        "count":            len(related),
        "related":          related,
    })
