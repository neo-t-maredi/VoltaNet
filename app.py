from dash import Dash, Output, Input

from components.cards import build_metric_cards, build_node_cards
from components.charts import build_demand_chart
from components.layout import build_layout
from data.db import (
    fetch_cluster_snapshot,
    fetch_demand_timeseries,
    fetch_node_snapshot,
)

app = Dash(__name__)
app.title = "VoltaNet Live Grid"
app.layout = build_layout()


@app.callback(
    Output("cluster-metrics", "children"),
    Input("refresh", "n_intervals"),
)
def update_metrics(_):
    snapshot = fetch_cluster_snapshot()
    return build_metric_cards(snapshot)


@app.callback(
    Output("demand-chart", "figure"),
    Input("refresh", "n_intervals"),
)
def update_chart(_):
    times, demand = fetch_demand_timeseries()
    return build_demand_chart(times, demand)


@app.callback(
    Output("node-grid", "children"),
    Input("refresh", "n_intervals"),
)
def update_nodes(_):
    nodes = fetch_node_snapshot()
    return build_node_cards(nodes)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)