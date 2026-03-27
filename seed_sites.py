"""
seed_sites.py — Genera datos de ejemplo realistas para las 4 plantas.

Uso:
    python seed_sites.py              # siembra todas las plantas
    python seed_sites.py alcobendas   # siembra solo una
"""
from __future__ import annotations

import os
import random
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta

from site_aggregator import SITES, DEFAULT_SITE


def _safe_print(msg: str) -> None:
    """Print ignoring encoding errors (Windows console compatibility)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))

# ── Pasos de empaquetado farmacéutico (igual que vsm.py) ─────────────────────

PHARMA_STEPS = [
    (1,  "Recepción granel", "non-value-add", 45.0, 15.0),
    (2,  "Alimentación",     "value-add",      8.0, 20.0),
    (3,  "Llenado",          "value-add",      6.0, 45.0),
    (4,  "Pesaje",           "value-add",      4.0, 15.0),
    (5,  "Cierre",           "value-add",      5.0, 30.0),
    (6,  "Etiquetado",       "value-add",      4.5, 25.0),
    (7,  "Serialización",    "value-add",      3.0, 20.0),
    (8,  "Estuchado",        "value-add",      6.5, 35.0),
    (9,  "Encajado",         "value-add",     12.0, 20.0),
    (10, "Paletizado",       "non-value-add", 18.0, 10.0),
]

# ── Configuración por planta ──────────────────────────────────────────────────
# Valores clave para alcanzar los OEEs objetivo:
# OEE = Avail × Perf × Qual
# Alcobendas 82%  → A=92% P=91% Q=98%
# Indianapolis 88%→ A=95% P=94% Q=98.5% (SMED leader)
# Fegersheim 79%  → A=88% P=90% Q=99.5%
# Sesto 85%       → A=93% P=92% Q=99%

SITE_CFG: dict[str, dict] = {
    "alcobendas": {
        "operators": [
            ("Pedro García",    "operator",    "ALB-001"),
            ("María López",     "operator",    "ALB-002"),
            ("Carlos Martínez", "operator",    "ALB-003"),
            ("Ana Rodríguez",   "quality",     "ALB-004"),
            ("José Fernández",  "maintenance", "ALB-005"),
            ("Isabel Torres",   "supervisor",  "ALB-006"),
        ],
        "downtime_range":  (22, 52),   # min/turno
        "speed_range":     (960, 1175),
        "reject_rate":     0.020,
        "co_range":        (38, 58),   # min changeover
        "comments": {
            "production": [
                "Atasco en transportador de blísteres, solucionado en {min} min",
                "Ajuste de velocidad de línea completado sin incidencias",
                "Cambio de lote iniciado sin anomalías",
                "Velocidad reducida por acumulación en estuchado",
                "Turno con buen ritmo de producción, sin paradas mayores",
                "Recuperación tras micro-parada en selladora",
            ],
            "quality": [
                "Calibración de balanza completada, dentro de especificación",
                "Control de peso: 2 unidades fuera de rango, rechazadas",
                "Verificación de serialización correcta al 100%",
                "Revisión de etiquetas: sin anomalías detectadas",
                "Control de hermeticidad conforme",
                "Registro de temperatura de sellado dentro de rango",
            ],
            "maintenance": [
                "Lubricación de cadena transportadora realizada",
                "Ajuste de sensor de nivel de llenado",
                "Fallo intermitente en selladora corregido",
                "Cambio de O-ring en bomba de llenado",
                "Mantenimiento preventivo de etiquetadora completado",
                "Tensión de correa ajustada en encajadora",
            ],
            "safety": [
                "Revisión de EPIs completada, todo conforme",
                "Zona de trabajo limpia y ordenada — 5S OK",
                "Derrame menor en zona de llenado: limpiado correctamente",
            ],
        },
        "co_comment": "Cambio de formato completado en {min} minutos",
    },

    "indianapolis": {
        "operators": [
            ("John Smith",      "operator",    "IND-001"),
            ("Emily Johnson",   "operator",    "IND-002"),
            ("Michael Davis",   "operator",    "IND-003"),
            ("Sarah Wilson",    "quality",     "IND-004"),
            ("Robert Brown",    "maintenance", "IND-005"),
            ("Jennifer Taylor", "supervisor",  "IND-006"),
        ],
        "downtime_range":  (10, 30),   # Best performer: low downtime
        "speed_range":     (1060, 1200),
        "reject_rate":     0.015,
        "co_range":        (16, 28),   # SMED leader: short changeovers
        "comments": {
            "production": [
                "SMED changeover completed in {min}min — within target",
                "Color-coded changeover kits used, smooth transition",
                "Line running at nominal speed, no issues",
                "Kaizen improvement applied to labeling station today",
                "Visual management board updated, all targets green",
                "Production ahead of schedule — excellent shift",
                "Pre-staged changeover kit ready for next format",
            ],
            "quality": [
                "Weight check within specification limits — zero rejects",
                "Serialization verification passed 100%",
                "SOP v2.3 followed for all inline QC checks",
                "Hermetic seal test: all units passed",
                "Label inspection: no anomalies found",
                "Right First Time 98.5% this shift",
            ],
            "maintenance": [
                "Preventive maintenance completed per schedule",
                "Conveyor belt tension adjusted proactively",
                "Filler nozzle cleaned, no leaks detected",
                "Predictive maintenance alert resolved — bearing replaced",
            ],
            "safety": [
                "Safety walkthrough completed, all clear",
                "5S audit passed — area score 4.9/5",
                "PPE check: all operators compliant",
            ],
        },
        "co_comment": "SMED changeover: {min}min — color-coded kit, SOP v2.3",
    },

    "fegersheim": {
        "operators": [
            ("Pierre Dupont",     "operator",    "FEG-001"),
            ("Marie Martin",      "operator",    "FEG-002"),
            ("Jean-Paul Bernard", "operator",    "FEG-003"),
            ("Sophie Lefebvre",   "quality",     "FEG-004"),
            ("François Moreau",   "maintenance", "FEG-005"),
            ("Claire Rousseau",   "supervisor",  "FEG-006"),
        ],
        "downtime_range":  (42, 78),   # Worst performer: high downtime
        "speed_range":     (860, 1140),
        "reject_rate":     0.005,
        "co_range":        (48, 68),   # Longest changeovers
        "comments": {
            "production": [
                "Bourrage convoyeur — arrêt {min} minutes, cause identifiée",
                "Perte de cadence en étiquetage, réglage effectué",
                "Changement de format: {min} minutes — délai habituel",
                "Arrêt non planifié, capteur défaillant remplacé",
                "Reprise après maintenance corrective, production normalisée",
                "Ralentissement dû à l'approvisionnement en matériaux",
            ],
            "quality": [
                "Calibration balance effectuée, résultats conformes",
                "Contrôle poids: 1 unité hors tolérance rejetée",
                "Vérification sérialisation OK",
                "Contrôle étiquettes: anomalie détectée et corrigée",
                "Inspection en cours de poste conforme aux procédures",
            ],
            "maintenance": [
                "Intervention tapis transporteur — remplacement courroie",
                "Réglage capteur niveau remplissage",
                "Panne intermittente soudeuse, intervention réalisée",
                "Changement joint O-ring pompe de dosage",
                "Maintenance corrective moteur convoyeur — même panne qu'en septembre",
            ],
            "safety": [
                "Vérification EPI complète",
                "Zone de travail propre et rangée",
                "Déversement mineur nettoyé immédiatement",
            ],
        },
        "co_comment": "Changement de format terminé en {min} minutes — procédure standard",
    },

    "sesto": {
        "operators": [
            ("Marco Rossi",      "operator",    "SES-001"),
            ("Giulia Ferrari",   "operator",    "SES-002"),
            ("Antonio Bianchi",  "operator",    "SES-003"),
            ("Laura Colombo",    "quality",     "SES-004"),
            ("Francesco Romano", "maintenance", "SES-005"),
            ("Chiara Ricci",     "supervisor",  "SES-006"),
        ],
        "downtime_range":  (22, 48),
        "speed_range":     (970, 1175),
        "reject_rate":     0.010,
        "co_range":        (32, 50),
        "comments": {
            "production": [
                "Blocco nastro trasportatore risolto in {min} minuti",
                "Regolazione velocità linea completata senza anomalie",
                "Cambio formato eseguito in {min} minuti",
                "Produzione regolare, nessuna anomalia significativa",
                "Rallentamento per accumulo in inscatolamento, risolto",
                "Turno produttivo, obiettivo raggiunto",
            ],
            "quality": [
                "Calibrazione bilancia completata, valori conformi",
                "Controllo peso: tutte le unità conformi",
                "Verifica serializzazione superata al 100%",
                "Ispezione etichette: nessuna anomalia rilevata",
                "1 unità scartata per peso fuori tolleranza",
            ],
            "maintenance": [
                "Lubrificazione catena trasportatore eseguita",
                "Regolazione sensore livello riempimento",
                "Guasto intermittente sigillatrice risolto",
                "Sostituzione O-ring pompa dosatrice",
                "Manutenzione preventiva etichettatrice completata",
            ],
            "safety": [
                "Verifica DPI completata, tutto conforme",
                "Area di lavoro pulita e ordinata — 5S OK",
                "Piccolo sversamento in zona riempimento: pulito",
            ],
        },
        "co_comment": "Cambio formato completato in {min} minuti",
    },
}


# ── Schema SQL (mismo que database.py) ───────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS operators (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'operator'
                 CHECK(role IN ('operator','supervisor','quality','maintenance')),
    badge_number TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS shifts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id    INTEGER NOT NULL REFERENCES operators(id) ON DELETE RESTRICT,
    line_number    INTEGER NOT NULL CHECK(line_number BETWEEN 1 AND 20),
    start_time     TEXT NOT NULL DEFAULT (datetime('now')),
    end_time       TEXT,
    status         TEXT NOT NULL DEFAULT 'active'
                   CHECK(status IN ('active','completed','interrupted')),
    shift_type     TEXT NOT NULL DEFAULT 'morning'
                   CHECK(shift_type IN ('morning','afternoon','night')),
    handover_notes TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id    INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE RESTRICT,
    text        TEXT NOT NULL CHECK(length(text) > 0 AND length(text) <= 2000),
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    category    TEXT NOT NULL DEFAULT 'production'
                CHECK(category IN ('safety','quality','production','maintenance')),
    source      TEXT NOT NULL DEFAULT 'voice'
                CHECK(source IN ('voice','manual'))
);
CREATE TABLE IF NOT EXISTS kpi_readings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id         INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    timestamp        TEXT NOT NULL DEFAULT (datetime('now')),
    units_produced   INTEGER NOT NULL DEFAULT 0 CHECK(units_produced >= 0),
    units_rejected   INTEGER NOT NULL DEFAULT 0 CHECK(units_rejected >= 0),
    downtime_minutes REAL NOT NULL DEFAULT 0.0 CHECK(downtime_minutes >= 0),
    line_speed       REAL NOT NULL DEFAULT 0.0 CHECK(line_speed >= 0),
    target_units     INTEGER NOT NULL DEFAULT 0,
    nominal_speed    REAL NOT NULL DEFAULT 0.0,
    planned_time_min REAL NOT NULL DEFAULT 480.0
);
CREATE TABLE IF NOT EXISTS knowledge_base (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'file'
                CHECK(source_type IN ('pdf','docx','xlsx','url')),
    chunk_index INTEGER NOT NULL,
    chunk_text  TEXT NOT NULL,
    indexed_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS assistant_suggestions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id        INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    comment_id      INTEGER REFERENCES comments(id) ON DELETE SET NULL,
    query_text      TEXT NOT NULL,
    context_sources TEXT NOT NULL DEFAULT '[]',
    response_text   TEXT NOT NULL,
    model_used      TEXT NOT NULL DEFAULT 'unknown',
    source          TEXT NOT NULL DEFAULT 'gateway'
                    CHECK(source IN ('gateway','mock')),
    feedback        TEXT CHECK(feedback IN ('useful','not_useful', NULL)),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS saved_charts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    prompt_text  TEXT NOT NULL,
    echarts_json TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS process_steps (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id                     INTEGER NOT NULL DEFAULT 1,
    line_number                 INTEGER NOT NULL CHECK(line_number BETWEEN 1 AND 20),
    step_order                  INTEGER NOT NULL,
    step_name                   TEXT NOT NULL,
    step_type                   TEXT NOT NULL DEFAULT 'value-add'
                                CHECK(step_type IN ('value-add','non-value-add','wait')),
    nominal_cycle_time_seconds  REAL NOT NULL DEFAULT 10.0,
    nominal_changeover_minutes  REAL NOT NULL DEFAULT 30.0,
    UNIQUE(line_number, step_order)
);
CREATE TABLE IF NOT EXISTS step_live_data (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id           INTEGER NOT NULL REFERENCES process_steps(id) ON DELETE CASCADE,
    timestamp         TEXT NOT NULL DEFAULT (datetime('now')),
    actual_cycle_time REAL NOT NULL DEFAULT 0.0,
    units_in_wip      INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'running'
                      CHECK(status IN ('running','stopped','changeover','waiting')),
    current_speed     REAL NOT NULL DEFAULT 0.0,
    defect_count      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_shifts_operator   ON shifts(operator_id);
CREATE INDEX IF NOT EXISTS idx_shifts_status     ON shifts(status);
CREATE INDEX IF NOT EXISTS idx_shifts_line       ON shifts(line_number);
CREATE INDEX IF NOT EXISTS idx_comments_shift    ON comments(shift_id);
CREATE INDEX IF NOT EXISTS idx_comments_ts       ON comments(timestamp);
CREATE INDEX IF NOT EXISTS idx_kpi_shift         ON kpi_readings(shift_id);
CREATE INDEX IF NOT EXISTS idx_kpi_ts            ON kpi_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_kb_source         ON knowledge_base(source_file);
CREATE INDEX IF NOT EXISTS idx_sugg_shift        ON assistant_suggestions(shift_id);
CREATE INDEX IF NOT EXISTS idx_sugg_comment      ON assistant_suggestions(comment_id);
CREATE INDEX IF NOT EXISTS idx_charts_created    ON saved_charts(created_at);
CREATE INDEX IF NOT EXISTS idx_process_steps_line ON process_steps(line_number);
CREATE INDEX IF NOT EXISTS idx_step_live_step     ON step_live_data(step_id);
CREATE INDEX IF NOT EXISTS idx_step_live_ts       ON step_live_data(timestamp);
"""


