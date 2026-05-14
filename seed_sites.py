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
        # 3 operadores por línea (L1: blísteres, L2: viales, L3: sobres)
        # + 1 calidad + 1 mantenimiento + 1 supervisor = 12 en total
        "operators": [
            # Línea 1 — blísteres
            ("Pedro García",      "operator",    "ALB-001"),
            ("Marta Sánchez",     "operator",    "ALB-002"),
            ("Javier Ruiz",       "operator",    "ALB-003"),
            # Línea 2 — viales
            ("María López",       "operator",    "ALB-004"),
            ("Carlos Martínez",   "operator",    "ALB-005"),
            ("Lucía Herrero",     "operator",    "ALB-006"),
            # Línea 3 — sobres
            ("Raúl Moreno",       "operator",    "ALB-007"),
            ("Cristina Jiménez",  "operator",    "ALB-008"),
            ("Sergio Navarro",    "operator",    "ALB-009"),
            # Roles de soporte
            ("Ana Rodríguez",     "quality",     "ALB-010"),
            ("José Fernández",    "maintenance", "ALB-011"),
            ("Isabel Torres",     "supervisor",  "ALB-012"),
        ],
        # OEE objetivo ~82%: Disponibilidad 92%, Rendimiento 91%, Calidad 98%
        # Problema recurrente de atasco en etiquetadora → downtime elevado
        "downtime_range":  (25, 58),   # min/turno — atasco etiquetadora aumenta paradas
        "speed_range":     (940, 1155),
        "reject_rate":     0.020,
        "co_range":        (45, 68),   # min changeover — cambios de formato lentos
        "comments": {
            "production": [
                "Atasco en etiquetadora automática — parada de {min} min, reinicio manual",
                "Cambio de formato L{min} completado con retraso: piezas no preconfiguradas",
                "Atasco recurrente en rodillos de avance de etiquetadora, limpieza correctiva",
                "Velocidad reducida al 85% por acumulación en estuchadora, se recupera en turno",
                "Cambio de lote iniciado sin anomalías, sin paradas significativas",
                "Recuperación tras micro-parada en selladora; velocidad nominal al cabo de 10 min",
                "Turno con buen ritmo de producción tras resolver atasco inicial en etiquetadora",
                "Cambio de formato lento ({min} min) — herramientas no preasignadas en carro",
            ],
            "quality": [
                "Calibración de balanza completada, dentro de especificación",
                "Control de peso: 2 unidades fuera de rango (±2%), rechazadas y documentadas",
                "Verificación de serialización correcta al 100%",
                "Revisión de etiquetas: adhesivo insuficiente en 3 unidades, corregido",
                "Control de hermeticidad conforme en blísteres de turno",
                "Registro de temperatura de sellado dentro de rango especificado",
                "Inspección de cierre de viales: todo conforme, sin desviaciones",
            ],
            "maintenance": [
                "Limpieza de rodillos de avance de etiquetadora completada (cada 4h según SOP)",
                "Sustitución de guía de papel en etiquetadora — desgaste detectado en inspección",
                "Ajuste de sensor de nivel de llenado en viales, verificado OK",
                "Lubricación de cadena transportadora realizada según plan preventivo",
                "Cambio de O-ring en bomba de llenado (desgaste en inspección de turno)",
                "Tensión de correa ajustada en encajadora — vibración reducida",
                "Fallo intermitente en selladora corregido; se monitoriza en próximo turno",
            ],
            "safety": [
                "Revisión de EPIs completada al inicio de turno, todo conforme",
                "Zona de trabajo limpia y ordenada — 5S OK tras cambio de formato",
                "Derrame menor en zona de llenado: contenido, limpiado y notificado",
            ],
        },
        "co_comment": "Cambio de formato completado en {min} min — tiempo superior al objetivo (<40 min)",
    },

    "indianapolis": {
        # 3 operators per line (L1: autoinjectors, L2: insulin pens, L3: vials)
        # + 1 quality + 1 maintenance + 1 supervisor = 12 total
        "operators": [
            # Line 1 — autoinjectors
            ("James Carter",     "operator",    "IND-001"),
            ("Emily Johnson",    "operator",    "IND-002"),
            ("Michael Davis",    "operator",    "IND-003"),
            # Line 2 — insulin pens
            ("Sarah Wilson",     "operator",    "IND-004"),
            ("Robert Brown",     "operator",    "IND-005"),
            ("Patricia Moore",   "operator",    "IND-006"),
            # Line 3 — vials
            ("Christopher Lee",  "operator",    "IND-007"),
            ("Amanda Harris",    "operator",    "IND-008"),
            ("Daniel Thompson",  "operator",    "IND-009"),
            # Support roles
            ("Karen Martinez",   "quality",     "IND-010"),
            ("Steven Anderson",  "maintenance", "IND-011"),
            ("Jennifer Taylor",  "supervisor",  "IND-012"),
        ],
        # OEE target ~88%: Availability 95%, Performance 94%, Quality 98.5%
        # Benchmark site for changeover — SMED fully deployed (avg 45 min)
        # Recurring issue: intermittent 2D camera read errors in serialization module
        "downtime_range":  (12, 32),   # min/12h shift
        "speed_range":     (1055, 1195),
        "reject_rate":     0.015,
        "co_range":        (38, 55),   # benchmark changeover ~45 min average
        # ── Indianapolis-specific: 12-hour shifts (day 06:00-18:00, night 18:00-06:00) ──
        "shift_config":    {"day": 6, "night": 18},
        "shift_hours":     12,
        "kpi_hours":       [3, 7, 11],   # 3 readings spread across 12h shift
        "target_units":    14400,
        "planned_time_min": 720.0,
        "comment_range":   (15, 700),
        "comments": {
            "production": [
                "SMED changeover completed in {min} min — color-coded kit, within target",
                "Pre-staged changeover kit ready, transition smooth and on time",
                "Serialization module: 2D camera read error — line stopped {min} min, camera cleaned and restarted",
                "Intermittent serialization reject at L{min} station — 4 units reprocessed, root cause under review",
                "Line running at nominal speed, all targets green on visual management board",
                "Production ahead of schedule this shift — excellent teamwork",
                "Changeover kit restocked after format change, area 5S verified",
                "Minor slowdown at filling station resolved — nominal speed recovered in 8 min",
            ],
            "quality": [
                "Weight check within spec limits — zero rejects this reading",
                "Serialization verification: 3 units rejected due to camera misread — reprocessed OK",
                "Inline QC check per SOP v2.3 — all results within limits",
                "Hermetic seal test: all autoinjector units passed",
                "Label adhesion check: all vials compliant",
                "Right First Time 98.5% this shift — above monthly target",
                "Torque closure SPC control chart in limits — Cpk 1.41",
            ],
            "maintenance": [
                "Serialization camera lens cleaned — adhesion residue found, SOP updated",
                "Preventive maintenance completed per TPM schedule, no issues found",
                "Conveyor belt tension adjusted proactively — vibration reduced",
                "Filling nozzle cleaned, no leaks or residue detected",
                "Predictive maintenance alert resolved — conveyor bearing replaced",
                "Changeover kit trolley restocked and verified for next format",
            ],
            "safety": [
                "Safety walkthrough completed at shift start — all clear",
                "5S area audit passed — score 4.8/5",
                "PPE check: all operators compliant before line start",
                "Near-miss report submitted: spillage at filling station, cleaned immediately",
            ],
        },
        "co_comment": "SMED changeover: {min} min — color-coded kit, SOP v2.3 followed",
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
                   CHECK(shift_type IN ('morning','afternoon','night','day')),
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
CREATE TABLE IF NOT EXISTS sqdcp_actions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    line_number  INTEGER NOT NULL CHECK(line_number BETWEEN 1 AND 20),
    action_date  TEXT NOT NULL DEFAULT (date('now')),
    pillar       TEXT NOT NULL CHECK(pillar IN ('S','Q','D','C','P')),
    title        TEXT NOT NULL CHECK(length(title) > 0 AND length(title) <= 300),
    owner        TEXT NOT NULL DEFAULT '',
    deadline     TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'open'
                 CHECK(status IN ('open','in_progress','done','blocked')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sqdcp_line_date ON sqdcp_actions(line_number, action_date);
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
    status           TEXT NOT NULL DEFAULT 'No iniciado'
                     CHECK(status IN ('No iniciado','En progreso','Terminado','Cancelado')),
    category         TEXT NOT NULL DEFAULT 'Quality'
                     CHECK(category IN ('Safety','Quality','Delivery','Cost','People')),
    owner            TEXT NOT NULL,
    start_date       TEXT NOT NULL,
    target_date      TEXT NOT NULL,
    completion_date  TEXT,
    expected_benefit TEXT,
    actual_benefit   TEXT,
    linked_problem_id INTEGER REFERENCES top_problems(id) ON DELETE SET NULL,
    deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    deleted_by       TEXT,
    deletion_reason  TEXT
);
CREATE TABLE IF NOT EXISTS initiative_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    initiative_id INTEGER NOT NULL REFERENCES improvement_initiatives(id) ON DELETE CASCADE,
    field_changed TEXT NOT NULL,
    old_value     TEXT,
    new_value     TEXT,
    changed_by    TEXT NOT NULL,
    changed_at    TEXT NOT NULL DEFAULT (datetime('now'))
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
CREATE INDEX IF NOT EXISTS idx_audit_log_init      ON initiative_audit_log(initiative_id);
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

CREATE TABLE IF NOT EXISTS kaizen_reports (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id            TEXT NOT NULL,
    report_text        TEXT NOT NULL,
    opportunities_json TEXT NOT NULL DEFAULT '[]',
    model_used         TEXT NOT NULL DEFAULT 'unknown',
    source             TEXT NOT NULL DEFAULT 'mock'
                       CHECK(source IN ('gateway','mock')),
    generated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    read_at            TEXT
);
CREATE INDEX IF NOT EXISTS idx_kaizen_reports_site ON kaizen_reports(site_id);
CREATE INDEX IF NOT EXISTS idx_kaizen_reports_ts   ON kaizen_reports(generated_at);
CREATE TABLE IF NOT EXISTS tiers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id     TEXT NOT NULL,
    tier_level  INTEGER NOT NULL CHECK(tier_level IN (0,1,2)),
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS tier_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id     TEXT NOT NULL,
    tier_id     INTEGER NOT NULL REFERENCES tiers(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    group_type  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS tier_group_assignments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_group_id INTEGER NOT NULL REFERENCES tier_groups(id) ON DELETE CASCADE,
    child_group_id  INTEGER NOT NULL REFERENCES tier_groups(id) ON DELETE CASCADE,
    assigned_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(parent_group_id, child_group_id)
);
CREATE TABLE IF NOT EXISTS tier_group_members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES tier_groups(id) ON DELETE CASCADE,
    operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('leader','member','support')),
    assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(group_id, operator_id)
);
CREATE TABLE IF NOT EXISTS escalation_paths (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id                     TEXT NOT NULL,
    from_group_id               INTEGER NOT NULL REFERENCES tier_groups(id) ON DELETE CASCADE,
    to_group_id                 INTEGER NOT NULL REFERENCES tier_groups(id) ON DELETE CASCADE,
    escalation_type             TEXT NOT NULL DEFAULT 'general'
                                CHECK(escalation_type IN ('quality','maintenance','safety','production','general')),
    auto_escalate_after_minutes INTEGER,
    notification_channel        TEXT NOT NULL DEFAULT 'app'
                                CHECK(notification_channel IN ('app','teams','email')),
    created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tiers_site       ON tiers(site_id);
CREATE INDEX IF NOT EXISTS idx_tier_groups_tier ON tier_groups(tier_id);
CREATE INDEX IF NOT EXISTS idx_tier_groups_site ON tier_groups(site_id);
CREATE INDEX IF NOT EXISTS idx_tga_parent       ON tier_group_assignments(parent_group_id);
CREATE INDEX IF NOT EXISTS idx_tga_child        ON tier_group_assignments(child_group_id);
CREATE INDEX IF NOT EXISTS idx_tgm_group        ON tier_group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_esc_from         ON escalation_paths(from_group_id);
CREATE TABLE IF NOT EXISTS equipment (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id          TEXT NOT NULL,
    group_id         INTEGER NOT NULL REFERENCES tier_groups(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    equipment_type   TEXT NOT NULL DEFAULT 'other'
                     CHECK(equipment_type IN ('thermoformer','filler','weigher','labeler',
                                              'serializer','cartoner','case_packer',
                                              'palletizer','inspection','other')),
    model            TEXT,
    manufacturer     TEXT,
    serial_number    TEXT,
    status           TEXT NOT NULL DEFAULT 'running'
                     CHECK(status IN ('running','stopped','changeover','maintenance','idle')),
    nominal_speed    REAL,
    installed_date   TEXT,
    last_maintenance TEXT,
    notes            TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_equipment_group  ON equipment(group_id);
CREATE INDEX IF NOT EXISTS idx_equipment_site   ON equipment(site_id);
"""


# ── Datos de Tiers por planta ─────────────────────────────────────────────────

# Estructura: tiers (tier_level_idx, name, description)
#             groups (tier_level_idx, name, description, group_type)
#             assignments [(parent_group_idx, child_group_idx), ...]
#             member_badges {group_idx: [(badge, role), ...]}
#             escalations [(from_idx, to_idx, type, minutes, channel), ...]

TIER_SEED: dict[str, dict] = {
    "alcobendas": {
        "tiers": [
            (0, "Tier 0 — Operadores de Línea",  "Grupos de operadores por línea de producción"),
            (1, "Tier 1 — Equipos de Proceso",   "Equipos multidisciplinares por área de proceso"),
            (2, "Tier 2 — Flujo de Valor",        "Gestión del flujo de valor completo de la planta"),
        ],
        "groups": [
            (0, "Línea 1 - Blísters",      "Línea de envasado de blísteres",        "packaging_line"),
            (0, "Línea 2 - Viales",        "Línea de llenado y cierre de viales",   "packaging_line"),
            (0, "Línea 3 - Sobres",        "Línea de envasado de sobres",           "packaging_line"),
            (1, "Equipo Sólidos Orales",   "Equipo de proceso para sólidos orales", "process_team"),
            (1, "Equipo Inyectables",      "Equipo de proceso para inyectables",    "process_team"),
            (2, "Value Stream Alcobendas", "Flujo de valor completo de Alcobendas", "value_stream"),
        ],
        "assignments": [(3, 0), (3, 2), (4, 1), (5, 3), (5, 4)],
        "member_badges": {
            0: [("ALB-001", "leader"), ("ALB-002", "member"), ("ALB-003", "member")],
            1: [("ALB-004", "leader"), ("ALB-005", "member"), ("ALB-006", "member")],
            2: [("ALB-007", "leader"), ("ALB-008", "member"), ("ALB-009", "member")],
        },
        "escalations": [
            (0, 3, "production", 30, "app"),
            (1, 4, "production", 30, "app"),
            (2, 3, "production", 30, "app"),
            (3, 5, "quality",    60, "teams"),
            (4, 5, "quality",    60, "teams"),
        ],
    },
    "indianapolis": {
        "tiers": [
            (0, "Tier 0 — Line Operators",   "Operator groups by production line"),
            (1, "Tier 1 — Process Teams",    "Cross-functional teams by process area"),
            (2, "Tier 2 — Value Stream",     "Full plant value stream management"),
        ],
        "groups": [
            (0, "Line 1 - Autoinjectors",     "Autoinjector filling and packaging line", "filling_line"),
            (0, "Line 2 - Insulin Pens",      "Insulin pen assembly and packaging line", "filling_line"),
            (0, "Line 3 - Vials",             "Vial filling and packaging line",         "packaging_line"),
            (1, "Injectables Process Team",   "Process team for injectables",            "process_team"),
            (1, "Vials & Packaging Team",     "Process team for vials and packaging",    "process_team"),
            (2, "Indianapolis Value Stream",  "Full Indianapolis value stream",           "value_stream"),
        ],
        "assignments": [(3, 0), (3, 1), (4, 2), (5, 3), (5, 4)],
        "member_badges": {
            0: [("IND-001", "leader"), ("IND-002", "member"), ("IND-003", "member")],
            1: [("IND-004", "leader"), ("IND-005", "member"), ("IND-006", "member")],
            2: [("IND-007", "leader"), ("IND-008", "member"), ("IND-009", "member")],
        },
        "escalations": [
            (0, 3, "production", 30, "app"),
            (1, 3, "production", 30, "app"),
            (2, 4, "production", 30, "app"),
            (3, 5, "quality",    60, "teams"),
            (4, 5, "quality",    60, "teams"),
        ],
    },
    "fegersheim": {
        "tiers": [
            (0, "Tier 0 — Opérateurs de Ligne",  "Groupes d'opérateurs par ligne de production"),
            (1, "Tier 1 — Équipes de Processus", "Équipes pluridisciplinaires par zone de process"),
            (2, "Tier 2 — Flux de Valeur",       "Gestion du flux de valeur complet du site"),
        ],
        "groups": [
            (0, "Ligne 1 - Sérialisation",   "Ligne sérialisation et conditionnement", "packaging_line"),
            (0, "Ligne 2 - Découpe",         "Ligne de découpe aluminium",             "manufacturing_equipment"),
            (0, "Ligne 3 - Étiquetage",      "Ligne d'étiquetage et mise en boîte",    "packaging_line"),
            (1, "Équipe Solides Oraux",      "Équipe process pour solides oraux",       "process_team"),
            (1, "Équipe Liquides",           "Équipe process pour liquides",            "process_team"),
            (2, "Value Stream Fegersheim",   "Flux de valeur complet de Fegersheim",   "value_stream"),
        ],
        "assignments": [(3, 0), (3, 2), (4, 1), (5, 3), (5, 4)],
        "member_badges": {
            0: [("FEG-001", "leader")],
            1: [("FEG-002", "leader")],
            2: [("FEG-003", "leader")],
        },
        "escalations": [
            (0, 3, "production", 30, "app"),
            (1, 4, "production", 30, "app"),
            (2, 3, "production", 30, "app"),
            (3, 5, "quality",    60, "teams"),
        ],
    },
    "sesto": {
        "tiers": [
            (0, "Tier 0 — Operatori di Linea",  "Gruppi di operatori per linea di produzione"),
            (1, "Tier 1 — Team di Processo",    "Team multidisciplinari per area di processo"),
            (2, "Tier 2 — Flusso di Valore",    "Gestione del flusso di valore completo del sito"),
        ],
        "groups": [
            (0, "Linea 1 - Blister",          "Linea di confezionamento blister",         "packaging_line"),
            (0, "Linea 2 - Pick-and-Place",   "Linea pick-and-place e assemblaggio",       "manufacturing_equipment"),
            (0, "Linea 3 - Pallettizzazione", "Linea di pallettizzazione e logistica",     "packaging_line"),
            (1, "Team Confezionamento",       "Team processo confezionamento e blister",   "process_team"),
            (1, "Team Logistica",             "Team processo pallettizzazione e logistica","process_team"),
            (2, "Value Stream Sesto S.G.",    "Flusso di valore completo di Sesto S.G.",   "value_stream"),
        ],
        "assignments": [(3, 0), (3, 1), (4, 2), (5, 3), (5, 4)],
        "member_badges": {
            0: [("SES-001", "leader")],
            1: [("SES-002", "leader")],
            2: [("SES-003", "leader")],
        },
        "escalations": [
            (0, 3, "production", 30, "app"),
            (1, 3, "production", 30, "app"),
            (2, 4, "production", 30, "app"),
            (3, 5, "quality",    60, "teams"),
        ],
    },
    "seishin": {
        "tiers": [
            (0, "Tier 0 — ラインオペレーター", "生産ラインごとのオペレーターグループ"),
            (1, "Tier 1 — プロセスチーム",     "プロセスエリアごとの部門横断チーム"),
            (2, "Tier 2 — バリューストリーム", "サイト全体のバリューストリーム管理"),
        ],
        "groups": [
            (0, "ライン1 - 包装",         "包装ラインオペレーターグループ",             "packaging_line"),
            (0, "ライン2 - 充填",         "充填ラインオペレーターグループ",             "filling_line"),
            (0, "ライン3 - シリアル化",   "シリアル化・検査ラインオペレーターグループ", "packaging_line"),
            (1, "生産チームA",            "包装・充填プロセスチーム",                   "process_team"),
            (1, "生産チームB",            "シリアル化・品質プロセスチーム",             "process_team"),
            (2, "バリューストリーム 星辰", "星辰工場全体のバリューストリーム",           "value_stream"),
        ],
        "assignments": [(3, 0), (3, 1), (4, 2), (5, 3), (5, 4)],
        "member_badges": {
            0: [("SEI-001", "leader")],
            1: [("SEI-002", "leader")],
            2: [("SEI-003", "leader")],
        },
        "escalations": [
            (0, 3, "production", 30, "app"),
            (1, 3, "production", 30, "app"),
            (2, 4, "production", 30, "app"),
            (3, 5, "quality",    60, "teams"),
        ],
    },
}


def _seed_tiers(site_id: str, conn: sqlite3.Connection) -> None:
    """Inserta datos de tiers de ejemplo para una planta. Idempotente."""
    seed = TIER_SEED.get(site_id)
    if not seed:
        return

    existing = conn.execute(
        "SELECT COUNT(*) FROM tiers WHERE site_id=?", (site_id,)
    ).fetchone()[0]
    if existing > 0:
        return

    # 1. Insertar tiers (nivel 0, 1, 2)
    tier_ids: list[int] = []
    for tier_level, name, description in seed["tiers"]:
        cur = conn.execute(
            "INSERT INTO tiers (site_id, tier_level, name, description) VALUES (?,?,?,?)",
            (site_id, tier_level, name, description),
        )
        tier_ids.append(cur.lastrowid)

    # tier_level_idx → tier_id (0→T0 id, 1→T1 id, 2→T2 id)
    tier_id_map = {i: tid for i, tid in enumerate(tier_ids)}

    # 2. Insertar grupos
    group_ids: list[int] = []
    for tier_level_idx, name, description, group_type in seed["groups"]:
        cur = conn.execute(
            "INSERT INTO tier_groups (site_id, tier_id, name, description, group_type) VALUES (?,?,?,?,?)",
            (site_id, tier_id_map[tier_level_idx], name, description, group_type),
        )
        group_ids.append(cur.lastrowid)

    # 3. Insertar asignaciones
    for parent_idx, child_idx in seed["assignments"]:
        conn.execute(
            "INSERT OR IGNORE INTO tier_group_assignments (parent_group_id, child_group_id) VALUES (?,?)",
            (group_ids[parent_idx], group_ids[child_idx]),
        )

    # 4. Insertar miembros (usando badge_number para encontrar operator_id)
    for group_idx, members in seed.get("member_badges", {}).items():
        gid = group_ids[group_idx]
        for badge, role in members:
            row = conn.execute(
                "SELECT id FROM operators WHERE badge_number=?", (badge,)
            ).fetchone()
            if row:
                conn.execute(
                    "INSERT OR IGNORE INTO tier_group_members (group_id, operator_id, role) VALUES (?,?,?)",
                    (gid, row[0], role),
                )

    # 5. Insertar rutas de escalado
    for from_idx, to_idx, esc_type, minutes, channel in seed.get("escalations", []):
        conn.execute(
            """INSERT INTO escalation_paths
               (site_id, from_group_id, to_group_id, escalation_type,
                auto_escalate_after_minutes, notification_channel)
               VALUES (?,?,?,?,?,?)""",
            (site_id, group_ids[from_idx], group_ids[to_idx], esc_type, minutes, channel),
        )

    conn.commit()
    _safe_print(f"  [ok] Tiers: {len(tier_ids)} niveles, {len(group_ids)} grupos → {site_id}")


# ── Datos de equipos por planta ───────────────────────────────────────────────
# Estructura por grupo: [(name, type, model, manufacturer, serial, status, nominal_speed,
#                         installed_date, last_maintenance, notes)]

EQUIPMENT_SEED: dict[str, dict[str, list]] = {
    "alcobendas": {
        "Línea 1 - Blísters": [
            ("Termoformadora TF1", "thermoformer", "TF-7000", "Uhlmann", "TF1-ALB-001", "running",  450.0, "2019-03-15", "2025-02-10", "Revisión lámina PVC mensual"),
            ("Llenadora BL1",     "filler",        "BL-500",  "IMA",     "BL1-ALB-001", "running",  450.0, "2019-03-15", "2025-03-01", None),
            ("Selladora SL1",     "other",          "SL-300",  "Romaco",  "SL1-ALB-001", "running",  450.0, "2019-03-15", "2025-01-20", "Cambio sellos trimestralmente"),
            ("Troqueladora TR1",  "other",          "TR-200",  "Romaco",  "TR1-ALB-001", "running",  450.0, "2019-03-15", "2025-02-28", None),
            ("Estuchadora ES1",   "cartoner",       "ES-600",  "Marchesini", "ES1-ALB-001", "running", 420.0, "2020-06-10", "2025-03-05", None),
            ("Etiquetadora ET1",  "labeler",        "ET-400",  "Herma",   "ET1-ALB-001", "stopped",  450.0, "2020-06-10", "2024-11-15", "Problema recurrente con bobina — en revisión"),
        ],
        "Línea 2 - Viales": [
            ("Lavadora LA1",     "other",       "LA-200",  "Bausch+Ströbel", "LA1-ALB-001", "running",    200.0, "2018-09-01", "2025-01-08", None),
            ("Llenadora VF1",    "filler",      "VF-1000", "Bosch",          "VF1-ALB-001", "running",    200.0, "2018-09-01", "2025-02-14", "Calibración dosificadora bimensual"),
            ("Taponadora TP1",   "other",       "TP-500",  "Bosch",          "TP1-ALB-001", "running",    200.0, "2018-09-01", "2025-02-14", None),
            ("Engarzadora EG1",  "other",       "EG-300",  "Bosch",          "EG1-ALB-001", "changeover", 200.0, "2018-09-01", "2025-03-10", "Cambio de formato en curso"),
            ("Etiquetadora ET2", "labeler",     "ET-400",  "Herma",          "ET2-ALB-001", "changeover", 200.0, "2021-04-20", "2025-03-10", None),
            ("Estuchadora ES2",  "cartoner",    "ES-600",  "Marchesini",     "ES2-ALB-001", "changeover", 180.0, "2021-04-20", "2025-03-01", None),
        ],
        "Línea 3 - Sobres": [
            ("Formadora SO1",    "other",   "SO-400",  "ICA",         "SO1-ALB-001", "running", 300.0, "2021-01-10", "2025-01-25", None),
            ("Dosificadora DO1", "weigher", "DO-200",  "Multipond",   "DO1-ALB-001", "running", 300.0, "2021-01-10", "2025-02-18", None),
            ("Selladora SL2",   "other",   "SL-300",  "Romaco",      "SL2-ALB-001", "running", 300.0, "2021-01-10", "2025-01-30", None),
            ("Cortadora CO1",   "other",   "CO-100",  "ICA",         "CO1-ALB-001", "idle",    300.0, "2021-01-10", "2025-02-05", "En espera de orden de fabricación"),
            ("Estuchadora ES3",  "cartoner","ES-400",  "Marchesini",  "ES3-ALB-001", "running", 280.0, "2021-01-10", "2025-03-08", None),
        ],
    },
    "indianapolis": {
        "Line 1 - Autoinjectors": [
            ("Assembly Unit AU1",   "other",       "AU-2000",  "Owen Mumford", "AU1-IND-001", "running",     800.0, "2020-05-01", "2025-02-20", None),
            ("Filling Station FS1", "filler",      "FS-500",   "Bausch+Ströbel","FS1-IND-001", "running",     800.0, "2020-05-01", "2025-01-15", None),
            ("Inspection Unit IN1", "inspection",  "VI-3000",  "Mettler-Toledo","IN1-IND-001", "running",     800.0, "2020-05-01", "2025-03-01", None),
            ("Labeler LB1",         "labeler",     "LB-600",   "Herma",        "LB1-IND-001", "running",     800.0, "2020-05-01", "2025-02-10", None),
            ("Cartoner CT1",        "cartoner",    "CT-800",   "Dividella",    "CT1-IND-001", "maintenance", 750.0, "2020-05-01", "2025-03-11", "Scheduled PM in progress"),
        ],
        "Line 2 - Insulin Pens": [
            ("Pen Assembly PA1",    "other",       "PA-1500",  "Ypsomed",      "PA1-IND-001", "running",  600.0, "2021-03-10", "2025-02-28", None),
            ("Fill & Finish FF1",   "filler",      "FF-800",   "Bosch",        "FF1-IND-001", "running",  600.0, "2021-03-10", "2025-02-05", None),
            ("Labeler LB2",         "labeler",     "LB-600",   "Herma",        "LB2-IND-001", "running",  600.0, "2021-03-10", "2025-01-20", None),
            ("Serializer SR1",      "serializer",  "SR-200",   "Systech",      "SR1-IND-001", "running",  600.0, "2021-03-10", "2025-03-01", None),
            ("Case Packer CP1",     "case_packer", "CP-400",   "Dividella",    "CP1-IND-001", "running",  580.0, "2021-03-10", "2025-02-15", None),
        ],
        "Line 3 - Vials": [
            ("Vial Washer VW1",    "other",      "VW-1000",  "Bausch+Ströbel","VW1-IND-001", "running",    400.0, "2019-07-15", "2025-01-30", None),
            ("Filler/Stopper FS2", "filler",     "FS-2000",  "Bosch",         "FS2-IND-001", "running",    400.0, "2019-07-15", "2025-02-22", None),
            ("Capper CP2",         "other",      "CP-600",   "Bosch",         "CP2-IND-001", "running",    400.0, "2019-07-15", "2025-02-22", None),
            ("Inspection VVI1",    "inspection", "VVI-5000", "Brevetti Angela","VVI1-IND-001","running",    400.0, "2019-07-15", "2025-03-05", None),
            ("Labeler LB3",        "labeler",    "LB-600",   "Herma",         "LB3-IND-001", "stopped",    400.0, "2019-07-15", "2024-12-10", "Encoder failure — parts on order"),
            ("Palletizer PL1",     "palletizer", "PL-200",   "KUKA",          "PL1-IND-001", "running",    380.0, "2019-07-15", "2025-02-18", None),
        ],
    },
    "fegersheim": {
        "Ligne 1 - Sérialisation": [
            ("Sérialisation SR1",   "serializer",  "SR-300",   "Körber",       "SR1-FEG-001", "running",   500.0, "2020-09-01", "2025-02-08", None),
            ("Étiqueteuse ET1",     "labeler",     "ET-500",   "Weber",        "ET1-FEG-001", "running",   500.0, "2020-09-01", "2025-01-28", None),
            ("Contrôle vision CV1", "inspection",  "CV-2000",  "Cognex",       "CV1-FEG-001", "running",   500.0, "2020-09-01", "2025-02-20", None),
            ("Cartonneuse CN1",     "cartoner",    "CN-600",   "Marchesini",   "CN1-FEG-001", "running",   480.0, "2020-09-01", "2025-03-03", None),
        ],
        "Ligne 2 - Découpe": [
            ("Presse découpe PD1",  "other",       "PD-800",   "Romaco",       "PD1-FEG-001", "running",   300.0, "2018-04-10", "2025-01-15", "Lame changée trimestrellement"),
            ("Découpe aluminium DA1","other",       "DA-400",   "Uhlmann",      "DA1-FEG-001", "maintenance",300.0,"2018-04-10", "2025-03-10", "Maintenance préventive en cours"),
            ("Contrôle qualité CQ1","inspection",  "CQ-1000",  "Keyence",      "CQ1-FEG-001", "running",   300.0, "2018-04-10", "2025-02-25", None),
        ],
        "Ligne 3 - Étiquetage": [
            ("Étiqueteuse ET2",     "labeler",     "ET-500",   "Weber",        "ET2-FEG-001", "running",   400.0, "2021-11-20", "2025-02-12", None),
            ("Applicateur AP1",     "other",       "AP-200",   "Herma",        "AP1-FEG-001", "running",   400.0, "2021-11-20", "2025-01-18", None),
            ("Cartonneuse CN2",     "cartoner",    "CN-400",   "IMA",          "CN2-FEG-001", "idle",      380.0, "2021-11-20", "2025-02-28", "Attente ordre de fabrication"),
        ],
    },
    "sesto": {
        "Linea 1 - Blister": [
            ("Termoformatrice TF1", "thermoformer","TF-7500",  "IMA",          "TF1-SES-001", "running",   420.0, "2019-06-01", "2025-02-05", None),
            ("Riempitrice RI1",     "filler",      "RI-600",   "MG2",          "RI1-SES-001", "running",   420.0, "2019-06-01", "2025-01-22", None),
            ("Saldatrice SD1",      "other",       "SD-300",   "Uhlmann",      "SD1-SES-001", "running",   420.0, "2019-06-01", "2025-03-02", None),
            ("Fustellatrice FU1",   "other",       "FU-200",   "Romaco",       "FU1-SES-001", "running",   420.0, "2019-06-01", "2025-02-18", None),
            ("Astucciatrice AS1",   "cartoner",    "AS-600",   "Marchesini",   "AS1-SES-001", "changeover",400.0, "2019-06-01", "2025-03-08", "Cambio formato in corso"),
        ],
        "Linea 2 - Pick-and-Place": [
            ("Robot Pick-Place PP1","other",       "PP-2000",  "Fanuc",        "PP1-SES-001", "running",   300.0, "2022-02-15", "2025-02-28", None),
            ("Controllo visione VC1","inspection", "VC-3000",  "Cognex",       "VC1-SES-001", "running",   300.0, "2022-02-15", "2025-03-01", None),
            ("Astucciatrice AS2",   "cartoner",    "AS-400",   "IMA",          "AS2-SES-001", "running",   280.0, "2022-02-15", "2025-01-30", None),
        ],
        "Linea 3 - Pallettizzazione": [
            ("Palettizzatore PL1",  "palletizer",  "PL-500",   "KUKA",         "PL1-SES-001", "running",   150.0, "2020-03-20", "2025-02-10", None),
            ("Avvolgitrice AV1",    "other",       "AV-200",   "Robopac",      "AV1-SES-001", "running",   150.0, "2020-03-20", "2025-01-25", None),
            ("Etichettatrice ET1",  "labeler",     "ET-300",   "Weber",        "ET1-SES-001", "stopped",   150.0, "2020-03-20", "2024-12-20", "Guasto scheda elettronica — in riparazione"),
        ],
    },
    "seishin": {
        "ライン1 - 包装": [
            ("サーモフォーマー TF1", "thermoformer","TF-6000",  "CKD",          "TF1-SEI-001", "running",   380.0, "2020-04-01", "2025-02-15", None),
            ("充填機 FL1",           "filler",      "FL-400",   "Shibuya",      "FL1-SEI-001", "running",   380.0, "2020-04-01", "2025-01-20", None),
            ("シール機 SL1",         "other",       "SL-200",   "Omori",        "SL1-SEI-001", "running",   380.0, "2020-04-01", "2025-02-28", None),
            ("ラベラー LB1",         "labeler",     "LB-300",   "Sato",         "LB1-SEI-001", "running",   380.0, "2020-04-01", "2025-03-05", None),
            ("カートナー CT1",       "cartoner",    "CT-500",   "Mutual",       "CT1-SEI-001", "running",   360.0, "2020-04-01", "2025-02-22", None),
        ],
        "ライン2 - 充填": [
            ("洗浄機 WS1",           "other",       "WS-800",   "Shibuya",      "WS1-SEI-001", "running",   200.0, "2018-10-15", "2025-01-10", None),
            ("充填密封機 FF1",       "filler",      "FF-1200",  "Bosch",        "FF1-SEI-001", "running",   200.0, "2018-10-15", "2025-02-05", None),
            ("打栓機 CP1",           "other",       "CP-400",   "Shibuya",      "CP1-SEI-001", "maintenance",200.0,"2018-10-15", "2025-03-10", "定期点検実施中"),
            ("検査機 IN1",           "inspection",  "VI-2000",  "Keyence",      "IN1-SEI-001", "running",   200.0, "2018-10-15", "2025-02-20", None),
        ],
        "ライン3 - シリアル化": [
            ("シリアライザー SR1",   "serializer",  "SR-100",   "Systech",      "SR1-SEI-001", "running",   300.0, "2022-07-01", "2025-03-01", None),
            ("集積機 AG1",           "other",       "AG-200",   "Omori",        "AG1-SEI-001", "running",   300.0, "2022-07-01", "2025-02-15", None),
            ("ケースパッカー CP2",   "case_packer", "CP-600",   "Fuji",         "CP2-SEI-001", "idle",      280.0, "2022-07-01", "2025-02-10", "次ロット待ち"),
        ],
    },
}


def _seed_equipment(site_id: str, conn: sqlite3.Connection) -> None:
    """Inserta equipos de ejemplo para una planta. Idempotente."""
    seed = EQUIPMENT_SEED.get(site_id)
    if not seed:
        return

    existing = conn.execute(
        "SELECT COUNT(*) FROM equipment WHERE site_id=?", (site_id,)
    ).fetchone()[0]
    if existing > 0:
        return

    count = 0
    for group_name, machines in seed.items():
        row = conn.execute(
            "SELECT id FROM tier_groups WHERE site_id=? AND name=?", (site_id, group_name)
        ).fetchone()
        if not row:
            continue
        group_id = row[0]
        for (name, eq_type, model, manufacturer, serial, status, speed,
             installed, last_maint, notes) in machines:
            conn.execute(
                """INSERT INTO equipment
                   (site_id, group_id, name, equipment_type, model, manufacturer,
                    serial_number, status, nominal_speed, installed_date,
                    last_maintenance, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (site_id, group_id, name, eq_type, model, manufacturer,
                 serial, status, speed, installed, last_maint, notes),
            )
            count += 1

    conn.commit()
    _safe_print(f"  [ok] Equipment: {count} máquinas → {site_id}")


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

    # Para Alcobendas: 9 operadores de línea (3 por línea), otros sites: los 3 primeros
    num_line_ops = len([o for o in cfg["operators"] if o[1] == "operator"])
    if num_line_ops >= 9:
        # 3 operadores por línea: L1=op_ids[0:3], L2=op_ids[3:6], L3=op_ids[6:9]
        line_operators = {1: op_ids[0:3], 2: op_ids[3:6], 3: op_ids[6:9]}
    else:
        line_operators = {1: op_ids[:3], 2: op_ids[:3], 3: op_ids[:3]}

    # ── 2. Turnos (14 días × 3 líneas × N turnos por día) ──
    now           = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    shift_config  = cfg.get("shift_config", {"morning": 6, "afternoon": 14, "night": 22})
    shift_hours   = cfg.get("shift_hours", 8)
    kpi_hours     = cfg.get("kpi_hours", [2, 4, 6])
    target_units  = cfg.get("target_units", 9600)
    planned_tmin  = cfg.get("planned_time_min", 480.0)
    comment_range = cfg.get("comment_range", (15, 455))
    categories    = (["production"] * 3 + ["quality"] * 2
                     + ["maintenance"] * 1 + ["safety"] * 1)

    shift_rows:   list[tuple] = []
    kpi_rows:     list[tuple] = []
    comment_rows: list[tuple] = []

    for day_offset in range(14, 0, -1):
        day = now - timedelta(days=day_offset)
        for line in [1, 2, 3]:
            for shift_type, start_hour in shift_config.items():
                start_dt = day.replace(hour=start_hour)
                end_dt   = start_dt + timedelta(hours=shift_hours)
                op_id    = random.choice(line_operators.get(line, op_ids[:3]))
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
        avail_t   = planned_tmin - dt_min
        units     = int(speed * avail_t / 60 * random.uniform(0.95, 1.05))
        rej_rate  = cfg["reject_rate"] * random.uniform(0.5, 2.0)
        units_rej = int(units * rej_rate)

        # 3 lecturas por turno distribuidas uniformemente
        for h in kpi_hours:
            frac = h / (shift_hours * 1.0)
            ts   = start_dt + timedelta(hours=h)
            kpi_rows.append((
                sid,
                ts.isoformat(sep=" ", timespec="seconds"),
                int(units * frac),
                int(units_rej * frac),
                round(dt_min * frac, 2),
                round(speed * random.uniform(0.95, 1.05), 1),
                target_units,
                1200.0,
                planned_tmin,
            ))

        # 2-3 comentarios por turno
        num_c = random.randint(2, 3)
        for _ in range(num_c):
            cat      = random.choice(categories)
            template = random.choice(cfg["comments"][cat])
            min_val  = random.randint(*cfg["co_range"])
            text     = template.format(min=min_val) if "{min}" in template else template
            c_ts     = start_dt + timedelta(minutes=random.randint(*comment_range))
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
    _seed_tiers(site_id, conn2)
    _seed_equipment(site_id, conn2)
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
                "line": None, "cat": "equipment",
                "desc": "Atasco recurrente en etiquetadora automática (todas las líneas)",
                "freq": 5.2, "impact": 9, "status": "investigating",
                "first": "2025-10-12", "last": "2026-04-15",
                "root": "Acumulación de adhesivo en rodillos de avance y desgaste de guías de papel (intervalo de sustitución de 6 meses insuficiente — el desgaste real se produce en ~7 semanas)",
                "counter": "Limpieza de rodillos cada 4 horas (nuevo SOP); sustitución preventiva de guías cada 7 semanas; alarma en HMI a las 3,5 h de funcionamiento continuo",
            },
            {
                "line": None, "cat": "process",
                "desc": "Cambios de formato lentos — tiempo medio 58 min (objetivo <40 min)",
                "freq": 3.0, "impact": 7, "status": "investigating",
                "first": "2025-09-01", "last": "2026-04-14",
                "root": "Piezas de formato no identificadas ni preasignadas en carro; 40% de las actividades internas (máquina parada) son convertibles a externas",
                "counter": "Proyecto SMED en curso: kits de cambio con código de color por formato, estandarización de secuencia SOP v2.0, objectivo <40 min",
            },
            {
                "line": 2, "cat": "quality",
                "desc": "Desviación de peso en viales: unidades fuera de ±2% de especificación",
                "freq": 2.5, "impact": 8, "status": "open",
                "first": "2025-12-10", "last": "2026-04-12",
                "root": "Deriva térmica del sensor de la balanza después de 4 horas de funcionamiento continuo; variabilidad de densidad del granulado ±2,1% (especificación: ±1,5%)",
                "counter": "Recalibración de balanza cada 2 horas; estudio para sustitución por balanza termocompensada; auditoría de proveedor de granulado",
            },
        ],
        "indianapolis": [
            {
                "line": None, "cat": "equipment",
                "desc": "Intermittent 2D camera read errors in serialization module (all lines)",
                "freq": 3.8, "impact": 9, "status": "investigating",
                "first": "2025-11-18", "last": "2026-04-15",
                "root": "Adhesive aerosol from labeling station deposits on camera lens over ~5 hours of operation; no scheduled lens cleaning in original SOP; ISO 7 cleanroom humidity fluctuations compound the issue",
                "counter": "Lens cleaning added to shift SOP every 4 hours; protective air curtain under evaluation; humidity sensor installed in serialization module",
            },
            {
                "line": 1, "cat": "equipment",
                "desc": "Film breakage in autoinjector blister sealer at >92% nominal speed",
                "freq": 2.1, "impact": 7, "status": "open",
                "first": "2026-01-22", "last": "2026-04-13",
                "root": "Forming station temperature variability (±4°C) induces film stress cracks at high throughput; root cause under investigation",
                "counter": "Nominal speed capped at 90% as interim measure; closed-loop temperature controller under procurement",
            },
            {
                "line": 2, "cat": "process",
                "desc": "Changeover time regression on L2 after Q4 2025 operator rotation",
                "freq": 1.2, "impact": 5, "status": "resolved",
                "first": "2025-10-10", "last": "2026-01-28",
                "root": "New operators unfamiliar with color-coded SMED kit sequence after rotation; buddy system not activated during onboarding",
                "counter": "OJT retraining completed; mandatory buddy pairing for first 10 changeovers; resolved January 2026",
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
                "line": None,
                "title": "A3: Eliminación de atascos en etiquetadora automática",
                "desc": "Proyecto A3 para eliminar las paradas recurrentes por atasco en la etiquetadora automática en todas las líneas de Alcobendas. Problema principal de OEE de la planta.",
                "method": "A3", "status": "Terminado", "category": "Quality",
                "owner": "Isabel Torres",
                "start": "2025-10-20", "target": "2026-02-28", "completion": "2026-02-18",
                "benefit_exp": "Reducción de atascos un 85%, recuperando ≥4 h/semana de producción perdida",
                "benefit_act": "Atascos reducidos de 5,2/semana a 0,9/semana. Recuperadas 3,8 h/semana de producción. OEE +1,2 pp.",
                "linked_prob_idx": 0,
            },
            {
                "line": None,
                "title": "SMED: Reducción del tiempo de cambio de formato (<40 min)",
                "desc": "Proyecto SMED para reducir el tiempo de cambio de formato de 58 min a menos de 40 min en todas las líneas. Incluye kits de cambio con código de color y estandarización de secuencia.",
                "method": "A3", "status": "En progreso", "category": "Delivery",
                "owner": "Pedro García",
                "start": "2026-02-03", "target": "2026-06-30", "completion": None,
                "benefit_exp": "Reducción del tiempo de cambio de 58 a <40 min; recuperar ≥3 h/semana de capacidad productiva",
                "benefit_act": None,
                "linked_prob_idx": 1,
            },
        ],
        "indianapolis": [
            {
                "line": None,
                "title": "SMED: Changeover Standardization — Global Best Practice (45 min benchmark)",
                "desc": "SMED project to reduce and standardize format changeover time across all 3 lines. Indianapolis established as the global benchmark site. Methodology transferable to all network plants.",
                "method": "A3", "status": "Terminado", "category": "Delivery",
                "owner": "Jennifer Taylor",
                "start": "2025-06-01", "target": "2025-11-30", "completion": "2025-11-20",
                "benefit_exp": "Reduce average changeover from 72 min to <50 min; establish transferable best practice for the global network",
                "benefit_act": "Average changeover: 72 min → 45 min (38% reduction). Variability: 55–90 min → 38–55 min. Annual hours recovered: 210 h/year (3 lines). OEE +4.1 pp. Methodology deployed to Alcobendas Q1 2026.",
                "linked_prob_idx": 2,
            },
            {
                "line": None,
                "title": "DMAIC: Elimination of Intermittent Serialization Camera Errors",
                "desc": "DMAIC project to identify and permanently eliminate the root cause of intermittent 2D camera read errors in the serialization module, which is the primary OEE loss driver across all Indianapolis lines.",
                "method": "DMAIC", "status": "En progreso", "category": "Quality",
                "owner": "Karen Martinez",
                "start": "2026-01-20", "target": "2026-06-30", "completion": None,
                "benefit_exp": "Reduce serialization stoppages from 3.8/week to <0.3/week; recover ~60 min/week of lost production; OEE +1.3 pp",
                "benefit_act": None,
                "linked_prob_idx": 0,
            },
        ],
        "fegersheim": [
            {
                "line": 1, "title": "Amélioration OEE ligne sérialisation — résolution erreurs caméra",
                "desc": "Projet A3 pour éliminer les erreurs répétées de lecture caméra 2D dans le module de sérialisation de la ligne 1.",
                "method": "A3", "status": "En progreso", "category": "Quality",
                "owner": "Claire Rousseau",
                "start": "2026-02-01", "target": "2026-06-30", "completion": None,
                "benefit_exp": "Réduire les arrêts liés à la sérialisation de 3,5/semaine à <0,5/semaine",
                "benefit_act": None,
                "linked_prob_idx": 0,
            },
            {
                "line": 3, "title": "5 Pourquoi: Adhérence étiquettes basse température",
                "desc": "Analyse 5 Pourquoi pour identifier et éliminer la cause racine du problème d'adhérence des étiquettes lors des périodes hivernales.",
                "method": "5Why", "status": "En progreso", "category": "Quality",
                "owner": "Sophie Lefebvre",
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
                "method": "A3", "status": "En progreso", "category": "Quality",
                "owner": "Chiara Ricci",
                "start": "2026-02-10", "target": "2026-05-31", "completion": None,
                "benefit_exp": "Ridurre il tasso di scarto da 1,5% a <0,5%; risparmio stimato 15.000 unità/mese",
                "benefit_act": None,
                "linked_prob_idx": 3,
            },
            {
                "line": 2, "title": "Kaizen: Eliminazione guasti pick-and-place L2",
                "desc": "Evento Kaizen focalizzato sull'eliminazione dei guasti ricorrenti nel sistema pick-and-place della linea 2 causati dal deterioramento delle ventose.",
                "method": "Kaizen", "status": "No iniciado", "category": "Cost",
                "owner": "Francesco Romano",
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
            # Doc 0: A3 completado — etiquetadora (todas las líneas)
            """<article class="a3-document">
<h2>A3: Eliminación de atascos en etiquetadora automática — Alcobendas</h2>
<p><strong>Autor:</strong> Isabel Torres &nbsp;|&nbsp; <strong>Planta:</strong> Alcobendas &nbsp;|&nbsp; <strong>Fecha inicio:</strong> 2025-10-20</p>
<hr>
<section><h3>1. Background / Contexto</h3>
<p>Las tres líneas de Alcobendas (L1-blísteres, L2-viales, L3-sobres) registran de forma recurrente atascos en la etiquetadora automática HERMA 500. Con una frecuencia media de 5,2 atascos semanales entre las tres líneas y una duración media de 18 minutos por evento, este problema representa la mayor pérdida de OEE de la planta. Los atascos se concentran tras 3-4 horas de funcionamiento continuo.</p>
</section>
<section><h3>2. Current Condition / Estado Actual</h3>
<ul>
<li>Frecuencia media: 5,2 paradas/semana por atasco en etiquetadora (todas las líneas)</li>
<li>Duración media por evento: 18 minutos</li>
<li>Producción perdida estimada: ~94 min/semana (~1.880 unidades/semana a velocidad nominal)</li>
<li>OEE impactado en ~1,9% por esta causa específica</li>
<li>Los atascos ocurren principalmente tras 3-4 horas de funcionamiento continuo</li>
<li>Causa inmediata: etiquetas pegadas o dobladas al pasar por las guías de papel</li>
</ul>
</section>
<section><h3>3. Goal / Objetivo</h3>
<p>Reducir los atascos en etiquetadora de 5,2/semana a <strong>≤0,5/semana</strong> antes del 28 de febrero 2026, recuperando ≥4 horas semanales de producción y mejorando el OEE en al menos +1,5 pp.</p>
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
                → ROOT CAUSE 1: Ausencia de procedimiento de limpieza preventiva en producción

  → Además: desgaste de guías de papel (tolerancia >0,5 mm)
      ¿Por qué están desgastadas?
        → Porque el intervalo de sustitución preventiva es de 6 meses
          pero el desgaste real ocurre en ~7 semanas (volumen real vs. diseño)
            → ROOT CAUSE 2: Frecuencia de sustitución de guías inadecuada al volumen real de producción
</pre>
</section>
<section><h3>5. Countermeasures / Contramedidas</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Contramedida</th><th>Responsable</th><th>Fecha</th><th>Estado</th></tr>
<tr><td style="padding:0.4rem">Implementar limpieza de rodillos cada 4 horas (incluir en SOP-ETQ-003)</td><td>Pedro García</td><td>2025-11-10</td><td>✅ Completado</td></tr>
<tr><td style="padding:0.4rem">Reducir intervalo de sustitución de guías de 6 meses a 7 semanas</td><td>José Fernández</td><td>2025-11-25</td><td>✅ Completado</td></tr>
<tr><td style="padding:0.4rem">Instalar alarma preventiva en HMI a las 3,5 h de funcionamiento continuo</td><td>José Fernández</td><td>2026-01-15</td><td>✅ Completado</td></tr>
<tr><td style="padding:0.4rem">Actualizar SOP-ETQ-003 con nuevas frecuencias de mantenimiento</td><td>Ana Rodríguez</td><td>2026-01-31</td><td>✅ Completado</td></tr>
<tr><td style="padding:0.4rem">Crear stock de guías de recambio en línea (min. 2 juegos por línea)</td><td>José Fernández</td><td>2026-02-15</td><td>✅ Completado</td></tr>
</table>
</section>
<section><h3>6. Implementation Plan</h3>
<ul>
<li><strong>Sem 1-2 (Oct 20 – Nov 3):</strong> Diagnóstico detallado, medición de desgaste, análisis de adhesivo residual</li>
<li><strong>Sem 3-6 (Nov 4 – Nov 29):</strong> Implantación protocolo limpieza + sustitución anticipada de guías en las 3 líneas</li>
<li><strong>Sem 7-12 (Dic – Ene):</strong> Seguimiento de métricas, ajuste de protocolo, instalación alarma HMI</li>
<li><strong>Sem 13-17 (Feb):</strong> Validación de resultados, actualización de SOP, cierre A3</li>
</ul>
</section>
<section><h3>7. Follow-up / Seguimiento</h3>
<p>KPIs de seguimiento semanales:</p>
<ul>
<li>Número de atascos/semana por línea (objetivo ≤0,5 total)</li>
<li>Tiempo perdido por atascos/semana (objetivo ≤9 min)</li>
<li>OEE mensual por línea (objetivo +1,5 pp vs. baseline)</li>
</ul>
</section>
<section><h3>8. Results / Resultados</h3>
<p style="background:#d4edda;padding:0.75rem;border-radius:4px">✅ <strong>Proyecto completado el 18 de febrero 2026.</strong></p>
<ul>
<li>Atascos/semana: de 5,2 → <strong>0,9</strong> (reducción del 83%)</li>
<li>Tiempo perdido/semana: de 94 min → <strong>16 min</strong></li>
<li>Producción recuperada: <strong>3,8 h/semana (~4.560 unidades)</strong></li>
<li>OEE: impacto positivo de <strong>+1,2 pp</strong></li>
</ul>
</section>
</article>""",
            # Doc 1: SMED cambio formato (in_progress)
            """<article class="a3-document">
<h2>SMED: Reducción del tiempo de cambio de formato (&lt;40 min) — Alcobendas</h2>
<p><strong>Autor:</strong> Pedro García &nbsp;|&nbsp; <strong>Planta:</strong> Alcobendas &nbsp;|&nbsp; <strong>Fecha inicio:</strong> 2026-02-03</p>
<hr>
<section><h3>1. Background / Contexto</h3>
<p>El tiempo de cambio de formato en Alcobendas es actualmente de 58 minutos de media, muy por encima del objetivo de 40 minutos y del benchmark interno de Indianapolis (22 minutos). Los cambios de formato son la segunda mayor causa de pérdida de OEE en la planta, con una frecuencia de ~3 cambios/semana por línea.</p>
</section>
<section><h3>2. Current Condition / Estado Actual</h3>
<ul>
<li>Tiempo medio de cambio de formato: 58 min (rango: 45–68 min)</li>
<li>OEE pérdida por changeovers: ~2,8% anual</li>
<li>~3 cambios/semana/línea = ~174 min/semana perdidos por línea</li>
<li>Sin kits de cambio estandarizados — operarios buscan piezas durante el cambio (+20 min)</li>
<li>Benchmark interno: Indianapolis 22 min (SMED consolidado)</li>
</ul>
</section>
<section><h3>3. Goal / Objetivo</h3>
<p>Reducir el tiempo medio de cambio de formato de 58 min a <strong>&lt;40 min</strong> antes del 30 de junio 2026, con variabilidad ≤8 min entre turnos y operarios.</p>
</section>
<section><h3>4. Root Cause Analysis</h3>
<ul>
<li>~55% del tiempo de cambio es interno (máquina parada) pero convertible a externo</li>
<li>Sin kits de cambio preasignados — operarios buscan piezas durante el cambio (+20 min de media)</li>
<li>Sin secuencia estandarizada — cada operario sigue su propia rutina</li>
<li>Sin gestión visual del progreso del changeover en tiempo real</li>
<li>Indianapolis ya resolvió este mismo problema: benchmark y transferencia de conocimiento planificada</li>
</ul>
</section>
<section><h3>5. Countermeasures / Contramedidas</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Contramedida</th><th>Responsable</th><th>Fecha</th><th>Estado</th></tr>
<tr><td style="padding:0.4rem">Visita benchmark a Indianapolis — análisis kits SMED</td><td>Pedro García</td><td>2026-02-20</td><td>✅ Completado</td></tr>
<tr><td style="padding:0.4rem">Crear kits de cambio con código de color por formato (9 formatos)</td><td>José Fernández</td><td>2026-04-15</td><td>🔄 En curso</td></tr>
<tr><td style="padding:0.4rem">Convertir actividades internas a externas (análisis de vídeo)</td><td>Pedro García</td><td>2026-04-30</td><td>🔄 En curso</td></tr>
<tr><td style="padding:0.4rem">Desarrollar SOP v2.0 con secuencia temporizada</td><td>Ana Rodríguez</td><td>2026-05-31</td><td>⏳ Pendiente</td></tr>
<tr><td style="padding:0.4rem">Instalar temporizador digital en cada puesto de cambio</td><td>José Fernández</td><td>2026-06-15</td><td>⏳ Pendiente</td></tr>
<tr><td style="padding:0.4rem">Formación y certificación de todos los operarios</td><td>Isabel Torres</td><td>2026-06-30</td><td>⏳ Pendiente</td></tr>
</table>
</section>
<section><h3>6. Implementation Plan</h3>
<ul>
<li><strong>Feb 3–28:</strong> Benchmark Indianapolis, análisis de vídeo de cambios actuales, identificación de desperdicios</li>
<li><strong>Mar–Abr 2026:</strong> Diseño y fabricación de kits de cambio, conversión de actividades internas a externas</li>
<li><strong>May–Jun 2026:</strong> Implementación SOP v2.0, instalación de temporizadores, formación de operarios</li>
<li><strong>Jul 2026:</strong> Medición de resultados, estandarización, transferencia a otras líneas si procede</li>
</ul>
</section>
<section><h3>7. Follow-up / Seguimiento</h3>
<ul>
<li>Tiempo medio de changeover por línea (objetivo &lt;40 min)</li>
<li>Desviación estándar del tiempo de changeover (objetivo ≤8 min)</li>
<li>Mejora de OEE atribuida a reducción de changeovers</li>
</ul>
</section>
<section><h3>8. Results / Resultados</h3>
<p style="background:#cce5ff;padding:0.75rem;border-radius:4px">🔄 <strong>En curso — Fase: análisis y diseño de kits (abril 2026).</strong> Visita benchmark a Indianapolis completada. Kits de cambio en fabricación. Conversión interna/externa en análisis. Resultados completos esperados junio 2026.</p>
</section>
</article>""",
        ],

        "indianapolis": [
            # Doc 0: SMED Changeover — COMPLETED global best practice
            """<article class="a3-document">
<h2>A3: SMED Changeover Standardization — Global Best Practice (Indianapolis Benchmark)</h2>
<p><strong>Author:</strong> Jennifer Taylor &nbsp;|&nbsp; <strong>Site:</strong> Indianapolis &nbsp;|&nbsp; <strong>Start:</strong> 2025-06-01</p>
<hr>
<section><h3>1. Background</h3>
<p>Indianapolis identified format changeover time as the single largest OEE loss driver in 2024 (contributing ~5.2% annual OEE loss). Average changeover across all 3 lines was 72 minutes, with high variability (55–90 min). A structured SMED project was launched with the dual goal of reducing changeover time and establishing Indianapolis as the global network benchmark and knowledge-transfer site.</p>
</section>
<section><h3>2. Current Condition</h3>
<ul>
<li>Average changeover: 72 min (range: 55–90 min)</li>
<li>OEE loss from changeovers: ~5.2% annually</li>
<li>~3.5 changeovers/week/line = 252 min/week lost per line</li>
<li>No standardized kit or sequence — each operator follows own routine</li>
<li>Internal / external activity split: 68% internal (machine stopped), 32% external</li>
<li>Benchmark target: Indianapolis to become global best practice site</li>
</ul>
</section>
<section><h3>3. Goal</h3>
<p>Reduce average changeover from 72 min to <strong>&lt;50 min</strong> with ≤8 min variability across all shifts and operators by November 30, 2025. Document methodology for global network deployment.</p>
</section>
<section><h3>4. Root Cause Analysis</h3>
<ul>
<li>68% of changeover time is internal (machine stopped) but 45% of it is convertible to external</li>
<li>No pre-staged kits — operators source parts during changeover (+25 min average)</li>
<li>No standardized sequence — significant variation between operators and shifts</li>
<li>No visual management to track changeover progress or elapsed time in real time</li>
<li>Format-specific tooling stored in central warehouse, not at line (&gt;12 min retrieval)</li>
</ul>
</section>
<section><h3>5. Countermeasures</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Action</th><th>Owner</th><th>Date</th><th>Status</th></tr>
<tr><td style="padding:0.4rem">Video analysis of 12 changeovers across 3 shifts — waste mapping</td><td>Jennifer Taylor</td><td>2025-07-15</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Design color-coded changeover kits per format (14 formats)</td><td>Steven Anderson</td><td>2025-08-31</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Convert internal→external activities (pre-staging protocol)</td><td>Jennifer Taylor</td><td>2025-09-15</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Install dedicated kit storage trolley at each line position</td><td>Steven Anderson</td><td>2025-09-30</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Develop standardized SOP v2.3 with timed sequence and visual aids</td><td>Karen Martinez</td><td>2025-10-15</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Install digital countdown timer display at each changeover station</td><td>Steven Anderson</td><td>2025-10-31</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Train all 9 line operators — OJT sign-off required per SOP v2.3</td><td>Jennifer Taylor</td><td>2025-11-20</td><td>✅ Done</td></tr>
</table>
</section>
<section><h3>6. Implementation Plan</h3>
<ul>
<li><strong>Jun–Jul 2025:</strong> SMED analysis, video recording, waste identification, activity mapping</li>
<li><strong>Aug–Sep 2025:</strong> Kit design, fabrication, pre-staging conversion trials</li>
<li><strong>Oct 2025:</strong> SOP v2.3 drafting, digital timer installation, pilot runs</li>
<li><strong>Nov 2025:</strong> Full rollout across all 3 lines, operator certification, measurement</li>
<li><strong>Dec 2025+:</strong> Network knowledge transfer — Alcobendas first deployment (Q1 2026)</li>
</ul>
</section>
<section><h3>7. Follow-up KPIs</h3>
<ul>
<li>Average changeover time per line per week (target &lt;50 min)</li>
<li>Changeover time standard deviation (target ≤8 min)</li>
<li>OEE improvement attributed to changeover reduction</li>
<li>Number of network sites deploying methodology</li>
</ul>
</section>
<section><h3>8. Results — GLOBAL BEST PRACTICE</h3>
<p style="background:#d4edda;padding:0.75rem;border-radius:4px">✅ <strong>Project completed November 20, 2025 — Established as Global Benchmark.</strong></p>
<ul>
<li>Average changeover: 72 min → <strong>45 min</strong> (38% reduction)</li>
<li>Variability: 55–90 min → <strong>38–55 min</strong></li>
<li>Annual hours recovered: <strong>210 h/year across 3 lines</strong></li>
<li>OEE improvement: <strong>+4.1 pp</strong></li>
<li>SOP v2.3 adopted as network standard — deployment to Alcobendas started Q1 2026</li>
<li>Alcobendas benchmark visit completed February 2026</li>
</ul>
</section>
</article>""",
            # Doc 1: DMAIC serialization — IN PROGRESS
            """<article class="a3-document">
<h2>DMAIC: Elimination of Intermittent Serialization Camera Errors — Indianapolis</h2>
<p><strong>Author:</strong> Karen Martinez &nbsp;|&nbsp; <strong>Site:</strong> Indianapolis &nbsp;|&nbsp; <strong>Start:</strong> 2026-01-20</p>
<hr>
<section><h3>1. Background</h3>
<p>All three Indianapolis lines experience intermittent 2D camera read errors in the serialization (Track &amp; Trace) module. With a combined frequency of 3.8 stops per week and an average duration of 16 minutes per event (cleaning + restart + revalidation), this is currently the primary OEE loss driver on the site. The issue has been recurring since November 2025 and no permanent fix has been implemented.</p>
</section>
<section><h3>2. Current Condition</h3>
<ul>
<li>Frequency: 3.8 stops/week across all lines (L1: 1.5/w, L2: 1.3/w, L3: 1.0/w)</li>
<li>Average stop duration: 16 min (cleaning + restart + revalidation sequence)</li>
<li>Lost production: ~61 min/week (~1,220 units/week at nominal speed)</li>
<li>OEE impact: -1.3 pp across the site</li>
<li>Pattern: errors cluster 4–6 hours into the 12-hour shift</li>
<li>Alcobendas reported a similar issue (condensation-related) — being cross-referenced</li>
</ul>
</section>
<section><h3>3. Goal</h3>
<p>Reduce serialization camera stops from 3.8/week to <strong>≤0.3/week</strong> by June 30, 2026. Recover ≥55 min/week of lost production and improve OEE by +1.3 pp.</p>
</section>
<section><h3>4. Root Cause Analysis — DMAIC Fishbone</h3>
<pre style="background:#f5f5f5;padding:1rem;border-radius:4px;font-size:0.85rem">
DEFINE: Intermittent 2D camera read errors in serialization — all Indianapolis lines
MEASURE: 3.8 stops/week | Avg duration 16 min | Pattern: h4–h6 of 12h shift

ANALYZE — Fishbone (Ishikawa):
  MACHINE:
    → Camera lens contamination detected at each failure event
    → Protective air flow absent in original module configuration
  METHOD:
    → No scheduled lens cleaning in current SOP (only on failure)
    → Serialization module SOP last updated 2023 — pre-expansion
  MATERIAL:
    → Adhesive aerosol from labeling station migrates to camera zone
    → Aerosol concentration increases over shift duration (explains h4–h6 pattern)
  ENVIRONMENT:
    → ISO 7 cleanroom humidity: 45–65% RH (fluctuates with HVAC cycling)
    → Humidity excursions may accelerate adhesive deposition on lens
  MAN:
    → Operators not trained to recognize early signs of lens fouling

PRIMARY ROOT CAUSE: Adhesive aerosol deposition on camera lens — no prevention protocol
SECONDARY: Humidity fluctuations in cleanroom compounding contamination rate
CROSS-REFERENCE: Alcobendas identified condensation as root cause on same camera model
</pre>
</section>
<section><h3>5. Countermeasures</h3>
<table border="1" style="border-collapse:collapse;width:100%;font-size:0.85rem">
<tr><th style="padding:0.4rem">Action</th><th>Owner</th><th>Date</th><th>Status</th></tr>
<tr><td style="padding:0.4rem">Add lens cleaning to shift SOP — every 4 hours (interim measure)</td><td>Karen Martinez</td><td>2026-02-10</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Install humidity/temperature sensor in serialization module</td><td>Steven Anderson</td><td>2026-03-15</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Design and install protective air curtain over camera lens</td><td>Steven Anderson</td><td>2026-04-30</td><td>🔄 In progress</td></tr>
<tr><td style="padding:0.4rem">Cross-site learning call with Alcobendas — share root cause findings</td><td>Karen Martinez</td><td>2026-03-28</td><td>✅ Done</td></tr>
<tr><td style="padding:0.4rem">Evaluate aerosol deflector between labeling and serialization stations</td><td>Steven Anderson</td><td>2026-05-15</td><td>⏳ Pending</td></tr>
<tr><td style="padding:0.4rem">CONTROL: Update SOP and validate results over 8-week monitoring period</td><td>Karen Martinez</td><td>2026-06-30</td><td>⏳ Pending</td></tr>
</table>
</section>
<section><h3>6. Implementation Plan</h3>
<ul>
<li><strong>Jan 20 – Feb 10:</strong> Define &amp; Measure — data collection, frequency baseline, pattern analysis</li>
<li><strong>Feb 11 – Mar 15:</strong> Analyze — root cause confirmation, cross-site benchmark (Alcobendas)</li>
<li><strong>Mar 16 – May 15:</strong> Improve — air curtain installation, aerosol deflector evaluation</li>
<li><strong>May 16 – Jun 30:</strong> Control — SOP update, 8-week validation, closure</li>
</ul>
</section>
<section><h3>7. Follow-up KPIs</h3>
<ul>
<li>Serialization stops per week per line (target ≤0.1/line)</li>
<li>Camera lens fouling interval (target: no fouling within 12h shift)</li>
<li>OEE contribution from serialization losses (target: &lt;0.1 pp)</li>
<li>Cleanroom RH within module (alert if &gt;60% RH)</li>
</ul>
</section>
<section><h3>8. Results</h3>
<p style="background:#cce5ff;padding:0.75rem;border-radius:4px">🔄 <strong>In progress — Phase: IMPROVE (as of April 2026).</strong> Lens cleaning SOP implemented — stops reduced from 3.8/week to 1.6/week. Humidity sensor installed. Air curtain installation in progress. Full results expected June 2026.</p>
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
                category, owner, start_date, target_date, completion_date,
                expected_benefit, actual_benefit, linked_problem_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                site_id, ini["line"], ini["title"], ini["desc"],
                ini["method"], ini["status"], ini.get("category", "Quality"),
                ini["owner"], ini["start"], ini["target"], ini.get("completion"),
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
    # Garantizar datos de tiers e equipment incluso en BDs ya inicializadas
    for site_id in SITES:
        db_path = SITES[site_id]["db_path"]
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            _seed_tiers(site_id, conn)
            _seed_equipment(site_id, conn)
            conn.close()
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
