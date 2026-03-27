"""
problems.py — Top Problemas por línea y por site.

Rutas HTML:
    GET /problems                → Página principal de problemas

Rutas API:
    GET /api/problems            → Lista de problemas (filtrada por site/period)
    GET /api/problems/pareto     → Datos para gráfico Pareto
    GET /api/problems/top-site   → TOP 3 a nivel site (agregado)
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, render_template, request

from database import get_db
from site_aggregator import SITES, DEFAULT_SITE

bp = Blueprint("problems", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _period_days(period: str) -> int:
    return {"week": 7, "month": 30, "quarter": 90}.get(period, 30)


def _get_problems(site_id: str, period: str = "month", line: int | None = None) -> list[dict]:
    days = _period_days(period)
    db = get_db(site_id)
    where = ["date(last_occurrence) >= date('now', ? || ' days')"]
    params: list = [f"-{days}"]
    if line:
        where.append("line_number = ?")
        params.append(line)
    sql = f"""
        SELECT p.*, i.id AS initiative_id, i.title AS initiative_title,
               i.status AS initiative_status
        FROM top_problems p
        LEFT JOIN improvement_initiatives i ON i.linked_problem_id = p.id
           AND i.id = (SELECT id FROM improvement_initiatives
                       WHERE linked_problem_id = p.id
                       ORDER BY id DESC LIMIT 1)
        WHERE {" AND ".join(where)}
        ORDER BY p.impact_score DESC, p.frequency DESC
    """
    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _top3_per_line(problems: list[dict]) -> dict[int, list[dict]]:
    """Agrupa por línea y devuelve los top 3 de cada línea."""
    by_line: dict[int, list[dict]] = {}
    for p in problems:
        line = p.get("line_number") or 0
        by_line.setdefault(line, [])
        if len(by_line[line]) < 3:
            by_line[line].append(p)
    return by_line


def _top3_site(problems: list[dict]) -> list[dict]:
    """Top 3 problemas del site (mayor impact × frequency)."""
    scored = sorted(
        problems,
        key=lambda p: p["impact_score"] * p["frequency"],
        reverse=True,
    )
    return scored[:3]


# ── Rutas HTML ─────────────────────────────────────────────────────────────────

@bp.get("/problems")
def problems_page():
    from site_aggregator import SITES, DEFAULT_SITE
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    if site_id == "global":
        site_id = DEFAULT_SITE

    period  = request.args.get("period", "month")
    line    = request.args.get("line", type=int)

    problems = _get_problems(site_id, period, line)
    by_line  = _top3_per_line(problems)
    top_site = _top3_site(problems)

    # Lines available for this site
    site_lines = SITES.get(site_id, {}).get("lines", [1, 2, 3])

    return render_template(
        "problems/index.html",
        problems=problems,
        by_line=by_line,
        top_site=top_site,
        site_lines=site_lines,
        current_period=period,
        current_line=line,
        site_id=site_id,
    )


# ── Rutas API ──────────────────────────────────────────────────────────────────

@bp.get("/api/problems")
def api_problems():
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    period  = request.args.get("period", "month")
    line    = request.args.get("line", type=int)
    return jsonify(_get_problems(site_id, period, line))


@bp.get("/api/problems/pareto")
def api_pareto():
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    period  = request.args.get("period", "month")

    db   = get_db(site_id)
    days = _period_days(period)
    rows = db.execute(
        """SELECT problem_description, frequency, category
           FROM top_problems
           WHERE date(last_occurrence) >= date('now', ? || ' days')
           ORDER BY frequency DESC""",
        (f"-{days}",),
    ).fetchall()

    if not rows:
        return jsonify({"names": [], "values": [], "cumulative": []})

    names  = [r["problem_description"][:40] + ("…" if len(r["problem_description"]) > 40 else "") for r in rows]
    values = [r["frequency"] for r in rows]
    total  = sum(values) or 1
    cumul  = []
    acc    = 0.0
    for v in values:
        acc += v / total * 100
        cumul.append(round(acc, 1))

    return jsonify({"names": names, "values": values, "cumulative": cumul})


@bp.get("/api/problems/top-site")
def api_top_site():
    site_id = request.args.get("site", getattr(g, "current_site", DEFAULT_SITE))
    if site_id == "global":
        site_id = DEFAULT_SITE
    period   = request.args.get("period", "month")
    problems = _get_problems(site_id, period)
    return jsonify(_top3_site(problems))
