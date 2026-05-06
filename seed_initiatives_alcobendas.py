"""
seed_initiatives_alcobendas.py — 4 iniciativas de ejemplo para Alcobendas.

Uso:
    python seed_initiatives_alcobendas.py
    python seed_initiatives_alcobendas.py --force   # borra las existentes primero
"""
from __future__ import annotations

import sqlite3
import sys

DB_PATH = "site_alcobendas.db"
SITE_ID = "alcobendas"


def _ts(date: str, time: str = "08:00:00") -> str:
    return f"{date} {time}"


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """
    Migra improvement_initiatives + tablas dependientes al schema actual.

    SQLite 3.26+ actualiza automáticamente las FKs de otras tablas cuando
    se hace RENAME, lo que deja initiative_documents apuntando a "_ini_old"
    si no se maneja correctamente. Solución: reconstruir todas las tablas
    afectadas preservando los datos.
    """
    ddl_ini = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='improvement_initiatives'"
    ).fetchone()[0]

    # Detectar si alguna tabla dependiente tiene FK a un nombre corrupto
    ddl_docs = (conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='initiative_documents'"
    ).fetchone() or ("",))[0]

    needs_migration = "'planned'" in ddl_ini or '"_ini_old"' in ddl_docs

    if not needs_migration:
        # Solo añadir columnas que falten
        cols = {r[1] for r in conn.execute("PRAGMA table_info(improvement_initiatives)")}
        for col_sql in [
            "ALTER TABLE improvement_initiatives ADD COLUMN category TEXT NOT NULL DEFAULT 'Quality'",
            "ALTER TABLE improvement_initiatives ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE improvement_initiatives ADD COLUMN deleted_at TEXT",
            "ALTER TABLE improvement_initiatives ADD COLUMN deleted_by TEXT",
            "ALTER TABLE improvement_initiatives ADD COLUMN deletion_reason TEXT",
        ]:
            col_name = col_sql.split("ADD COLUMN ")[1].split()[0]
            if col_name not in cols:
                conn.execute(col_sql)
    else:
        # Guardar datos existentes antes de tocar nada
        conn.execute("PRAGMA foreign_keys = OFF")

        ini_rows = conn.execute(
            "SELECT * FROM improvement_initiatives"
        ).fetchall()
        ini_cols = [d[1] for d in conn.execute("PRAGMA table_info(improvement_initiatives)")]

        doc_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='initiative_documents'"
        ).fetchone()
        doc_rows = []
        if doc_table:
            doc_rows = conn.execute("SELECT * FROM initiative_documents").fetchall()

        # Borrar tablas dependientes primero
        conn.execute("DROP TABLE IF EXISTS initiative_documents")
        conn.execute("DROP TABLE IF EXISTS initiative_audit_log")
        conn.execute("DROP TABLE IF EXISTS _ini_old")
        conn.execute("DROP TABLE IF EXISTS improvement_initiatives")
        conn.commit()

        # Recrear improvement_initiatives con schema nuevo
        conn.execute("""
            CREATE TABLE improvement_initiatives (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id           TEXT NOT NULL,
                line_number       INTEGER CHECK(line_number BETWEEN 1 AND 20),
                title             TEXT NOT NULL,
                description       TEXT NOT NULL,
                methodology       TEXT NOT NULL DEFAULT 'Kaizen'
                                  CHECK(methodology IN ('A3','Kaizen','DMAIC','5Why','other')),
                status            TEXT NOT NULL DEFAULT 'No iniciado'
                                  CHECK(status IN ('No iniciado','En progreso','Terminado','Cancelado')),
                category          TEXT NOT NULL DEFAULT 'Quality'
                                  CHECK(category IN ('Safety','Quality','Delivery','Cost','People')),
                owner             TEXT NOT NULL,
                start_date        TEXT NOT NULL,
                target_date       TEXT NOT NULL,
                completion_date   TEXT,
                expected_benefit  TEXT,
                actual_benefit    TEXT,
                linked_problem_id INTEGER REFERENCES top_problems(id) ON DELETE SET NULL,
                deleted           INTEGER NOT NULL DEFAULT 0,
                deleted_at        TEXT,
                deleted_by        TEXT,
                deletion_reason   TEXT
            )
        """)

        # Reinsertar filas con mapeo de status
        status_map = {
            "planned":     "No iniciado",
            "in_progress": "En progreso",
            "completed":   "Terminado",
            "on_hold":     "Cancelado",
        }
        for row in ini_rows:
            d = dict(zip(ini_cols, row))
            d["status"] = status_map.get(d.get("status", ""), d.get("status", "No iniciado"))
            d.setdefault("category", "Quality")
            d.setdefault("deleted", 0)
            d.setdefault("deleted_at", None)
            d.setdefault("deleted_by", None)
            d.setdefault("deletion_reason", None)
            conn.execute(
                """INSERT INTO improvement_initiatives
                   (id, site_id, line_number, title, description, methodology,
                    status, category, owner, start_date, target_date,
                    completion_date, expected_benefit, actual_benefit,
                    linked_problem_id, deleted, deleted_at, deleted_by, deletion_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    d["id"], d["site_id"], d.get("line_number"), d["title"],
                    d["description"], d["methodology"], d["status"], d["category"],
                    d["owner"], d["start_date"], d["target_date"],
                    d.get("completion_date"), d.get("expected_benefit"),
                    d.get("actual_benefit"), d.get("linked_problem_id"),
                    d["deleted"], d["deleted_at"], d["deleted_by"], d["deletion_reason"],
                ),
            )

        # Recrear initiative_documents con FK correcta
        conn.execute("""
            CREATE TABLE initiative_documents (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                initiative_id INTEGER NOT NULL REFERENCES improvement_initiatives(id) ON DELETE CASCADE,
                document_type TEXT NOT NULL DEFAULT 'A3'
                              CHECK(document_type IN ('A3','project_charter','report','SOP_update')),
                title         TEXT NOT NULL,
                content_html  TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                author        TEXT NOT NULL
            )
        """)
        if doc_rows:
            conn.executemany(
                "INSERT INTO initiative_documents VALUES (?,?,?,?,?,?,?)",
                doc_rows,
            )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_site   ON improvement_initiatives(site_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_initiatives_status ON improvement_initiatives(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_init_docs_init     ON initiative_documents(initiative_id)")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        print("[ok] Tabla improvement_initiatives migrada al nuevo schema")

    # Siempre asegurar que las tablas dependientes existen
    conn.execute("""
        CREATE TABLE IF NOT EXISTS initiative_documents (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            initiative_id INTEGER NOT NULL REFERENCES improvement_initiatives(id) ON DELETE CASCADE,
            document_type TEXT NOT NULL DEFAULT 'A3'
                          CHECK(document_type IN ('A3','project_charter','report','SOP_update')),
            title         TEXT NOT NULL,
            content_html  TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            author        TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_init_docs_init ON initiative_documents(initiative_id)")

    # initiative_audit_log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS initiative_audit_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            initiative_id INTEGER NOT NULL REFERENCES improvement_initiatives(id) ON DELETE CASCADE,
            field_changed TEXT NOT NULL,
            old_value     TEXT,
            new_value     TEXT,
            changed_by    TEXT NOT NULL,
            changed_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def run(force: bool = False) -> None:
    # Migrar schema en una conexión separada; executescript() deja la conexión
    # en estado de autocommit que interfiere con las inserciones siguientes.
    with sqlite3.connect(DB_PATH) as _mig:
        _migrate_schema(_mig)

    # Reabrir conexión limpia para los inserts
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    if force:
        for title in [
            "Reducción de atascos en etiquetadora L1",
            "Mejora de tiempo de cambio de formato L2",
            "Reducción de rechazos por peso en llenadora L2",
            "Eliminación de microparadas en estuchadora L3",
        ]:
            conn.execute(
                "DELETE FROM improvement_initiatives WHERE site_id = ? AND title = ?",
                (SITE_ID, title),
            )
        conn.commit()

    # ── 1. Terminado — A3 — Etiquetadora L1 ───────────────────────────────────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id, line_number, title, description, methodology, status,
            category, owner, start_date, target_date, completion_date,
            expected_benefit, actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 1,
            "Reducción de atascos en etiquetadora L1",
            "Proyecto A3 para eliminar las paradas recurrentes por atasco en la etiquetadora "
            "automática HERMA 500 de la línea 1 (blísteres). Los atascos se producen cada 4-5 h "
            "de operación continua por acumulación de adhesivo en rodillos y desgaste de guías. "
            "Metodología A3 con análisis de causa raíz (5 Por Qué) y contramedidas verificadas.",
            "A3", "Terminado", "Delivery",
            "Isabel Torres",
            "2025-11-03", "2026-03-31", "2026-03-12",
            "Reducción del 40% en paradas por atasco (de 4,8/semana a ≤2,9/semana); "
            "recuperar ≥35 min/semana de producción perdida",
            "Atascos reducidos de 4,8/semana a 1,1/semana (−77%). "
            "Tiempo recuperado: 68 min/semana. OEE L1 +1,4 pp.",
        ),
    )
    ini1_id = cur.lastrowid

    # Audit log — ini 1
    for field, old_v, new_v, who, ts in [
        ("status",         None,          "No iniciado",  "Isabel Torres",  _ts("2025-10-28")),
        ("title",          None,          "Reducción de atascos en etiquetadora L1",
                                                          "Isabel Torres",  _ts("2025-10-28")),
        ("status",         "No iniciado", "En progreso",  "Isabel Torres",  _ts("2025-11-03")),
        ("status_comment", None,
         "Iniciamos análisis con datos de los últimos 3 meses. "
         "Frecuencia confirmada: 4,8 atascos/semana.",              "Isabel Torres",  _ts("2025-11-03")),
        ("status",         "En progreso", "Terminado",    "Ana Rodríguez",  _ts("2026-03-12")),
        ("status_comment", None,
         "Contramedidas validadas durante 8 semanas. Resultados sostenidos: "
         "1,1 atascos/semana. Cierre A3 aprobado por supervisora.",
                                                          "Ana Rodríguez",  _ts("2026-03-12")),
    ]:
        conn.execute(
            """INSERT INTO initiative_audit_log
               (initiative_id, field_changed, old_value, new_value, changed_by, changed_at)
               VALUES (?,?,?,?,?,?)""",
            (ini1_id, field, old_v, new_v, who, ts),
        )

    # Documento A3 — ini 1
    a3_html = """<article class="a3-document">
<h2>A3: Reducción de atascos en etiquetadora L1 — Alcobendas</h2>
<p><strong>Autor:</strong> Isabel Torres &nbsp;|&nbsp; <strong>Línea:</strong> L1 Blísteres &nbsp;|&nbsp; <strong>Inicio:</strong> 2025-11-03 &nbsp;|&nbsp; <strong>Cierre:</strong> 2026-03-12</p>
<hr>

<section><h3>1. Background / Contexto</h3>
<p>La etiquetadora automática HERMA 500 de la línea 1 genera paradas recurrentes por atasco
con una frecuencia media de <strong>4,8 paradas/semana</strong> y una duración media de
14 min por evento. Este defecto representa la mayor pérdida de OEE en L1 (~1,9 pp).</p>
</section>

<section><h3>2. Estado Actual (baseline)</h3>
<ul>
  <li>Frecuencia: 4,8 atascos/semana (L1)</li>
  <li>Duración media: 14 min/evento → <strong>67 min perdidos/semana</strong></li>
  <li>Patrón temporal: el 82% ocurre tras 4-5 h de funcionamiento continuo</li>
  <li>OEE L1 impactado en −1,9 pp por esta causa</li>
</ul>
</section>

<section><h3>3. Objetivo</h3>
<p>Reducir los atascos a <strong>≤2,9/semana (−40%)</strong> antes del 31 de marzo 2026,
recuperando ≥35 min/semana de producción.</p>
</section>

<section><h3>4. Análisis de Causa Raíz — 5 Por Qué</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
¿Por qué se producen los atascos?
  → Las etiquetas se pegan al pasar por las guías de papel
    ¿Por qué se pegan?
      → Adhesivo acumulado en rodillos de avance
        ¿Por qué se acumula adhesivo?
          → No existe limpieza preventiva durante la producción
            → CAUSA RAÍZ 1: Ausencia de protocolo de limpieza en operación

  → Además: guías de papel desgastadas (huelgo &gt;0,5 mm)
      ¿Por qué están desgastadas?
        → Intervalo de sustitución (6 meses) no ajustado al volumen real
          → CAUSA RAÍZ 2: Frecuencia de mantenimiento inadecuada
</pre>
</section>

<section><h3>5. Contramedidas</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Acción</th><th>Responsable</th><th>Fecha</th><th>Estado</th></tr>
<tr><td style="padding:0.4rem">Limpieza de rodillos cada 4 h (nuevo SOP-ETQ-003)</td><td>Pedro García</td><td>2025-11-20</td><td>✅ OK</td></tr>
<tr><td style="padding:0.4rem">Reducir sustitución de guías de 6 meses a 7 semanas</td><td>José Fernández</td><td>2025-12-05</td><td>✅ OK</td></tr>
<tr><td style="padding:0.4rem">Alarma preventiva en HMI a las 3,5 h de operación continua</td><td>José Fernández</td><td>2026-01-20</td><td>✅ OK</td></tr>
<tr><td style="padding:0.4rem">Stock mínimo de 2 juegos de guías de recambio en línea</td><td>José Fernández</td><td>2026-02-10</td><td>✅ OK</td></tr>
</table>
</section>

<section><h3>6. Plan de Implementación</h3>
<ul>
  <li><strong>Nov 3–28:</strong> Diagnóstico, medición de desgaste, análisis adhesivo residual</li>
  <li><strong>Dic 2025:</strong> Implementación limpieza preventiva + sustitución anticipada guías</li>
  <li><strong>Ene–Feb 2026:</strong> Instalación alarma HMI, seguimiento semanal de KPIs</li>
  <li><strong>Mar 2026:</strong> Validación 8 semanas, actualización SOP, cierre A3</li>
</ul>
</section>

<section><h3>7. Seguimiento de KPIs</h3>
<ul>
  <li>Atascos/semana L1 (objetivo ≤2,9 → resultado final: 1,1)</li>
  <li>Tiempo perdido/semana por atascos (objetivo ≤40 min → resultado: 15 min)</li>
  <li>OEE L1 mensual (objetivo +0,8 pp → resultado: +1,4 pp)</li>
</ul>
</section>

<section><h3>8. Resultados</h3>
<p style="background:#d4edda;padding:0.75rem;border-radius:4px">
✅ <strong>Proyecto cerrado el 12 de marzo 2026. Objetivo superado.</strong></p>
<ul>
  <li>Atascos/semana: 4,8 → <strong>1,1</strong> (reducción del 77% — objetivo era −40%)</li>
  <li>Tiempo perdido/semana: 67 min → <strong>15 min</strong></li>
  <li>Producción recuperada: <strong>68 min/semana (~1.360 unidades adicionales)</strong></li>
  <li>OEE L1: <strong>+1,4 pp</strong> (objetivo: +0,8 pp)</li>
</ul>
</section>
</article>"""

    conn.execute(
        """INSERT INTO initiative_documents
           (initiative_id, document_type, title, content_html, author)
           VALUES (?,?,?,?,?)""",
        (ini1_id, "A3",
         "A3: Reducción de atascos en etiquetadora L1",
         a3_html, "Isabel Torres"),
    )

    # ── 2. En progreso — Kaizen — Cambio de formato L2 ────────────────────────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id, line_number, title, description, methodology, status,
            category, owner, start_date, target_date,
            expected_benefit, actual_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 2,
            "Mejora de tiempo de cambio de formato L2",
            "Evento Kaizen para reducir el tiempo de cambio de formato en la línea 2 (viales). "
            "El tiempo actual es de 90 min de media, muy por encima del objetivo de 45 min. "
            "Se han identificado actividades internas convertibles a externas y la falta de "
            "kits de cambio preasignados como principales causas. El benchmark de referencia "
            "es Indianapolis (45 min con SMED consolidado).",
            "Kaizen", "En progreso", "Delivery",
            "Carlos Martínez",
            "2026-03-10", "2026-07-31",
            "Reducir tiempo de cambio de 90 min a ≤50 min; recuperar ≥4 h/semana de capacidad "
            "en L2 (3 cambios/semana × 40 min ahorrados)",
            None,
        ),
    )
    ini2_id = cur.lastrowid

    for field, old_v, new_v, who, ts in [
        ("status", None, "No iniciado",  "Carlos Martínez", _ts("2026-02-25")),
        ("title",  None, "Mejora de tiempo de cambio de formato L2",
                                         "Carlos Martínez", _ts("2026-02-25")),
        ("status", "No iniciado", "En progreso", "Carlos Martínez", _ts("2026-03-10")),
        ("status_comment", None,
         "Análisis de vídeo de 4 cambios completado. Tiempo medio confirmado: 90 min. "
         "Mapa de actividades internas/externas elaborado — 52% convertible a externo.",
                                         "Carlos Martínez", _ts("2026-03-10")),
        ("owner", "Carlos Martínez", "Javier Ruiz", "Isabel Torres", _ts("2026-04-02")),
    ]:
        conn.execute(
            """INSERT INTO initiative_audit_log
               (initiative_id, field_changed, old_value, new_value, changed_by, changed_at)
               VALUES (?,?,?,?,?,?)""",
            (ini2_id, field, old_v, new_v, who, ts),
        )

    # ── 3. No iniciado — DMAIC — Rechazos por peso L2 ─────────────────────────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id, line_number, title, description, methodology, status,
            category, owner, start_date, target_date,
            expected_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 2,
            "Reducción de rechazos por peso en llenadora L2",
            "Proyecto DMAIC para reducir el tasa de rechazo por peso fuera de especificación "
            "(±2%) en la llenadora de la línea 2 (viales). Tasa actual: 1,8% (objetivo: ≤0,5%). "
            "Causa sospechada: deriva térmica del sensor de la balanza tras 4 h de operación "
            "continua. Se abrirá en junio 2026 tras liberar recursos del proyecto Kaizen L2.",
            "DMAIC", "No iniciado", "Quality",
            "Ana Rodríguez",
            "2026-06-02", "2026-11-28",
            "Reducir tasa de rechazo por peso de 1,8% a ≤0,5% en L2; "
            "ahorro estimado de ≥9.000 unidades/mes y reducción de coste de no calidad",
        ),
    )
    ini3_id = cur.lastrowid

    for field, old_v, new_v, who, ts in [
        ("status", None, "No iniciado", "Ana Rodríguez", _ts("2026-05-06")),
        ("title",  None, "Reducción de rechazos por peso en llenadora L2",
                                        "Ana Rodríguez", _ts("2026-05-06")),
        ("description", None,
         "Scope ampliado: incluir análisis del proveedor de granulado (variabilidad densidad ±2,1%).",
                                        "Ana Rodríguez", _ts("2026-05-06", "11:30:00")),
    ]:
        conn.execute(
            """INSERT INTO initiative_audit_log
               (initiative_id, field_changed, old_value, new_value, changed_by, changed_at)
               VALUES (?,?,?,?,?,?)""",
            (ini3_id, field, old_v, new_v, who, ts),
        )

    # ── 4. Cancelado — Microparadas estuchadora L3 ────────────────────────────
    cur = conn.execute(
        """INSERT INTO improvement_initiatives
           (site_id, line_number, title, description, methodology, status,
            category, owner, start_date, target_date,
            expected_benefit)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            SITE_ID, 3,
            "Eliminación de microparadas en estuchadora L3",
            "Proyecto para identificar y eliminar las microparadas recurrentes en la estuchadora "
            "de la línea 3 (sobres). Frecuencia media: 12 microparadas/turno con duración "
            "<3 min cada una. Impacto estimado en rendimiento: −3,2%. Iniciativa cancelada "
            "porque el equipo fue sustituido por un nuevo modelo (IMA Carton 3200) en el "
            "plan de inversiones aprobado para Q2 2026.",
            "other", "Cancelado", "Delivery",
            "Raúl Moreno",
            "2026-01-20", "2026-05-30",
            "Reducir microparadas de 12/turno a ≤3/turno; mejora de rendimiento L3 +3 pp",
        ),
    )
    ini4_id = cur.lastrowid

    for field, old_v, new_v, who, ts in [
        ("status", None, "No iniciado", "Raúl Moreno",    _ts("2026-01-15")),
        ("title",  None, "Eliminación de microparadas en estuchadora L3",
                                        "Raúl Moreno",    _ts("2026-01-15")),
        ("status", "No iniciado", "Cancelado", "Isabel Torres", _ts("2026-03-18")),
        ("status_comment", None,
         "Iniciativa cancelada. Motivo: la estuchadora L3 será reemplazada por el nuevo "
         "modelo IMA Carton 3200 (plan de inversiones Q2-2026 aprobado en comité del "
         "15/03/2026). No procede invertir tiempo en mejorar el equipo a reemplazar.",
                                        "Isabel Torres", _ts("2026-03-18")),
    ]:
        conn.execute(
            """INSERT INTO initiative_audit_log
               (initiative_id, field_changed, old_value, new_value, changed_by, changed_at)
               VALUES (?,?,?,?,?,?)""",
            (ini4_id, field, old_v, new_v, who, ts),
        )

    conn.commit()
    conn.close()

    print(f"[ok] Iniciativas insertadas en {DB_PATH}:")
    print(f"  #{ini1_id:3d} Terminado   — Reducción de atascos en etiquetadora L1")
    print(f"  #{ini2_id:3d} En progreso — Mejora de tiempo de cambio de formato L2")
    print(f"  #{ini3_id:3d} No iniciado — Reducción de rechazos por peso en llenadora L2")
    print(f"  #{ini4_id:3d} Cancelado   — Eliminación de microparadas en estuchadora L3")


if __name__ == "__main__":
    force = "--force" in sys.argv
    run(force=force)