def _create_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_shifts_active_line
        ON shifts(line_number) WHERE status = 'active'
    """)
    conn.commit()
    conn.close()


def _is_seeded(db_path: str) -> bool:
    """Devuelve True si la BD ya tiene al menos 6 operadores."""
    try:
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM operators").fetchone()[0]
        conn.close()
        return count >= 6
    except Exception:
        return False


def seed_site(site_id: str, force: bool = False) -> None:
    """Genera datos de ejemplo para una planta."""
    site = SITES.get(site_id)
    if not site:
        _safe_print(f"  [!] Site desconocido: {site_id}")
        return

    db_path = site["db_path"]
    _create_schema(db_path)

    if not force and _is_seeded(db_path):
        _safe_print(f"  [ok] {site['name']} -- ya tiene datos, omitido")
        return

    _safe_print(f"  [>>] Generando datos para {site['name']} ({db_path})...")
    cfg = SITE_CFG[site_id]
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")  # desactivar FK para seed masivo

    # ── 1. Operadores ──
    op_ids: list[int] = []
    for name, role, badge in cfg["operators"]:
        conn.execute("DELETE FROM operators WHERE badge_number=?", (badge,))
        cur = conn.execute(
            "INSERT INTO operators (name, role, badge_number) VALUES (?,?,?)",
            (name, role, badge),
        )
        op_ids.append(cur.lastrowid)
    conn.commit()

    operator_ids = op_ids[:3]  # los 3 primeros son operadores de línea

    # ── 2. Turnos (14 días × 3 líneas × 3 turnos = 126 por planta) ──
    now        = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    shift_hrs  = {"morning": 6, "afternoon": 14, "night": 22}
    categories = (["production"] * 3 + ["quality"] * 2
                  + ["maintenance"] * 1 + ["safety"] * 1)

    shift_rows:   list[tuple] = []
    kpi_rows:     list[tuple] = []
    comment_rows: list[tuple] = []

    for day_offset in range(14, 0, -1):
        day = now - timedelta(days=day_offset)
        for line in [1, 2, 3]:
            for shift_type, start_hour in shift_hrs.items():
                start_dt = day.replace(hour=start_hour)
                end_dt   = start_dt + timedelta(hours=8)
                op_id    = random.choice(operator_ids)
                dt_min   = random.uniform(*cfg["downtime_range"])
                co_min   = random.randint(*cfg["co_range"])
                notes    = cfg["co_comment"].format(min=co_min)

                shift_rows.append((
                    op_id, line,
                    start_dt.isoformat(sep=" ", timespec="seconds"),
                    end_dt.isoformat(sep=" ", timespec="seconds"),
                    shift_type, notes,
                ))

    conn.executemany("""
        INSERT INTO shifts
        (operator_id, line_number, start_time, end_time,
         status, shift_type, handover_notes)
        VALUES (?,?  ,?,?,'completed',?,?)
    """, shift_rows)
    conn.commit()

    shift_ids = [r[0] for r in conn.execute(
        "SELECT id FROM shifts ORDER BY id"
    ).fetchall()]

    # Reconstruir datos de turno para las lecturas y comentarios
    shift_meta = conn.execute(
        "SELECT id, operator_id, line_number, start_time FROM shifts ORDER BY id"
    ).fetchall()

    for row in shift_meta:
        sid       = row[0]
        op_id     = row[1]
        line      = row[2]
        start_dt  = datetime.fromisoformat(row[3])
        dt_min    = random.uniform(*cfg["downtime_range"])
        speed     = random.uniform(*cfg["speed_range"])
        avail_t   = 480.0 - dt_min
        units     = int(speed * avail_t / 60 * random.uniform(0.95, 1.05))
        rej_rate  = cfg["reject_rate"] * random.uniform(0.5, 2.0)
        units_rej = int(units * rej_rate)

        # 3 lecturas por turno (h2, h5, h8)
        for frac_idx, h in enumerate([2, 5, 8]):
            frac = h / 8.0
            ts   = start_dt + timedelta(hours=h)
            kpi_rows.append((
                sid,
                ts.isoformat(sep=" ", timespec="seconds"),
                int(units * frac),
                int(units_rej * frac),
                round(dt_min * frac, 2),
                round(speed * random.uniform(0.95, 1.05), 1),
                9600,
                1200.0,
                480.0,
            ))

        # 3-5 comentarios por turno
        num_c = random.randint(3, 5)
        for _ in range(num_c):
            cat      = random.choice(categories)
            template = random.choice(cfg["comments"][cat])
            min_val  = random.randint(*cfg["co_range"])
            text     = template.format(min=min_val) if "{min}" in template else template
            c_ts     = start_dt + timedelta(minutes=random.randint(15, 455))
            comment_rows.append((
                sid, op_id, text,
                c_ts.isoformat(sep=" ", timespec="seconds"),
                cat,
            ))

    conn.executemany("""
        INSERT INTO kpi_readings
        (shift_id, timestamp, units_produced, units_rejected,
         downtime_minutes, line_speed, target_units, nominal_speed, planned_time_min)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, kpi_rows)

    conn.executemany("""
        INSERT INTO comments (shift_id, operator_id, text, timestamp, category, source)
        VALUES (?,?,?,?,'production','manual')
    """, [(r[0], r[1], r[2], r[3]) for r in comment_rows])

    # Actualizar categoría correcta (no se puede hacer con executemany fácil)
    # Reinsertamos con categoría
    conn.execute("DELETE FROM comments")
    conn.executemany("""
        INSERT INTO comments (shift_id, operator_id, text, timestamp, category, source)
        VALUES (?,?,?,?,?,'manual')
    """, comment_rows)

    conn.commit()

    # ── 3. Pasos de proceso (VSM) ──
    for line in [1, 2, 3]:
        for order, name, stype, nom_ct, nom_co in PHARMA_STEPS:
            conn.execute("""
                INSERT OR IGNORE INTO process_steps
                (site_id, line_number, step_order, step_name, step_type,
                 nominal_cycle_time_seconds, nominal_changeover_minutes)
                VALUES (1,?,?,?,?,?,?)
            """, (line, order, name, stype, nom_ct, nom_co))
    conn.commit()

    # ── 4. Datos en vivo de VSM ──
    statuses = ["running"] * 5 + ["stopped", "changeover", "waiting"]
    step_rows = conn.execute(
        "SELECT id, nominal_cycle_time_seconds FROM process_steps"
    ).fetchall()

    live_rows: list[tuple] = []
    for step in step_rows:
        for i in range(20):
            ts     = now - timedelta(minutes=(20 - i) * 15)
            jitter = random.uniform(0.85, 1.30)
            ct     = round(step[1] * jitter, 2)
            live_rows.append((
                step[0],
                ts.isoformat(sep=" ", timespec="seconds"),
                ct,
                random.randint(0, 80),
                random.choice(statuses),
                round(3600 / ct if ct > 0 else 0, 1),
                random.randint(0, 3) if random.random() < 0.2 else 0,
            ))

    conn.executemany("""
        INSERT INTO step_live_data
        (step_id, timestamp, actual_cycle_time, units_in_wip,
         status, current_speed, defect_count)
        VALUES (?,?,?,?,?,?,?)
    """, live_rows)

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()

    shifts_n   = len(shift_rows)
    kpis_n     = len(kpi_rows)
    comments_n = len(comment_rows)
    _safe_print(f"  [ok] {site['name']}: {shifts_n} turnos, {kpis_n} KPIs, {comments_n} comentarios")


def migrate_legacy_db() -> None:
    """Copia opex.db → site_alcobendas.db si aún no existe."""
    src = "opex.db"
    dst = SITES["alcobendas"]["db_path"]
    if os.path.exists(src) and not os.path.exists(dst):
        _safe_print(f"  [>>] Migrando {src} -> {dst}")
        shutil.copy2(src, dst)
        _safe_print(f"  [ok] Migracion completada")


def seed_all_sites(force: bool = False) -> None:
    """Inicializa todas las plantas. Migra opex.db si procede."""
    _safe_print("[ seed_sites ] Iniciando generacion de datos multi-planta...")
    migrate_legacy_db()
    for site_id in SITES:
        seed_site(site_id, force=force)
    _safe_print("[ seed_sites ] Completado.")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    force  = "--force" in sys.argv

    if target and target in SITES:
        seed_site(target, force=force)
    elif target == "--force":
        seed_all_sites(force=True)
    else:
        seed_all_sites(force=force)
