from widgets.base import BaseWidget
from widgets.data_providers import get_site_oee


class OEEGaugeWidget(BaseWidget):
    widget_type = "oee_gauge"
    title = "OEE"

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        return get_site_oee(site_id, days=1)

    def get_echarts_config(self, data: dict) -> dict:
        oee = data.get("oee", 0)
        thresholds = self.params.get("thresholds", [60, 85])
        colors = self.params.get("colors", ["#e74c3c", "#f39c12", "#27ae60"])
        t1 = thresholds[0] / 100
        t2 = thresholds[1] / 100

        return {
            "backgroundColor": "transparent",
            "series": [
                {
                    "type": "gauge",
                    "startAngle": 200,
                    "endAngle": -20,
                    "min": 0,
                    "max": 100,
                    "splitNumber": 5,
                    "progress": {"show": True, "roundCap": True, "width": 12},
                    "pointer": {"show": False},
                    "axisLine": {
                        "roundCap": True,
                        "lineStyle": {
                            "width": 12,
                            "color": [
                                [t1, colors[0]],
                                [t2, colors[1]],
                                [1, colors[2]],
                            ],
                        },
                    },
                    "axisTick": {"show": False},
                    "splitLine": {"show": False},
                    "axisLabel": {"show": False},
                    "detail": {
                        "valueAnimation": True,
                        "fontSize": 26,
                        "color": "#e8e8e8",
                        "formatter": "{value}%",
                        "offsetCenter": [0, "5%"],
                    },
                    "title": {
                        "fontSize": 12,
                        "color": "#9ca3af",
                        "offsetCenter": [0, "28%"],
                    },
                    "data": [{"value": oee, "name": "OEE"}],
                }
            ],
        }
