from widgets.base import BaseWidget
from widgets.data_providers import get_line_speed


class SpeedGaugeWidget(BaseWidget):
    widget_type = "speed_gauge"
    title = "Velocidad"

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        d = get_line_speed(site_id, line_number=line_number)
        d["nominal_speed"] = self.params.get("nominal_speed", 300)
        return d

    def get_echarts_config(self, data: dict) -> dict:
        speed = data.get("speed", 0)
        nominal = data.get("nominal_speed", 300)
        max_val = int(nominal * 1.25)

        t1 = 0.6  # < 60% → rojo
        t2 = 0.9  # < 90% → amarillo, ≥ 90% → verde

        return {
            "backgroundColor": "transparent",
            "series": [
                {
                    "type": "gauge",
                    "min": 0,
                    "max": max_val,
                    "splitNumber": 5,
                    "progress": {"show": True, "roundCap": True, "width": 12},
                    "pointer": {"show": False},
                    "axisLine": {
                        "roundCap": True,
                        "lineStyle": {
                            "width": 12,
                            "color": [
                                [t1, "#e74c3c"],
                                [t2, "#f39c12"],
                                [1, "#27ae60"],
                            ],
                        },
                    },
                    "axisTick": {"show": False},
                    "splitLine": {"show": False},
                    "axisLabel": {"show": True, "color": "#9ca3af", "fontSize": 9, "distance": 16},
                    "detail": {
                        "valueAnimation": True,
                        "fontSize": 20,
                        "color": "#e8e8e8",
                        "formatter": "{value}\nuds/h",
                        "offsetCenter": [0, "5%"],
                    },
                    "title": {
                        "fontSize": 11,
                        "color": "#9ca3af",
                        "offsetCenter": [0, "30%"],
                    },
                    "data": [{"value": int(speed), "name": f"Nominal: {nominal}"}],
                }
            ],
        }
