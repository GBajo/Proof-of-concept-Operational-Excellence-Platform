from flask import Blueprint, render_template, redirect, url_for, jsonify, request, g
from database import get_db
from site_aggregator import SITES, DEFAULT_SITE
from pathlib import Path
import os

bp = Blueprint("admin", __name__)

DOCS_DIR = Path(__file__).parent.parent / "docs"
SUPPORTED_EXT = {".pdf", ".docx", ".xlsx", ".xls"}
MAX_UPLOAD_MB = 50
# Extensiones ejecutables/peligrosas que nunca se aceptan aunque pasen el SUPPORTED_EXT check
_BLOCKED_EXT = {".py", ".sh", ".bat", ".exe", ".js", ".php", ".rb", ".pl", ".ps1"}


def _current_db_path() -> str:
    """Devuelve la ruta al DB del site activo en la solicitud actual."""
    site_id = getattr(g, "current_site", DEFAULT_SITE)
    return SITES.get(site_id, SITES[DEFAULT_SITE])["db_path"]


def _get_index_stats(db) -> list[dict]:
    """Devuelve estadísticas de indexación agrupadas por archivo."""
    rows = db.execute("""
        SELECT source_file, source_type,
               COUNT(*) AS chunks,
               MAX(indexed_at) AS last_indexed
        FROM knowledge_base
        GROUP BY source_file
        ORDER BY last_indexed DESC
    """).fetchall()
    return [dict(r) for r in rows]


