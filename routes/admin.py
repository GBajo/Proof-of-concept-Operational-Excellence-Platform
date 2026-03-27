from flask import Blueprint, render_template, redirect, url_for, jsonify
from database import get_db
from pathlib import Path
import os

bp = Blueprint("admin", __name__)

DOCS_DIR = Path(__file__).parent.parent / "docs"
SUPPORTED_EXT = {".pdf", ".docx", ".xlsx", ".xls"}


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


@bp.get("/admin/docs")
def admin_docs():
    db = get_db()
    indexed = _get_index_stats(db)
    indexed_names = {r["source_file"] for r in indexed}
    disk_files = _get_docs_on_disk()

    # Marcar qué archivos están indexados
    for f in disk_files:
        f["indexed"] = f["name"] in indexed_names

    total_chunks = db.execute(
        "SELECT COUNT(*) FROM knowledge_base"
    ).fetchone()[0]

    return render_template(
        "admin/docs.html",
        indexed=indexed,
        disk_files=disk_files,
        total_chunks=total_chunks,
        docs_dir=str(DOCS_DIR.resolve()),
    )


@bp.post("/admin/docs/reindex")
def admin_reindex():
    """Re-indexa todos los documentos de docs/ (forzando actualización)."""
    from ingest import run_ingest
    import sys
    db_path = os.environ.get("DATABASE_PATH", "packline.db")
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
    db_path = os.environ.get("DATABASE_PATH", "packline.db")
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
