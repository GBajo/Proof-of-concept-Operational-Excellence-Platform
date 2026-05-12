from widgets.base import BaseWidget
from widgets.data_providers import get_reject_distribution

_CAT_COLORS = {
    "quality": "#e74c3c",
    "maintenance": "#f39c12",
    "production": "#3a86ff",
    "safety": "#7c3aed",
}
_CAT_LABELS = {
    "quality": "Calidad",
    "maintenance": "Mantenimiento",
    "production": "Producción",
    "safety": "Seguridad",
}


class RejectDonutWidget(BaseWidget):
    widget_type = "reject_donut"
    title = "Rechazos"

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        days = self.params.get("days", 7)
        return get_reject_distribution(site_id, line_number=line_number, days=days)

    def get_echarts_config(self, data: dict) -> dict:
        good = data.get("good", 0)
        rejected = data.get("rejected", 0)
        categories = data.get("categories", {})

        # Si no hay datos usa demo
        if good == 0 and rejected == 0:
            good, rejected = 18500, 480

        # Construir segmentos de categoría para los rechazos
        if categories and rejected > 0:
            series_data = [
                {
                    "value": good,
                    "name": "Buenas",
                    "itemStyle": {"color": "#27ae60"},
                }
            ]
            for cat, cnt in categories.items():
                series_data.append(
                    {
                        "value": cnt,
                        "name": _CAT_LABELS.get(cat, cat.capitalize()),
                        "itemStyle": {"color": _CAT_COLORS.get(cat, "#888")},
                    }
                )
        else:
            series_data = [
                {"value": good, "name": "Buenas", "itemStyle": {"color": "#27ae60"}},
                {"value": rejected, "name": "Rechazadas", "itemStyle": {"color": "#e74c3c"}},
            ]

        return {
            "backgroundColor": "transparent",
            "tooltip": {
                "trigger": "item",
                "formatter": "{b}: {c} ({d}%)",
            },
            "legend": {
                "orient": "vertical",
                "right": "2%",
                "top": "center",
                "textStyle": {"color": "#9ca3af", "fontSize": 11},
            },
            "series": [
                {
                    "type": "pie",
                    "radius": ["40%", "70%"],
                    "center": ["40%", "50%"],
                    "avoidLabelOverlap": True,
                    "label": {"show": False},
                    "emphasis": {
                        "label": {"show": True, "fontSize": 13, "fontWeight": "bold", "color": "#e8e8e8"}
                    },
                    "data": series_data,
                }
            ],
        }
