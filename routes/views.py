from flask import Blueprint, render_template, abort, redirect, url_for, request, make_response, g
from models.shift import get_shift_by_id, get_active_lines, get_shifts_history, get_line_performance_summary
from models.operator import get_all_operators
from models.comment import get_comments_by_shift
from models.kpi import calculate_oee
from site_aggregator import SITES, DEFAULT_SITE
import json

bp = Blueprint("views", __name__)


@bp.post("/set-lang")
def set_lang():
    """Guarda el idioma preferido en una cookie y redirige al referer."""
    lang = request.form.get("lang", "es")
    if lang not in ("es", "en"):
        lang = "es"
    redirect_to = request.form.get("next") or request.referrer or "/"
    resp = make_response(redirect(redirect_to))
    resp.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


@bp.post("/set-site")
def set_site():
    """Guarda la planta activa en una cookie y redirige."""
    from site_aggregator import SITES, DEFAULT_SITE
    site = request.form.get("site", DEFAULT_SITE)
    if site not in SITES and site != "global":
        site = DEFAULT_SITE
    redirect_to = request.form.get("next") or request.referrer or "/"
    if site == "global":
        redirect_to = "/global"
    resp = make_response(redirect(redirect_to))
    resp.set_cookie("site", site, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


@bp.get("/global")
def global_view():
    """Vista global: comparativa y ranking de todas las plantas."""
    from site_aggregator import get_site_rankings, get_cross_site_comparison, get_global_summary
    days       = int(request.args.get("days", 7))
    rankings   = get_site_rankings("oee", days)
    summary    = get_global_summary(days)
    comparison = get_cross_site_comparison("oee", days)
    return render_template(
        "global/index.html",
        rankings=rankings,
        summary=summary,
        comparison=comparison,
        days=days,
    )


@bp.get("/")
def index():
    active_lines = get_active_lines()
    return render_template("index.html", active_lines=active_lines)


@bp.get("/shift/start")
def shift_start():
    operators = get_all_operators()
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    site_lines = SITES.get(site_id, SITES[DEFAULT_SITE])["lines"]
    return render_template("shift/start.html", operators=operators, site_lines=site_lines)


@bp.get("/shift/<int:shift_id>/active")
def shift_active(shift_id: int):
    shift = get_shift_by_id(shift_id)
    if not shift:
        abort(404)
    return render_template("shift/active.html", shift=shift)


@bp.get("/shift/<int:shift_id>/end")
def shift_end(shift_id: int):
    shift = get_shift_by_id(shift_id)
    if not shift:
        abort(404)
    # Si el turno ya está cerrado, redirigir directamente al resumen
    if shift["status"] != "active":
        return redirect(url_for("views.shift_summary_view", shift_id=shift_id))

    comments = get_comments_by_shift(shift_id)
    kpi = calculate_oee(shift_id)

    # Duración del turno (UTC naive, consistente con datetime('now') de SQLite)
    from datetime import datetime, timezone
    start_dt = datetime.fromisoformat(shift["start_time"])
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    duration_min = int((now_utc - start_dt).total_seconds() / 60)
    duration_h = duration_min // 60
    duration_m = duration_min % 60

    # Comentarios por categoría
    by_category: dict = {}
    for c in comments:
        by_category.setdefault(c["category"], []).append(c)

    return render_template(
        "shift/end.html",
        shift=shift,
        kpi=kpi,
        total_comments=len(comments),
        by_category=by_category,
        duration_h=duration_h,
        duration_m=duration_m,
    )


@bp.get("/shift/<int:shift_id>/summary")
def shift_summary_view(shift_id: int):
    shift = get_shift_by_id(shift_id)
    if not shift:
        abort(404)
    comments = get_comments_by_shift(shift_id)
    kpi = calculate_oee(shift_id)
    by_category: dict = {}
    for c in comments:
        by_category.setdefault(c["category"], []).append(c)

    from datetime import datetime, timezone
    start_dt = datetime.fromisoformat(shift["start_time"])
    if shift["end_time"]:
        end_dt = datetime.fromisoformat(shift["end_time"])
    else:
        end_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    duration_min = int((end_dt - start_dt).total_seconds() / 60)
    duration_h = duration_min // 60
    duration_m = duration_min % 60
    generation_date = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Sugerencias del asistente del turno
    from database import get_db
    db = get_db()
    sugg_rows = db.execute(
        """SELECT id, comment_id, query_text, context_sources,
                  response_text, model_used, source, feedback, created_at
           FROM assistant_suggestions WHERE shift_id = ?
           ORDER BY created_at ASC""",
        (shift_id,),
    ).fetchall()
    suggestions = []
    for r in sugg_rows:
        s = dict(r)
        try:
            s["context_sources"] = json.loads(s["context_sources"] or "[]")
        except Exception:
            s["context_sources"] = []
        suggestions.append(s)

    return render_template(
        "shift/summary.html",
        shift=shift,
        kpi=kpi,
        comments=comments,
        by_category=by_category,
        duration_h=duration_h,
        duration_m=duration_m,
        generation_date=generation_date,
        suggestions=suggestions,
    )


@bp.get("/dashboard")
def dashboard():
    active_lines = get_active_lines()
    line_perf = get_line_performance_summary(days=7)
    recent_shifts = get_shifts_history(limit=10)
    return render_template(
        "dashboard/kpi.html",
        active_lines=active_lines,
        line_perf=line_perf,
        recent_shifts=recent_shifts,
    )


@bp.get("/shifts")
def shifts_history():
    from datetime import datetime
    line      = request.args.get("line",     type=int)
    operator  = request.args.get("operator", type=str, default="").strip()
    date_from = request.args.get("from",     type=str, default="").strip()
    date_to   = request.args.get("to",       type=str, default="").strip()
    status    = request.args.get("status",   type=str, default="").strip()

    shifts = get_shifts_history(
        line      = line or None,
        operator  = operator or None,
        date_from = date_from or None,
        date_to   = date_to or None,
        status    = status or None,
        limit     = 100,
    )

    # Calcular duración de cada turno
    for s in shifts:
        if s.get("end_time") and s.get("start_time"):
            try:
                mins = int((datetime.fromisoformat(s["end_time"]) -
                            datetime.fromisoformat(s["start_time"])).total_seconds() / 60)
                s["duration_h"] = mins // 60
                s["duration_m"] = mins % 60
            except Exception:
                s["duration_h"] = s["duration_m"] = None
        else:
            s["duration_h"] = s["duration_m"] = None

    operators = get_all_operators()
    return render_template(
        "shifts/history.html",
        shifts    = shifts,
        operators = operators,
        filters   = {
            "line": line, "operator": operator,
            "from": date_from, "to": date_to, "status": status,
        },
    )
