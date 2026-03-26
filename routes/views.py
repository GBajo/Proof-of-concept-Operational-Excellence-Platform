from flask import Blueprint, render_template, abort, redirect, url_for
from models.shift import get_shift_by_id, get_active_lines
from models.operator import get_all_operators
from models.comment import get_comments_by_shift
from models.kpi import calculate_oee

bp = Blueprint("views", __name__)


@bp.get("/")
def index():
    active_lines = get_active_lines()
    return render_template("index.html", active_lines=active_lines)


@bp.get("/shift/start")
def shift_start():
    operators = get_all_operators()
    return render_template("shift/start.html", operators=operators)


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
    return render_template(
        "shift/summary.html",
        shift=shift,
        kpi=kpi,
        comments=comments,
        by_category=by_category,
    )


@bp.get("/dashboard")
def dashboard():
    active_lines = get_active_lines()
    return render_template("dashboard/kpi.html", active_lines=active_lines)
