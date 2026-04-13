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

    "seishin": {
        "operators": [
            ("Tanaka Hiroshi",   "operator",    "SEI-001"),
            ("Yamamoto Yuki",    "operator",    "SEI-002"),
            ("Nakamura Kenji",   "operator",    "SEI-003"),
            ("Suzuki Aiko",      "quality",     "SEI-004"),
            ("Ito Masashi",      "maintenance", "SEI-005"),
            ("Watanabe Emi",     "supervisor",  "SEI-006"),
        ],
        "downtime_range":  (8, 25),    # Best-in-class: minimal downtime (TPM culture)
        "speed_range":     (1080, 1220),
        "reject_rate":     0.010,
        "co_range":        (14, 24),   # SMED-driven short changeovers
        "comments": {
            "production": [
                "段取り替え完了: {min}分 — 標準手順通り",
                "ライン速度調整完了、異常なし",
                "ロット切替え順調に完了",
                "包装ステーションの軽微な詰まり解消: {min}分",
                "生産目標達成、シフト好調",
                "かんばん補充完了、在庫問題なし",
                "TPM自主保全チェック完了",
            ],
            "quality": [
                "重量検査: 全品規格内 — 不合格ゼロ",
                "シリアル化確認: 100%合格",
                "ラベル検査: 異常なし",
                "密封テスト: 全品合格",
                "ポカヨケ装置正常動作確認",
                "一発合格率 99.0% — 目標達成",
            ],
            "maintenance": [
                "定期保全完了 — スケジュール通り",
                "コンベアベルト張力調整 (予防措置)",
                "充填ノズル清掃、異常なし",
                "予知保全アラート対応 — ベアリング交換",
                "5S点検実施: エリアスコア 4.8/5",
            ],
            "safety": [
                "安全点検完了、全項目合格",
                "5S監査合格 — エリアスコア 4.9/5",
                "保護具確認: 全員適切着用",
                "ヒヤリハット報告書提出: 是正措置済み",
            ],
        },
        "co_comment": "段取り替え完了: {min}分 — SMED標準手順",
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
CREATE TABLE IF NOT EXISTS top_problems (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id             TEXT NOT NULL,
    line_number         INTEGER CHECK(line_number BETWEEN 1 AND 20),
    problem_description TEXT NOT NULL,
    category            TEXT NOT NULL DEFAULT 'equipment'
                        CHECK(category IN ('quality','equipment','process','safety','material')),
    frequency           REAL NOT NULL DEFAULT 1.0,
    impact_score        INTEGER NOT NULL DEFAULT 5 CHECK(impact_score BETWEEN 1 AND 10),
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open','investigating','resolved')),
    first_detected      TEXT NOT NULL DEFAULT (date('now')),
    last_occurrence     TEXT NOT NULL DEFAULT (date('now')),
    root_cause          TEXT,
    countermeasure      TEXT
);
CREATE TABLE IF NOT EXISTS improvement_initiatives (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id          TEXT NOT NULL,
    line_number      INTEGER CHECK(line_number BETWEEN 1 AND 20),
    title            TEXT NOT NULL,
    description      TEXT NOT NULL,
    methodology      TEXT NOT NULL DEFAULT 'Kaizen'
                     CHECK(methodology IN ('A3','Kaizen','DMAIC','5Why','other')),
    status           TEXT NOT NULL DEFAULT 'planned'
                     CHECK(status IN ('planned','in_progress','completed','on_hold')),
    owner            TEXT NOT NULL,
    start_date       TEXT NOT NULL,
    target_date      TEXT NOT NULL,
    completion_date  TEXT,
    expected_benefit TEXT,
    actual_benefit   TEXT,
    linked_problem_id INTEGER REFERENCES top_problems(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS initiative_documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    initiative_id INTEGER NOT NULL REFERENCES improvement_initiatives(id) ON DELETE CASCADE,
    document_type TEXT NOT NULL DEFAULT 'A3'
                  CHECK(document_type IN ('A3','project_charter','report','SOP_update')),
    title         TEXT NOT NULL,
    content_html  TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    author        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_problems_site       ON top_problems(site_id);
CREATE INDEX IF NOT EXISTS idx_problems_status     ON top_problems(status);
CREATE INDEX IF NOT EXISTS idx_problems_line       ON top_problems(line_number);
CREATE INDEX IF NOT EXISTS idx_initiatives_site    ON improvement_initiatives(site_id);
CREATE INDEX IF NOT EXISTS idx_initiatives_status  ON improvement_initiatives(status);
CREATE INDEX IF NOT EXISTS idx_init_docs_init      ON initiative_documents(initiative_id);
CREATE TABLE IF NOT EXISTS notification_config (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id     TEXT NOT NULL UNIQUE,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS notification_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT NOT NULL,
    title        TEXT NOT NULL,
    recipient    TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL CHECK(status IN ('sent','failed','skipped')),
    site_id      TEXT NOT NULL DEFAULT '',
    line_number  TEXT NOT NULL DEFAULT '',
    error_detail TEXT NOT NULL DEFAULT '',
    sent_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notif_log_sent_at    ON notification_log(sent_at);
CREATE INDEX IF NOT EXISTS idx_notif_log_event_type ON notification_log(event_type);
CREATE INDEX IF NOT EXISTS idx_notif_log_status     ON notification_log(status);
CREATE TABLE IF NOT EXISTS alert_rules (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    name                   TEXT NOT NULL,
    metric                 TEXT NOT NULL
                           CHECK(metric IN ('oee','reject_rate','downtime','line_speed','cycle_time')),
    operator               TEXT NOT NULL
                           CHECK(operator IN ('less_than','greater_than','equals')),
    threshold_value        REAL NOT NULL,
    severity               TEXT NOT NULL DEFAULT 'warning'
                           CHECK(severity IN ('info','warning','critical')),
    active                 INTEGER NOT NULL DEFAULT 1,
    notification_channels  TEXT NOT NULL DEFAULT '["app"]',
    cooldown_minutes       INTEGER NOT NULL DEFAULT 30,
    created_at             TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS alert_rule_cooldowns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id         INTEGER NOT NULL,
    site_id         TEXT NOT NULL,
    line_number     INTEGER NOT NULL,
    last_triggered  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(rule_id, site_id, line_number)
);
CREATE TABLE IF NOT EXISTS alerts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id                 TEXT NOT NULL,
    line_number             INTEGER NOT NULL,
    timestamp               TEXT NOT NULL DEFAULT (datetime('now')),
    source                  TEXT NOT NULL DEFAULT 'rule'
                            CHECK(source IN ('rule','ai')),
    rule_id                 INTEGER,
    severity                TEXT NOT NULL DEFAULT 'warning'
                            CHECK(severity IN ('info','warning','critical')),
    title                   TEXT NOT NULL,
    description             TEXT NOT NULL,
    metric_name             TEXT NOT NULL DEFAULT '',
    metric_value            REAL,
    threshold_value         REAL,
    status                  TEXT NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active','acknowledged','resolved')),
    acknowledged_by         TEXT,
    acknowledged_at         TEXT,
    resolved_at             TEXT,
    notification_sent_app   INTEGER NOT NULL DEFAULT 0,
    notification_sent_teams INTEGER NOT NULL DEFAULT 0,
    notification_sent_email INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_site        ON alerts(site_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status      ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity    ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp   ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_rule        ON alerts(rule_id);
CREATE INDEX IF NOT EXISTS idx_cooldown_rule_site ON alert_rule_cooldowns(rule_id, site_id, line_number);
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

    # ── 5. Problemas top e iniciativas ──
    conn2 = sqlite3.connect(db_path)
    conn2.execute("PRAGMA foreign_keys = ON")
    _seed_problems_and_initiatives(site_id, conn2)
    conn2.close()

    shifts_n   = len(shift_rows)
    kpis_n     = len(kpi_rows)
    comments_n = len(comment_rows)
    _safe_print(f"  [ok] {site['name']}: {shifts_n} turnos, {kpis_n} KPIs, {comments_n} comentarios")


def _seed_problems_and_initiatives(site_id: str, conn: sqlite3.Connection) -> None:
    """Inserta problemas top e iniciativas de mejora para una planta."""

    # ── Datos por planta ──────────────────────────────────────────────────────
    PROBLEMS: dict[str, list[dict]] = {
        "alcobendas": [
            {
                "line": 1, "cat": "equipment",
                "desc": "Atasco frecuente en etiquetadora automática",
                "freq": 4.5, "impact": 8, "status": "investigating",
                "first": "2025-11-10", "last": "2026-03-24",
                "root": "Desgaste de guías de papel y acumulación de adhesivo en rodillos de avance",
                "counter": "Plan de limpieza cada 4 horas y sustitución preventiva de guías cada 2 meses",
            },
            {
                "line": 2, "cat": "quality",
                "desc": "Desviación de peso en llenadora: unidades fuera de ±2%",
                "freq": 2.8, "impact": 9, "status": "investigating",
                "first": "2025-12-05", "last": "2026-03-22",
                "root": "Variación en densidad del producto granulado junto con desgaste de la bomba dosificadora",
                "counter": "Recalibración diaria de la llenadora y sustitución del diafragma de la bomba",
            },
            {
                "line": 3, "cat": "equipment",
                "desc": "Fallo de sensor en módulo de serialización (lecturas erróneas)",
                "freq": 3.2, "impact": 9, "status": "open",
                "first": "2026-01-15", "last": "2026-03-25",
                "root": "Degradación del sensor de cámara por condensación en cámara limpia",
                "counter": "Instalación de purga de aire seco en el módulo y sustitución del sensor",
            },
            {
                "line": 1, "cat": "process",
                "desc": "Tiempo de cambio de formato elevado (>55 min) en línea 1",
                "freq": 1.5, "impact": 6, "status": "resolved",
                "first": "2025-10-01", "last": "2026-02-28",
                "root": "Piezas de formato no identificadas y herramientas no preasignadas",
                "counter": "SMED aplicado: kits de cambio con código de color, reducción a 38 min promedio",
            },
            {
                "line": None, "cat": "material",
                "desc": "Retrasos en suministro de material de acondicionamiento (cartón)",
                "freq": 1.0, "impact": 5, "status": "open",
                "first": "2026-02-01", "last": "2026-03-20",
                "root": None,
                "counter": None,
            },
        ],
        "indianapolis": [
            {
                "line": 1, "cat": "equipment",
                "desc": "Film breakage in blister sealing machine during high-speed runs",
                "freq": 2.5, "impact": 7, "status": "investigating",
                "first": "2025-12-10", "last": "2026-03-23",
                "root": "Forming station temperature variability causes film stress at >95% speed",
                "counter": "Install closed-loop temperature control; reduce nominal speed to 92%",
            },
            {
                "line": 2, "cat": "quality",
                "desc": "Torque closure variability exceeding ±5% spec on capping station",
                "freq": 3.8, "impact": 8, "status": "in_progress",
                "first": "2026-01-08", "last": "2026-03-25",
                "root": "Worn torque clutch coupling combined with ambient temperature variation",
                "counter": "Replace clutch coupling Q1; implement torque SPC control chart",
            },
            {
                "line": 3, "cat": "material",
                "desc": "Line stoppages due to material shortage (labels and inserts)",
                "freq": 1.8, "impact": 6, "status": "open",
                "first": "2026-02-14", "last": "2026-03-24",
                "root": None,
                "counter": None,
            },
            {
                "line": 2, "cat": "process",
                "desc": "Changeover time regression after operator rotation (Q4 2025)",
                "freq": 1.2, "impact": 5, "status": "resolved",
                "first": "2025-10-15", "last": "2026-01-31",
                "root": "New operators unfamiliar with color-coded SMED kit sequence",
                "counter": "OJT retraining program completed; buddy system for first 10 changeovers",
            },
            {
                "line": 1, "cat": "safety",
                "desc": "Ergonomic risk at manual palletizing station (repetitive strain)",
                "freq": 0.5, "impact": 7, "status": "investigating",
                "first": "2026-01-20", "last": "2026-03-10",
                "root": "High-frequency repetitive lifting above shoulder height",
                "counter": "Semi-automatic palletizer investment under evaluation",
            },
        ],
        "fegersheim": [
            {
                "line": 1, "cat": "equipment",
                "desc": "Erreur de lecture répétée en module sérialisation (caméra 2D)",
                "freq": 3.5, "impact": 9, "status": "investigating",
                "first": "2025-11-20", "last": "2026-03-25",
                "root": "Condensation sur l'objectif de la caméra en salle ISO 7 — même cause identifiée qu'à Alcobendas",
                "counter": "Purge d'air sec sur le module caméra; protocole de nettoyage hebdomadaire",
            },
            {
                "line": 2, "cat": "equipment",
                "desc": "Usure prématurée des couteaux de découpe (remplacement tous les 3 semaines)",
                "freq": 0.33, "impact": 7, "status": "open",
                "first": "2025-09-01", "last": "2026-03-18",
                "root": "Dureté insuffisante des couteaux actuels pour les formats d'aluminium épais",
                "counter": "Essai de couteaux en carbure de tungstène — durée de vie estimée x4",
            },
            {
                "line": 3, "cat": "quality",
                "desc": "Problème d'adhérence des étiquettes à basse température (<18°C)",
                "freq": 2.0, "impact": 8, "status": "investigating",
                "first": "2026-01-10", "last": "2026-03-22",
                "root": "Colle thermosensible non adaptée aux conditions d'hiver de la salle de production",
                "counter": "Changement de référence colle vers formulation basse température; contrôle T° ambiante",
            },
            {
                "line": 1, "cat": "process",
                "desc": "Temps de changement de format excessif (>65 min) sur ligne 1",
                "freq": 1.5, "impact": 6, "status": "open",
                "first": "2025-08-01", "last": "2026-03-15",
                "root": "Manque de standardisation des pièces de format et absence de préparation anticipée",
                "counter": "Projet SMED en cours — objectif <45 min",
            },
            {
                "line": None, "cat": "material",
                "desc": "Rupture de stock matière première (film aluminium) — 2 arrêts/mois",
                "freq": 2.0, "impact": 8, "status": "open",
                "first": "2026-01-01", "last": "2026-03-20",
                "root": None,
                "counter": None,
            },
        ],
        "sesto": [
            {
                "line": 1, "cat": "equipment",
                "desc": "Vibrazione eccessiva nell'incassatrice — cause arresti non pianificati",
                "freq": 2.8, "impact": 8, "status": "investigating",
                "first": "2025-12-01", "last": "2026-03-24",
                "root": "Cuscinetti usurati nel gruppo di trasmissione principale — vibrazione a 18 Hz",
                "counter": "Sostituzione cuscinetti pianificata per prossima fermata programmata; monitoraggio vibrazioni IoT",
            },
            {
                "line": 2, "cat": "equipment",
                "desc": "Guasto del sistema vuoto nel pick-and-place (perdita di presa)",
                "freq": 3.5, "impact": 9, "status": "open",
                "first": "2026-01-20", "last": "2026-03-25",
                "root": "Micro-fessure nelle ventose in silicone accelerate da cicli termici",
                "counter": "Sostituzione preventiva delle ventose ogni 6 settimane; ispezione visiva settimanale",
            },
            {
                "line": 3, "cat": "process",
                "desc": "Disallineamento ciclico nel paletizzatore — errori di posizionamento",
                "freq": 1.5, "impact": 6, "status": "resolved",
                "first": "2025-10-10", "last": "2026-02-15",
                "root": "Deriva meccanica del sistema di guida lineare per mancanza di lubrificazione periodica",
                "counter": "Aggiunto intervento di lubrificazione nel piano di manutenzione mensile — problema risolto",
            },
            {
                "line": 1, "cat": "quality",
                "desc": "Unità scartate per peso fuori tolleranza — tasso >1,5% su L1",
                "freq": 2.0, "impact": 8, "status": "investigating",
                "first": "2026-02-01", "last": "2026-03-23",
                "root": "Deriva sensore bilancia dopo 4 ore di funzionamento continuo — temperatura influente",
                "counter": "Ricalibrazione ogni 2 ore; studio per sostituzione con bilancia termocompensata",
            },
            {
                "line": None, "cat": "safety",
                "desc": "Rischio scivolamento zona riempimento (pavimento bagnato ricorrente)",
                "freq": 1.0, "impact": 7, "status": "open",
                "first": "2026-01-15", "last": "2026-03-18",
                "root": None,
                "counter": None,
            },
        ],
    }

    # Insert problems and collect IDs
    prob_ids: list[int] = []
    for p in PROBLEMS.get(site_id, []):
        cur = conn.execute(
            """INSERT INTO top_problems
               (site_id, line_number, problem_description, category,
                frequency, impact_score, status,
                first_detected, last_occurrence, root_cause, countermeasure)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                site_id, p["line"], p["desc"], p["cat"],
                p["freq"], p["impact"], p["status"],
                p["first"], p["last"], p.get("root"), p.get("counter"),
            ),
        )
        prob_ids.append(cur.lastrowid)
    conn.commit()

    # ── Iniciativas de mejora ─────────────────────────────────────────────────
    # prob_ids indexing: prob_ids[0] = first problem for this site, etc.
    INITIATIVES: dict[str, list[dict]] = {
        "alcobendas": [
            {
                "line": 1, "title": "Reducción de paradas por atasco en etiquetadora L1",
                "desc": "Proyecto A3 para eliminar las paradas recurrentes causadas por atascos en la etiquetadora automática de la línea 1.",
                "method": "A3", "status": "completed", "owner": "Isabel Torres",
                "start": "2025-11-15", "target": "2026-02-28", "completion": "2026-02-20",
                "benefit_exp": "Reducción de paradas no planificadas un 80%, recuperando ~3h/semana de producción",
                "benefit_act": "Paradas reducidas de 4,5/semana a 0,8/semana. Recuperadas 2,7 h/semana.",
                "linked_prob_idx": 0,
            },
            {
                "line": None, "title": "Kaizen: Reducción de tiempo de limpieza entre lotes",
                "desc": "Evento Kaizen de 3 días para reducir el tiempo de limpieza CIP/SIP entre lotes de diferente producto.",
                "method": "Kaizen", "status": "planned", "owner": "Pedro García",
                "start": "2026-04-07", "target": "2026-04-09", "completion": None,
                "benefit_exp": "Reducción del 30% del tiempo de limpieza (de 4h a 2,8h por cambio de lote)",
                "benefit_act": None,
                "linked_prob_idx": None,
            },
        ],
        "indianapolis": [
            {
                "line": 2, "title": "DMAIC: Variabilidad en torque de cierre — Capping L2",
                "desc": "Proyecto DMAIC para reducir la variabilidad en el torque de cierre de la línea 2 que genera rechazos y reclamaciones de cliente.",
                "method": "DMAIC", "status": "in_progress", "owner": "Jennifer Taylor",
                "start": "2026-01-15", "target": "2026-05-15", "completion": None,
                "benefit_exp": "Reducir variabilidad de torque de ±8% a ±3%; eliminar rechazos por cierre defectuoso",
                "benefit_act": None,
                "linked_prob_idx": 1,
            },
            {
                "line": None, "title": "Estandarización de cambio de formato (SMED Best Practice)",
                "desc": "Documentación y estandarización del proceso SMED que posiciona a Indianapolis como benchmark global en tiempos de changeover.",
                "method": "A3", "status": "completed", "owner": "Robert Brown",
                "start": "2025-07-01", "target": "2025-11-30", "completion": "2025-11-15",
                "benefit_exp": "Reducir changeover promedio de 45 min a <25 min en todas las líneas",
                "benefit_act": "Changeover promedio 22 min. Ahorro estimado: 180 h/año de producción perdida.",
                "linked_prob_idx": 3,
            },
        ],
        "fegersheim": [
            {
                "line": 1, "title": "Amélioration OEE ligne sérialisation — résolution erreurs caméra",
                "desc": "Projet A3 pour éliminer les erreurs répétées de lecture caméra 2D dans le module de sérialisation de la ligne 1.",
                "method": "A3", "status": "in_progress", "owner": "Claire Rousseau",
                "start": "2026-02-01", "target": "2026-06-30", "completion": None,
                "benefit_exp": "Réduire les arrêts liés à la sérialisation de 3,5/semaine à <0,5/semaine",
                "benefit_act": None,
                "linked_prob_idx": 0,
            },
            {
                "line": 3, "title": "5 Pourquoi: Adhérence étiquettes basse température",
                "desc": "Analyse 5 Pourquoi pour identifier et éliminer la cause racine du problème d'adhérence des étiquettes lors des périodes hivernales.",
                "method": "5Why", "status": "in_progress", "owner": "Sophie Lefebvre",
                "start": "2026-02-15", "target": "2026-04-30", "completion": None,
                "benefit_exp": "Éliminer les non-conformités étiquetage liées à la température — 0 réclamation client",
                "benefit_act": None,
                "linked_prob_idx": 2,
            },
        ],
        "sesto": [
            {
                "line": 1, "title": "Riduzione scarti per peso fuori tolleranza — Linea 1",
                "desc": "Progetto A3 per ridurre il tasso di scarto per peso fuori tolleranza sulla linea 1, attualmente superiore all'1,5%.",
                "method": "A3", "status": "in_progress", "owner": "Chiara Ricci",
                "start": "2026-02-10", "target": "2026-05-31", "completion": None,
                "benefit_exp": "Ridurre il tasso di scarto da 1,5% a <0,5%; risparmio stimato 15.000 unità/mese",
                "benefit_act": None,
                "linked_prob_idx": 3,
            },
            {
                "line": 2, "title": "Kaizen: Eliminazione guasti pick-and-place L2",
                "desc": "Evento Kaizen focalizzato sull'eliminazione dei guasti ricorrenti nel sistema pick-and-place della linea 2 causati dal deterioramento delle ventose.",
                "method": "Kaizen", "status": "planned", "owner": "Francesco Romano",
                "start": "2026-04-14", "target": "2026-04-16", "completion": None,
                "benefit_exp": "Ridurre i guasti pick-and-place da 3,5/settimana a <0,5/settimana",
                "benefit_act": None,
                "linked_prob_idx": 1,
            },
        ],
    }

    # ── Documentos A3 completos ───────────────────────────────────────────────
    A3_DOCS: dict[str, list[str]] = {
        "alcobendas": [
            # Doc 0: A3 completado — etiquetadora L1
            """<article class="a3-document">
<h2>A3: Reducción de paradas por atasco en etiquetadora L1</h2>
<p><strong>Autor:</strong> Isabel Torres &nbsp;|&nbsp; <strong>Planta:</strong> Alcobendas &nbsp;|&nbsp; <strong>Fecha:</strong> 2025-11-15</p>
<hr>
<section><h3>1. Background / Contexto</h3>
<p>La línea 1 de Alcobendas registra de forma recurrente atascos en la etiquetadora automática HERMA 500. Estos eventos generan paradas no planificadas de entre 8 y 22 minutos que impactan directamente en el OEE. Desde noviembre 2025 se registran una media de 4,5 atascos semanales.</p>
</section>
<section><h3>2. Current Condition / Estado Actual</h3>
<ul>
<li>Frecuencia media: 4,5 paradas/semana por atasco en etiquetadora</li>
<li>Duración media por evento: 12 minutos</li>
<li>Producción perdida estimada: ~54 min/semana (~1.080 unidades/semana a velocidad nominal)</li>
<li>OEE L1 impactado en ~1,1% por esta causa específica</li>
<li>Las paradas ocurren principalmente tras 3-4 horas de funcionamiento continuo</li>
</ul>
</section>
<section><h3>3. Goal / Objetivo</h3>
<p>Reducir las paradas por atasco en etiquetadora de 4,5/semana a <strong>≤0,5/semana</strong> antes del 28 de febrero 2026, recuperando ≥2,5 horas de producción semanales.</p>
</section>
<section><h3>4. Root Cause Analysis — Diagrama 5 Por Qué</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
¿Por qué se producen los atascos?
  → Porque las etiquetas se pegan o se doblan al avanzar por las guías
    ¿Por qué se pegan?
      → Porque hay acumulación de adhesivo en los rodillos de avance
        ¿Por qué se acumula adhesivo?
          → Porque no existe un protocolo de limpieza durante la producción
            ¿Por qué no existe ese protocolo?
              → Porque el manual de operación original no lo contemplaba
                → ROOT CAUSE: Ausencia de procedimiento de limpieza preventiva en producción
  → Además: desgaste de guías de papel (guías con tolerancia >0,5mm)
        ¿Por qué están desgastadas?
          → Porque el intervalo de sustitución preventiva es de 6 meses pero el desgaste real ocurre a los 2 meses
            → ROOT CAUSE SECUNDARIA: Frecuencia de sustitución de guías inadecuada
</pre>
</section>
<section><h3>5. Countermeasures / Contramedidas</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Contramedida</th><th>Responsable</th><th>Fecha</th><th>Estado</th></tr>
<tr><td style="padding:0.4rem">Implementar limpieza de rodillos cada 4 horas (incluir en SOP)</td><td>Pedro García</td><td>2025-12-01</td><td>✅ Completado</td></tr>
<tr><td style="padding:0.4rem">Reducir intervalo de sustitución de guías de 6 a 2 meses</td><td>José Fernández</td><td>2025-12-15</td><td>✅ Completado</td></tr>
<tr><td style="padding:0.4rem">Instalar alarma de aviso preventivo en HMI a las 3,5 h de funcionamiento</td><td>José Fernández</td><td>2026-01-20</td><td>✅ Completado</td></tr>
<tr><td style="padding:0.4rem">Actualizar SOP-L1-ETQ-003 con nuevas frecuencias de mantenimiento</td><td>Ana Rodríguez</td><td>2026-01-31</td><td>✅ Completado</td></tr>
</table>
</section>
<section><h3>6. Implementation Plan</h3>
<ul>
<li><strong>Semana 1-2 (Nov 15-29):</strong> Diagnóstico detallado, medición de desgaste de guías, análisis de adhesivo</li>
<li><strong>Semana 3-4 (Dic 1-15):</strong> Implantación de protocolo de limpieza + sustitución de guías</li>
<li><strong>Semana 5-8 (Dic 16 - Ene 15):</strong> Seguimiento de métricas, ajuste de protocolo si necesario</li>
<li><strong>Semana 9-12 (Ene 16 - Feb 15):</strong> Instalación de alarma preventiva en HMI</li>
<li><strong>Semana 13-15 (Feb 16-28):</strong> Validación de resultados, actualización de SOP, cierre A3</li>
</ul>
</section>
<section><h3>7. Follow-up / Seguimiento</h3>
<p>KPIs de seguimiento semanales:</p>
<ul>
<li>Número de atascos/semana (objetivo ≤0,5)</li>
<li>Tiempo perdido por atascos/semana (objetivo ≤6 min)</li>
<li>OEE L1 mensual (objetivo +1,1 pp vs baseline)</li>
</ul>
</section>
<section><h3>8. Results / Resultados</h3>
<p style="background:#d4edda;padding:0.75rem;border-radius:4px">✅ <strong>Proyecto completado el 20 de febrero 2026.</strong></p>
<ul>
<li>Atascos/semana: de 4,5 → <strong>0,8</strong> (reducción del 82%)</li>
<li>Tiempo perdido/semana: de 54 min → <strong>9,6 min</strong></li>
<li>Producción recuperada: <strong>2,7 h/semana (~3.240 unidades)</strong></li>
<li>OEE L1: impacto positivo de +0,95 pp</li>
</ul>
</section>
</article>""",
            # Doc 1: Kaizen limpieza (planned — sin resultados)
            """<article class="a3-document">
<h2>Kaizen: Reducción de tiempo de limpieza entre lotes</h2>
<p><strong>Autor:</strong> Pedro García &nbsp;|&nbsp; <strong>Planta:</strong> Alcobendas &nbsp;|&nbsp; <strong>Fecha:</strong> 2026-03-15</p>
<hr>
<section><h3>1. Background / Contexto</h3>
<p>El tiempo de limpieza CIP/SIP entre lotes de diferente producto en Alcobendas es actualmente de 4 horas. Este tiempo impacta significativamente en el OEE y en la capacidad productiva disponible, especialmente en semanas con alta rotación de productos.</p>
</section>
<section><h3>2. Current Condition / Estado Actual</h3>
<ul>
<li>Tiempo de limpieza actual: 4 horas por cambio de lote</li>
<li>Frecuencia media de cambios: 2,5 por semana</li>
<li>Tiempo perdido total: ~10 h/semana de capacidad productiva</li>
<li>Benchmark interno (Indianapolis): 2,2 horas de limpieza</li>
</ul>
</section>
<section><h3>3. Goal / Objetivo</h3>
<p>Reducir el tiempo de limpieza entre lotes un <strong>30%</strong> (de 4h a ≤2,8h) mediante un evento Kaizen de 3 días, sin comprometer los requisitos GMP de validación de limpieza.</p>
</section>
<section><h3>4. Root Cause Analysis</h3>
<p>Análisis preliminar (a confirmar en el Kaizen):</p>
<ul>
<li>Secuencia de pasos no optimizada — algunos pasos en serie podrían hacerse en paralelo</li>
<li>Tiempos de espera de validación analítica no aprovechados para preparación del siguiente lote</li>
<li>Falta de estandarización del kit de limpieza (tiempo buscando materiales: ~20 min/limpieza)</li>
</ul>
</section>
<section><h3>5. Countermeasures / Contramedidas (propuestas)</h3>
<ul>
<li>Paralelizar pasos independientes (enjuague y preparación de reactivos)</li>
<li>Estandarizar kit de limpieza con carro de materiales preparado</li>
<li>Revisar y simplificar el SOP de limpieza con equipo GMP</li>
</ul>
</section>
<section><h3>6. Implementation Plan</h3>
<ul>
<li><strong>Día 1 (07 Abr):</strong> Mapeo del proceso actual (VSM limpieza), identificación de desperdicios</li>
<li><strong>Día 2 (08 Abr):</strong> Diseño e implementación de contramedidas rápidas (Quick Wins)</li>
<li><strong>Día 3 (09 Abr):</strong> Validación de nuevo proceso, medición de tiempo, plan de estandarización</li>
<li><strong>Post-Kaizen:</strong> Actualización de SOP y formación del equipo</li>
</ul>
</section>
<section><h3>7. Follow-up / Seguimiento</h3>
<ul>
<li>Tiempo de limpieza por lote (objetivo ≤2,8h)</li>
<li>Capacidad productiva recuperada (horas/semana)</li>
<li>Verificación cumplimiento GMP (sin desviaciones de limpieza)</li>
</ul>
</section>
<section><h3>8. Results / Resultados</h3>
<p style="background:#fff3cd;padding:0.75rem;border-radius:4px">⏳ <strong>Evento Kaizen planificado para 7-9 de abril 2026. Pendiente de ejecución.</strong></p>
</section>
</article>""",
        ],

        "indianapolis": [
            # Doc 0: DMAIC torque (in_progress)
            """<article class="a3-document">
<h2>DMAIC: Torque Closure Variability — Capping Station L2</h2>
<p><strong>Author:</strong> Jennifer Taylor &nbsp;|&nbsp; <strong>Site:</strong> Indianapolis &nbsp;|&nbsp; <strong>Date:</strong> 2026-01-15</p>
<hr>
<section><h3>1. Background</h3>
<p>The capping station on Line 2 is generating torque closure readings outside the ±5% specification at a rate of 3.8 events per week. This has resulted in 2 customer complaints (Q4 2025) regarding loose closures, and is a recurring source of finished goods rejection.</p>
</section>
<section><h3>2. Current Condition</h3>
<ul>
<li>Torque variability: ±8% (spec: ±5%)</li>
<li>Rejection rate from torque defects: 0.35% of L2 output</li>
<li>Events per week: 3.8 (target: 0)</li>
<li>Customer complaints linked to closure: 2 in Q4 2025</li>
<li>Cpk torque: 0.72 (target: ≥1.33)</li>
</ul>
</section>
<section><h3>3. Goal</h3>
<p>Reduce torque closure variability from ±8% to <strong>≤±3%</strong> by May 15, 2026. Achieve Cpk ≥1.33 and zero customer complaints related to closures.</p>
</section>
<section><h3>4. Root Cause Analysis — DMAIC Fishbone</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
DEFINE: Torque closure out-of-spec on L2 capping station
MEASURE: Cpk = 0.72 | Variability = ±8% | Root causes under investigation

FISHBONE (Ishikawa):
  MACHINE:
    → Worn torque clutch coupling (confirmed — 18 months in service, spec: 12 months)
    → Spindle bearing play: 0.12mm (spec: <0.05mm)
  METHOD:
    → No torque SPC chart on the line — operators not alerted to drift
    → Torque calibration: monthly (should be weekly per SOP v2.0)
  MATERIAL:
    → Closure supplier change (Q3 2025) — new batch has ±1.5% wall thickness variation
  ENVIRONMENT:
    → Ambient temperature variation (18-26°C in production area) affects lubricant viscosity
  MAN:
    → Operator judgment on torque "feel" inconsistent across shifts

PRIMARY ROOT CAUSE: Worn torque clutch coupling + absence of real-time SPC monitoring
SECONDARY: New closure batch with higher dimensional variability
</pre>
</section>
<section><h3>5. Countermeasures</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Action</th><th>Owner</th><th>Date</th><th>Status</th></tr>
<tr><td style="padding:0.4rem">Replace torque clutch coupling (planned downtime)</td><td>Robert Brown</td><td>2026-02-28</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Replace spindle bearing</td><td>Robert Brown</td><td>2026-02-28</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Implement torque SPC control chart (X-bar/R)</td><td>Sarah Wilson</td><td>2026-03-31</td><td>🔄 In progress</td></tr>
<tr><td style="padding:0.4rem">Change torque calibration frequency to weekly</td><td>Jennifer Taylor</td><td>2026-03-15</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Qualify new closure supplier batch — dimensional audit</td><td>Sarah Wilson</td><td>2026-04-30</td><td>⏳ Pending</td></tr>
<tr><td style="padding:0.4rem">IMPROVE: Implement closed-loop torque feedback</td><td>Robert Brown</td><td>2026-05-15</td><td>⏳ Pending</td></tr>
</table>
</section>
<section><h3>6. Implementation Plan</h3>
<ul>
<li><strong>Jan 15 – Feb 14:</strong> Define & Measure — data collection, Cpk baseline, fishbone</li>
<li><strong>Feb 15 – Mar 14:</strong> Analyze — root cause confirmation, coupling replacement</li>
<li><strong>Mar 15 – Apr 30:</strong> Improve — SPC implementation, supplier qualification</li>
<li><strong>May 1 – May 15:</strong> Control — CONTROL plan, SOP update, handover to operations</li>
</ul>
</section>
<section><h3>7. Follow-up / KPIs</h3>
<ul>
<li>Weekly Cpk torque (target ≥1.33)</li>
<li>Torque OOC events/week (target 0)</li>
<li>L2 rejection rate from torque (target <0.05%)</li>
<li>Customer complaints (target 0)</li>
</ul>
</section>
<section><h3>8. Results</h3>
<p style="background:#cce5ff;padding:0.75rem;border-radius:4px">🔄 <strong>In progress — Phase: IMPROVE (as of March 2026).</strong> Coupling replaced; Cpk improved to 0.98 post-repair. SPC implementation in progress. Full results expected May 2026.</p>
</section>
</article>""",
            # Doc 1: SMED Best Practice (completed)
            """<article class="a3-document">
<h2>A3: Changeover Standardization — SMED Best Practice (Global Benchmark)</h2>
<p><strong>Author:</strong> Robert Brown &nbsp;|&nbsp; <strong>Site:</strong> Indianapolis &nbsp;|&nbsp; <strong>Date:</strong> 2025-07-01</p>
<hr>
<section><h3>1. Background</h3>
<p>Indianapolis identified changeover time as the primary OEE loss driver in 2024. Average changeover was 45 minutes across all 3 lines, with high variability (28–68 min). A structured SMED project was launched to establish Indianapolis as the global benchmark for changeover excellence.</p>
</section>
<section><h3>2. Current Condition</h3>
<ul>
<li>Average changeover: 45 min (range: 28–68 min)</li>
<li>OEE loss from changeovers: ~4.2% annually</li>
<li>~3.5 changeovers/week per line = 157 min/week lost per line</li>
<li>No standardized kit or sequence — each operator follows own routine</li>
</ul>
</section>
<section><h3>3. Goal</h3>
<p>Reduce average changeover to <strong>≤25 minutes</strong> with ≤5 min variability across all shifts and operators by November 30, 2025.</p>
</section>
<section><h3>4. Root Cause Analysis</h3>
<ul>
<li>60% of changeover time is internal (machine stopped) but convertible to external</li>
<li>No pre-staged kits — operators source parts during changeover (+12 min average)</li>
<li>No standardized sequence — significant variation between operators</li>
<li>No visual management to track changeover progress in real-time</li>
</ul>
</section>
<section><h3>5. Countermeasures</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Action</th><th>Owner</th><th>Date</th><th>Status</th></tr>
<tr><td style="padding:0.4rem">Create color-coded changeover kits per format (12 formats)</td><td>Robert Brown</td><td>2025-08-31</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Convert internal→external activities (video analysis)</td><td>Jennifer Taylor</td><td>2025-09-15</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Develop standardized SOP v2.3 with timed sequence</td><td>Sarah Wilson</td><td>2025-10-01</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Install digital timer display at each line changeover station</td><td>Michael Davis</td><td>2025-10-31</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Train all operators — OJT sign-off required</td><td>Jennifer Taylor</td><td>2025-11-15</td><td>✅ Done</td></tr>
</table>
</section>
<section><h3>6. Implementation Plan</h3>
<ul>
<li><strong>Jul–Aug 2025:</strong> SMED analysis, video recording, waste identification</li>
<li><strong>Sep 2025:</strong> Kit design and external conversion trials</li>
<li><strong>Oct 2025:</strong> SOP drafting, digital timer installation</li>
<li><strong>Nov 2025:</strong> Full rollout, operator training, measurement</li>
</ul>
</section>
<section><h3>7. Follow-up KPIs</h3>
<ul>
<li>Average changeover time per line per week</li>
<li>Changeover time standard deviation (target ≤5 min)</li>
<li>OEE improvement attributed to changeover reduction</li>
</ul>
</section>
<section><h3>8. Results</h3>
<p style="background:#d4edda;padding:0.75rem;border-radius:4px">✅ <strong>Project completed November 15, 2025 — GLOBAL BEST PRACTICE.</strong></p>
<ul>
<li>Average changeover: 45 min → <strong>22 min</strong> (51% reduction)</li>
<li>Variability: 28–68 min → <strong>18–26 min</strong></li>
<li>Annual hours recovered: <strong>180 h/year across 3 lines</strong></li>
<li>OEE improvement: <strong>+3.8 pp</strong></li>
<li>This methodology is now being deployed to Alcobendas (Q2 2026)</li>
</ul>
</section>
</article>""",
        ],

        "fegersheim": [
            # Doc 0: A3 sérialisation (in_progress)
            """<article class="a3-document">
<h2>A3: Amélioration OEE ligne sérialisation — Résolution erreurs caméra 2D</h2>
<p><strong>Auteur:</strong> Claire Rousseau &nbsp;|&nbsp; <strong>Site:</strong> Fegersheim &nbsp;|&nbsp; <strong>Date:</strong> 2026-02-01</p>
<hr>
<section><h3>1. Background / Contexte</h3>
<p>La ligne 1 de Fegersheim rencontre des erreurs de lecture répétées dans le module de sérialisation (caméra 2D Track &amp; Trace). Avec une fréquence de 3,5 arrêts par semaine, ce problème est le premier contributeur aux pertes d'OEE sur cette ligne. Une analyse préliminaire révèle une similitude avec un problème identifié sur le site d'Alcobendas.</p>
</section>
<section><h3>2. État Actuel</h3>
<ul>
<li>Fréquence d'arrêts: 3,5/semaine sur le module sérialisation</li>
<li>Durée moyenne par arrêt: 18 minutes (nettoyage + redémarrage + revalidation)</li>
<li>Temps perdu: ~63 min/semaine (~1.260 unités perdues)</li>
<li>Impact OEE L1: -1,3 pp (contribution majeure à l'OEE actuel de 79%)</li>
<li>Note: Alcobendas a identifié la condensation comme cause racine sur une caméra similaire</li>
</ul>
</section>
<section><h3>3. Objectif</h3>
<p>Réduire les arrêts liés à la sérialisation de <strong>3,5/semaine à ≤0,5/semaine</strong> avant le 30 juin 2026. Récupérer ≥54 min de production hebdomadaire.</p>
</section>
<section><h3>4. Analyse des Causes Racines — 5 Pourquoi</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
Pourquoi la caméra génère-t-elle des erreurs de lecture ?
  → Parce que l'objectif est souillé au moment de la défaillance
    Pourquoi l'objectif est-il souillé ?
      → Parce que de la condensation se forme sur la surface froide de l'objectif
        Pourquoi y a-t-il condensation ?
          → Parce que la salle ISO 7 est à 18-20°C et l'optique se refroidit lors des arrêts
            Pourquoi n'y a-t-il pas de protection contre la condensation ?
              → Parce que la configuration d'origine ne prévoyait pas de purge d'air sec
                → CAUSE RACINE: Absence de purge d'air sec sur le module caméra (même cause qu'Alcobendas)
  → CAUSE SECONDAIRE: Protocole de nettoyage hebdomadaire insuffisant — devrait être journalier
</pre>
</section>
<section><h3>5. Contre-mesures</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Action</th><th>Responsable</th><th>Date</th><th>Statut</th></tr>
<tr><td style="padding:0.4rem">Installer purge d'air sec sur module caméra L1</td><td>François Moreau</td><td>2026-03-15</td><td>✅ Fait</td></tr>
<tr><td style="padding:0.4rem">Mettre en place nettoyage optique journalier (SOP mise à jour)</td><td>Sophie Lefebvre</td><td>2026-02-28</td><td>✅ Fait</td></tr>
<tr><td style="padding:0.4rem">Installer capteur T°/humidité dans le module sérialisation</td><td>François Moreau</td><td>2026-04-30</td><td>🔄 En cours</td></tr>
<tr><td style="padding:0.4rem">Partager solution avec Alcobendas (cross-site learning)</td><td>Claire Rousseau</td><td>2026-03-31</td><td>✅ Fait</td></tr>
<tr><td style="padding:0.4rem">Valider résultats — mesure OEE pendant 8 semaines</td><td>Claire Rousseau</td><td>2026-06-30</td><td>⏳ En attente</td></tr>
</table>
</section>
<section><h3>6. Plan d'implémentation</h3>
<ul>
<li><strong>Fév 1–14:</strong> Analyse détaillée, confirmation cause racine, benchmark Alcobendas</li>
<li><strong>Fév 15 – Mar 15:</strong> Installation purge air sec + mise à jour SOP nettoyage</li>
<li><strong>Avr–Mai 2026:</strong> Installation capteur T°/humidité, suivi des métriques</li>
<li><strong>Juin 2026:</strong> Validation des résultats, clôture A3</li>
</ul>
</section>
<section><h3>7. Suivi / KPIs</h3>
<ul>
<li>Arrêts sérialisation/semaine (cible ≤0,5)</li>
<li>OEE L1 mensuel (cible +1,3 pp)</li>
<li>Humidité relative dans le module (cible &lt;60% HR)</li>
</ul>
</section>
<section><h3>8. Résultats</h3>
<p style="background:#cce5ff;padding:0.75rem;border-radius:4px">🔄 <strong>En cours — Phase installation contre-mesures (mars 2026).</strong> Purge air sec installée. Premiers résultats: arrêts réduits à 1,2/semaine. Suivi en cours pendant 8 semaines.</p>
</section>
</article>""",
            # Doc 1: 5Why étiquettes
            """<article class="a3-document">
<h2>Analyse 5 Pourquoi: Problème d'Adhérence des Étiquettes à Basse Température</h2>
<p><strong>Auteur:</strong> Sophie Lefebvre &nbsp;|&nbsp; <strong>Site:</strong> Fegersheim &nbsp;|&nbsp; <strong>Date:</strong> 2026-02-15</p>
<hr>
<section><h3>1. Background / Contexte</h3>
<p>Depuis janvier 2026, la ligne 3 de Fegersheim enregistre des non-conformités d'étiquetage lors des périodes où la température ambiante de la salle de production descend en dessous de 18°C. Le taux de non-conformité atteint 0,8% contre un objectif de 0,1%.</p>
</section>
<section><h3>2. État Actuel</h3>
<ul>
<li>Fréquence: 2 incidents/semaine en période hivernale</li>
<li>Taux de non-conformité étiquetage: 0,8% (objectif: 0,1%)</li>
<li>Réclamations client potentielles: 1 en janvier 2026 (décollement étiquette)</li>
<li>Température salle en hiver: 16-19°C (spec procédé: 18-24°C)</li>
</ul>
</section>
<section><h3>3. Objectif</h3>
<p>Éliminer les non-conformités d'étiquetage liées à la température et ramener le taux à <strong>≤0,1%</strong> avant le 30 avril 2026.</p>
</section>
<section><h3>4. Analyse 5 Pourquoi</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
Pourquoi les étiquettes se décollent-elles ?
  → Parce que la colle ne polymérise pas correctement sur le flacon
    Pourquoi la colle ne polymérise pas ?
      → Parce que la température du flacon est inférieure à 18°C au moment de l'étiquetage
        Pourquoi le flacon est-il trop froid ?
          → Parce que les flacons viennent directement du stockage à 15°C sans préchauffage
            Pourquoi n'y a-t-il pas de préchauffage ?
              → Parce que la ligne a été conçue pour T° ambiante ≥18°C et cette condition n'est pas toujours respectée
                → CAUSE RACINE 1: Colle non adaptée aux conditions réelles de température de la salle
                → CAUSE RACINE 2: Absence de contrôle T° des flacons avant étiquetage
</pre>
</section>
<section><h3>5. Contre-mesures</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Action</th><th>Responsable</th><th>Date</th><th>Statut</th></tr>
<tr><td style="padding:0.4rem">Qualifier colle basse température (ref. HM-LT2000)</td><td>Sophie Lefebvre</td><td>2026-03-31</td><td>🔄 En cours</td></tr>
<tr><td style="padding:0.4rem">Installer tunnel de préchauffage flacons avant étiquetage</td><td>François Moreau</td><td>2026-04-15</td><td>⏳ En attente</td></tr>
<tr><td style="padding:0.4rem">Ajouter alarme T° ambiante &lt;18°C sur HMI ligne 3</td><td>François Moreau</td><td>2026-03-15</td><td>✅ Fait</td></tr>
<tr><td style="padding:0.4rem">Mettre à jour SOP étiquetage avec exigence T° min</td><td>Sophie Lefebvre</td><td>2026-04-30</td><td>⏳ En attente</td></tr>
</table>
</section>
<section><h3>6. Plan d'implémentation</h3>
<ul>
<li><strong>Fév 15 – Mar 15:</strong> Qualification colle basse température en laboratoire</li>
<li><strong>Mar 16 – Avr 14:</strong> Essais industriels colle + installation alarme T°</li>
<li><strong>Avr 15 – Avr 30:</strong> Installation tunnel préchauffage + validation, mise à jour SOP</li>
</ul>
</section>
<section><h3>7. Suivi / KPIs</h3>
<ul>
<li>Taux de non-conformité étiquetage/semaine (cible ≤0,1%)</li>
<li>Température ambiante salle de production (alarme si &lt;18°C)</li>
<li>Réclamations client liées à l'étiquetage (cible 0)</li>
</ul>
</section>
<section><h3>8. Résultats</h3>
<p style="background:#cce5ff;padding:0.75rem;border-radius:4px">🔄 <strong>En cours — Phase qualification colle (mars 2026).</strong> Alarme T° installée. Qualification colle HM-LT2000 en cours au laboratoire.</p>
</section>
</article>""",
        ],

        "sesto": [
            # Doc 0: A3 scarti peso (in_progress)
            """<article class="a3-document">
<h2>A3: Riduzione Scarti per Peso Fuori Tolleranza — Linea 1</h2>
<p><strong>Autore:</strong> Chiara Ricci &nbsp;|&nbsp; <strong>Sito:</strong> Sesto S.G. &nbsp;|&nbsp; <strong>Data:</strong> 2026-02-10</p>
<hr>
<section><h3>1. Background / Contesto</h3>
<p>La linea 1 dello stabilimento di Sesto S.G. presenta un tasso di scarto per peso fuori tolleranza superiore all'1,5%, ben al di sopra dell'obiettivo dello 0,5%. Il problema causa perdite dirette di prodotto e aumenta il rischio di reclami da parte del cliente finale.</p>
</section>
<section><h3>2. Condizione Attuale</h3>
<ul>
<li>Tasso di scarto per peso: 1,5% (obiettivo: ≤0,5%)</li>
<li>Unità scartate stimate: ~15.000/mese</li>
<li>Costo diretto stimato: €18.000/mese (costo prodotto + rilavorazione)</li>
<li>Frequenza: 2 eventi significativi/settimana (deriva &gt;±3σ)</li>
<li>Il problema si manifesta principalmente dopo 4 ore di funzionamento continuo</li>
</ul>
</section>
<section><h3>3. Obiettivo</h3>
<p>Ridurre il tasso di scarto per peso da 1,5% a <strong>≤0,5%</strong> entro il 31 maggio 2026, con un risparmio atteso di ≥€12.000/mese.</p>
</section>
<section><h3>4. Analisi delle Cause Radice — Diagramma Ishikawa</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
PROBLEMA: Tasso di scarto per peso &gt;1,5% su Linea 1

MACCHINA:
  → Deriva del sensore bilancia dopo 4h di funzionamento (confermato da test)
  → Coefficiente di deriva: +0,8g/h a T° &gt;22°C
  → Nessun sistema di auto-calibrazione durante la produzione

METODO:
  → Ricalibrazione bilancia solo una volta per turno (ogni 8h)
  → Assenza di carta di controllo SPC per il peso
  → SOP P-W-001 obsoleto (versione 2021 — non aggiornato post-upgrade bilancia)

MATERIALE:
  → Variabilità densità del granulato: ±2,1% tra lotti (spec: ±1,5%)
  → Cambio fornitore granulato in Q3 2025 non documentato formalmente

AMBIENTE:
  → Temperatura sala produzione: 18-26°C — influenza diretta sulla deriva bilancia
  → Nessun sistema di climatizzazione dedicato alla zona pesatura

ROOT CAUSE PRIMARIA: Deriva termica del sensore bilancia non compensata
ROOT CAUSE SECONDARIA: Variabilità del materiale in ingresso superiore alle specifiche
</pre>
</section>
<section><h3>5. Contromisure</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Azione</th><th>Responsabile</th><th>Data</th><th>Stato</th></tr>
<tr><td style="padding:0.4rem">Aumentare frequenza ricalibrazione bilancia a ogni 2h</td><td>Marco Rossi</td><td>2026-02-20</td><td>✅ Fatto</td></tr>
<tr><td style="padding:0.4rem">Implementare carta di controllo SPC per peso (X-bar/R)</td><td>Laura Colombo</td><td>2026-03-15</td><td>🔄 In corso</td></tr>
<tr><td style="padding:0.4rem">Valutare sostituzione con bilancia termocompensata</td><td>Chiara Ricci</td><td>2026-04-30</td><td>⏳ In attesa</td></tr>
<tr><td style="padding:0.4rem">Audit fornitore granulato — richiesta riduzione variabilità a ±1%</td><td>Laura Colombo</td><td>2026-04-15</td><td>⏳ In attesa</td></tr>
<tr><td style="padding:0.4rem">Aggiornare SOP P-W-001 con nuove frequenze e soglie SPC</td><td>Chiara Ricci</td><td>2026-05-31</td><td>⏳ In attesa</td></tr>
</table>
</section>
<section><h3>6. Piano di Implementazione</h3>
<ul>
<li><strong>10-28 Feb:</strong> Diagnosi, raccolta dati, conferma causa radice, prima contromisura (ricalibrazione ogni 2h)</li>
<li><strong>1-31 Mar:</strong> Implementazione SPC, formazione operatori</li>
<li><strong>Apr 2026:</strong> Valutazione bilancia termocompensata, audit fornitore</li>
<li><strong>Mag 2026:</strong> Validazione risultati, aggiornamento SOP, chiusura A3</li>
</ul>
</section>
<section><h3>7. Follow-up / KPI</h3>
<ul>
<li>Tasso di scarto per peso settimanale (obiettivo ≤0,5%)</li>
<li>Cpk peso L1 (obiettivo ≥1,33)</li>
<li>Costo mensile degli scarti (obiettivo ≤€6.000)</li>
</ul>
</section>
<section><h3>8. Risultati</h3>
<p style="background:#cce5ff;padding:0.75rem;border-radius:4px">🔄 <strong>In corso — fase implementazione SPC (marzo 2026).</strong> Dopo aumento frequenza ricalibrazione: tasso scarto ridotto da 1,5% a 1,1%. Implementazione SPC in corso. Risultati completi attesi maggio 2026.</p>
</section>
</article>""",
            # Doc 1: Kaizen pick-and-place (planned)
            """<article class="a3-document">
<h2>Kaizen: Eliminazione Guasti Pick-and-Place — Linea 2</h2>
<p><strong>Autore:</strong> Francesco Romano &nbsp;|&nbsp; <strong>Sito:</strong> Sesto S.G. &nbsp;|&nbsp; <strong>Data:</strong> 2026-03-10</p>
<hr>
<section><h3>1. Background / Contesto</h3>
<p>Il sistema pick-and-place della linea 2 genera guasti ricorrenti a causa del deterioramento delle ventose in silicone. Con una frequenza di 3,5 guasti/settimana e una durata media di 15 minuti per intervento, questa è la seconda causa di perdita di OEE sulla linea 2 di Sesto.</p>
</section>
<section><h3>2. Condizione Attuale</h3>
<ul>
<li>Frequenza guasti: 3,5/settimana</li>
<li>Tempo medio per intervento: 15 minuti</li>
<li>Tempo produzione perso: ~52 min/settimana</li>
<li>Intervallo attuale sostituzione ventose: su guasto (reattivo)</li>
<li>Costo ventose: €12/set × 3,5 rip/settimana = €42/settimana</li>
</ul>
</section>
<section><h3>3. Obiettivo</h3>
<p>Ridurre i guasti del pick-and-place da 3,5/settimana a <strong>≤0,5/settimana</strong> attraverso un approccio di manutenzione preventiva strutturato nell'evento Kaizen del 14-16 aprile 2026.</p>
</section>
<section><h3>4. Analisi Preliminare delle Cause</h3>
<ul>
<li>Le ventose si deteriorano principalmente per cicli termici (T° 18-35°C durante pulizia)</li>
<li>Micro-fessure visibili a 4-5 settimane dall'installazione</li>
<li>Nessun piano di sostituzione preventiva — solo su rottura</li>
<li>Assenza di ispezione visiva programmata</li>
</ul>
</section>
<section><h3>5. Contromisure Proposte</h3>
<ul>
<li>Implementare sostituzione preventiva ventose ogni 6 settimane</li>
<li>Introdurre ispezione visiva settimanale (10 min) documentata</li>
<li>Valutare ventose in poliuretano (maggiore resistenza termica)</li>
<li>Creare kit di sostituzione rapida pronto in linea</li>
</ul>
</section>
<section><h3>6. Piano di Implementazione</h3>
<ul>
<li><strong>Giorno 1 (14 Apr):</strong> Analisi dettagliata guasti, misura tempi, identificazione sprechi</li>
<li><strong>Giorno 2 (15 Apr):</strong> Test ventose in poliuretano, progettazione kit sostituzione rapida</li>
<li><strong>Giorno 3 (16 Apr):</strong> Implementazione protocollo preventivo, formazione operatori, standardizzazione</li>
<li><strong>Post-Kaizen:</strong> Follow-up settimanale per 8 settimane</li>
</ul>
</section>
<section><h3>7. Follow-up / KPI</h3>
<ul>
<li>Guasti pick-and-place/settimana (obiettivo ≤0,5)</li>
<li>Costo ventose settimanale (obiettivo ≤€10)</li>
<li>OEE L2 (contributo atteso +0,9 pp)</li>
</ul>
</section>
<section><h3>8. Risultati</h3>
<p style="background:#fff3cd;padding:0.75rem;border-radius:4px">⏳ <strong>Evento Kaizen pianificato per 14-16 aprile 2026. In attesa di esecuzione.</strong></p>
</section>
</article>""",
        ],
    }

    # Insert initiatives and documents
    for idx, ini in enumerate(INITIATIVES.get(site_id, [])):
        linked_id = None
        if ini["linked_prob_idx"] is not None and ini["linked_prob_idx"] < len(prob_ids):
            linked_id = prob_ids[ini["linked_prob_idx"]]

        cur = conn.execute(
            """INSERT INTO improvement_initiatives
               (site_id, line_number, title, description, methodology, status,
                owner, start_date, target_date, completion_date,
                expected_benefit, actual_benefit, linked_problem_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                site_id, ini["line"], ini["title"], ini["desc"],
                ini["method"], ini["status"], ini["owner"],
                ini["start"], ini["target"], ini.get("completion"),
                ini.get("benefit_exp"), ini.get("benefit_act"), linked_id,
            ),
        )
        init_id = cur.lastrowid

        # Insert A3 document if we have one for this initiative index
        docs = A3_DOCS.get(site_id, [])
        if idx < len(docs):
            conn.execute(
                """INSERT INTO initiative_documents
                   (initiative_id, document_type, title, content_html, author)
                   VALUES (?,?,?,?,?)""",
                (init_id, "A3", ini["title"], docs[idx], ini["owner"]),
            )

    conn.commit()


def migrate_legacy_db() -> None:
    """Copia opex.db → site_alcobendas.db si aún no existe."""
    src = "opex.db"
    dst = SITES["alcobendas"]["db_path"]
    if os.path.exists(src) and not os.path.exists(dst):
        _safe_print(f"  [>>] Migrando {src} -> {dst}")
        shutil.copy2(src, dst)
        _safe_print(f"  [ok] Migracion completada")


def _seed_alert_rules() -> None:
    """Inserta reglas de alerta por defecto en la BD del DEFAULT_SITE (una sola vez)."""
    db_path = SITES[DEFAULT_SITE]["db_path"]
    conn = sqlite3.connect(db_path)
    existing = conn.execute("SELECT COUNT(*) FROM alert_rules").fetchone()[0]
    if existing >= 8:
        conn.close()
        return

    rules = [
        # OEE crítico < 60%
        ("OEE crítico — por debajo del 60%", "oee", "less_than", 60.0, "critical",
         '["app","teams","email"]', 60),
        # OEE bajo < 75%
        ("OEE bajo — por debajo del 75%", "oee", "less_than", 75.0, "warning",
         '["app","teams"]', 30),
        # Tasa de rechazo crítica > 5%
        ("Tasa de rechazo crítica — superior al 5%", "reject_rate", "greater_than", 5.0, "critical",
         '["app","teams","email"]', 60),
        # Tasa de rechazo advertencia > 2%
        ("Tasa de rechazo elevada — superior al 2%", "reject_rate", "greater_than", 2.0, "warning",
         '["app"]', 20),
        # Parada larga > 10 min
        ("Parada de línea prolongada — más de 10 min", "downtime", "greater_than", 10.0, "critical",
         '["app","teams","email"]', 45),
        # Parada corta > 5 min
        ("Parada de línea — más de 5 min", "downtime", "greater_than", 5.0, "warning",
         '["app","teams"]', 15),
        # Velocidad de línea < 80% nominal (se evalúa como % de nominal)
        ("Velocidad de línea baja — por debajo del 80% del nominal", "line_speed",
         "less_than", 80.0, "warning", '["app"]', 20),
        # Tiempo de ciclo VSM > 120% nominal
        ("Tiempo de ciclo VSM elevado — superior al 120% del nominal", "cycle_time",
         "greater_than", 120.0, "warning", '["app"]', 15),
    ]

    conn.execute("DELETE FROM alert_rules")
    conn.executemany(
        """INSERT INTO alert_rules
           (name, metric, operator, threshold_value, severity,
            notification_channels, cooldown_minutes)
           VALUES (?,?,?,?,?,?,?)""",
        rules,
    )
    conn.commit()
    conn.close()
    _safe_print("  [ok] Reglas de alerta por defecto insertadas")


def seed_all_sites(force: bool = False) -> None:
    """Inicializa todas las plantas. Migra opex.db si procede."""
    _safe_print("[ seed_sites ] Iniciando generacion de datos multi-planta...")
    migrate_legacy_db()
    for site_id in SITES:
        seed_site(site_id, force=force)
    _seed_alert_rules()
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
