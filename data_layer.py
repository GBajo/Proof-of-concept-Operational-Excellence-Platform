"""
data_layer.py — Capa de abstracción de datos: SQLite (demo) o Redshift (GMDF).

Controla el modo mediante la variable de entorno:
    DATA_SOURCE=sqlite    (por defecto — datos de prueba locales)
    DATA_SOURCE=redshift  (GMDF real en Redshift)

Las funciones expuestas tienen la misma firma independientemente de la fuente,
lo que permite a la app funcionar en ambos modos sin cambios en las rutas.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────

DATA_SOURCE: str = os.environ.get("DATA_SOURCE", "sqlite").lower().strip()

_VALID_SOURCES = {"sqlite", "redshift"}
if DATA_SOURCE not in _VALID_SOURCES:
    logger.warning(
        "DATA_SOURCE='%s' no reconocido, usando 'sqlite'. "
        "Valores válidos: %s",
        DATA_SOURCE,
        ", ".join(_VALID_SOURCES),
    )
    DATA_SOURCE = "sqlite"


# ── Utilidades ────────────────────────────────────────────────────────────────

def is_redshift() -> bool:
    """Devuelve True si la fuente activa es Redshift."""
    return DATA_SOURCE == "redshift"


def get_source_info() -> dict:
    """
    Información sobre la fuente de datos activa.

    Devuelve: {source, host_masked, schema, connected, mode_label}
    La contraseña y el host completo nunca se exponen.
    """
    if DATA_SOURCE == "sqlite":
        return {
            "source":      "sqlite",
            "host_masked": "localhost",
            "schema":      "N/A",
            "connected":   True,
            "mode_label":  "SQLite (modo demo)",
        }

    from gmdf_connector import _HOST, SCHEMA, RedshiftConnector, ConfigError
    host_masked = (_HOST[:4] + "***") if _HOST else "N/A"
    try:
        conn = RedshiftConnector()
        result = conn.test_connection()
        return {
            "source":      "redshift",
            "host_masked": host_masked,
            "schema":      SCHEMA,
            "connected":   result["ok"],
            "mode_label":  "Redshift (GMDF)",
            "error":       result.get("error"),
        }
    except ConfigError as exc:
        return {
            "source":      "redshift",
            "host_masked": host_masked,
            "schema":      "N/A",
            "connected":   False,
            "mode_label":  "Redshift (GMDF) — no configurado",
            "error":       str(exc),
        }


# ── KPIs ──────────────────────────────────────────────────────────────────────

def get_kpis(site_id: str, line_number: int | None = None, days: int = 7) -> list[dict]:
    """
    Devuelve KPIs de una planta para los últimos N días.

    Parámetros:
        site_id     — Identificador de la planta (ej. "alcobendas")
        line_number — Filtrar por línea (None = todas las líneas)
        days        — Ventana temporal en días (por defecto 7)

    Devuelve lista de dicts con: site_id, line_number, oee, availability,
    performance, quality, units_produced, units_rejected, downtime_minutes,
    shifts_count, period_days
    """
    if DATA_SOURCE == "sqlite":
        return _get_kpis_sqlite(site_id, line_number, days)
    return _get_kpis_redshift(site_id, line_number, days)


def _get_kpis_sqlite(site_id: str, line_number: int | None, days: int) -> list[dict]:
    """Obtiene KPIs desde SQLite usando site_aggregator."""
    from site_aggregator import get_site_kpis
    kpi = get_site_kpis(site_id, days=days)
    if kpi is None:
        return []
    # get_site_kpis devuelve un único dict; adaptamos al formato esperado
    result = {
        "site_id":          site_id,
        "line_number":      line_number,
        "oee":              kpi.get("oee"),
        "availability":     kpi.get("availability"),
        "performance":      kpi.get("performance"),
        "quality":          kpi.get("quality"),
        "units_produced":   kpi.get("units_produced"),
        "units_rejected":   kpi.get("units_rejected"),
        "downtime_minutes": kpi.get("downtime_minutes"),
        "shifts_count":     kpi.get("shifts_count"),
        "period_days":      days,
        "source":           "sqlite",
    }
    return [result]


def _get_kpis_redshift(site_id: str, line_number: int | None, days: int) -> list[dict]:
    """
    Obtiene KPIs desde el GMDF en Redshift.

    STUB: La estructura de tablas del GMDF no está mapeada todavía.
    Devuelve una lista vacía con metadatos para que la app arranque limpiamente.
    Los integradores deben reemplazar esta función con las queries reales del GMDF.
    """
    from gmdf_connector import RedshiftConnector, ConfigError, SCHEMA
    logger.info(
        "data_layer: consultando KPIs en Redshift — site=%s line=%s days=%d",
        site_id, line_number, days,
    )
    try:
        with RedshiftConnector() as conn:
            # TODO: reemplazar con el nombre real de la tabla de KPIs en el GMDF
            # Ejemplo de estructura esperada (adaptar al schema real):
            # SELECT line_id, AVG(oee) as oee, ...
            # FROM {SCHEMA}.manufacturing_kpis
            # WHERE plant_id = %s AND record_date >= DATEADD(day, -%s, GETDATE())
            # GROUP BY line_id
            logger.warning(
                "data_layer: STUB Redshift KPI query — esquema GMDF no mapeado todavía. "
                "Devolviendo lista vacía. Implementar query real en data_layer._get_kpis_redshift()."
            )
            return [{"redshift_stub": True, "site_id": site_id, "source": "redshift"}]
    except ConfigError as exc:
        logger.error("data_layer: Redshift no configurado — %s", exc)
        return []
    except Exception as exc:
        safe_err = re.sub(
            r"password[=:\s]+\S+", "password=[REDACTED]", str(exc), flags=re.IGNORECASE
        )
        logger.error("data_layer: error al consultar Redshift — %s", safe_err)
        return []
