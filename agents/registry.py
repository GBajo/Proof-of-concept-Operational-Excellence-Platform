"""
agents/registry.py — Registro central de todos los agentes disponibles.

Uso:
    from agents.registry import get_agent, list_agents

    agents = list_agents()            # [{"name": ..., "description": ...}, ...]
    agent  = get_agent("kpi_analyst") # instancia del agente, o None
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base import Agent

# ── Mapa de agentes registrados ───────────────────────────────────────────────
# Formato: { nombre_clave: clase_agente }
#
# Los agentes individuales se importan de forma lazy (dentro de get_agent)
# para evitar importaciones circulares y acelerar el arranque cuando solo
# se necesita listar los agentes disponibles.

_REGISTRY: dict[str, str] = {}

# Metadatos estáticos de cada agente para que el orquestador pueda
# presentarlos al LLM sin necesidad de instanciar las clases.
_METADATA: dict[str, dict] = {}


# ── Registro de agentes del sistema ──────────────────────────────────────────
# Cada llamada a register_agent() añade el agente al sistema.
# Añadir aquí los nuevos agentes conforme se creen.

def _register_builtin_agents() -> None:
    register_agent(
        name="kpi_analyst",
        import_path="agents.kpi_analyst:KpiAnalystAgent",
        description=(
            "Analiza KPIs de producción farmacéutica: OEE y sus componentes (Disponibilidad, "
            "Rendimiento, Calidad), velocidad de línea, tasa de rechazo y downtime. "
            "Detecta anomalías, calcula tendencias, compara líneas y puede generar gráficos. "
            "Activar cuando el operador pregunte por producción, rendimiento, OEE, rechazos, "
            "velocidad, targets o comparativas entre líneas."
        ),
        category="production",
    )

    register_agent(
        name="maintenance",
        import_path="agents.maintenance_agent:MaintenanceAgent",
        description=(
            "Ingeniero de mantenimiento predictivo para equipos de packaging farmacéutico. "
            "Analiza alertas activas, cycle times del VSM y problemas recurrentes para detectar "
            "fallos inminentes, identificar causas raíz y recomendar mantenimiento preventivo. "
            "Calcula MTBF y MTTR. "
            "Activar cuando el operador mencione averías, paradas, fallos, alertas, "
            "vibraciones, ruidos anómalos, desgaste, mantenimiento o reparaciones."
        ),
        category="maintenance",
    )

    register_agent(
        name="doc_search",
        import_path="agents.doc_search_agent:DocSearchAgent",
        description=(
            "Especialista en documentación técnica farmacéutica (SOPs, manuales, procedimientos). "
            "Busca en la base de conocimiento indexada y cita siempre el documento fuente. "
            "Puede detectar lagunas documentales y sugerir actualizaciones de SOPs. "
            "Activar cuando el operador busque un procedimiento, instrucción de trabajo, "
            "especificación técnica, normativa GMP o quiera saber cómo hacer algo."
        ),
        category="documentation",
    )

    register_agent(
        name="production",
        import_path="agents.production_agent:ProductionAgent",
        description=(
            "Planificador de producción farmacéutica. Analiza la capacidad de cada línea, "
            "detecta cuellos de botella en el flujo de proceso (VSM), calcula el impacto de "
            "paradas en el plan y proyecta si el turno alcanzará el target de producción. "
            "Activar cuando el operador pregunte por planificación, capacidad, si llegarán al "
            "objetivo, cuánto se ha perdido por paradas, o cómo recuperar producción."
        ),
        category="production",
    )

    register_agent(
        name="kaizen",
        import_path="agents.kaizen_agent:KaizenAgent",
        description=(
            "Consultor Lean/Six Sigma especializado en fabricación farmacéutica. "
            "Analiza problemas e iniciativas de todos los sites para sugerir proyectos kaizen, "
            "identificar best practices transferibles entre plantas y proponer A3s. "
            "Evalúa el impacto real de iniciativas completadas. "
            "Activar cuando el operador pregunte por mejoras, oportunidades de mejora, "
            "kaizen, iniciativas, best practices o quiera saber qué hacen otras plantas."
        ),
        category="improvement",
    )


# ── API pública ───────────────────────────────────────────────────────────────

def register_agent(
    name: str,
    import_path: str,
    description: str,
    category: str = "general",
) -> None:
    """
    Registra un agente en el sistema.

    Parámetros:
        name        — Identificador único (e.g. "kpi_analyst")
        import_path — "módulo:Clase" (e.g. "agents.kpi_analyst:KpiAnalystAgent")
        description — Descripción breve que el orquestador enviará al LLM para decidir
                      si activar este agente. Debe ser específica y en español.
        category    — Categoría opcional para agrupar agentes en la UI.
    """
    _REGISTRY[name] = import_path
    _METADATA[name] = {"description": description, "category": category}


def list_agents() -> list[dict]:
    """
    Devuelve la lista de agentes registrados con su nombre y descripción.
    No instancia las clases; solo devuelve metadatos.

    Devuelve lista de dicts con keys: name, description, category.
    """
    return [
        {
            "name": name,
            "description": meta["description"],
            "category": meta.get("category", "general"),
        }
        for name, meta in _METADATA.items()
    ]


def get_agent(
    name: str,
    site_id: str = "alcobendas",
    db_path: str = "site_alcobendas.db",
) -> "Agent | None":
    """
    Instancia y devuelve el agente con ese nombre, o None si no existe.

    Parámetros:
        name    — Nombre del agente (clave en el registro)
        site_id — Identificador del site activo (inyectado en el agente)
        db_path — Ruta a la base de datos del site activo

    Devuelve una instancia de la subclase Agent correspondiente, o None.
    """
    import_path = _REGISTRY.get(name)
    if not import_path:
        return None

    try:
        module_path, class_name = import_path.rsplit(":", 1)
        import importlib
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls(site_id=site_id, db_path=db_path)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(
            "Error al cargar el agente '%s' desde '%s': %s",
            name, import_path, exc,
        )
        return None


def get_agent_description(name: str) -> str | None:
    """Devuelve la descripción de un agente sin instanciarlo."""
    meta = _METADATA.get(name)
    return meta["description"] if meta else None


# Registrar los agentes integrados al importar el módulo
_register_builtin_agents()
