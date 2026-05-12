from widgets.base import BaseWidget
from widgets.data_providers import get_downtime_heatmap

_DOW_LABELS = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
_HOURS = [f"{h:02d}h" for h in range(6, 23)]  # 06h..22h


class DowntimeHeatmapWidget(BaseWidget):
    widget_type = "downtime_heatmap"
    title = "Heatmap de Paradas"

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        days = self.params.get("days", 14)
        return get_downtime_heatmap(site_id, line_number=line_number, days=days)

    def get_echarts_config(self, data: dict) -> dict:
        raw = data.get("data", [])
        max_val = data.get("max_val", 10)

        # Filtrar a rango horario laboral (6-22h) y remapear índice x
        plot_data = []
        for hour, dow, value in raw:
            if 6 <= hour <= 22:
                plot_data.append([hour - 6, dow, value])

        # Si no hay datos, generar demo
        if not plot_data:
            import random

            random.seed(42)
            for h in range(17):
                for d in range(7):
                    v = round(random.uniform(0, 25) if random.random() > 0.6 else 0, 1)
                    if v > 0:
                        plot_data.append([h, d, v])
            max_val = 25

        return {
            "backgroundColor": "transparent",
            "tooltip": {
                "position": "top",
                "formatter": "params => `${params.value[2]} min`",
            },
            "grid": {"left": "8%", "right": "5%", "bottom": "10%", "top": "5%"},
            "xAxis": {
                "type": "category",
                "data": _HOURS,
                "splitArea": {"show": True, "areaStyle": {"color": ["rgba(255,255,255,0.02)", "transparent"]}},
                "axisLabel": {"color": "#9ca3af", "fontSize": 10},
                "axisLine": {"lineStyle": {"color": "#444"}},
            },
            "yAxis": {
                "type": "category",
                "data": _DOW_LABELS,
                "splitArea": {"show": True, "areaStyle": {"color": ["rgba(255,255,255,0.02)", "transparent"]}},
                "axisLabel": {"color": "#9ca3af"},
                "axisLine": {"lineStyle": {"color": "#444"}},
            },
            "visualMap": {
                "min": 0,
                "max": max_val,
                "calculable": True,
                "orient": "horizontal",
                "left": "center",
                "bottom": "0%",
                "textStyle": {"color": "#9ca3af", "fontSize": 10},
                "inRange": {"color": ["#1a1a2e", "#e74c3c"]},
            },
            "series": [
                {
                    "type": "heatmap",
                    "data": plot_data,
                    "label": {"show": False},
                    "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0,0,0,0.5)"}},
                }
            ],
        }
