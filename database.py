import sqlite3
from flask import g


def get_db(site_id: str | None = None) -> sqlite3.Connection:
    """
    Devuelve la conexión a la BD del site activo en la solicitud actual.
    Si se pasa site_id explícitamente, usa esa planta.
    """
    from site_aggregator import SITES, DEFAULT_SITE

    if site_id is None:
        site_id = getattr(g, "current_site", DEFAULT_SITE)

    key = f"db_{site_id}"
    existing = getattr(g, key, None)
    if existing is not None:
        return existing

    db_path = SITES.get(site_id, SITES[DEFAULT_SITE])["db_path"]
    db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    setattr(g, key, db)
    return db


def close_db(e=None) -> None:
    """Cierra todas las conexiones abiertas al finalizar la solicitud."""
    from site_aggregator import SITES
    for site_id in SITES:
        key = f"db_{site_id}"
        db = getattr(g, key, None)
        if db is not None:
            try:
                delattr(g, key)
            except AttributeError:
                pass
            db.close()
    # Conexión de reglas de alertas (gestionada por routes/alerts.py bajo la clave
    # g._alerts_rules_db, siempre apuntando a la BD del DEFAULT_SITE)
    rules_db = getattr(g, "_alerts_rules_db", None)
    if rules_db is not None:
        try:
            delattr(g, "_alerts_rules_db")
        except AttributeError:
            pass
        rules_db.close()
    # Compatibilidad con clave legacy "db" si quedara alguna
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app) -> None:
    """Crea el esquema en todas las bases de datos de planta y siembra datos."""
    from site_aggregator import SITES
    from seed_sites import seed_all_sites, _create_schema

    with app.app_context():
        for site_info in SITES.values():
            _create_schema(site_info["db_path"])
        seed_all_sites()
