"""
agents/orchestrator.py — Agente orquestador del ecosistema de agentes.

Flujo de ejecución:
  1. Recibe el mensaje del usuario y el contexto de sesión.
  2. Llama al LLM con un prompt de clasificación para decidir qué agentes activar.
     El LLM responde con JSON: {"agents": ["kpi_analyst", "maintenance"], "chain": true}
  3. Ejecuta los agentes seleccionados:
     - Si chain=false: en paralelo (independientes), combina al final.
     - Si chain=true:  en secuencia, pasando la salida de cada uno al siguiente.
  4. Genera una respuesta final unificada llamando de nuevo al LLM.
  5. Guarda en BD y devuelve el resultado.

Uso:
    from agents.orchestrator import Orchestrator

    orch = Orchestrator(site_id="alcobendas", db_path="site_alcobendas.db")
    result = orch.run(
        user_message="¿Cuál es el OEE de hoy y hay alguna alerta de mantenimiento?",
        shift_id=42,
        comment_id=None,
        category="production",
    )
    print(result["text"])
"""

from __future__ import annotations

import json
import logging
from typing import Any

from llm_client import _call_gateway, _get_api_key, _mock_response
from retriever import get_context
from agents.registry import list_agents, get_agent

logger = logging.getLogger(__name__)

# ── Prompt de clasificación ───────────────────────────────────────────────────

_CLASSIFICATION_SYSTEM = (
    "Eres el orquestador de un sistema multiagente para plantas de fabricación farmacéutica. "
    "Tu única tarea es analizar el mensaje del operador y decidir qué agentes especializados "
    "deben activarse para responderlo de forma óptima. "
    "Responde SIEMPRE con un objeto JSON válido y nada más. "
    "No añadas explicaciones fuera del JSON. "
    "Si no hay agentes registrados o el mensaje es genérico, usa la lista vacía.\n\n"
    "Guía de selección rápida:\n"
    "- 'ci_coach': preguntas sobre cómo gestionar o mejorar una iniciativa concreta, "
    "revisión de A3, estimar beneficio, validar plazos, buscar proyectos similares entre plantas.\n"
    "- 'kaizen': oportunidades de mejora nuevas, análisis cross-site de problemas, "
    "best practices, informe diario.\n"
    "- Ambos pueden activarse juntos si el mensaje mezcla análisis de oportunidades y "
    "coaching sobre una iniciativa específica."
)

_CLASSIFICATION_TEMPLATE = """\
## Agentes disponibles
{agents_list}

## Mensaje del operador
{user_message}

## Tarea
Analiza el mensaje y decide qué agentes de la lista anterior deben activarse.

Responde con este JSON exacto:
{{
  "agents": ["nombre_agente_1", "nombre_agente_2"],
  "chain": false,
  "reasoning": "breve explicación de la selección"
}}

Notas:
- "agents": lista de nombres exactos de la lista (puede estar vacía []).
- "chain": true si los agentes deben ejecutarse en secuencia (la salida de uno
  alimenta al siguiente), false si pueden responder de forma independiente.
- Usa chain:true solo cuando el segundo agente necesite el análisis del primero.
"""

# ── Prompt de síntesis final ──────────────────────────────────────────────────

_SYNTHESIS_SYSTEM = (
    "Eres un asistente técnico experto en líneas de empaquetado farmacéutico. "
    "Detect the language of the user's message and ALWAYS respond in that same language. "
    "Recibes los análisis de varios agentes especializados y debes sintetizarlos en "
    "una respuesta única, clara y accionable para el operador de planta. "
    "Integra la información de todos los agentes sin repetir datos. "
    "Sé conciso: máximo 5-6 frases. Cita las fuentes documentales entre corchetes."
)

_SYNTHESIS_TEMPLATE = """\
## Mensaje original del operador
{user_message}

## Análisis de los agentes especializados
{agent_outputs}

## Tarea
Sintetiza los análisis anteriores en una respuesta única, directa y útil para el operador.
"""

# ── Fallback cuando no hay agentes ────────────────────────────────────────────

_FALLBACK_SYSTEM = (
    "Eres un asistente técnico experto en líneas de empaquetado farmacéutico. "
    "Detect the language of the user's message and ALWAYS respond in that same language. "
    "Basa tus respuestas en la documentación proporcionada. "
    "Sé conciso: máximo 4-5 frases. Cita las fuentes entre corchetes."
)


