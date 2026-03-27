from flask import Flask, request as flask_request
from config import config
from database import close_db, init_db
from translations import get_text


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_PATH"] = config.DATABASE_PATH
    app.config["DEBUG"] = config.DEBUG
    app.config["SECRET_KEY"] = config.SECRET_KEY

    # Inicializar base de datos
    init_db(app)

    # Cerrar conexión al finalizar cada solicitud
    app.teardown_appcontext(close_db)

    # Registrar blueprints API (primero)
    from routes.operators import bp as operators_bp
    from routes.shifts import bp as shifts_bp
    from routes.comments import bp as comments_bp
    from routes.kpis import bp as kpis_bp
    from routes.assistant import bp as assistant_bp
    from routes.views import bp as views_bp
    from routes.admin import bp as admin_bp
    from routes.chart_builder import bp as chart_builder_bp

    app.register_blueprint(operators_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(comments_bp)
    app.register_blueprint(kpis_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(chart_builder_bp)
    app.register_blueprint(views_bp)  # vistas HTML al final

    @app.context_processor
    def inject_globals():
        from models.shift import get_active_lines
        try:
            active = get_active_lines()
        except Exception:
            active = []
        # Idioma desde cookie (es por defecto)
        lang = flask_request.cookies.get("lang", "es")
        if lang not in ("es", "en"):
            lang = "es"
        # t() es el helper de traducción disponible en todos los templates
        def t(key: str) -> str:
            return get_text(key, lang)
        return {
            'navbar_active_shifts': active,
            'lang': lang,
            't': t,
        }

    return app


if __name__ == "__main__":
    application = create_app()
    # 0.0.0.0 para compatibilidad con GitHub Codespaces
    application.run(host="0.0.0.0", port=5000, debug=config.DEBUG)
