from widgets.base import BaseWidget
from widgets.data_providers import get_sqdcp_data

_DIM_LABELS = {
    "seguridad": "Seguridad",
    "calidad": "Calidad",
    "entrega": "Entrega",
    "coste": "Coste",
    "personal": "Personal",
}


class SQDCPSummaryWidget(BaseWidget):
    widget_type = "sqdcp_summary"
    title = "SQDCP"

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        days = self.params.get("days", 7)
        return get_sqdcp_data(site_id, line_number=line_number, days=days)

    def get_echarts_config(self, data: dict) -> dict:
        dims = ["seguridad", "calidad", "entrega", "coste", "personal"]
        values = [data.get(d, 0) for d in dims]
        labels = [_DIM_LABELS[d] for d in dims]

        return {
            "backgroundColor": "transparent",
            "tooltip": {"trigger": "item"},
            "radar": {
                "indicator": [{"name": lb, "max": 100} for lb in labels],
                "axisName": {"color": "#9ca3af", "fontSize": 12},
                "splitLine": {"lineStyle": {"color": "#2a2a2a"}},
                "splitArea": {"areaStyle": {"color": "transparent"}},
                "axisLine": {"lineStyle": {"color": "#444"}},
                "radius": "65%",
            },
            "series": [
                {
                    "type": "radar",
                    "data": [
                        {
                            "value": values,
                            "name": "SQDCP",
                            "areaStyle": {"color": "#3a86ff", "opacity": 0.18},
                            "lineStyle": {"color": "#3a86ff", "width": 2},
                            "itemStyle": {"color": "#3a86ff"},
                            "label": {
                                "show": True,
                                "formatter": "{c}%",
                                "color": "#9ca3af",
                                "fontSize": 10,
                            },
                        }
                    ],
                }
            ],
        }
