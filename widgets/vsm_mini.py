from widgets.base import BaseWidget
from widgets.data_providers import get_vsm_data


class VSMMiniWidget(BaseWidget):
    widget_type = "vsm_mini"
    title = "Flujo de Proceso"

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        return get_vsm_data(site_id, line_number=line_number)

    def get_echarts_config(self, data: dict) -> dict:
        steps = data.get("steps", [])

        if not steps:
            return {}

        names = [s["name"] for s in steps]
        cycle_times = [s["cycle_time"] for s in steps]
        uptimes = [s["uptime"] for s in steps]

        # Cuello de botella: paso con mayor cycle_time
        max_ct = max(cycle_times) if cycle_times else 1

        bar_colors = [
            "#e74c3c" if ct == max_ct else "#3a86ff"
            for ct in cycle_times
        ]

        return {
            "backgroundColor": "transparent",
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "shadow"},
                "formatter": (
                    "function(p){"
                    "let s=p[0];"
                    "return s.name+'<br/>Ciclo: '+s.value+' s<br/>Disponib: '+p[1]?.value+'%';"
                    "}"
                ),
            },
            "legend": {
                "data": ["Tiempo de ciclo (s)", "Disponibilidad (%)"],
                "textStyle": {"color": "#9ca3af"},
                "top": 0,
            },
            "grid": {"left": "3%", "right": "8%", "bottom": "3%", "top": "14%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": names,
                "axisLabel": {"color": "#9ca3af", "fontSize": 11},
                "axisLine": {"lineStyle": {"color": "#444"}},
            },
            "yAxis": [
                {
                    "type": "value",
                    "name": "Ciclo (s)",
                    "nameTextStyle": {"color": "#9ca3af", "fontSize": 10},
                    "axisLabel": {"color": "#9ca3af"},
                    "splitLine": {"lineStyle": {"color": "#2a2a2a"}},
                },
                {
                    "type": "value",
                    "name": "Disponib. (%)",
                    "min": 0,
                    "max": 100,
                    "nameTextStyle": {"color": "#9ca3af", "fontSize": 10},
                    "axisLabel": {"color": "#9ca3af", "formatter": "{value}%"},
                    "splitLine": {"show": False},
                },
            ],
            "series": [
                {
                    "name": "Tiempo de ciclo (s)",
                    "type": "bar",
                    "data": [
                        {"value": ct, "itemStyle": {"color": c}}
                        for ct, c in zip(cycle_times, bar_colors)
                    ],
                    "label": {
                        "show": True,
                        "position": "top",
                        "color": "#9ca3af",
                        "fontSize": 10,
                        "formatter": "{c}s",
                    },
                },
                {
                    "name": "Disponibilidad (%)",
                    "type": "line",
                    "yAxisIndex": 1,
                    "data": uptimes,
                    "smooth": True,
                    "lineStyle": {"color": "#27ae60", "width": 2},
                    "itemStyle": {"color": "#27ae60"},
                    "symbol": "circle",
                    "symbolSize": 6,
                },
            ],
        }
