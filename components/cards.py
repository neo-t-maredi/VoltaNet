from dash import html


def get_battery_color(soc: float) -> str:
    if soc >= 60:
        return "#00ff88"
    if soc >= 30:
        return "#ffaa00"
    return "#ff3366"


def get_battery_class(soc: float) -> str:
    if soc >= 60:
        return "high"
    if soc >= 30:
        return "medium"
    return "low"


def build_metric_cards(snapshot: dict):
    return [
        html.Div(
            [
                html.Div("⚡", className="metric-icon-wrapper"),
                html.Div(f"{snapshot['total_kw_demand']:.1f} kW", className="metric-value"),
                html.Div("Total Demand", className="metric-label"),
            ],
            className="metric-card demand",
        ),
        html.Div(
            [
                html.Div("🔌", className="metric-icon-wrapper"),
                html.Div(f"{snapshot['active_nodes']}", className="metric-value"),
                html.Div("Active Nodes", className="metric-label"),
            ],
            className="metric-card nodes",
        ),
        html.Div(
            [
                html.Div("🔋", className="metric-icon-wrapper"),
                html.Div(f"{snapshot['avg_battery_soc_pct']:.1f}%", className="metric-value"),
                html.Div("Avg Battery", className="metric-label"),
            ],
            className="metric-card battery",
        ),
        html.Div(
            [
                html.Div("☀️", className="metric-icon-wrapper"),
                html.Div(f"{snapshot['total_solar_kw']:.1f} kW", className="metric-value"),
                html.Div("Solar Output", className="metric-label"),
            ],
            className="metric-card solar",
        ),
    ]


def build_node_cards(nodes: list):
    cards = []

    for node in nodes:
        soc = node["battery_soc"]
        color = get_battery_color(soc)
        battery_class = get_battery_class(soc)

        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                node["meter_id"].replace("_", " ").title(),
                                className="node-id",
                            ),
                            html.Div(
                                [
                                    html.Span(className="status-dot"),
                                    "Online",
                                ],
                                className="node-status",
                            ),
                        ],
                        className="node-header",
                    ),
                    html.Div(f"{node['kw_demand']:.1f} kW", className="node-power"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Solar", className="stat-label"),
                                    html.Span(
                                        f"{node['solar_kw']:.1f} kW",
                                        className="stat-value solar",
                                    ),
                                ],
                                className="stat-item",
                            ),
                            html.Div(
                                [
                                    html.Span("Load", className="stat-label"),
                                    html.Span(
                                        f"{node['kw_demand']:.1f} kW",
                                        className="stat-value",
                                    ),
                                ],
                                className="stat-item",
                            ),
                        ],
                        className="node-stats",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Battery Level", className="battery-label"),
                                    html.Span(
                                        f"{soc:.0f}%",
                                        className="battery-percentage",
                                        style={"color": color},
                                    ),
                                ],
                                className="battery-info",
                            ),
                            html.Div(
                                html.Div(
                                    className=f"battery-fill {battery_class}",
                                    style={"width": f"{max(0.0, min(100.0, soc))}%"},
                                ),
                                className="battery-track",
                            ),
                        ],
                        className="battery-wrapper",
                    ),
                ],
                className="node-card",
            )
        )

    return cards