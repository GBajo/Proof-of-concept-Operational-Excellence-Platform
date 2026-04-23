"""
agents/doc_search_agent.py — Agente de búsqueda en documentación técnica.

Especializado en:
  - Búsqueda profunda en SOPs, manuales y documentación técnica indexada
  - Cita precisa de la fuente documental (nombre de archivo, sección)
  - Identificación de lagunas documentales (procedimientos no cubiertos)
  - Sugerencia de actualizaciones o creación de nuevos SOPs
  - Consultas de cumplimiento regulatorio (GMP, GDP)
"""

from __future__ import annotations

from typing import Any

from agents.base import Agent
from retriever import get_context


class DocSearchAgent(Agent):

    name = "doc_search"
    description = (
        "Especialista en documentación técnica farmacéutica (SOPs, manuales, procedimientos). "
        "Busca en la base de conocimiento indexada para encontrar procedimientos, "
        "especificaciones y normativas relevantes. Siempre cita el documento fuente "
        "y puede sugerir actualizaciones de SOPs cuando detecta lagunas."
    )
    required_data = ["knowledge_base_stats", "relevant_docs"]

    system_prompt = (
        "Eres un especialista en documentación técnica de fabricación farmacéutica "
        "con dominio profundo de normativas GMP (Good Manufacturing Practices) y "
        "sistemas de gestión documental. "
        "Detect the language of the user's message and ALWAYS respond in that same language. "
        "\n\nTus capacidades incluyen:\n"
        "- Localizar el procedimiento exacto en los SOPs y manuales disponibles\n"
        "- Citar textualmente los fragmentos más relevantes de la documentación\n"
        "- Identificar si un procedimiento está documentado o existe laguna documental\n"
        "- Sugerir actualizaciones de SOPs cuando el procedimiento existente es insuficiente\n"
        "- Indicar si una práctica cumple con los requisitos GMP/GDP\n"
        "- Proporcionar referencias cruzadas entre documentos relacionados\n"
        "\nReglas obligatorias:\n"
        "- SIEMPRE cita el nombre exacto del documento fuente entre corchetes: "
        "[NombreDocumento.pdf]\n"
        "- Si no encuentras documentación relevante, indícalo explícitamente: "
        "'No se ha encontrado documentación específica sobre este procedimiento.'\n"
        "- Si detectas que el SOP podría estar desactualizado o incompleto, "
        "indícalo como sugerencia de mejora\n"
        "- Nunca inventes contenido documental; solo usa lo que está en el contexto\n"
        "\nFormato: cita directa del fragmento más relevante, seguida de tu interpretación. "
        "Máximo 5 frases. Si hay laguna documental, sugiere el título del SOP que debería crearse."
    )

    # ── Recuperación de datos de BD ───────────────────────────────────────────

    def get_context(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        Enriquece el contexto con:
          - Estadísticas de la base de conocimiento (cuántos docs, tipos)
          - Búsqueda ampliada en knowledge_base (top_k=8, más que el default)
          - Lista de todos los documentos indexados (para detectar lagunas)
        """
        ctx = dict(context_data)

        try:
            conn = self._get_conn()

            # ── Estadísticas de la knowledge_base ─────────────────────────
            stats_row = conn.execute(
                """SELECT COUNT(DISTINCT source_file) AS doc_count,
                          COUNT(*) AS chunk_count,
                          GROUP_CONCAT(DISTINCT source_type) AS types
                   FROM knowledge_base""",
            ).fetchone()

            if stats_row and stats_row["doc_count"]:
                ctx["knowledge_base_stats"] = (
                    f"{stats_row['doc_count']} documentos indexados | "
                    f"{stats_row['chunk_count']} fragmentos | "
                    f"tipos: {stats_row['types']}"
                )

                # Lista de todos los documentos disponibles
                doc_rows = conn.execute(
                    """SELECT DISTINCT source_file, source_type,
                              COUNT(*) AS chunks
                       FROM knowledge_base
                       GROUP BY source_file
                       ORDER BY source_file""",
                ).fetchall()

                doc_list = [
                    f"  - {r['source_file']} ({r['source_type']}, {r['chunks']} fragmentos)"
                    for r in doc_rows
                ]
                ctx["available_documents"] = (
                    "Documentos disponibles en la base de conocimiento:\n"
                    + "\n".join(doc_list)
                )
            else:
                ctx["knowledge_base_stats"] = "Base de conocimiento vacía — no hay documentos indexados."

            self._close_conn_if_external(conn)

        except Exception as exc:
            ctx["doc_data_error"] = f"Error al leer knowledge_base: {exc}"

        return ctx

    def run(
        self,
        user_message: str,
        context_data: dict[str, Any] | None = None,
        rag_chunks: list[dict] | None = None,
        previous_outputs: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Sobreescribe run() para ampliar la búsqueda RAG antes de llamar al LLM.
        Usa top_k=8 (más exhaustivo que el default de 4) y también busca con
        variantes de las palabras clave para maximizar la cobertura documental.
        """
        ctx = self.get_context(context_data or {})

        # Búsqueda RAG ampliada (top_k=8)
        try:
            deep_chunks = get_context(user_message, top_k=8, db_path=self.db_path)
        except Exception:
            deep_chunks = rag_chunks or []

        # Si el orquestador ya pasó chunks, combinar sin duplicados
        if rag_chunks:
            seen_ids = {c.get("id") for c in deep_chunks}
            for c in rag_chunks:
                if c.get("id") not in seen_ids:
                    deep_chunks.append(c)
                    seen_ids.add(c.get("id"))

        prompt = self.build_prompt(user_message, ctx, deep_chunks, previous_outputs)

        from llm_client import _call_gateway, _get_api_key, _mock_response

        api_key = _get_api_key()
        if not api_key:
            mock = _mock_response(user_message, deep_chunks, "production")
            return {
                "agent": self.name,
                "response": mock["text"],
                "model": "mock",
                "source": "mock",
                "error": "Token de autenticación no disponible",
            }

        try:
            result = _call_gateway(prompt, api_key, system=self.system_prompt)
            return {
                "agent": self.name,
                "response": result["text"],
                "model": result["model"],
                "source": "gateway",
            }
        except Exception as exc:
            error_str = str(exc)
            mock = _mock_response(user_message, deep_chunks, "production")
            return {
                "agent": self.name,
                "response": mock["text"],
                "model": "mock",
                "source": "mock",
                "error": error_str[:120],
            }

    # ── Prompt de usuario personalizado ──────────────────────────────────────

    def build_prompt(
        self,
        user_message: str,
        context_data: dict[str, Any],
        rag_chunks: list[dict] | None = None,
        previous_outputs: list[dict] | None = None,
    ) -> str:
        parts: list[str] = []

        if context_data.get("knowledge_base_stats"):
            parts.append(f"## Base de conocimiento\n{context_data['knowledge_base_stats']}")

        if context_data.get("available_documents"):
            parts.append(context_data["available_documents"])

        if rag_chunks:
            parts.append(f"## Fragmentos más relevantes encontrados ({len(rag_chunks)} resultados)")
            for chunk in rag_chunks:
                source = chunk.get("source_file", "Desconocido")
                score = chunk.get("score", "?")
                text = chunk.get("chunk_text", "").strip()
                keywords = chunk.get("keywords_matched", [])
                kw_str = f" [coincidencias: {', '.join(keywords)}]" if keywords else ""
                parts.append(f"**[{source}]** (relevancia: {score}){kw_str}\n{text}")
        else:
            parts.append(
                "## Sin resultados documentales\n"
                "No se han encontrado fragmentos relevantes para esta consulta en la knowledge_base."
            )

        if previous_outputs:
            parts.append("## Contexto de otros agentes")
            for o in previous_outputs:
                parts.append(f"**{o.get('agent', 'Agente')}:** {o.get('response', '')}")

        if context_data.get("doc_data_error"):
            parts.append(f"## Aviso\n{context_data['doc_data_error']}")

        parts.append(
            f"## Consulta del operador\n{user_message.strip()}\n\n"
            "Busca en los fragmentos anteriores la información más relevante. "
            "Si no hay documentación, indícalo y sugiere el SOP que debería existir."
        )

        return "\n\n".join(parts)