def _get_docs_on_disk() -> list[dict]:
    """Lista los archivos disponibles en docs/."""
    DOCS_DIR.mkdir(exist_ok=True)
    files = []
    for f in sorted(DOCS_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXT:
            files.append({
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "ext": f.suffix.lower().lstrip("."),
            })
    return files


def _get_assistant_stats(db) -> dict:
    """Estadísticas del asistente: consultas hoy y % útil."""
    queries_today = db.execute(
        "SELECT COUNT(*) FROM assistant_suggestions "
        "WHERE date(created_at) = date('now')"
    ).fetchone()[0]

    total_feedback = db.execute(
        "SELECT COUNT(*) FROM assistant_suggestions "
        "WHERE feedback IS NOT NULL"
    ).fetchone()[0]

    useful = db.execute(
        "SELECT COUNT(*) FROM assistant_suggestions "
        "WHERE feedback = 'useful'"
    ).fetchone()[0]

    useful_pct = round(useful / total_feedback * 100) if total_feedback > 0 else None

    return {
        "queries_today": queries_today,
        "useful_pct": useful_pct,
        "total_feedback": total_feedback,
    }


@bp.get("/admin/docs")
def admin_docs():
    db = get_db()
    indexed = _get_index_stats(db)
    indexed_names = {r["source_file"] for r in indexed}
    disk_files = _get_docs_on_disk()

    # Marcar qué archivos están indexados y cuántos fragmentos tienen
    indexed_map = {r["source_file"]: r for r in indexed}
    for f in disk_files:
        f["indexed"] = f["name"] in indexed_names
        f["chunks"] = indexed_map[f["name"]]["chunks"] if f["name"] in indexed_map else 0
        f["last_indexed"] = indexed_map[f["name"]]["last_indexed"] if f["name"] in indexed_map else None

    # URLs indexadas (source_type = 'url')
    url_sources = [r for r in indexed if r["source_type"] == "url"]

    total_chunks = db.execute(
        "SELECT COUNT(*) FROM knowledge_base"
    ).fetchone()[0]

    assistant_stats = _get_assistant_stats(db)

    return render_template(
        "admin/docs.html",
        indexed=indexed,
        disk_files=disk_files,
        url_sources=url_sources,
        total_chunks=total_chunks,
        docs_dir=str(DOCS_DIR.resolve()),
        assistant_stats=assistant_stats,
    )


@bp.post("/admin/docs/upload")
def admin_upload():
    """Recibe un archivo vía multipart, lo guarda en docs/ y lo indexa."""
    if "file" not in request.files:
        return jsonify({"ok": False, "message": "No se recibió ningún archivo."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "message": "Nombre de archivo vacío."}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in SUPPORTED_EXT or ext in _BLOCKED_EXT:
        return jsonify({
            "ok": False,
            "message": f"Formato no soportado: {ext}. Usa PDF, DOCX o XLSX."
        }), 400

    # Limitar tamaño
    f.seek(0, 2)
    size_mb = f.tell() / (1024 * 1024)
    f.seek(0)
    if size_mb > MAX_UPLOAD_MB:
        return jsonify({
            "ok": False,
            "message": f"Archivo demasiado grande ({size_mb:.1f} MB). Máximo {MAX_UPLOAD_MB} MB."
        }), 400

    DOCS_DIR.mkdir(exist_ok=True)
    save_path = DOCS_DIR / Path(f.filename).name
    f.save(str(save_path))

    # Indexar inmediatamente
    from ingest import index_file, get_conn
    db_path = _current_db_path()
    try:
        conn = get_conn(db_path)
        result = index_file(save_path, conn, force=True)
        conn.close()
        return jsonify({
            "ok": True,
            "message": f"'{save_path.name}' subido e indexado ({result.get('chunks', 0)} fragmentos).",
            "filename": save_path.name,
            "chunks": result.get("chunks", 0),
        })
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@bp.post("/admin/docs/index-url")
def admin_index_url():
    """Indexa una URL."""
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "message": "URL vacía."}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"ok": False, "message": "La URL debe empezar por http:// o https://"}), 400

    from ingest import index_url, get_conn
    db_path = _current_db_path()
    try:
        conn = get_conn(db_path)
        result = index_url(url, conn, force=True)
        conn.close()
        if result["status"] == "error":
            return jsonify({"ok": False, "message": result.get("error", "Error al indexar URL.")}), 500
        return jsonify({
            "ok": True,
            "message": f"URL indexada ({result.get('chunks', 0)} fragmentos).",
            "url": url,
            "chunks": result.get("chunks", 0),
        })
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@bp.delete("/admin/docs/delete/<path:filename>")
def admin_delete(filename: str):
    """Elimina un documento (fragmentos KB + archivo en disco si existe)."""
    db_path = _current_db_path()
    from ingest import get_conn, delete_source
    try:
        conn = get_conn(db_path)
        delete_source(conn, filename)
        conn.close()
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500

    # Eliminar del disco sólo si es un archivo local (no URL)
    if not filename.startswith(("http://", "https://")):
        disk_path = DOCS_DIR / filename
        if disk_path.exists():
            disk_path.unlink()

    return jsonify({"ok": True, "message": f"'{filename}' eliminado."})


@bp.post("/admin/docs/reindex")
def admin_reindex():
    """Re-indexa todos los documentos de docs/ (forzando actualización)."""
    from ingest import run_ingest
    db_path = _current_db_path()
    try:
        summary = run_ingest(
            docs_dir=DOCS_DIR,
            db_path=db_path,
            force=True,
        )
        return jsonify({
            "ok": True,
            "message": (
                f"{summary['ok']} archivo(s) indexado(s), "
                f"{summary['total_chunks']} fragmentos totales."
            ),
            "summary": summary,
        })
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@bp.post("/admin/docs/reindex/<path:filename>")
def admin_reindex_file(filename: str):
    """Re-indexa un único archivo."""
    from ingest import index_file, get_conn
    db_path = _current_db_path()
    path = DOCS_DIR / filename
    if not path.exists():
        return jsonify({"ok": False, "message": "Archivo no encontrado"}), 404
    try:
        conn = get_conn(db_path)
        result = index_file(path, conn, force=True)
        conn.close()
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@bp.post("/admin/docs/clear")
def admin_clear():
    """Vacía completamente la base de conocimiento."""
    db = get_db()
    db.execute("DELETE FROM knowledge_base")
    db.commit()
    return jsonify({"ok": True, "message": "Base de conocimiento vaciada."})
