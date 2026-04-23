"""
agents/base.py — Clase base para todos los agentes inteligentes.

Cada agente especializado hereda de Agent y define:
  - name, description            → identidad para el orquestador
  - system_prompt                → instrucciones del rol que desempeña
  - required_data                → qué consultas de BD necesita (nombres clave)
  - get_context(context_data)    → construye el contexto enriquecido con datos de BD
  - run(user_message, context_data) → llama al LLM y devuelve la respuesta
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from llm_client import _call_gateway, _get_api_key, _mock_response, MAX_TOKENS


class Agent(ABC):
    """
    Clase base abstracta para agentes especializados.

    Subclases deben definir name, description, system_prompt y required_data,
    y pueden sobreescribir get_context() para enriquecer el contexto con BD.
    """

    # ── Identidad del agente ──────────────────────────────────────────────────
    name: str = ""
    description: str = ""
    system_prompt: str = ""
    max_tokens: int = MAX_TOKENS  # subclasses can override for larger responses

    # Lista de claves que este agente necesita en context_data.
    # El orquestador usa esta lista para saber qué datos preparar antes de
    # llamar a run(). Ejemplo: ["active_shift", "last_kpi_reading"]
    required_data: list[str] = []

    # ── Contexto de ejecución (inyectado por el orquestador) ──────────────────
    # site_id y db_path se populan en runtime; no se definen a nivel de clase
    # para evitar estado compartido entre instancias.

    def __init__(self, site_id: str = "alcobendas", db_path: str = "site_alcobendas.db") -> None:
        self.site_id = site_id
        self.db_path = db_path

    def _get_conn(self) -> "sqlite3.Connection":
        """
        Devuelve una conexión SQLite al db_path del agente.

        Dentro de un request Flask reutiliza la conexión cacheada en g (evita
        abrir una segunda conexión). Fuera de contexto Flask abre una directa.
        """
        import sqlite3 as _sqlite3
        try:
            from flask import g
            from database import get_db
            return get_db(self.site_id)
        except RuntimeError:
            # Fuera de contexto Flask (tests, background tasks)
            conn = _sqlite3.connect(self.db_path)
            conn.row_factory = _sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn

    def _close_conn_if_external(self, conn: "sqlite3.Connection") -> None:
        """Cierra la conexión solo si fue abierta fuera de contexto Flask."""
        try:
            from flask import g  # noqa — si falla, estamos fuera de contexto
            # Dentro de Flask: get_db() gestiona el ciclo de vida, no cerrar
        except RuntimeError:
            conn.close()

    # ── Recuperación de datos de BD ───────────────────────────────────────────

    def get_context(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        Enriquece context_data con información de BD específica de este agente.

        La implementación por defecto devuelve context_data sin modificar.
        Subclases sobrescriben este método para inyectar datos que necesitan
        (KPIs actuales, turno activo, problemas abiertos, etc.).

        Parámetros:
            context_data — Datos ya reunidos por el orquestador (puede estar vacío).

        Devuelve:
            Diccionario enriquecido con los datos que el agente necesita.
        """
        return context_data

    # ── Construcción del prompt de usuario ───────────────────────────────────

    def build_prompt(
        self,
        user_message: str,
        context_data: dict[str, Any],
        rag_chunks: list[dict] | None = None,
        previous_outputs: list[dict] | None = None,
    ) -> str:
        """
        Construye el mensaje de usuario que se enviará al LLM.

        Incluye:
          1. Contexto de datos estructurados (context_data)
          2. Fragmentos RAG si los hay
          3. Salidas de agentes anteriores (para colaboración en cadena)
          4. El mensaje original del usuario

        Las subclases pueden sobreescribir este método para personalizar
        el formato del prompt.
        """
        parts: list[str] = []

        if context_data:
            parts.append("## Datos del sistema")
            for key, value in context_data.items():
                parts.append(f"**{key}:** {value}")
            parts.append("")

        if rag_chunks:
            parts.append("## Documentación de referencia")
            for chunk in rag_chunks:
                source = chunk.get("source_file", "Desconocido")
                text = chunk.get("chunk_text", "").strip()
                parts.append(f"[Fuente: {source}]\n{text}")
            parts.append("")

        if previous_outputs:
            parts.append("## Análisis de otros agentes especializados")
            for output in previous_outputs:
                agent_name = output.get("agent", "Agente")
                response = output.get("response", "")
                parts.append(f"**{agent_name}:** {response}")
            parts.append("")

        parts.append("## Mensaje del operador")
        parts.append(user_message.strip())

        return "\n\n".join(parts)

    # ── Llamada al LLM ────────────────────────────────────────────────────────

    def run(
        self,
        user_message: str,
        context_data: dict[str, Any] | None = None,
        rag_chunks: list[dict] | None = None,
        previous_outputs: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Ejecuta el agente: enriquece el contexto, construye el prompt y llama al LLM.

        Parámetros:
            user_message      — Mensaje original del usuario
            context_data      — Datos de contexto ya preparados (BD, sesión, etc.)
            rag_chunks        — Fragmentos RAG recuperados por el retriever
            previous_outputs  — Respuestas de agentes ejecutados anteriormente

        Devuelve dict con:
            agent       — Nombre del agente
            response    — Texto de la respuesta
            model       — Modelo LLM usado
            source      — "gateway" | "mock"
            error       — Mensaje de error si lo hubo (opcional)
        """
        ctx = self.get_context(context_data or {})
        prompt = self.build_prompt(user_message, ctx, rag_chunks, previous_outputs)

        api_key = _get_api_key()
        if not api_key:
            mock = _mock_response(user_message, rag_chunks or [], "production")
            return {
                "agent": self.name,
                "response": mock["text"],
                "model": "mock",
                "source": "mock",
                "error": "Token de autenticación no disponible",
            }

        try:
            result = _call_gateway(prompt, api_key, system=self.system_prompt, max_tokens=self.max_tokens)
            return {
                "agent": self.name,
                "response": result["text"],
                "model": result["model"],
                "source": "gateway",
            }

        except Exception as exc:
            error_str = str(exc)
            if "401" in error_str or "authentication" in error_str.lower():
                error_msg = "Error de autenticación con el gateway (401)"
            elif "timeout" in error_str.lower():
                error_msg = "Timeout al conectar con el gateway"
            elif any(c in error_str for c in ("500", "502", "503")):
                error_msg = "El gateway no está disponible temporalmente"
            else:
                error_msg = f"Error inesperado: {error_str[:120]}"

            mock = _mock_response(user_message, rag_chunks or [], "production")
            return {
                "agent": self.name,
                "response": mock["text"],
                "model": "mock",
                "source": "mock",
                "error": error_msg,
            }

    # ── Representación ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<Agent name={self.name!r}>"
