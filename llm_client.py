"""
llm_client.py — Cliente para el LLM Gateway de Lilly (compatible Anthropic API).

Uso:
    from llm_client import ask_assistant

    reply = ask_assistant(
        comment_text="La línea lleva 20 min parada por atasco en troquelado",
        context_chunks=[...],   # lista de dicts de retriever.get_context()
        category="maintenance",
    )
    print(reply["text"])
    print(reply["source"])   # "gateway" | "mock"
"""

from __future__ import annotations

import os
import subprocess
import json
import time
from typing import Optional

# ── Configuración del gateway ─────────────────────────────────
GATEWAY_BASE_URL = os.environ.get(
    "ANTHROPIC_BASE_URL",
    "https://lilly-code-server.api.gateway.llm.lilly.com",
)
MODEL = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "sonnet-latest")
TIMEOUT = 30          # segundos
MAX_TOKENS = 1024

SYSTEM_PROMPT = (
    "Eres un asistente técnico experto en líneas de empaquetado farmacéutico. "
    "Responde siempre en español. "
    "Basa tus respuestas en la documentación proporcionada como contexto. "
    "Si la documentación no cubre el problema, indícalo claramente y da "
    "recomendaciones generales basadas en buenas prácticas. "
    "Siempre cita el nombre del documento fuente entre corchetes, "
    "por ejemplo: [SOP-LIN-001_Limpieza_Linea.docx]. "
    "Sé conciso: máximo 4-5 frases por respuesta."
)

CATEGORY_LABELS = {
    "safety":      "Seguridad",
    "quality":     "Calidad",
    "production":  "Producción",
    "maintenance": "Mantenimiento",
}

# ── Obtención del token de autenticación ─────────────────────

def _get_api_key() -> Optional[str]:
    """
    Obtiene el token de autenticación con este orden de prioridad:
    1. Variable de entorno ANTHROPIC_API_KEY
    2. Comando helper de Lilly Code ('lilly-code token')
    3. None → activar modo mock
    """
    # 1. Variable de entorno
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key

    # 2. Helper de Lilly Code
    try:
        result = subprocess.run(
            ["lilly-code", "token"],
            capture_output=True, text=True, timeout=10,
        )
        token = result.stdout.strip()
        if token:
            return token
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return None


# ── Construcción del prompt ───────────────────────────────────

def _build_user_message(
    comment_text: str,
    context_chunks: list[dict],
    category: str,
) -> str:
    cat_label = CATEGORY_LABELS.get(category, category.capitalize())
    parts: list[str] = []

    if context_chunks:
        parts.append("## Documentación de referencia\n")
        for chunk in context_chunks:
            source = chunk.get("source_file", "Desconocido")
            text   = chunk.get("chunk_text", "").strip()
            parts.append(f"[Fuente: {source}]\n{text}")
        parts.append("")

    parts.append(f"## Comentario del operador [{cat_label}]")
    parts.append(comment_text.strip())
    parts.append("")
    parts.append("Por favor, analiza el comentario anterior y proporciona "
                 "orientación técnica basada en la documentación.")

    return "\n\n".join(parts)


# ── Llamada al gateway ────────────────────────────────────────

def _call_gateway(user_message: str, api_key: str) -> dict:
    """
    Llama al LLM Gateway usando la librería anthropic con base_url personalizada.
    Devuelve dict con 'text' y 'model'.
    Lanza excepciones en caso de error para que ask_assistant las gestione.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "Instala la librería anthropic:  pip install anthropic"
        )

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url=GATEWAY_BASE_URL,
        timeout=TIMEOUT,
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    text = message.content[0].text if message.content else ""
    return {"text": text, "model": message.model}


# ── Respuesta mock ────────────────────────────────────────────

def _mock_response(
    comment_text: str,
    context_chunks: list[dict],
    category: str,
) -> dict:
    """
    Respuesta simulada cuando el gateway no está disponible.
    Devuelve una respuesta genérica adaptada a la categoría.
    """
    cat_label = CATEGORY_LABELS.get(category, category.capitalize())

    if context_chunks:
        source = context_chunks[0].get("source_file", "documentación interna")
        snippet = context_chunks[0].get("chunk_text", "")[:200].strip()
        mock_text = (
            f"[MOCK] Basándome en [{source}]: {snippet}… "
            f"Para el incidente de {cat_label.lower()} reportado, "
            "se recomienda seguir el procedimiento estándar indicado en la documentación. "
            "Contacta con el supervisor si el problema persiste. "
            "(Respuesta simulada — gateway no disponible)"
        )
    else:
        mock_text = (
            f"[MOCK] Comentario de {cat_label.lower()} recibido. "
            "No se encontraron documentos indexados para proporcionar contexto específico. "
            "Consulta el SOP correspondiente o contacta con el supervisor. "
            "(Respuesta simulada — gateway no disponible)"
        )

    return {"text": mock_text, "model": "mock", "source": "mock"}


# ── Función principal pública ─────────────────────────────────

def ask_assistant(
    comment_text: str,
    context_chunks: list[dict],
    category: str = "production",
    force_mock: bool = False,
) -> dict:
    """
    Envía el comentario del operador al LLM con el contexto recuperado.

    Parámetros:
        comment_text    — Texto del comentario o pregunta del operario
        context_chunks  — Lista de fragmentos de retriever.get_context()
        category        — Categoría: 'safety'|'quality'|'production'|'maintenance'
        force_mock      — Si True, omite el gateway y devuelve respuesta simulada

    Devuelve dict con:
        text    — Texto de la respuesta
        model   — Modelo usado o 'mock'
        source  — 'gateway' | 'mock'
        error   — Mensaje de error si lo hubo (solo presente en caso de fallo)
    """
    if force_mock:
        return _mock_response(comment_text, context_chunks, category)

    api_key = _get_api_key()
    if not api_key:
        result = _mock_response(comment_text, context_chunks, category)
        result["error"] = "Token de autenticación no disponible"
        return result

    user_message = _build_user_message(comment_text, context_chunks, category)

    try:
        result = _call_gateway(user_message, api_key)
        result["source"] = "gateway"
        return result

    except Exception as e:
        error_str = str(e)

        # Clasificar el tipo de error para el log
        if "401" in error_str or "authentication" in error_str.lower():
            error_msg = "Error de autenticación con el gateway (401)"
        elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
            error_msg = f"Timeout al conectar con el gateway ({TIMEOUT}s)"
        elif "500" in error_str or "502" in error_str or "503" in error_str:
            error_msg = "El gateway no está disponible temporalmente (5xx)"
        elif "connect" in error_str.lower() or "network" in error_str.lower():
            error_msg = "Error de red — sin conexión al gateway"
        else:
            error_msg = f"Error inesperado: {error_str[:120]}"

        result = _mock_response(comment_text, context_chunks, category)
        result["error"] = error_msg
        return result


# ── CLI de prueba ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from retriever import get_context, format_context_for_llm

    comment = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "La línea lleva 20 minutos parada, hay un atasco en la zona de troquelado"
    )

    print(f"\nComentario: «{comment}»")
    print("Buscando contexto en knowledge_base…")

    chunks = get_context(comment, top_k=3)
    print(f"  → {len(chunks)} fragmento(s) encontrado(s)\n")

    print("Consultando asistente…")
    response = ask_assistant(
        comment_text=comment,
        context_chunks=chunks,
        category="maintenance",
    )

    source = response.get("source", "?")
    model  = response.get("model", "?")
    print(f"\n[{source.upper()} / {model}]\n")
    print(response["text"])

    if "error" in response:
        print(f"\n⚠ Aviso: {response['error']}")
