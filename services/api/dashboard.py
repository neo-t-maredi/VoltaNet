import os
import psycopg2
import plotly.graph_objs as go

from dash import Dash, html, dcc, Output, Input
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "voltanet"),
        user=os.getenv("POSTGRES_USER", "voltanet_user"),
        password=os.getenv("POSTGRES_PASSWORD", "voltanet_secret_2025"),
    )


def fetch_cluster_snapshot():
    query = """
    WITH latest_per_meter AS (
        SELECT DISTINCT ON (meter_id)
            meter_id,
            time,
            kw_demand,
            solar_kw,
            battery_soc_pct
        FROM readings
        ORDER BY meter_id, time DESC
    )
    SELECT
        COUNT(*) AS active_nodes,
        COALESCE(SUM(kw_demand), 0) AS total_kw_demand,
        COALESCE(SUM(solar_kw), 0) AS total_solar_kw,
        COALESCE(AVG(battery_soc_pct), 0) AS avg_battery_soc_pct,
        MAX(time) AS latest_time
    FROM latest_per_meter;
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()

        return {
            "active_nodes": row[0],
            "total_kw_demand": float(row[1]),
            "total_solar_kw": float(row[2]),
            "avg_battery_soc_pct": float(row[3]),
            "latest_time": str(row[4]),
        }
    finally:
        conn.close()


def fetch_demand_timeseries():
    query = """
    SELECT
        time_bucket('5 seconds', time) AS bucket,
        AVG(kw_demand) AS avg_kw
    FROM readings
    WHERE time > NOW() - INTERVAL '5 minutes'
    GROUP BY bucket
    ORDER BY bucket;
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

        times = [r[0] for r in rows]
        demand = [float(r[1]) for r in rows]

        return times, demand
    finally:
        conn.close()


