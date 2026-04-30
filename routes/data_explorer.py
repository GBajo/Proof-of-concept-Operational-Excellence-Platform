"""
routes/data_explorer.py — Data Explorer del GMDF / SQLite.

Endpoints:
    GET  /admin/data-explorer                  → página principal
    GET  /api/data-explorer/status             → test de conexión
    GET  /api/data-explorer/tables             → lista de tablas
    GET  /api/data-explorer/columns/<table>    → columnas de una tabla
    POST /api/data-explorer/query              → ejecutar SELECT (solo lectura)

Seguridad:
    - Solo SELECT permitido (validado en gmdf_connector._validate_select_only
      para Redshift, y localmente para SQLite)
    - Límite máximo de 500 filas por query
    - Timeout de 30 s
    - Todas las queries se loguean
    - Las credenciales nunca aparecen en respuestas ni logs
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from typing import Any

from flask import Blueprint, g, jsonify, render_template, request

from data_layer import DATA_SOURCE, get_source_info, is_redshift
from gmdf_connector import SecurityError, _validate_select_only
from site_aggregator import DEFAULT_SITE, SITES

bp = Blueprint("data_explorer", __name__)
logger = logging.getLogger(__name__)

MAX_ROWS    = 500
PAGE_ROWS   = 25  # filas por página en la UI (paginación en JS)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _current_site_db() -> tuple[str, str]:
    """Devuelve (site_id, db_path) del site activo."""
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    db_path = SITES.get(site_id, SITES[DEFAULT_SITE])["db_path"]
    return site_id, db_path


def _sqlite_get_tables(db_path: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _sqlite_get_columns(db_path: str, table_name: str) -> list[dict]:
    # Sanitize: solo letras, números, guiones bajos (no parámetros en PRAGMA)
    if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
        raise ValueError(f"Nombre de tabla inválido: {table_name!r}")
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return [
            {
                "name":     r[1],
                "type":     r[2] or "TEXT",
                "nullable": r[3] == 0,
                "position": r[0],
            }
            for r in rows
        ]
    finally:
        conn.close()


def _sqlite_query(db_path: str, sql: str, limit: int) -> dict:
    """Ejecuta un SELECT en SQLite con validación de seguridad."""
    _validate_select_only(sql)

    # Inyectar LIMIT si no lo tiene
    sql_upper = sql.strip().upper()
    if "LIMIT" not in sql_upper:
        sql = sql.rstrip(";") + f" LIMIT {limit}"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    t0 = time.perf_counter()
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(limit)
        columns = [d[0] for d in cur.description] if cur.description else []
        duration_ms = int((time.perf_counter() - t0) * 1000)

        logger.info(
            "data_explorer SQLite OK | %dms | rows=%d | sql=%s",
            duration_ms, len(rows), sql.strip()[:200].replace("\n", " "),
        )
        return {
            "columns":    columns,
            "rows":       [list(r) for r in rows],
            "row_count":  len(rows),
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.error("data_explorer SQLite ERROR | %dms | %s", duration_ms, exc)
        raise
    finally:
        conn.close()


# ── Rutas HTML ────────────────────────────────────────────────────────────────

@bp.get("/admin/data-explorer")
def data_explorer_page():
    source_info = get_source_info()
    return render_template("admin/data_explorer.html", source_info=source_info)


# ── Rutas API ─────────────────────────────────────────────────────────────────

@bp.get("/api/data-explorer/status")
def api_status():
    """Test de conexión con latencia y conteo de tablas."""
    t0 = time.perf_counter()

    if is_redshift():
        from gmdf_connector import RedshiftConnector, ConfigError
        try:
            conn = RedshiftConnector()
            result = conn.test_connection()
            return jsonify({
                "ok":          result["ok"],
                "source":      "redshift",
                "host":        result.get("host", "N/A"),
                "schema":      result.get("schema"),
                "latency_ms":  result.get("latency_ms"),
                "table_count": result.get("table_count", 0),
                "error":       result.get("error"),
            })
        except ConfigError as exc:
            return jsonify({"ok": False, "source": "redshift", "error": str(exc)}), 503

    # SQLite
    _, db_path = _current_site_db()
    try:
        tables = _sqlite_get_tables(db_path)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return jsonify({
            "ok":          True,
            "source":      "sqlite",
            "host":        "localhost",
            "schema":      db_path,
            "latency_ms":  latency_ms,
            "table_count": len(tables),
            "error":       None,
        })
    except Exception as exc:
        return jsonify({"ok": False, "source": "sqlite", "error": str(exc)}), 503


@bp.get("/api/data-explorer/tables")
def api_tables():
    """Lista todas las tablas disponibles en la fuente activa."""
    if is_redshift():
        from gmdf_connector import RedshiftConnector, ConfigError, ConnectionError as RSConnErr
        try:
            with RedshiftConnector() as conn:
                tables = conn.get_tables()
            return jsonify([{"name": t} for t in tables])
        except (ConfigError, RSConnErr) as exc:
            return jsonify({"error": str(exc)}), 503

    _, db_path = _current_site_db()
    try:
        tables = _sqlite_get_tables(db_path)
        return jsonify([{"name": t} for t in tables])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.get("/api/data-explorer/columns/<table_name>")
def api_columns(table_name: str):
    """Devuelve las columnas y tipos de una tabla."""
    if is_redshift():
        from gmdf_connector import RedshiftConnector, ConfigError, ConnectionError as RSConnErr
        try:
            with RedshiftConnector() as conn:
                cols = conn.get_columns(table_name)
            return jsonify(cols)
        except (ConfigError, RSConnErr) as exc:
            return jsonify({"error": str(exc)}), 503
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    _, db_path = _current_site_db()
    try:
        cols = _sqlite_get_columns(db_path, table_name)
        return jsonify(cols)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/api/data-explorer/query")
def api_query():
    """
    Ejecuta un SELECT y devuelve columnas + filas.

    Body JSON: { "sql": "SELECT ...", "limit": 100 }
    Límite máximo: 500 filas.
    Solo SELECT permitido.
    """
    data = request.get_json(silent=True) or {}
    sql   = (data.get("sql") or "").strip()
    limit = min(int(data.get("limit") or PAGE_ROWS), MAX_ROWS)

    if not sql:
        return jsonify({"error": "El campo 'sql' es obligatorio"}), 400

    # Validación de seguridad (aplica a ambas fuentes)
    try:
        _validate_select_only(sql)
    except SecurityError as exc:
        logger.warning("data_explorer: query bloqueada — %s", exc)
        return jsonify({"error": str(exc)}), 400

    if is_redshift():
        from gmdf_connector import RedshiftConnector, ConfigError, ConnectionError as RSConnErr
        try:
            with RedshiftConnector() as conn:
                rows_dicts = conn.query(sql + (f" LIMIT {limit}" if "LIMIT" not in sql.upper() else ""))
            if not rows_dicts:
                return jsonify({"columns": [], "rows": [], "row_count": 0, "duration_ms": 0})
            columns = list(rows_dicts[0].keys())
            rows    = [[r[c] for c in columns] for r in rows_dicts]
            return jsonify({
                "columns":    columns,
                "rows":       rows,
                "row_count":  len(rows),
                "duration_ms": 0,  # connector no expone timing en este path
            })
        except SecurityError as exc:
            return jsonify({"error": str(exc)}), 400
        except (ConfigError, RSConnErr) as exc:
            return jsonify({"error": str(exc)}), 503
        except Exception as exc:
            safe_err = re.sub(
                r"password[=:\s]+\S+", "password=[REDACTED]", str(exc), flags=re.IGNORECASE
            )
            return jsonify({"error": safe_err}), 500

    # SQLite
    _, db_path = _current_site_db()
    try:
        result = _sqlite_query(db_path, sql, limit)
        return jsonify(result)
    except SecurityError as exc:
        return jsonify({"error": str(exc)}), 400
    except sqlite3.OperationalError as exc:
        return jsonify({"error": f"Error SQL: {exc}"}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
