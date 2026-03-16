from dash import html, dcc


def build_particles(count: int = 20):
    return html.Div(
        [
            html.Div(
                className="particle",
                style={
                    "left": f"{i * 5}%",
                    "animationDelay": f"{i * 0.7}s",
                    "animationDuration": f"{10 + (i % 5) * 2}s",
                },
            )
            for i in range(count)
        ],
        className="particles",
    )


def build_layout():
    return html.Div(
        [
            html.Div(className="bg-grid"),
            build_particles(),
            html.Div(className="scanlines"),

            dcc.Interval(id="refresh", interval=2000, n_intervals=0),

            html.Header(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div("⚡", className="logo-icon"),
                                            html.Div(className="logo-glow"),
                                        ],
                                        className="logo-container",
                                    ),
                                    html.Div(
                                        [
                                            html.H1("VoltaNet Live Grid"),
                                            html.P("Real-time Microgrid Monitoring System"),
                                        ],
                                        className="brand-text",
                                    ),
                                ],
                                className="brand",
                            ),
                            html.Div(
                                [
                                    html.Div(className="pulse-ring"),
                                    html.Span("Live", className="live-text"),
                                ],
                                className="live-indicator",
                            ),
                        ],
                        className="header-content",
                    )
                ],
                className="dashboard-header",
            ),

            html.Main(
                [
                    html.Div(id="cluster-metrics", className="metrics-grid"),

                    html.Div(
                        [
                            html.Div(
                                [html.H2("Cluster Demand", className="chart-title")],
                                className="chart-header",
                            ),
                            dcc.Graph(id="demand-chart", config={"displayModeBar": False}),
                        ],
                        className="chart-container",
                    ),

                    html.Div(
                        [
                            html.Div(
                                [html.H2("Live Grid Nodes", className="section-title")],
                                className="section-header",
                            ),
                            html.Div(id="node-grid", className="nodes-grid"),
                        ],
                        className="nodes-section",
                    ),
                ],
                className="dashboard-container",
            ),
        ]
    )