from widgets.base import BaseWidget
from widgets.data_providers import get_metric_trend

_METRIC_LABELS = {
    "oee": "OEE (%)",
    "units_produced": "Unidades producidas",
    "reject_rate": "Tasa de rechazo (%)",
    "downtime": "Tiempo de paro (min)",
}

_METRIC_COLORS = {
    "oee": "#3a86ff",
    "units_produced": "#27ae60",
    "reject_rate": "#e74c3c",
    "downtime": "#f39c12",
}


class TrendLineWidget(BaseWidget):
    widget_type = "trend_line"
    title = "Tendencia"

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        metric = self.params.get("metric", "oee")
        period = self.params.get("period", "7d")
        return get_metric_trend(site_id, line_number, metric=metric, period=period)

    def get_echarts_config(self, data: dict) -> dict:
        labels = data.get("labels", [])
        values = data.get("values", [])
        metric = data.get("metric", "oee")
        color = self.params.get("color") or _METRIC_COLORS.get(metric, "#3a86ff")
        metric_label = _METRIC_LABELS.get(metric, metric)

        is_pct = metric in ("oee", "reject_rate")
        y_formatter = "{value}%" if is_pct else "{value}"

        return {
            "backgroundColor": "transparent",
            "tooltip": {
                "trigger": "axis",
                "formatter": f"{{b}}<br/>{metric_label}: {{c}}{'%' if is_pct else ''}",
            },
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "top": "8%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": labels,
                "axisLabel": {"color": "#9ca3af", "rotate": 30, "fontSize": 10},
                "axisLine": {"lineStyle": {"color": "#444"}},
                "boundaryGap": False,
            },
            "yAxis": {
                "type": "value",
                "axisLabel": {"color": "#9ca3af", "formatter": y_formatter},
                "splitLine": {"lineStyle": {"color": "#2a2a2a"}},
                **({"min": 0, "max": 100} if is_pct else {}),
            },
            "series": [
                {
                    "name": metric_label,
                    "type": "line",
                    "smooth": True,
                    "symbol": "circle",
                    "symbolSize": 4,
                    "data": values,
                    "lineStyle": {"color": color, "width": 2},
                    "itemStyle": {"color": color},
                    "areaStyle": {"color": color, "opacity": 0.12},
                }
            ],
        }
