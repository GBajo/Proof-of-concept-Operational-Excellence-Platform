"""
seed_data.py — Poblar la base de datos con datos de muestra.
Ejecutar una vez: python seed_data.py
Es idempotente: omite si ya hay datos.
"""

import sqlite3
import random
from datetime import datetime, timedelta
from config import config

DB_PATH = config.DATABASE_PATH

OPERATORS = [
    ("Carlos Martínez", "operator",   "OP-001"),
    ("Ana García",       "operator",   "OP-002"),
    ("Luis Fernández",   "operator",   "OP-003"),
    ("María López",      "supervisor", "SV-001"),
    ("Pedro Sánchez",    "quality",    "QA-001"),
]

COMMENTS_POOL = {
    "production": [
        "Velocidad de línea estable, sin incidencias.",
        "Cambio de formato completado en 12 minutos.",
        "Lote {lot} iniciado correctamente.",
        "Contador de unidades actualizado en HMI.",
        "Pausa programada de 10 minutos para limpieza CIP.",
        "Producción al 95% del objetivo del turno.",
        "Selladora funcionando correctamente tras ajuste.",
        "Alimentación de blisters sin atascos.",
    ],
    "quality": [
        "Muestra de control tomada a las {time} — conforme.",
        "Revisión AQL en lote {lot}: 0 defectos críticos.",
        "Ajuste de peso neto en tolva tras desviación.",
        "Temperatura de sellado verificada: 185°C ± 2°C.",
        "Etiqueta de trazabilidad aplicada correctamente.",
        "Comprobación de impermeabilidad: OK.",
    ],
    "safety": [
        "EPI completo verificado al inicio del turno.",
        "Zona de trabajo despejada y señalizada.",
        "Prueba de parada de emergencia realizada.",
        "Derrame menor limpiado, área asegurada.",
        "Bloqueo LOTO aplicado en cinta transportadora 3.",
    ],
    "maintenance": [
        "Lubricación de cadena de transporte realizada.",
        "Sensor de presencia ajustado en estación 4.",
        "Cambio de filtro HEPA en cabina de llenado.",
        "Ruido inusual en selladora — reportado a mantenimiento.",
        "Parada por atasco en etiquetadora — resuelta en 8 min.",
        "Revisión preventiva de compresor completada.",
    ],
}

LOT_NUMBERS = [f"LOT-2026-{str(i).zfill(3)}" for i in range(1, 15)]


def seed() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    # Idempotencia
    count = conn.execute("SELECT COUNT(*) FROM operators").fetchone()[0]
    if count > 0:
        print("Los datos ya están sembrados. Omitiendo.")
        conn.close()
        return

    # 1. Operadores
    op_ids = []
    for name, role, badge in OPERATORS:
        cur = conn.execute(
            "INSERT INTO operators (name, role, badge_number) VALUES (?,?,?)",
            (name, role, badge),
        )
        op_ids.append(cur.lastrowid)
    conn.commit()
    print(f"  + {len(op_ids)} operarios insertados")

    operator_ids = op_ids[:3]  # solo operarios de línea

    # 2. Turnos históricos (líneas 1-3, últimos 5 días, 2 turnos/día)
    shift_ids = []
    now = datetime.utcnow()
    shift_hours = {"morning": 6, "afternoon": 14, "night": 22}

    for line in range(1, 4):
        for day_offset in range(5, 0, -1):
            for turn_idx, stype in enumerate(["morning", "afternoon"]):
                base_date = now - timedelta(days=day_offset)
                start = base_date.replace(
                    hour=shift_hours[stype], minute=0, second=0, microsecond=0
                )
                end = start + timedelta(hours=8)
                op_id = random.choice(operator_ids)
                cur = conn.execute(
                    """INSERT INTO shifts
                       (operator_id, line_number, start_time, end_time, status, shift_type)
                       VALUES (?,?,?,?,'completed',?)""",
                    (op_id, line,
                     start.strftime("%Y-%m-%dT%H:%M:%S"),
                     end.strftime("%Y-%m-%dT%H:%M:%S"),
                     stype),
                )
                shift_ids.append((cur.lastrowid, start, end, op_id, line))
    conn.commit()

    # 3. Turno activo en línea 1
    active_start = now - timedelta(hours=3)
    active_op = operator_ids[0]
    cur = conn.execute(
        """INSERT INTO shifts
           (operator_id, line_number, start_time, status, shift_type)
           VALUES (?,1,?,'active','morning')""",
        (active_op, active_start.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    active_shift_id = cur.lastrowid
    shift_ids.append((active_shift_id, active_start, None, active_op, 1))
    conn.commit()
    print(f"  + {len(shift_ids)} turnos insertados (1 activo)")

    # 4. KPI readings (cada 15 min por turno completado)
    kpi_count = 0
    nominal_speed = 1200.0
    target_units = 9600

    for shift_id, start, end, op_id, line in shift_ids:
        duration_h = 8 if end else 3
        intervals = int(duration_h * 60 / 15)
        cumulative_produced = 0
        cumulative_rejected = 0
        cumulative_downtime = 0.0

        for i in range(intervals):
            ts = start + timedelta(minutes=15 * i)
            # Velocidad con algo de variación
            speed = nominal_speed * random.uniform(0.80, 1.05)
            units_this = int(speed / 4)  # 15 min = speed/4
            rejected_this = max(0, int(units_this * random.uniform(0.01, 0.06)))
            downtime_this = random.choices(
                [0.0, random.uniform(3, 12)], weights=[85, 15]
            )[0]

            cumulative_produced += units_this
            cumulative_rejected += rejected_this
            cumulative_downtime += downtime_this

            conn.execute(
                """INSERT INTO kpi_readings
                   (shift_id, timestamp, units_produced, units_rejected,
                    downtime_minutes, line_speed, target_units, nominal_speed, planned_time_min)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (shift_id, ts.strftime("%Y-%m-%dT%H:%M:%S"),
                 cumulative_produced, cumulative_rejected,
                 round(cumulative_downtime, 1), round(speed, 1),
                 target_units, nominal_speed, 480.0),
            )
            kpi_count += 1

    conn.commit()
    print(f"  + {kpi_count} lecturas KPI insertadas")

    # 5. Comentarios por turno
    comment_count = 0
    categories = list(COMMENTS_POOL.keys())
    cat_weights = [0.40, 0.25, 0.15, 0.20]

    for shift_id, start, end, op_id, line in shift_ids:
        n_comments = random.randint(6, 12)
        duration_h = 8 if end else 3
        for j in range(n_comments):
            cat = random.choices(categories, weights=cat_weights)[0]
            template = random.choice(COMMENTS_POOL[cat])
            text = template.format(
                lot=random.choice(LOT_NUMBERS),
                time=(start + timedelta(hours=random.uniform(0, duration_h))).strftime("%H:%M"),
            )
            ts = start + timedelta(hours=random.uniform(0.1, duration_h - 0.1))
            source = random.choice(["voice", "voice", "manual"])
            conn.execute(
                """INSERT INTO comments
                   (shift_id, operator_id, text, timestamp, category, source)
                   VALUES (?,?,?,?,?,?)""",
                (shift_id, op_id, text, ts.strftime("%Y-%m-%dT%H:%M:%S"), cat, source),
            )
            comment_count += 1

    conn.commit()
    print(f"  + {comment_count} comentarios insertados")
    conn.close()
    print("\nDatos sembrados correctamente.")


if __name__ == "__main__":
    # Crear schema si no existe
    from app import create_app
    app = create_app()
    print("Sembrando datos de muestra...")
    with app.app_context():
        seed()
