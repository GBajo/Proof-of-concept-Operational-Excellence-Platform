"""
initiatives.py — Iniciativas de Mejora Continua.

Rutas HTML:
    GET /initiatives                   → Página principal de iniciativas

Rutas API:
    GET /api/initiatives               → Lista de iniciativas (filtrada)
    GET /api/initiatives/<id>/document → Documento completo (A3, etc.)
    GET /api/initiatives/gantt         → Datos para Gantt simplificado
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, render_template, request

from database import get_db
from site_aggregator import SITES, DEFAULT_SITE

bp = Blueprint("initiatives", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_initiatives(
    site_id: str,
    status: str | None = None,
    methodology: str | None = None,
    line: int | None = None,
) -> list[dict]:
    db = get_db(site_id)
    where = ["1=1"]
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
        ORDER BY
          CASE i.status
            WHEN 'in_progress' THEN 1
            WHEN 'planned'     THEN 2
            WHEN 'on_hold'     THEN 3
            WHEN 'completed'   THEN 4
          END,
          i.start_date DESC
    """
    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ── Rutas HTML ─────────────────────────────────────────────────────────────────

@bp.get("/initiatives")
def initiatives_page():
    site_id     = getattr(g, "current_site", DEFAULT_SITE)
    if site_id == "global":
        site_id = DEFAULT_SITE

    status      = request.args.get("status")     or None
    methodology = request.args.get("methodology") or None
    line        = request.args.get("line", type=int)
    highlight   = request.args.get("highlight", type=int)

    initiatives = _get_initiatives(site_id, status, methodology, line)
    site_lines  = SITES.get(site_id, {}).get("lines", [1, 2, 3])

    return render_template(
        "initiatives/index.html",
        initiatives=initiatives,
        site_lines=site_lines,
        site_id=site_id,
        current_status=status,
        current_method=methodology,
        current_line=line,
        highlight=highlight,
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
    return jsonify(_get_initiatives(site_id, status, methodology, line))


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
        return jsonify({"error": "Document not found"}), 404
    return jsonify(dict(row))


@bp.get("/api/initiatives/gantt")
def api_gantt():
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    db   = get_db(site_id)
    rows = db.execute(
        """SELECT id, title, methodology, status, start_date, target_date,
                  completion_date, owner
           FROM improvement_initiatives
           ORDER BY start_date""",
    ).fetchall()
    return jsonify([dict(r) for r in rows])
