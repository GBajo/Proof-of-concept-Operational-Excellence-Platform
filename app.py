from flask import Flask, request as flask_request, g
from config import config
from database import close_db, init_db
from translations import get_text


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_PATH"] = config.DATABASE_PATH
    app.config["DEBUG"] = config.DEBUG
    app.config["SECRET_KEY"] = config.SECRET_KEY

    # Inicializar bases de datos (todas las plantas)
    init_db(app)

    # Cerrar conexiones al finalizar cada solicitud
    app.teardown_appcontext(close_db)

    # Registrar blueprints API (primero)
    from routes.operators import bp as operators_bp
    from routes.shifts import bp as shifts_bp
    from routes.comments import bp as comments_bp
    from routes.kpis import bp as kpis_bp
    from routes.assistant import bp as assistant_bp
    from routes.agents import bp as agents_bp
    from routes.views import bp as views_bp
    from routes.admin import bp as admin_bp
    from routes.chart_builder import bp as chart_builder_bp
    from routes.vsm import bp as vsm_bp
    from routes.problems import bp as problems_bp
    from routes.initiatives import bp as initiatives_bp
    from routes.notifications import bp as notifications_bp
    from routes.alerts import bp as alerts_bp
    from routes.data_explorer import bp as data_explorer_bp
    from routes.sqdcp import bp as sqdcp_bp
    from routes.widgets import bp as widgets_bp
    from routes.tiers import bp as tiers_bp
    from routes.group_view import bp as group_view_bp
    from routes.equipment_admin import bp as equipment_admin_bp

    app.register_blueprint(operators_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(comments_bp)
    app.register_blueprint(kpis_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(chart_builder_bp)
    app.register_blueprint(vsm_bp)
    app.register_blueprint(problems_bp)
    app.register_blueprint(initiatives_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(data_explorer_bp)
    app.register_blueprint(sqdcp_bp)
    app.register_blueprint(widgets_bp)
    app.register_blueprint(tiers_bp)
    app.register_blueprint(group_view_bp)
    app.register_blueprint(equipment_admin_bp)
    app.register_blueprint(views_bp)  # vistas HTML al final

    @app.before_request
    def set_current_site():
        """Lee el site activo desde cookie y lo guarda en g."""
        from site_aggregator import SITES, DEFAULT_SITE
        site = flask_request.cookies.get("site", DEFAULT_SITE)
        if site not in SITES and site != "global":
            site = DEFAULT_SITE
        g.current_site = site

    @app.context_processor
    def inject_globals():
        from site_aggregator import SITES, DEFAULT_SITE
        from models.shift import get_active_lines
        try:
            active = get_active_lines()
        except Exception:
            active = []

        # Idioma desde cookie (es por defecto)
        lang = flask_request.cookies.get("lang", "es")
        if lang not in ("es", "en", "ja"):
            lang = "es"

        # Site activo
        current_site = getattr(g, "current_site", DEFAULT_SITE)

        def t(key: str) -> str:
            return get_text(key, lang)

        # Tier hierarchy for sidebar navigation
        nav_hierarchy = None
        if current_site and current_site != "global":
            try:
                from models.tier import get_site_hierarchy
                nav_hierarchy = get_site_hierarchy(current_site)
            except Exception:
                pass

        # Active group from /group/<id> path
        import re as _re
        _gm = _re.match(r"^/group/(\d+)", flask_request.path)
        active_gid = int(_gm.group(1)) if _gm else None

        return {
            "navbar_active_shifts":        active,
            "lang":                        lang,
            "t":                           t,
            "current_site":                current_site,
            "sites":                       SITES,
            "navbar_tier_hierarchy":       nav_hierarchy,
            "navbar_active_group_id":      active_gid,
            "navbar_active_tier_group_id": active_gid,
        }

    # ── Arrancar el monitor en segundo plano ──────────────────────────────────
    # Solo arranca una vez (evita doble start en modo debug con reloader)
    import os
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from monitor import start_monitor
        start_monitor()

    return app


if __name__ == "__main__":
    application = create_app()
    # 0.0.0.0 para compatibilidad con GitHub Codespaces
    application.run(host="0.0.0.0", port=5000, debug=config.DEBUG)
