"""Catálogo de widgets disponibles para dashboards configurables."""

WIDGET_REGISTRY: dict = {
    "oee_gauge": {
        "widget_type": "oee_gauge",
        "name": "OEE Gauge",
        "description": "Indicador circular de OEE con zonas rojo/amarillo/verde",
        "default_size": "small",
        "data_source": "get_site_oee",
        "configurable_params": {
            "thresholds": {"type": "list", "default": [60, 85], "label": "Umbrales (%)"},
            "colors": {
                "type": "list",
                "default": ["#e74c3c", "#f39c12", "#27ae60"],
                "label": "Colores R/A/V",
            },
            "title": {"type": "string", "default": "OEE", "label": "Título"},
        },
    },
    "production_bars": {
        "widget_type": "production_bars",
        "name": "Producción vs Objetivo",
        "description": "Barras comparando producción real vs objetivo por línea",
        "default_size": "medium",
        "data_source": "get_line_performance",
        "configurable_params": {
            "days": {"type": "int", "default": 7, "label": "Últimos N días"},
            "color_real": {"type": "string", "default": "#3a86ff", "label": "Color real"},
            "color_target": {"type": "string", "default": "#555", "label": "Color objetivo"},
            "title": {"type": "string", "default": "Producción vs Objetivo", "label": "Título"},
        },
    },
    "trend_line": {
        "widget_type": "trend_line",
        "name": "Tendencia",
        "description": "Línea de tendencia de cualquier métrica a lo largo del tiempo",
        "default_size": "large",
        "data_source": "get_metric_trend",
        "configurable_params": {
            "metric": {
                "type": "select",
                "options": ["oee", "units_produced", "reject_rate", "downtime"],
                "default": "oee",
                "label": "Métrica",
            },
            "period": {
                "type": "select",
                "options": ["24h", "7d", "30d"],
                "default": "7d",
                "label": "Período",
            },
            "color": {"type": "string", "default": "#3a86ff", "label": "Color"},
            "title": {"type": "string", "default": "Tendencia OEE", "label": "Título"},
        },
    },
    "reject_donut": {
        "widget_type": "reject_donut",
        "name": "Distribución de Rechazos",
        "description": "Gráfico de dona mostrando distribución de unidades buenas vs rechazadas",
        "default_size": "small",
        "data_source": "get_reject_distribution",
        "configurable_params": {
            "days": {"type": "int", "default": 7, "label": "Últimos N días"},
            "title": {"type": "string", "default": "Rechazos", "label": "Título"},
        },
    },
    "kpi_card": {
        "widget_type": "kpi_card",
        "name": "Tarjeta KPI",
        "description": "Tarjeta de métrica con valor actual, tendencia y semáforo de color",
        "default_size": "small",
        "data_source": "get_kpi_metric_value",
        "configurable_params": {
            "metric": {
                "type": "select",
                "options": [
                    "oee",
                    "units_produced",
                    "reject_rate",
                    "downtime_minutes",
                    "line_speed",
                    "availability",
                    "performance",
                    "quality",
                ],
                "default": "oee",
                "label": "Métrica",
            },
            "thresholds": {"type": "list", "default": [60, 85], "label": "Umbrales OK/Warn"},
            "title": {"type": "string", "default": "", "label": "Título personalizado"},
            "unit": {"type": "string", "default": "%", "label": "Unidad"},
        },
    },
    "downtime_heatmap": {
        "widget_type": "downtime_heatmap",
        "name": "Heatmap de Paradas",
        "description": "Mapa de calor de tiempo de parada por hora y día de la semana",
        "default_size": "large",
        "data_source": "get_downtime_heatmap",
        "configurable_params": {
            "days": {"type": "int", "default": 14, "label": "Últimos N días"},
            "title": {
                "type": "string",
                "default": "Paradas por Hora/Día",
                "label": "Título",
            },
        },
    },
    "pareto_chart": {
        "widget_type": "pareto_chart",
        "name": "Pareto de Paradas",
        "description": "Diagrama de Pareto de causas de incidencia por frecuencia acumulada",
        "default_size": "large",
        "data_source": "get_pareto_data",
        "configurable_params": {
            "days": {"type": "int", "default": 30, "label": "Últimos N días"},
            "max_causes": {"type": "int", "default": 8, "label": "Máx. causas"},
            "title": {"type": "string", "default": "Pareto de Paradas", "label": "Título"},
        },
    },
    "speed_gauge": {
        "widget_type": "speed_gauge",
        "name": "Velocidad de Línea",
        "description": "Indicador de velocidad actual vs velocidad nominal de la línea",
        "default_size": "small",
        "data_source": "get_line_speed",
        "configurable_params": {
            "nominal_speed": {
                "type": "int",
                "default": 300,
                "label": "Velocidad nominal (uds/h)",
            },
            "title": {"type": "string", "default": "Velocidad", "label": "Título"},
        },
    },
    "vsm_mini": {
        "widget_type": "vsm_mini",
        "name": "VSM Mini",
        "description": "Mapa de flujo de valor simplificado con tiempos de ciclo por proceso",
        "default_size": "large",
        "data_source": "get_vsm_data",
        "configurable_params": {
            "title": {"type": "string", "default": "Flujo de Proceso", "label": "Título"},
        },
    },
    "sqdcp_summary": {
        "widget_type": "sqdcp_summary",
        "name": "SQDCP Resumen",
        "description": "Radar de indicadores Seguridad / Calidad / Entrega / Coste / Personal",
        "default_size": "large",
        "data_source": "get_sqdcp_data",
        "configurable_params": {
            "days": {"type": "int", "default": 7, "label": "Últimos N días"},
            "title": {"type": "string", "default": "SQDCP", "label": "Título"},
        },
    },
}
