from flask import Blueprint, jsonify, request
from models.kpi import (
    create_kpi_reading, get_kpi_readings_by_shift,
    get_latest_kpi_reading, calculate_oee,
)

bp = Blueprint("kpis", __name__)


@bp.post("/api/kpis")
def add_kpi():
    data = request.get_json(silent=True) or {}
    required = ("shift_id", "units_produced", "units_rejected",
                 "downtime_minutes", "line_speed", "target_units", "nominal_speed")
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Campos requeridos: {', '.join(missing)}"}), 400

    try:
        row_id = create_kpi_reading(
            shift_id=int(data["shift_id"]),
            units_produced=int(data["units_produced"]),
            units_rejected=int(data["units_rejected"]),
            downtime_minutes=float(data["downtime_minutes"]),
            line_speed=float(data["line_speed"]),
            target_units=int(data["target_units"]),
            nominal_speed=float(data["nominal_speed"]),
            planned_time_min=float(data.get("planned_time_min", 480.0)),
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"id": row_id}), 201


@bp.get("/api/kpis/<int:shift_id>")
def list_kpis(shift_id: int):
    return jsonify(get_kpi_readings_by_shift(shift_id))


@bp.get("/api/kpis/<int:shift_id>/latest")
def latest_kpi(shift_id: int):
    reading = get_latest_kpi_reading(shift_id)
    if not reading:
        return jsonify({"error": "Sin lecturas KPI para este turno"}), 404
    reading["oee_snapshot"] = calculate_oee(shift_id)
    return jsonify(reading)


@bp.get("/api/kpis/<int:shift_id>/aggregate")
def aggregate_kpis(shift_id: int):
    return jsonify(calculate_oee(shift_id))
