import sqlite3
from flask import g, current_app


def get_db() -> sqlite3.Connection:
    """Devuelve la conexión a la BD para la solicitud actual."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None) -> None:
    """Cierra la conexión al finalizar la solicitud."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app) -> None:
    """Crea las tablas si no existen."""
    with app.app_context():
        db = sqlite3.connect(app.config["DATABASE_PATH"])
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
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

            CREATE INDEX IF NOT EXISTS idx_shifts_operator   ON shifts(operator_id);
            CREATE INDEX IF NOT EXISTS idx_shifts_status     ON shifts(status);
            CREATE INDEX IF NOT EXISTS idx_shifts_line       ON shifts(line_number);
            CREATE INDEX IF NOT EXISTS idx_comments_shift    ON comments(shift_id);
            CREATE INDEX IF NOT EXISTS idx_comments_ts       ON comments(timestamp);
            CREATE INDEX IF NOT EXISTS idx_kpi_shift         ON kpi_readings(shift_id);
            CREATE INDEX IF NOT EXISTS idx_kpi_ts            ON kpi_readings(timestamp);

            CREATE TABLE IF NOT EXISTS knowledge_base (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'file'
                            CHECK(source_type IN ('pdf','docx','xlsx','url')),
                chunk_index INTEGER NOT NULL,
                chunk_text  TEXT NOT NULL,
                indexed_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_kb_source ON knowledge_base(source_file);

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

            CREATE INDEX IF NOT EXISTS idx_sugg_shift   ON assistant_suggestions(shift_id);
            CREATE INDEX IF NOT EXISTS idx_sugg_comment ON assistant_suggestions(comment_id);

            CREATE TABLE IF NOT EXISTS saved_charts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT NOT NULL,
                prompt_text  TEXT NOT NULL,
                echarts_json TEXT NOT NULL,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_charts_created ON saved_charts(created_at);

            -- ── VSM: pasos de proceso por línea ──────────────────────────
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

            CREATE INDEX IF NOT EXISTS idx_process_steps_line ON process_steps(line_number);
            CREATE INDEX IF NOT EXISTS idx_step_live_step      ON step_live_data(step_id);
            CREATE INDEX IF NOT EXISTS idx_step_live_ts        ON step_live_data(timestamp);
        """)
        # Índice parcial único: solo un turno activo por línea
        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_shifts_active_line
            ON shifts(line_number) WHERE status = 'active'
        """)
        db.commit()
        db.close()
