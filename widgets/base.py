"""Clase base y factoría para todos los widgets del dashboard."""
from __future__ import annotations


class BaseWidget:
    widget_type: str = ""
    title: str = ""
    render_type: str = "chart"  # "chart" | "card"

    _heights: dict[str, int] = {"small": 220, "medium": 260, "large": 280}

    def __init__(self, config: dict) -> None:
        self.params: dict = config.get("params", {})
        self.size: str = config.get("size", "small")

    def get_data(self, site_id: str, line_number: int | None = None) -> dict:
        return {}

    def get_echarts_config(self, data: dict) -> dict:
        return {}

    def render(self, site_id: str, line_number: int | None = None) -> dict:
        try:
            data = self.get_data(site_id, line_number)
        except Exception:
            data = {}

        base = {
            "widget_type": self.widget_type,
            "size": self.size,
            "render_type": self.render_type,
            "title": self.params.get("title") or self.title,
            "height": self._heights.get(self.size, 240),
        }

        if self.render_type == "card":
            base["card_data"] = data
        else:
            try:
                base["echarts_config"] = self.get_echarts_config(data)
            except Exception:
                base["echarts_config"] = {}

        return base


def create_widget(widget_type: str, config: dict) -> BaseWidget:
    """Factoría: devuelve la instancia correcta dado widget_type."""
    from widgets.oee_gauge import OEEGaugeWidget
    from widgets.production_bars import ProductionBarsWidget
    from widgets.trend_line import TrendLineWidget
    from widgets.reject_donut import RejectDonutWidget
    from widgets.kpi_card import KPICardWidget
    from widgets.downtime_heatmap import DowntimeHeatmapWidget
    from widgets.pareto_chart import ParetoChartWidget
    from widgets.speed_gauge import SpeedGaugeWidget
    from widgets.vsm_mini import VSMMiniWidget
    from widgets.sqdcp_summary import SQDCPSummaryWidget

    _map: dict[str, type] = {
        "oee_gauge": OEEGaugeWidget,
        "production_bars": ProductionBarsWidget,
        "trend_line": TrendLineWidget,
        "reject_donut": RejectDonutWidget,
        "kpi_card": KPICardWidget,
        "downtime_heatmap": DowntimeHeatmapWidget,
        "pareto_chart": ParetoChartWidget,
        "speed_gauge": SpeedGaugeWidget,
        "vsm_mini": VSMMiniWidget,
        "sqdcp_summary": SQDCPSummaryWidget,
    }

    cls = _map.get(widget_type, BaseWidget)
    return cls(config)
