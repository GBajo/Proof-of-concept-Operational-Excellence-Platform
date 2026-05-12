from widgets.base import BaseWidget
from widgets.data_providers import get_pareto_data

_CAT_LABELS = {
    "quality": "Calidad",
    "maintenance": "Mantenimiento",
    "production": "Producción",
    "safety": "Seguridad",
    "other": "Otros",
}


class ParetoChartWidget(BaseWidget):
    widget_type = "pareto_chart"
    title = "Pareto de Paradas"

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        days = self.params.get("days", 30)
        max_causes = self.params.get("max_causes", 8)
        return get_pareto_data(site_id, line_number=line_number, days=days, max_causes=max_causes)

    def get_echarts_config(self, data: dict) -> dict:
        raw_labels = data.get("labels", [])
        counts = data.get("counts", [])
        cumulative = data.get("cumulative", [])

        labels = [_CAT_LABELS.get(lb, lb.capitalize()) for lb in raw_labels]

        # Demo si no hay datos
        if not labels:
            labels = ["Mantenimiento", "Calidad", "Producción", "Seguridad", "Otros"]
            counts = [42, 28, 15, 9, 6]
            cumulative = [42.0, 70.0, 85.0, 94.0, 100.0]

        return {
            "backgroundColor": "transparent",
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {
                "data": ["Frecuencia", "% Acumulado"],
                "textStyle": {"color": "#9ca3af"},
                "top": 0,
            },
            "grid": {"left": "3%", "right": "8%", "bottom": "12%", "top": "14%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": labels,
                "axisLabel": {"color": "#9ca3af", "rotate": 20, "fontSize": 11},
                "axisLine": {"lineStyle": {"color": "#444"}},
            },
            "yAxis": [
                {
                    "type": "value",
                    "name": "Frec.",
                    "nameTextStyle": {"color": "#9ca3af", "fontSize": 10},
                    "axisLabel": {"color": "#9ca3af"},
                    "splitLine": {"lineStyle": {"color": "#2a2a2a"}},
                },
                {
                    "type": "value",
                    "name": "% Acum.",
                    "min": 0,
                    "max": 100,
                    "nameTextStyle": {"color": "#9ca3af", "fontSize": 10},
                    "axisLabel": {"color": "#9ca3af", "formatter": "{value}%"},
                    "splitLine": {"show": False},
                },
            ],
            "series": [
                {
                    "name": "Frecuencia",
                    "type": "bar",
                    "data": counts,
                    "itemStyle": {"color": "#3a86ff", "borderRadius": [3, 3, 0, 0]},
                },
                {
                    "name": "% Acumulado",
                    "type": "line",
                    "yAxisIndex": 1,
                    "data": cumulative,
                    "smooth": False,
                    "symbol": "circle",
                    "symbolSize": 6,
                    "lineStyle": {"color": "#f39c12", "width": 2},
                    "itemStyle": {"color": "#f39c12"},
                },
            ],
        }