class Orchestrator:
    """
    Agente orquestador que coordina el ecosistema de agentes especializados.
    """

    def __init__(self, site_id: str = "alcobendas", db_path: str = "site_alcobendas.db") -> None:
        self.site_id = site_id
        self.db_path = db_path

    # ── Paso 1: Clasificación ─────────────────────────────────────────────────

    def _classify(self, user_message: str, api_key: str | None) -> dict:
        """
        Pregunta al LLM qué agentes activar.
        Devuelve {"agents": [...], "chain": bool, "reasoning": str}.
        Si no hay agentes registrados o la llamada falla, devuelve lista vacía.
        """
        agents = list_agents()
        if not agents:
            return {"agents": [], "chain": False, "reasoning": "No hay agentes registrados"}

        agents_list = "\n".join(
            f"- **{a['name']}**: {a['description']}" for a in agents
        )
        prompt = _CLASSIFICATION_TEMPLATE.format(
            agents_list=agents_list,
            user_message=user_message.strip(),
        )

        if not api_key:
            logger.warning("Orquestador: sin API key, omitiendo clasificación")
            return {"agents": [], "chain": False, "reasoning": "Sin API key"}

        try:
            result = _call_gateway(prompt, api_key, system=_CLASSIFICATION_SYSTEM)
            raw = result["text"].strip()

            # Extraer JSON aunque el LLM añada texto extra
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

            classification = json.loads(raw)
            # Validar que los agentes listados existen en el registro
            registered_names = {a["name"] for a in agents}
            valid_agents = [
                name for name in classification.get("agents", [])
                if name in registered_names
            ]
            return {
                "agents": valid_agents,
                "chain": bool(classification.get("chain", False)),
                "reasoning": classification.get("reasoning", ""),
            }

        except Exception as exc:
            logger.warning("Error en clasificación: %s — activando fallback directo", exc)
            return {"agents": [], "chain": False, "reasoning": f"Error: {exc}"}

    # ── Paso 2: Ejecución de agentes ──────────────────────────────────────────

    def _run_agents(
        self,
        agent_names: list[str],
        chain: bool,
        user_message: str,
        rag_chunks: list[dict],
        context_data: dict,
    ) -> list[dict]:
        """
        Ejecuta los agentes seleccionados.
        - chain=False: cada agente recibe el mismo prompt base (independientes).
        - chain=True:  la salida de cada agente se pasa como previous_outputs al siguiente.
        """
        outputs: list[dict] = []

        for name in agent_names:
            agent = get_agent(name, site_id=self.site_id, db_path=self.db_path)
            if agent is None:
                logger.warning("Agente '%s' no encontrado, se omite", name)
                continue

            previous = outputs if chain else []
            output = agent.run(
                user_message=user_message,
                context_data=context_data,
                rag_chunks=rag_chunks,
                previous_outputs=previous,
            )
            outputs.append(output)
            logger.debug("Agente '%s' completado (source=%s)", name, output.get("source"))

        return outputs

    # ── Paso 3: Síntesis ──────────────────────────────────────────────────────

    def _synthesize(
        self,
        user_message: str,
        agent_outputs: list[dict],
        rag_chunks: list[dict],
        api_key: str | None,
    ) -> dict:
        """
        Combina las respuestas de todos los agentes en una respuesta final unificada.
        Si solo hay un agente, devuelve su respuesta directamente.
        """
        if not agent_outputs:
            # Fallback: respuesta directa sin agentes
            return self._direct_response(user_message, rag_chunks, api_key)

        if len(agent_outputs) == 1:
            output = agent_outputs[0]
            return {
                "text": output["response"],
                "model": output.get("model", "unknown"),
                "source": output.get("source", "mock"),
                "error": output.get("error"),
                "agents_used": [output["agent"]],
            }

        # Múltiples agentes → síntesis
        agent_section = "\n\n".join(
            f"### {o['agent']}\n{o['response']}" for o in agent_outputs
        )
        prompt = _SYNTHESIS_TEMPLATE.format(
            user_message=user_message.strip(),
            agent_outputs=agent_section,
        )

        models_used = [o.get("model", "unknown") for o in agent_outputs]
        errors = [o["error"] for o in agent_outputs if o.get("error")]
        agents_used = [o["agent"] for o in agent_outputs]

        if not api_key:
            combined = "\n\n".join(
                f"**{o['agent']}:** {o['response']}" for o in agent_outputs
            )
            return {
                "text": combined,
                "model": "mock",
                "source": "mock",
                "error": errors[0] if errors else None,
                "agents_used": agents_used,
            }

        try:
            result = _call_gateway(prompt, api_key, system=_SYNTHESIS_SYSTEM)
            return {
                "text": result["text"],
                "model": result["model"],
                "source": "gateway",
                "error": errors[0] if errors else None,
                "agents_used": agents_used,
            }
        except Exception as exc:
            logger.warning("Error en síntesis: %s — usando respuestas individuales", exc)
            combined = "\n\n".join(
                f"**{o['agent']}:** {o['response']}" for o in agent_outputs
            )
            return {
                "text": combined,
                "model": models_used[0] if models_used else "unknown",
                "source": "mock",
                "error": str(exc),
                "agents_used": agents_used,
            }

    def _direct_response(
        self,
        user_message: str,
        rag_chunks: list[dict],
        api_key: str | None,
    ) -> dict:
        """Respuesta directa al LLM sin pasar por agentes (fallback)."""
        from llm_client import _build_user_message, SYSTEM_PROMPT

        prompt = _build_user_message(user_message, rag_chunks, "production")

        if not api_key:
            mock = _mock_response(user_message, rag_chunks, "production")
            return {
                "text": mock["text"],
                "model": "mock",
                "source": "mock",
                "error": "Token de autenticación no disponible",
                "agents_used": [],
            }

        try:
            result = _call_gateway(prompt, api_key, system=SYSTEM_PROMPT)
            return {
                "text": result["text"],
                "model": result["model"],
                "source": "gateway",
                "agents_used": [],
            }
        except Exception as exc:
            mock = _mock_response(user_message, rag_chunks, "production")
            return {
                "text": mock["text"],
                "model": "mock",
                "source": "mock",
                "error": str(exc),
                "agents_used": [],
            }

    # ── Punto de entrada principal ────────────────────────────────────────────

    def run(
        self,
        user_message: str,
        shift_id: int | None = None,
        comment_id: int | None = None,
        category: str = "production",
        context_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Ejecuta el pipeline completo del orquestador.

        Parámetros:
            user_message  — Texto del operador
            shift_id      — ID del turno activo (para contexto)
            comment_id    — ID del comentario que originó la consulta (opcional)
            category      — Categoría del mensaje ('production'|'safety'|etc.)
            context_data  — Datos adicionales de sesión ya preparados

        Devuelve dict con:
            text         — Respuesta final para el operador
            model        — Modelo LLM usado en la síntesis
            source       — "gateway" | "mock"
            sources      — Lista de documentos RAG usados
            agents_used  — Lista de nombres de agentes activados
            reasoning    — Explicación del orquestador sobre la selección
            error        — Mensaje de error si lo hubo (opcional)
        """
        ctx = dict(context_data or {})
        if shift_id:
            ctx["shift_id"] = shift_id
        if comment_id:
            ctx["comment_id"] = comment_id
        ctx["category"] = category

        # Recuperar fragmentos RAG
        try:
            rag_chunks = get_context(user_message, top_k=4, db_path=self.db_path)
        except Exception as exc:
            logger.warning("Error en RAG retrieval: %s", exc)
            rag_chunks = []

        rag_sources = list({c["source_file"] for c in rag_chunks}) if rag_chunks else []

        api_key = _get_api_key()

        # Paso 1: Clasificación
        classification = self._classify(user_message, api_key)
        agent_names = classification["agents"]
        chain = classification["chain"]
        reasoning = classification["reasoning"]

        logger.info(
            "Orquestador: agentes seleccionados=%s chain=%s | %s",
            agent_names, chain, reasoning,
        )

        # Paso 2: Ejecución de agentes
        agent_outputs = self._run_agents(
            agent_names, chain, user_message, rag_chunks, ctx
        )

        # Paso 3: Síntesis
        final = self._synthesize(user_message, agent_outputs, rag_chunks, api_key)

        return {
            "text": final["text"],
            "model": final.get("model", "unknown"),
            "source": final.get("source", "mock"),
            "sources": rag_sources,
            "agents_used": final.get("agents_used", []),
            "reasoning": reasoning,
            "error": final.get("error"),
        }
