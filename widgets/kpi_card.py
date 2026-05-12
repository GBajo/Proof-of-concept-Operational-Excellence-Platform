from widgets.base import BaseWidget
from widgets.data_providers import get_kpi_metric_value

_METRIC_DEFAULTS = {
    "oee":              {"label": "OEE",          "unit": "%"},
    "units_produced":   {"label": "Producción",   "unit": "uds"},
    "reject_rate":      {"label": "Tasa Rechazo", "unit": "%"},
    "downtime_minutes": {"label": "Paros",        "unit": "min"},
    "line_speed":       {"label": "Velocidad",    "unit": "uds/h"},
    "availability":     {"label": "Disponib.",    "unit": "%"},
    "performance":      {"label": "Rendimiento",  "unit": "%"},
    "quality":          {"label": "Calidad",      "unit": "%"},
}


def _status_color(value: float, thresholds: list, metric: str) -> str:
    """Devuelve color CSS según si la métrica debe ser alta (OEE) o baja (rechazos)."""
    low_is_good = metric in ("reject_rate", "downtime_minutes")
    t_warn, t_ok = thresholds[0], thresholds[1]
    if low_is_good:
        if value <= t_warn:
            return "#27ae60"
        if value <= t_ok:
            return "#f39c12"
        return "#e74c3c"
    else:
        if value >= t_ok:
            return "#27ae60"
        if value >= t_warn:
            return "#f39c12"
        return "#e74c3c"


class KPICardWidget(BaseWidget):
    widget_type = "kpi_card"
    title = "KPI"
    render_type = "card"

    _heights = {"small": 110, "medium": 110, "large": 110}

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        metric = self.params.get("metric", "oee")
        days = self.params.get("days", 1)
        result = get_kpi_metric_value(site_id, line_number=line_number, metric=metric, days=days)

        defaults = _METRIC_DEFAULTS.get(metric, {"label": metric, "unit": ""})
        thresholds = self.params.get("thresholds", [60, 85])
        unit = self.params.get("unit") or defaults["unit"]
        label = self.params.get("title") or defaults["label"]

        value = result.get("value", 0)
        trend = result.get("trend", 0)

        # Formatear valor
        if metric == "units_produced":
            display_value = f"{int(value):,}".replace(",", ".")
        else:
            display_value = str(round(value, 1))

        color = _status_color(value, thresholds, metric)
        trend_label = f"+{trend}" if trend >= 0 else str(trend)
        trend_class = "pp-faint" if trend == 0 else ("pp-ok" if trend > 0 else "pp-bad")

        return {
            "label": label,
            "value": display_value,
            "unit": unit,
            "color": color,
            "trend": trend,
            "trend_label": trend_label,
            "trend_class": trend_class,
            "metric": metric,
        }
