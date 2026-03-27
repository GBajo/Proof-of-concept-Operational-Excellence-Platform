"""
retriever.py — Búsqueda de contexto por palabras clave en knowledge_base.

Uso:
    from retriever import get_context

    fragments = get_context("la línea lleva parada 20 minutos por atasco en troquelado")
    for f in fragments:
        print(f["source_file"], f["score"], f["chunk_text"][:200])
"""

from __future__ import annotations

import os
import re
import sqlite3

DB_PATH = os.environ.get("DATABASE_PATH", "opex.db")

# ── Stopwords en español ──────────────────────────────────────
STOPWORDS: set[str] = {
    "a", "al", "algo", "algunas", "algunos", "ante", "antes", "como",
    "con", "contra", "cual", "cuando", "de", "del", "desde", "donde",
    "durante", "e", "el", "ella", "ellas", "ellos", "en", "entre",
    "era", "es", "esa", "esas", "ese", "eso", "esos", "esta", "estas",
    "este", "esto", "estos", "está", "estaba", "estaban", "estamos",
    "están", "estar", "este", "fue", "fueron", "fui", "ha", "han",
    "has", "hasta", "hay", "he", "la", "las", "le", "les", "lo",
    "los", "me", "mi", "mis", "muy", "más", "ni", "no", "nos",
    "nosotros", "o", "os", "para", "pero", "por", "que", "se",
    "si", "sin", "sobre", "su", "sus", "también", "tan", "te",
    "tengo", "ti", "tiene", "tienen", "todo", "todos", "tu", "tus",
    "un", "una", "unas", "unos", "ya", "yo", "él", "es", "era",
    "ser", "sido", "siendo", "está", "estoy", "han", "hay",
}


def extract_keywords(text: str, min_len: int = 3) -> list[str]:
    """
    Extrae palabras clave de un texto:
    - Convierte a minúsculas
    - Elimina puntuación y caracteres especiales
    - Elimina stopwords en español
    - Elimina palabras cortas (< min_len caracteres)
    - Devuelve lista de palabras únicas preservando orden de aparición
    """
    text = text.lower()
    # Normalizar tildes para mejorar coincidencias
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
    }
    for accented, plain in replacements.items():
        text = text.replace(accented, plain)

    words = re.findall(r"[a-z0-9]+", text)

    seen: set[str] = set()
    keywords: list[str] = []
    for w in words:
        if w not in seen and w not in STOPWORDS and len(w) >= min_len:
            seen.add(w)
            keywords.append(w)

    return keywords


def get_context(
    query: str,
    top_k: int = 5,
    db_path: str = DB_PATH,
    min_score: int = 1,
) -> list[dict]:
    """
    Busca fragmentos relevantes en knowledge_base para el texto dado.

    Parámetros:
        query     — Texto del comentario del operador
        top_k     — Número máximo de fragmentos a devolver (3–5 recomendado)
        db_path   — Ruta a la BD SQLite
        min_score — Puntuación mínima para incluir un fragmento (coincidencias)

    Devuelve lista de dicts con:
        id, source_file, source_type, chunk_index, chunk_text, score
    Ordenada de mayor a menor relevancia.
    """
    keywords = extract_keywords(query)
    if not keywords:
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Verificar que la tabla existe
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_base'"
    ).fetchone()
    if not exists:
        conn.close()
        return []

    # Construir condición LIKE para cada palabra clave
    # Recuperamos todos los fragmentos que contengan AL MENOS una keyword
    conditions = " OR ".join(
        "LOWER(chunk_text) LIKE ?" for _ in keywords
    )
    params = [f"%{kw}%" for kw in keywords]

    rows = conn.execute(
        f"""
        SELECT id, source_file, source_type, chunk_index, chunk_text
        FROM knowledge_base
        WHERE {conditions}
        """,
        params,
    ).fetchall()
    conn.close()

    # Puntuar cada fragmento: contar cuántas keywords aparecen en él
    scored: list[tuple[int, dict]] = []
    for row in rows:
        text_lower = row["chunk_text"].lower()
        # Normalizar tildes en el texto del fragmento también
        replacements = {
            "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
        }
        for accented, plain in replacements.items():
            text_lower = text_lower.replace(accented, plain)

        score = sum(1 for kw in keywords if kw in text_lower)
        if score >= min_score:
            scored.append((score, dict(row)))

    # Ordenar por puntuación descendente, luego por chunk_index ascendente
    scored.sort(key=lambda x: (-x[0], x[1]["chunk_index"]))

    results = []
    for score, fragment in scored[:top_k]:
        fragment["score"] = score
        fragment["keywords_matched"] = [
            kw for kw in keywords
            if kw in fragment["chunk_text"].lower()
        ]
        results.append(fragment)

    return results


def format_context_for_llm(fragments: list[dict], max_chars: int = 3000) -> str:
    """
    Formatea los fragmentos recuperados como contexto para enviar al LLM.
    Incluye la fuente de cada fragmento para que el LLM pueda citarla.
    """
    if not fragments:
        return ""

    parts: list[str] = []
    total = 0
    for f in fragments:
        source = f["source_file"]
        text   = f["chunk_text"].strip()
        block  = f"[Fuente: {source}]\n{text}"
        if total + len(block) > max_chars:
            # Truncar el último bloque si no cabe completo
            remaining = max_chars - total
            if remaining > 100:
                block = block[:remaining] + "…"
                parts.append(block)
            break
        parts.append(block)
        total += len(block)

    return "\n\n---\n\n".join(parts)


# ── CLI de prueba ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "la línea lleva parada 20 minutos por atasco en troquelado"
    )

    print(f"\nConsulta: «{query}»")
    keywords = extract_keywords(query)
    print(f"Keywords: {keywords}\n")

    fragments = get_context(query, top_k=5)

    if not fragments:
        print("Sin resultados. Verifica que knowledge_base tiene datos (python ingest.py).")
    else:
        print(f"{len(fragments)} fragmento(s) encontrado(s):\n")
        for i, f in enumerate(fragments, 1):
            print(f"── {i}. {f['source_file']} (score: {f['score']}, "
                  f"keywords: {f['keywords_matched']})")
            print(f"   {f['chunk_text'][:300].strip()}…")
            print()

        print("── Contexto formateado para LLM ──")
        print(format_context_for_llm(fragments, max_chars=1000))
