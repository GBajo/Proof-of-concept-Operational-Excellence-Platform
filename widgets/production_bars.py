from widgets.base import BaseWidget
from widgets.data_providers import get_line_performance


class ProductionBarsWidget(BaseWidget):
    widget_type = "production_bars"
    title = "Producción vs Objetivo"

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        days = self.params.get("days", 7)
        rows = get_line_performance(site_id, line_number=line_number, days=days)
        return {"rows": rows}

    def get_echarts_config(self, data: dict) -> dict:
        rows = data.get("rows", [])
        color_real = self.params.get("color_real", "#3a86ff")
        color_target = self.params.get("color_target", "#555555")

        labels = [f"L{r['line_number']}" for r in rows]
        real_vals = [int(r.get("total_units") or 0) for r in rows]
        target_vals = [int(r.get("target_units") or 0) for r in rows]

        # Si no hay datos reales, mostrar demo
        if not labels:
            labels = ["L1", "L2", "L3", "L4", "L5"]
            real_vals = [18400, 21200, 15800, 22500, 19100]
            target_vals = [20000, 20000, 20000, 20000, 20000]

        return {
            "backgroundColor": "transparent",
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {
                "data": ["Real", "Objetivo"],
                "textStyle": {"color": "#9ca3af"},
                "top": 0,
            },
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "top": "14%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": labels,
                "axisLabel": {"color": "#9ca3af"},
                "axisLine": {"lineStyle": {"color": "#444"}},
            },
            "yAxis": {
                "type": "value",
                "axisLabel": {"color": "#9ca3af"},
                "splitLine": {"lineStyle": {"color": "#2a2a2a"}},
            },
            "series": [
                {
                    "name": "Real",
                    "type": "bar",
                    "data": real_vals,
                    "itemStyle": {"color": color_real, "borderRadius": [3, 3, 0, 0]},
                },
                {
                    "name": "Objetivo",
                    "type": "bar",
                    "data": target_vals,
                    "itemStyle": {"color": color_target, "borderRadius": [3, 3, 0, 0]},
                },
            ],
        }