def fetch_node_snapshot():
    query = """
    SELECT DISTINCT ON (meter_id)
        meter_id,
        kw_demand,
        solar_kw,
        battery_soc_pct,
        time
    FROM readings
    ORDER BY meter_id, time DESC;
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

        nodes = []
        for r in rows:
            nodes.append(
                {
                    "meter_id": r[0],
                    "kw_demand": float(r[1]),
                    "solar_kw": float(r[2]),
                    "battery_soc": float(r[3]),
                    "time": r[4],
                }
            )

        return nodes
    finally:
        conn.close()

def battery_bar(soc):

    if soc >= 60:
        color = "#22c55e"
    elif soc >= 30:
        color = "#f59e0b"
    else:
        color = "#ef4444"

    return html.Div(
        [
            html.Div(
                style={
                    "width": f"{soc}%",
                    "height": "8px",
                    "backgroundColor": color,
                    "borderRadius": "6px",
                }
            )
        ],
        style={
            "width": "100%",
            "height": "8px",
            "backgroundColor": "#1f2937",
            "borderRadius": "6px",
            "marginTop": "6px",
        },
    )


def battery_color(soc: float) -> str:
    if soc >= 60:
        return "#22c55e"
    if soc >= 30:
        return "#f59e0b"
    return "#ef4444"


app = Dash(__name__)
app.title = "VoltaNet Live Grid"

app.layout = html.Div(
    [
        dcc.Interval(
            id="refresh",
            interval=2000,
            n_intervals=0,
        ),
        html.Div(
            [
                html.H1(
                    "VoltaNet Live Grid",
                    style={
                        "marginBottom": "8px",
                        "fontSize": "52px",
                        "fontWeight": "700",
                        "letterSpacing": "-1px",
                    },
                ),
                html.P(
                    "Real-time SME microgrid monitoring dashboard",
                    style={
                        "marginTop": "0",
                        "color": "#94a3b8",
                        "fontSize": "18px",
                    },
                ),
            ]
        ),
        html.Div(
            id="cluster-metrics",
            style={"marginTop": "28px"},
        ),
        html.Div(
            [
                html.H3(
                    "Cluster Demand",
                    style={
                        "marginTop": "42px",
                        "marginBottom": "16px",
                        "fontSize": "24px",
                        "fontWeight": "600",
                        "color": "#e5e7eb",
                    },
                ),
                dcc.Graph(id="demand-chart"),
            ]
        ),
        html.Div(
            [
                html.H3(
                    "Live Grid Nodes",
                    style={
                        "marginTop": "42px",
                        "marginBottom": "16px",
                        "fontSize": "24px",
                        "fontWeight": "600",
                        "color": "#e5e7eb",
                    },
                ),
                html.Div(id="node-grid"),
            ]
        ),
    ],
    style={
        "backgroundColor": "#020617",
        "color": "#e5e7eb",
        "minHeight": "100vh",
        "padding": "32px",
        "fontFamily": "Arial, sans-serif",
    },
)


@app.callback(
    Output("cluster-metrics", "children"),
    Input("refresh", "n_intervals"),
)
def update_cluster_metrics(_):
    snapshot = fetch_cluster_snapshot()

    return html.Div(
        [
            html.Div(
                [
                    html.H2(f"{snapshot['total_kw_demand']:.1f} kW"),
                    html.P("Total Demand"),
                ],
                className="card",
            ),
            html.Div(
                [
                    html.H2(f"{snapshot['active_nodes']}"),
                    html.P("Active Nodes"),
                ],
                className="card",
            ),
            html.Div(
                [
                    html.H2(f"{snapshot['avg_battery_soc_pct']:.1f}%"),
                    html.P("Battery SOC"),
                ],
                className="card",
            ),
            html.Div(
                [
                    html.H2(f"{snapshot['total_solar_kw']:.1f} kW"),
                    html.P("Solar Output"),
                ],
                className="card",
            ),
        ],
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(4, 1fr)",
            "gap": "20px",
        },
    )


@app.callback(
    Output("demand-chart", "figure"),
    Input("refresh", "n_intervals"),
)
def update_demand_chart(_):
    times, demand = fetch_demand_timeseries()

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=times,
            y=demand,
            mode="lines",
            name="Cluster Demand",
            line=dict(color="#60a5fa", width=3),
            fill="tozeroy",
            fillcolor="rgba(96, 165, 250, 0.10)",
        )
    )

    fig.update_layout(
        title="Average Cluster Demand (Last 5 Minutes)",
        template="plotly_dark",
        paper_bgcolor="#0f172a",
        plot_bgcolor="#111827",
        margin=dict(l=40, r=40, t=50, b=40),
        height=420,
        font=dict(color="#e5e7eb"),
        xaxis=dict(
            showgrid=True,
            gridcolor="#1f2937",
            zeroline=False,
        ),
        yaxis=dict(
            title="kW",
            showgrid=True,
            gridcolor="#1f2937",
            zeroline=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )

    return fig


@app.callback(
    Output("node-grid", "children"),
    Input("refresh", "n_intervals"),
)
def update_nodes(_):
    nodes = fetch_node_snapshot()

    cards = []
    for node in nodes:
        soc_color = battery_color(node["battery_soc"])

        cards.append(
    html.Div(
        [
            html.H3(
                node["meter_id"].replace("_", " ").title(),
                style={
                    "marginBottom": "12px",
                    "fontSize": "18px",
                    "fontWeight": "600",
                    "color": "#e5e7eb",
                },
            ),

            html.H2(
                f"{node['kw_demand']:.1f} kW",
                style={
                    "margin": "0 0 10px 0",
                    "fontSize": "32px",
                    "color": "#38bdf8",
                },
            ),

            html.P(
                f"Solar {node['solar_kw']:.1f} kW",
                style={
                    "margin": "4px 0",
                    "color": "#94a3b8",
                    "fontSize": "14px",
                },
            ),

            html.P(
                f"Battery {node['battery_soc']:.0f}%",
                style={
                    "margin": "6px 0 2px 0",
                    "color": soc_color,
                    "fontWeight": "700",
                    "fontSize": "15px",
                },
            ),

            battery_bar(node["battery_soc"]),
        ],
        className="card",
    )
)

    return html.Div(
        cards,
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(5, 1fr)",
            "gap": "20px",
            "marginTop": "12px",
        },
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)