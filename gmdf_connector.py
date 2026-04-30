"""
gmdf_connector.py — Conector al GMDF de Lilly via Amazon Redshift.

Credenciales leídas exclusivamente de variables de entorno:
    REDSHIFT_HOST, REDSHIFT_PORT, REDSHIFT_DATABASE,
    REDSHIFT_USER, REDSHIFT_PASSWORD, REDSHIFT_SCHEMA

Nunca se hardcodean credenciales en este módulo.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuración desde variables de entorno ──────────────────────────────────

_HOST     = os.environ.get("REDSHIFT_HOST", "")
_PORT     = int(os.environ.get("REDSHIFT_PORT", "5439"))
_DATABASE = os.environ.get("REDSHIFT_DATABASE", "")
_USER     = os.environ.get("REDSHIFT_USER", "")
_PASSWORD = os.environ.get("REDSHIFT_PASSWORD", "")
SCHEMA    = os.environ.get("REDSHIFT_SCHEMA", "public")

QUERY_TIMEOUT_S = 30
_MAX_RETRIES    = 3
_RETRY_DELAY_S  = 2


# ── Excepciones propias ───────────────────────────────────────────────────────

class ConfigError(Exception):
    """Variable de entorno de configuración faltante o inválida."""


class SecurityError(Exception):
    """La query no cumple la política de solo lectura."""


class ConnectionError(Exception):  # noqa: A001 — shadowing built-in intentionally
    """No se pudo establecer conexión con Redshift."""


# ── Validación de SELECT-only ─────────────────────────────────────────────────

# Palabras clave que modifican datos — bloqueadas siempre
_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)
# Comentarios SQL (-- y /* */)
_SQL_COMMENT = re.compile(r"(--[^\n]*|/\*[\s\S]*?\*/)", re.MULTILINE)


def _validate_select_only(sql: str) -> None:
    """
    Lanza SecurityError si la query no es un SELECT puro.

    Elimina comentarios antes de analizar para evitar bypass mediante
    comentarios que oculten palabras clave peligrosas.
    """
    clean = _SQL_COMMENT.sub(" ", sql).strip()
    first_token = clean.split()[0].upper() if clean.split() else ""
    if first_token != "SELECT":
        raise SecurityError(
            f"Solo se permiten consultas SELECT. "
            f"Primer token encontrado: '{first_token}'"
        )
    if _BLOCKED_KEYWORDS.search(clean):
        raise SecurityError(
            "La query contiene palabras clave no permitidas (INSERT, UPDATE, DELETE, etc.)"
        )


# ── Conector principal ────────────────────────────────────────────────────────

class RedshiftConnector:
    """
    Conector a Amazon Redshift con retry automático y política SELECT-only.

    Uso típico:
        connector = RedshiftConnector()
        connector.connect()
        rows = connector.query("SELECT * FROM table LIMIT 10")
        connector.close()

    O como context manager:
        with RedshiftConnector() as conn:
            rows = conn.query("SELECT ...")
    """

    def __init__(self) -> None:
        self._validate_config()
        self._conn: Any = None

    # ── Validación de configuración ───────────────────────────────────────────

    @staticmethod
    def _validate_config() -> None:
        """Comprueba que las variables de entorno necesarias están definidas."""
        missing = [
            name for name, val in [
                ("REDSHIFT_HOST",     _HOST),
                ("REDSHIFT_DATABASE", _DATABASE),
                ("REDSHIFT_USER",     _USER),
                ("REDSHIFT_PASSWORD", _PASSWORD),
            ]
            if not val
        ]
        if missing:
            raise ConfigError(
                f"Variables de entorno Redshift no configuradas: {', '.join(missing)}. "
                "Consulta la documentación de despliegue."
            )

    # ── Conexión ──────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Abre conexión al cluster Redshift con reintentos."""
        try:
            import redshift_connector  # noqa: PLC0415
        except ImportError as exc:
            raise ConfigError(
                "Librería 'redshift_connector' no instalada. "
                "Ejecuta: pip install redshift-connector"
            ) from exc

        last_err: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._conn = redshift_connector.connect(
                    host=_HOST,
                    port=_PORT,
                    database=_DATABASE,
                    user=_USER,
                    password=_PASSWORD,
                    timeout=QUERY_TIMEOUT_S,
                )
                self._conn.autocommit = True
                logger.info(
                    "Redshift: conexión establecida con %s:%d/%s (intento %d)",
                    _HOST[:4] + "***",   # no logar host completo
                    _PORT,
                    _DATABASE,
                    attempt,
                )
                return
            except Exception as exc:
                last_err = exc
                # No incluir la excepción raw porque puede contener credenciales
                safe_msg = re.sub(
                    r"password[=:\s]+\S+", "password=[REDACTED]", str(exc), flags=re.IGNORECASE
                )
                logger.warning(
                    "Redshift: intento %d/%d fallido — %s",
                    attempt, _MAX_RETRIES, safe_msg,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY_S)

        raise ConnectionError(
            f"No se pudo conectar a Redshift tras {_MAX_RETRIES} intentos. "
            "Verifica las credenciales y la conectividad de red."
        ) from last_err

    def _ensure_connected(self) -> None:
        """Reabre la conexión si se ha cerrado o perdido."""
        if self._conn is None:
            self.connect()
            return
        try:
            # Ping ligero para verificar que sigue activa
            cur = self._conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        except Exception:
            logger.info("Redshift: conexión perdida, reconectando...")
            self._conn = None
            self.connect()

    # ── Consultas ─────────────────────────────────────────────────────────────

    def query(self, sql: str, params: tuple | None = None) -> list[dict]:
        """
        Ejecuta una query SELECT y devuelve los resultados como lista de dicts.

        Parámetros:
            sql    — Consulta SQL (solo SELECT permitido)
            params — Parámetros para placeholders (%s)

        Lanza:
            SecurityError    — Si la query no es un SELECT
            ConnectionError  — Si no se puede conectar
        """
        _validate_select_only(sql)
        self._ensure_connected()

        t0 = time.perf_counter()
        safe_sql_log = sql.strip()[:200].replace("\n", " ")
        param_count  = len(params) if params else 0

        try:
            cur = self._conn.cursor()
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)

            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows    = cur.fetchall()
            cur.close()

            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "Redshift query OK | %dms | params=%d | sql=%s",
                duration_ms, param_count, safe_sql_log,
            )

            return [dict(zip(columns, row)) for row in rows]

        except Exception as exc:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            safe_err = re.sub(
                r"password[=:\s]+\S+", "password=[REDACTED]", str(exc), flags=re.IGNORECASE
            )
            logger.error(
                "Redshift query ERROR | %dms | sql=%s | error=%s",
                duration_ms, safe_sql_log, safe_err,
            )
            raise

    def get_tables(self) -> list[str]:
        """Lista todas las tablas accesibles en el schema configurado."""
        rows = self.query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s "
            "ORDER BY table_name",
            (SCHEMA,),
        )
        return [r["table_name"] for r in rows]

    def get_columns(self, table_name: str) -> list[dict]:
        """
        Devuelve las columnas de una tabla.

        Retorna lista de: {name, data_type, nullable, ordinal_position}
        """
        rows = self.query(
            "SELECT column_name, data_type, is_nullable, ordinal_position "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (SCHEMA, table_name),
        )
        return [
            {
                "name":     r["column_name"],
                "type":     r["data_type"],
                "nullable": r["is_nullable"] == "YES",
                "position": r["ordinal_position"],
            }
            for r in rows
        ]

    def test_connection(self) -> dict:
        """
        Prueba la conexión y devuelve métricas básicas.

        Retorna: {ok, latency_ms, table_count, schema, error}
        La contraseña nunca aparece en el resultado.
        """
        t0 = time.perf_counter()
        try:
            self._ensure_connected()
            tables = self.get_tables()
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "ok":          True,
                "latency_ms":  latency_ms,
                "table_count": len(tables),
                "schema":      SCHEMA,
                "host":        (_HOST[:4] + "***") if _HOST else "N/A",
                "error":       None,
            }
        except ConfigError as exc:
            return {"ok": False, "error": str(exc), "latency_ms": None, "table_count": 0}
        except Exception as exc:
            safe_err = re.sub(
                r"password[=:\s]+\S+", "password=[REDACTED]", str(exc), flags=re.IGNORECASE
            )
            return {"ok": False, "error": safe_err, "latency_ms": None, "table_count": 0}

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def close(self) -> None:
        """Cierra la conexión de forma limpia."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> "RedshiftConnector":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        host_safe = (_HOST[:4] + "***") if _HOST else "not-configured"
        connected = "connected" if self._conn else "disconnected"
        return f"<RedshiftConnector host={host_safe} db={_DATABASE!r} {connected}>"
